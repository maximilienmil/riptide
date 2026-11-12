"""Build assets/readme/banner.png and video.png (design: assets/video/DESIGN.md).

Fonts: convert the Space's woff2 to ttf first (see assets/blog/build_thumbnail.py),
then pass the folder: python3 build_images.py /path/with/alumni.ttf+albert.ttf
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
FD = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp")
INK, PAPER, SIGNAL, PATINA, MUTE = "#111110", "#F7F7F4", "#FF4D00", "#3FD8C3", "#A3A39B"


def F(name, size, wt):
    f = ImageFont.truetype(str(FD / f"{name}.ttf"), size)
    f.set_variation_by_axes([wt])
    return f


def tracked(d, xy, text, f, fill, tr):
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += d.textlength(ch, font=f) + tr
    return x


def banner():
    W, H, G = 1600, 640, 96
    img = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(img)
    # mark: a drift line falling from patina to signal, then the wordmark
    pts = [(G, 92), (G + 14, 98), (G + 28, 112), (G + 42, 124)]
    d.line(pts, fill=PATINA, width=6, joint="curve")
    d.ellipse([G - 7, 85, G + 7, 99], fill=PATINA)
    d.ellipse([G + 35, 117, G + 49, 131], fill=SIGNAL)
    tracked(d, (G + 70, 62), "RIPTIDE", F("alumni", 64, 800), PAPER, 5)
    d.text((G, 180), "A turn-by-turn", font=F("albert", 76, 800), fill=PAPER)
    d.text((G, 262), "safety audit for", font=F("albert", 76, 800), fill=PAPER)
    d.text((G, 344), "teen conversations.", font=F("albert", 76, 800), fill=PAPER)
    d.text((G, 500), "Six models in eight configurations.", font=F("albert", 28, 500), fill=MUTE)
    d.text((G, 540), "120 scripted teen conversations, every reply scored.", font=F("albert", 28, 500), fill=MUTE)
    # the finding, right column
    RX = 940
    num = F("alumni", 290, 800)
    d.text((RX, 135), "24", font=num, fill=MUTE)
    ax = RX + d.textlength("24", font=num) + 26
    d.line([(ax, 290), (ax + 86, 290)], fill=MUTE, width=6)
    d.polygon([(ax + 104, 290), (ax + 72, 270), (ax + 72, 310)], fill=MUTE)
    d.text((ax + 126, 135), "36", font=num, fill=PATINA)
    d.text((RX, 455), "of 120 conversations stayed safe", font=F("albert", 40, 800), fill=PAPER)
    d.text((RX, 506), "Tiny Aya, before and after DPO repair.", font=F("albert", 28, 500), fill=MUTE)
    d.text((RX, 546), "Luna judge, McNemar p = 0.023.", font=F("albert", 28, 500), fill=MUTE)
    img.save(ROOT / "assets/readme/banner.png", optimize=True)


def video():
    src = Image.open(ROOT / "assets/video/shots/1a-kind.png").convert("RGB").resize((1600, 900), Image.LANCZOS)
    d = ImageDraw.Draw(src)
    cx, cy, r = 1300, 450, 112
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=INK)
    d.polygon([(cx - 34, cy - 54), (cx - 34, cy + 54), (cx + 62, cy)], fill=PAPER)
    d.rectangle([0, 820, 1600, 900], fill=INK)
    d.text((80, 840), "Watch the 2-minute demo", font=F("albert", 36, 800), fill=PAPER)
    t = "youtu.be/bvprQrSPzdU  ·  captioned"
    d.text((1520 - d.textlength(t, font=F("albert", 28, 500)), 846), t, font=F("albert", 28, 500), fill=MUTE)
    src.save(ROOT / "assets/readme/video.png", optimize=True)


banner(); video()
