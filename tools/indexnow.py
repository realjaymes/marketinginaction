#!/usr/bin/env python3
"""
indexnow.py

Tells Bing (and the other IndexNow engines: Yandex, Seznam, Naver, Yep) which
pages changed, right after a deploy, so they recrawl them within hours instead
of waiting for their own schedule. ChatGPT search leans on Bing's index, so a
page Bing has not crawled is a page ChatGPT cannot cite.

How it picks URLs:
  * It reads the site's own sitemap.xml (following a sitemap index to the local
    child sitemaps on the same host). Only sitemap URLs are ever submitted, so
    noindex pages, /go/ bridges and private pitch pages stay out by the same
    rule that keeps them out of the sitemap.
  * With --before and --after (the push range), it submits only the sitemap
    URLs whose source file changed: /x/ maps to x/index.html, /x maps to x.html
    or x/index.html.
  * With no --before, an all-zero --before (first push), or --all, it submits
    every sitemap URL. Run it that way once by hand, or from the Actions tab
    with "Run workflow", to seed a site.

The key is the 32-character hex file at the repo root, <key>.txt, whose content
is the key itself. IndexNow fetches that file from the live site to prove the
ping came from the site owner, so it must be deployed before the first ping.

A failed ping never fails the deploy: the workflow step uses continue-on-error.

Usage:
    python3 tools/indexnow.py --base-url https://jamespraise.xyz/ \
        [--before SHA --after SHA | --all] [--dry-run]
"""
import argparse
import html
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ENDPOINT = "https://api.indexnow.org/indexnow"
ROOT = Path(__file__).resolve().parent.parent


def find_key() -> str:
    for f in ROOT.glob("*.txt"):
        if re.fullmatch(r"[0-9a-f]{32}", f.stem) and f.read_text().strip() == f.stem:
            return f.stem
    sys.exit("No IndexNow key file (<32 hex chars>.txt containing the key) at the repo root.")


def sitemap_urls(host: str) -> list[str]:
    # Plain text matching, not an XML parser: sitemaps are flat, and some local
    # Python builds ship a broken expat that would stop the script.
    urls, queue, seen = [], [ROOT / "sitemap.xml"], set()
    while queue:
        path = queue.pop()
        if path in seen or not path.exists():
            continue
        seen.add(path)
        text = path.read_text(encoding="utf-8")
        locs = [html.unescape(m.strip()) for m in re.findall(r"<loc>(.*?)</loc>", text, re.S)]
        if "<sitemapindex" in text:
            for loc in locs:
                u = urlparse(loc)
                if u.netloc == host:
                    queue.append(ROOT / u.path.lstrip("/"))
        else:
            urls += locs
    return urls


def source_files(url: str) -> set[str]:
    p = urlparse(url).path.strip("/")
    if not p:
        return {"index.html"}
    return {f"{p}/index.html", f"{p}.html"}


def changed_files(before: str, after: str) -> set[str] | None:
    """Files changed in the push, or None when git cannot compare the range."""
    out = subprocess.run(["git", "diff", "--name-only", before, after],
                         cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0:
        print(f"git diff failed ({out.stderr.strip()}); submitting the whole sitemap.")
        return None
    return set(out.stdout.splitlines())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--before", default="")
    ap.add_argument("--after", default="HEAD")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    host = urlparse(args.base_url).netloc
    key = find_key()
    every = sitemap_urls(host)

    changed = None if args.all or not args.before.strip("0") else changed_files(args.before, args.after)
    urls = every if changed is None else [u for u in every if source_files(u) & changed]

    if not urls:
        print("No sitemap pages changed in this push. Nothing to submit.")
        return 0

    payload = {"host": host, "key": key,
               "keyLocation": f"https://{host}/{key}.txt", "urlList": urls[:10000]}
    print(f"Submitting {len(payload['urlList'])} URL(s) for {host}:")
    for u in payload["urlList"][:50]:
        print("  " + u)
    if len(urls) > 50:
        print(f"  ... and {len(urls) - 50} more")
    if args.dry_run:
        print("DRY RUN. Nothing sent.")
        return 0

    req = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"IndexNow accepted: HTTP {r.status}")
            return 0
    except urllib.error.HTTPError as e:
        # 403 = key file not reachable or wrong; 422 = URLs not on this host.
        print(f"IndexNow rejected: HTTP {e.code} {e.read().decode(errors='replace')[:300]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
