#!/usr/bin/env python3
"""Add new events and tools to the MIA resource pages from the daily 17:00 run.

Sources:
  - Events: "MIA Events Watch" reports (a ChatGPT scheduled task), harvested
    into the vault. Each row is kept only when its official page loads and shows
    the claimed start date. A row for an event already listed, whose new date is
    later, becomes that event's next edition.
  - Tools: "MIA Tools Watch" reports, the "Tool launches" table in each X brief,
    and the n8n feed of tools James sends by email or chat. Rows that arrive
    complete (overview, type, categories, use cases) are checked and added. Rows
    with only a name and a link become candidates, which a Claude step in the
    runner researches into full rows; "add" then checks and adds those.
  - Thought leaders: James's own list, Areas/Work/MIA/Resources/Thought Leader
    Candidates.md, passed in every day and never marked processed. Each person
    not yet listed becomes a candidate, a Claude step in the runner researches
    role, company, region, topics and links from their own pages, and
    "add-leaders" keeps the person only when name, role, a topic, profile_source
    and a working link are present. The digest lists each new person with follow
    links. X briefs are not a source: their authors are mostly viral accounts,
    news outlets and brands, with no clean repeat signal.

Every row is checked: the site must load, it must not already be listed (by
name or domain), and tool labels must be ones tool-groups.json knows (old Notion
names are translated through its "aliases").
Rejected rows are listed with the reason. The run state (briefs read,
candidates already tried) lives in data/resources/upkeep-state.json.

Usage (run inside the intake worktree, see tools/resources/intake-run.sh):
  python3 tools/resources/intake.py collect --events F.md ... --tools F.md ... --briefs DIR --feed URL --out DIR
  python3 tools/resources/intake.py add DIR/enriched.json --out DIR
  python3 tools/resources/intake.py collect ... --leaders "Thought Leader Candidates.md"   (also writes DIR/leader-candidates.json)
  python3 tools/resources/intake.py add-leaders DIR/leaders-enriched.json --out DIR [--no-fetch]
All write DIR/summary.html for the digest and print what changed.

Vault: AI Workflows/MIA Resources from Notion — Build Plan.
"""
import argparse, json, pathlib, re, sys, urllib.request
from datetime import date, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import upkeep as U  # fetch, failed, dates_in, jsonld_dates, plain, host
import build as B  # DOMAINS and REGIONS for thought leaders

DATA = U.DATA
TODAY = date.today()
AFRICA = {c.strip() for c in """algeria, angola, benin, botswana, burkina faso, burundi, cameroon, cape verde, central african republic,
chad, comoros, congo, dr congo, djibouti, egypt, equatorial guinea, eritrea, eswatini, ethiopia, gabon, gambia, ghana, guinea,
guinea-bissau, ivory coast, cote d'ivoire, kenya, lesotho, liberia, libya, madagascar, malawi, mali, mauritania, mauritius, morocco,
mozambique, namibia, niger, nigeria, rwanda, senegal, seychelles, sierra leone, somalia, south africa, south sudan, sudan, tanzania,
togo, tunisia, uganda, zambia, zimbabwe""".split(",")}
TYPES = {"conference": "Conference", "summit": "Summit", "expo": "Expo", "festival": "Festival", "meetup": "Meetup", "awards": "Awards",
         "workshop": "Workshop", "hackathon": "Hackathon"}
FORMATS = {"in person": "in-person", "in-person": "in-person", "online": "virtual", "virtual": "virtual", "hybrid": "hybrid"}
GENERIC_HOSTS = {"github.com", "google.com", "microsoft.com", "adobe.com", "facebook.com", "linkedin.com", "x.com", "twitter.com",
                 "notion.site", "vercel.app", "netlify.app", "framer.website", "webflow.io", "substack.com", "medium.com", "youtube.com",
                 "capcut.com", "bytedance.com", "about.fb.com", "openai.com", "anthropic.com", "meta.com", "amazon.com", "apple.com"}


