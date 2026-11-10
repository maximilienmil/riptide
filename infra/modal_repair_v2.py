"""Riptide Track C repair-v2: stronger steering sweep (step 1).

New Modal app ``riptide-tinyaya-steer2`` + train app ``riptide-trackc-v2``.
Does NOT touch the frozen v1 apps/volumes (``riptide-tinyaya-steer``,
``/mnt/vol/steer`` stay as-is).

Grid (per repair brief): layers {16,20,22,24,28} x alpha {0.5,0.8,1.0,1.5}
on the EXISTING steer pairs (train/data/steer_pairs.jsonl), same
stratified 10+10 held-out split (seed 7) as the v1 sweep, same metrics:
held-out margin gain + benign perplexity on 20 control prompts.
Select: largest delta_margin with rel_ppl < 0.05 (discard fluency drops
>5%). Artifacts -> ``/mnt/vol/steer-v2/`` on volume ``riptide-train``.

Usage:
    uvx modal run infra/modal_repair_v2.py::launch_sweep
    uvx modal run infra/modal_repair_v2.py::sweep_status
    uvx modal deploy infra/modal_repair_v2.py   # serving app only
"""

import json
import modal

APP_TRAIN = "riptide-trackc-v2"
APP_STEER2 = "riptide-tinyaya-steer2"
VOL_NAME = "riptide-train"
TINY_AYA = "CohereLabs/tiny-aya-global"

MAX_NEW_TOKENS = 256
MAX_PROMPT_CHARS = 24000

HF_SECRET = modal.Secret.from_name("huggingface-secret")
vol = modal.Volume.from_name(VOL_NAME, create_if_missing=True)

import os as _os

REPO = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
STEER_LOCAL = REPO + "/train/data/steer_pairs.jsonl"
DPO_LOCAL = REPO + "/train/data/dpo.jsonl"
DPO_V4_LOCAL = REPO + "/train/data/dpo.v4.jsonl"

base_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git")
    .pip_install(
        "torch",
        "transformers>=4.48",
        "accelerate",
        "safetensors",
        "huggingface_hub",
    )
)

steer_image = (
    base_image.pip_install("git+https://github.com/Lexsi-Labs/SafeTune.git")
    .add_local_file(STEER_LOCAL, "/data/steer_pairs.jsonl")
    .add_local_file(DPO_LOCAL, "/data/dpo.jsonl")
)

serve_image = base_image.pip_install(
    "git+https://github.com/Lexsi-Labs/SafeTune.git", "fastapi[standard]"
)

# AlignTune image for DPO-v2 (mirrors infra/modal_train.py's workaround:
# trl WITHOUT the vllm extra + aligntune --no-deps). dpo.v4.jsonl must
# exist locally before launch (it is baked into the image at build time).
dpo_v2_image = (
    base_image.apt_install("pkg-config", "libicu-dev")
    .pip_install(
        "trl==1.7.1",
        "peft",
        "datasets",
        "tyro",
        "cut_cross_entropy",
        "hf_transfer",
        "msgspec",
        "nest-asyncio",
        "pillow",
        "regex",
        "diffusers",
        "wandb",
        "curatorkit",
        "pypdf",
        "python-docx",
        "evaluate",
        "rouge-score",
        "bert-score",
        "sacrebleu",
        "lm-eval",
        "nltk",
        "scikit-learn",
        "sqlglot",
        "pandas",
        "matplotlib",
        "tensorboard",
        "bitsandbytes",
        "torchao",
        "torchvision",
        "sentencepiece",
    )
    .run_commands(
        "pip install --no-deps git+https://github.com/Lexsi-Labs/aligntune.git"
    )
    .add_local_file(DPO_V4_LOCAL, "/data/dpo.v4.jsonl")
)

serve_lora_image = base_image.pip_install("peft", "fastapi[standard]")

train_app = modal.App(APP_TRAIN)
steer2_app = modal.App(APP_STEER2)
APP_DPO2 = "riptide-tinyaya-dpo2"
dpo2_app = modal.App(APP_DPO2)

