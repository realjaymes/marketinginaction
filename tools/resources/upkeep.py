#!/usr/bin/env python3
"""Keep the events calendar and the tools database current, with no manual step.

Events (every run, weekly):
  - A scheduled event that has ended becomes "past-awaiting-next".
  - For each event waiting for its next edition, the official site is read. A
    future date found in the page's event data (JSON-LD) or its title is taken as
    the next edition, and the event goes back to "scheduled".
  - For each upcoming event, the page that proved its date is read again. If the
    date no longer appears there, the event is flagged for review.
  - An event whose last edition is over two years old, or whose site has failed
    two runs in a row, is flagged for review, never removed automatically.

Tools (monthly, or with --tools):
  - Each tool's website is loaded. A site that fails two runs in a row (no
    answer, 404, 410, a server error or a parked domain) is hidden from the page
    with "hidden_since"; it shows again once the site loads. Sites that block
    scripts (401, 403, 429 and similar) are not counted as failures.
  - A tool with "retired" (shut down, or merged into another listed product) is
    skipped: it stays off the page whatever its old site does.
  - The homepage title and description are saved on first sight. When they
    change sharply, or the site now redirects to another domain, the tool is
    flagged as a possible pivot or acquisition. --accept SLUG takes the current
    homepage as the new baseline after a review.

Run state lives in data/resources/upkeep-state.json, and everything that needs
James's yes or no is written to data/resources/review.json, which the 17:00
intake run reports in the daily digest. The weekly GitHub Action
(.github/workflows/resources-upkeep.yml) runs this, then build.py --write, and
commits.

Usage:
  python3 tools/resources/upkeep.py                 events, plus tools on the first run of a month
  python3 tools/resources/upkeep.py --tools         force the tools check
  python3 tools/resources/upkeep.py --no-fetch      date moves only, no network
  python3 tools/resources/upkeep.py --accept SLUG   accept a tool's current homepage after review

Vault: AI Workflows/MIA Resources from Notion — Build Plan.
"""
import argparse, concurrent.futures as cf, html, json, pathlib, re, sys, urllib.error, urllib.request
from datetime import date, timedelta

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = ROOT / "data/resources"
STATE = DATA / "upkeep-state.json"
REVIEW = DATA / "review.json"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml", "Accept-Language": "en"}
BLOCKED = {400, 401, 403, 405, 406, 429, 451, 999}
PARKED = re.compile(r"hugedomains|sedo\.com|dan\.com|afternic|parkingcrew|bodis|godaddy\.com/domainsearch|domain is for sale|buy this domain", re.I)
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
MON = "|".join(m[:3] + r"[a-z]*\.?" for m in MONTHS)
DAY = r"\d{1,2}(?:st|nd|rd|th)?"
MORE = rf"(?:\s*(?:[-–,&]|to|and)\s*(?:(?:{MON})\s+)?{DAY})*"
DATE_MDY = re.compile(rf"\b({MON})\s+({DAY}){MORE}(?:,?\s+(20\d\d))?\b", re.I)
DATE_DMY = re.compile(rf"\b({DAY}){MORE}\s+(?:of\s+)?({MON})(?:,?\s+(20\d\d))?\b", re.I)
YEAR = re.compile(r"\b20\d\d\b")


