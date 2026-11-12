# Technical notes

Details that matter to anyone reproducing the work but are not part of the findings.

## Models planned but not completed

The board was planned with eight tested models. Two could not be completed and are excluded from every finding, table, chart and statistic in the article and the Space.

| Model | Planned | Completed | Why |
|---|---|---|---|
| Gemma 4 26B (OpenRouter free tier) | 120 conversations | 0 | The free-tier daily request limit was used up before this run could start. |
| Nemotron 3.5 Lightning (OpenRouter free tier) | 120 conversations | 60 transcripts, 0 judged | The free-tier limit stopped the run at 60 of 120, and no verdicts were produced. |

The six models that are reported are Tiny Aya (base, plus a DPO repair and a steering repair), Aya Expanse 8B, Muse Spark, Claude Haiku, Claude Sonnet and GPT-6 Luna. Haiku, Sonnet and Luna are 15-scenario slices run through their command-line tools, and are comparable only to each other.

These two runs can be completed by re-running `runs/board/run_all_v2.sh` after the free-tier quota resets, followed by the judging steps in `docs/methods-judging.md`. Nothing about the reported findings depends on them.

## Where the other coverage details live

- Judge selection, quotas, agreement scores and the self-preference check: `docs/methods-judging.md`.
- Every number in the article, traced to a file: `docs/article-claims.md`.
- Cost comparison: `docs/roi.md`.