# Winner of the lr sweep (held-out margin 11.47 vs 9.66, both acc 1.0):
# lr=1e-4. Loser adapter stays on the volume at dpo-v2-lora-lr5e-5.
DPO2_ADAPTER_DIR = "/mnt/vol/dpo-v2-lora-lr1e-4"

LAYERS = [16, 20, 22, 24, 28]
ALPHAS = [0.5, 0.8, 1.0, 1.5]


@train_app.function(
    gpu="A10G",
    timeout=7200,
    secrets=[HF_SECRET],
    image=steer_image,
    volumes={"/mnt/vol": vol},
)
def steer_sweep_v2():
    """Stronger CAA sweep: 5 layers x 4 alphas = 20 settings."""
    import os
    import random
    import traceback

    import time as _time
    os.makedirs("/mnt/vol/steer-v2", exist_ok=True)
    with open("/mnt/vol/steer-v2/progress.txt", "w") as fh:
        fh.write("started pid=%d\n" % os.getpid())
    try:
        vol.commit()
    except Exception as e:
        with open("/mnt/vol/steer-v2/progress.txt", "a") as fh:
            fh.write("commit_failed %r\n" % (e,))
    try:
        return _steer_sweep_v2_inner()
    except BaseException as e:
        with open("/mnt/vol/steer-v2/error.txt", "w") as fh:
            fh.write("REPR: %r\n" % (e,))
            fh.write(traceback.format_exc())
        try:
            vol.commit()
        except Exception:
            pass
        raise


