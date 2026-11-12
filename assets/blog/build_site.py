"""Render the article to a static page in the Space/video design system.

Output goes to site/ (gitignored): the same bytes are published to GitHub
Pages and to a static Hugging Face Space.

    ~/.hermes/hermes-agent/venv/bin/python assets/blog/build_site.py

Tokens come from space/index.html and assets/video/DESIGN.md so the article,
the report cards and the video share one look.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "site"
SRC = ROOT / "docs" / "article.md"
THUMB = ROOT / "assets" / "blog" / "thumbnail.png"
FONTS = ROOT / "space" / "fonts"

TITLE = "Riptide: every reply sounds kind, the conversation is not"

CSS = """
:root{
  --ink:#111110; --paper:#F7F7F4; --signal:#FF4D00; --patina:#3FD8C3;
  --patina-p:#0B7D6E; --mute-p:#5B5B55; --cell:#E9E9E3; --rule:#DCDCD5;
  --sans:"Albert Sans","Avenir Next","Helvetica Neue",Arial,sans-serif;
  --cond:"Alumni Sans","Albert Sans",sans-serif;
}
@font-face{font-family:"Albert Sans";src:url("fonts/albert-sans.woff2") format("woff2");font-weight:400;font-display:swap}
@font-face{font-family:"Alumni Sans";src:url("fonts/alumni-sans.woff2") format("woff2");font-weight:400;font-display:swap}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font:400 19px/1.62 var(--sans);
  font-feature-settings:"kern" 1;-webkit-font-smoothing:antialiased}
.wrap{max-width:min(46rem,calc(100% - 3rem));margin:0 auto;padding:0 0 6rem}
header.top{padding:4.5rem 0 2.5rem;border-bottom:2px solid var(--ink)}
.kicker{font:600 13px/1 var(--sans);letter-spacing:.18em;text-transform:uppercase;color:var(--mute-p);margin:0 0 1.4rem}
h1{font:400 clamp(2.4rem,6vw,4rem)/1.02 var(--cond);letter-spacing:-.01em;margin:0 0 1.2rem}
.byline{color:var(--mute-p);font-size:15px;margin:0 0 1.6rem}
.byline a{color:var(--patina-p)}
.artifacts{display:flex;flex-wrap:wrap;gap:.5rem 1.2rem;font-size:15px;margin:0}
.artifacts a{color:var(--patina-p);text-decoration:none;border-bottom:1px solid rgba(11,125,110,.35)}
.artifacts a:hover{border-bottom-color:var(--patina-p)}
img.hero{display:block;width:100%;height:auto;margin:2.6rem 0 0;border:1px solid var(--rule)}
.disclosure{margin:0 0 1.6rem;padding:.9rem 1rem;border-left:3px solid var(--signal);
  background:var(--cell);font-size:15px;line-height:1.55;color:var(--mute-p)}
.disclosure p{margin:0}
.disclosure strong{color:var(--ink)}
article{padding-top:2.6rem}
h2{font:400 clamp(1.7rem,3.4vw,2.3rem)/1.15 var(--cond);margin:3.2rem 0 .9rem}
h3{font:600 1.05rem/1.4 var(--sans);margin:2.2rem 0 .6rem}
p{margin:0 0 1.15rem}
a{color:var(--patina-p)}
ul,ol{margin:0 0 1.2rem;padding-left:1.3rem}
li{margin:.35rem 0}
code{font:400 .88em/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--cell);
  padding:.12em .35em;border-radius:2px}
pre{background:var(--cell);padding:1rem 1.1rem;overflow-x:auto;margin:0 0 1.3rem}
pre code{background:none;padding:0;font-size:.85em}
table{width:100%;border-collapse:collapse;margin:0 0 1.5rem;font-size:15px}
th{text-align:left;font:600 12px/1.4 var(--sans);letter-spacing:.08em;text-transform:uppercase;
  color:var(--mute-p);border-bottom:2px solid var(--ink);padding:.55rem .6rem .55rem 0}
td{border-bottom:1px solid var(--rule);padding:.55rem .6rem .55rem 0;vertical-align:top}
blockquote{margin:0 0 1.3rem;padding-left:1.1rem;border-left:3px solid var(--signal);color:var(--mute-p)}
hr{border:0;border-top:1px solid var(--rule);margin:2.6rem 0}
footer{border-top:2px solid var(--ink);margin-top:4rem;padding-top:1.6rem;font-size:15px;color:var(--mute-p)}
footer a{color:var(--patina-p)}
@media (max-width:520px){body{font-size:17px}.wrap{max-width:calc(100% - 2rem)}}
"""


def main() -> int:
    text = SRC.read_text()
    m = re.match(r"#\s+(.+?)\n", text)
    if not m:
        raise SystemExit("article has no leading H1")
    body_md = text[m.end():]
    html = markdown.markdown(
        body_md,
        extensions=["tables", "fenced_code", "sane_lists", "attr_list"],
        output_format="html5",
    )

    # the disclosure is the first paragraph of the source; lift it into the
    # header so it is visible without scrolling past the hero
    disclosure = ""
    dm = re.match(r"\s*<p><strong>Disclosure\.</strong>.*?</p>\s*", html, re.S)
    if dm:
        disclosure = '<div class="disclosure">' + dm.group(0).strip() + "</div>"
        html = html[dm.end():]

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "fonts").mkdir(parents=True)
    for f in FONTS.glob("*.woff2"):
        shutil.copy2(f, OUT / "fonts" / f.name)
    shutil.copy2(THUMB, OUT / "thumbnail.png")
    (OUT / ".nojekyll").write_text("")

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{TITLE}</title>
<meta name="description" content="A multi-turn safety audit of eight chatbot configurations, scored turn by turn by two independent judges, plus a repair that keeps the model kind.">
<meta property="og:title" content="{TITLE}">
<meta property="og:image" content="thumbnail.png">
<meta property="og:type" content="article">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header class="top">
  <p class="kicker">Riptide &middot; multi-turn safety audit</p>
  <h1>{m.group(1)}</h1>
  <p class="byline">Maximilian Milovidov &middot; November 2026</p>
  {disclosure}
  <p class="artifacts">
    <a href="https://huggingface.co/spaces/maximilianmilo/riptide">Report cards</a>
    <a href="https://huggingface.co/datasets/maximilianmilo/riptide-bench">Dataset</a>
    <a href="https://huggingface.co/datasets/maximilianmilo/riptide-verdicts">Verdicts</a>
    <a href="https://huggingface.co/maximilianmilo/tiny-aya-global-riptide-dpo2">Adapter</a>
    <a href="https://github.com/maximilienmil/riptide">Code</a>
    <a href="https://youtu.be/bvprQrSPzdU">Video</a>
  </p>
  <img class="hero" src="thumbnail.png" alt="Riptide: 81% of conversations clean at turn 2, 17% at turn 12" width="1300" height="650">
</header>
<article>
{html}
</article>
<footer>
  <p><strong>Riptide</strong> &middot; real judged transcripts, no invented numbers.
  Crisis help: <a href="tel:988">988</a> (US/Canada) or
  <a href="https://findahelpline.com">findahelpline.com</a>.
  Transcript text for the disclosure and age families is distributed only through
  the gated dataset.</p>
</footer>
</div>
</body>
</html>
"""
    (OUT / "index.html").write_text(page)
    print(f"wrote {OUT / 'index.html'} ({len(page):,} bytes)")
    print("tables rendered:", html.count("<table>"))
    print("h2 sections:", html.count("<h2>"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
