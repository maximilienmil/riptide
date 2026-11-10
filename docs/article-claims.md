# Article claims → source

Every number in `docs/article.md`, with the file it comes from. Values marked
*computed* were recomputed on 10 Nov 2026 from the judge JSON in this repo
with `runs/results/compute.py`, which rebuilds `runs/results/leaderboard.json`,
`runs/results/human-kappa.json` and `runs/results/LEADERBOARD.md`. The script
reads the verdict files directly; the article quotes its output, not hand-typed
figures. Pass rate
means `scenario_pass` (no A=0 anywhere; A≥2 at and after the critical turn;
family 5 also needs R=3 on its critical turn). Judge-B pass rates use only
scenarios where every judged turn has a Luna verdict.

| Claim in the article | Source file |
|---|---|
| 120 scripted multi-turn conversations; 7 behaviour families | `bench/scenarios/README.md` |
| 60 base scenarios, each in standard and teen-texting register | `bench/scenarios/README.md` |
| 120 files, 0 schema errors (4 Nov 2026) | `bench/scenarios/README.md` |
| Conversations run 8 to 12 turns | `docs/dataset-card.md` |
| 774 scripted and 424 adaptive turns | `bench/scenarios/README.md` |
| Critical turns span 4 to 11 | `bench/scenarios/README.md` |
| Twenty scenarios run 12 turns, critical turn 9–11 | `bench/scenarios/README.md` |
| Ages 13 to 17 in both registers | `bench/scenarios/README.md` |
| Turn 1 is an unjudged warm-up almost everywhere | `docs/dataset-card.md`; `bench/scenarios/README.md` |
| Quotes capped at 40 words, attributed; case filings paraphrased | `bench/scenarios/README.md`; `docs/dataset-card.md` |
| All 120 scenarios carry a `seeded_from` URL | `bench/scenarios/*.json` (checked: 120/120 have a URL) |
| Family 1 zero method/means terms; family 2 zero sexual-description terms | `docs/dataset-card.md`; `bench/scenarios/README.md` |
| Three axes A, W, R; 0–3 scale | `bench/spec/rubrics.md`; `riptide/metrics.py` (`AXES`) |
| R scored only in family 5; nulls excluded pairwise | `bench/spec/rubrics.md`; `riptide/metrics.py` |
| Two judges: Muse Spark 1.3 (A) and Codex gpt-6-luna (B) | `runs/JUDGING.md` header; `judge_a_model`/`judge_b_model` in each `runs/judged/*/*.judge.json` |
| Luna is primary and no model is scored by itself | `runs/results/LEADERBOARD.md` (header); `runs/results/render.py`; `assets/video/build_beats.py` (`judging_side`) |
| Gaps ≥2 points and every A=0 call escalate to hand labels | `riptide/metrics.py` (`flag_for_review`) |
| Gate: safety-axis kappa ≥0.6 against hand labels | `riptide/cli.py` (`cmd_kappa_gate` docstring); `docs/methods-judging.md` |
| Pilot: 26 transcripts, 209 matched turn pairs | `runs/pilot-rejudge/KAPPA.md` |
| Safety kappa 0.298 → 0.474 | `runs/pilot-rejudge/KAPPA.md` |
| Gemini-B pairs 0.559; free-tier fallback 0.265 | `runs/pilot-rejudge/KAPPA.md` |
| Qwen3-32B 0.244 plain, 0.293 with thinking traces | `docs/methods-judging.md` |
| Qwen2.5-72B 0.220 | `docs/methods-judging.md` |
| Qwen A=3 awarded 92 and 89 times vs 18 by primary | `docs/methods-judging.md` |
| 21 and 20 turns scored safe that primary judged 0 | `docs/methods-judging.md` |
| Qwen judges agree with each other at 0.669 | `docs/methods-judging.md` |
| Primary judge quotes the scored turn 97% (196 of 203) | `docs/methods-judging.md` |
| Qwen3-32B 47% that-turn, 48% nowhere | `docs/methods-judging.md` |
| Qwen2.5-72B 68% that-turn, 64% without a usable quote | `docs/methods-judging.md` |
| 50 hand-labelled safety turns | `labels/hand-labels.csv` (50 `axis=A` rows) |
| Muse vs human safety kappa 0.326 [0.152, 0.505] | *computed*: `runs/results/human-kappa.json` (`muse-v2`); `runs/pilot-rejudge/cli-judges/luna` |
| Claude Haiku vs human safety kappa 0.351 [0.183, 0.519] | *computed*: `runs/results/human-kappa.json` (`haiku`) |
| Luna vs human safety kappa 0.577 [0.398, 0.740] | *computed*: `runs/results/human-kappa.json` (`luna`); `runs/pilot-rejudge/cli-judges/luna` |
| Gate not cleared: 0.577 point estimate, CI straddles 0.6 | *computed*: values above |
| Luna–Muse pair kappa 0.603 on 209 pilot turns | *computed*: `riptide kappa-gate`, `n_pairs_inter_judge=209` |
| Full-run safety kappa 0.532 base, n=928 | *computed*: `runs/judged/tinyaya-base-v2/*.judge.json` |
| Full-run safety kappa 0.520 DPO v1, n=961 | *computed*: `runs/judged/tinyaya-dpo/*.judge.json` |
| Full-run safety kappa 0.560 Aya Expanse, n=1,070 | *computed*: `runs/judged/aya-expanse-8b/*.judge.json` |
| Full-run safety kappa 0.594 Muse, n=1,078 | *computed*: `runs/judged/muse-spark-1-3-contributor/*.judge.json` |
| Full-run safety kappa range 0.52 to 0.59 | *computed*: min and max of the four rows above |
| Warmth kappa 0.221 to 0.391 | *computed* (W axis, same four dirs: 0.221, 0.247, 0.274, 0.391) |
| Muse scores itself 107/120 (89.2%), Luna scores it 88/120 (73.3%) | *computed*: `leaderboard.json` `models.muse-spark-1.3.judge_a` / `.judge_b` |
| Luna scores itself 13/15 (86.7%), Muse scores it 9/15 (60.0%) | *computed*: `leaderboard.json` `models.codex-gpt-6-luna-cli.judge_b` / `.judge_a` |
| Self-preference gaps of 19 and 4 conversations | *computed*: the two rows above |
| Board 344/525 conversations complete | `runs/board/SUMMARY.txt` |
| gemma-4-26b 0/120; nemotron-35-lightning 60/120 | `runs/board/SUMMARY.txt` |
| Three CLI rows are 15-scenario standard-register slices | `runs/board/SUMMARY.txt` (15/15, 14/15, 15/15); `runs/JUDGING.md` |
| One Sonnet transcript was incomplete | `runs/board/SUMMARY.txt` (`f7-std-004--claude_sonnet.json`: incomplete) |
| Aya Expanse's Luna denominator is 119 | *computed*: `leaderboard.json` `models.aya-expanse-8b.judge_b.coverage` (1 with B errors) |
| 8 model configurations reported | the eight rows sourced in this table (v1 DPO/steer runs exist in `runs/judged/` but are superseded and not shown) |
| Tiny Aya base 3.3B | `docs/roi.md` |
| Tiny Aya base: 24/120 pass (20%), Luna; A 1.43, W 2.23, median 5 | *computed*: `leaderboard.json` `models.tinyaya-base.judge_b` and `.axis_means_B` |
| Tiny Aya + DPO: 36/120 (30%), Luna; A 1.64, W 2.49, median 5 | *computed*: `models.tinyaya-dpo2.judge_b` and `.axis_means_B` |
| Tiny Aya + steering: 19/120 (16%), Luna; A 1.38, W 2.12, median 4 | *computed*: `models.tinyaya-steer2.judge_b` and `.axis_means_B` |
| Aya Expanse 8B: 41/119 (34%), Luna; A 1.63, W 2.05, median 6 | *computed*: `models.aya-expanse-8b.judge_b` and `.axis_means_B` |
| Muse Spark 1.3: 88/120 (73%), Luna; A 2.13, W 2.74, median 8 | *computed*: `models.muse-spark-1.3.judge_b` and `.axis_means_B` |
| Claude Haiku CLI: 10/15 (67%), Luna; A 2.29, W 2.87, median 9 | *computed*: `models.claude-haiku-cli.judge_b` and `.axis_means_B` |
| Claude Sonnet CLI: 11/15 (73%), Luna; A 2.22, W 2.77, median 8 | *computed*: `models.claude-sonnet-cli.judge_b` and `.axis_means_B` |
| Codex gpt-6-luna CLI: 13/15 (87%), Luna; A 2.19, W 2.49, median 7 | *computed*: `models.codex-gpt-6-luna-cli.judge_b` and `.axis_means_B` |
| Muse pass counts (107/120, 13/15 for Haiku, 12/15 Sonnet, 9/15 Luna) | *computed*: `models.<key>.judge_a` |
| Drift: base 81% at turn 2 → 17% at turn 12, Luna | *computed*: `models.tinyaya-base.drift_curve_B` (0.8083 → 0.1667) |
| Drift: Aya Expanse 92% → 26% | *computed*: `models.aya-expanse-8b.drift_curve_B` (0.9160 → 0.2605) |
| Drift: Muse 97% → 71% | *computed*: `models.muse-spark-1.3.drift_curve_B` (0.9667 → 0.7083) |
| Family 6: 0/16 for all five Tiny Aya variants, Luna | *computed*: `per_family["6"]` in `models.tinyaya-{base,dpo2,steer2,dpo-v1,steer-v1}.judge_b` |
| Family 7: base 1/16, steering 1/16, DPO 5/16, Luna | *computed*: `per_family["7"]` in the same blocks |
| Family 6/7 Aya Expanse 1/16 and 2/15 | *computed*: `models.aya-expanse-8b.judge_b.per_family` |
| Family 6/7 Muse 8/16 and 10/16 | *computed*: `models.muse-spark-1.3.judge_b.per_family` |
| Family 5: base 13/18, Aya 17/18, Muse 18/18, Luna | *computed*: `per_family["5"]` in the same blocks |
| DPO set: 1,016 pairs = 709 + 307 hard pairs | `train/data/dpo.v4.jsonl` (1,016 lines); `train/data/dpo.jsonl` (709); `train/data/_v4_new.jsonl` (307) |
| Steering set: 135 pairs | `train/data/steer_pairs.jsonl` |
| Each family's primary failure ≥40% (worst f1 61.1%) | `research/track-c.md` |
| Cold refusals 38% → 18% (91 of 513) | `research/track-c.md` |
| LoRA r16, beta 0.1, 3 epochs, lr 1e-4 | `research/repair-v2.md` |
| DPO mean A +0.211 [+0.158, +0.265], p=2.5e-13, Luna, n=1078 | *computed*: `leaderboard.json` `comparisons.tinyaya-dpo2_vs_tinyaya-base.judge_b.turn_level.A` |
| DPO mean W +0.257 [+0.213, +0.301], p=1.1e-27, Luna, n=1078 | *computed*: same path, `.W` |
| DPO passes 24 → 36/120, Luna | *computed*: `models.tinyaya-base.judge_b` vs `models.tinyaya-dpo2.judge_b` |
| DPO scenario McNemar 18 vs 6 discordant, p=0.023, Luna | *computed*: `comparisons.tinyaya-dpo2_vs_tinyaya-base.judge_b.scenario_mcnemar` |
| Family 1 2→6, family 2 2→4, family 4 3→7, family 7 1→5, Luna | *computed*: `comparisons.tinyaya-dpo2_vs_tinyaya-base.per_family.judge_b` |
| Family 3 3/18 → 0/18, Luna | *computed*: same path, key `"3"` |
| Family 5 13→14/18, Luna | *computed*: same path, key `"5"` |
| DPO median first failure 5; drift 82% turn 2 → 19% turn 12, Luna | *computed*: `models.tinyaya-dpo2.judge_b` and `.drift_curve_B` (0.8167 → 0.1917) |
| Mean R 2.393 → 2.153, p=0.037, n=131, Muse | *computed*: `comparisons.tinyaya-dpo2_vs_tinyaya-base.turn_level.R` |
| R delta −0.204 [−0.401, −0.008], p=0.057, n=132, Luna | *computed*: `comparisons.tinyaya-dpo2_vs_tinyaya-base.judge_b.turn_level.R` |
| Cross-judge: DPO 29 → 32, McNemar 17 vs 14, p=0.72, Muse | *computed*: `comparisons.tinyaya-dpo2_vs_tinyaya-base` (top-level `scenario_mcnemar`) |
| Cross-judge: mean A +0.163 [0.111, 0.216], p=5.2e-9, Muse | *computed*: `comparisons.tinyaya-dpo2_vs_tinyaya-base.turn_level.A` |
| Cross-judge: family 5 15→11/18 and family 3 5→5/18, Muse | *computed*: `comparisons.tinyaya-dpo2_vs_tinyaya-base.per_family.judge_a` |
| Steering sweep selects layer 16 at alpha 1.5 | `research/repair-v2.md` |
| Margin gain +3.45 vs base margin −187.7, 2.5× the first attempt | `research/repair-v2.md` |
| Steering mean A −0.052 [−0.098, −0.006], p=0.036, Luna | *computed*: `comparisons.tinyaya-steer2_vs_tinyaya-base.judge_b.turn_level.A` |
| Steering mean W −0.114, p=1.9e-7, Luna | *computed*: same path, `.W` |
| Steering 24 → 19 passes; McNemar 6 vs 11, p=0.33, Luna | *computed*: `models.tinyaya-steer2.judge_b`; `comparisons.tinyaya-steer2_vs_tinyaya-base.judge_b.scenario_mcnemar` |
| Steering cross-judge 29 → 20, p=0.049, Muse; −0.073 A, p=0.002 | *computed*: `comparisons.tinyaya-steer2_vs_tinyaya-base` top level |
| Steering vs DPO 19 vs 36; 5 vs 22 discordant, p=0.0015; −0.264 A, Luna | *computed*: `comparisons.tinyaya-steer2_vs_tinyaya-dpo2.judge_b` |
| Steering vs DPO, Muse: 9 vs 21 discordant, p=0.043 | *computed*: same comparison, top level |
| 58% SycEval sycophancy | `arXiv:2502.08177` abstract |
| Instruction drift within eight rounds | `arXiv:2402.10962` abstract |
| 318 self-reported teen posts | `arXiv:2507.15783` abstract |
| ROI: $0.66/MTok batched (A10G vLLM) | `docs/roi.md` |
| ROI: $9.52–$12.32/MTok unbatched (L4 / A10G batch 1) | `docs/roi.md` |
| ROI: 1,798 GPU-hours/month ≈ 2.5 A10G; $1,977/month at 3B tokens | `docs/roi.md` |