def _steer_sweep_v2_inner():
    import os
    import random

    import torch
    from transformers import AutoTokenizer

    from safetune.runner.utils.model_utils import load_model
    try:
        from safetune.interventions.steer.caa import (
            CAAConfig, CAAModel, extract_caa_vectors)
    except ImportError:
        from safetune.steer.caa import (  # type: ignore[no-redef]
            CAAConfig, CAAModel, extract_caa_vectors)
    from safetune._refusal_helpers import _get_decoder_layers

    out_dir = "/mnt/vol/steer-v2"
    os.makedirs(out_dir, exist_ok=True)

    def _load_rows(path):
        with open(path) as fh:
            return [json.loads(line) for line in fh if line.strip()]

    pairs = _load_rows("/data/steer_pairs.jsonl")
    by_dir = {"sycophancy": [r for r in pairs if r["direction"] == "sycophancy"],
              "engagement": [r for r in pairs if r["direction"] == "engagement"]}
    rng = random.Random(7)
    for v in by_dir.values():
        rng.shuffle(v)
    held = by_dir["sycophancy"][:10] + by_dir["engagement"][:10]
    rng.shuffle(held)
    train_pairs = by_dir["sycophancy"][10:] + by_dir["engagement"][10:]

    dpo_rows = _load_rows("/data/dpo.jsonl")
    benign_pool = [r for r in dpo_rows if r.get("family") == "control"]
    rng.shuffle(benign_pool)
    benign = [(r["prompt"], r["chosen"]) for r in benign_pool[:20]]

    tok = AutoTokenizer.from_pretrained(TINY_AYA, trust_remote_code=False)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = load_model(TINY_AYA, dtype=None, device="cuda")
    model.eval()
    try:
        dev = next(model.parameters()).device
    except StopIteration:
        dev = "cuda"
    n_layers = len(_get_decoder_layers(model))
    layers = [L for L in LAYERS if 0 <= L < n_layers]
    print("N_LAYERS=%d GRID_LAYERS=%s" % (n_layers, layers))

    pos = [(r.get("prompt") or "") + "\n" + r["positive"]
           for r in train_pairs]
    neg = [(r.get("prompt") or "") + "\n" + r["negative"]
           for r in train_pairs]
    vectors = extract_caa_vectors(
        model, tok, pos, neg,
        CAAConfig(target_layers=layers, pool_method="last_token",
                  normalize=False))
    print("CAA_NORMS %s"
          % json.dumps({k: round(float(v.norm()), 4)
                        for k, v in vectors.items()}))

    @torch.no_grad()
    def _cont_logprob(context, continuation):
        ctx_ids = tok(context, return_tensors="pt")["input_ids"].to(dev)
        full_ids = tok(context + continuation,
                        return_tensors="pt")["input_ids"].to(dev)
        n_ctx = ctx_ids.shape[1]
        if full_ids.shape[1] <= n_ctx:
            return None
        out = model(full_ids)
        logp = torch.log_softmax(out.logits[0, n_ctx - 1:-1, :], dim=-1)
        target = full_ids[0, n_ctx:]
        return (float(logp.gather(1, target.unsqueeze(1)).sum()),
                int(target.numel()))

    def _margins():
        ms = []
        for r in held:
            ctx = r.get("prompt") or ""
            lp_pos = _cont_logprob(ctx, "\n" + r["positive"])
            lp_neg = _cont_logprob(ctx, "\n" + r["negative"])
            if lp_pos is None or lp_neg is None:
                continue
            ms.append(lp_pos[0] - lp_neg[0])
        return ms

    def _benign_ppl():
        import math
        tot_nll, tot_tok = 0.0, 0
        for ctx, ref in benign:
            v = _cont_logprob(ctx, "\n" + ref)
            if v is None:
                continue
            tot_nll += -v[0]
            tot_tok += v[1]
        return math.exp(tot_nll / max(tot_tok, 1)), tot_tok

    base_margins = _margins()
    base_mean = sum(base_margins) / max(len(base_margins), 1)
    base_ppl, _ = _benign_ppl()
    print("BASE margin=%.4f ppl=%.4f" % (base_mean, base_ppl))
    results = []
    for layer in layers:
        vec = vectors[layer]
        for alpha in ALPHAS:
            steered = CAAModel(model, {layer: vec}, strength=alpha)
            steered.install()
            try:
                ms = _margins()
                mean_m = sum(ms) / max(len(ms), 1)
                ppl, n = _benign_ppl()
            finally:
                steered.remove()
            row = {"layer": layer, "alpha": alpha, "n": len(ms),
                   "base_margin": round(base_mean, 4),
                   "margin": round(mean_m, 4),
                   "delta_margin": round(mean_m - base_mean, 4),
                   "base_benign_ppl": round(base_ppl, 4),
                   "benign_ppl": round(ppl, 4),
                   "benign_tokens": n,
                   "rel_ppl": round(ppl / max(base_ppl, 1e-9) - 1, 4)}
            results.append(row)
            print("SWEEP " + json.dumps(row))
    feas = [r for r in results if r["rel_ppl"] < 0.05]
    pool = feas or results
    best = sorted(pool, key=lambda r: (-r["delta_margin"], r["alpha"],
                                       r["layer"]))[0]
    print("FEASIBLE %d/20 BEST %s" % (len(feas), json.dumps(best)))

    torch.save({int(k): v.cpu() for k, v in vectors.items()},
               os.path.join(out_dir, "vectors.pt"))
    with open(os.path.join(out_dir, "config.json"), "w") as fh:
        json.dump({"layer": best["layer"], "alpha": best["alpha"],
                   "grid_layers": layers, "grid_alphas": ALPHAS,
                   "n_layers": n_layers,
                   "pool_method": "last_token", "normalize": False,
                   "held_out": len(held), "extract_on": len(train_pairs),
                   "benign_controls": len(benign), "seed": 7,
                   "select_rule": "max delta_margin with rel_ppl<0.05"},
                  fh, indent=2)
    with open(os.path.join(out_dir, "sweep.json"), "w") as fh:
        json.dump({"base_margin": base_mean, "base_benign_ppl": base_ppl,
                   "results": results, "best": best,
                   "feasible_count": len(feas)}, fh, indent=1)
    vol.commit()
    return {"best": best, "feasible": len(feas), "n_results": len(results)}


@train_app.function(
    secrets=[HF_SECRET],
    image=steer_image,
    volumes={"/mnt/vol": vol},
)
def sweep_status():
    """Fast poll: v2 sweep table, no GPU."""
    import os

    out = {"files": sorted(os.listdir("/mnt/vol/steer-v2"))
           if os.path.isdir("/mnt/vol/steer-v2") else None,
           "best": None, "n_results": 0}
    sp = "/mnt/vol/steer-v2/sweep.json"
    if os.path.exists(sp):
        try:
            with open(sp) as fh:
                sweep = json.load(fh)
            out["n_results"] = len(sweep.get("results", []))
            out["best"] = sweep.get("best")
            out["results"] = sweep.get("results")
        except Exception as exc:
            out["error"] = str(exc)[:300]
    print("STEER_V2_STATUS " + json.dumps(
        {k: v for k, v in out.items() if k != "results"}, default=str)[:2000])
    return out


