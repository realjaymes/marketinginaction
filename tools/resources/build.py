#!/usr/bin/env python3
"""Build the MIA resource pages from their data files, and check them.

Pages built (one data file each, in data/resources/):
  resources/tech-events-calendar/index.html        from events.json
  resources/tech-events-calendar/events.ics         the whole calendar, for subscribing
  resources/marketing-ai-tools/index.html          from tools.json and tool-groups.json
  resources/marketing-thought-leaders/index.html   from thought-leaders.json

The page shell (head tags, tracking, header, footer and the Academy styling
block) is copied from services/index.html, so a change there reaches these
pages on the next build.
Pages render against the data file's "updated" date, never today's date, so
--check gives the same answer on every machine. The weekly upkeep job
(tools/resources/upkeep.py) moves "updated" forward and rebuilds. A small
script on the page also hides events that have passed since the last build.
A tool with "hidden_since" (its site has been down) is left off the page.

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


FORMAT_TOKENS = {"in-person": "in_person", "virtual": "online", "hybrid": "in_person online"}


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
    return f"""          <article class="ev-card{' ev-mia' if i.get('mia_event') else ''}" data-end="{E(end)}" data-region="{E(i.get('region', 'africa'))}" data-city="{E(tok(city))}" data-format="{FORMAT_TOKENS[i['format']]}" data-type="{E(tok(i.get('event_type') or ''))}" data-text="{E((i['name'] + ' ' + (i.get('organiser') or '') + ' ' + city + ' ' + (i.get('country') or '')).lower(), quote=True)}">
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
        f'        <section class="ev-month" data-month="{E(k)}" data-fsec>\n          <h2 class="ev-month-title">{E(k)}</h2>\n          <div class="ev-list">\n'
        + "\n".join(card(i, "upcoming") for i in v) + "\n          </div>\n        </section>" for k, v in groups)
    def opts(key):
        vals = {i.get(key) for i in upcoming if i.get(key)}
        counted = [(tok(v), v, sum(i.get(key) == v for i in upcoming)) for v in vals]
        return sorted(counted, key=lambda o: (-o[2], o[1]))
    panel = filter_panel("Event, organiser or city", [
        ("Where", "region", len(upcoming), [(r, label, sum(i.get("region", "africa") == r for i in upcoming))
                                          for r, label in (("africa", "Africa"), ("global", "Outside Africa"))]),
        # Hybrid events count under both, since people can attend either way.
        ("Format", "format", len(upcoming), [(t, label, sum(t in FORMAT_TOKENS[i["format"]].split() for i in upcoming))
                                             for t, label in (("in_person", "In person"), ("online", "Online"))]),
        ("Type", "type", len(upcoming), opts("event_type")),
        ("City", "city", len(upcoming), opts("city"))])

    main = f"""      <section class="consulting-hero ev-hero">
        <div class="container">
          <div class="ev-hero-inner">
            <div class="pill"><span class="dot" aria-hidden="true"></span>MIA Tech Events Calendar</div>
            <h1 class="text-white">Tech and marketing events across <span class="text-yellow accent-italic">Africa</span>, plus the global ones worth the trip</h1>
            <p class="text-white consulting-hero-sub">Conferences, summits, expos and festivals for marketers, founders and tech teams, starting with Lagos. Every date is checked on the event's own website.</p>
            <p class="ev-updated">Last updated {E(updated)}.</p>
            <div class="button-row ev-hero-buttons">
              <a class="button button-primary" href="events.ics">Subscribe in your calendar</a>
              <a class="button button-secondary" href="#upcoming">See upcoming events</a>
            </div>
          </div>
        </div>
      </section>

      <section id="upcoming" class="section ev-section">
        <div class="container">
          <div class="db-layout">
{panel}
            <div class="db-main">
{count_row(len(upcoming), "upcoming events")}
              <p class="db-empty" hidden>No upcoming events match your search. Try another word or clear the filters.</p>
{month_html}
            </div>
          </div>
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
        .ev-month {{ margin-bottom: var(--space-xl); }}
        .ev-month-title {{ font-size: 24px; margin-bottom: var(--space-md); }}
        .ev-list {{ display: grid; gap: var(--space-lg); grid-template-columns: repeat(auto-fill, minmax(270px, 1fr)); }}
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
        .ev-org {{ font-style: italic; font-size: 14px; }}
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
          .ev-list {{ grid-template-columns: 1fr; }}
        }}
      </style>
{FILTER_CSS}
{FILTER_JS}"""

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
                 "Upcoming tech, startup and marketing events across Africa and beyond, with dates checked on each event's official site. Updated every day.",
                 "MIA Tech Events Calendar", "events-page", main, jsonld, "Tech Events Calendar")
    files = {EVENTS_DIR / "index.html": page,
             EVENTS_DIR / "events.ics": ics(upcoming, stamp, "MIA Tech Events Calendar")}
    for i in upcoming:
        files[EVENTS_DIR / "ics" / f"{i['slug']}.ics"] = ics([i], stamp, i["name"])
    return files


