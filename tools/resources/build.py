#!/usr/bin/env python3
"""Build the MIA resource pages from their data files, and check them.

Pages built (one data file each, in data/resources/):
  resources/tech-events-calendar/index.html   from events.json
  resources/tech-events-calendar/events.ics    the whole calendar, for subscribing

The page shell (head tags, tracking, header, footer and the Academy styling
block) is copied from services/index.html, so a change there reaches these
pages on the next build.
Pages render against the data file's "updated" date, never today's date, so
--check gives the same answer on every machine. The daily upkeep job moves
"updated" forward and rebuilds. A small script on the page also hides events
that have passed since the last build.

Usage:
  python3 tools/resources/build.py --write   rewrite the pages from the data
  python3 tools/resources/build.py --check   fail if data is invalid or a page is stale

Vault: AI Workflows/MIA Resources from Notion — Build Plan.
"""
import argparse, html, json, pathlib, re, sys
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = ROOT / "data/resources"
SHELL = ROOT / "services/index.html"
BASE = "https://marketinginaction.xyz"
EVENTS_DIR = ROOT / "resources/tech-events-calendar"
STATUSES = {"scheduled", "past-awaiting-next", "discontinued", "unknown"}
FORMATS = {"in-person", "virtual", "hybrid"}
E = html.escape


def fail(errors):
    for e in errors:
        print(f"resources check: {e}")
    sys.exit(1)


# ---------- validation ----------

def iso(s):
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def validate_events(d):
    errs, seen = [], set()
    if not iso(d.get("updated")):
        errs.append("events.json needs an 'updated' date (YYYY-MM-DD)")
    for i in d["items"]:
        s = i.get("slug", "?")
        if s in seen:
            errs.append(f"duplicate event slug {s}")
        seen.add(s)
        if not i.get("name"):
            errs.append(f"{s}: missing name")
        if i.get("status") not in STATUSES:
            errs.append(f"{s}: status must be one of {sorted(STATUSES)}")
        if i.get("format") not in FORMATS:
            errs.append(f"{s}: format must be one of {sorted(FORMATS)}")
        st, en = i.get("start_date"), i.get("end_date")
        if st and not iso(st):
            errs.append(f"{s}: bad start_date {st}")
        if en and (not iso(en) or (iso(st) and iso(en) < iso(st))):
            errs.append(f"{s}: bad end_date {en}")
        if i.get("status") == "scheduled" and not (st and i.get("date_source")):
            errs.append(f"{s}: a scheduled event needs a start_date and the date_source page that shows it")
        for k in ("website", "tickets", "date_source"):
            v = i.get(k)
            if v and not re.match(r"https?://[^\s]+$", v):
                errs.append(f"{s}: {k} is not a link: {v}")
    return errs


# ---------- page shell ----------

def sub1(pattern, repl, text, label):
    new, n = re.subn(pattern, lambda m: repl, text, count=1, flags=re.S)
    if n != 1:
        fail([f"page shell: could not find {label} in resources/index.html"])
    return new


