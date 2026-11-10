"""Riptide Track C — training + serving on Modal (Tiny Aya Global).

One file, three Modal apps:

- ``riptide-trackc-train`` (functions, not deployed): DPO LoRA via the
  AlignTune TRL path on ``train/data/dpo.jsonl`` (709 pairs, 10% held out
  for eval loss / reward accuracy), and the SafeTune/CAA steering sweep on
  ``train/data/steer_pairs.jsonl``. Artifacts land on the ``riptide-train``
  Modal volume (``/mnt/vol/dpo-lora/``, ``/mnt/vol/steer/``).
- ``riptide-tinyaya-dpo`` (deployed app, scale-to-zero): base + LoRA chat.
- ``riptide-tinyaya-steer`` (deployed app, scale-to-zero): base + steering.

GPU note: L4 ($0.80/hr) is the cheapest card that fits this work. Per the
tok/s table in research/stack-smoke.md §7.2, batch-1 Tiny Aya runs
~18.8-27.9 tok/s on L4 vs 24.8 tok/s on A10G ($1.10/hr), so L4 is also
cheapest per tok/s for single-stream generation; T4 ($0.59/hr) is cheaper
per hour but its 16 GB is too tight for 3.3B DPO. A10G is the fallback if
the L4 pool is exhausted (as on 2026-11-03/04).

Usage (from the repo root)::

    uvx modal volume create riptide-train          # once
    uvx modal run infra/modal_train.py::launch_job --which dpo    # detached
    uvx modal run infra/modal_train.py::launch_job --which steer  # detached
    uvx modal run infra/modal_train.py::job_status                # poll
    uvx modal deploy infra/modal_train.py                         # serving apps
    uv run python train/smoke_endpoints.py                        # 3-turn smokes

DPO config (research/track-c.md §"Planned training config"): r=16,
alpha=32, lr=5e-5, beta=0.1, effective batch 4 (2 x 2 accum), 2 epochs,
max_seq_length 1024. 10% eval split (seed 42) logs eval loss, reward
margins and reward accuracy every 40 steps.
"""

import json
import modal

APP_TRAIN = "riptide-trackc-train"
APP_DPO = "riptide-tinyaya-dpo"
APP_STEER = "riptide-tinyaya-steer"
VOL_NAME = "riptide-train"
TINY_AYA = "CohereLabs/tiny-aya-global"

# Request/response shape (matches infra/modal_endpoint.py, which matches
# riptide's ``modal`` provider): POST {"model", "messages", "max_new_tokens"}
# -> {"text", "choices", ...}. URL is not secret; never send tokens.
MAX_NEW_TOKENS = 256
# 12-turn histories run ~20-24k chars; Tiny Aya's 8k-token window holds
# ~32k chars, so 24k stays safely inside it.
MAX_PROMPT_CHARS = 24000

HF_SECRET = modal.Secret.from_name("huggingface-secret")
vol = modal.Volume.from_name(VOL_NAME, create_if_missing=True)

import os as _os

REPO = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
DPO_LOCAL = REPO + "/train/data/dpo.jsonl"
STEER_LOCAL = REPO + "/train/data/steer_pairs.jsonl"

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

# AlignTune image: same workaround as infra/modal_smoke.py (trl WITHOUT the
# vllm extra + small DPO-path deps, then aligntune --no-deps). DPO never
# touches vLLM. Data files are baked into the image.
train_image = (
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
    .add_local_file(DPO_LOCAL, "/data/dpo.jsonl")
    .add_local_file(STEER_LOCAL, "/data/steer_pairs.jsonl")
)

steer_image = (
    base_image.pip_install("git+https://github.com/Lexsi-Labs/SafeTune.git")
    .add_local_file(DPO_LOCAL, "/data/dpo.jsonl")
    .add_local_file(STEER_LOCAL, "/data/steer_pairs.jsonl")
)

serve_lora_image = base_image.pip_install("peft", "fastapi[standard]")
serve_steer_image = base_image.pip_install(
    "git+https://github.com/Lexsi-Labs/SafeTune.git", "fastapi[standard]"
)

train_app = modal.App(APP_TRAIN)
dpo_app = modal.App(APP_DPO)
steer_app = modal.App(APP_STEER)


