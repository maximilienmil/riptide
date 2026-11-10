# DESIGN.md — Riptide video kit

Bold, modern, large. A two-minute motion piece for judges watching on a laptop,
often muted: so the type is the film. One idea per frame, a headline or a number
that fills the canvas, three decisive grounds, one strong left edge.

Replaces the earlier quiet-serif editorial kit (EB Garamond, 14–34 px type,
dense tables, hairline rules), which Max rejected: too small, too dense, not
following the impeccable or Hallmark guidelines. Nothing of that look is kept.

## References studied, and what was taken

Fetched and read: impeccable.style (its `kinpaku-tokens` and page CSS) and
usehallmark.com (`style.css`).

| Token | impeccable.style | usehallmark.com | Riptide |
|---|---|---|---|
| Text face | Albert Sans 400–700 | Geist 400–600 | **Albert Sans**, variable 100–900 |
| Display face | Alumni Sans 200–800 (wordmark, display) | Newsreader / Fraunces, tracking −0.025 to −0.035em | **Alumni Sans 800** for numerals and wordmark; Albert Sans 800 at −0.03 to −0.04em for headlines |
| Display size | clamp(3.2rem, 6.2vw, 5.6rem), line-height 1 | clamp(2.75rem, …, 5.5rem), 8–9 steps of 4px space | 96 to 168 px headlines, 420 to 660 px numerals at 1920 wide (the same ratio to the canvas, scaled for video) |
| Ground | paper `oklch(97.8% 0 0)`, ink `oklch(13% 0 0)`, instrument greys | paper `#FAFAF9`, ink `#0F0F0E`, ink panel `#121211` | paper `#F7F7F4`, ink `#111110` |
| Accent | one saturated hue as a field (kinpaku gold `oklch(84% .19 80)`) | one orange `#FC4C02` | signal `#FF4D00`; patina `#3FD8C3` is impeccable's own second hue (`--ks-patina`) |
| Rules | 1px `oklch(13% 0 0 / .08)`, radius 3–8 | 1px lines, radius 14 | radius 0, 2px rules only in the one table |
| Motion | functional, short | `--ease-out: cubic-bezier(.16,1,.3,1)`, 320 ms; 160 ms fast | the same exponential ease-out, 800–1100 ms (film, not UI) |
| Composition | huge type, one idea per section, tight groups, big gaps between | full-bleed ink and paper panels, one idea per screen | full-bleed grounds, headline top-left, supporting line anchored to the foot |

## Tokens

### Type
Albert Sans (text) and Alumni Sans (numerals, wordmark). Both SIL OFL, embedded
as base64 in each page, so macOS previews, the HyperFrames render and the
fallback renderer all draw the same glyphs. `fonts/` holds the woff2 files.

| Class | Face · weight · size / line-height · tracking | Used for |
|---|---|---|
| `.num` | Alumni Sans 800 · 400–660 px / .74 | huge numerals: 88, 24, 0, 24 → 36 |
| `.h-xl` | Albert Sans 800 · 168 / .94 · −.04em | the pattern line, the turn-4 quote, closing frame |
| `.h-l` | 800 · 128 / .96 · −.035em | content note, "She is fifteen.", two judges |
| `.h-m` | 800 · 96 / 1 · −.03em | one-line headlines, "Turn 6. She says goodbye." |
| `.h-s` | 800 · 72 / 1.04 · −.025em | judge rationale heads, counts, support line |
| `.q` | 700 · 60–72 / 1.14 · −.018em | the model's words, the careful reply |
| `.p` | 500 · 52–64 / 1.22 · −.01em | the user's words, deck lines |
| `.p-s` | 500 · 40–44 / 1.3 | rationale text, notes |
| `.lab` | 600 · 32 / 1.2 | speaker tags, axis labels |
| chrome | wordmark Alumni 800 56 px · tag 600 28 px | top left, top right |
| `.src` | 500 · **20 px** | source line only |

Nothing is set below **28 px** except the source line (`verify_pages.py`
enforces it). Tracking never goes below −0.04em. Numerals are tabular.

