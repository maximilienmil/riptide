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

1. **The article is published, but not as an HF blog post.** Hub docs require,
   for publishing under a personal namespace, a confirmed email **and** either
   an active PRO subscription or a write/admin role in a Team/Enterprise org.
   This account has `isPro: false` and no orgs, so `huggingface.co/new-blog`
   returns 403. Rather than pay, the same article is served from two free hosts:

   | Host | URL |
   |---|---|
   | GitHub Pages | https://maximilienmil.github.io/riptide/ |
   | Static Space (on the Hub) | https://huggingface.co/spaces/maximilianmilo/riptide-article |

   Both are built from `docs/article.md` by `assets/blog/build_site.py` in the
   Space/video design system, so the article, the report cards and the video
   match. Give the form the Space URL if it wants a Hugging Face link, and the
   Pages URL as the public web version.

   The only free route to a real `huggingface.co/blog/...` URL is membership of
   the `blog-explorers` org: request it from the org page, then publish
   `docs/article-hf-blog.md` (front-matter and thumbnail are ready). Approval is
   not guaranteed before the deadline.
2. **Submit.** Paste `docs/abstract.md` into the Abstract field (474 words),
   and give the form the two collection URLs, an article URL from the table
   above, and the GitHub repo URL.

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

## Deadline and consent (recorded 2026-11-12)

Three boxes on the form are being ticked, and the third one freezes the
submission:

1. The article and submission may be shared and promoted by Hugging Face and
   Cohere on their socials, and there may be an invitation to a featured blog
   based on the submission.
2. The organising team may tag the author for winning, featured or highlighted
   submissions.
3. **All repos and collections are public and final as of Nov 15, 11:59 PM AoE.
   Nothing changes after the deadline.**

Deadline in local time: **Monday 16 November 2026, 06:59 EST** (11:59 UTC).
In practice that is Sunday night, not Monday.

Because box 3 freezes everything, here is the state that would be frozen if
nothing else changes:

| Repo | Type | Visibility | Commit |
|---|---|---|---|
| `maximilianmilo/riptide` | space | public | `016bbb31` |
| `maximilianmilo/riptide-article` | space | public | `80973095` |
| `maximilianmilo/riptide-bench` | dataset | public, gated (manual) | `c7e15bb4` |
| `maximilianmilo/riptide-verdicts` | dataset | public, gated (manual) | `25635c22` |
| `maximilianmilo/tiny-aya-global-riptide-dpo2` | model | public | `c827fab8` |
| `maximilianmilo/tiny-aya-global-riptide-steer2` | model | public | `ca2eedf3` |
| `github.com/maximilienmil/riptide` | repo | public | `92ef0e5` |
| `gh-pages` (article page) | branch | public | `29c927a3` |

The AI disclosure at the top of the article matters more under consent 1 than
it would otherwise: if Hugging Face or Cohere promote this, the authorship
statement should travel with it rather than be discovered later.

Open decision before the freeze: **the article title**. It is still the long
two-clause version. The alternative chosen in discussion is *Clean at turn two,
failing by turn twelve*, with *Riptide: a multi-turn safety audit of eight
chatbots* as the subtitle. Changing it means four edits (article H1, page
header, blog front-matter, README) and a republish of both hosts. After the
deadline it cannot be changed at all.
