# Submit checklist

Status as of 2026-11-10. **All artifacts are public.** Nothing is left to
build; two publishing steps need your account.

| Artifact | URL | State |
|---|---|---|
| Space | https://huggingface.co/spaces/maximilianmilo/riptide | public, static, serving 200 |
| Dataset | https://huggingface.co/datasets/maximilianmilo/riptide-bench | public, **gated (manual)**, anon 401 |
| Verdicts + logs | https://huggingface.co/datasets/maximilianmilo/riptide-verdicts | public, **gated (manual)**, anon 401 |
| DPO adapter | https://huggingface.co/maximilianmilo/tiny-aya-global-riptide-dpo2 | public |
| Steering vectors | https://huggingface.co/maximilianmilo/tiny-aya-global-riptide-steer2 | public, negative result |
| Model collection | https://huggingface.co/collections/maximilianmilo/riptide-repaired-model-artifacts-6af3599ac0a67864cbd7f53c | public, 3 items |
| Dataset collection | https://huggingface.co/collections/maximilianmilo/riptide-benchmark-verdicts-and-logs-6af3599a7c085692f65e2646 | public, 2 items |
| GitHub repo | https://github.com/maximilienmil/riptide | public, 147 files |
| Video | https://youtu.be/bvprQrSPzdU | live |
| Article | `docs/article.md` | links filled, ready to paste |
| Abstract | `docs/abstract.md` | 474 words, under the 500 limit |

## What is left

1. **Publish the article.** Open https://huggingface.co/new-blog and paste
   `docs/article.md`. Every link in it resolves; no placeholders remain.
2. **Submit.** Paste `docs/abstract.md` into the Abstract field (474 words),
   and give the form the two collection URLs, the article URL, and the GitHub
   repo URL.

## What the GitHub repo does not contain, and why

- `runs/` (116 MB of transcripts and verdicts): they live in the gated
  datasets.
- `bench/scenarios/`, `labels/sheet.html`, `bench/spec/examples/f1-std-001.json`,
  `train/data/*.jsonl`: these quote transcript text from families 1, 2 and 7,
  which the dataset card gates. Verified by exact full-text matching against
  3,921 gated turns: 0 leaks in the published tree.
- `train/out/` (29 MB of adapter weights): on the Hub.

## Verification performed before publishing

- Space: deployed files hash-match the local build; public index, data JSON and
  fonts return 200; `gated_families: [1,2,7]` confirmed in the public data.
- Both gated datasets return 401 to unauthenticated requests.
- Collections resolve publicly with the expected items.
- GitHub README and repo page return 200.
- Secret scan over the staged tree: no matches.
- Video URL returns 200.

## Honest gaps

- Board coverage is 344/525: `gemma-4-26b` never started and
  `nemotron-35-lightning` has 60/120 transcripts with no verdicts. The Space
  and the README state both; do not describe the leaderboard as complete.
- Safety-axis human agreement peaks at 0.577 against the 0.6 gate, so every
  score is provisional.
- The Space's visual rendering was verified from the identical local build
  (screenshots), not by a browser in this session.
- The repo has no LICENSE file. The data-derived artifacts are CC-BY-NC-4.0;
  the code has no licence declared yet, so treat it as all rights reserved.
