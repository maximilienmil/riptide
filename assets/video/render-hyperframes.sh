#!/usr/bin/env bash
# Render the five beat pages with HyperFrames (preferred path).
#
# HyperFrames renders one composition per project directory, so each page is
# copied into a scratch project as index.html, rendered, and the clips are
# concatenated with ffmpeg. The pages declare data-width/data-height, so the
# output is 1920x1080 and the clip length is the page's own animation length.
#
#   ./render-hyperframes.sh                 # all five -> riptide-demo.mp4 (120 s)
#   ./render-hyperframes.sh beat-2-failure  # one beat  -> build/beat-2-failure.mp4
#   FPS=30 ./render-hyperframes.sh
#
# First run needs the network once (npx fetches hyperframes, Apache-2.0, no paid
# component). After that it renders offline.

set -euo pipefail
cd "$(dirname "$0")"

FPS="${FPS:-12}"
OUT="${OUT:-build}"
HF_VERSION="hyperframes@0.9.28"
BEATS=(beat-0-note beat-1-pattern beat-2-failure beat-3-reportcard beat-4-repair)

command -v ffmpeg >/dev/null || { echo "ffmpeg not found (brew install ffmpeg)" >&2; exit 1; }
mkdir -p "$OUT"
OUT_ABS="$(cd "$OUT" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

render_beat() {
  local name="$1" dir="$WORK/$1"
  mkdir -p "$dir"
  cp "$name.html" "$dir/index.html"
  echo "== $name"
  ( cd "$dir" && npx -y "$HF_VERSION" render . --fps "$FPS" --quiet -o "$OUT_ABS/$name.mp4" )
  echo "   -> $OUT/$name.mp4"
}

if [[ $# -gt 0 ]]; then
  for arg in "$@"; do
    [[ -f "$arg.html" ]] || { echo "unknown beat: $arg" >&2; exit 1; }
    render_beat "$arg"
  done
  exit 0
fi

: > "$OUT/concat.txt"
for b in "${BEATS[@]}"; do
  render_beat "$b"
  echo "file '$b.mp4'" >> "$OUT/concat.txt"
done
ffmpeg -y -loglevel error -f concat -safe 0 -i "$OUT/concat.txt" -c copy "$OUT/riptide-demo.mp4"
cp "$OUT/riptide-demo.mp4" riptide-demo.mp4
echo "== riptide-demo.mp4  (120 s, 1920x1080, no audio)"