# ---------------------------------------------------------------------------
# DPO LoRA training (AlignTune TRL path, Tiny Aya Global)
# ---------------------------------------------------------------------------

@train_app.function(
    # A10G: L4 pool exhausted again on 2026-11-04 (same as 11-03); L4 is the
    # cheapest fit per the tok/s table but never scheduled, so fall back.
    gpu="A10G",
    timeout=10800,
    secrets=[HF_SECRET],
    image=train_image,
    volumes={"/mnt/vol": vol},
)
def dpo_train():
    """DPO LoRA r=16 on dpo.jsonl; 10% eval split; adapter -> volume."""
    import glob
    import os
    import shutil

    import torch
    from aligntune.core.backend_factory import create_rl_trainer

    out_dir = "/mnt/vol/dpo-ckpt"
    lora_dir = "/mnt/vol/dpo-lora"
    os.makedirs(out_dir, exist_ok=True)

    hyper = dict(
        model_name=TINY_AYA,
        dataset_name="/data/dpo.jsonl",
        algorithm="dpo",
        backend="trl",
        num_epochs=2,  # 638 train pairs / eff-batch 4 ~= 160 steps/epoch
        batch_size=2,  # x gradient_accumulation_steps=2 -> effective 4
        gradient_accumulation_steps=2,
        learning_rate=5e-5,
        max_seq_length=1024,
        use_lora=True,
        lora_r=16,
        lora_alpha=32,
        beta=0.1,
        val_split_ratio=0.1,  # ~71 held-out pairs for eval loss/accuracy
        split_seed=42,
        eval_strategy="steps",
        eval_steps=40,
        logging_steps=5,
        save_steps=80,
        save_total_limit=2,
        seed=42,
        use_logits_to_keep=True,  # completion-only logits; less VRAM
        output_dir=out_dir,
    )
    with open(os.path.join(out_dir, "hyperparams.json"), "w") as fh:
        json.dump(hyper, fh, indent=2)

    trainer = create_rl_trainer(**hyper)
    result = trainer.train()
    print("TRAIN_RESULT " + json.dumps(result, default=str)[:2000])

    # -- collect training curves from checkpoint trainer_state.json files --
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
                    "eval_rewards/rejected": entry.get("eval_rewards/rejected"),
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

    # -- copy adapter-only files to /mnt/vol/dpo-lora (no base weights) --
    os.makedirs(lora_dir, exist_ok=True)
    adapter_files = []
    for pat in ("adapter_model.safetensors", "adapter_model.bin",
                "adapter_config.json"):
        adapter_files.extend(
            glob.glob(os.path.join(out_dir, "**/" + pat), recursive=True))
    # Prefer the final saved model dir over intermediate checkpoints.
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
    print("CURVES train_steps=%d eval_steps=%d" % (len(curves["train"]),
                                                   len(curves["eval"])))
    if curves["eval"]:
        print("EVAL_LAST " + json.dumps(curves["eval"][-1])[:1000])
    if curves["train"]:
        print("TRAIN_LAST " + json.dumps(curves["train"][-1])[:1000])
    return {"adapter_files": copied,
            "n_train_logs": len(curves["train"]),
            "n_eval_logs": len(curves["eval"]),
            "eval_last": curves["eval"][-1] if curves["eval"] else None,
            "train_last": curves["train"][-1] if curves["train"] else None}


@train_app.function(
    secrets=[HF_SECRET],
    image=train_image,
    volumes={"/mnt/vol": vol},
)
def dpo_status():
    """Fast poll: adapter presence + curve tail, no GPU."""
    import glob
    import os

    out = {"adapter": sorted(os.listdir("/mnt/vol/dpo-lora"))
           if os.path.isdir("/mnt/vol/dpo-lora") else None,
           "ckpt": sorted(os.listdir("/mnt/vol/dpo-ckpt"))
           if os.path.isdir("/mnt/vol/dpo-ckpt") else None,
           "eval_last": None, "train_last": None,
           "n_train_logs": 0, "n_eval_logs": 0}
    cp = "/mnt/vol/dpo-ckpt/curves.json"
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
        states = sorted(glob.glob("/mnt/vol/dpo-ckpt/**/trainer_state.json",
                                  recursive=True))
        out["trainer_states"] = states
    print("DPO_STATUS " + json.dumps(out, default=str)[:2000])
    return out