def norm(n):
    n = re.sub(r"\b20\d\d\b", "", (n or "").lower())
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\.(ai|io|app|so|com)\b", "", n))


def slug(n):
    return re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-")


def table_rows(md, after=None):
    """Rows of the first markdown table (after a heading matching `after`), as dicts keyed by lower-case header."""
    if after:
        m = re.search(after, md, re.I | re.M)
        if not m:
            return []
        md = md[m.end():]
        nxt = re.search(r"^#{1,3} ", md, re.M)
        md = md[:nxt.start()] if nxt else md
    lines = [l.strip() for l in md.splitlines() if l.strip().startswith("|")]
    if len(lines) < 3:
        return []
    cells = lambda l: [c.strip() for c in l.strip("|").split("|")]
    head = [re.sub(r"[*_]", "", h).lower() for h in cells(lines[0])]
    out = []
    for l in lines[2:]:
        c = cells(l)
        if len(c) >= len(head) - 1:
            out.append({h: re.sub(r"^\*+|\*+$", "", (c[k] if k < len(c) else "")).strip() for k, h in enumerate(head)})
    return out


def link_of(cell):
    m = re.search(r"\((https?://[^)\s]+)\)", cell or "") or re.search(r"https?://[^\s|)>\]]+", cell or "")
    return (m.group(1) if m and m.lastindex else m.group(0)) if m else ""


def pick(row, *keys):
    for k in keys:
        for h, v in row.items():
            if h.startswith(k):
                return v
    return ""


# ---------- events ----------

def events_from(files, log):
    d = json.loads((DATA / "events.json").read_text(encoding="utf-8"))
    by_name = {norm(i["name"]): i for i in d["items"]}
    by_site = {(U.host(i.get("website")), i.get("start_date")): i for i in d["items"]}
    for f in files:
        for r in table_rows(pathlib.Path(f).read_text(encoding="utf-8")):
            name, site = pick(r, "event", "name"), link_of(pick(r, "official"))
            start, end = pick(r, "start"), pick(r, "end") or pick(r, "start")
            why = None
            try:
                s_, e_ = date.fromisoformat(start), date.fromisoformat(end)
            except ValueError:
                why = f"dates are not YYYY-MM-DD ({start}, {end})"
            if not why and (not name or not site):
                why = "no name or official link"
            if not why and e_ < TODAY:
                why = "already over"
            fmt = FORMATS.get(pick(r, "format").lower().strip())
            if not why and not fmt:
                why = f"format '{pick(r, 'format')}' is not In person, Online or Hybrid"
            if why:
                log["events_rejected"].append(f"{name or '?'}: {why}")
                continue
            old = by_name.get(norm(name)) or by_site.get((U.host(site), start))
            if old and old.get("start_date") and date.fromisoformat(old["start_date"]) >= s_:
                if old["start_date"] != start and old["status"] == "scheduled":
                    log["events_rejected"].append(f"{name}: already listed for {old['start_date']}, the report says {start}. Check {site}")
                continue  # already listed with this or a later date
            status, final, text = U.fetch(site)
            found = [x for x, _ in U.jsonld_dates(text)] + U.dates_in(U.plain(text)) if status == 200 else []
            if s_ not in found:
                log["events_rejected"].append(f"{name}: its official page {'does not show ' + start if status == 200 else 'could not be read (' + str(status) + ')'}")
                continue
            country = pick(r, "country")
            row = {"start_date": start, "end_date": end, "status": "scheduled", "date_source": final, "verified": TODAY.isoformat(),
                   "website": site, "notes": "Next edition added by the intake from the official site." if old else "Added by the intake from the MIA Events Watch report."}
            if old:
                old.update(row)
                log["events_added"].append(f"{old['name']}: next edition {start}")
                continue
            item = {"slug": slug(name), "name": name, **row, "city": pick(r, "city") or None, "country": country or None,
                    "venue": pick(r, "venue") or None, "format": fmt, "event_type": TYPES.get(pick(r, "type").lower().strip(), "Conference"),
                    "tickets": link_of(pick(r, "ticket")) or None, "organiser": pick(r, "organiser", "organizer") or None,
                    "description": pick(r, "what", "description") or None, "mia_event": False,
                    "region": "africa" if country.lower() in AFRICA else "global", "origin": "chatgpt"}
            if any(i["slug"] == item["slug"] for i in d["items"]):
                item["slug"] += f"-{s_.year}"
            d["items"].append(item)
            by_name[norm(name)] = item
            log["events_added"].append(f"{name} on {start}")
    d["count"] = len(d["items"])
    (DATA / "events.json").write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------- tools ----------

