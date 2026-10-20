#!/usr/bin/env python3
"""Export the three public MIA Notion databases into data/resources/*.json.

One-time seed for the coded resource pages (vault: AI Workflows/MIA Resources from
Notion — Build Plan). The Notion pages are public, so Notion's own page endpoints
return every row without a login. Re-running overwrites the seed files, so run it
only before the coded pages become the source of truth.

Usage: python3 tools/resources/notion_export.py
"""
import json, pathlib, re, urllib.request
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "data/resources"
PAGES = {
    "tools": "224a6d41709c8106ba43f1731bc9c3b7",
    "thought-leaders": "207a6d41709c80e78e22e94c52270e89",
    "events": "2e2a6d41709c80dc8181cdbcb4c01096",
}
H = {"content-type": "application/json", "user-agent": "Mozilla/5.0"}


def post(endpoint, body):
    req = urllib.request.Request("https://www.notion.so/api/v3/" + endpoint, json.dumps(body).encode(), H)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def uuid(s):
    return f"{s[:8]}-{s[8:12]}-{s[12:16]}-{s[16:20]}-{s[20:]}"


def val(record):
    v = record["value"]
    return v.get("value", v)


def rows_for(page_id):
    """Every live row of the first database on the page, with the database schema."""
    pid, blocks, colls, cursor, n = uuid(page_id), {}, {}, {"stack": []}, 0
    while True:
        d = post("loadPageChunk", {"page": {"id": pid}, "limit": 100, "cursor": cursor,
                                   "chunkNumber": n, "verticalColumns": False})
        for k, v in d["recordMap"].get("block", {}).items():
            blocks[k] = val(v)
        for k, v in d["recordMap"].get("collection", {}).items():
            colls[k] = val(v)
        cursor, n = d["cursor"], n + 1
        if not cursor["stack"] or n > 10:
            break
    for b in blocks.values():
        if b.get("type") not in ("collection_view", "collection_view_page"):
            continue
        cid = b.get("collection_id") or b.get("format", {}).get("collection_pointer", {}).get("id")
        if cid not in colls or not b.get("view_ids"):
            continue
        r = post("queryCollection", {
            "collection": {"id": cid, "spaceId": b["space_id"]},
            "collectionView": {"id": b["view_ids"][0], "spaceId": b["space_id"]},
            "loader": {"type": "reducer", "reducers": {"collection_group_results": {"type": "results", "limit": 1000}},
                       "searchQuery": "", "userTimeZone": "UTC"}})
        schema = val(r["recordMap"]["collection"][cid])["schema"]
        rows = [val(x) for x in r["recordMap"]["block"].values()]
        return schema, [x for x in rows if x.get("parent_table") == "collection" and x.get("alive", True)]
    raise SystemExit(f"No database found on page {page_id}")


def text(prop):
    return "".join(s[0] for s in prop or [] if isinstance(s, list) and s and isinstance(s[0], str)).strip()


def links(prop):
    out = []
    for s in prop or []:
        for a in (s[1] if isinstance(s, list) and len(s) > 1 else []):
            if a[0] == "a":
                out.append(a[1])
    t = text(prop)
    out += [u for u in re.findall(r"https?://[^\s,]+", t) if u not in out]
    return out


def date(prop):
    for s in prop or []:
        for a in (s[1] if isinstance(s, list) and len(s) > 1 else []):
            if a[0] == "d":
                return a[1].get("start_date"), a[1].get("end_date")
    return None, None


def multi(prop):
    return [x.strip() for x in text(prop).split(",") if x.strip() and "[object" not in x]


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d")


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def export(kind, page_id):
    schema, rows = rows_for(page_id)
    name = {k: p["name"].strip() for k, p in schema.items()}
    out = []
    for r in rows:
        p = {name[k]: v for k, v in r.get("properties", {}).items() if k in name}
        base = {"notion_id": r["id"], "created": iso(r["created_time"]), "last_edited": iso(r["last_edited_time"])}
        if kind == "tools":
            title = text(p.get("Product Name"))
            site = links(p.get("Website"))
            base.update(name=title, overview=text(p.get("Overview")), product_type=multi(p.get("Product Type")),
                        notion_categories=multi(p.get("Category")),
                        use_cases=[u.strip(" •-•") for u in text(p.get("Use Cases")).splitlines() if u.strip(" •-•")],
                        website=site[0] if site else "")
        elif kind == "thought-leaders":
            title = text(p.get("Marketer's Name") or p.get("Name"))
            def first(label):
                for k, v in p.items():
                    if k.lower().startswith(label):
                        l = links(v)
                        return l[0] if l else ""
                return ""
            head = p.get("Headshot")
            base.update(name=title, domains=multi(p.get("Marketing Domain")), x=first("x"), linkedin=first("linkedin"),
                        newsletter=first("newsletter"), website=first("website"),
                        notion_headshot=(links(head) or [text(head)])[0] if head else "")
        else:
            title = text(p.get("Event Name"))
            start, end = date(p.get("Date"))
            site = links(p.get("Event Website"))
            base.update(name=title, start_date=start, end_date=end, location=text(p.get("Location")),
                        event_type=text(p.get("Event Type")), website=site[0] if site else "",
                        other_links=site[1:], description=text(p.get("Description")))
        base["slug"] = slugify(title)
        out.append(base)
    out.sort(key=lambda x: x["name"].lower())
    path = OUT / f"{kind}.json"
    path.write_text(json.dumps({"source": f"https://www.notion.so/realjaymes/{page_id}",
                                "exported": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                                "count": len(out), "items": out}, indent=2, ensure_ascii=False) + "\n")
    print(f"{kind}: {len(out)} rows -> {path.relative_to(ROOT)}")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for kind, pid in PAGES.items():
        export(kind, pid)
