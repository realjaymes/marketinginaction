#!/usr/bin/env python3
"""Build the example homeowner pages at /acquisition/[niche]/example/.

Why this exists
---------------
Every MIA Acquisition niche has a View Leads sheet of example rows. Each row's
Page URL points at an example page the made-up business would run, so a
prospect can open the page their customers would see and try the form. One page
per niche, all in the same mobile-first layout (the form is the hero), is too
many to keep in step by hand, so the copy lives in ``data/example-pages.json``
and this script writes the pages.

The form questions match the sheet tab's own columns F, G and H, with the same
answer options, so a test submission reads like the example rows. Submissions go
to the Apps Script web app in ``ENDPOINT``, which appends them to the "Demo
submissions" tab of the View Leads sheet. The script source and how it is
deployed are in ``tools/example-pages-apps-script.gs``.

Every page is ``noindex`` (so the sitemap skips it), says on its ribbon and its
fine print that the business is made up, and never shows fake reviews.

Run it after editing the data file::

    python3 tools/build-example-pages.py            # write every page
    python3 tools/build-example-pages.py --check    # fail if a page is stale

The three-layout comparison page for water treatment
(``acquisition/water-treatment/example/options/``) is hand-built and kept as a
reference. This script does not touch it.
"""
import argparse
import html
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "example-pages.json"
SITE = "https://marketinginaction.xyz"

# Apps Script web app for the "Demo submissions" tab. Empty means the form shows
# its thank-you without sending anything.
ENDPOINT = "https://script.google.com/macros/s/AKfycbwMr1GPCvitOGZ-RKDrWS3woB8Ec-92Y40WA-DSoEugg-TnS4LLZzIlZ0Ghkjgnd4CZ/exec"

CITY = '<span data-city>your area</span>'


def esc(text):
    """Escape for HTML and turn {city} into the swappable city span."""
    return html.escape(text, quote=False).replace("{city}", CITY)


def attr(text):
    return html.escape(text, quote=True)


def taps(name, options):
    """Tap-to-pick radio buttons. Three options sit in one row; an odd last one spans."""
    cls = "taps three" if len(options) == 3 else "taps"
    out = []
    for i, opt in enumerate(options):
        wide = len(options) != 3 and len(options) % 2 == 1 and i == len(options) - 1
        req = " required" if i == 0 else ""
        out.append(
            f'<label class="tap{" wide" if wide else ""}"><input type="radio" name="{name}" '
            f'value="{attr(opt)}"{req}><span>{esc(opt)}</span></label>'
        )
    return f'<div class="{cls}">' + "".join(out) + "</div>"


def question(i, q):
    return (
        f'<span class="q">{esc(q["ask"])}</span>'
        f'<input type="hidden" name="a{i}Label" value="{attr(q["label"])}">'
        + taps(f"a{i}", q["options"])
    )