def shell(path, title, description, social_title, body_class, main_html, jsonld, crumb):
    t = SHELL.read_text(encoding="utf-8")
    url = f"{BASE}/{path}"
    a = E(social_title, quote=True)
    d = E(description, quote=True)
    t = sub1(r'<meta property="og:title" content="[^"]*" />', f'<meta property="og:title" content="{a}" />', t, "og:title")
    t = sub1(r'<meta property="og:description" content="[^"]*" />', f'<meta property="og:description" content="{d}" />', t, "og:description")
    t = sub1(r'<meta property="og:url" content="[^"]*" />', f'<meta property="og:url" content="{url}" />', t, "og:url")
    t = sub1(r'<meta name="twitter:title" content="[^"]*" />', f'<meta name="twitter:title" content="{a}" />', t, "twitter:title")
    t = sub1(r'<meta name="twitter:description" content="[^"]*" />', f'<meta name="twitter:description" content="{d}" />', t, "twitter:description")
    t = sub1(r"<title>.*?</title>", f"<title>{E(title)}</title>", t, "title")
    t = sub1(r'<link rel="canonical" href="[^"]*" />', f'<link rel="canonical" href="{url}" />', t, "canonical")
    t = sub1(r'<meta\s+name="description"\s+content="[^"]*"\s*/>', f'<meta\n      name="description"\n      content="{d}"\n    />', t, "meta description")
    t = sub1(r'(    <!-- BreadcrumbList schema -->)', '    <script type="application/ld+json">\n' + jsonld + '\n    </script>\n    <!-- BreadcrumbList schema -->', t, "breadcrumb comment")
    t = sub1(r'\{ "@type": "ListItem", "position": 2, "name": "Services", "item": "https://marketinginaction.xyz/services/" \}',
             '{ "@type": "ListItem", "position": 2, "name": "Resources", "item": "https://marketinginaction.xyz/resources/" },\n'
             f'        {{ "@type": "ListItem", "position": 3, "name": "{crumb}", "item": "{url}" }}', t, "breadcrumb item")
    t = sub1(r'<body class="consulting-page">', f'<body class="consulting-page {body_class}">', t, "body class")
    t = sub1(r"<main>.*?</main>", "<main>\n" + main_html + "\n    </main>", t, "main")
    return t


# ---------- events page ----------

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def place(i):
    if i.get("format") == "virtual":
        return "Online"
    bits = [x for x in (i.get("venue"), i.get("city"), i.get("country")) if x]
    return ", ".join(bits) if bits else "Location to be announced"


def when(i):
    s, e = iso(i.get("start_date")), iso(i.get("end_date"))
    if not s:
        return "Date to be announced"
    if not e or e == s:
        return f"{s.day} {MONTHS[s.month - 1]} {s.year}"
    if (s.year, s.month) == (e.year, e.month):
        return f"{s.day} to {e.day} {MONTHS[s.month - 1]} {s.year}"
    if s.year == e.year:
        return f"{s.day} {MONTHS[s.month - 1]} to {e.day} {MONTHS[e.month - 1]} {s.year}"
    return f"{s.day} {MONTHS[s.month - 1]} {s.year} to {e.day} {MONTHS[e.month - 1]} {e.year}"


def card(i, kind):
    s = iso(i.get("start_date"))
    end = i.get("end_date") or i.get("start_date") or ""
    links = []
    if i.get("website"):
        links.append(f'<a class="ev-link" href="{E(i["website"], quote=True)}" target="_blank" rel="noopener">Official site</a>')
    if i.get("tickets") and i.get("tickets") != i.get("website"):
        links.append(f'<a class="ev-link" href="{E(i["tickets"], quote=True)}" target="_blank" rel="noopener">Tickets</a>')
    if kind == "upcoming":
        links.append(f'<a class="ev-link" href="ics/{E(i["slug"])}.ics" download>Add to calendar</a>')
    if kind == "tba" and s:
        note = f'Last held {when(i)}. The next date goes up here once the organiser announces it.'
    elif kind == "tba":
        note = "The next date goes up here once the organiser announces it."
    else:
        note = ""
    city = i.get("city") or ("Online" if i.get("format") == "virtual" else "")
    datebox = (f'<div class="ev-date"><span class="ev-day">{s.day}</span><span class="ev-mon">{MONTHS[s.month - 1][:3]}</span></div>'
               if s and kind != "tba" else '<div class="ev-date ev-date-tba"><span class="ev-mon">TBA</span></div>')
    tags = [i.get("event_type") or "Event", {"in-person": "In person", "virtual": "Online", "hybrid": "In person and online"}[i["format"]]]
    if i.get("mia_event"):
        tags.insert(0, "MIA event")
    return f"""          <article class="ev-card{' ev-mia' if i.get('mia_event') else ''}" data-end="{E(end)}" data-region="{E(i.get('region', 'africa'))}" data-city="{E(city)}" data-type="{E(i.get('event_type') or '')}" data-text="{E((i['name'] + ' ' + (i.get('organiser') or '') + ' ' + city + ' ' + (i.get('country') or '')).lower(), quote=True)}">
            {datebox}
            <div class="ev-body">
              <div class="ev-tags">{''.join(f'<span class="ev-tag">{E(t)}</span>' for t in tags)}</div>
              <h3 class="ev-name">{E(i['name'])}</h3>
              <p class="ev-meta">{E(when(i))} · {E(place(i))}</p>
              {f'<p class="ev-desc">{E(i["description"])}</p>' if i.get('description') else ''}
              {f'<p class="ev-note">{E(note)}</p>' if note else ''}
              {f'<p class="ev-org">Organised by {E(i["organiser"])}</p>' if i.get('organiser') else ''}
              <div class="ev-links">{''.join(links)}</div>
            </div>
          </article>"""


