#!/usr/bin/env python3
"""Write a complete, consistent Open Graph and Twitter block into every page.

Why this exists
---------------
By October 2026, 63 of 121 pages shipped no social tags at all (every acquisition
page, every thank-you page, every /go/ bridge page), and 40 more pointed at
``og-image.png``, a 512x512 square that ``summary_large_image`` crops badly. Pages
are cloned by hand, so tags drift with each clone. This script rewrites the block
from one set of rules, and ``tools/check-og.py`` enforces the result at deploy.

Rules
-----
* **Copy.** A page's existing ``og:title`` and ``og:description`` are kept, since
  most are deliberate social copy. A page with none takes its ``<title>`` and
  meta description.
* **Borrowed copy.** Pages whose own copy makes a poor preview borrow it:
  thank-you pages take their sales page's tags and point ``og:url`` at it, so a
  shared receipt link previews the offer; ``/go/`` bridge pages take their
  offer's copy but keep their own URL; ``404.html`` takes the homepage's.
* **Image.** One 1200x630 image per section, chosen by path in ``IMAGES``. A page
  already using a 1200x630 image from that list keeps it.
* **URL.** ``og:url`` is the canonical URL, or the page's own URL when it has none.

Run it after adding pages, then commit the result::

    python3 tools/og-tags.py
"""
import html
import pathlib
import re
import sys
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = "https://marketinginaction.xyz/"
SITE_NAME = "Marketing In Action"
TWITTER_SITE = "@marketinginact"

# First match wins. Paths are relative to the repo root, with a trailing slash.
IMAGES = [
    (r"^$", "assets/og-homepage.png", "Marketing In Action: put marketing into action, unlock revenue"),
    (r"^consulting/", "assets/og-consulting.png", "MIA GTM: Go-To-Market Systems for tech companies and agencies"),
    (r"^acquisition/", "assets/og-acquisition.png", "MIA Acquisition: get more customers, predictably"),
    (r"^(academy/dime|go/dime)", "assets/og-dime.png", "DIME by MIA Academy: Digital Income Made Easy"),
    (r"^(academy/pro-bootcamp|go/pro-bootcamp)/", "assets/og-pro-bootcamp.png", "Product & Growth Marketing with AI Bootcamp by MIA Academy"),
    (r"^(academy/sme/|go/)", "assets/og-sme.png", "MIA Academy for business owners: Online Marketing Simplified"),
    (r"^academy/", "assets/og-academy.png", "MIA Academy: Marketing Simplified"),
    (r"", "assets/og-homepage.png", "Marketing In Action: put marketing into action, unlock revenue"),
]

# Social titles that no longer describe the page. Applied over whatever is there.
OVERRIDES = {
    "services/": {"og:title": "Marketing Services: Go-To-Market Systems & Paid Acquisition | MIA"},
}

GO_OFFERS = {
    "bundle": "academy/sme/bundle/", "consulting": "academy/sme/consulting/",
    "dime-class": "academy/dime/class/", "dime-masterclass": "academy/dime-masterclass/",
    "meta-ads": "academy/sme/meta-ads/", "pro-bootcamp": "academy/pro-bootcamp/",
    "safety-net": "academy/sme/safety-net/", "target-buyer": "academy/sme/target-buyer/",
    "targeting-setup": "academy/sme/targeting-setup/", "tiktok-ads": "academy/sme/tiktok-ads/",
}

SOCIAL_META = re.compile(
    r'[ \t]*<meta\b[^>]*\b(?:property|name)=["\'](?:og|twitter):[^"\']*["\'][^>]*>[ \t]*\n?', re.I)
SOCIAL_COMMENT = re.compile(r"[ \t]*<!--\s*(?:Open Graph|Twitter)\s*-->[ \t]*\n?", re.I)