def tools_index():
    d = json.loads((DATA / "tools.json").read_text(encoding="utf-8"))
    names = {norm(i["name"]) for i in d["items"]}
    hosts = {U.host(i["website"]) for i in d["items"]} - GENERIC_HOSTS
    ids = {i.get("notion_id") for i in d["items"] if i.get("notion_id")}
    return d, names, hosts, ids


def known(name, site, names, hosts):
    h = U.host(site)
    return norm(name) in names or (site and h in hosts and h not in GENERIC_HOSTS)


def labels():
    """Every label the site knows, plus the old Notion names in "aliases", each mapped to its current label."""
    g = json.loads((DATA / "tool-groups.json").read_text(encoding="utf-8"))
    out = {c: c for cs in g["groups"].values() for c in cs}
    out.update({old: new for old, new in g.get("aliases", {}).items() if new in out})
    return out


def add_tool(row, d, names, hosts, log, cats):
    name, site = row.get("name", "").strip(), row.get("website", "").strip()
    if known(name, site, names, hosts):
        return
    c = list(dict.fromkeys(cats[x] for x in row.get("notion_categories") or row.get("categories") or [] if x in cats))
    types = [t for t in row.get("product_type") or [] if t in ("AI Tool", "Marketing Tool")]
    uses = [u.strip().rstrip(".") for u in row.get("use_cases") or [] if u.strip()][:6]
    why = None
    if not name or not site.startswith("http"):
        why = "no name or website"
    elif not c:
        why = "no category the site knows"
    elif not types:
        why = "not an AI or marketing tool"
    elif not row.get("overview") or row["overview"].startswith("Waiting for research"):
        why = "no overview"
    elif len(uses) < 3:
        why = "fewer than 3 use cases"
    if not why:
        status, final, text = U.fetch(site)
        if U.failed(status, text):
            why = f"its site does not load ({status})"
    if why:
        log["tools_rejected"].append(f"{name or '?'}: {why}")
        return
    item = {"created": TODAY.isoformat(), "last_edited": TODAY.isoformat(), "name": name, "overview": row["overview"].strip(),
            "product_type": types, "notion_categories": c, "use_cases": uses, "website": site, "slug": slug(name)}
    if row.get("notion_id"):
        item = {"notion_id": row["notion_id"], **item}
    if any(i["slug"] == item["slug"] for i in d["items"]):
        item["slug"] += "-tool"
    d["items"].append(item)
    names.add(norm(name))
    hosts.add(U.host(site))
    log["tools_added"].append(f"{name} ({row.get('source', 'intake')})")


