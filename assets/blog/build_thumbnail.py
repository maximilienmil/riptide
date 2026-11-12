"""Build the 1300x650 blog thumbnail from the design system in space/index.html.

Fonts are the Space's own woff2 files, converted to ttf first:

    uvx --from fonttools --with brotli fonttools ttLib.woff2 decompress \
        -o /tmp/alumni.ttf space/fonts/alumni-sans.woff2
    uvx --from fonttools --with brotli fonttools ttLib.woff2 decompress \
        -o /tmp/albert.ttf space/fonts/albert-sans.woff2

    python3 assets/blog/build_thumbnail.py

Palette and type come from assets/video/DESIGN.md, which the Space and the
video both follow.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "assets" / "blog" / "thumbnail.png"

INK = "#111110"
PAPER = "#F7F7F4"
SIGNAL = "#FF4D00"
PATINA = "#0B7D6E"
MUTE = "#5B5B55"
CELL = "#E9E9E3"

COND = Path("/tmp/alumni.ttf")
SANS = Path("/tmp/albert.ttf")

W, H = 1300, 650
GUT = 84


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def tracked(draw: ImageDraw.ImageDraw, xy, text, f, fill, tracking=3):
    """Draw text with letter spacing; PIL has no native tracking."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=f, fill=fill)
        x += draw.textlength(ch, font=f) + tracking
    return x


def main() -> int:
    if not COND.exists() or not SANS.exists():
        raise SystemExit(
            "Missing converted fonts. Run the two uvx fonttools commands in "
            "this file's docstring first."
        )

    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)

    # the drift curve, drawn first so type sits over it
    pts = [(880, 214), (938, 236), (996, 276), (1054, 330), (1112, 396), (1170, 452), (1228, 486)]
    d.line(pts, fill=PATINA, width=5, joint="curve")
    d.ellipse([pts[0][0] - 8, pts[0][1] - 8, pts[0][0] + 8, pts[0][1] + 8], fill=PATINA)
    d.ellipse([pts[-1][0] - 8, pts[-1][1] - 8, pts[-1][0] + 8, pts[-1][1] + 8], fill=SIGNAL)

    tracked(d, (GUT, 74), "RIPTIDE", font(SANS, 24), INK, tracking=6)
    d.text((GUT + 176, 74), "multi-turn safety audit", font=font(SANS, 24), fill=MUTE)

    d.text((GUT, 148), "81% at turn 2.", font=font(COND, 132), fill=INK)
    d.text((GUT, 268), "17% at the end.", font=font(COND, 132), fill=SIGNAL)

    d.text(
        (GUT, 432),
        "Tiny Aya (3.3B) in 120 scripted teen conversations, scored",
        font=font(SANS, 30),
        fill=INK,
    )
    d.text(
        (GUT, 472),
        "turn by turn by two independent judges. Stronger models held",
        font=font(SANS, 30),
        fill=MUTE,
    )
    d.text(
        (GUT, 512),
        "up better. Clean means no unsafe reply so far.",
        font=font(SANS, 30),
        fill=MUTE,
    )

    d.line([(GUT, 574), (W - GUT, 574)], fill=CELL, width=2)
    d.text(
        (GUT, 594),
        "huggingface.co/spaces/maximilianmilo/riptide",
        font=font(SANS, 22),
        fill=MUTE,
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT)
    print(f"wrote {OUT} ({W}x{H})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