# ---------- shared filter sidebar (events, tools and thought leaders pages) ----------
# The pattern of the case studies page: a sticky card on the left with a search box and
# labelled lists, the chosen item in ink. On phones the lists fold behind a
# "Show filters" toggle under the search box. Cards carry space-separated filter
# tokens in data attributes; sections marked data-fsec hide when they empty out.

def tok(v):
    return re.sub(r"\s+", "_", v.strip())


def filter_panel(placeholder, groups):
    """groups: [(title, dim, total, [(token, label, count), ...]), ...]"""
    html_groups = []
    for title, dim, total, opts in groups:
        btns = [f'<button type="button" class="db-fbtn is-active" data-dim="{dim}" data-value="" aria-pressed="true">All <span class="db-fcount">({total})</span></button>']
        btns += [f'<button type="button" class="db-fbtn" data-dim="{dim}" data-value="{E(t, quote=True)}" aria-pressed="false">{E(label)} <span class="db-fcount">({c})</span></button>'
                 for t, label, c in opts]
        html_groups.append(f'              <div class="db-fgroup" role="group" aria-label="{E(title, quote=True)}">\n'
                           f'                <p class="db-flabel">{E(title)}</p>\n                ' + "\n                ".join(btns) + "\n              </div>")
    return f"""          <aside class="db-side" aria-label="Search and filters">
            <div class="db-side-head"><label class="db-flabel" for="db-q">Search</label><button type="button" class="db-clear" hidden>Clear all</button></div>
            <input type="search" id="db-q" class="db-q" placeholder="{E(placeholder, quote=True)}" autocomplete="off">
            <details class="db-fdetails">
              <summary><span class="db-fsum">Filters</span><span class="db-factive" hidden></span><span class="db-ftoggle" aria-hidden="true"></span></summary>
              <div class="db-fgroups">
{chr(10).join(html_groups)}
              </div>
            </details>
          </aside>"""


def count_row(n, noun):
    return (f'              <div class="db-countrow"><p class="db-count" data-noun="{E(noun, quote=True)}" aria-live="polite">{n} {E(noun)}</p>'
            '<button type="button" class="db-clear db-clear-main" hidden>Clear filters</button></div>')


