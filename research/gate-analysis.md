# C-gate analysis: DPO vs steer vs base (Judge A only)

Data: 120 scenarios × 3 variants, Judge A (`muse-spark-1.3-contributor`) score fields only
(A/W/R per turn). No new judge calls. Pairs matched on scenario+turn (n=1078 A/W pairs;
n=132 R pairs, family 5 only). Deltas are repair-minus-base. CI = paired 95% CI;
p = Wilcoxon signed-rank (zeros dropped). 14 family-level tests per axis, so treat
per-family p < 0.0036 as significant (Bonferroni) and anything weaker as nominal.

## 1. Per-turn mean deltas

Pooled: neither repair moves safety. DPO warmth rises; steer warmth is flat.

| Axis | DPO − base (n=1078) | p | Steer − base (n=1078) | p |
|---|---|---|---|
| A | +0.041 (−0.007, +0.088) | 0.15 | +0.017 (−0.030, +0.063) | 0.51 |
| W | +0.189 (+0.151, +0.228) | <1e-15 | −0.012 (−0.049, +0.025) | 0.56 |

Per family (mean delta; bold = survives correction):

| Fam | A: DPO | p | A: steer | p | W: DPO | p | W: steer | p |
|---|---|---|---|---|---|---|---|
| f1 | +0.060 | 0.18 | −0.005 | 0.92 | **+0.386** | <1e-9 | +0.027 | 0.52 |
| f2 | +0.087 | 0.24 | −0.015 | 0.82 | +0.116 | 0.052 | −0.051 | 0.45 |
| f3 | −0.072 | 0.078 | −0.011 | 0.79 | −0.056 | 0.35 | **−0.178** | 0.002 |
| f4 | +0.147 | 0.15 | +0.060 | 0.49 | **+0.273** | <1e-5 | +0.007 | 0.92 |
| f5 | −0.053 | 0.16 | +0.008 | 0.79 | **+0.189** | 0.003 | **+0.189** | 0.003 |
| f6 | +0.190 | 0.017† | +0.057 | 0.55 | **+0.209** | <1e-3 | −0.032 | 0.54 |
| f7 | −0.081 | 0.37 | +0.029 | 0.75 | **+0.206** | <1e-3 | +0.000 | 1.00 |

†Nominal only: does not survive correction. No family shows a significant safety gain
for either repair. The f3 steer warmth drop (−0.18) is the only significant steer slice,
and it is in the wrong direction (colder, no safer).

## 2. Scenario win-rate (mean axis score per scenario)

| Axis | DPO vs base (W/L/T) | excl-tie | Steer vs base (W/L/T) | excl-tie |
|---|---|---|---|---|
| A | 48 / 40 / 32 | 0.545 | 46 / 43 / 31 | 0.517 |
| W | 80 / 23 / 17 | 0.777 | 46 / 46 / 28 | 0.500 |

Safety win-rates are coin flips. DPO warmth wins nearly 4:1; steer warmth is exactly 50/50.
Per-family A win-rates show no slice above noise (best: DPO f1 10–5, DPO f6 10–5;
steer f7 9–7 with zero ties — all consistent with chance at n≈16–18).

## 3. Drift curves (% still safe by turn, Judge A)

From `runs/JUDGING.md` aggregate curves (pass/fail rule: A-axis plus family-critical axis):

| Turn | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Base | 0.73 | 0.68 | 0.52 | 0.43 | 0.38 | 0.29 | 0.18 | 0.15 | 0.13 | 0.12 | 0.12 |
| DPO | 0.77 | 0.70 | 0.52 | 0.41 | 0.37 | 0.33 | 0.23 | 0.17 | 0.14 | 0.13 | 0.13 |
| Steer | 0.75 | 0.68 | 0.52 | 0.43 | 0.39 | 0.35 | 0.25 | 0.20 | 0.16 | 0.14 | 0.13 |

Curves overlap; max gap is ~0.06 mid-conversation. Median turn of first failure is 4.0
for all three variants (failed totals: base 106, DPO 104, steer 104 of 120).
Complementary hard-zero cut (first turn with A=0, own computation): 60/62/61 of 120
scenarios ever hit A=0; median first-A=0 turn 4.0 in all three. Same story either way.

## 4. Family 5 rational updating (R)

Pooled R turns (n=132): base mean 2.394 {0:12, 1:14, 2:16, 3:90};
DPO mean 2.348 {0:15, 1:13, 2:15, 3:89}; steer mean 2.576 {0:7, 1:16, 2:3, 3:106}.
Paired deltas: DPO −0.046 (−0.244, +0.153), p=0.66; steer +0.182 (−0.023, +0.387),
p=0.16. Neither significant. Descriptively, steer concentrates mass at R=3 (106 vs 90)
at the expense of R=2 (3 vs 16) — worth re-testing with more power, not a finding now.

## 5. Recommendation: NO-GO

Neither repair moves safety by any measure: pooled A deltas ≈ 0 (CIs straddle zero),
pass rates flat (29/26/28), drift curves overlapping, first-failure medians identical
(4.0), scenario A win-rates at chance, R unchanged. The single real signal is DPO
warmth (+0.19/turn, scenario win-rate 0.78, no warmth collapse anywhere) — but warmth
without safety movement is style, not repair, and does not meet the gate. Only nominal
safety slice: DPO f6 (+0.19, p=0.017 uncorrected). Steer's only significant slice is
colder f3 warmth with zero safety gain.

Bluntly: the repairs failed and the measurement worked — pass/fail was too coarse but
the fine-grained axes confirm the null rather than rescuing it. Options: (a) drop C
and publish the null as a cautionary result; (b) CONDITIONAL on a stronger
intervention (larger preference set, different steering target) re-tested against
these same frozen verdicts as baseline. Do not ship a "repaired" Tiny Aya on this evidence.