class Head(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta, self.title, self.canonical = {}, None, None
        self._in_title = self._done = False

    def handle_starttag(self, tag, attrs):
        if self._done:
            return
        a = dict(attrs)
        if tag == "meta":
            key = a.get("property") or a.get("name")
            if key and key not in self.meta:
                self.meta[key] = a.get("content") or ""
        elif tag == "link" and (a.get("rel") or "").lower() == "canonical":
            self.canonical = a.get("href")
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "head":
            self._done = True

    def handle_data(self, data):
        if self._in_title and self.title is None:
            self.title = data.strip()


def rel(page: pathlib.Path) -> str:
    """Site path with a trailing slash: '' for the homepage, '404.html' for the 404."""
    r = page.relative_to(ROOT).as_posix()
    return r[: -len("index.html")] if r.endswith("index.html") else r


def parse(page: pathlib.Path) -> Head:
    h = Head()
    h.feed(page.read_text(errors="ignore").split("</head>")[0] + "</head>")
    return h


def image_for(path: str, current: str):
    for pattern, img, alt in IMAGES:
        if re.search(pattern, path):
            chosen = (img, alt)
            break
    # Keep a page's own section image when it is already one of the 1200x630 set.
    for _, img, alt in IMAGES:
        if current == BASE + img:
            return img, alt
    return chosen


def attr(v: str) -> str:
    return v.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def desired(page: pathlib.Path) -> dict:
    path = rel(page)
    own = parse(page)
    src, url = own, None

    if path.endswith("thank-you/"):
        parent = path[: -len("thank-you/")]
        src, url = parse(ROOT / parent / "index.html"), BASE + parent
    elif path.startswith("go/"):
        src = parse(ROOT / GO_OFFERS[path.split("/")[1]] / "index.html")
    elif path == "404.html":
        src, url = parse(ROOT / "index.html"), BASE

    m = src.meta
    title = m.get("og:title") or src.title
    desc = m.get("og:description") or m.get("description")
    if src is own:
        url = m.get("og:url") or own.canonical or BASE + path
    elif url is None:
        url = own.canonical or BASE + path
    img, alt = image_for(path, m.get("og:image", ""))
    tags = {
        "og:type": own.meta.get("og:type") or "website",
        "og:title": title,
        "og:description": desc,
        "og:url": url,
        "og:image": BASE + img,
        "og:image:width": "1200",
        "og:image:height": "630",
        "og:image:alt": alt,
        "og:site_name": SITE_NAME,
        "twitter:card": "summary_large_image",
        "twitter:site": TWITTER_SITE,
        "twitter:title": m.get("twitter:title") or title,
        "twitter:description": m.get("twitter:description") or desc,
        "twitter:image": BASE + img,
        "twitter:image:alt": alt,
    }
    for k, v in OVERRIDES.get(path, {}).items():
        tags[k] = v
        tags["twitter:" + k.split(":", 1)[1]] = v
    missing = [k for k, v in tags.items() if not v]
    if missing:
        raise SystemExit(f"{path or '/'}: no source for {missing}")
    return tags


def write(page: pathlib.Path, tags: dict) -> bool:
    text = page.read_text()
    head, sep, body = text.partition("</head>")
    close = " />" if re.search(r"<meta[^>]*/>", head) else ">"
    indent = re.search(r"\n([ \t]*)<title>", head)
    pad = indent.group(1) if indent else "    "

    first = SOCIAL_META.search(head)
    stripped = SOCIAL_COMMENT.sub("", SOCIAL_META.sub("", head))
    if first:
        at = len(SOCIAL_COMMENT.sub("", SOCIAL_META.sub("", head[: first.start()])))
    else:
        anchor = re.search(r'<meta[^>]*name=["\']description["\'][^>]*>[ \t]*\n', stripped) \
            or re.search(r"</title>[ \t]*\n", stripped)
        at = anchor.end()

    def line(k, v):
        kind = "name" if k.startswith("twitter:") else "property"
        return f'{pad}<meta {kind}="{k}" content="{attr(v)}"{close}\n'

    og = "".join(line(k, v) for k, v in tags.items() if k.startswith("og:"))
    tw = "".join(line(k, v) for k, v in tags.items() if k.startswith("twitter:"))
    block = f"{pad}<!-- Open Graph -->\n{og}{pad}<!-- Twitter -->\n{tw}"
    new = stripped[:at] + block + stripped[at:] + sep + body
    if new != text:
        page.write_text(new)
        return True
    return False


def main() -> int:
    pages = sorted(p for p in ROOT.rglob("*.html") if ".git" not in p.parts and "node_modules" not in p.parts)
    # Pages that borrow copy read their source after it has been written.
    borrowed = lambda p: rel(p).endswith("thank-you/") or rel(p).startswith("go/") or rel(p) == "404.html"
    changed = 0
    for page in [p for p in pages if not borrowed(p)] + [p for p in pages if borrowed(p)]:
        changed += write(page, desired(page))
    print(f"{len(pages)} pages checked, {changed} updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
