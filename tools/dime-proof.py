#!/usr/bin/env python3
"""Keep the DIME proof numbers and screenshots in step across every DIME page.

Why this exists
---------------
James's Selar numbers (sales count, naira volume, currencies, milestones) appear
on seven DIME pages, in headlines, captions and image alt text, and the same
screenshots sit behind them. Each milestone used to mean hunting the old figure
page by page, and a missed copy left two different totals live on the site.
``data/dime-proof.json`` is now the single source: change a value there, run
``--write``, and every marked spot updates at once.

How pages carry the numbers
---------------------------
* Text: ``<span data-proof="selar_ngn">&#8358;12,886,850</span>``. The span's
  content is rewritten from ``values``.
* Alt text: ``data-proof-alt="Selar dashboard: {selar_sales} sales"``. The
  ``alt`` attribute on the same tag is rebuilt from that template.
* Screenshots: ``data-proof-img`` on an ``<img>``. Its ``?v=`` is set to a
  short hash of the image file, so browsers fetch the new file the moment it
  changes and never before.

Modes
-----
``python3 tools/dime-proof.py``          check only (the build and pre-push run this)
``python3 tools/dime-proof.py --write``  copy fresh screenshots in from
                                          ``source_dir`` and rewrite every marker

The check fails when a marker disagrees with the data file, when a screenshot's
``?v=`` is stale, when a proof value appears on a listed page outside a marker
(so the next update would miss it), or when a retired figure is still live.
"""
import hashlib
import html
import json
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "dime-proof.json"

SPAN = re.compile(r'(<span\b[^>]*\bdata-proof="([a-z0-9_]+)"[^>]*>)(.*?)(</span>)', re.S)
TAG = re.compile(r"<(?:img|[a-z]+)\b[^>]*\bdata-proof-(?:alt|img)\b[^>]*>", re.S)
ALT_TPL = re.compile(r'\bdata-proof-alt="([^"]*)"')
ALT = re.compile(r'((?<![\w-])alt=")([^"]*)(")')
SRC = re.compile(r'(\bsrc=")([^"?]+)(?:\?v=[^"]*)?(")')


def load():
    return json.loads(DATA.read_text())


def file_hash(path):
    return hashlib.sha1(path.read_bytes()).hexdigest()[:8]


def render_alt(tpl, values):
    return re.sub(r"\{([a-z0-9_]+)\}", lambda m: values[m.group(1)], tpl)


def visible_text(text):
    """Page text a visitor reads, with proof markers removed."""
    text = SPAN.sub(" ", text)
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(text)


def bounded(needle):
    """Match a figure only where it is not part of a longer number."""
    return re.compile(r"(?<![\d.,])" + re.escape(needle) + r"(?![\d])")


def process(page, data, write):
    values = data["values"]
    text = page.read_text()
    problems = []

    def fix_span(m):
        key, current = m.group(2), m.group(3)
        if key not in values:
            problems.append(f'unknown key data-proof="{key}"')
            return m.group(0)
        if current != values[key]:
            problems.append(f'{key} shows "{current}", data file says "{values[key]}"')
            # Retire the old figure so an unmarked copy of it fails the check.
            # Short counts are too common to retire safely.
            if write and len(html.unescape(current)) >= 5 and current not in data["retired"]:
                data["retired"].append(current)
        return m.group(1) + values[key] + m.group(4)

    def fix_tag(m):
        tag = m.group(0)
        tpl = ALT_TPL.search(tag)
        if tpl:
            try:
                want = render_alt(tpl.group(1), values)
            except KeyError as e:
                problems.append(f"unknown key {e} in data-proof-alt")
                want = None
            if want is not None:
                have = ALT.search(tag)
                if not have or have.group(2) != want:
                    problems.append(f'alt is "{have.group(2) if have else ""}", should be "{want}"')
                    tag = ALT.sub(lambda a: a.group(1) + want + a.group(3), tag) if have else tag.replace(
                        "data-proof-alt=", f'alt="{want}" data-proof-alt=', 1)
        if "data-proof-img" in tag:
            src = SRC.search(tag)
            asset = ROOT / src.group(2).lstrip("/") if src else None
            if not asset or not asset.exists():
                problems.append(f"screenshot missing: {src.group(2) if src else '(no src)'}")
            else:
                want_src = f"{src.group(2)}?v={file_hash(asset)}"
                if f'src="{want_src}"' not in tag:
                    problems.append(f"stale cache-buster on {src.group(2)}")
                    tag = SRC.sub(lambda s: s.group(1) + want_src + s.group(3), tag)
        return tag

    new = SPAN.sub(fix_span, text)
    new = TAG.sub(fix_tag, new)

    readable = visible_text(new)
    for key, value in values.items():
        plain = html.unescape(value)
        if key in data.get("unscanned_keys", []):
            # Short counts like "831" collide with other numbers, so only
            # their sentence forms are scanned. Words like "May" are skipped.
            if not plain.isdigit():
                continue
            needles = [f"{plain} sales", f"{plain} times"]
        else:
            needles = [plain]
        for needle in needles:
            if bounded(needle).search(readable):
                problems.append(f'"{needle}" ({key}) appears outside a data-proof marker; wrap it')
    page_text = html.unescape(re.sub(r"<!--.*?-->", " ", new, flags=re.S))
    for old in data.get("retired", []):
        if bounded(html.unescape(old)).search(page_text):
            problems.append(f'retired figure "{old}" is still on the page')

    if write and new != text:
        page.write_text(new)
    return problems


def copy_screenshots(data):
    src_dir = pathlib.Path(data["source_dir"]).expanduser()
    if not src_dir.exists():
        print(f"Source folder not found, screenshots left as they are: {src_dir}")
        return
    for target, source in data["screenshots"].items():
        src, dst = src_dir / source, ROOT / target
        if not src.exists():
            print(f"Missing source screenshot: {src}")
            continue
        if not dst.exists() or file_hash(src) != file_hash(dst):
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            print(f"Copied {source} -> {target}")


def main():
    write = "--write" in sys.argv
    data = load()
    if write:
        copy_screenshots(data)
    failures = []
    for rel in data["pages"]:
        page = ROOT / rel
        if not page.exists():
            failures.append(f"{rel}: listed in data/dime-proof.json but missing")
            continue
        for p in process(page, data, write):
            failures.append(f"{rel}: {p}")
    if write:
        DATA.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        # Re-run as a check so only problems --write cannot fix are reported.
        failures = []
        for rel in data["pages"]:
            for p in process(ROOT / rel, data, False):
                failures.append(f"{rel}: {p}")
    if failures:
        print("DIME proof check failed:\n" + "\n".join(failures))
        if not write:
            print("Run python3 tools/dime-proof.py --write after editing data/dime-proof.json.")
        return 1
    print(f"DIME proof check passed ({len(data['pages'])} pages, figures as of {data['as_of']}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
