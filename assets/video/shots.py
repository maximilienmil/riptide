#!/usr/bin/env python3
"""Cut one still per frame out of the rendered clips into shots/.

The stills come from the MP4s rather than from a browser screenshot, so what
sits in shots/ is exactly what the film shows, including the fonts HyperFrames
actually renders with. frames.json (written by build_beats.py) lists every frame,
its scene, and the time inside the scene at which all of its parts have landed.

Run ./render-hyperframes.sh first (it writes build/beat-*.mp4), then:

Usage:  uv run python assets/video/shots.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
SHOTS = HERE / "shots"


def main() -> None:
    SHOTS.mkdir(exist_ok=True)
    for old in SHOTS.glob("*.png"):
        old.unlink()
    frames = json.loads((HERE / "frames.json").read_text())
    for fr in frames:
        clip = BUILD / f"{fr['file'][:-5]}.mp4"
        if not clip.exists():
            sys.exit(f"{clip} missing: run ./render-hyperframes.sh first")
        out = SHOTS / f"{fr['frame']}.png"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{fr['shot']:g}", "-i", str(clip),
             "-frames:v", "1", str(out)],
            check=True,
        )
        print(f"  shots/{out.name:18s} {fr['beat']} t={fr['shot']:g}s")


if __name__ == "__main__":
    main()