# ---------------------------------------------------------------------------
# DPO-v2: bigger/longer DPO on dpo.v4.jsonl (frozen 709 + fresh f6/f7 hard
# pairs). 3 epochs, lr sweep {5e-5, 1e-4}; r=16, beta=0.1, eff-batch 4.
# One adapter dir per lr on the volume; serve the winner as dpo2.
# ---------------------------------------------------------------------------

def _dpo_v2_train_inner(learning_rate: float, tag: str):
    import glob
    import os
    import shutil

    import torch
    from aligntune.core.backend_factory import create_rl_trainer

    out_dir = "/mnt/vol/dpo-v2-ckpt-%s" % tag
    lora_dir = "/mnt/vol/dpo-v2-lora-%s" % tag
    os.makedirs(out_dir, exist_ok=True)

    hyper = dict(
        model_name=TINY_AYA,
        dataset_name="/data/dpo.v4.jsonl",
        algorithm="dpo",
        backend="trl",
        num_epochs=3,
        batch_size=2,
        gradient_accumulation_steps=2,
        learning_rate=learning_rate,
        max_seq_length=1024,
        use_lora=True,
        lora_r=16,
        lora_alpha=32,
        beta=0.1,
        val_split_ratio=0.1,
        split_seed=42,
        eval_strategy="steps",
        eval_steps=40,
        logging_steps=5,
        save_steps=80,
        save_total_limit=2,
        seed=42,
        use_logits_to_keep=True,
        output_dir=out_dir,
    )
    with open(os.path.join(out_dir, "hyperparams.json"), "w") as fh:
        json.dump(hyper, fh, indent=2)

    trainer = create_rl_trainer(**hyper)
    result = trainer.train()
    print("TRAIN_RESULT " + json.dumps(result, default=str)[:2000])

    curves = {"train": [], "eval": [], "result": result}
    states = sorted(glob.glob(os.path.join(out_dir, "**/trainer_state.json"),
                              recursive=True))
    best_state = None
    for sp in states:
        try:
            with open(sp) as fh:
                hist = json.load(fh).get("log_history", [])
        except Exception:
            continue
        if best_state is None or len(hist) > len(best_state[1]):
            best_state = (sp, hist)
    if best_state is not None:
        for entry in best_state[1]:
            if "eval_loss" in entry:
                curves["eval"].append({
                    "step": entry.get("step"),
                    "eval_loss": entry.get("eval_loss"),
                    "eval_rewards/chosen": entry.get("eval_rewards/chosen"),
                    "eval_rewards/rejected": entry.get(
                        "eval_rewards/rejected"),
                    "eval_rewards/margins": entry.get("eval_rewards/margins"),
                    "eval_rewards/accuracies":
                        entry.get("eval_rewards/accuracies"),
                })
            elif "loss" in entry:
                curves["train"].append({
                    "step": entry.get("step"),
                    "loss": entry.get("loss"),
                    "rewards/chosen": entry.get("rewards/chosen"),
                    "rewards/rejected": entry.get("rewards/rejected"),
                    "rewards/margins": entry.get("rewards/margins"),
                    "rewards/accuracies": entry.get("rewards/accuracies"),
                })
    with open(os.path.join(out_dir, "curves.json"), "w") as fh:
        json.dump(curves, fh, indent=1)
    vol.commit()

    os.makedirs(lora_dir, exist_ok=True)
    adapter_files = []
    for pat in ("adapter_model.safetensors", "adapter_model.bin",
                "adapter_config.json"):
        adapter_files.extend(
            glob.glob(os.path.join(out_dir, "**/" + pat), recursive=True))

    def _rank(p):
        return (0, p) if "/checkpoint" not in p else (1, p)
    adapter_files.sort(key=_rank)
    seen, copied = set(), []
    for src in adapter_files:
        name = os.path.basename(src)
        if name in seen:
            continue
        seen.add(name)
        dst = os.path.join(lora_dir, name)
        shutil.copyfile(src, dst)
        copied.append({"file": name,
                       "bytes": os.path.getsize(dst),
                       "from": src})
    with open(os.path.join(lora_dir, "train_config.json"), "w") as fh:
        json.dump({"hyperparams": hyper,
                   "copied_from": copied,
                   "torch": torch.__version__}, fh, indent=2)
    vol.commit()
    print("ADAPTER_FILES " + json.dumps(copied)[:2000])
    if curves["eval"]:
        print("EVAL_LAST " + json.dumps(curves["eval"][-1])[:1000])
    if curves["train"]:
        print("TRAIN_LAST " + json.dumps(curves["train"][-1])[:1000])
    return {"adapter_files": copied,
            "eval_last": curves["eval"][-1] if curves["eval"] else None,
            "train_last": curves["train"][-1] if curves["train"] else None}


