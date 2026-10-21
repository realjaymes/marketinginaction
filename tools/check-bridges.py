#!/usr/bin/env python3
"""Fail the deploy when a page that runs paid ads has no working /go/ bridge.

Why this exists
---------------
Ads point at a minimal, trigger-free bridge page at go/[slug]/, never straight
at the funnel. Only pages that run or will run paid ads need one. Acquisition
niche pages and resource pages are exempt. The list of advertised pages is
explicit, in data/advertised-pages.json, so the exemption is a decision and not
an accident.

What it checks, for every entry in that file
--------------------------------------------
1. The advertised page exists.
2. The bridge go/[slug]/index.html exists.
3. The bridge carries a robots meta tag with noindex.
4. The bridge links to the advertised page (the click-gated CTA).
5. The bridge does not auto-redirect (no meta refresh, no location assignment).
6. Neither the bridge nor go/ appears in sitemap-main.xml.

Fix a failure by building the bridge from the mia-landing-page skill's
references/bridge-page-template.html, or by removing the page from the list if
it will not run ads.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "advertised-pages.json"


def main() -> int:
    entries = json.loads(DATA.read_text())["pages"]
    sitemap = (ROOT / "sitemap-main.xml")
    sitemap_text = sitemap.read_text() if sitemap.exists() else ""
    failures = []
    for entry in entries:
        page, bridge = entry["page"], entry["bridge"]
        if not (ROOT / page / "index.html").exists():
            failures.append(f"{page}: advertised page does not exist")
            continue
        bridge_file = ROOT / bridge / "index.html"
        if not bridge_file.exists():
            failures.append(f"{page}: advertised page has no bridge at {bridge}")
            continue
        html = bridge_file.read_text(errors="ignore")
        robots = re.search(r'<meta[^>]+name=["\']robots["\'][^>]*>', html, re.I)
        if not robots or "noindex" not in robots.group(0).lower():
            failures.append(f"{bridge}: missing robots noindex meta tag")
        if f'href="/{page}"' not in html:
            failures.append(f"{bridge}: no link to /{page}")
        if re.search(r'http-equiv=["\']refresh["\']', html, re.I) or re.search(
                r"(window\.)?location(\.href)?\s*=|location\.(replace|assign)\(", html):
            failures.append(f"{bridge}: auto-redirect found, the CTA must be click-gated")
        if "/go/" in sitemap_text:
            failures.append("sitemap-main.xml lists a /go/ URL, bridges stay out of the sitemap")
    for failure in sorted(set(failures)):
        print("check-bridges: " + failure)
    if failures:
        print(f"check-bridges: {len(set(failures))} problem(s). See tools/check-bridges.py for the rules.")
        return 1
    print(f"check-bridges: {len(entries)} advertised pages, all have a clean bridge")
    return 0


if __name__ == "__main__":
    sys.exit(main())