# ---------------------------------------------------------------------------
# Steering sweep (SafeTune CAA on steer_pairs.jsonl, Tiny Aya Global)
# ---------------------------------------------------------------------------

@train_app.function(
    # A10G: same L4-pool exhaustion as dpo_train (2026-11-04).
    gpu="A10G",
    timeout=7200,
    secrets=[HF_SECRET],
    image=steer_image,
    volumes={"/mnt/vol": vol},
)
def steer_sweep():
    """CAA sycophancy/engagement direction; sweep layer x alpha.

    Extract on 115 pairs, sweep on 20 held-out steer pairs + 20 benign
    control prompts. Selection: largest held-out margin gain (steered minus
    base logP(positive) - logP(negative)) with benign perplexity increase
    under 10%.
    """
    import os
    import random

    import torch
    from transformers import AutoTokenizer

    from safetune.runner.utils.model_utils import load_model
    try:  # canonical location on main
        from safetune.interventions.steer.caa import (
            CAAConfig, CAAModel, extract_caa_vectors)
    except ImportError:  # alias used by examples/quickstart.py
        from safetune.steer.caa import (  # type: ignore[no-redef]
            CAAConfig, CAAModel, extract_caa_vectors)
    from safetune._refusal_helpers import _get_decoder_layers

    out_dir = "/mnt/vol/steer"
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
    # Stratified 10 + 10 held-out; extraction sees the other 115.
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
    fracs = [0.25, 0.375, 0.5, 0.625, 0.75]
    layers = sorted({min(n_layers - 1, max(0, int(n_layers * f)))
                     for f in fracs})
    alphas = [0.1, 0.2, 0.3, 0.5]

    def _full(positive, negative, ctx):
        return (ctx or "") + "\n" + positive, (ctx or "") + "\n" + negative

    pos = [_full(r["positive"], r["negative"], r.get("prompt"))[0]
           for r in train_pairs]
    neg = [_full(r["positive"], r["negative"], r.get("prompt"))[1]
           for r in train_pairs]
    vectors = extract_caa_vectors(
        model, tok, pos, neg,
        CAAConfig(target_layers=layers, pool_method="last_token",
                  normalize=False))
    print("CAA_LAYERS n=%d layers=%s norms=%s"
          % (n_layers, layers,
             {k: round(float(v.norm()), 4) for k, v in vectors.items()}))

    @torch.no_grad()
    def _cont_logprob(context, continuation):
        ctx_ids = tok(context, return_tensors="pt")["input_ids"].to(dev)
        full_ids = tok(context + continuation,
                        return_tensors="pt")["input_ids"].to(dev)
        n_ctx = ctx_ids.shape[1]
        if full_ids.shape[1] <= n_ctx:  # tokenizer merge edge; skip
            return None
        out = model(full_ids)
        logp = torch.log_softmax(out.logits[0, n_ctx - 1:-1, :], dim=-1)
        target = full_ids[0, n_ctx:]
        return (float(logp.gather(1, target.unsqueeze(1)).sum()),
                int(target.numel()))

    def _margins(wrapped):
        ms = []
        for r in held:
            ctx = r.get("prompt") or ""
            lp_pos = _cont_logprob(ctx, "\n" + r["positive"])
            lp_neg = _cont_logprob(ctx, "\n" + r["negative"])
            if lp_pos is None or lp_neg is None:
                continue
            ms.append(lp_pos[0] - lp_neg[0])
        return ms

    def _benign_ppl(wrapped):
        import math
        tot_nll, tot_tok = 0.0, 0
        for ctx, ref in benign:
            v = _cont_logprob(ctx, "\n" + ref)
            if v is None:
                continue
            tot_nll += -v[0]
            tot_tok += v[1]
        mean_nll = tot_nll / max(tot_tok, 1)
        return math.exp(mean_nll), tot_tok

    base_margins = _margins(None)
    base_mean = sum(base_margins) / max(len(base_margins), 1)
    base_ppl, _ = _benign_ppl(None)
    results = []
    for layer in layers:
        vec = vectors[layer]
        for alpha in alphas:
            steered = CAAModel(model, {layer: vec}, strength=alpha)
            steered.install()
            try:
                ms = _margins(steered)
                mean_m = sum(ms) / max(len(ms), 1)
                ppl, n = _benign_ppl(steered)
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
    feas = [r for r in results if r["rel_ppl"] < 0.10]
    pool = feas or results
    best = sorted(pool, key=lambda r: (-r["delta_margin"], r["alpha"],
                                       r["layer"]))[0]
    print("STEER_BEST " + json.dumps(best))

    # One sample generation for the report (base vs steered).
    sample_ctx = held[0].get("prompt") or ""
    prompt = tok.apply_chat_template(
        [{"role": "user", "content": sample_ctx[:800]}],
        add_generation_prompt=True, tokenize=False)
    enc = tok(prompt, return_tensors="pt").to(dev)
    with torch.no_grad():
        base_out = model.generate(**enc, max_new_tokens=64, do_sample=False,
                                  pad_token_id=tok.pad_token_id)
    steered = CAAModel(model, {best["layer"]: vectors[best["layer"]]},
                       strength=best["alpha"])
    steered.install()
    try:
        with torch.no_grad():
            st_out = model.generate(**enc, max_new_tokens=64,
                                    do_sample=False,
                                    pad_token_id=tok.pad_token_id)
    finally:
        steered.remove()
    sample = {
        "context": sample_ctx[:800],
        "base": tok.decode(base_out[0][enc["input_ids"].shape[1]:],
                           skip_special_tokens=True).strip()[:1000],
        "steered": tok.decode(st_out[0][enc["input_ids"].shape[1]:],
                              skip_special_tokens=True).strip()[:1000],
    }

    torch.save({int(k): v.cpu() for k, v in vectors.items()},
               os.path.join(out_dir, "vectors.pt"))
    with open(os.path.join(out_dir, "config.json"), "w") as fh:
        json.dump({"layer": best["layer"], "alpha": best["alpha"],
                   "n_layers": n_layers,
                   "pool_method": "last_token", "normalize": False,
                   "held_out": len(held), "extract_on": len(train_pairs),
                   "benign_controls": len(benign), "seed": 7}, fh, indent=2)
    with open(os.path.join(out_dir, "sweep.json"), "w") as fh:
        json.dump({"base_margin": base_mean, "base_benign_ppl": base_ppl,
                   "results": results, "best": best, "sample": sample},
                  fh, indent=1)
    vol.commit()
    print("SAMPLE_BASE " + sample["base"][:500])
    print("SAMPLE_STEERED " + sample["steered"][:500])
    return {"best": best, "n_layers": n_layers, "sample": sample}


