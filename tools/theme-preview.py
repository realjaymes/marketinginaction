#!/usr/bin/env python3
"""Preview a site-wide theme on every MIA page without editing any page.

Serves the repo like ``python3 -m http.server`` and, for every HTML page, adds
the fonts plus ``_theme/<theme>-base.css`` and the stylesheet for that page's
template family just before ``</head>``. Real pages on disk never change, so a
theme can be judged across the whole site and then dropped or shipped.

    python3 tools/theme-preview.py            # http://localhost:8003
    add ?theme=off to any URL to see the page as it ships today
    add ?hero=gold to see heroes in the soft gold of Option C instead of cream

Families (the same split the theme files follow):
    bridge          go/*
    thank-you       */thank-you/*, */confirmed*
    sales-template  academy offer pages (hero__headline + announcement-bar)
    styles-css      pages on /styles.css (home of academy, acquisition, consulting, case studies)
    other-inline    homepage and resource tools with their own inline styles
"""
import http.server
import pathlib
import socketserver
import sys
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
THEME = "mono"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8003
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=Nunito+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">')


def family(rel, html):
    if rel.startswith("go/"):
        return "bridge"
    if "/thank-you/" in rel or "/confirmed" in rel:
        return "thank-you"
    if "hero__headline" in html and "announcement-bar" in html:
        return "sales-template"
    if "/styles.css" in html:
        return "styles-css"
    return "other-inline"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        if "theme=off" in url.query:
            return super().do_GET()
        path = pathlib.Path(self.translate_path(url.path))
        if path.is_dir():
            path = path / "index.html"
        if path.suffix != ".html" or not path.exists():
            return super().do_GET()
        rel = path.relative_to(ROOT).as_posix()
        html = path.read_text(errors="ignore")
        fam = family(rel, html)
        tags = (FONTS + f'<link rel="stylesheet" href="/_theme/{THEME}-base.css">'
                f'<link rel="stylesheet" href="/_theme/{THEME}-{fam}.css">'
                f'<meta name="theme-family" content="{fam}">')
        if "hero=gold" in url.query:
            tags += f'<link rel="stylesheet" href="/_theme/{THEME}-hero-gold.css">'
        i = html.lower().rfind("</head>")
        html = html[:i] + tags + html[i:] if i != -1 else tags + html
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), Handler) as srv:
        print(f"Theme preview ({THEME}) on http://localhost:{PORT}  (add ?theme=off for the original)")
        srv.serve_forever()
