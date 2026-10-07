#!/usr/bin/env python3
"""Render a 1200x630 Open Graph image in the MIA house template.

Why this exists
---------------
The first set of OG images (``assets/og-*.png``) was rendered in an ad hoc
session and the generator was never saved, so the template could not be reused
when the acquisition pages needed their own image. This is that template, kept
in the repo: dark background, yellow top rule, a green-dot pill label, a two-part
headline with the last part in yellow, one or two lines of subtitle, and the
domain in the footer bar.

It renders through headless Chrome, so the fonts match what the browser draws.

Usage::

    python3 tools/og-image.py --out assets/og-acquisition.png \\
        --pill "MIA ACQUISITION" \\
        --headline "Get more customers," --accent "predictably." \\
        --sub "Paid, creative & content systems that bring you customers," \\
        --sub "built and run for you."

``--headline`` and ``--sub`` repeat, one per line.
"""
import argparse
import html
import pathlib
import subprocess
import sys
import tempfile

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

TEMPLATE = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;width:1200px;height:630px;overflow:hidden}}
body{{background:#1c1522;font-family:Arial,Helvetica,sans-serif;position:relative}}
.rule{{position:absolute;top:0;left:0;right:0;height:7px;background:#f2dc6b}}
.pill{{position:absolute;top:72px;left:64px;background:#2a2230;border-radius:14px;
  padding:6px 14px 6px 30px;color:#fff;font-weight:700;font-size:14px;letter-spacing:.2px}}
.pill:before{{content:"";position:absolute;left:14px;top:9px;width:9px;height:9px;
  border-radius:50%;background:#2ecc71}}
.copy{{position:absolute;top:150px;left:80px;width:760px}}
h1{{margin:0;color:#fff;font-family:"Arial Black",Arial,sans-serif;font-weight:900;
  font-size:54px;line-height:1.08;letter-spacing:.5px}}
h1 .y{{color:#f2dc6b}}
p{{margin:16px 0 0;color:#fff;font-size:20px;line-height:1.35}}
.foot{{position:absolute;left:0;right:0;bottom:0;height:50px;background:#2c2236}}
.foot span{{position:absolute;left:80px;top:13px;color:#f2dc6b;font-size:14px}}
</style></head><body>
<div class="rule"></div>
<div class="pill">{pill}</div>
<div class="copy"><h1>{headline}<br><span class="y">{accent}</span></h1><p>{sub}</p></div>
<div class="foot"><span>marketinginaction.xyz</span></div>
</body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--pill", required=True)
    ap.add_argument("--headline", action="append", required=True)
    ap.add_argument("--accent", required=True)
    ap.add_argument("--sub", action="append", default=[])
    a = ap.parse_args()

    page = TEMPLATE.format(
        pill=html.escape(a.pill),
        headline="<br>".join(html.escape(h) for h in a.headline),
        accent=html.escape(a.accent),
        sub="<br>".join(html.escape(s) for s in a.sub),
    )
    out = pathlib.Path(a.out).resolve()
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(page)
    subprocess.run(
        [CHROME, "--headless=new", "--hide-scrollbars", "--force-device-scale-factor=1",
         "--window-size=1200,630", f"--screenshot={out}", f"file://{f.name}"],
        check=True, capture_output=True,
    )
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
