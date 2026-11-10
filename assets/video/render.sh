#!/usr/bin/env bash
# Render the five Riptide beat pages to MP4.
#
# Needs only what this machine already has: the Playwright Chromium headless
# shell (browser binary only, no npm package) and ffmpeg. No network.
#
#   ./render.sh              # all five beats -> build/riptide-demo.mp4 (120 s)
#   ./render.sh beat-2-failure  # one beat -> build/beat-2-failure.mp4
#   FPS=15 ./render.sh       # smoother, slower
#
# Frames are captured by freezing each page's CSS animations at t = i/FPS
# (the pages accept ?t=seconds), so the output is deterministic.

set -euo pipefail
cd "$(dirname "$0")"

FPS="${FPS:-12}"
OUT="build"
BEATS=(beat-0-note:4 beat-1-pattern:34 beat-2-failure:34 beat-3-reportcard:30 beat-4-repair:22)

find_shell() {
  if [[ -n "${CHROME:-}" ]]; then echo "$CHROME"; return; fi
  local hit
  hit=$(ls -1 "$HOME"/Library/Caches/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-mac-*/chrome-headless-shell 2>/dev/null | tail -1)
  if [[ -z "$hit" ]]; then
    echo "No chrome-headless-shell found. Install it with: npx playwright install chromium" >&2
    exit 1
  fi
  echo "$hit"
}

SHELL_BIN="$(find_shell)"
command -v ffmpeg >/dev/null || { echo "ffmpeg not found (brew install ffmpeg)" >&2; exit 1; }
mkdir -p "$OUT"

render_beat() {
  local name="$1" dur="$2" frames i t
  frames=$(( dur * FPS ))
  mkdir -p "$OUT/$name"
  echo "== $name  ${dur}s  ${frames} frames @ ${FPS}fps"
  for (( i = 0; i < frames; i++ )); do
    t=$(awk -v i="$i" -v f="$FPS" 'BEGIN{printf "%.4f", i/f}')
    "$SHELL_BIN" --headless --disable-gpu --hide-scrollbars \
      --window-size=1920,1080 --virtual-time-budget=900 \
      --screenshot="$OUT/$name/$(printf '%05d' "$i").png" \
      "file://$PWD/$name.html?t=$t" >/dev/null 2>&1
    if (( i % 60 == 0 )); then printf '   %d/%d\n' "$i" "$frames"; fi
  done
  ffmpeg -y -loglevel error -framerate "$FPS" -i "$OUT/$name/%05d.png" \
    -c:v libx264 -pix_fmt yuv420p -crf 18 -preset medium -movflags +faststart \
    "$OUT/$name.mp4"
  echo "   -> $OUT/$name.mp4"
}

if [[ $# -gt 0 ]]; then
  for arg in "$@"; do
    dur=""
    for b in "${BEATS[@]}"; do [[ "${b%%:*}" == "$arg" ]] && dur="${b##*:}"; done
    [[ -z "$dur" ]] && { echo "unknown beat: $arg" >&2; exit 1; }
    render_beat "$arg" "$dur"
  done
  exit 0
fi

: > "$OUT/concat.txt"
for b in "${BEATS[@]}"; do
  render_beat "${b%%:*}" "${b##*:}"
  echo "file '${b%%:*}.mp4'" >> "$OUT/concat.txt"
done
ffmpeg -y -loglevel error -f concat -safe 0 -i "$OUT/concat.txt" -c copy "$OUT/riptide-demo.mp4"
echo "== $OUT/riptide-demo.mp4  (120 s, 1920x1080, no audio)"
