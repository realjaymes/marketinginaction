#!/usr/bin/env python3
"""Analytics check for every public MIA page. Runs in tools/cf-build.sh and .githooks/pre-push.

Fails when a page is missing Google Tag Manager GTM-KRT2BT27 in <head> or its noscript iframe
after <body>, the Google Ads tag AW-17909542714 or the Meta Pixel 660940561182168 (the
mia-landing-page skill's standard <head> wiring), or loads GA4 directly with a gtag.js G- snippet
(GA4 G-4HYQTZEZ52 loads through GTM, so a direct snippet counts every visit twice).

Skipped: design option pages (any /options/ folder), the Acquisition example pages
(acquisition/*/example/, demo sites for prospects under made-up brands) and _lab/.
"""
import pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GTM, ADS, PIXEL = "GTM-KRT2BT27", "AW-17909542714", "660940561182168"


def skipped(rel: str) -> bool:
    parts = rel.split("/")
    return (parts[0] in {".git", "node_modules", "_lab"} or "options" in parts[:-1]
            or (parts[0] == "acquisition" and "example" in parts[:-1]))


fails, n = [], 0
for p in sorted(ROOT.rglob("*.html")):
    rel = p.relative_to(ROOT).as_posix()
    if skipped(rel):
        continue
    s = p.read_text(encoding="utf8", errors="ignore")
    if 'http-equiv="refresh"' in s:
        continue  # redirect stubs carry no tags
    n += 1
    head = s.split("</head>", 1)[0]
    body = re.search(r"<body[^>]*>", s)
    if "googletagmanager.com/gtm.js" not in head or GTM not in head:
        fails.append(f"{rel}: GTM {GTM} missing from <head>")
    if not body or f"ns.html?id={GTM}" not in s[body.end(): body.end() + 600]:
        fails.append(f"{rel}: GTM noscript iframe missing right after <body>")
    if re.search(r"gtag/js\?id=G-", s):
        fails.append(f"{rel}: loads GA4 with a gtag.js G- snippet; GA4 comes through GTM only")
    if ADS not in head:
        fails.append(f"{rel}: Google Ads tag {ADS} missing from <head>")
    if PIXEL not in head:
        fails.append(f"{rel}: Meta Pixel {PIXEL} missing from <head>")

for f in fails:
    print("FAIL", f)
if fails:
    print(f"check-analytics: {len(fails)} problem(s). Copy the <head> and <body> wiring from a live page "
          "(see the mia-landing-page skill).", file=sys.stderr)
    sys.exit(1)
print(f"check-analytics: GTM, Google Ads and Meta Pixel wiring correct on all {n} pages")