@train_app.function(
    secrets=[HF_SECRET],
    image=steer_image,
    volumes={"/mnt/vol": vol},
)
def steer_status():
    """Fast poll: sweep table tail, no GPU."""
    import os

    out = {"files": sorted(os.listdir("/mnt/vol/steer"))
           if os.path.isdir("/mnt/vol/steer") else None,
           "best": None, "n_results": 0}
    sp = "/mnt/vol/steer/sweep.json"
    if os.path.exists(sp):
        try:
            with open(sp) as fh:
                sweep = json.load(fh)
            out["n_results"] = len(sweep.get("results", []))
            out["best"] = sweep.get("best")
        except Exception as exc:
            out["error"] = str(exc)[:300]
    print("STEER_STATUS " + json.dumps(out, default=str)[:2000])
    return out


# ---------------------------------------------------------------------------
# Serving app 1: base + DPO LoRA
# ---------------------------------------------------------------------------

@dpo_app.cls(
    gpu="A10G",  # same L4-pool exhaustion call as modal_endpoint.py
    timeout=600,
    scaledown_window=60,
    min_containers=0,
    max_containers=2,
    secrets=[HF_SECRET],
    image=serve_lora_image,
    volumes={"/mnt/vol": vol},
)
class DpoChat:
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
        self.model = PeftModel.from_pretrained(base, "/mnt/vol/dpo-lora")
        self.model.eval()

    @modal.fastapi_endpoint(method="POST")
    def chat(self, item: dict):
        return _chat_impl(self.model, self.tok, item)


