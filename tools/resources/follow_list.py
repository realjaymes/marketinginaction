#!/usr/bin/env python3
"""Write James's follow list for the Marketing Thought Leaders database.

One row per person in data/resources/thought-leaders.json, with their X,
LinkedIn and Newsletter/other links, each next to a follow status cell James
fills in by hand: blank (not yet followed), "followed", or "none" when the
platform does not apply to that person. The script only writes the links and
never touches a social account.

The note is regenerated from the data every run, so it cannot drift. James's
status cells are read back from the existing table first and kept, matched by
person name and platform. A status for a platform the person has no link on
becomes "none"; a "none" for a platform that now has a link goes back to blank.
People who leave the data keep no row.

Usage:
  python3 tools/resources/follow_list.py [--out NOTE.md] [--check]
  --check exits 1 when the note on disk differs from what would be written.
The default note is Areas/Work/MIA/Resources/Thought Leaders — Follow List.md in the vault.

Vault: AI Workflows/MIA Resources from Notion — Build Plan.
"""
import argparse, json, pathlib, re, sys
from datetime import date
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = ROOT / "data/resources/thought-leaders.json"
NOTE = pathlib.Path.home() / "Documents/James Obsidian Vault/Areas/Work/MIA/Resources/Thought Leaders — Follow List.md"
HEAD = "| Name | X | X status | LinkedIn | LinkedIn status | Newsletter / other | Newsletter / other status |"


def label(url, kind):
    u = urlparse(url)
    path = u.path.strip("/")
    if kind == "x":
        return "@" + path.split("/")[0]
    if kind == "linkedin":
        return path.split("/")[-1] or "LinkedIn"
    return (u.netloc.replace("www.", "") + ("/" + path if path else ""))[:40]


def cell(url, kind):
    return f"[{label(url, kind)}]({url})" if url else "none"


def other(i):
    """Newsletter first, then website when it is a different page."""
    links = [i.get("newsletter") or ""]
    w = i.get("website") or ""
    if w and w.rstrip("/") != links[0].rstrip("/"):
        links.append(w)
    return [l for l in links if l]


def old_status(text):
    """name -> [x, linkedin, other] status cells from the existing table."""
    out = {}
    for l in text.splitlines():
        c = [x.strip() for x in l.strip().strip("|").split("|")]
        if l.strip().startswith("|") and len(c) == 7 and c[0] not in ("Name", "---") and not set(c[0]) <= set("-: "):
            out[c[0]] = [c[2], c[4], c[6]]
    return out


def render(items, prev, today):
    rows = []
    for i in sorted(items, key=lambda p: p["name"].lower()):
        old = prev.get(i["name"], ["", "", ""])
        have = [bool(i.get("x")), bool(i.get("linkedin")), bool(other(i))]
        st = [(o if o.lower() != "none" else "") if h else "none" for o, h in zip(old, have)]
        oth = " · ".join(cell(l, "other") for l in other(i)) or "none"
        rows.append(f"| {i['name']} | {cell(i.get('x'), 'x')} | {st[0]} | {cell(i.get('linkedin'), 'linkedin')} | {st[1]} | {oth} | {st[2]} |")
    return f"""---
type: resource-follow-list
project: MIA Website
page: https://marketinginaction.xyz/resources/marketing-thought-leaders/
last_touch_date: {today}
tags: [mia, resources, thought-leaders, follow]
---

# Thought Leaders: Follow List

Every person in the Marketing Thought Leaders database, with their links, so James can follow them on each platform. `tools/resources/follow_list.py` regenerates this table from `data/resources/thought-leaders.json`, and the 17:00 resources intake runs it, so a new person appears here the day they are added. Do not edit names or links here, because the next run rewrites them.

Set a status cell to `followed` once you follow them there. Leave it blank until then. A cell reads `none` when the person has no account on that platform, and the script sets that itself. Your status cells are kept on every run. Nothing here follows anyone for you. How it works: [[MIA Resources from Notion — Build Plan]].

{HEAD}
|---|---|---|---|---|---|---|
""" + "\n".join(rows) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=pathlib.Path, default=NOTE)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    items = json.loads(DATA.read_text(encoding="utf-8"))["items"]
    prev = old_status(a.out.read_text(encoding="utf-8")) if a.out.exists() else {}
    text = render(items, prev, date.today().isoformat())
    if a.out.exists():
        same = re.sub(r"last_touch_date: .*", "", a.out.read_text(encoding="utf-8")) == re.sub(r"last_touch_date: .*", "", text)
        if same:
            print(f"{a.out.name}: {len(items)} rows, unchanged")
            return 0
    if a.check:
        print("follow list is out of date")
        return 1
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(text, encoding="utf-8")
    print(f"{a.out.name}: {len(items)} rows written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
