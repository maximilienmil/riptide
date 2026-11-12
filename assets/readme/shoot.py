"""Re-shoot the README screenshots of the live Space design.

    uv run --with playwright python assets/readme/shoot.py
    (first time: uvx playwright install chromium, or set CHROMIUM=/path/to/chrome)

Serves space/ locally, loads it at 1440 px wide with reduced motion (so reveal
animations land in their final state), waits for charts and data, then crops
named sections to assets/readme/space-*.png. Each shot lists candidate
selectors; if none match (section ids changed) it falls back to a full-width
viewport crop at a fixed scroll fraction. The transcript viewer (#read) is
never captured, since it can show gated-family text. Anything on the page that
names an excluded model (BANNED below) is hidden before capture, and the run
fails loudly if such text is still visible in a shot.
"""
import re
import functools, http.server, os, threading
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
W, H = 1440, 900
BANNED = "gemma|nemotron"

# name -> (candidate selectors, fallback scroll fraction of page)
SHOTS = {
    "space-hero": (["main > .g-paper:first-child", "main > div:first-child", "#top", "header"], 0.0),
    "space-grid": (["#grid", "section:has(#rc-table)", "#rc-table"], 0.42),
    "space-repair": (["#repair", "section:has(#beat-dpo)"], 0.62),
}


def serve():
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / "space"))
    h.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main():
    srv = serve()
    url = f"http://127.0.0.1:{srv.server_port}/index.html"
    with sync_playwright() as p:
        kw = {"executable_path": os.environ["CHROMIUM"]} if os.environ.get("CHROMIUM") else {}
        b = p.chromium.launch(**kw)
        pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1, reduced_motion="reduce")
        pg.goto(url, wait_until="networkidle")
        pg.evaluate("document.fonts.ready")
        pg.wait_for_timeout(2500)
        pg.evaluate("""(re) => {
          const rx = new RegExp(re, 'i');
          document.querySelectorAll('main *').forEach(el => {
            if (!rx.test(el.textContent)) return;
            if ([...el.children].some(c => rx.test(c.textContent))) return;  // deepest match only
            const blk = el.closest('tr,p,li') || el;
            blk.style.display = 'none';
          });
        }""", BANNED)
        total = pg.evaluate("document.documentElement.scrollHeight")
        for name, (sels, frac) in SHOTS.items():
            done = False
            for s in sels:
                loc = pg.locator(s).first
                try:
                    if loc.count() and loc.is_visible():
                        loc.scroll_into_view_if_needed()
                        pg.wait_for_timeout(600)
                        box = loc.bounding_box()
                        if box and box["height"] > 200:
                            loc.screenshot(path=str(OUT / f"{name}.png"), animations="disabled")
                            if re.search(BANNED, loc.inner_text(), re.I):
                                raise SystemExit(f"{name}: excluded-model text still visible")
                            done = True
                            print(name, "<-", s)
                            break
                except Exception as e:
                    print(name, s, "failed:", e)
            if not done:
                pg.evaluate(f"window.scrollTo(0, {int(total * frac)})")
                pg.wait_for_timeout(600)
                if re.search(BANNED, pg.evaluate("document.body.innerText"), re.I):
                    print(name, "WARNING: excluded-model text may be in viewport")
                pg.screenshot(path=str(OUT / f"{name}.png"))
                print(name, "<- viewport fallback at", frac)
        b.close()
    srv.shutdown()


main()