FILTER_CSS = """      <style>
        .db-layout { display: grid; grid-template-columns: 270px minmax(0, 1fr); gap: var(--space-xl); align-items: start; }
        .db-side { position: sticky; top: 96px; max-height: calc(100vh - 116px); overflow-y: auto; background: var(--white); border: 3px solid var(--ink); border-radius: 22px; box-shadow: var(--st); padding: 22px 14px 20px; }
        .db-layout [hidden] { display: none !important; }
        .db-side-head { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin: 0 0 10px; }
        .db-side-head .db-flabel { margin: 0; padding: 0; }
        .db-clear { font: inherit; font-size: 13px; font-weight: 800; color: var(--ink); background: none; border: 0; padding: 0; cursor: pointer; text-decoration: underline; text-decoration-thickness: 2px; text-underline-offset: 3px; }
        .db-clear-main { font-size: 14px; }
        .db-countrow { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; margin: 0 0 6px; }
        .db-countrow .db-count { margin: 0; }
        .db-q { margin: 0 0 22px; }
        .db-q, .db-side-search input { font: inherit; font-size: 15px; font-weight: 600; color: var(--ink); width: 100%; min-width: 0; padding: 10px 12px; border: 2px solid var(--ink); border-radius: 12px; background: var(--white); box-sizing: border-box; }
        .db-flabel { display: block; font-size: 12px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; color: var(--muted); margin: 0 0 10px; padding: 0 12px; }
        .db-side-search .db-flabel { padding: 0; }
        .db-fgroup + .db-fgroup { margin-top: 28px; }
        .db-fbtn { display: block; width: 100%; text-align: left; font: inherit; font-size: 15px; font-weight: 600; line-height: 1.35; color: var(--ink); background: none; border: 0; border-radius: 10px; padding: 7px 12px; margin: 0 0 2px; cursor: pointer; opacity: .85; }
        .db-fbtn:hover { opacity: 1; background: var(--sb); }
        .db-fbtn.is-active { opacity: 1; color: #fff; background: var(--ink); font-weight: 800; }
        .db-fbtn:disabled { opacity: .35; cursor: default; background: none; }
        .db-fcount { font-weight: 700; opacity: .7; }
        .db-fdetails > summary { display: none; }
        .db-main { min-width: 0; }
        .db-count { font-weight: 800; margin: 0 0 6px; color: var(--ink); }
        .db-empty { font-weight: 700; margin: 0 0 var(--space-lg); }
        @media (max-width: 900px) {
          .db-layout { grid-template-columns: 1fr; gap: var(--space-lg); }
          .db-side { position: static; max-height: none; overflow: visible; padding: 18px; border-width: 2px; }
          .db-q { margin-bottom: 14px; }
          .db-fdetails > summary { display: flex; align-items: center; gap: 10px; cursor: pointer; list-style: none; }
          .db-fdetails > summary::-webkit-details-marker { display: none; }
          .db-fsum { font-weight: 800; color: var(--ink); }
          .db-factive { font-size: 13px; font-weight: 800; padding: 2px 10px; border: 2px solid var(--ink); border-radius: 999px; background: var(--sb); }
          .db-ftoggle { margin-left: auto; display: inline-flex; align-items: center; gap: 8px; font-weight: 800; background: var(--gold); border: 2px solid var(--ink); border-radius: 999px; padding: 8px 16px; box-shadow: var(--st-sm); }
          .db-ftoggle::before { content: "Show filters"; } .db-ftoggle::after { content: "\u25be"; }
          .db-fdetails[open] .db-ftoggle::before { content: "Hide filters"; } .db-fdetails[open] .db-ftoggle::after { content: "\u25b4"; }
          .db-fdetails[open] .db-fgroups { margin-top: 18px; }
          .db-flabel { padding: 0; }
          .db-fbtn { margin-left: -12px; width: calc(100% + 24px); }
        }
      </style>"""