def collect_tools(args, state, log, out):
    d, names, hosts, ids = tools_index()
    cats = labels()
    st = state.setdefault("intake", {})
    tried = st.setdefault("candidates_tried", {})
    cutoff = (TODAY - timedelta(days=90)).isoformat()
    tried = st["candidates_tried"] = {k: v for k, v in tried.items() if v >= cutoff}
    cands = {}

    def candidate(name, site, what, source):
        name = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", name or "").strip()
        k = norm(name)
        if not k or k in tried or k in cands or known(name, site, names, hosts):
            return
        cands[k] = {"name": name, "website": site, "what_it_does": what, "source": source}

    for f in args.tools or []:
        for r in table_rows(pathlib.Path(f).read_text(encoding="utf-8")):
            candidate(pick(r, "tool", "name"), link_of(pick(r, "official", "website", "site")), pick(r, "what", "why"), "MIA Tools Watch")
    if args.briefs:
        done = set(st.setdefault("briefs_done", []))
        for f in sorted(pathlib.Path(args.briefs).glob("20*Brief.md")):
            if f.name in done or f.name[:10] < "2026-10-20":
                continue
            for r in table_rows(f.read_text(encoding="utf-8"), after=r"^## Tool launches"):
                candidate(pick(r, "name"), link_of(pick(r, "official")), pick(r, "what"), f"X brief {f.name[:10]}")
            done.add(f.name)
        st["briefs_done"] = sorted(done)[-120:]
    if args.feed:
        try:
            since = (TODAY - timedelta(days=60)).isoformat()
            with urllib.request.urlopen(f"{args.feed}?since={since}", timeout=90) as r:
                feed = json.loads(r.read())
        except Exception as e:
            feed = []
            log["notes"].append(f"The n8n tools feed did not answer ({type(e).__name__}).")
        for row in feed:
            if row.get("none") or row.get("notion_id") in ids:
                continue
            if row.get("overview", "").startswith("Waiting for research") or not row.get("categories"):
                candidate(row.get("name"), row.get("website"), "", "sent by James through n8n")
            else:
                add_tool({**row, "source": "sent by James through n8n"}, d, names, hosts, log, cats)
    d["items"].sort(key=lambda i: i["name"].lower())
    d["count"] = len(d["items"])
    (DATA / "tools.json").write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for k in cands:
        tried[k] = TODAY.isoformat()
    (out / "candidates.json").write_text(json.dumps(list(cands.values()), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log["candidates"] = [c["name"] for c in cands.values()]


def add_enriched(path, log):
    d, names, hosts, _ = tools_index()
    cats = labels()
    rows = json.loads(pathlib.Path(path).read_text(encoding="utf-8")) if pathlib.Path(path).exists() else []
    for r in rows:
        if r.get("skip"):
            log["tools_rejected"].append(f"{r.get('name', '?')}: {r['skip']}")
            continue
        add_tool(r, d, names, hosts, log, cats)
    d["items"].sort(key=lambda i: i["name"].lower())
    d["count"] = len(d["items"])
    (DATA / "tools.json").write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------- thought leaders ----------

LEADERS_FILE = DATA / "thought-leaders.json"
FOLLOW_KEYS = ("x", "linkedin", "newsletter", "website")
PROFILE_HOSTS = {"x.com", "twitter.com", "linkedin.com"}


def links_in(cell):
    return list(dict.fromkeys(re.findall(r"https?://[^\s|)>\]]+", cell or "")))


def handle_keys(url):
    """Identity keys for a profile link: an X handle, a LinkedIn /in/ name, or a site host that is not a shared platform."""
    u = (url or "").strip().lower().rstrip("/")
    if not u.startswith("http"):
        return set()
    m = re.search(r"(?:x|twitter)\.com/@?([a-z0-9_]{1,15})(?:[/?#]|$)", u)
    if m:
        return {"x:" + m.group(1)}
    m = re.search(r"linkedin\.com/(?:in|company)/([^/?#]+)", u)
    if m:
        return {"li:" + m.group(1)}
    h = U.host(u)
    return {"site:" + h} if h and h not in GENERIC_HOSTS | PROFILE_HOSTS else set()


def person_keys(p):
    keys = {"slug:" + (p.get("slug") or slug(p.get("name", "")))}
    for k in FOLLOW_KEYS:
        keys |= handle_keys(p.get(k))
    return keys


def leaders_index():
    d = json.loads(LEADERS_FILE.read_text(encoding="utf-8"))
    keys = set()
    for i in d["items"]:
        keys |= person_keys(i)
    return d, keys


def collect_leaders(files, state, log, out):
    d, keys = leaders_index()
    st = state.setdefault("intake", {})
    cutoff = (TODAY - timedelta(days=90)).isoformat()
    tried = st["leaders_tried"] = {k: v for k, v in st.setdefault("leaders_tried", {}).items() if v >= cutoff}
    cands = {}
    for f in files:
        for r in table_rows(pathlib.Path(f).read_text(encoding="utf-8")):
            name = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", pick(r, "name", "person")).strip()
            links = links_in(pick(r, "profile", "link", "x", "site"))
            if not name or not links:
                if name:
                    log["leaders_rejected"].append(f"{name}: no profile link in the candidate list")
                continue
            ck = {"slug:" + slug(name)}
            for l in links:
                ck |= handle_keys(l)
            if ck & keys or slug(name) in tried or slug(name) in cands:
                continue
            cands[slug(name)] = {"name": name, "links": links, "note": pick(r, "note", "what", "why"), "source": "James's candidate list"}
    for k in cands:
        tried[k] = TODAY.isoformat()
    (out / "leader-candidates.json").write_text(json.dumps(list(cands.values()), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log["leader_candidates"] = [c["name"] for c in cands.values()]


def x_profile(url):
    """Display name of an X account through the fxtwitter API (no login), or None."""
    m = re.search(r"(?:x|twitter)\.com/@?([A-Za-z0-9_]{1,15})", url or "")
    if not m:
        return None
    try:
        req = urllib.request.Request(f"https://api.fxtwitter.com/{m.group(1)}", headers=U.UA)
        with urllib.request.urlopen(req, timeout=25) as r:
            return (json.loads(r.read()).get("user") or {}).get("name")
    except Exception:
        return None


def add_leader(row, d, keys, log, fetch=True):
    name = (row.get("name") or "").strip()
    domains = [t for t in dict.fromkeys(row.get("domains") or row.get("tags") or []) if t in B.DOMAINS]
    links = {k: (row.get(k) or "").strip() for k in FOLLOW_KEYS}
    links = {k: v for k, v in links.items() if v.startswith("http")}
    src = (row.get("profile_source") or "").strip()
    why = None
    if not name:
        why = "no name"
    elif not (row.get("role") or "").strip():
        why = "no role confirmed from their own pages"
    elif not domains:
        why = "no topic tag the site knows"
    elif not src.startswith("http"):
        why = "no profile_source"
    elif not links:
        why = "no link"
    else:
        ck = {"slug:" + slug(name)}
        for l in links.values():
            ck |= handle_keys(l)
        if ck & keys:
            return  # already listed
    xname = None
    if not why and fetch:
        working = False
        for k in ("website", "newsletter"):
            if links.get(k):
                status, _, text = U.fetch(links[k])
                if not U.failed(status, text):
                    working = True
        if links.get("x"):
            xname = x_profile(links["x"])
            working = working or bool(xname)
        if not working:
            why = "none of its links loads (X is checked through fxtwitter, LinkedIn is not counted)"
    if why:
        log["leaders_rejected"].append(f"{name or '?'}: {why}")
        return
    clean = lambda t: re.sub(r"\s*[\u2014\u2013]\s*|\s+-\s+", ", ", (t or "").strip())
    item = {"name": name, "domains": sorted(domains, key=B.DOMAINS.index), "x": links.get("x", ""), "linkedin": links.get("linkedin", ""),
            "newsletter": links.get("newsletter", ""), "website": links.get("website", ""), "slug": slug(name),
            "role": clean(row["role"]), "company": clean(row.get("company")) or None, "one_liner": clean(row.get("one_liner")) or None,
            "profile_source": src}
    if row.get("region") in B.REGIONS:
        item["region"] = row["region"]
        if row.get("country"):
            item["country"] = row["country"].strip()
    if xname and U.words(xname) & U.words(name):
        item["x_verified"] = True
    item = {k: v for k, v in item.items() if v is not None}
    if any(i["slug"] == item["slug"] for i in d["items"]):
        item["slug"] += "-" + (item.get("company") and slug(item["company"]) or "mia")
    d["items"].append(item)
    keys |= person_keys(item)
    log["leaders_added"].append(item["slug"])
    log["leaders_follow"].append({"name": name, "role": item["role"], "company": item.get("company"),
                                  "links": {k: links[k] for k in FOLLOW_KEYS if links.get(k)}})


def add_leaders(path, log, fetch=True):
    d, keys = leaders_index()
    rows = json.loads(pathlib.Path(path).read_text(encoding="utf-8")) if pathlib.Path(path).exists() else []
    for r in rows:
        if r.get("skip"):
            log["leaders_rejected"].append(f"{r.get('name', '?')}: {r['skip']}")
            continue
        add_leader(r, d, keys, log, fetch)
    if log["leaders_added"]:
        d["updated"] = TODAY.isoformat()
        d["count"] = len(d["items"])
        LEADERS_FILE.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------- summary ----------

def summary(log, out):
    review = U.load(U.REVIEW, {})
    parts = []
    li = lambda xs: "<ul>" + "".join(f"<li>{x}</li>" for x in xs) + "</ul>"
    if log["events_added"]:
        parts.append("<p>Events added to the calendar:</p>" + li(log["events_added"]))
    if log["tools_added"]:
        parts.append("<p>Tools added to the directory:</p>" + li(log["tools_added"]))
    if log.get("leaders_follow"):
        lab = {"x": "X", "linkedin": "LinkedIn", "newsletter": "Newsletter", "website": "Website"}
        rows = [f"{p['name']} ({' at '.join(x for x in (p['role'], p.get('company')) if x)}): follow on "
                + ", ".join(f'<a href="{u}">{lab[k]}</a>' for k, u in p["links"].items()) for p in log["leaders_follow"]]
        parts.append("<p>Thought leaders added to the directory. Follow them, then mark them followed in "
                     "MIA/Resources/Thought Leaders — Follow List:</p>" + li(rows))
    rej = log["events_rejected"] + log["tools_rejected"] + log.get("leaders_rejected", [])
    if rej:
        parts.append("<p>Not added:</p>" + li(rej))
    flags = [f"{f['name']}: {f['message']}" for f in review.get("events", []) + review.get("tools", []) + review.get("leaders", [])]
    if flags:
        parts.append(f"<p>Waiting for your yes or no (from the {review.get('as_of', '')} upkeep run):</p>" + li(flags))
    parts += [f"<p>{n}</p>" for n in log["notes"]]
    (out / "summary.html").write_text("\n".join(parts), encoding="utf-8")
    for k in ("events_added", "tools_added", "events_rejected", "tools_rejected", "candidates", "leaders_added", "leaders_rejected", "leader_candidates"):
        for x in log.get(k, []):
            print(f"{k}: {x}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--events", nargs="*")
    c.add_argument("--tools", nargs="*")
    c.add_argument("--briefs")
    c.add_argument("--feed")
    c.add_argument("--leaders", nargs="*", help="James's thought leader candidate list(s)")
    c.add_argument("--out", required=True)
    a = sub.add_parser("add")
    a.add_argument("enriched")
    a.add_argument("--out", required=True)
    l = sub.add_parser("add-leaders")
    l.add_argument("enriched")
    l.add_argument("--out", required=True)
    l.add_argument("--no-fetch", action="store_true", help="skip the link checks (tests)")
    args = ap.parse_args()
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    logf = out / "log.json"
    fresh = {"events_added": [], "events_rejected": [], "tools_added": [], "tools_rejected": [], "candidates": [], "notes": [],
             "leaders_added": [], "leaders_rejected": [], "leader_candidates": [], "leaders_follow": []}
    log = {**fresh, **json.loads(logf.read_text())} if args.cmd != "collect" and logf.exists() else fresh
    state = U.load(U.STATE, {})
    if args.cmd == "collect":
        events_from(args.events or [], log)
        collect_tools(args, state, log, out)
        collect_leaders(args.leaders or [], state, log, out)
    elif args.cmd == "add":
        add_enriched(args.enriched, log)
    else:
        add_leaders(args.enriched, log, not args.no_fetch)
    U.save(U.STATE, state)
    logf.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
    summary(log, out)


if __name__ == "__main__":
    main()
