#!/usr/bin/env python3
"""Render a 1200x630 Open Graph image in the October 2026 MIA look.

Layout: pale-gold ground with an ink bottom rule, a bordered pill, a large
Satoshi headline on the left with the last phrase underlined in the section
colour, and a bordered, hard-shadow block on the right holding the real logo
(``assets/mia-logo.svg``) and the domain. The block takes the section colour.

Satoshi comes from Fontshare. The script downloads the four weights once into
``~/.cache/mia-og-fonts`` and embeds them in the page as data URIs, so the
screenshot never races a network font load and never falls back to Arial.
It renders through headless Chrome.

Usage, one image::

    python3 tools/og-image.py --out assets/og-acquisition.png \\
        --pill "MIA ACQUISITION" --accent-color "#f171c4" \\
        --headline "Get more customers," --accent "predictably." \\
        --sub "Lead generation and paid acquisition systems," \\
        --sub "built and run for you."

``--headline`` and ``--sub`` repeat, one per line. ``--accent-color`` is the
section colour (blue #71c4f1, purple #7184f1, pink #f171c4, green #71f19e,
default yellow #f1de71).

Usage, all seven site images into ``assets/`` (copy lives in ``IMAGES``)::

    python3 tools/og-image.py --all

After re-rendering, bump ``VERSION`` in ``tools/og-tags.py`` and run it, so
social platforms fetch the new files.
"""
import argparse
import base64
import html
import pathlib
import re
import subprocess
import sys
import tempfile
import urllib.request

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
ROOT = pathlib.Path(__file__).resolve().parent.parent
FONT_CSS = "https://api.fontshare.com/v2/css?f[]=satoshi@400,500,700,900&display=swap"
CACHE = pathlib.Path.home() / ".cache" / "mia-og-fonts"

INK, LILAC, GOLD, GOLD_T = "#100a16", "#F7F4FA", "#f1de71", "#FBF3C6"
BLUE, PURPLE, PINK, GREEN = "#71c4f1", "#7184f1", "#f171c4", "#71f19e"

# name: (pill, headline lines, accent phrase, sub lines, section colour)
IMAGES = {
    "og-homepage": ("MARKETING IN ACTION", ["Put marketing", "into action,"], "unlock revenue.",
                    ["Academy programs, done-for-you services, free playbooks & tools"], GOLD),
    "og-academy": ("MIA ACADEMY", ["Marketing"], "Simplified.",
                   ["Courses, bootcamps & hands-on programs", "for marketers and business owners."], PURPLE),
    "og-sme": ("MIA ACADEMY · FOR BUSINESS OWNERS", ["Online Marketing"], "Simplified.",
               ["Workshops, templates & done-for-you services", "for Nigerian SME business owners."], GREEN),
    "og-dime": ("MIA ACADEMY · DIME", ["Digital Income"], "Made Easy.",
                ["Make your first ₦500,000 online with AI."], PINK),
    "og-consulting": ("MIA GTM", ["Go-To-Market"], "Systems.",
                      ["Positioning, GTM infrastructure, outbound and paid systems", "for tech companies and agencies."], BLUE),
    "og-acquisition": ("MIA ACQUISITION", ["Get more customers,"], "predictably.",
                       ["Lead generation and paid acquisition systems,", "built and run for you."], PINK),
    "og-pro-bootcamp": ("MIA ACADEMY · BOOTCAMP", ["Product & Growth"], "Marketing with AI",
                        ["12-week execution-first bootcamp."], PURPLE),
}


def font_css() -> str:
    """Satoshi @font-face rules with the woff2 files embedded as data URIs."""
    CACHE.mkdir(parents=True, exist_ok=True)
    css_file = CACHE / "satoshi.css"
    if not css_file.exists():
        req = urllib.request.Request(FONT_CSS, headers={"User-Agent": "Mozilla/5.0 Chrome/120"})
        css_file.write_text(urllib.request.urlopen(req, timeout=30).read().decode())
    out = []
    for block in re.findall(r"@font-face\s*{[^}]*}", css_file.read_text()):
        url = re.search(r"url\('(//[^']+\.woff2)'\)", block).group(1)
        weight = re.search(r"font-weight:\s*(\d+)", block).group(1)
        f = CACHE / (url.rsplit("/", 1)[1])
        if not f.exists():
            f.write_bytes(urllib.request.urlopen("https:" + url, timeout=30).read())
        b64 = base64.b64encode(f.read_bytes()).decode()
        out.append("@font-face{font-family:'Satoshi';font-weight:%s;src:url(data:font/woff2;base64,%s) format('woff2')}" % (weight, b64))
    return "\n".join(out)