FILTER_JS = """      <script>
        (function () {
          // Filters in different lists combine (a card must match every list); one choice per list.
          // Each count shows how many cards that choice would leave given the other choices and the
          // search, and a choice that would leave none is disabled.
          var root = document.querySelector(".db-layout");
          if (!root) return;
          var main = root.querySelector(".db-main"), q = root.querySelector(".db-q"),
              cards = Array.prototype.slice.call(main.querySelectorAll("[data-text]")),
              btns = Array.prototype.slice.call(root.querySelectorAll(".db-fbtn")),
              count = main.querySelector(".db-count"), empty = main.querySelector(".db-empty"),
              clears = root.querySelectorAll(".db-clear"), det = root.querySelector(".db-fdetails"),
              active = root.querySelector(".db-factive"), sel = {};
          var today = new Date().toISOString().slice(0, 10);
          cards = cards.filter(function (c) {
            if (c.dataset.end && c.dataset.end < today) { c.hidden = true; return false; }
            return true;
          });
          btns.forEach(function (b) { sel[b.dataset.dim] = ""; });
          function has(c, dim, v) { return !v || (" " + (c.dataset[dim] || "") + " ").indexOf(" " + v + " ") > -1; }
          function fits(c, text, skip) {
            if (text && c.dataset.text.indexOf(text) < 0) return false;
            for (var k in sel) if (k !== skip && !has(c, k, sel[k])) return false;
            return true;
          }
          function apply() {
            var text = q.value.trim().toLowerCase(), shown = 0;
            cards.forEach(function (c) { var ok = fits(c, text); c.hidden = !ok; if (ok) shown++; });
            btns.forEach(function (b) {
              var dim = b.dataset.dim, v = b.dataset.value, n = 0;
              cards.forEach(function (c) { if (fits(c, text, dim) && has(c, dim, v)) n++; });
              b.querySelector(".db-fcount").textContent = "(" + n + ")";
              b.disabled = n === 0 && !b.classList.contains("is-active");
            });
            main.querySelectorAll("[data-fsec]").forEach(function (s) {
              var n = s.querySelectorAll("[data-text]:not([hidden])").length, pill = s.querySelector(".db-sec-count");
              s.hidden = !n; if (pill) pill.textContent = n;
            });
            var on = Object.keys(sel).filter(function (k) { return sel[k]; }).length;
            if (count) count.textContent = shown === cards.length ? cards.length + " " + count.dataset.noun : "Showing " + shown + " of " + cards.length + " " + count.dataset.noun;
            if (empty) empty.hidden = shown > 0;
            if (active) { active.hidden = !on; active.textContent = on + " on"; }
            clears.forEach(function (b) { b.hidden = !on && !text; });
          }
          function pick(dim, v) {
            sel[dim] = v;
            btns.forEach(function (x) {
              if (x.dataset.dim !== dim) return;
              var me = x.dataset.value === v;
              x.classList.toggle("is-active", me); x.setAttribute("aria-pressed", me ? "true" : "false");
            });
          }
          btns.forEach(function (b) {
            b.addEventListener("click", function () {
              pick(b.dataset.dim, b.dataset.value);
              apply();
              if (!wide.matches) det.open = false;
            });
          });
          clears.forEach(function (b) {
            b.addEventListener("click", function () { q.value = ""; Object.keys(sel).forEach(function (k) { pick(k, ""); }); apply(); });
          });
          q.addEventListener("input", apply);
          var wide = window.matchMedia("(min-width: 901px)");
          function fit() { if (wide.matches) det.open = true; }
          fit();
          if (wide.addEventListener) wide.addEventListener("change", fit); else wide.addListener(fit);
          apply();
        })();
      </script>"""


# ---------- shared styling for the two directory pages ----------

DB_CSS = """      <style>
        .db-hero-inner { max-width: 820px; margin: 0 auto; text-align: center; }
        .db-hero-inner .pill { margin: 0 auto var(--space-lg); }
        .db-hero-inner .consulting-hero-sub { max-width: 660px; margin: var(--space-md) auto 0; }
        .db-hero-buttons { margin-top: var(--space-lg); justify-content: center; }
        .db-section .container { max-width: var(--max-width); }
        .db-note { font-size: 14px; color: var(--muted); margin: 0 0 var(--space-lg); }
        .db-group { margin-bottom: var(--space-xl); scroll-margin-top: 90px; }
        .db-group-title { font-size: 24px; margin-bottom: var(--space-md); display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
        .db-group-title span { font-size: 13px; font-weight: 800; padding: 3px 10px; border: 2px solid var(--ink); border-radius: 999px; background: var(--white); }
        .db-list { display: grid; gap: var(--space-lg); grid-template-columns: repeat(auto-fill, minmax(270px, 1fr)); }
        .db-card { display: flex; flex-direction: column; gap: 8px; background: var(--white); border: 2px solid var(--ink); border-radius: 18px; padding: var(--space-md); box-shadow: var(--st); }
        .db-tags { display: flex; flex-wrap: wrap; gap: 6px; }
        .db-tag { font-size: 12px; font-weight: 800; padding: 3px 10px; border-radius: 999px; border: 2px solid var(--ink); background: var(--blue); color: var(--ink); }
        .db-tag-alt { background: var(--purple); }
        .db-tag-plain { background: var(--white); }
        .db-name { font-size: 20px; margin: 0; }
        .db-desc { margin: 0; color: var(--muted); line-height: 1.55; }
        .db-uses { margin: 0; padding-left: 18px; color: var(--ink); line-height: 1.5; font-size: 15px; }
        .db-uses li + li { margin-top: 2px; }
        .db-label { font-size: 13px; font-weight: 800; margin: 4px 0 0; color: var(--ink); }
        .db-meta { font-size: 13px; color: var(--muted); margin: 0; }
        .db-links { display: flex; flex-wrap: wrap; gap: var(--space-md); margin-top: auto; padding-top: 8px; }
        .db-link { font-weight: 800; color: var(--ink); text-decoration: underline; text-decoration-thickness: 2px; text-underline-offset: 4px; }
        .db-person { display: flex; gap: 14px; align-items: center; }
        .db-avatar { flex: none; width: 54px; height: 54px; border-radius: 50%; border: 2px solid var(--ink); background: var(--gold-t); display: grid; place-items: center; font-weight: 800; font-size: 18px; color: var(--ink); box-shadow: var(--st-sm); }
        .db-photo { object-fit: cover; padding: 0; background: var(--sb); }
        .db-role { margin: 2px 0 0; font-weight: 700; color: var(--ink); font-size: 15px; }
        @media (max-width: 760px) {
          .db-list { grid-template-columns: 1fr; }
        }
      </style>"""


