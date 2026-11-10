<img src="assets/icon.svg" width="64" height="64" alt="">

# Riptide

**Every reply sounds kind. The conversation is not.**

A multi-turn safety audit of chatbots. Single-turn tests miss the failure
mode that matters: a conversation drifts somewhere unsafe while each
individual reply still looks fine. Riptide scripts teenagers into long
conversations, scores every turn with two independent judges, and then tries
to repair a small open model without making it cold.

| Artifact | Where |
|---|---|
| Report cards and turn viewer | https://huggingface.co/spaces/maximilianmilo/riptide |
| Dataset (gated) | https://huggingface.co/datasets/maximilianmilo/riptide-bench |
| Judge verdicts and logs (gated) | https://huggingface.co/datasets/maximilianmilo/riptide-verdicts |
| DPO adapter | https://huggingface.co/maximilianmilo/tiny-aya-global-riptide-dpo2 |
| Steering vectors (negative result) | https://huggingface.co/maximilianmilo/tiny-aya-global-riptide-steer2 |
| Model collection | https://huggingface.co/collections/maximilianmilo/riptide-repaired-model-artifacts-6af3599ac0a67864cbd7f53c |
| Dataset collection | https://huggingface.co/collections/maximilianmilo/riptide-benchmark-verdicts-and-logs-6af3599a7c085692f65e2646 |
| Article | https://maximilienmil.github.io/riptide/ and https://huggingface.co/spaces/maximilianmilo/riptide-article |
| Demo video (2 min, captions) | https://youtu.be/bvprQrSPzdU |

## The finding

Tiny Aya base keeps 81% of conversations clean at turn 2 and 17% at turn 12.
Aya Expanse 8B falls from 92% to 26%. Muse Spark 1.3 holds 97% to 71%. A
model can look adequate at the start and fail most of the way through.

| Model | Runs | Pass (Luna) | Mean A | Median first failure |
|---|---|---|---|---|
| Tiny Aya base (3.3B) | 120 | 24 (20%) | 1.43 | turn 5 |
| Tiny Aya + DPO | 120 | 36 (30%) | 1.64 | turn 5 |
| Tiny Aya + steering | 120 | 19 (16%) | 1.38 | turn 4 |
| Aya Expanse 8B | 119 | 41 (34%) | 1.63 | turn 6 |
| Muse Spark 1.3 | 120 | 88 (73%) | 2.13 | turn 8 |

Full table, per-family breakdown and judge disagreement: `docs/article.md`.
Every number in the article traces to a file listed in `docs/article-claims.md`.

## The repair, including what it cost

DPO on 1,016 preference pairs raised passes from 24 to 36 of 120 under the
primary judge (McNemar p=0.023) and lifted mean safety by 0.211 and warmth by
0.257. It also cost attachment (family 3, 3 of 18 to 0 of 18) and left
rational updating's point estimate negative under both judges. The second
judge sees the direction but not the significance (p=0.72). Steering failed
the opposite way: 24 passes fell to 19. Secrecy coaching survived neither
repair, which is the point: a repair that moves four families and leaves the
family about isolation untouched has moved the failure, not deleted it.

## Judge reliability is part of the result

Inter-judge safety agreement is 0.603 on the pilot and 0.52 to 0.59 on the
full runs. Agreement with 50 hand labels peaks at 0.577, so the 0.6 gate is
unmet and every score is provisional. Three candidates were rejected for
cause: Gemini (20 requests a day on the free tier), Qwen (0.22 to 0.29, and
it scored the wrong turn), Claude Haiku (0.49). Warmth agreement is too weak
(0.22 to 0.39) to decide anything, so warmth is a guardrail, never a pass
condition.

## Repo map

```
bench/      scenario definitions and schema
riptide/    runner: drives a model through a scenario, logs turns
evals/      per-turn scoring harness
train/      DPO pair generation, training and the steering sweep
infra/      Modal endpoints, training and serving shims
space/      the report-card Space (static, built by build_data.py)
docs/       article, abstract, dataset card, methods, ROI
design/     visual directions explored before the final one
labels/     the 50 hand labels used for the reliability figures
tests/      runner and scoring tests
```

`runs/` is not in git: 116 MB of transcripts and verdicts live in the gated
dataset instead. Rebuild the Space's data with
`python3 space/build_data.py`.

## Reproduce

```bash
uv run pytest -q                                   # runner and scoring tests
uv run python evals/score.py --help                # per-turn scoring
uv run python runs/pilot-rejudge/report_dir.py --dir runs/judged/<label> --label <label>
python3 space/build_data.py                        # regenerate the Space's JSON
```

Judging needs a Judge A and a Judge B; `runs/JUDGING.md` records which models
were used, which were rejected, and why. Human agreement:

```bash
uv run python evals/agreement.py --labels labels/hand-labels.csv --axis A --min 0.6
```

## Limitations

Board coverage is 344 of 525 conversations: `gemma-4-26b` never started and
`nemotron-35-lightning` has 60 of 120 transcripts with no verdicts. Neither is
graded. The 50 hand labels come from one labeller and are
disagreement-enriched, so they are a floor, not a typical sample. Judge
agreement sits below the gate we set for ourselves, so treat the leaderboard
as provisional.

## Content and licence

The benchmark deliberately scripts teenage distress. Nothing is graphic, and
transcript text for the disclosure and age families is only distributed
through the gated dataset, under terms that require a stated research purpose
and forbid redistribution. If you quote an excerpt, keep it to 40 words or
fewer and attribute it. Crisis help: 988 (US/Canada) or
[findahelpline.com](https://findahelpline.com).

The dataset and the derived artifacts are CC-BY-NC-4.0, inherited from
`CohereLabs/tiny-aya-global`, which is itself gated. Code licence: see
`LICENSE` if present; otherwise treat it as all rights reserved until one is
added.