def load(p, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def save(p, d):
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def fetch(url):
    """Return (status, final_url, text). status is an int, "down" when nothing answered, or "not-html"."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
            if "html" not in (r.headers.get("Content-Type") or "html"):
                return "not-html", r.geturl(), ""  # a PDF or file: nothing to read, and not a failure
            return r.status, r.geturl(), r.read(600_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, url, ""
    except Exception:
        return "down", url, ""


def failed(status, text):
    if status == "down" or status in (404, 410) or (isinstance(status, int) and status >= 500):
        return True
    return status == 200 and bool(PARKED.search(text[:20000]))


def head_meta(text):
    t = re.search(r"<title[^>]*>(.*?)</title>", text, re.S | re.I)
    d = (re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)', text, re.I)
         or re.search(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']*)', text, re.I))
    clean = lambda s: re.sub(r"\s+", " ", html.unescape(s or "")).strip()
    return clean(t.group(1) if t else ""), clean(d.group(1) if d else "")


def host(url):
    h = re.sub(r"^https?://", "", url or "").split("/")[0].split(":")[0].lower()
    parts = h.split(".")
    keep = 3 if len(parts) > 2 and parts[-2] in {"co", "com", "org", "net", "ac", "gov"} and len(parts[-1]) == 2 else 2
    return ".".join(parts[-keep:])


def words(s):
    return set(re.findall(r"[a-z0-9]{3,}", s.lower()))


def to_date(mon, day, year):
    m = next((n for n, name in enumerate(MONTHS, 1) if mon.lower().startswith(name[:3])), None)
    try:
        return date(int(year), m, int(day))
    except (TypeError, ValueError):
        return None


def dates_in(text):
    """Dates written out in prose, such as "Nov 18-19", "June 17th, 18th & 19th, 2027" or "28 October 2026".
    A date with no year takes the nearest year written within 80 characters."""
    out = []
    for rx, order in ((DATE_MDY, "md"), (DATE_DMY, "dm")):
        for m in rx.finditer(text):
            a, b, y = m.groups()
            mon, day = (a, b) if order == "md" else (b, a)
            if not y:
                near = [(abs(n.start() - m.start()), n.group()) for n in YEAR.finditer(text, max(0, m.start() - 80), m.end() + 80)]
                if not near:
                    continue
                y = min(near)[1]
            x = to_date(mon, re.match(r"\d+", day).group(), y)
            if x:
                out.append(x)
    return out


def jsonld_dates(text):
    out = []
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', text, re.S | re.I):
        for s, e in re.findall(r'"startDate"\s*:\s*"(\d{4}-\d\d-\d\d)[^"]*"(?:[^{}]*?"endDate"\s*:\s*"(\d{4}-\d\d-\d\d))?', block):
            try:
                out.append((date.fromisoformat(s), date.fromisoformat(e) if e else None))
            except ValueError:
                pass
    return out


def plain(text):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I))))


# ---------- events ----------

def run_events(today, state, review, net):
    d = load(DATA / "events.json", None)
    st = state.setdefault("events", {})
    items, flags, changes = d["items"], [], []
    for i in items:
        end = i.get("end_date") or i.get("start_date")
        if i["status"] == "scheduled" and end and date.fromisoformat(end) < today:
            i["status"] = "past-awaiting-next"
            changes.append(f"{i['name']} has ended and now waits for its next edition")
    if net:
        todo = [i for i in items if i["status"] in ("past-awaiting-next", "unknown", "scheduled") and (i.get("website") or i.get("date_source"))]
        with cf.ThreadPoolExecutor(8) as ex:
            pages = dict(zip([i["slug"] for i in todo],
                             ex.map(lambda i: fetch(i["date_source"] if i["status"] == "scheduled" and i.get("date_source") else i["website"]), todo)))
        for i in todo:
            status, final, text = pages[i["slug"]]
            s = st.setdefault(i["slug"], {"fails": 0})
            if failed(status, text):
                s["fails"] += 1
                if s["fails"] >= 2:
                    flags.append({"kind": "event-site-down", "slug": i["slug"], "name": i["name"],
                                  "message": f"Its site has failed {s['fails']} runs in a row ({status}). Mark it discontinued or give a new link."})
                continue
            s["fails"], s["checked"] = 0, today.isoformat()
            if status != 200:
                continue  # the site blocks scripts, so it says nothing either way
            title, desc = head_meta(text)
            if i["status"] == "scheduled":
                want = date.fromisoformat(i["start_date"])
                found = [x for x, _ in jsonld_dates(text)] + dates_in(title + " " + desc + " " + plain(text))
                if want not in found:
                    flags.append({"kind": "event-date-unconfirmed", "slug": i["slug"], "name": i["name"],
                                  "message": f"Its page no longer shows {want.isoformat()}. Check whether the date moved: {i['date_source']}"})
                continue
            nxt = sorted((s_, e_) for s_, e_ in jsonld_dates(text) if s_ >= today)
            src = "event data"
            if not nxt:
                nxt = sorted((x, None) for x in dates_in(title + " " + desc) if x >= today)
                src = "page title"
            if nxt:
                s_, e_ = nxt[0]
                i.update({"start_date": s_.isoformat(), "end_date": (e_ or s_).isoformat(), "status": "scheduled",
                          "date_source": final, "verified": today.isoformat(),
                          "notes": f"Next edition date read from the official site's {src}."})
                changes.append(f"{i['name']} has its next edition on {s_.isoformat()} (from the site's {src})")
            elif i.get("start_date") and date.fromisoformat(i["start_date"]) < today - timedelta(days=730):
                flags.append({"kind": "event-stale", "slug": i["slug"], "name": i["name"],
                              "message": "No edition in over two years. Mark it discontinued, or give the page with its next date."})
    d["updated"] = today.isoformat()
    save(DATA / "events.json", d)
    review["events"] = flags
    return changes, flags


# ---------- tools ----------

def run_tools(today, state, review):
    d = load(DATA / "tools.json", None)
    st = state.setdefault("tools", {})
    with cf.ThreadPoolExecutor(12) as ex:
        live = [i for i in d["items"] if not i.get("retired")]
        pages = dict(zip([i["slug"] for i in live], ex.map(lambda i: fetch(i["website"]), live)))
    flags, changes = [], []
    partner = re.compile(r"james|partnerlinks|partnerstack|via=|fpr=|affiliate|referral|partners\.|partnerwith", re.I)
    for i in d["items"]:
        if i.get("retired"):
            continue
        status, final, text = pages[i["slug"]]
        s = st.setdefault(i["slug"], {"fails": 0})
        if failed(status, text):
            s["fails"] += 1
            if s["fails"] >= 2 and not i.get("hidden_since"):
                i["hidden_since"] = today.isoformat()
                changes.append(f"{i['name']} is hidden: its site failed {s['fails']} runs in a row ({status})")
            continue
        s["fails"] = 0
        if i.pop("hidden_since", None):
            changes.append(f"{i['name']} is shown again: its site loads")
        if status != 200:
            continue
        title, desc = head_meta(text)
        s["checked"] = today.isoformat()
        if "title" not in s:
            s.update({"title": title, "description": desc, "host": host(final)})
            continue
        before, now = words(s["title"] + " " + s["description"]), words(title + " " + desc)
        moved = host(final) != s["host"] and not (i.get("partner") or partner.search(i["website"]))
        if moved or (before and now and len(before & now) / len(before | now) < 0.2):
            why = f"now redirects to {host(final)}" if moved else "its homepage title and description changed"
            flags.append({"kind": "tool-pivot", "slug": i["slug"], "name": i["name"],
                          "message": f"Possible pivot or acquisition: {why}. Was \"{s['title']}\", now \"{title}\". Keep, rewrite or remove it."})
    d["updated"] = today.isoformat()
    save(DATA / "tools.json", d)
    review["tools"] = flags
    state["tools_checked"] = today.isoformat()
    return changes, flags


def accept(slug, state):
    d = load(DATA / "tools.json", None)
    i = next((x for x in d["items"] if x["slug"] == slug), None)
    if not i:
        sys.exit(f"no tool {slug}")
    status, final, text = fetch(i["website"])
    title, desc = head_meta(text)
    state.setdefault("tools", {})[slug] = {"fails": 0, "title": title, "description": desc, "host": host(final), "checked": date.today().isoformat()}
    review = load(REVIEW, {})
    review["tools"] = [f for f in review.get("tools", []) if f["slug"] != slug]
    save(REVIEW, review)
    print(f"accepted {slug}: {title}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tools", action="store_true")
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--accept")
    ap.add_argument("--today")
    args = ap.parse_args()
    state, review = load(STATE, {}), load(REVIEW, {})
    if args.accept:
        accept(args.accept, state)
        save(STATE, state)
        return
    today = date.fromisoformat(args.today) if args.today else date.today()
    changes, flags = run_events(today, state, review, not args.no_fetch)
    last = state.get("tools_checked", "")
    if not args.no_fetch and (args.tools or last[:7] != today.isoformat()[:7]):
        c, f = run_tools(today, state, review)
        changes += c
        flags += f
    review["as_of"] = today.isoformat()
    save(STATE, state)
    save(REVIEW, review)
    for c in changes:
        print("changed:", c)
    for f in review.get("events", []) + review.get("tools", []):
        print("review:", f["name"], "-", f["message"])


if __name__ == "__main__":
    main()
