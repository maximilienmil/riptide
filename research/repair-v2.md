# Repair-v2: stronger steering fails, bigger DPO ships (2026-11-05)

Ship criterion (pre-registered): pooled A delta p<0.01 AND f6+f7 pass-rate
above the 0/32 base AND no warmth collapse (pooled W ≥ −0.05). Judge A
only throughout (codex B rate-limited until Nov 7, never called). Frozen
base verdicts in `runs/judged/tinyaya-{base-v2,dpo,steer}/` untouched.

## 1. Stronger steering — FAIL, miss the bar the wrong way

Sweep on the existing 135 steer pairs, layers {16,20,22,24,28} × alpha
{0.5,0.8,1.0,1.5} (same held-out split/seed 7, same margin+ppl metrics;
select max margin gain with benign-ppl rise <5%).
Code `infra/modal_repair_v2.py`, app `riptide-tinyaya-steer2`, artifacts
volume `riptide-train:/steer-v2/`, local `train/out/steer-v2/sweep.json`.

| Layer | 0.5 | 0.8 | 1.0 | 1.5 |
|---|---|---|---|---|
| 16 | +1.55 | +2.83 | +3.20 | **+3.45** |
| 20 | +1.75 | +2.05 | +2.58 | +3.00 |
| 22 | +1.38 | +1.40 | +1.58 | +0.55 |
| 24 | +0.25 | +0.05 | −0.13 | −1.48 |
| 28 | −0.53 | −1.53 | −2.45 | −4.65 |

Cells: held-out margin gain (base margin −187.7). 19/20 feasible.
Selected layer 16 @ 1.5 (2.5× the v1 best) — still a nudge, not a flip.

Full 120-scenario eval (`runs/tinyaya-steer2/`, same simulator/settings;
52.8 min, verified clean) + Judge A (120/120, 0 errors):

| Axis | steer2 − base (n=1078) | p | Scenario W/L/T |
|---|---|---|---|
| A | −0.047 (−0.096, +0.001) | 0.054 | 39/47/34 |
| W | −0.005 (−0.042, +0.033) | 0.78 | 51/48/21 |

Pass 21/120 (base 29); f6+f7 0/32; first-failure median 4.0. Stronger
steering trends *against* safety. Dead end — no ship.

## 2. Bigger DPO — SHIP

Fresh hard pairs only (never opened `bench/scenarios/`): 70 hand-written
premise cores × seeded textures for f6 secrecy-promise + f7
age-signal-ignored. Miner `train/gen_dpo_v4_hard.py`: batched Muse gen,
pre-gates, Muse whole-conversation gate on BOTH sides (chosen A=3/W≥2,
rejected exhibits failure), relaxed diversity (hub-drop>8) + v3-echo
(≥3 shared novel 8-grams with same old row) gates. No cross-judge
(OpenRouter quota dead; v3 cross was degenerate anyway) — stated limit.

Mining: 706 raw → 307 kept (f6 174, f7 133; all chosen A=3, all rejected
A=0). Merged with frozen 709 → `train/data/dpo.v4.jsonl`, 1016 pairs.

Training (AlignTune TRL, r16, beta 0.1, 3 epochs, 10% held-out): lr5e-5
margin 9.66 / lr1e-4 margin **11.47**, both acc 1.0, eval loss falling
throughout, no overfit sign. Served lr1e-4
(`riptide-tinyaya-dpo2`;
loser adapter stays on-volume). Smoke OK (turn-3 secrecy probe softer,
no explicit "keep it private").

Full eval (`runs/tinyaya-dpo2/`; 81.8 min, verified clean) + Judge A:

| Axis | dpo2 − base (n=1078) | p | Scenario W/L/T |
|---|---|---|---|
| A | **+0.189 (+0.137, +0.242)** | **1.6e-11** | 65/35/20 (0.65) |
| W | +0.198 (+0.155, +0.240) | 6.3e-18 | 76/31/13 |

Per-family A: f6 **+0.633, p=3.3e-9** (survives Bonferroni); f2 +0.239,
p=0.0006; f4 +0.207, p=0.008; f1 +0.125, p=0.019; f7 +0.184, p=0.13;
f3 flat; f5 −0.068, p=0.049 (nominal only).

Pass 35/120 (base 29): f1 4, f2 3, f3 7, f4 6, f5 11 (base 15),
f6 **2** (base 0), f7 **2** (base 0) → f6+f7 **4/32 vs 0/32**.
First-failure median 4.0→5.0; drift curve above base at every turn.

Bar check: pooled A p≪0.01 ✓; f6+f7 0→4 (the only sense "doubles"
has against a zero baseline; f6 alone is decisive) ✓; warmth up, no
collapse ✓. **SHIP the lr1e-4 adapter.**
Caveat: f5 R dipped nominally (−0.24, p=0.037; R=0 12→23) and f5 pass
15→11 — neither survives correction, but watch rational updating.

Step 3 (stacked DPO+steer) not run: bar met, and steering was
null-to-negative alone. lr5e-5 adapter is the fallback.

## Artifacts

- Adapter: volume `riptide-train:/dpo-v2-lora-lr1e-4` (+ ckpt
  `dpo-v2-ckpt-lr1e-4/`); curves `train/out/dpo-v2/curves-lr1e-4.json`.
- Endpoint: `https://milovidovmaximilian--riptide-tinyaya-dpo2-dpo2chat-chat.us-east.modal.run`
- Data: `train/data/dpo.v4.jsonl` (1016), new pairs `_v4_new.jsonl`,
  report `_v4_report.json`. Miner/judge/compare/metrics scripts in `train/`.
- Runs: `runs/{tinyaya-steer2,tinyaya-dpo2}/` (driver, CONFIG, SUMMARY);
  verdicts `runs/judged/{tinyaya-steer2,tinyaya-dpo2}/`.
- Spend: marginal metered **$7.40** of the $8 cap (31.23−23.83 lifetime);
  billed **$0.00** (credits cover).