def form(p):
    qs = p["questions"]
    first, rest = qs[:2], qs[2:]
    step1 = "".join(question(i + 1, q) for i, q in enumerate(first))
    step2 = "".join(question(i + 3, q) for i, q in enumerate(rest))
    zip_label = p.get("zip_label", "ZIP code")
    return f"""<template id="form-tpl">
  <form class="formcard msform" novalidate>
    <h3>{esc(p["form_title"])}</h3>
    <div class="sub">{esc(p["form_sub"])}</div>
    <div class="msbar"><span></span><span></span><span></span></div>
    <div class="hp" aria-hidden="true"><label>Leave this empty<input type="text" name="company" tabindex="-1" autocomplete="off"></label></div>

    <div class="mspanel" data-step="1">
      {step1}
      <div class="err"></div>
      <button type="button" class="btn next">Continue →</button>
    </div>

    <div class="mspanel" data-step="2" hidden>
      {step2}
      <span class="q">{esc(zip_label)}</span>
      <input type="text" name="zip" inputmode="numeric" pattern="[0-9]{{5}}" maxlength="5" placeholder="5-digit ZIP" required>
      <div class="err"></div>
      <div class="msnav"><button type="button" class="btn ghost back">← Back</button><button type="button" class="btn next">Continue →</button></div>
    </div>

    <div class="mspanel" data-step="3" hidden>
      <span class="q">Your name</span>
      <input type="text" name="name" autocomplete="name" placeholder="First and last name" required>
      <div class="grid2">
        <div><span class="q">Mobile number</span><input type="tel" name="phone" autocomplete="tel" placeholder="Mobile number" required></div>
        <div><span class="q">Email (optional)</span><input type="email" name="email" autocomplete="email" placeholder="you@email.com"></div>
      </div>
      <span class="q">Best time to call you</span>
      <div class="taps three">
        <label class="tap"><input type="radio" name="bestTime" value="Morning" required><span>Morning</span></label>
        <label class="tap"><input type="radio" name="bestTime" value="Afternoon"><span>Afternoon</span></label>
        <label class="tap"><input type="radio" name="bestTime" value="Evening"><span>Evening</span></label>
      </div>
      <div class="err"></div>
      <div class="msnav"><button type="button" class="btn ghost back">← Back</button><button type="submit" class="btn">{esc(p["submit"])} →</button></div>
    </div>

    <div class="fineprint">This is an example page. Details sent here go to Marketing In Action's demo sheet, not to a real business.</div>
  </form>
</template>"""


def cards(c):
    icon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>'
    items = "".join(
        f'<div class="card"><div class="ic">{icon}</div><h3>{esc(i["h"])}</h3><p>{esc(i["p"])}</p></div>'
        for i in c["items"]
    )
    return f"""<section class="pad">
  <div class="wrap">
    <div class="center">
      <div class="eyebrow">{esc(c["eyebrow"])}</div>
      <h2>{esc(c["h2"])}</h2>
      <p>{esc(c["p"])}</p>
    </div>
    <div class="cards">{items}</div>
  </div>
</section>"""


def checks(c):
    if not c:
        return ""
    items = "".join(f'<div>{esc(i["h"])}<small>{esc(i["small"])}</small></div>' for i in c["items"])
    return f"""<section class="pad tint">
  <div class="wrap">
    <div class="center">
      <div class="eyebrow">{esc(c["eyebrow"])}</div>
      <h2>{esc(c["h2"])}</h2>
      <p>{esc(c["p"])}</p>
    </div>
    <div class="checks">{items}</div>
  </div>
</section>"""


def steps(s, tinted):
    items = "".join(f'<div class="step"><h3>{esc(i["h"])}</h3><p>{esc(i["p"])}</p></div>' for i in s["items"])
    return f"""<section class="pad{" tint" if tinted else ""}">
  <div class="wrap">
    <div class="center">
      <div class="eyebrow">How it works</div>
      <h2>{esc(s["h2"])}</h2>
    </div>
    <div class="steps">{items}</div>
  </div>
</section>"""


def faq(items):
    return "".join(f"<details><summary>{esc(i['q'])}</summary><p>{esc(i['a'])}</p></details>" for i in items)


def page(p):
    url = f"{SITE}/acquisition/{p['slug']}/example/"
    title = f"{p['title']} | {p['business']} (example page)"
    desc = (
        f"An example customer page for a {p['niche'].lower()} business, built by Marketing In Action. "
        f"{p['business']} is made up."
    )
    pal = p["palette"]
    has_checks = bool(p.get("checks"))
    # Alternate section tints so the page reads in bands whether or not it has a checks section.
    tint_steps = not has_checks
    tint_reviews = has_checks
    tint_faq = not tint_reviews
    mark = p["business"][0]
    ribbon_link = p["offer_page"]
    ribbon_text = "See the offer →" if ribbon_link.endswith("/niches/") else "See the offer for businesses like this →"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow">
