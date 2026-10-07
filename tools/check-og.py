#!/usr/bin/env python3
"""Fail the deploy when a page's Open Graph or Twitter tags are incomplete.

Why this exists
---------------
Pages are cloned by hand, and social tags were the part that drifted: 63 pages
shipped none and 40 pointed at a 512x512 square image. ``tools/og-tags.py``
writes the block; this makes sure every page still has it.

What it checks, on every ``.html`` page
---------------------------------------
1. Every tag in ``REQUIRED`` is present and non-empty.
2. ``og:image`` and ``twitter:image`` are absolute URLs on this site, the file
   exists in the repo, and it is 1200x630.
3. ``og:url`` equals the canonical URL when the page declares one.

Fix a failure with ``python3 tools/og-tags.py``, then commit.
"""
import importlib.util
import pathlib
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = "https://marketinginaction.xyz/"

spec = importlib.util.spec_from_file_location("og_tags", ROOT / "tools" / "og-tags.py")
og_tags = importlib.util.module_from_spec(spec)
spec.loader.exec_module(og_tags)

REQUIRED = [
    "og:type", "og:title", "og:description", "og:url", "og:image", "og:image:width",
    "og:image:height", "og:image:alt", "og:site_name", "twitter:card", "twitter:site",
    "twitter:title", "twitter:description", "twitter:image", "twitter:image:alt",
]


def png_size(path: pathlib.Path):
    head = path.read_bytes()[:24]
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", head[16:24])


def main() -> int:
    failures = []
    for page in sorted(ROOT.rglob("*.html")):
        if ".git" in page.parts or "node_modules" in page.parts:
            continue
        name = page.relative_to(ROOT).as_posix()
        h = og_tags.parse(page)
        for key in REQUIRED:
            if not h.meta.get(key):
                failures.append(f"{name}: missing {key}")
        for key in ("og:image", "twitter:image"):
            url = h.meta.get(key) or ""
            if not url:
                continue
            if not url.startswith(BASE):
                failures.append(f"{name}: {key} is not on {BASE}: {url}")
                continue
            img = ROOT / url[len(BASE):]
            if not img.exists():
                failures.append(f"{name}: {key} file does not exist: {img.relative_to(ROOT)}")
            elif png_size(img) != (1200, 630):
                failures.append(f"{name}: {key} is {png_size(img)}, needs 1200x630")
        if h.canonical and h.meta.get("og:url") and h.meta["og:url"] != h.canonical:
            failures.append(f"{name}: og:url {h.meta['og:url']} != canonical {h.canonical}")
    if failures:
        print("Open Graph check failed:\n" + "\n".join(failures))
        print("Fix with: python3 tools/og-tags.py")
        return 1
    print("Open Graph check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
