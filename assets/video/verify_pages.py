#!/usr/bin/env python3
"""Check every frame of the five scene pages (frames.json) at 1920x1080.

Per frame, with CSS animation disabled and every other frame hidden:
  - nothing leaves the canvas or crosses the safe area (content stops at y=952;
    the crisis line and the source line own the foot)
  - nothing is set smaller than 28 px except the source line (20 px)
  - the persistent crisis line is on every failing-turn frame
  - no console errors

Runs the locally installed chrome-headless-shell (no npm install).

Usage:  uv run python assets/video/verify_pages.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHELL_GLOB = "~/Library/Caches/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-mac-*/chrome-headless-shell"
MIN_PX = 28          # smallest type on a frame, source line excepted
SAFE_BOTTOM = 952    # content bottom; the foot belongs to .crisis and .src
CHROME = (".wm", ".tag", ".src", ".crisis", ".clock")

PROBE = """
<script>
document.fonts.ready.then(function(){
  var out = [], frames = [].slice.call(document.querySelectorAll('.f'));
  var skip = %s;
  function isChrome(el){ return skip.some(function(s){ return el.closest(s); }); }
  frames.forEach(function(fr, i){
    frames.forEach(function(o){ o.style.display = (o === fr) ? 'block' : 'none'; });
    var id = fr.getAttribute('data-frame'), n = 0, minpx = 999, maxb = 0;
    fr.querySelectorAll('*').forEach(function(el){
      if (el.closest('.clock')) return;
      var r = el.getBoundingClientRect();
      if (!r.width && !r.height) return;
      var tag = el.tagName.toLowerCase() + (el.className && el.className.baseVal === undefined && el.className ? '.' + String(el.className).split(' ')[0] : '');
      if (r.right > 1920.5 || r.left < -0.5 || r.bottom > 1080.5 || r.top < -0.5)
        out.push('OUT ' + id + ' ' + tag + ' ' + [r.left, r.top, r.right, r.bottom].map(Math.round).join(','));
      if (!isChrome(el)) {
        if (r.right > 1824.5) out.push('MARGIN ' + id + ' ' + tag + ' right=' + Math.round(r.right));
        if (r.bottom > %d) out.push('SAFE ' + id + ' ' + tag + ' bottom=' + Math.round(r.bottom));
        if (r.bottom > maxb) maxb = r.bottom;
      }
      var own = [].some.call(el.childNodes, function(c){ return c.nodeType === 3 && c.textContent.trim(); });
      if (own && !el.closest('.src')) {
        var fs = parseFloat(getComputedStyle(el).fontSize);
        n++; if (fs < minpx) minpx = fs;
        if (fs < %d) out.push('SMALL ' + id + ' ' + tag + ' ' + fs + 'px "' + el.textContent.trim().slice(0,30) + '"');
      }
      /* text clipped by its own box */
      if (own && el.scrollWidth > el.clientWidth + 2 && getComputedStyle(el).overflow !== 'visible')
        out.push('CLIP ' + id + ' ' + tag);
    });
    var cr = fr.querySelector('.crisis');
    if (cr) {
      var c = cr.getBoundingClientRect();
      if (maxb > c.top - 6) out.push('CRISISOVERLAP ' + id + ' content=' + Math.round(maxb) + ' crisis.top=' + Math.round(c.top));
    }
    out.push('info ' + id + ' min=' + minpx + 'px content.bottom=' + Math.round(maxb) + (cr ? ' crisis' : ''));
  });
  var sw = document.documentElement.scrollWidth, sh = document.documentElement.scrollHeight;
  if (sw !== 1920 || sh !== 1080) out.push('CANVAS ' + sw + 'x' + sh);
  var t = document.createElement('pre'); t.id = 'probe'; t.textContent = out.join(' || ');
  document.body.appendChild(t);
});
</script>
""" % (json.dumps(list(CHROME)), SAFE_BOTTOM, MIN_PX)


def find_shell() -> str:
    hits = sorted(Path.home().glob(SHELL_GLOB.replace("~/", "")))
    if not hits:
        sys.exit("chrome-headless-shell not found in the playwright cache")
    return str(hits[-1])


def check(shell: str, page: Path) -> tuple[list[str], list[str]]:
    html = page.read_text(encoding="utf-8")
    html = html.replace("</style>", "*{animation:none !important;clip-path:none !important}</style>", 1)
    html = html.replace("</body>", PROBE + "</body>")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / page.name
        tmp.write_text(html, encoding="utf-8")
        proc = subprocess.run(
            [shell, "--headless", "--disable-gpu", "--window-size=1920,1080",
             "--virtual-time-budget=1500", "--dump-dom", tmp.as_uri()],
            capture_output=True, text=True,
        )
    m = re.search(r'<pre id="probe">(.*?)</pre>', proc.stdout, re.S)
    issues = [x.strip() for x in (m.group(1) if m else "PROBE MISSING").split("||") if x.strip()]
    noise = [ln for ln in proc.stderr.splitlines()
             if re.search(r"CONSOLE|Uncaught|SyntaxError|Failed to load", ln)]
    return issues, noise


def main() -> None:
    shell = find_shell()
    frames = json.loads((HERE / "frames.json").read_text())
    files = list(dict.fromkeys(f["file"] for f in frames))
    total = sum(f["end"] - f["start"] for f in frames)
    print(f"shell: {shell}\n{len(frames)} frames in {len(files)} scenes\n")
    bad = 0
    for name in files:
        issues, noise = check(shell, HERE / name)
        errors = [i for i in issues if not i.startswith("info")]
        print(name)
        for i in issues:
            if i.startswith("info"):
                print("  " + i[5:])
        for e in errors:
            print(f"  !! {e}")
        for n in noise[:3]:
            print(f"  console: {n.strip()[:160]}")
        # the persistent crisis line on every frame of the failing-turn scene
        if name == "beat-2-failure.html":
            html = (HERE / name).read_text()
            ncr = html.count('class="crisis"')
            want = sum(1 for f in frames if f["file"] == name)
            if ncr != want:
                print(f"  !! crisis line on {ncr} of {want} frames")
                errors.append("crisis")
        if errors or noise:
            bad += 1
        print()
    print(f"scenes: {len(files)}  frames: {len(frames)}")
    print("OK" if not bad else f"{bad} page(s) need attention")
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