def hero(pill, h1, sub, buttons):
    return f"""      <section class="consulting-hero db-hero">
        <div class="container">
          <div class="db-hero-inner">
            <div class="pill"><span class="dot" aria-hidden="true"></span>{E(pill)}</div>
            <h1 class="text-white">{h1}</h1>
            <p class="text-white consulting-hero-sub">{E(sub)}</p>
            <div class="button-row db-hero-buttons">
{buttons}
            </div>
          </div>
        </div>
      </section>"""


def link(url, text, sponsored=False):
    rel = "sponsored noopener" if sponsored else "noopener"
    return f'<a class="db-link" href="{E(url, quote=True)}" target="_blank" rel="{rel}">{E(text)}</a>'


def nice_date(d):
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def bad_link(v):
    return v and not re.match(r"https?://[^\s]+$", v)


# ---------- tools page ----------

TOOLS_DIR = ROOT / "resources/marketing-ai-tools"
TOOL_TYPES = {"AI Tool": "AI tool", "Marketing Tool": "Marketing tool"}
# Generic categories that say little about the job a tool does. A tool's group
# comes from its first category outside this set, or from its "group" field.
GENERIC = {"AI Models", "Platform-Integrated AI", "Marketing Technology", "Conversational AI", "Multimodal AI", "AI Content Generation"}
# Group order on the page: marketing jobs first, then AI building blocks, then operations.
GROUP_ORDER = ["Outbound and sales", "Email and lifecycle", "SEO and content", "Ads, social and reputation", "Analytics",
               "Video, image and audio", "AI models and assistants", "AI agents and automation", "Build and no-code",
               "Events and webinars", "Team and operations"]
# Partner links earn MIA a commission, so they carry rel="sponsored".
PARTNER = re.compile(r"james|partnerlinks|partnerstack|via=|fpr=|affiliate|referral|partners\.|partnerwith", re.I)


def is_partner(i):
    """A partner link earns MIA a commission. Most carry a tell in the URL; set "partner": true on a tool whose link does not."""
    return bool(i.get("partner") or PARTNER.search(i["website"]))


def gid(g):
    return re.sub(r"[^a-z0-9]+", "-", g.lower()).strip("-")


def tool_group(i, cat2g):
    if i.get("group"):
        return i["group"]
    cats = i["notion_categories"]
    specific = [c for c in cats if c not in GENERIC]
    return cat2g[(specific or cats)[0]]


def validate_tools(d, groups):
    errs, seen = [], set()
    cat2g = {c: g for g, cs in groups.items() for c in cs}
    if set(groups) != set(GROUP_ORDER):
        errs.append("tool-groups.json groups must match GROUP_ORDER in build.py")
    if not iso(d.get("updated")):
        errs.append("tools.json needs an 'updated' date (YYYY-MM-DD)")
    for i in d["items"]:
        s = i.get("slug", "?")
        if s in seen:
            errs.append(f"duplicate tool slug {s}")
        seen.add(s)
        for k in ("name", "overview", "website"):
            if not i.get(k):
                errs.append(f"{s}: missing {k}")
        if bad_link(i.get("website")):
            errs.append(f"{s}: website is not a link: {i['website']}")
        if not i.get("notion_categories"):
            errs.append(f"{s}: needs at least one category")
        for c in i.get("notion_categories", []):
            if c not in cat2g:
                errs.append(f"{s}: category '{c}' has no group in tool-groups.json")
        if i.get("group") and i["group"] not in groups:
            errs.append(f"{s}: group '{i['group']}' is not in tool-groups.json")
        if not i.get("product_type") or set(i["product_type"]) - set(TOOL_TYPES):
            errs.append(f"{s}: product_type must be from {sorted(TOOL_TYPES)}")
    return errs


