# RENDER.md — turning the five pages into an MP4

Checked on this machine on 2026-11-10. The preferred path (HyperFrames) and the
fallback (headless Chromium + ffmpeg) both produce a 1920×1080, 120 s, silent
MP4 from these five files.

| Tool | State |
|---|---|
| `ffmpeg` | 9.0.2 at `/opt/homebrew/bin/ffmpeg` |
| Node / npm | v26.8.1 / 11.19.0 |
| Playwright Chromium headless shell | in `~/Library/Caches/ms-playwright/` (browser binary only) |
| HyperFrames | not installed globally; `npx hyperframes@0.9.28` works, Apache-2.0, renders locally |

---

## Path A — HyperFrames (preferred, verified)

```bash
cd assets/video
./render-hyperframes.sh          # -> riptide-demo.mp4  (120 s) + build/ clips
./render-hyperframes.sh beat-2-failure   # -> build/beat-2-failure.mp4
FPS=30 ./render-hyperframes.sh   # what the shipped film used
```

Each page is copied into a scratch directory as `index.html`, rendered, and the
five clips are concatenated with ffmpeg. The pages declare
`data-composition-id="root" data-width="1920" data-height="1080"`, and the
page's longest CSS animation is the beat's length (5/33/30/30/22 s).

```
beat-0-note        1920x1080    5.000 s
beat-1-pattern     1920x1080   33.000 s
beat-2-failure     1920x1080   30.000 s
beat-3-reportcard  1920x1080   30.000 s
beat-4-repair      1920x1080   22.000 s
riptide-demo       1920x1080  120.000 s
```

**Fonts.** Albert Sans and Alumni Sans (both SIL OFL, files in `fonts/`) are
embedded as base64 `@font-face` in every page by `build_beats.py`, so the film,
a browser preview and `render.sh` all draw the same glyphs. Nothing is fetched
at render time.

**Stills.** `uv run python shots.py` cuts one PNG per frame (20) out of `build/`, so
`shots/` matches the film exactly; it reads `frames.json`. It needs the render first.

**Do not** pass `--composition` at a page from outside the project directory;
the scratch-directory copy is what makes the relative paths and the composition
root line up.

---

## Path B — headless Chromium + ffmpeg (fallback, no packages)

```bash
cd assets/video
./render.sh                        # -> build/riptide-demo.mp4
./render.sh beat-2-failure         # -> build/beat-2-failure.mp4
FPS=15 ./render.sh                 # smoother, slower
```

This path uses only the Chromium binary in the Playwright cache and `ffmpeg`.
It captures one PNG per frame by freezing the page's CSS animations at
`t = frame / fps` (each page accepts `?t=seconds`), then encodes the sequence.
Deterministic, and it renders the macOS faces rather than HyperFrames' bundled
ones, so line breaks can differ by a few pixels from the film.

If `chrome-headless-shell` is missing, install it once with
`npx playwright install chromium`, or set `CHROME=/path/to/chrome`.

---

## Path C — screen record, cut in any editor (no tooling)

1. Open a page in a browser window sized 1920×1080.
2. Record that window (macOS: `⇧⌘5` → Record Selected Portion, 1920×1080).
3. Record each page for its full length (5, 33, 30, 30, 22 s). Frames wipe
   into each other inside the page.
4. Cut the five clips back to back. Scenes cut hard; no crossfade is needed.

---

## Notes that apply to every path

- **No audio.** No voiceover, no music. Scene cuts land at 5 s, 38 s, 68 s and 98 s.
- **Captions are inside the pages**, not a separate SRT. `BEATS.md` lists every
  caption with its in and out time and the beat offsets.
- **Do not upscale.** Render at 1920×1080, 12–30 fps. `yuv420p` and
  `-movflags +faststart` keep the file playable in QuickTime and in browsers.
- **Check the copy before shipping:** `uv run python verify_pages.py` (layout,
  no overflow, no console noise) and `uv run python verify_numbers.py` (every
  figure and quote against the verdict files).
