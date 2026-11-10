# Submit checklist

Status as of 2026-11-10, after the publish flip. **All four artifacts are
public. Nothing is left to build.**

| Artifact | URL | State |
|---|---|---|
| Space | https://huggingface.co/spaces/maximilianmilo/riptide | public, static, serving 200 |
| Dataset | https://huggingface.co/datasets/maximilianmilo/riptide-bench | public, **gated (manual)**, anon access 401 |
| DPO adapter | https://huggingface.co/maximilianmilo/tiny-aya-global-riptide-dpo2 | public |
| Steering vectors | https://huggingface.co/maximilianmilo/tiny-aya-global-riptide-steer2 | public, negative result |
| Video | https://youtu.be/bvprQrSPzdU | live |
| Article | `docs/article.md` | links filled, ready to paste |
| Abstract | `docs/abstract.md` | 474 words, under the 500 limit |

## What is left

1. **Publish the article.** Open https://huggingface.co/new-blog and paste
   `docs/article.md`. The four artifact links and the video link are already
   in it; no placeholders remain.
2. **Submit.** Paste the abstract from `docs/abstract.md` into the form's
   Abstract field (474 words), and give it the four URLs plus the video.

## Verification performed before flipping public

- Deployed Space files hash-matched the local build, file for file.
- Public index, `data/index.json`, and both fonts return 200 unauthenticated.
- Public `data/index.json` carries `gated_families: [1, 2, 7]`, so the
  transcript text that the dataset card gates is not in the page.
- Dataset returns 401 to an unauthenticated request, as gating requires.
- One stale file was removed from the Space: `style.css`, 388 bytes, not
  referenced by `index.html` (the CSS is inlined), absent from the local build.
- Video URL returns 200.

## Honest gaps

- Board coverage is 344/525: `gemma-4-26b` never started and
  `nemotron-35-lightning` has 60/120 transcripts with no verdicts. The Space
  states both; do not describe the leaderboard as complete.
- Safety-axis human agreement peaks at 0.577 against the 0.6 gate, so every
  score is provisional and the article says so.
- The Space's visual rendering was verified from the identical local build
  (screenshots), not by a browser in this session; no browser was attached.