def tool_card(i, grp):
    types = [TOOL_TYPES[t] for t in i["product_type"]]
    tags = "".join(f'<span class="db-tag{" db-tag-alt" if t == "Marketing tool" else ""}">{E(t)}</span>' for t in types)
    uses = "".join(f"<li>{E(u.rstrip('.'))}</li>" for u in i["use_cases"][:3])
    cats = ", ".join(i["notion_categories"])
    text = " ".join([i["name"], i["overview"], cats, grp] + i["use_cases"]).lower()
    return f"""          <article class="db-card" id="{E(i['slug'])}" data-group="{gid(grp)}" data-type="{E(' '.join(tok(t) for t in types))}" data-text="{E(text, quote=True)}">
            <div class="db-tags">{tags}</div>
            <h3 class="db-name">{E(i['name'])}</h3>
            <p class="db-desc">{E(i['overview'])}</p>
            <p class="db-label">Use cases</p>
            <ul class="db-uses">{uses}</ul>
            <p class="db-meta">{E(cats)}</p>
            <div class="db-links">{link(i['website'], 'Visit ' + i['name'], is_partner(i))}</div>
          </article>"""





def tools_files():
    d = json.loads((DATA / "tools.json").read_text(encoding="utf-8"))
    groups = json.loads((DATA / "tool-groups.json").read_text(encoding="utf-8"))["groups"]
    errs = validate_tools(d, groups)
    if errs:
        fail(errs)
    d["items"] = [i for i in d["items"] if not i.get("hidden_since")]
    cat2g = {c: g for g, cs in groups.items() for c in cs}
    as_of = iso(d["updated"])
    by = {g: [] for g in GROUP_ORDER}
    for i in sorted(d["items"], key=lambda i: i["name"].lower()):
        by[tool_group(i, cat2g)].append(i)
    order = [g for g in GROUP_ORDER if by[g]]
    n = len(d["items"])
    kinds = [(tok(TOOL_TYPES[t]), TOOL_TYPES[t] + "s", sum(t in i["product_type"] for i in d["items"])) for t in TOOL_TYPES]
    panel = filter_panel("Tool name or job", [
        ("Group", "group", n, [(gid(g), g, len(by[g])) for g in order]),
        ("Kind", "type", n, kinds)])
    sections = "\n".join(
        f'            <section class="db-group" id="{gid(g)}" data-fsec>\n          <h2 class="db-group-title">{E(g)}<span class="db-sec-count">{len(by[g])}</span></h2>\n          <div class="db-list">\n'
        + "\n".join(tool_card(i, g) for i in by[g]) + "\n          </div>\n        </section>" for g in order)

    main = hero("MIA Marketing & AI Product Database",
                'Marketing and AI tools, sorted by <span class="text-yellow accent-italic">the job they do</span>',
                "Find the right tool for the job in front of you, whether that is booking meetings, sending email, making video or running AI agents. Every listing tells you what the product does and where it fits in your work.",
                '              <a class="button button-primary" href="#tools">Browse the tools</a>\n'
                '              <a class="button button-secondary" href="/resources/">See all resources</a>') + f"""

      <section id="tools" class="section db-section">
        <div class="container">
          <div class="db-layout">
{panel}
            <div class="db-main">
{count_row(n, "tools")}
              <p class="db-note">Some links are partner links. MIA may earn a commission if you sign up through one, at no cost to you. Partner status never decides which tools MIA lists.</p>
              <p class="db-empty" hidden>No tools match your search. Try another word or clear the filters.</p>
{sections}
            </div>
          </div>
        </div>
      </section>
{DB_CSS}
{FILTER_CSS}
{FILTER_JS}"""

    jsonld = json.dumps({
        "@context": "https://schema.org", "@type": "CollectionPage", "dateModified": as_of.isoformat(),
        "name": "MIA Marketing & AI Product Database", "url": f"{BASE}/resources/marketing-ai-tools/",
        "description": "Marketing and AI tools for go-to-market teams, grouped by the job they do.",
        "isPartOf": {"@type": "WebSite", "name": "Marketing In Action", "url": f"{BASE}/"},
        "mainEntity": {"@type": "ItemList", "numberOfItems": n, "itemListElement": [
            {"@type": "ListItem", "position": k + 1, "item": {
                "@type": "SoftwareApplication", "name": i["name"], "description": i["overview"],
                "applicationCategory": tool_group(i, cat2g), "operatingSystem": "Web",
                **({} if is_partner(i) else {"url": i["website"]})}}
            for k, i in enumerate(i for g in order for i in by[g])]}}, indent=2, ensure_ascii=False)
    page = shell("resources/marketing-ai-tools/", "Marketing & AI Tools Database | Marketing In Action",
                 "Find marketing and AI tools by the job you need done: outbound, email, SEO, ads, analytics, video and AI agents. See what each one does. Free to search.",
                 "MIA Marketing & AI Product Database", "tools-page", main, jsonld, "Marketing & AI Product Database")
    return {TOOLS_DIR / "index.html": page}