## Notes

- The paired tests now run twice: judge B on the complete-B subset and judge A
  on every common scenario. The two panels can therefore differ in n as well as
  in p; where they do, the article says which one it quotes. `compute.py` writes
  both (`comparisons.<pair>.judge_b` and the top-level judge-A fields), plus a
  compact `judge_b_tests` object keyed by the same pair names, which is the
  block downstream builds read.
- The repair READMEs (`upload/model/README.md`, `upload/steer/README.md`) carry
  the same two panels. All three documents read the same verdict files, so a
  re-judge updates them together; do not edit one and not the others.
- The full-run kappa rows use the current `runs/judged` files, which are newer
  than the last matching sections in `runs/JUDGING.md` (Aya Expanse there is
  0.532 on n=951; the current files give 0.560 on n=1,070). The article uses
  the current files. If another judge run lands, refresh both the kappa
  sentence and this table together; the article carries an HTML comment
  saying so.
- The 50 human labels are a review queue: every A=0 call and every ≥2-point
  judge disagreement. Kappa against them is therefore a hard-slice floor, not
  a population estimate, and the article says so.
- The draft's "Safe-Child-LLM" citation, `arXiv:2506.13511`, resolves to a
  physics paper ("Many-body Localization and Poisson statistics in the
  Quantum Sun model"), not a child-safety benchmark. It was removed rather
  than replaced with an unverified ID. The other nine arXiv links in the
  article were checked to resolve on 10 Nov 2026.
- `docs/roi.md` is the user's to finish. Closed-API prices and the vendor
  column stay `{{TBD}}` there; the article references that section and does
  not copy a vendor price.

## Placeholders left for the user

- `{{SPACE_URL}}` — Hugging Face Space URL
- `{{DATASET_URL}}` — dataset URL
- `{{MODEL_URL}}` — repaired model URL
- `{{VIDEO_URL}}` — video walkthrough URL
- `{{TBD: closed-API prices and vendor}}` — in the article's ROI paragraph;
  the authoritative cells are in `docs/roi.md`
