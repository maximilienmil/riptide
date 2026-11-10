# design/v3 — slop tells removed (merge-data base)

Base: copy of `design/merge-data/index.html`, revised per brief. All data still
MOCK-labelled (fakebar, MOCK tags, PLACEHOLDER labels, invented transcript).

1. Removed all "evenings / many evenings / months" framing. Each test is one
   conversation of 8 to 12 turns. Chart x-axis reads Turn 1 to Turn 10.
2. Hero rewritten to the set direction: "Most chatbots start kind. The
   question is who's still careful by turn ten." Lede states the design
   (single 8 to 12 turn conversations, turn of first unsafe reply).
3. Removed every em-dash from body copy and title. Colons and periods only.
4. Rewrote all five section headlines as statements. No stacked
   rhetorical-question headlines remain.
5. Removed generic pill-chip row (including the "Reading time" chip). Replaced
   with two factual scope sentences (placeholder scope, planned scope).
6. Renamed cute model labels (Steady, Middling, Cold, Flatter, Drifty) to
   neutral Model A to F (mock) with plain failure descriptors.
7. Report-card headers use the editorial version's plain behaviour names
   (Notices slow crisis through Acts its age).
8. Removed "not X but Y" constructions ("readable, not clinical"; "pattern,
   not precision") and triplet slogans. Each sentence states one fact.
9. Removed duplicated explanations: chart note, caption, and method box each
   state distinct facts. No repeated median-turn-6 sentences.
10. Cut filler captions and decoration. Captions add reading or scope facts
    only. No emoji-like ornament.
11. Behaviour definitions rewritten as scoring rules (what the scenario does,
    what the score records) instead of Monday/Friday vignettes.
12. Transcript viewer keeps the benign invented talent-show exchange. Turns
    labelled Turn 5 to 7. No "teen" persona voice in labels (user/model).
13. Fixed drift-chart label clipping: legend moved into open plot area with
    short labels (A 68%, C 47%, F 31%). Verified unclipped at 1440 and 390.
14. Verified layout at 1440 and 390 widths via headless-chromium screenshots:
    table scrolls horizontally at 390, pipeline and repair cards stack, no
    overlap. Previews saved as preview-1440.png and preview-390.png.
15. Footer reduced to layout facts and token provenance. No voice claims.

## Revision 2026-11-10: real numbers wired in

The page now carries measured results instead of placeholders. Numbers come
from `runs/results/leaderboard.json` and are injected by
`runs/results/render.py` between `<!-- AUTO:... -->` markers, so a rebuild
after the Luna re-judge queue lands needs no HTML edits:

```
uv run python runs/results/compute.py
uv run python runs/results/render.py
uv run --with pillow python runs/results/preview.py
```

16. Judge B (Codex gpt-6-luna) is the primary column, because judge A
    (Muse Spark) is also a tested model. Where Luna verdicts are missing the
    cell says `pending`; it is never filled with judge A.
17. Stat row replaced with four measured facts: base survival 79 to 19%
    (turn 2 to 12, judge B, n=105), base median first failure turn 5,
    Luna-vs-human safety kappa 0.58 [0.40, 0.74], and 29 to 32 scenario
    passes after DPO (exact McNemar p=0.72, not significant).
18. Drift chart redrawn from the real survival curves for Tiny Aya base,
    Aya Expanse 8B and Muse Spark under judge B. Axis runs T2 to T12; the
    footnote carries each n.
19. Report-card rows are the five 120-scenario models, sorted by judge-B
    pass rate. Grades map pass rate: A >=90%, B >=70%, C >=50%, D >=25%,
    F below. Rows without a Luna side say "judge A, Luna pending" in the
    row itself.
20. Repair cards now use mean score per judged turn on a 0 to 3 scale
    (base, +DPO, +steer), so the warmth gain and the rational-updating
    regression are visible without rescaling. The Luna side of both repair
    runs is pending, so the block is labelled judge A.
21. The transcript in section 05 stays invented and is now labelled
    "illustrative" rather than MOCK; no count on the page depends on it.
22. Previews re-rendered with the pinned headless shell
    (`chromium_headless_shell-1248`) at 1440 and 390 CSS px, cropped to the
    last non-background row.
