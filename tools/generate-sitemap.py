#!/usr/bin/env python3
"""Generate a static site's sitemap.xml from the pages actually on disk.

Why this exists
---------------
Both jamespraise.xyz and marketinginaction.xyz deploy to GitHub Pages with no
build step: the Actions workflow uploads the repo as-is. Nothing regenerates the
sitemap, so every hand-edited sitemap silently drifts the moment a page ships.
This script makes the sitemap a derived artifact instead of a file you remember
to update.

What it does
------------
Walks the repo for ``index.html`` files, converts each to a clean URL, drops any
page that is excluded from search (a ``<meta name="robots" ...noindex>`` tag, or
a matching ``Disallow:`` rule in robots.txt), and writes a sorted sitemap.

It matches whichever optional fields the existing sitemap already uses, so
regenerating does not restyle a site. If the current file carries
``<changefreq>`` and ``<priority>``, the regenerated one does too, reusing each
URL's hand-tuned value so curation survives; new URLs get depth-based defaults.
If the current file has no optional fields at all, the output still gains
``<lastmod>``, which is the one optional field Google actually reads.

``<lastmod>`` comes from the file's last git commit date, falling back to
filesystem mtime for uncommitted files.

Usage
-----
    # Rewrite the sitemap in place
    python3 tools/generate-sitemap.py --base-url https://marketinginaction.xyz/ \
        --output sitemap-main.xml

    # Exit non-zero if the sitemap is out of date, changing nothing (for CI)
    python3 tools/generate-sitemap.py --base-url https://marketinginaction.xyz/ \
        --output sitemap-main.xml --check

This file is kept byte-identical in ~/Documents/mia-website-directory/tools/ and
~/Documents/james-website/tools/. All site-specific values are CLI flags, so the
two copies never need to diverge. Copy, do not fork.
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# Directories never worth walking for pages.
SKIP_DIRS = {".git", ".github", "node_modules", "assets", ".claude", "attachments"}

ROBOTS_META_RE = re.compile(
    r"""<meta\s+[^>]*name\s*=\s*["']robots["'][^>]*>""", re.IGNORECASE
)
CONTENT_RE = re.compile(r"""content\s*=\s*["']([^"']*)["']""", re.IGNORECASE)
LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.IGNORECASE)
URL_BLOCK_RE = re.compile(r"<url>(.*?)</url>", re.IGNORECASE | re.DOTALL)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument(
        "--base-url",
        required=True,
        help="Site root, e.g. https://marketinginaction.xyz/",
    )
    p.add_argument(
        "--output",
        default="sitemap.xml",
        help="Sitemap path relative to --root (default: sitemap.xml)",
    )
    p.add_argument(
        "--root",
        default=".",
        help="Repo root to walk (default: current directory)",
    )
    p.add_argument(
        "--check",
        action="store_true",
        help="Do not write. Exit 1 if the sitemap on disk is out of date.",
    )
    p.add_argument(
        "--quiet", action="store_true", help="Only report errors and the summary line"
    )
    return p.parse_args(argv)


def load_robots_disallows(root: Path) -> list[str]:
    """Return Disallow path patterns from robots.txt for the catch-all agent."""
    robots = root / "robots.txt"
    if not robots.is_file():
        return []
    disallows: list[str] = []
    applies = False
    for raw in robots.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            applies = value == "*"
        elif key == "disallow" and applies and value:
            disallows.append(value)
    return disallows


def is_disallowed(url_path: str, patterns: list[str]) -> bool:
    """True if url_path is blocked by a robots.txt Disallow rule.

    Handles both prefix rules (``/blog/``) and wildcard rules (``/work/*/proof/``).
    """
    for pattern in patterns:
        if "*" in pattern or "$" in pattern:
            if fnmatch.fnmatch(url_path, pattern.rstrip("$") + "*"):
                return True
        elif url_path.startswith(pattern):
            return True
    return False


def is_noindex(html: str) -> bool:
    """True if the page carries a robots meta tag containing 'noindex'."""
    for tag in ROBOTS_META_RE.findall(html):
        content = CONTENT_RE.search(tag)
        if content and "noindex" in content.group(1).lower():
            return True
    return False