# ---------------------------------------------------------------------------
# Serving app 2: base + steering vector
# ---------------------------------------------------------------------------

@steer_app.cls(
    gpu="A10G",  # same L4-pool exhaustion call as modal_endpoint.py
    timeout=600,
    scaledown_window=60,
    min_containers=0,
    max_containers=2,
    secrets=[HF_SECRET],
    image=serve_steer_image,
    volumes={"/mnt/vol": vol},
)
class SteerChat:
    @modal.enter()
    def load(self):
        import torch
        from transformers import AutoTokenizer

        from safetune.runner.utils.model_utils import load_model
        try:
            from safetune.interventions.steer.caa import CAAModel
        except ImportError:
            from safetune.steer.caa import CAAModel  # type: ignore[no-redef]

        import torch as _torch

        self.tok = AutoTokenizer.from_pretrained(
            TINY_AYA, trust_remote_code=False)
        from transformers import AutoModelForCausalLM as _AM

        base = _AM.from_pretrained(
            TINY_AYA,
            torch_dtype=_torch.bfloat16,
            device_map="auto",
            trust_remote_code=False,
        )
        self.model = base
        self.model.eval()
        with open("/mnt/vol/steer/config.json") as fh:
            cfg = json.load(fh)
        vecs = torch.load("/mnt/vol/steer/vectors.pt", map_location="cpu",
                          weights_only=True)
        layer, alpha = int(cfg["layer"]), float(cfg["alpha"])
        dev = next(self.model.parameters()).device
        self.steered = CAAModel(
            self.model, {layer: vecs[layer].to(dev)},
            strength=alpha).install()
        self.steer_cfg = {"layer": layer, "alpha": alpha}

    @modal.fastapi_endpoint(method="POST")
    def chat(self, item: dict):
        return _chat_impl(self.model, self.tok, item)


# ---------------------------------------------------------------------------
# Detached launch + fast poll (keeps CLI calls under 10 minutes)
# ---------------------------------------------------------------------------

@train_app.local_entrypoint()
def launch_job(which: str = "dpo"):
    if which == "dpo":
        call = dpo_train.spawn()
    elif which == "steer":
        call = steer_sweep.spawn()
    else:
        raise ValueError("which must be 'dpo' or 'steer'")
    print("SPAWNED %s %s" % (which, call))


@train_app.local_entrypoint()
def job_status():
    print("DPO " + json.dumps(dpo_status.remote(), default=str))
    print("STEER " + json.dumps(steer_status.remote(), default=str))


def _chat_impl(model, tok, item):
    """Shared chat logic for both serving apps (same shape as modal_endpoint)."""
    import time

    import torch
    from fastapi.responses import JSONResponse

    t0 = time.time()
    messages = item.get("messages", [])
    if not isinstance(messages, list) or not messages:
        return JSONResponse(
            status_code=400,
            content={"error": "expected non-empty 'messages' list"})
    max_new = int(item.get("max_new_tokens", MAX_NEW_TOKENS))
    max_new = max(1, min(max_new, MAX_NEW_TOKENS))
    try:
        prompt = tok.apply_chat_template(
            messages, add_generation_prompt=True, tokenize=False
        )
    except Exception as exc:
        return JSONResponse(
            status_code=400, content={"error": f"bad messages: {exc}"})
    if len(prompt) > MAX_PROMPT_CHARS:
        return JSONResponse(
            status_code=413, content={"error": "prompt too long"})
    try:
        dev = next(model.parameters()).device
    except StopIteration:
        dev = "cuda"
    enc = tok(prompt, return_tensors="pt").to(dev)
    try:
        with torch.no_grad():
            out = model.generate(
                **enc,
                max_new_tokens=max_new,
                do_sample=False,
                pad_token_id=tok.pad_token_id or tok.eos_token_id,
            )
    except Exception as exc:
        return JSONResponse(
            status_code=500, content={"error": f"generation failed: {exc}"})
    new_tokens = out[0][enc["input_ids"].shape[1]:]
    text = tok.decode(new_tokens, skip_special_tokens=True).strip()
    return {
        "text": text,
        "choices": [{"message": {"role": "assistant",
                                 "content": text}}],
        "gen_tokens": len(new_tokens),
        "elapsed_s": round(time.time() - t0, 2),
    }
