#!/usr/bin/env python3
"""
Check that a redesigned preview keeps everything the live page needs to sell
and measure, before the preview is copied over the live page.

Why this exists
---------------
Sales page redesigns are built as untracked previews at
`<page>/options/new/index.html`. A redesign can quietly drop a checkout link,
a pixel call, a form endpoint or a DIME proof marker. This script compares the
preview with the live file and lists anything the preview lost.

Usage
-----
  python3 tools/preview-parity.py academy/pmm-course
  python3 tools/preview-parity.py academy/sme/consulting academy/tech-sales
  python3 tools/preview-parity.py --option b services consulting

--option NAME compares `options/NAME/index.html` instead of `options/new/`,
for pages built as several design options at once.

For each page folder it compares `index.html` (live) with
`options/new/index.html` (preview):

  ids          element ids on the live page that the preview lacks
  links        external hrefs (checkout, Selar, WhatsApp, forms) the preview lacks
  scripts      script srcs the preview lacks
  meta         meta tags (name/property + content) that differ, ignoring robots
  tracking     GTM, Google Ads, Meta and TikTok ids, and counts of dataLayer
               pushes, fbq( and ttq. calls, JSON-LD blocks, Selar links,
               Apps Script urls and data-proof markers (preview lower = flagged)
  robots       whether the preview still carries noindex (it must be stripped
               when shipping)

Exit code 1 when anything is missing, so it can gate a ship step.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def ids(s):
    return set(re.findall(r'\sid="([^"]+)"', s))


def ext_links(s):
    return set(h for h in re.findall(r'href="([^"]+)"', s) if h.startswith(("http", "mailto:", "tel:", "https://wa.me")))


def scripts(s):
    return set(re.findall(r'<script[^>]+src="([^"]+)"', s))


def metas(s):
    out = {}
    for tag in re.findall(r"<meta\s[^>]*>", s):
        k = re.search(r'(?:name|property)="([^"]+)"', tag)
        c = re.search(r'content="([^"]*)"', tag)
        if k and c and k.group(1) != "robots":
            out[k.group(1)] = c.group(1)
    return out


TRACK_IDS = [r"GTM-[A-Z0-9]+", r"AW-\d+", r"G-[A-Z0-9]{6,}", r"fbq\('init',\s*'(\d+)'", r"ttq\.load\('([A-Z0-9]+)'"]
TRACK_COUNTS = {
    "dataLayer.push": r"dataLayer\.push",
    "fbq(": r"fbq\(",
    "ttq.": r"ttq\.",
    "ld+json": r"application/ld\+json",
    "selar": r"selar\.co",
    "apps script": r"script\.google\.com/macros",
    "data-proof": r"data-proof",
}


def compare(folder, option="new"):
    live_p = ROOT / folder / "index.html"
    prev_p = ROOT / folder / "options" / option / "index.html"
    live, prev = live_p.read_text(), prev_p.read_text()
    problems = []

    for label, fn in (("ids", ids), ("links", ext_links), ("scripts", scripts)):
        missing = sorted(fn(live) - fn(prev))
        if missing:
            problems.append(f"{label} missing: {', '.join(missing)}")

    lm, pm = metas(live), metas(prev)
    for k, v in lm.items():
        if pm.get(k) != v:
            problems.append(f"meta {k} differs: live={v!r} preview={pm.get(k)!r}")

    for pat in TRACK_IDS:
        lv, pv = set(re.findall(pat, live)), set(re.findall(pat, prev))
        if lv - pv:
            problems.append(f"tracking id missing: {sorted(lv - pv)}")
    for label, pat in TRACK_COUNTS.items():
        a, b = len(re.findall(pat, live)), len(re.findall(pat, prev))
        if b < a:
            problems.append(f"{label}: live {a}, preview {b}")

    noindex = 'name="robots"' in prev and "noindex" in prev
    print(f"\n{folder}" + ("" if option == "new" else f" (option {option})"))
    for p in problems:
        print(f"  MISSING  {p}")
    if not problems:
        print("  parity ok")
    print(f"  preview noindex: {'yes (strip before shipping)' if noindex else 'no'}")
    return not problems


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    args, option = sys.argv[1:], "new"
    if args[0] == "--option":
        option, args = args[1], args[2:]
    ok = all([compare(f.rstrip("/"), option) for f in args])
    sys.exit(0 if ok else 1)