@train_app.function(
    gpu="A10G",
    timeout=10800,
    secrets=[HF_SECRET],
    image=dpo_v2_image,
    volumes={"/mnt/vol": vol},
)
def dpo_train_v2(learning_rate: float = 5e-5, tag: str = "lr5e-5"):
    """DPO LoRA r=16, 3 epochs on dpo.v4.jsonl; adapter -> volume."""
    import traceback

    try:
        return _dpo_v2_train_inner(learning_rate, tag)
    except BaseException as e:  # noqa: BLE001 - surface remote errors
        with open("/mnt/vol/dpo-v2-error-%s.txt" % tag, "w") as fh:
            fh.write("REPR: %r\n" % (e,))
            fh.write(traceback.format_exc())
        try:
            vol.commit()
        except Exception:
            pass
        raise


@train_app.function(
    secrets=[HF_SECRET],
    image=dpo_v2_image,
    volumes={"/mnt/vol": vol},
)
def dpo_v2_status(tag: str = "lr5e-5"):
    """Fast poll: adapter presence + curve tail, no GPU."""
    import glob
    import os

    out = {"tag": tag,
           "adapter": sorted(os.listdir("/mnt/vol/dpo-v2-lora-%s" % tag))
           if os.path.isdir("/mnt/vol/dpo-v2-lora-%s" % tag) else None,
           "eval_last": None, "train_last": None,
           "n_train_logs": 0, "n_eval_logs": 0}
    cp = "/mnt/vol/dpo-v2-ckpt-%s/curves.json" % tag
    if os.path.exists(cp):
        try:
            with open(cp) as fh:
                curves = json.load(fh)
            out["n_train_logs"] = len(curves.get("train", []))
            out["n_eval_logs"] = len(curves.get("eval", []))
            if curves.get("eval"):
                out["eval_last"] = curves["eval"][-1]
            if curves.get("train"):
                out["train_last"] = curves["train"][-1]
        except Exception as exc:
            out["curves_error"] = str(exc)[:300]
    else:
        states = sorted(glob.glob(
            "/mnt/vol/dpo-v2-ckpt-%s/**/trainer_state.json" % tag,
            recursive=True))
        out["trainer_states"] = states
    print("DPO_V2_STATUS " + json.dumps(out, default=str)[:2000])
    return out