### Colour: three grounds, two signals
| Token | Value | Meaning |
|---|---|---|
| ink | `#111110` | evidence ground; text on paper |
| paper | `#F7F7F4` | verdict ground; text on ink |
| signal | `#FF4D00` | unsafe: a score of 0 or 1, a pass rate under half, a negative delta. Also a full ground for the two loudest frames (the promise, 0/16) |
| patina | `#3FD8C3` (on paper `#0B7D6E`) | help and improvement: the support line, +delta, DPO's gain |
| mute | ink `#A3A39B` · paper `#5B5B55` · signal `#33150A` | secondary text; every pair is above 4.5:1 |

Colour lives at page scale: the frame owns the ground. No tints, no alpha, no
gradients, no shadows, no glow.

### Space and grid
1920×1080. Margin 96 px left and right. Wordmark baseline at y 46–102; body
starts y 150; body ends y 950; the foot (crisis line at y 966, source line at y
1028) never moves. One strong left edge at x 96: every headline, number and
quote starts there. Supporting lines anchor to the foot with `margin-top:auto`,
so a frame reads as one big thing at the top, a small fact at the bottom, and
air between. Eight-pixel steps (8 / 12 / 20 / 28 / 44 / 56 / 96).

### Motion
Exponential ease-out `cubic-bezier(.16,1,.3,1)` for every entrance (impeccable
and Hallmark's own curve), 0.8–1.1 s. Four moves only:

- **line lift**: a headline line rises out of its own mask (`.ln`), 0.12 s apart
- **rise**: a block moves up 56 px and fades in
- **grow**: a bar scales from its baseline (`growx`, `growy`)
- **wipe**: each frame wipes up over the last (`clip-path`, 0.6 s,
  `cubic-bezier(.76,0,.24,1)`)

Contents of a frame start 0.6 s after its wipe begins, so the eye arrives, then
reads. One thing enters at a time. No scale, no bounce, no loop, no pulse.

## How each impeccable and Hallmark rule is applied

| Rule | Applied as |
|---|---|
| Big confident sans, high contrast | Albert Sans 800 at 96–168 px on ink, paper or signal; the lowest text-contrast pair is 5.2:1 |
| One idea per frame | 20 frames, each with one headline or one number; dense content is split, never shrunk (report card is 5 frames) |
| Huge numerals | Alumni 800 at 420–660 px for 88, 24, 24 → 36, 24 → 19, 0/16 |
| Decisive colour at page scale | three whole-frame grounds; signal fills two frames outright |
| Strong grid, tight groups, big gaps | one left edge at x 96, foot-anchored support lines, no equal gaps |
| Nothing small | 28 px floor, enforced; source line the one exception |
| Purposeful motion | one authored move per element, exponential ease-out, wipe between frames |
| **Ban:** kicker or eyebrow above a heading | removed; speaker tags sit under the line they label (turn 4 tag is below the promise) or label a block, never head one |
| **Ban:** section numbers | none; the frame order carries the sequence |
| **Ban:** hero-metric template (big number, small label, supporting stats) | each numeral is the headline, with one sentence under it, no stat row |
| **Ban:** icon-plus-heading cards, nested cards | no cards at all; ground and space do the grouping |
| **Ban:** gradient text, glass, hard offset shadows, side-stripe borders | none present |
| **Ban:** side-tab accent border | none |
| Display faces with a point of view | Alumni Sans, impeccable's own wordmark face; no Inter, Fraunces, Space Grotesk, DM Sans, Plus Jakarta, Instrument Sans or other default |
| Tracking floor −0.04em, display balanced | `.h-xl` at −.04; quotes use `text-wrap:balance` |
| Light or dark chosen by scene, not category | ink for evidence, paper for verdicts, signal for the two moments a number should hurt |
| Browser surfaces themed | `::selection` set to signal on ink; numerals tabular |
| Real content, no placeholders | every quote verbatim from the transcript; every number read from the verdict files |
| AI-default look refused | no cream paper, no serif display, no terracotta; no dark-plus-neon glow; no broadsheet hairlines |

## Why the display sizes exceed 6rem
The impeccable floor caps web display at 6rem (96 px at 1×). A 1920 px frame is
read at about half that on a laptop, so the film scales the same ratio up: 96 px
is the smallest headline here, 168 px the largest, and numerals run to 660 px.
The rule is about proportion to the viewport, and it is kept.

## Content rules kept
The 988 / findahelpline.com note opens the film (frame 0). The same line sits at
y 966 on all four frames of the failing-turn scene. The family-6 secrecy example
is the only transcript on that scene; turn 5 and every other family's sensitive
text are absent. Quotes are verbatim; `verify_numbers.py` asserts them.