def ics_event(i, stamp):
    s, e = iso(i["start_date"]), iso(i.get("end_date") or i["start_date"])
    end = date.fromordinal(e.toordinal() + 1)
    def esc(x):
        return (x or "").replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", " ")
    return "\r\n".join([
        "BEGIN:VEVENT", f"UID:{i['slug']}-{s.isoformat()}@marketinginaction.xyz", f"DTSTAMP:{stamp}T000000Z",
        f"DTSTART;VALUE=DATE:{s.strftime('%Y%m%d')}", f"DTEND;VALUE=DATE:{end.strftime('%Y%m%d')}",
        f"SUMMARY:{esc(i['name'])}", f"LOCATION:{esc(place(i))}",
        f"DESCRIPTION:{esc((i.get('description') or '') + ' ' + (i.get('website') or ''))}",
        f"URL:{i.get('website') or BASE + '/resources/tech-events-calendar/'}", "END:VEVENT"])


def ics(items, stamp, name):
    return "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Marketing In Action//Tech Events Calendar//EN",
                        "CALSCALE:GREGORIAN", f"X-WR-CALNAME:{name}", "X-WR-TIMEZONE:Africa/Lagos"]
                       + [ics_event(i, stamp) for i in items] + ["END:VCALENDAR", ""])