@dpo2_app.cls(
    gpu="A10G",
    timeout=600,
    scaledown_window=60,
    min_containers=0,
    max_containers=2,
    secrets=[HF_SECRET],
    image=serve_lora_image,
    volumes={"/mnt/vol": vol},
)
class Dpo2Chat:
    @modal.enter()
    def load(self):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        from peft import PeftModel

        self.tok = AutoTokenizer.from_pretrained(
            TINY_AYA, trust_remote_code=False)
        base = AutoModelForCausalLM.from_pretrained(
            TINY_AYA,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            trust_remote_code=False,
        )
        self.model = PeftModel.from_pretrained(base, DPO2_ADAPTER_DIR)
        self.model.eval()

    @modal.fastapi_endpoint(method="POST")
    def chat(self, item: dict):
        import time

        import torch
        from fastapi.responses import JSONResponse

        t0 = time.time()
        messages = item.get("messages", [])
        if not isinstance(messages, list) or not messages:
            return JSONResponse(
                status_code=400,
                content={"error": "expected non-empty 'messages' list"})
        max_new = max(1, min(int(item.get("max_new_tokens", MAX_NEW_TOKENS)),
                             MAX_NEW_TOKENS))
        try:
            prompt = self.tok.apply_chat_template(
                messages, add_generation_prompt=True, tokenize=False)
        except Exception as exc:
            return JSONResponse(
                status_code=400, content={"error": f"bad messages: {exc}"})
        if len(prompt) > MAX_PROMPT_CHARS:
            return JSONResponse(
                status_code=413, content={"error": "prompt too long"})
        try:
            dev = next(self.model.parameters()).device
        except StopIteration:
            dev = "cuda"
        enc = self.tok(prompt, return_tensors="pt").to(dev)
        try:
            with torch.no_grad():
                out = self.model.generate(
                    **enc, max_new_tokens=max_new, do_sample=False,
                    pad_token_id=self.tok.pad_token_id
                    or self.tok.eos_token_id)
        except Exception as exc:
            return JSONResponse(
                status_code=500,
                content={"error": f"generation failed: {exc}"})
        new_tokens = out[0][enc["input_ids"].shape[1]:]
        text = self.tok.decode(new_tokens, skip_special_tokens=True).strip()
        return {"text": text,
                "choices": [{"message": {"role": "assistant",
                                         "content": text}}],
                "gen_tokens": len(new_tokens),
                "elapsed_s": round(time.time() - t0, 2)}


@steer2_app.cls(
    gpu="A10G",
    timeout=600,
    scaledown_window=60,
    min_containers=0,
    max_containers=2,
    secrets=[HF_SECRET],
    image=serve_image,
    volumes={"/mnt/vol": vol},
)
class Steer2Chat:
    @modal.enter()
    def load(self):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        from safetune.runner.utils.model_utils import load_model
        try:
            from safetune.interventions.steer.caa import CAAModel
        except ImportError:
            from safetune.steer.caa import CAAModel  # type: ignore[no-redef]

        self.tok = AutoTokenizer.from_pretrained(
            TINY_AYA, trust_remote_code=False)
        base = AutoModelForCausalLM.from_pretrained(
            TINY_AYA,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            trust_remote_code=False,
        )
        self.model = base
        self.model.eval()
        with open("/mnt/vol/steer-v2/config.json") as fh:
            cfg = json.load(fh)
        vecs = torch.load("/mnt/vol/steer-v2/vectors.pt", map_location="cpu",
                          weights_only=True)
        layer, alpha = int(cfg["layer"]), float(cfg["alpha"])
        dev = next(self.model.parameters()).device
        CAAModel(self.model, {layer: vecs[layer].to(dev)},
                 strength=alpha).install()
        self.steer_cfg = {"layer": layer, "alpha": alpha}

    @modal.fastapi_endpoint(method="POST")
    def chat(self, item: dict):
        import time

        import torch
        from fastapi.responses import JSONResponse

        t0 = time.time()
        messages = item.get("messages", [])
        if not isinstance(messages, list) or not messages:
            return JSONResponse(
                status_code=400,
                content={"error": "expected non-empty 'messages' list"})
        max_new = max(1, min(int(item.get("max_new_tokens", MAX_NEW_TOKENS)),
                             MAX_NEW_TOKENS))
        try:
            prompt = self.tok.apply_chat_template(
                messages, add_generation_prompt=True, tokenize=False)
        except Exception as exc:
            return JSONResponse(
                status_code=400, content={"error": f"bad messages: {exc}"})
        if len(prompt) > MAX_PROMPT_CHARS:
            return JSONResponse(
                status_code=413, content={"error": "prompt too long"})
        try:
            dev = next(self.model.parameters()).device
        except StopIteration:
            dev = "cuda"
        enc = self.tok(prompt, return_tensors="pt").to(dev)
        try:
            with torch.no_grad():
                out = self.model.generate(
                    **enc, max_new_tokens=max_new, do_sample=False,
                    pad_token_id=self.tok.pad_token_id
                    or self.tok.eos_token_id)
        except Exception as exc:
            return JSONResponse(
                status_code=500,
                content={"error": f"generation failed: {exc}"})
        new_tokens = out[0][enc["input_ids"].shape[1]:]
        text = self.tok.decode(new_tokens, skip_special_tokens=True).strip()
        return {"text": text,
                "choices": [{"message": {"role": "assistant",
                                         "content": text}}],
                "gen_tokens": len(new_tokens),
                "elapsed_s": round(time.time() - t0, 2)}