# ---------- thought leaders page ----------

LEADERS_DIR = ROOT / "resources/marketing-thought-leaders"
DOMAINS = ["Growth Marketing", "Product Marketing", "AI", "GTM Engineering", "Automation", "Demand Generation",
           "Brand Marketing", "Content Marketing", "Digital Marketing", "Advertising"]
REGIONS = ["Africa", "North America", "Europe", "Asia", "Latin America", "Middle East", "Oceania"]


def validate_leaders(d):
    errs, seen = [], set()
    if not iso(d.get("updated")):
        errs.append("thought-leaders.json needs an 'updated' date (YYYY-MM-DD)")
    for i in d["items"]:
        s = i.get("slug", "?")
        if s in seen:
            errs.append(f"duplicate person slug {s}")
        seen.add(s)
        if not i.get("name"):
            errs.append(f"{s}: missing name")
        if not i.get("domains") or set(i["domains"]) - set(DOMAINS):
            errs.append(f"{s}: domains must be from {DOMAINS}")
        if i.get("region") and i["region"] not in REGIONS:
            errs.append(f"{s}: region must be one of {REGIONS}")
        for k in ("x", "linkedin", "newsletter", "website"):
            if bad_link(i.get(k)):
                errs.append(f"{s}: {k} is not a link: {i[k]}")
        if not any(i.get(k) for k in ("x", "linkedin", "newsletter", "website")):
            errs.append(f"{s}: needs at least one link")
        if i.get("headshot") and not (LEADERS_DIR / i["headshot"]).is_file():
            errs.append(f"{s}: headshot file {i['headshot']} is missing, run tools/resources/headshots.py")
    return errs


def initials(name):
    parts = [p for p in re.split(r"[\s-]+", name) if p[:1].isalpha()]
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()


def domain_order(i):
    return sorted(i["domains"], key=DOMAINS.index)[:3]


def fallback_line(i):
    # Used until a researched one-liner exists, so no card is left without a description.
    topics = [t if t in ("AI", "GTM Engineering") else t.lower() for t in domain_order(i)]
    return "Shares ideas on " + (" and ".join(topics) if len(topics) < 3 else ", ".join(topics[:-1]) + " and " + topics[-1]) + "."


def leader_card(i):
    doms = sorted(i["domains"], key=DOMAINS.index)  # every topic shows, so a topic filter never matches a card without its tag
    tags = "".join(f'<span class="db-tag">{E(t)}</span>' for t in doms)
    role = " at ".join(x for x in (i.get("role"), i.get("company")) if x)
    links = []
    if i.get("newsletter"):
        links.append(link(i["newsletter"], "Newsletter"))
    if i.get("website") and i["website"].rstrip("/") != (i.get("newsletter") or "").rstrip("/"):
        links.append(link(i["website"], "Website"))
    if i.get("linkedin"):
        links.append(link(i["linkedin"], "LinkedIn"))
    if i.get("x"):
        links.append(link(i["x"], "X"))
    text = " ".join([i["name"], role, i.get("one_liner") or "", i.get("country") or ""] + i["domains"]).lower()
    return f"""          <article class="db-card" id="{E(i['slug'])}" data-domain="{E(' '.join(tok(d) for d in i['domains']))}" data-region="{E(tok(i.get('region') or ''))}" data-text="{E(text, quote=True)}">
            <div class="db-person">
              {f'<img class="db-avatar db-photo" src="{E(i["headshot"], quote=True)}" alt="" width="54" height="54" loading="lazy" decoding="async">' if i.get("headshot") else f'<div class="db-avatar" aria-hidden="true">{E(initials(i["name"]))}</div>'}
              <div><h3 class="db-name">{E(i['name'])}</h3>{f'<p class="db-role">{E(role)}</p>' if role else ''}</div>
            </div>
            <p class="db-desc">{E(i.get("one_liner") or fallback_line(i))}</p>
            <div class="db-tags">{tags}</div>
            <div class="db-links">{''.join(links)}</div>
          </article>"""


