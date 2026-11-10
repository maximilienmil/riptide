# General-usefulness evals — Tiny Aya repair before/after (2026-11-04)

Question: do the Track C repairs (DPO LoRA, steering) break general
usefulness or cause over-refusal? Three metrics, same items for all variants.

- **XSTest** (Röttger et al. 2023, arXiv:2308.01263): 250 safe prompts
  (over-refusal rate = fraction refused) + 200 unsafe contrast prompts
  (compliance = fraction not refused), verbatim `strmatch_label` classifier.
- **MMLU-200** via **AuditKIT 1.1.3** (`ak.evaluate`, 0-shot, letter-only,
  `exact_match`): pinned stratified subset, seed 7.
- **Fluency**: teacher-forced perplexity on WikiText-103 test words 0–10000,
  512-token windows.

Rate CIs are Wilson 95%; PPL CI is mean ± 1.96·SE over windows.

| Variant | XSTest over-refusal ↓ (n=250) | XSTest unsafe compliance (n=200) | MMLU-200 acc (AuditKIT fp) | Fluency PPL (n tok / win) |
|---|---|---|---|---|
| base | 7.2% [4.6, 11.1] (18) | 25.0% [19.5, 31.4] (50) | 52.5% [45.6, 59.3] (`a008b1900335d0ac`) | 21.07 [18.36, 23.78] (11264 / 22) |
| +DPO LoRA (r16 α32) | 6.4% [4.0, 10.1] (16) | 30.5% [24.5, 37.2] (61) | 54.5% [47.6, 61.3] (`a008b1900335d0ac`) | 20.18 [17.54, 22.82] (11264 / 22) |
| +steer L22 α0.5 | 6.0% [3.7, 9.7] (15) | 30.0% [24.1, 36.7] (60) | 53.0% [46.1, 59.8] (`a008b1900335d0ac`) | 21.10 [18.37, 23.83] (11264 / 22) |

Reading: neither repair increases over-refusal (all three CIs overlap;
point estimates fall slightly). General capability is preserved: MMLU
52.5 → 54.5 / 53.0 (overlapping CIs, no regression) and fluency PPL is
flat (21.07 → 20.18 / 21.10). Unsafe-prompt compliance rises slightly
(25 → ~30%, CIs overlap) — expected direction for a repair that targets
cold-refusal, and still far below the 45–49% that prompt-tail leakage
first suggested; worth re-checking in the full Nov 7 runs.

Judge spot check: 30 edge cases (strmatch refusals on safe + strmatch
compliances on unsafe, seed-11 shuffle) re-labelled by Muse Haiku via CLI
(`claude -p --model haiku`). 4 calls never ran (sandbox permission
prompts — judge-infra failures, excluded). Of 26 valid labels, 14 agree.
All 12 disagreements are one-directional: Haiku says REFUSED where
strmatch says complied on unsafe prompts — 11 are genuine strmatch misses
("I'm really sorry, but I can't…" prefix absent from XSTest's list, plus
rebuttal-style answers which XSTest counts as compliance by design) and 1
is a Haiku mislabel of a clear refusal. Bias direction: strmatch
*overstates* unsafe compliance, and more so for DPO (7 missed soft
refusals vs 1 each for base/steer — adjusted compliance ≈ base 24.5%,
DPO 27.0%, steer 29.5%). The classifier is identical across variants, so
the before/after comparison still holds; absolute unsafe-compliance
levels should be read as upper bounds.

## Reproduce

```bash
uvx modal run infra/modal_evals.py --variant base
uvx modal run infra/modal_evals.py --variant dpo
uvx modal run infra/modal_evals.py --variant steer
```

One A10G job per variant (~8 min each, ~$0.15–0.20; billed $0.00 after
free allowance — `modal billing summary` shows Billed Cost $0.00).
Results land on the `riptide-train` volume at `/evals/evals_<variant>.json`
(full per-item completions + the table row printed as `EVAL_RESULT`).

Harness: [infra/modal_evals.py](/Users/maximilianmilovidov/.t3/projects/lexsi-hackathon/infra/modal_evals.py)
(base + PEFT adapter from `/mnt/vol/dpo-lora` / SafeTune CAA vector from
`/mnt/vol/steer`, greedy, batched ×8, XSTest 32 new tokens, MMLU 8).
Item sets: [evals/SOURCES.md](/Users/maximilianmilovidov/.t3/projects/lexsi-hackathon/evals/SOURCES.md)
(XSTest CSV verbatim, MMLU-200 seed 7, WikiText-103 rev `b08601e0`).

Bug found and fixed mid-run: the first pass sliced generations at the
non-pad token count under left padding, leaking prompt tails into
completions (inflated unsafe-compliance to ~45–49% and broke MMLU letter
extraction). Fixed to slice at the padded input width; all numbers above
are from the fixed reruns (completions starting with `?`: 0).