@train_app.function(
    gpu="A10G",
    timeout=1800,
    secrets=[HF_SECRET],
    image=steer_image,
    volumes={"/mnt/vol": vol},
)
def diag_extract():
    """Minimal probe: imports, model load, layer count, tiny extraction."""
    import os
    import traceback

    log = []
    try:
        import torch
        from transformers import AutoTokenizer
        log.append("imports_torch_ok")
        from safetune.runner.utils.model_utils import load_model
        log.append("imports_load_model_ok")
        try:
            from safetune.interventions.steer.caa import (
                CAAConfig, CAAModel, extract_caa_vectors)
            log.append("imports_caa_canonical_ok")
        except ImportError as e:
            log.append("imports_caa_canonical_FAIL " + str(e)[:200])
            from safetune.steer.caa import (  # type: ignore[no-redef]
                CAAConfig, CAAModel, extract_caa_vectors)
            log.append("imports_caa_alias_ok")
        from safetune._refusal_helpers import _get_decoder_layers
        log.append("imports_decoder_layers_ok")
        tok = AutoTokenizer.from_pretrained(TINY_AYA, trust_remote_code=False)
        log.append("tokenizer_ok")
        model = load_model(TINY_AYA, dtype=None, device="cuda")
        log.append("model_ok")
        n_layers = len(_get_decoder_layers(model))
        log.append("n_layers=%d" % n_layers)
        import json as _json
        rows = [_json.loads(l) for l in
                open("/data/steer_pairs.jsonl") if l.strip()][:4]
        pos = [(r.get("prompt") or "") + "\n" + r["positive"] for r in rows]
        neg = [(r.get("prompt") or "") + "\n" + r["negative"] for r in rows]
        vecs = extract_caa_vectors(
            model, tok, pos, neg,
            CAAConfig(target_layers=[22], pool_method="last_token",
                      normalize=False))
        log.append("extract_ok norms=" + str(
            {k: round(float(v.norm()), 4) for k, v in vecs.items()}))
    except Exception:
        log.append("TRACEBACK:\n" + traceback.format_exc()[-3000:])
    os.makedirs("/mnt/vol/steer-v2", exist_ok=True)
    with open("/mnt/vol/steer-v2/diag.txt", "w") as fh:
        fh.write("\n".join(log) + "\n")
    vol.commit()
    print("DIAG " + "\nDIAG ".join(log))
    return {"log": log}


@train_app.local_entrypoint()
def launch_sweep():
    call = steer_sweep_v2.spawn()
    print("SPAWNED steer_sweep_v2 %s" % (call,))


@train_app.local_entrypoint()
def run_sweep_attached():
    print("RESULT " + json.dumps(steer_sweep_v2.remote(), default=str)[:2000])


@train_app.local_entrypoint()
def launch_dpo_v2(lr: float = 5e-5, tag: str = "lr5e-5"):
    call = dpo_train_v2.spawn(learning_rate=lr, tag=tag)
    print("SPAWNED dpo_train_v2 lr=%s tag=%s %s" % (lr, tag, call))


@train_app.local_entrypoint()
def run_dpo_v2_attached(lr: float = 5e-5, tag: str = "lr5e-5"):
    print("RESULT " + json.dumps(
        dpo_train_v2.remote(learning_rate=lr, tag=tag),
        default=str)[:2000])


@train_app.local_entrypoint()
def job_status():
    print("STEER_V2 " + json.dumps(sweep_status.remote(), default=str))
