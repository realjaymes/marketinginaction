#!/usr/bin/env python3
"""Record how a host serves marketinginaction.xyz, and compare two hosts.

Built to prove the move from Netlify to Cloudflare Pages changes nothing a visitor or a
search engine sees. It requests, without following redirects:
  - every rule in _redirects, with a sample path for each wildcard and a query string,
    so old Substack links (/p/..., /newsletters, /about ...) are checked one by one
  - every page in sitemap-main.xml, with and without its trailing slash
  - a missing page (must be a real 404, not the home page)
  - on the live domain only: www and http variants
and records the status code and the redirect target.

  check-hosting.py record https://marketinginaction.xyz baseline.json
  check-hosting.py record https://<project>.pages.dev preview.json
  check-hosting.py compare baseline.json preview.json
compare treats the two hosts as the same site, so a redirect to /x/ on either host matches,
and lists every difference. Exit code 1 when anything differs.
"""
import json
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIVE = "marketinginaction.xyz"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "mia-hosting-check/1.0"}, method="GET")
    try:
        with OPENER.open(req, timeout=30) as r:
            body = r.read(4000).decode("utf-8", "ignore")
            return r.status, "", body
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read(4000).decode("utf-8", "ignore")
        except Exception:
            pass
        return e.code, e.headers.get("Location", ""), body
    except Exception as e:
        return 0, f"error: {e}", ""


def paths():
    out = []
    for line in (ROOT / "_redirects").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        src = line.split()[0]
        if src.endswith("/*"):
            base = src[:-1]
            out += [base + "sample-post", base + "sample-post?utm_source=check&x=1"]
        else:
            out += [src, src + "?utm_source=check"]
    for loc in re.findall(r"<loc>([^<]+)</loc>", (ROOT / "sitemap-main.xml").read_text()):
        p = urllib.parse.urlparse(loc).path or "/"
        out.append(p)
        if p != "/" and p.endswith("/"):
            out.append(p.rstrip("/"))
    out += ["/this-page-does-not-exist-404-check", "/404.html", "/robots.txt", "/sitemap.xml", "/llms.txt"]
    seen, uniq = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def title(body):
    m = re.search(r"<title>(.*?)</title>", body, re.S | re.I)
    return m.group(1).strip()[:80] if m else ""


def record(base, outfile):
    base = base.rstrip("/")
    host = urllib.parse.urlparse(base).netloc
    res = {}
    targets = paths()
    for p in targets:
        status, loc, body = fetch(base + p)
        res[p] = {"status": status, "location": loc, "title": title(body) if status == 200 else ""}
    if host == LIVE:
        for u in ["https://www.marketinginaction.xyz/", "https://www.marketinginaction.xyz/consulting/",
                  "http://marketinginaction.xyz/", "http://marketinginaction.xyz/consulting/",
                  "http://www.marketinginaction.xyz/"]:
            status, loc, _ = fetch(u)
            res["@" + u] = {"status": status, "location": loc, "title": ""}
    pathlib.Path(outfile).write_text(json.dumps({"base": base, "results": res}, indent=1))
    bad = sum(1 for v in res.values() if v["status"] == 0)
    print(f"recorded {len(res)} requests from {base} into {outfile}" + (f", {bad} failed to connect" if bad else ""))


def norm(loc, base):
    """A redirect target with this host removed, so two hosts compare as one site."""
    host = urllib.parse.urlparse(base).netloc
    for h in (host, LIVE):
        for scheme in ("https://", "http://"):
            if loc.startswith(scheme + h):
                return loc[len(scheme + h):] or "/"
    return loc


def compare(a_file, b_file):
    a, b = json.loads(pathlib.Path(a_file).read_text()), json.loads(pathlib.Path(b_file).read_text())
    diffs = []
    for p, ra in a["results"].items():
        if p.startswith("@") and p not in b["results"]:
            continue
        rb = b["results"].get(p)
        if not rb:
            diffs.append(f"{p}: missing from {b_file}")
            continue
        la, lb = norm(ra["location"], a["base"]), norm(rb["location"], b["base"])
        if ra["status"] != rb["status"] or la != lb:
            diffs.append(f"{p}: {ra['status']} {la}  vs  {rb['status']} {lb}")
        elif ra["title"] != rb["title"]:
            diffs.append(f"{p}: page title differs: {ra['title']!r} vs {rb['title']!r}")
    print(f"compared {len(a['results'])} requests: {len(diffs)} differences")
    for d in diffs:
        print("  " + d)
    return 1 if diffs else 0


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "record":
        record(sys.argv[2], sys.argv[3])
    elif len(sys.argv) == 4 and sys.argv[1] == "compare":
        sys.exit(compare(sys.argv[2], sys.argv[3]))
    else:
        sys.exit(__doc__)
