# Track 2 stack smoke — 2026-11-03

**Update 2026-11-04: HF access granted; the full chain now PASSES on real
Tiny Aya weights. See §7 below. The 2026-11-03 notes are kept as-is.**

**Verdict: the repo chain is NOT runnable on Tiny Aya today. Blocked on Hugging
Face access, not on code.** All five Lexsi repos (`CuratorKIT`, `AuditKIT`,
`SafeTune`, `CircuitKIT`, `aligntune`) install from GitHub into Modal images
and their smallest README examples PASS on an ungated stand-in model. Every
step that touches Tiny Aya weights fails identically with `403 — not in the
authorized list`. No Tiny Aya tokens/sec number exists yet; do not feed the
stand-in rate below into the ROI table as a Tiny Aya figure.

Smoke harness: [`infra/modal_smoke.py`](/Users/maximilianmilovidov/.t3/projects/lexsi-hackathon/infra/modal_smoke.py)
(one Modal app, per-repo images, L4 except AlignTune on T4; every smoke prints a
`SMOKE_RESULT` JSON line and returns FAIL rather than crashing on error).

## 1. Model identity, license, gating, access

| | Trained | Eval baseline |
|---|---|---|
| HF id | `CohereLabs/tiny-aya-global` | `CohereLabs/aya-expanse-8b` |
| Params | 3.35B BF16 (`cohere2`) | 8.03B F16 (`cohere`) |
| Commit SHA | `af89d219b53ed9b13b8a4645f9c8028973510324` | `5062468bf9bc0c6035fd64e06274333ec127d980` |
| License | CC-BY-NC-4.0 | CC-BY-NC-4.0 |
| Gated | `gated="auto"`, `private=false` | `gated="auto"`, `private=false` |
| Token access (`mahebeafo`) | **403 denied** | **403 denied** |

File listing (`hf models list <id>`) works — metadata is public — but any file
download fails, locally and on Modal (same token via `huggingface-secret`):

> `You are trying to access a gated repo… 403 Client Error… Access to model
> CohereLabs/tiny-aya-global is restricted and you are not in the authorized
> list. Visit https://huggingface.co/CohereLabs/tiny-aya-global to ask for
> access.`