def git_lastmod(path: Path, root: Path) -> str | None:
    """Last commit date for a file as YYYY-MM-DD, or None if never committed."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--", str(path.relative_to(root))],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    stamp = out.stdout.strip()
    return stamp if out.returncode == 0 and stamp else None


def mtime_lastmod(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).date().isoformat()


def default_priority(url_path: str) -> str:
    """Depth-based default: the root scores highest, deeper pages score lower."""
    depth = len([seg for seg in url_path.strip("/").split("/") if seg])
    return {0: "1.0", 1: "0.9", 2: "0.8"}.get(depth, "0.7")


def discover_pages(root: Path, disallows: list[str], quiet: bool) -> list[str]:
    """Return sorted, indexable URL paths (each beginning and ending with '/')."""
    paths: list[str] = []
    skipped_noindex = 0
    skipped_robots = 0

    for html_file in root.rglob("index.html"):
        rel = html_file.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue

        url_path = "/" + str(rel.parent).replace("\\", "/").strip(".").strip("/")
        if not url_path.endswith("/"):
            url_path += "/"
        url_path = re.sub(r"/{2,}", "/", url_path)

        if is_disallowed(url_path, disallows):
            skipped_robots += 1
            continue

        try:
            html = html_file.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"  warning: could not read {rel}: {exc}", file=sys.stderr)
            continue

        if is_noindex(html):
            skipped_noindex += 1
            continue

        paths.append(url_path)

    if not quiet:
        print(
            f"  found {len(paths)} indexable pages "
            f"({skipped_noindex} noindex, {skipped_robots} robots.txt-blocked)"
        )
    return sorted(set(paths))


def read_existing(sitemap: Path) -> tuple[dict[str, dict[str, str]], set[str]]:
    """Return per-URL existing field values, and which optional fields are in use."""
    if not sitemap.is_file():
        return {}, {"lastmod"}

    text = sitemap.read_text(encoding="utf-8", errors="replace")
    existing: dict[str, dict[str, str]] = {}
    fields_used: set[str] = set()

    for block in URL_BLOCK_RE.findall(text):
        loc = LOC_RE.search(block)
        if not loc:
            continue
        entry: dict[str, str] = {}
        for field in ("lastmod", "changefreq", "priority"):
            match = re.search(rf"<{field}>\s*([^<]+?)\s*</{field}>", block, re.I)
            if match:
                entry[field] = match.group(1).strip()
                fields_used.add(field)
        existing[loc.group(1).strip()] = entry

    if not fields_used:
        fields_used = {"lastmod"}
    return existing, fields_used


def build_sitemap(
    paths: list[str],
    base_url: str,
    root: Path,
    existing: dict[str, dict[str, str]],
    fields: set[str],
) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    today = date.today().isoformat()

    for url_path in paths:
        url = base_url.rstrip("/") + url_path
        prior = existing.get(url, {})
        lines.append("  <url>")
        lines.append(f"    <loc>{url}</loc>")

        if "lastmod" in fields:
            page = root / url_path.strip("/") / "index.html"
            stamp = git_lastmod(page, root) or (
                mtime_lastmod(page) if page.is_file() else today
            )
            lines.append(f"    <lastmod>{stamp}</lastmod>")

        if "changefreq" in fields:
            lines.append(
                f"    <changefreq>{prior.get('changefreq', 'monthly')}</changefreq>"
            )

        if "priority" in fields:
            value = prior.get("priority", default_priority(url_path))
            lines.append(f"    <priority>{value}</priority>")

        lines.append("  </url>")

    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve()
    sitemap = root / args.output

    if not args.quiet:
        print(f"Scanning {root}")

    disallows = load_robots_disallows(root)
    paths = discover_pages(root, disallows, args.quiet)
    if not paths:
        print("error: no indexable pages found, refusing to write", file=sys.stderr)
        return 2

    existing, fields = read_existing(sitemap)
    rendered = build_sitemap(paths, args.base_url, root, existing, fields)

    current = (
        sitemap.read_text(encoding="utf-8", errors="replace")
        if sitemap.is_file()
        else ""
    )
    if current == rendered:
        print(f"{args.output} is up to date ({len(paths)} URLs)")
        return 0

    if args.check:
        on_disk = set(LOC_RE.findall(current))
        expected = set(LOC_RE.findall(rendered))
        for url in sorted(expected - on_disk):
            print(f"  + {url}")
        for url in sorted(on_disk - expected):
            print(f"  - {url}")
        print(
            f"error: {args.output} is out of date. Run without --check.",
            file=sys.stderr,
        )
        return 1

    sitemap.write_text(rendered, encoding="utf-8")
    print(f"wrote {args.output} ({len(paths)} URLs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