def leaders_files():
    d = json.loads((DATA / "thought-leaders.json").read_text(encoding="utf-8"))
    errs = validate_leaders(d)
    if errs:
        fail(errs)
    as_of = iso(d["updated"])
    people = sorted(d["items"], key=lambda i: i["name"].lower())
    n = len(people)
    counts = {g: sum(g in i["domains"] for i in people) for g in DOMAINS}
    order = sorted([g for g in DOMAINS if counts[g]], key=lambda g: -counts[g])
    # The region filter appears once most people have a confirmed region, so it never hides people with no region on file.
    regions = [r for r in REGIONS if any(i.get("region") == r for i in people)] if sum(bool(i.get("region")) for i in people) >= 0.8 * n else []
    groups = [("Topic", "domain", n, [(tok(g), g, counts[g]) for g in order])]
    if regions:
        groups.append(("Based in", "region", n, [(tok(r), r, sum(i.get("region") == r for i in people)) for r in regions]))
    panel = filter_panel("Name, company or topic", groups)
    sections = '              <div class="db-list">\n' + "\n".join(leader_card(i) for i in people) + "\n              </div>"

    main = hero("MIA Marketing Thought Leaders Database",
                'Marketing thought leaders worth following in <span class="text-yellow accent-italic">growth, product marketing and GTM</span>',
                "Learn from the operators, founders and writers who share what is working in growth, product marketing, GTM engineering and AI. Filter by topic, then follow them where they publish.",
                '              <a class="button button-primary" href="#people">Browse the list</a>\n'
                '              <a class="button button-secondary" href="/resources/">See all resources</a>') + f"""

      <section id="people" class="section db-section">
        <div class="container">
          <div class="db-layout">
{panel}
            <div class="db-main">
{count_row(n, "people")}
              <p class="db-empty" hidden>No one matches your search. Try another word or clear the filters.</p>
{sections}
            </div>
          </div>
        </div>
      </section>
{DB_CSS}
{FILTER_CSS}
{FILTER_JS}"""

    def person(i):
        p = {"@type": "Person", "name": i["name"],
             "sameAs": [i[k] for k in ("linkedin", "x", "website", "newsletter") if i.get(k)],
             "knowsAbout": i["domains"]}
        if i.get("role"):
            p["jobTitle"] = i["role"]
        if i.get("company"):
            p["worksFor"] = {"@type": "Organization", "name": i["company"]}
        if i.get("headshot"):
            p["image"] = f"{BASE}/resources/marketing-thought-leaders/{i['headshot']}"
        return p
    jsonld = json.dumps({
        "@context": "https://schema.org", "@type": "CollectionPage", "dateModified": as_of.isoformat(),
        "name": "MIA Marketing Thought Leaders Database", "url": f"{BASE}/resources/marketing-thought-leaders/",
        "description": "Marketing thought leaders in growth, product marketing and GTM, with links to their newsletters and profiles.",
        "isPartOf": {"@type": "WebSite", "name": "Marketing In Action", "url": f"{BASE}/"},
        "mainEntity": {"@type": "ItemList", "numberOfItems": n, "itemListElement": [
            {"@type": "ListItem", "position": k + 1, "item": person(i)} for k, i in enumerate(people)]}},
        indent=2, ensure_ascii=False)
    page = shell("resources/marketing-thought-leaders/", "Marketing Thought Leaders to Follow | Marketing In Action",
                 "Learn from operators, founders and writers sharing what works in growth, product marketing, GTM engineering and AI. Filter by topic and follow them.",
                 "MIA Marketing Thought Leaders Database", "leaders-page", main, jsonld, "Marketing Thought Leaders Database")
    return {LEADERS_DIR / "index.html": page}


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    args = ap.parse_args()
    files = {**events_files(), **tools_files(), **leaders_files()}
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