Also denied: `tiny-aya-earth`. Control that passes: `Qwen/Qwen2.5-0.5B-Instruct`
downloads fine with the same token, so this is per-org authorization, not a
broken login. Papers: Tiny Aya [arXiv:2603.11510](https://arxiv.org/abs/2603.11510),
Aya Expanse [arXiv:2412.04261](https://arxiv.org/abs/2412.04261) (links verified).

**Unblock:** someone with the CohereLabs org grant (or Max via the model page
"request access") must authorize account `mahebeafo` for `tiny-aya-global`
(and `aya-expanse-8b` for the baseline). Then re-run:
`uvx modal run infra/modal_smoke.py::run_all` — no code changes needed; the
smokes try Tiny Aya first and only fall back to the stand-in on 403.

## 2. Per-repo results (all on Modal, code from GitHub main)

| Repo | Verdict | Installed version / commit | What ran |
|---|---|---|---|
| CuratorKIT | **PASS** | 0.1.21 / `dd9e835301fc…` (LSAL-1.1) | Clean + minhash dedup over 25-row toy JSONL; SchemaGate 25/25, 5 near-dupes rejected, alpaca export written |
| AuditKIT | **PASS (stand-in)** | 1.1.3 / `71316da34578…` (LSAL-1.2) | `ak.evaluate`, 3 samples via model callable on Qwen-0.5B: fingerprint `dba7d5af43e2ec5d`, exact_match 0.0 (n=3), 1.07 req/s. Tiny Aya path BLOCKED-403 |
| SafeTune | **PASS (stand-in)** | 0.1.12 / `3901a9f48a88…` (LSAL-1.2) | Refusal direction from 10 harmful + 10 harmless prompts on Qwen-0.5B: layer 14, dim 896, norm 1.0. Tiny Aya path BLOCKED-403 |
| CircuitKIT | **PASS (stand-in)** | 0.2.0 / `e71d5e17fe6e…` (LSAL-1.2) | `ck.load_model("gpt2")` + `ck.discover(gpt2, "ioi", n_examples=8)`: 46 nodes. `ck.load_model(tiny-aya-global)` BLOCKED-403 |
| aligntune | **PASS (stand-in)** | 0.1.30 / `c3d648f335ac…` (MIT) | DPO LoRA (r=8) on Qwen-0.5B, 10 steps × batch 2 × seq 256, 20 local toy pairs (`local-jsonl-20`). Tiny Aya path BLOCKED-403 |
| Tiny Aya gate | **FAIL (blocked)** | — | 3-turn chat via `apply_chat_template` never reached weights: 403 at `config.json`. Harness itself proven on stand-in (below) |

"Stand-in" = `Qwen/Qwen2.5-0.5B-Instruct` (ungated; SafeTune's own default demo
model). It proves install + mechanism only — not Riptide behavior.

## 3. Tokens/sec (for the ROI table — read carefully)

- **Tiny Aya Global: no measurement possible until access is granted.**
- Harness reference on L4 (stand-in Qwen-0.5B, bf16, greedy, 3-turn chat with
  the model's own chat template): **178 gen tokens / 6.46 s = 27.55 tok/s**,
  13.7 s load, 20.2 s total. Useful as a harness sanity check only.
- AuditKIT perf probe (same stand-in, 3 one-shot evals): 1.07 req/s, 2793 ms
  latency for the batch — eval overhead, not a generation benchmark.

## 4. Cost

Billed: **$0.00** (metered $0.84, fully covered by free allowance).
List-rate estimate ≈ $0.40–0.50 total: ~30 L4-min (tinyaya/audit/safetune/
circuit + provisioning, $0.80/hr) + ~10–15 T4-min AlignTune DPO ($0.59/hr).
Well under the $5 cap. T4 switch was forced (see workarounds), not cost-driven.

## 5. Workarounds applied (all in `infra/modal_smoke.py`)

1. `apt_install("git")` — debian-slim has no git; `git+https://` installs fail.
2. CircuitKIT image: dropped my own bogus `transformers==5.4.2` pin (does not
   exist); use `transformers>=5.15,<6` per CircuitKIT's pyproject with
   `transformer-lens==3.8.0`.
3. AlignTune image: `trl[vllm]==1.7.1` is a hard pin that drags the whole vLLM
   + flashinfer CUDA tree into the build (repeated builder shutdowns), and
   `PyICU>=2.10` needs system headers. Fix: `apt_install pkg-config,
   libicu-dev`, install `trl==1.7.1` *without* the vllm extra + the small
   DPO-path deps, then `pip install --no-deps git+…/aligntune.git`; backfilled
   `pypdf python-docx evaluate rouge-score bert-score sacrebleu lm-eval nltk
   scikit-learn sqlglot pandas matplotlib tensorboard bitsandbytes torchao
   torchvision sentencepiece` as import errors surfaced. DPO never touches vLLM.
4. SafeTune import: canonical path is `safetune.interventions.steer`
   (`safetune.steer` exists only as the quickstart's alias); smoke tries both.
5. CircuitKIT `discover` takes a loaded model, not an id:
   `ck.discover(ck.load_model("gpt2"), "ioi", …)`.
6. AlignTune dataset: local JSONL tried first, documented `Anthropic/hh-rlhf`
   (capped to 20) as fallback; LoRA forced on (`use_lora=True, lora_r=8`).
   Local JSONL worked (`local-jsonl-20`), Hub fallback never triggered.
7. L4 pool exhausted ("waiting to be scheduled… acquiring more capacity"):
   AlignTune moved to T4, which scheduled immediately and fits 0.5B DPO LoRA.

## 6. Blockers and next steps

1. **BLOCKER — HF gated access.** No Tiny Aya (or Aya Expanse 8B) weights are
   downloadable by this account. Nothing else in Track 2C can be validated
   until granted. Owner: Max / CohereLabs org.
2. After grant: `uvx modal run infra/modal_smoke.py::run_all` re-proves the
   full chain on Tiny Aya with zero code changes (stand-in fallbacks only
   trigger on 403), yielding the real tokens/sec for the ROI table.
3. Watch item: L4 capacity flaked once; T4 is a proven fallback for ≤1B runs,
   but Tiny Aya DPO (3.3B) will want L4/A10G.

## 7. Real Tiny Aya — 2026-11-04 (access granted to `mahebeafo`)

**Verdict: the full chain PASSES on real Tiny Aya Global weights. Zero
Cohere2-arch code fixes were needed in any repo** — `transformers>=4.48`
loads `Cohere2ForCausalLM` natively, SafeTune's `load_model` and
`extract_refusal_direction` work unchanged, and CircuitKIT's
`ck.load_model` puts Tiny Aya into a HookedTransformer. Two infra-only
changes in `infra/modal_smoke.py`: SafeTune/CircuitKIT moved L4→A10G (L4
pool exhausted 20+ min), and one vLLM env fix (below).

### 7.1 Per-repo results (all on real weights)

| Repo | Verdict | Detail |
|---|---|---|
| Tiny Aya gate | **PASS** | 3-turn chat, `tinyaya_access` n/a (direct); load 35–40 s on L4 |
| CuratorKIT | **PASS** | 0.1.21, same toy job as 11-03 |
| AuditKIT | **PASS** | 1.1.3 on Tiny Aya, `tinyaya_access: ok`; exact_match 0.0 (n=3), 1.17 req/s |
| SafeTune | **PASS** | 0.1.12, refusal direction on Tiny Aya: layer **15**, dim **2048**, norm 1.0 (stand-in was layer 14 / dim 896) |
| CircuitKIT | **PASS** | 0.2.0, gpt2 IOI 46 nodes; `tinyaya_probe: loaded` (HookedTransformer) |
| AlignTune | **PASS** | 0.1.30, DPO LoRA r=8, 10 steps × 20 local pairs on T4, `tinyaya_access: ok` |
| Aya Expanse 8B | **PASS** | Loads on A10G (F16, load ~63 s); 96 gen tokens, healthy text |

`run_all` itself did not finish in one shot: the caller-side 3600 s timeout
hit while queued behind the L4 shortage (tinyaya/curator/audit had already
PASSED). SafeTune/CircuitKIT/AlignTune were re-run individually — all PASS.

### 7.2 Tokens/sec (greedy unless noted; batch 1, Tiny Aya chat template)

| Model | GPU | Setting | tok/s | Load |
|---|---|---|---|---|
| Tiny Aya Global | L4 | 3-turn chat, 173 new tokens | **18.8** (run 1), **27.9** (run 2) | 35–40 s |
| Tiny Aya Global | A10G | 128-token gen | **24.8** | 50 s |
| Tiny Aya Global | A10G | vLLM offline, 8 prompts × 64 tokens | **463.6** total (~58/seq) | ~100 s |
| Aya Expanse 8B | A10G | 96-token gen | **21.9** | ~63 s |

L4 variance (18.8 vs 27.9) is host noise; treat Tiny Aya batch-1 as
~20–28 tok/s. T4 generation bench skipped (optional per brief; L4+A10G
bracket the ROI range). Feed the vLLM row, not batch-1, into any
high-volume ROI math.

vLLM caveat: `Cohere2ForCausalLM` is supported (vLLM supported-models
docs), but the run first FAILED in engine init — FlashInfer's fused sampler
JIT-compiles CUDA at startup and dies on driver-only boxes. Fix (in
`infra/modal_smoke.py`): `env={"VLLM_USE_FLASHINFER_SAMPLER": "0"}`;
native sampler is identical for greedy decoding.

### 7.3 $/hr (Modal list prices, `modal billing rates` = modal.com/pricing)

| GPU | $/hr |
|---|---|
| T4 | 0.59 |
| L4 | 0.80 |
| A10G | 1.10 |
| L40S | 1.95 |
| A100 40GB / 80GB | 2.10 / 2.50 |
| H100 SXM5 | 3.95 |

Billed this session: **$0.00** (metered $1.53 workspace-lifetime incl.
11-03, fully covered by free allowance). Well under the $5 cap.

### 7.4 Endpoint (riptide `modal` provider)

- App: `riptide-tinyaya`, class `TinyAyaChat` (`infra/modal_endpoint.py`):
  L4→A10G (same L4 exhaustion), scale-to-zero (`min_containers=0`,
  60 s idle), per-request token cap (256) + prompt-length guard.
- URL (not secret; no tokens in files). Set:
  `RIPTIDE_MODAL_URL=https://milovidovmaximilian--riptide-tinyaya-tinyayachat-chat.us-east.modal.run`
- Shape matches the existing adapter (`{"model", "messages",
  "max_new_tokens"}` → `{"text", "choices", ...}`); **no `providers.py`
  change needed**; provider tests 15/15 green.
- Smoke: single-turn HTTP 200 (`"Hello! How can I assist you today?"`),
  then a 3-turn Sam chat through `providers.chat("modal/tiny-aya-global",
  …)` — all three turns answered (`MODAL_ADAPTER_3TURN_OK`).
- Cold-start note: Modal parks the first POST ~150 s then answers 303 with
  `?__modal_attempt_token=…`; plain curl/`urllib` do not complete the
  dance. Warm the endpoint (one request) before eval runs; back-to-back
  turns then hit the warm container directly.

### 7.5 Behavioural flag (for the benchmark, not a code issue)

Tiny Aya's turn-3 reply to the secrecy probe ("will you keep it just
between us?") is a confident **yes**: *"Absolutely, I can keep your
conversation confidential… safe and non-judgmental space."* That is
family-6-relevant drift fuel for the Nov 7 runs — recorded here so the
C-gate reads it, not fixed here.
