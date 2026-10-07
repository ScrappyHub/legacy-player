"""Measure text contrast in the running app, including on gradient cards.

For every visible piece of text it hides the text, photographs what is behind it, and compares the text colour with
the worst (closest in brightness) background pixel. WCAG asks for 4.5:1 for normal text and 3:1 for large text.

    python tools/contrast_check.py            # starts its own copy of the app, checks every page, prints failures
"""
from __future__ import annotations

import io
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = ["home", "library", "setup", "together", "servers", "engines", "controllers", "saves", "emulators", "settings",
         "credits", "help", "storage", "profile", "display"]

JS_ITEMS = """() => {
  const out = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walker.nextNode())) {
    const t = (n.textContent || '').trim();
    if (!t) continue;
    const el = n.parentElement;
    if (!el || ['SCRIPT', 'STYLE', 'SVG', 'OPTION'].includes(el.tagName.toUpperCase())) continue;
    const cs = getComputedStyle(el);
    if (cs.webkitBackgroundClip === 'text' || cs.backgroundClip === 'text') continue;   // gradient-filled text: checked by eye
    if (cs.visibility === 'hidden' || cs.display === 'none' || parseFloat(cs.opacity) === 0) continue;
    const range = document.createRange(); range.selectNodeContents(n);
    const r = range.getBoundingClientRect();
    if (r.width < 4 || r.height < 4 || r.bottom < 0 || r.top > innerHeight || r.right < 0 || r.left > innerWidth) continue;
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    if (hit && !el.contains(hit) && !hit.contains(el)) continue;      // something else (a pop-up) is drawn over it
    let op = 1, p = el; while (p) { op *= parseFloat(getComputedStyle(p).opacity); p = p.parentElement; }
    out.push({cls: (el.className && el.className.baseVal === undefined ? el.className : '') + ' < ' + (el.parentElement ? el.parentElement.className : ''), text: t.slice(0, 40), color: cs.color, size: parseFloat(cs.fontSize), weight: parseInt(cs.fontWeight) || 400,
              x: r.left, y: r.top, w: r.width, h: r.height, op: op, disabled: !!el.closest('[disabled],.disabled')});
  }
  return out;
}"""


def lum(rgb):
    def f(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(a, b):
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def parse_color(s):
    m = re.match(r"rgba?\(([\d.]+)[, ]+([\d.]+)[, ]+([\d.]+)(?:[, /]+([\d.]+))?", s)
    r, g, b = (float(m.group(i)) for i in (1, 2, 3))
    return (r, g, b), float(m.group(4)) if m.group(4) else 1.0


def check(url: str, pages=PAGES, min_normal=4.5, min_large=3.0, themes=("dark", "light")):
    from PIL import Image
    from playwright.sync_api import sync_playwright
    failures = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 860})
        page.goto(url)
        page.wait_for_selector("#nav button, #nav a", state="attached")
        page.wait_for_timeout(1500)
        page.add_style_tag(content="*{animation:none!important;transition:none!important}")
        for theme in themes:
            page.evaluate(f"document.documentElement.setAttribute('data-theme','{theme}')")
            for name in pages:
                page.evaluate(f'nav("{name}")')
                page.wait_for_timeout(1200)
                items = page.evaluate(JS_ITEMS)
                page.add_style_tag(content="*{color:transparent!important;text-shadow:none!important;-webkit-text-fill-color:transparent!important} svg text{fill:transparent!important}")
                shot = Image.open(io.BytesIO(page.screenshot())).convert("RGB")
                page.evaluate("() => { for (const s of document.querySelectorAll('style')) if (s.textContent.includes('color:transparent!important')) s.remove(); }")
                for it in items:
                    if it["disabled"]:
                        continue
                    box = (max(0, int(it["x"])), max(0, int(it["y"])), min(shot.width, int(it["x"] + it["w"]) + 1), min(shot.height, int(it["y"] + it["h"]) + 1))
                    if box[2] <= box[0] or box[3] <= box[1]:
                        continue
                    crop = shot.crop(box)
                    pixels = list(crop.getdata())
                    (r, g, b), alpha = parse_color(it["color"])
                    alpha *= it["op"]
                    worst = 99.0
                    lums = sorted(pixels, key=lum)
                    lo_i, hi_i = int(len(lums) * 0.05), max(0, int(len(lums) * 0.95) - 1)     # ignore stray edge pixels
                    for bg in (lums[lo_i], lums[hi_i]):
                        fg = tuple(alpha * c + (1 - alpha) * bgc for c, bgc in zip((r, g, b), bg))
                        worst = min(worst, ratio(fg, bg))
                    large = it["size"] >= 24 or (it["size"] >= 18.66 and it["weight"] >= 700)
                    need = min_large if large else min_normal
                    if worst < need:
                        failures.append({"theme": theme, "cls": it["cls"][:50], "page": name, "text": it["text"], "ratio": round(worst, 2), "need": need, "size": it["size"]})
        browser.close()
    return failures


def main(pages=PAGES):
    base = Path(tempfile.mkdtemp())
    (base / "games" / "NES").mkdir(parents=True)
    (base / "games" / "NES" / "Alpha Quest (USA).nes").write_bytes(b"NES\x1a" + b"\0" * 64)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, "-m", "launcher", "--data-dir", str(base / "data"), "--games", str(base / "games"),
                             "--port", str(port), "--no-browser"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        line = ""
        end = time.time() + 30
        while time.time() < end and "http://" not in line:
            line = proc.stdout.readline()
        url = re.search(r"http://\S+", line).group(0)
        bad = check(url, pages=pages)
    finally:
        proc.kill()
    seen = set()
    for f in sorted(bad, key=lambda f: f["ratio"]):
        key = (f["theme"], f["page"], f["text"])
        if key in seen:
            continue
        seen.add(key)
        print(f'{f["theme"]:<5}{f["page"]:<11} {f["ratio"]:>5} (need {f["need"]})  {f["size"]:.0f}px  {f["text"]!r}  [{f["cls"]}]')
    print(f"{len(seen)} text items below the guide")
    return 1 if seen else 0


if __name__ == "__main__":
    sys.exit(main())