def logo_uri() -> str:
    return "data:image/svg+xml;base64," + base64.b64encode((ROOT / "assets" / "mia-logo.svg").read_bytes()).decode()


BASE = """html,body{margin:0;width:1200px;height:630px;overflow:hidden}
*{box-sizing:border-box}
body{font-family:'Satoshi',sans-serif;position:relative;color:#100a16;-webkit-font-smoothing:antialiased}
h1{margin:0;font-weight:900;letter-spacing:-.025em;line-height:1.06}
p{margin:0}
.dot{display:inline-block;width:11px;height:11px;border-radius:50%;border:2px solid #100a16;margin-right:10px;vertical-align:-1px}
"""

CSS = """body{background:#FBF3C6}
.rule{position:absolute;left:0;right:0;bottom:0;height:12px;background:#100a16}
.pill{position:absolute;left:64px;top:52px;background:#fff;border:2px solid #100a16;border-radius:999px;
  padding:7px 18px;font-weight:800;font-size:17px;line-height:1.3}
.copy{position:absolute;left:64px;top:132px;width:780px}
h1{font-size:68px}
h1 .y{color:#100a16;text-decoration:underline;text-decoration-thickness:9px;text-underline-offset:7px;text-decoration-color:var(--c);text-decoration-skip-ink:none}
p{margin-top:24px;font-size:24px;line-height:1.34;font-weight:500;color:rgba(16,10,22,.78)}
.block{position:absolute;right:56px;top:68px;width:290px;height:452px;background:var(--c);border:4px solid #100a16;
  border-radius:26px;box-shadow:10px 10px 0 #100a16}
.block img{position:absolute;left:50%;top:50%;width:176px;height:176px;margin:-100px 0 0 -88px;border:4px solid #100a16;border-radius:30px}
.block span{position:absolute;left:0;right:0;bottom:30px;text-align:center;font-weight:800;font-size:19px}
.foot{display:none}"""

BODY = """<div class="pill"><span class="dot" style="background:{c}"></span>{pill}</div>
<div class="copy"><h1>{headline}<br><span class="y">{accent}</span></h1><p>{sub}</p></div>
<div class="block"><img src="{logo}"><span>marketinginaction.xyz</span></div><div class="rule"></div>"""


def render(out, pill, headline, accent, sub, color):
    page = "<!doctype html><html><head><meta charset='utf-8'><style>%s\n%s\n%s\n:root{--c:%s}</style></head><body>%s</body></html>" % (
        font_css(), BASE, CSS, color,
        BODY.format(
            logo=logo_uri(), c=color, pill=html.escape(pill),
            headline="<br>".join(html.escape(h) for h in headline), accent=html.escape(accent),
            sub="<br>".join(html.escape(s) for s in sub)))
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(page)
    pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([CHROME, "--headless=new", "--hide-scrollbars", "--force-device-scale-factor=1",
                    "--virtual-time-budget=3000", "--window-size=1200,630",
                    f"--screenshot={pathlib.Path(out).resolve()}", f"file://{f.name}"],
                   check=True, capture_output=True)
    print(f"wrote {out}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", nargs="?", const=str(ROOT / "assets"), metavar="DIR", help="render all seven site images (default DIR: assets/)")
    ap.add_argument("--out")
    ap.add_argument("--pill")
    ap.add_argument("--headline", action="append")
    ap.add_argument("--accent")
    ap.add_argument("--sub", action="append", default=[])
    ap.add_argument("--accent-color", default=GOLD)
    a = ap.parse_args()
    if a.all:
        for name, (pill, hl, acc, sub, col) in IMAGES.items():
            render(f"{a.all}/{name}.png", pill, hl, acc, sub, col)
        return 0
    if not (a.out and a.pill and a.headline and a.accent):
        ap.error("--out, --pill, --headline and --accent are required without --all")
    render(a.out, a.pill, a.headline, a.accent, a.sub, a.accent_color)
    return 0


if __name__ == "__main__":
    sys.exit(main())