<title>{attr(title)}</title>
<meta name="description" content="{attr(desc)}">
<!-- Generated by tools/build-example-pages.py from data/example-pages.json. Edit those, not this file. -->
<!-- Open Graph -->
<meta property="og:type" content="website">
<meta property="og:title" content="{attr(title)}">
<meta property="og:description" content="{attr(desc)}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{SITE}/assets/og-acquisition.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="MIA Acquisition: get more customers, predictably">
<meta property="og:site_name" content="Marketing In Action">
<!-- Twitter -->
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:site" content="@marketinginact">
<meta name="twitter:title" content="{attr(title)}">
<meta name="twitter:description" content="{attr(desc)}">
<meta name="twitter:image" content="{SITE}/assets/og-acquisition.png">
<meta name="twitter:image:alt" content="MIA Acquisition: get more customers, predictably">
<link rel="icon" href="/favicon-32x32.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root{{
    --deep:{pal["deep"]}; --deep-dk:{pal["deep_dk"]}; --accent:{pal["accent"]}; --accent-dk:{pal["accent_dk"]}; --sky:{pal["sky"]};
    --ink:#14212b; --slate:#4d5f6c; --line:#dfe6ea; --white:#fff; --radius:16px;
    --shadow:0 10px 30px rgba(20,33,43,.12); --shadow-sm:0 4px 14px rgba(20,33,43,.09);
    --mia-ink:#100a16; --mia-gold:#f1de71;
  }}
  *{{box-sizing:border-box;margin:0;padding:0}}
  html{{scroll-behavior:smooth}}
  body{{font-family:"Plus Jakarta Sans",system-ui,sans-serif;color:var(--slate);line-height:1.6;background:var(--white);overflow-x:hidden}}
  h1,h2,h3{{color:var(--deep);line-height:1.15;font-weight:800;letter-spacing:-.02em}}
  h2{{font-size:clamp(1.6rem,3.4vw,2.35rem);margin-bottom:.6rem}}
  h3{{font-size:1.12rem;font-weight:700}}
  p{{margin-bottom:1rem}}
  a{{color:inherit;text-decoration:none}}
  .wrap{{max-width:1140px;margin:0 auto;padding:0 16px}}
  .btn{{display:inline-block;background:var(--accent);color:#fff;font-weight:700;font-size:1.02rem;padding:15px 28px;border-radius:999px;box-shadow:var(--shadow-sm);border:none;cursor:pointer;transition:transform .12s ease,background .12s ease;text-align:center;font-family:inherit}}
  .btn:hover{{background:var(--accent-dk);transform:translateY(-2px)}}
  .btn:disabled{{opacity:.7;cursor:default;transform:none}}
  .btn.ghost{{background:color-mix(in srgb,var(--deep) 7%,#fff);color:var(--deep);box-shadow:none}}
  .btn.ghost:hover{{background:color-mix(in srgb,var(--deep) 12%,#fff)}}
  .eyebrow{{color:var(--accent-dk);font-weight:700;text-transform:uppercase;letter-spacing:.08em;font-size:.8rem;margin-bottom:.5rem}}

  .ribbon{{background:var(--mia-ink);color:#f7f4fa;font-size:.84rem;padding:9px 16px;text-align:center;line-height:1.45}}
  .ribbon b{{color:var(--mia-gold)}}
  .ribbon a{{color:var(--mia-gold);text-decoration:underline;white-space:nowrap}}

  header{{position:sticky;top:0;z-index:50;background:rgba(255,255,255,.96);backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}}
  .nav{{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 16px;max-width:1140px;margin:0 auto}}
  .brand{{display:flex;align-items:center;gap:11px;min-width:0}}
  .brand .mark{{flex:none;width:40px;height:40px;border-radius:11px;background:linear-gradient(135deg,var(--deep),var(--accent));display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:1.2rem}}
  .brand b{{color:var(--deep);font-size:1.1rem;font-weight:800;display:block;line-height:1.1}}
  .brand span{{font-size:.74rem;color:var(--slate);font-weight:500}}
  .nav .btn .short{{display:none}}
  @media(max-width:600px){{.brand span{{display:none}}.brand b{{font-size:1rem}}.nav .btn{{padding:10px 16px;font-size:.88rem;white-space:nowrap}}.nav .btn .long{{display:none}}.nav .btn .short{{display:inline}}}}

  .hero{{background:linear-gradient(180deg,var(--sky) 0%,#fff 100%)}}
  .hero .inner{{max-width:640px;margin:0 auto;padding:44px 16px 56px;text-align:center}}
  .hero h1{{font-size:clamp(1.9rem,5vw,2.9rem);margin-bottom:.8rem}}
  .hero .lead{{font-size:1.08rem;margin:0 auto 1.6rem;max-width:44ch}}
  .hero .formcard{{text-align:left}}
  .trust{{display:flex;justify-content:center;flex-wrap:wrap;gap:8px 18px;margin-top:1.1rem;font-size:.86rem;font-weight:600;color:var(--deep)}}

  .formcard{{background:#fff;border-radius:var(--radius);box-shadow:var(--shadow);padding:24px;color:var(--slate);border:1px solid var(--line)}}
  .formcard h3{{color:var(--deep);font-size:1.25rem;margin-bottom:.2rem}}
  .formcard .sub{{font-size:.9rem;margin-bottom:.9rem}}
  .formcard .q{{display:block;font-size:.88rem;font-weight:700;color:var(--ink);margin:.9rem 0 .45rem}}
  .formcard .mspanel > .q:first-child{{margin-top:.1rem}}
  .formcard input[type=text],.formcard input[type=tel],.formcard input[type=email]{{width:100%;padding:12px 13px;border:1.5px solid var(--line);border-radius:10px;font-family:inherit;font-size:1rem;color:var(--ink);background:#fbfcfd}}
  .formcard input:focus{{outline:none;border-color:var(--accent);background:#fff}}
  .formcard .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
  @media(max-width:420px){{.formcard .grid2{{grid-template-columns:1fr}}}}
  .hp{{position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden}}
  .taps{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}
  .taps.three{{grid-template-columns:repeat(3,1fr)}}
  .tap{{position:relative}}
  .tap input{{position:absolute;opacity:0;pointer-events:none}}
  .tap span{{display:flex;align-items:center;justify-content:center;text-align:center;min-height:48px;height:100%;padding:9px 10px;border:1.5px solid var(--line);border-radius:11px;font-size:.88rem;font-weight:600;color:var(--ink);background:#fbfcfd;cursor:pointer;line-height:1.25;transition:border-color .12s,background .12s}}
  .tap input:checked + span{{border-color:var(--accent);background:color-mix(in srgb,var(--accent) 12%,#fff);color:var(--deep)}}
  .tap input:focus-visible + span{{outline:2px solid var(--accent);outline-offset:2px}}
  .tap.wide{{grid-column:1 / -1}}
  .fineprint{{font-size:.75rem;color:#7b8b96;text-align:center;margin-top:.9rem}}
  .msbar{{display:flex;gap:6px;margin-bottom:1rem}}
  .msbar span{{height:5px;flex:1;background:color-mix(in srgb,var(--deep) 10%,#fff);border-radius:3px;transition:background .2s}}
  .msbar span.on{{background:var(--accent)}}
  .mspanel .next,.mspanel button[type="submit"]{{width:100%}}
  .mspanel .next{{margin-top:14px}}
  .msnav{{display:flex;gap:10px;margin-top:14px}}
  .msnav .btn{{flex:1;padding:13px 14px;font-size:.96rem}}
  .msnav .next{{margin-top:0}}
  .err{{color:#b3261e;font-size:.82rem;font-weight:600;margin-top:.5rem;min-height:1.1em}}
  .thanks{{text-align:center;padding:16px 4px}}
  .thanks-ic{{width:60px;height:60px;border-radius:50%;background:color-mix(in srgb,var(--accent) 14%,#fff);color:var(--accent-dk);display:flex;align-items:center;justify-content:center;font-size:1.9rem;margin:0 auto 14px}}
  .thanks h3{{font-size:1.4rem;margin-bottom:.5rem}}
  .thanks .muted{{font-size:.85rem;color:#7b8b96;margin-top:.5rem}}

  section.pad{{padding:64px 0}}
  .tint{{background:var(--sky)}}
  .center{{text-align:center;max-width:720px;margin:0 auto 40px}}
  .cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}}
  @media(max-width:820px){{.cards{{grid-template-columns:1fr 1fr}}}}
  @media(max-width:520px){{.cards{{grid-template-columns:1fr}}}}
  .card{{background:#fff;border:1px solid var(--line);border-radius:var(--radius);padding:22px;box-shadow:var(--shadow-sm)}}
  .card .ic{{width:40px;height:40px;border-radius:11px;background:var(--sky);display:flex;align-items:center;justify-content:center;margin-bottom:12px}}
  .card .ic svg{{width:22px;height:22px;color:var(--accent-dk)}}
  .card h3{{margin-bottom:.3rem}}
  .card p{{font-size:.94rem;margin:0}}
  .checks{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;max-width:860px;margin:0 auto}}
  @media(max-width:700px){{.checks{{grid-template-columns:1fr 1fr}}}}
  .checks div{{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px 16px;font-weight:700;color:var(--deep);font-size:.95rem}}
  .checks div small{{display:block;font-weight:500;color:var(--slate);font-size:.82rem}}
  .steps{{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;counter-reset:s}}
  @media(max-width:820px){{.steps{{grid-template-columns:1fr;gap:30px}}}}
  .step{{position:relative;background:#fff;border-radius:var(--radius);padding:30px 24px 24px;box-shadow:var(--shadow-sm);border:1px solid var(--line)}}
  .step::before{{counter-increment:s;content:counter(s);position:absolute;top:-18px;left:24px;width:42px;height:42px;background:var(--accent);color:#fff;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:1.15rem}}
  .step h3{{margin:.5rem 0 .3rem}}
  .step p{{font-size:.95rem;margin:0}}
  .reviews{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}}
  @media(max-width:820px){{.reviews{{grid-template-columns:1fr}}}}
  .slot{{border:2px dashed color-mix(in srgb,var(--deep) 22%,#fff);border-radius:var(--radius);padding:24px;background:#fff;color:#7b8b96;font-size:.92rem}}
  .slot .stars{{color:#f5a623;font-size:1.05rem;margin-bottom:.4rem}}
  .faq{{max-width:760px;margin:0 auto}}
  .faq details{{background:#fff;border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin-bottom:10px}}
  .faq summary{{cursor:pointer;font-weight:700;color:var(--deep);list-style:none;display:flex;justify-content:space-between;gap:12px}}
  .faq summary::-webkit-details-marker{{display:none}}
  .faq summary::after{{content:"+";font-size:1.3rem;line-height:1;color:var(--accent-dk)}}
  .faq details[open] summary::after{{content:"–"}}
  .faq details p{{margin:.7rem 0 0;font-size:.96rem}}
  footer{{background:var(--ink);color:#b9c4cc;padding:40px 0 24px;font-size:.9rem}}
  footer .cols{{display:grid;grid-template-columns:2fr 1fr;gap:28px;margin-bottom:22px}}
  @media(max-width:700px){{footer .cols{{grid-template-columns:1fr}}}}
  footer b{{color:#fff;display:block;margin-bottom:.4rem}}
  .legal{{border-top:1px solid rgba(255,255,255,.12);padding-top:16px;font-size:.78rem;color:#8a98a3;text-align:center}}
  .legal a{{text-decoration:underline}}
</style>
</head>
<body>

<div class="ribbon"><b>Example page by Marketing In Action.</b> {esc(p["business"])} is made up. This is the page your customers would see. <a href="{ribbon_link}">{ribbon_text}</a></div>

<header>
  <div class="nav">
    <div class="brand">
      <div class="mark" aria-hidden="true">{esc(mark)}</div>
      <div><b>{esc(p["business"])}</b><span>{esc(p["tagline"])} · {CITY}</span></div>
    </div>
    <a class="btn" href="#book"><span class="long">{esc(p["cta_long"])}</span><span class="short">{esc(p["cta_short"])}</span></a>
  </div>
</header>

<section class="hero">
  <div class="inner">
    <div class="eyebrow">{esc(p["eyebrow"])} · {CITY}</div>
    <h1>{esc(p["h1"])}</h1>
    <p class="lead">{esc(p["lead"])}</p>
    <div data-form></div>
    <div class="trust">{"".join(f"<span>✓ {esc(t)}</span>" for t in p["trust"])}</div>
  </div>
</section>

{cards(p["cards"])}

{checks(p.get("checks"))}

{steps(p["steps"], tint_steps)}

<section class="pad{" tint" if tint_reviews else ""}">
  <div class="wrap">
    <div class="center">
      <div class="eyebrow">Reviews</div>
      <h2>What your neighbors say</h2>
      <p>On a real page, this section shows the business's own Google reviews.</p>
    </div>
    <div class="reviews">
      <div class="slot"><div class="stars">★★★★★</div>A real Google review goes here, with the customer's first name and town.</div>
      <div class="slot"><div class="stars">★★★★★</div>A real Google review goes here, with the customer's first name and town.</div>
      <div class="slot"><div class="stars">★★★★★</div>A real Google review goes here, with the customer's first name and town.</div>
    </div>
  </div>
</section>

<section class="pad{" tint" if tint_faq else ""}">
  <div class="wrap">
    <div class="center"><div class="eyebrow">Questions</div><h2>Before you book</h2></div>
    <div class="faq">{faq(p["faq"])}</div>
  </div>
</section>

<section class="pad{"" if tint_faq else " tint"}" id="book">
  <div class="wrap">
    <div class="center" style="margin-bottom:24px"><div class="eyebrow">{esc(p["eyebrow"])}</div><h2>{esc(p["book"]["h2"])}</h2><p>{esc(p["book"]["p"])}</p></div>
    <div style="max-width:520px;margin:0 auto" data-form></div>
  </div>
</section>

<footer>
  <div class="wrap">
    <div class="cols">
      <div><b>{esc(p["business"])}</b>{esc(p["footer"])} This business is made up for an example page.</div>
      <div><b>Book</b><a href="#book">{esc(p["cta_long"])}</a></div>
    </div>
    <div class="legal">Example page built by <a href="{ribbon_link}">Marketing In Action</a> to show local businesses what their customer page could look like.</div>
  </div>
</footer>

{form(p)}

<script>
  // Demo backend: the Apps Script web app behind the "Demo submissions" tab of the
  // MIA Acquisition View Leads sheet (tools/example-pages-apps-script.gs).
  var ENDPOINT = {json.dumps(ENDPOINT)};
  var NICHE = {json.dumps(p["niche"])};
  var BUSINESS = {json.dumps(p["business"])};

  var q = new URLSearchParams(location.search);
  var city = (q.get('city') || '').trim().slice(0, 40);
  if (city) document.querySelectorAll('[data-city]').forEach(function(el){{ el.textContent = city; }});

  var tpl = document.getElementById('form-tpl');
  document.querySelectorAll('[data-form]').forEach(function(slot){{ slot.appendChild(tpl.content.cloneNode(true)); }});

  document.querySelectorAll('.msform').forEach(function(form){{
    var panels = Array.prototype.slice.call(form.querySelectorAll('.mspanel'));
    var dots = form.querySelectorAll('.msbar span');
    var cur = 0;
    function show(i){{
      panels.forEach(function(p, idx){{ p.hidden = idx !== i; }});
      dots.forEach(function(d, idx){{ d.classList.toggle('on', idx <= i); }});
      cur = i;
    }}
    function validPanel(){{
      var p = panels[cur], err = p.querySelector('.err'), seen = {{}};
      var fields = p.querySelectorAll('[required]');
      for (var k = 0; k < fields.length; k++){{
        var f = fields[k];
        if (f.type === 'radio'){{
          if (seen[f.name]) continue; seen[f.name] = 1;
          if (!form.querySelector('input[name="' + f.name + '"]:checked')){{ err.textContent = 'Please pick one answer for each question.'; return false; }}
        }} else if (!f.value.trim() || !f.checkValidity()){{
          err.textContent = f.name === 'zip' ? 'Please enter a 5-digit ZIP code.' : 'Please fill in your name and mobile number.';
          f.focus(); return false;
        }}
      }}
      err.textContent = '';
      return true;
    }}
    form.querySelectorAll('.next').forEach(function(b){{ b.addEventListener('click', function(){{ if (validPanel()) show(Math.min(cur + 1, panels.length - 1)); }}); }});
    form.querySelectorAll('.back').forEach(function(b){{ b.addEventListener('click', function(){{ show(Math.max(cur - 1, 0)); }}); }});
    form.addEventListener('submit', function(ev){{
      ev.preventDefault();
      if (!validPanel()) return;
      var btn = form.querySelector('button[type="submit"]');
      btn.disabled = true; btn.textContent = 'Sending…';
      var fd = new FormData(form), data = {{}};
      fd.forEach(function(val, key){{ data[key] = val; }});
      for (var i = 1; i <= 4; i++){{
        if (data['a' + i]) data['answer' + i] = data['a' + i + 'Label'] + ': ' + data['a' + i];
        delete data['a' + i]; delete data['a' + i + 'Label'];
      }}
      data.niche = NICHE;
      data.business = BUSINESS;
      data.city = city;
      data.pageUrl = location.href;
      data.utmSource = q.get('utm_source') || '';
      data.utmMedium = q.get('utm_medium') || '';
      data.utmCampaign = q.get('utm_campaign') || '';
      var done = function(){{ thanks(form, data.name); }};
      if (!ENDPOINT || data.company) return done();
      fetch(ENDPOINT, {{method:'POST', mode:'no-cors', headers:{{'Content-Type':'text/plain;charset=utf-8'}}, body: JSON.stringify(data)}})
        .catch(function(){{}}).finally(done);
    }});
    show(0);
  }});

  function thanks(form, name){{
    var first = name ? name.trim().split(' ')[0].replace(/[<>&"']/g, '') : '';
    form.innerHTML = '<div class="thanks"><div class="thanks-ic">&#10003;</div>' +
      '<h3>Thanks' + (first ? ', ' + first : '') + '. You\\'re on the list.</h3>' +
      '<p>' + {json.dumps(html.escape(p["thanks"], quote=False))} + '</p>' +
      '<p class="muted">On a real page, the business gets this request by email and text the moment it arrives.</p></div>';
    form.scrollIntoView({{behavior:'smooth', block:'center'}});
  }}
</script>
</body>
</html>
"""


REQUIRED = ["slug", "niche", "offer_page", "business", "tagline", "palette", "title", "cta_long", "cta_short",
            "eyebrow", "h1", "lead", "trust", "form_title", "form_sub", "questions", "submit", "thanks",
            "cards", "steps", "faq", "book", "footer"]


def validate(p):
    missing = [k for k in REQUIRED if k not in p]
    if missing:
        return f"{p.get('slug', '?')}: missing {', '.join(missing)}"
    if not 3 <= len(p["questions"]) <= 4:
        return f"{p['slug']}: needs 3 or 4 questions"
    if len(p["cards"]["items"]) != 6 or len(p["steps"]["items"]) != 3 or len(p["trust"]) != 3:
        return f"{p['slug']}: needs 6 cards, 3 steps and 3 trust points"
    if not re.fullmatch(r"[a-z0-9-]+", p["slug"]):
        return f"{p['slug']}: bad slug"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="fail if any page differs from the data file")
    args = ap.parse_args()
    pages = json.loads(DATA.read_text(encoding="utf-8"))
    errors, stale = [], []
    for p in pages:
        err = validate(p)
        if err:
            errors.append(err)
            continue
        out = ROOT / "acquisition" / p["slug"] / "example" / "index.html"
        text = page(p)
        if args.check:
            if not out.is_file() or out.read_text(encoding="utf-8") != text:
                stale.append(str(out.relative_to(ROOT)))
        else:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
    for e in errors:
        print("ERROR", e)
    for s in stale:
        print("STALE", s)
    if errors or stale:
        return 1
    print(f"{len(pages)} example page(s) {'up to date' if args.check else 'written'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