def events_files():
    d = json.loads((DATA / "events.json").read_text(encoding="utf-8"))
    errs = validate_events(d)
    if errs:
        fail(errs)
    as_of = iso(d["updated"])
    live = [i for i in d["items"] if i["status"] != "discontinued"]
    upcoming = sorted([i for i in live if iso(i.get("end_date") or i.get("start_date") or "") and iso(i.get("end_date") or i["start_date"]) >= as_of],
                      key=lambda i: (i["start_date"], i["name"].lower()))
    tba = sorted([i for i in live if i not in upcoming and not (iso(i.get("start_date") or "") and iso(i["start_date"]).year == as_of.year)],
                 key=lambda i: i["name"].lower())
    past = sorted([i for i in live if i not in upcoming and i not in tba], key=lambda i: i["start_date"], reverse=True)
    stamp = as_of.strftime("%Y%m%d")
    updated = f"{as_of.day} {MONTHS[as_of.month - 1]} {as_of.year}"

    groups, cur = [], None
    for i in upcoming:
        s = iso(i["start_date"])
        key = f"{MONTHS[s.month - 1]} {s.year}"
        if key != cur:
            groups.append((key, []))
            cur = key
        groups[-1][1].append(i)
    month_html = "\n".join(
        f'        <section class="ev-month" data-month="{E(k)}">\n          <h2 class="ev-month-title">{E(k)}</h2>\n          <div class="ev-list">\n'
        + "\n".join(card(i, "upcoming") for i in v) + "\n          </div>\n        </section>" for k, v in groups)
    cities = sorted({i.get("city") for i in upcoming + tba if i.get("city")})
    types = sorted({i.get("event_type") for i in upcoming + tba if i.get("event_type")})

    main = f"""      <section class="consulting-hero ev-hero">
        <div class="container">
          <div class="ev-hero-inner">
            <div class="pill"><span class="dot" aria-hidden="true"></span>MIA Tech Events Calendar</div>
            <h1 class="text-white">Tech and marketing events across <span class="text-yellow accent-italic">Africa</span>, plus the global ones worth the trip</h1>
            <p class="text-white consulting-hero-sub">Conferences, summits, expos and festivals for marketers, founders and tech teams, starting with Lagos. Every date is checked on the event's own website.</p>
            <p class="ev-updated">Last updated {E(updated)}. {len(upcoming)} upcoming events.</p>
            <div class="button-row ev-hero-buttons">
              <a class="button button-primary" href="events.ics">Subscribe in your calendar</a>
              <a class="button button-secondary" href="#upcoming">See upcoming events</a>
            </div>
          </div>
        </div>
      </section>

      <section id="upcoming" class="section ev-section">
        <div class="container">
          <form class="ev-filters" role="search" onsubmit="return false">
            <label class="ev-field ev-search"><span>Search</span><input type="search" id="ev-q" placeholder="Event, organiser or city" autocomplete="off"></label>
            <label class="ev-field"><span>Where</span><select id="ev-region"><option value="">Everywhere</option><option value="africa">Africa</option><option value="global">Outside Africa</option></select></label>
            <label class="ev-field"><span>City</span><select id="ev-city"><option value="">All cities</option>{''.join(f'<option>{E(c)}</option>' for c in cities)}</select></label>
            <label class="ev-field"><span>Type</span><select id="ev-type"><option value="">All types</option>{''.join(f'<option>{E(t)}</option>' for t in types)}</select></label>
          </form>
          <p class="ev-empty" hidden>No upcoming events match. Clear a filter to see more.</p>
{month_html}
        </div>
      </section>

      <section id="to-be-announced" class="section ev-section ev-tba">
        <div class="container">
          <div class="ev-head"><h2>Dates to be announced</h2><p>These events run most years. Each one moves up to the calendar as soon as its organiser publishes the next date.</p></div>
          <div class="ev-list">
{chr(10).join(card(i, 'tba') for i in tba)}
          </div>
        </div>
      </section>
{f"""
      <section id="past" class="section ev-section ev-past">
        <div class="container">
          <details>
            <summary><h2>Past events this year</h2><span class="ev-past-count">{len(past)} events</span><span class="ev-past-toggle" aria-hidden="true"></span></summary>
            <div class="ev-list">
{chr(10).join(card(i, 'past') for i in past)}
            </div>
          </details>
        </div>
      </section>""" if past else ''}

      <style>
        .ev-hero-inner {{ max-width: 820px; margin: 0 auto; text-align: center; }}
        .ev-hero-inner .pill {{ margin: 0 auto var(--space-lg); }}
        .ev-hero-inner .consulting-hero-sub {{ max-width: 660px; margin: var(--space-md) auto 0; }}
        .ev-updated {{ margin: var(--space-sm) 0 0; font-weight: 700; color: var(--ink); }}
        .ev-hero-buttons {{ margin-top: var(--space-lg); justify-content: center; }}
        .ev-section .container {{ max-width: var(--max-width); }}
        .ev-head {{ max-width: 720px; margin: 0 0 var(--space-lg); }}
        .ev-head p {{ color: var(--muted); }}
        .ev-filters {{ display: grid; grid-template-columns: 2fr 1fr 1fr 1fr; gap: var(--space-sm); margin-bottom: var(--space-xl); }}
        .ev-field {{ display: flex; flex-direction: column; gap: 6px; font-size: 13px; font-weight: 800; color: var(--ink); }}
        .ev-field input, .ev-field select {{ font: inherit; font-size: 15px; font-weight: 600; color: var(--ink); padding: 11px 14px; border: 2px solid var(--ink); border-radius: 14px; background: var(--white); box-shadow: var(--st-sm); }}
        .ev-month {{ margin-bottom: var(--space-xl); }}
        .ev-month-title {{ font-size: 24px; margin-bottom: var(--space-md); }}
        .ev-list {{ display: grid; gap: var(--space-lg); grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); }}
        .ev-card {{ display: flex; flex-direction: column; gap: var(--space-sm); background: var(--white); border: 2px solid var(--ink); border-radius: 18px; padding: var(--space-md); box-shadow: var(--st); }}
        .ev-mia {{ background: var(--gold-t); }}
        .ev-date {{ display: inline-flex; align-self: flex-start; align-items: baseline; gap: 8px; background: var(--ink); color: var(--white); border-radius: 999px; padding: 6px 14px; }}
        .ev-day {{ font-size: 18px; font-weight: 800; line-height: 1; }}
        .ev-mon {{ font-size: 13px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.06em; color: var(--gold); }}
        .ev-date-tba {{ background: var(--sb); }} .ev-date-tba .ev-mon {{ color: var(--ink); }}
        .ev-tags {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 4px; }}
        .ev-tag {{ font-size: 12px; font-weight: 800; padding: 3px 10px; border-radius: 999px; border: 2px solid var(--ink); background: var(--blue); color: var(--ink); }}
        .ev-tag + .ev-tag {{ background: var(--purple); }}
        .ev-mia .ev-tag:first-child {{ background: var(--gold); }}
        .ev-mia .ev-tag:nth-child(2) {{ background: var(--blue); }}
        .ev-name {{ font-size: 20px; margin: 0 0 4px; }}
        .ev-meta {{ font-weight: 800; margin: 0 0 6px; color: var(--ink); }}
        .ev-desc, .ev-note, .ev-org {{ margin: 0 0 6px; color: var(--muted); line-height: 1.55; }}
        .ev-links {{ display: flex; flex-wrap: wrap; gap: var(--space-md); margin-top: auto; padding-top: 8px; }}
        .ev-link {{ font-weight: 800; color: var(--ink); text-decoration: underline; text-decoration-thickness: 2px; text-underline-offset: 4px; }}
        .ev-body {{ display: flex; flex-direction: column; flex: 1; }}
        .ev-past summary {{ cursor: pointer; list-style: none; display: flex; align-items: center; gap: var(--space-sm); flex-wrap: wrap; background: var(--white); border: 2px solid var(--ink); border-radius: 18px; padding: var(--space-md) var(--space-lg); box-shadow: var(--st); transition: transform .14s ease, box-shadow .14s ease; }}
        .ev-past summary::-webkit-details-marker {{ display: none; }}
        .ev-past summary:hover {{ transform: translate(2px, 2px); box-shadow: 2px 2px 0 var(--ink); }}
        .ev-past summary h2 {{ display: inline; margin: 0; font-size: 22px; }}
        .ev-past-count {{ font-size: 13px; font-weight: 800; padding: 3px 10px; border: 2px solid var(--ink); border-radius: 999px; background: var(--sb); }}
        .ev-past-toggle {{ margin-left: auto; display: inline-flex; align-items: center; gap: 8px; font-weight: 800; background: var(--gold); border: 2px solid var(--ink); border-radius: 999px; padding: 8px 16px; box-shadow: var(--st-sm); }}
        .ev-past-toggle::before {{ content: "Show past events"; }} .ev-past-toggle::after {{ content: "▾"; }}
        .ev-past details[open] .ev-past-toggle::before {{ content: "Hide past events"; }} .ev-past details[open] .ev-past-toggle::after {{ content: "▴"; }}
        .ev-past .ev-list {{ margin-top: var(--space-lg); }}
        @media (max-width: 760px) {{
          .ev-filters {{ grid-template-columns: 1fr 1fr; }}
          .ev-search {{ grid-column: 1 / -1; }}
          .ev-list {{ grid-template-columns: 1fr; }}
        }}
      </style>
      <script>
        (function () {{
          var today = new Date().toISOString().slice(0, 10);
          var cards = document.querySelectorAll("#upcoming .ev-card");
          cards.forEach(function (c) {{ if (c.dataset.end && c.dataset.end < today) c.dataset.past = "1"; }});
          var q = document.getElementById("ev-q"), r = document.getElementById("ev-region"),
              ci = document.getElementById("ev-city"), ty = document.getElementById("ev-type");
          function apply() {{
            var text = q.value.trim().toLowerCase(), shown = 0;
            cards.forEach(function (c) {{
              var ok = !c.dataset.past && (!text || c.dataset.text.indexOf(text) > -1) &&
                (!r.value || c.dataset.region === r.value) && (!ci.value || c.dataset.city === ci.value) &&
                (!ty.value || c.dataset.type === ty.value);
              c.hidden = !ok; if (ok) shown++;
            }});
            document.querySelectorAll("#upcoming .ev-month").forEach(function (m) {{
              m.hidden = !m.querySelector(".ev-card:not([hidden])");
            }});
            document.querySelector(".ev-empty").hidden = shown > 0;
          }}
          [q, r, ci, ty].forEach(function (el) {{ el.addEventListener("input", apply); }});
          apply();
        }})();
      </script>"""

    jsonld = json.dumps({
        "@context": "https://schema.org", "@type": "CollectionPage", "dateModified": as_of.isoformat(),
        "name": "MIA Tech Events Calendar", "url": f"{BASE}/resources/tech-events-calendar/",
        "description": "Tech, startup and marketing events across Africa, plus major global marketing events, with every date checked on the official site.",
        "isPartOf": {"@type": "WebSite", "name": "Marketing In Action", "url": f"{BASE}/"},
        "mainEntity": {"@type": "ItemList", "itemListElement": [
            {"@type": "ListItem", "position": n + 1, "item": {
                "@type": "Event", "name": i["name"], "startDate": i["start_date"], "endDate": i.get("end_date") or i["start_date"],
                "eventAttendanceMode": {"virtual": "https://schema.org/OnlineEventAttendanceMode", "hybrid": "https://schema.org/MixedEventAttendanceMode"}.get(i["format"], "https://schema.org/OfflineEventAttendanceMode"),
                "eventStatus": "https://schema.org/EventScheduled",
                "location": ({"@type": "VirtualLocation", "url": i.get("website")} if i["format"] == "virtual" else
                             {"@type": "Place", "name": i.get("venue") or i.get("city") or "To be announced",
                              "address": {"@type": "PostalAddress", "addressLocality": i.get("city"), "addressCountry": i.get("country")}}),
                **({"url": i["website"]} if i.get("website") else {}),
                **({"description": i["description"]} if i.get("description") else {}),
                **({"organizer": {"@type": "Organization", "name": i["organiser"]}} if i.get("organiser") else {})}}
            for n, i in enumerate(upcoming)]}}, indent=2, ensure_ascii=False)

    page = shell("resources/tech-events-calendar/", "Tech Events Calendar for Africa | Marketing In Action",
                 f"{len(upcoming)} upcoming tech, startup and marketing events across Africa and beyond, with dates checked on each event's official site. Updated every day.",
                 "MIA Tech Events Calendar", "events-page", main, jsonld, "Tech Events Calendar")
    files = {EVENTS_DIR / "index.html": page,
             EVENTS_DIR / "events.ics": ics(upcoming, stamp, "MIA Tech Events Calendar")}
    for i in upcoming:
        files[EVENTS_DIR / "ics" / f"{i['slug']}.ics"] = ics([i], stamp, i["name"])
    return files


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    args = ap.parse_args()
    files = events_files()
    if args.write:
        old = set((EVENTS_DIR / "ics").glob("*.ics")) if (EVENTS_DIR / "ics").exists() else set()
        for p, text in files.items():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8", newline="")
        for p in old - set(files):
            p.unlink()
        print(f"resources: wrote {len(files)} files")
        return
    stale = [str(p.relative_to(ROOT)) for p, text in files.items()
             if not p.exists() or p.open(encoding="utf-8", newline="").read() != text]
    extra = [str(p.relative_to(ROOT)) for p in (EVENTS_DIR / "ics").glob("*.ics") if p not in files] if (EVENTS_DIR / "ics").exists() else []
    if stale or extra:
        fail([f"out of date with its data, run tools/resources/build.py --write: {p}" for p in stale]
             + [f"no longer in the data, run tools/resources/build.py --write: {p}" for p in extra])
    print("resources: data valid and pages current")


if __name__ == "__main__":
    main()
