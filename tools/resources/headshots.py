#!/usr/bin/env python3
"""Fetch the thought leaders' headshots and save them into the site.

Each person's photo is their public X profile picture, read through the
fxtwitter API (api.fxtwitter.com), which needs no login. A person whose X name
does not match their name on file is flagged for a manual check and gets no
photo until the "x" link is fixed or "headshot" is set by hand. People with no
X account keep their initials unless a "headshot_url" is set in the data.

Photos are saved as resources/marketing-thought-leaders/img/<slug>.jpg at
240px, and the data file records "headshot" (the site path) and
"headshot_source". A contact sheet for a visual check is written to the system temp
folder (its path is printed), never into the site.

Usage:
  python3 tools/resources/headshots.py            fetch missing photos
  python3 tools/resources/headshots.py --refresh  fetch every photo again
Then run tools/resources/build.py --write.

Vault: AI Workflows/MIA Resources from Notion — Build Plan.
"""
import argparse, json, pathlib, re, subprocess, sys, tempfile, time, unicodedata, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = ROOT / "data/resources/thought-leaders.json"
IMG = ROOT / "resources/marketing-thought-leaders/img"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh) MIA-resources-headshots"}


def get(url, timeout=25):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def handle(x):
    m = re.search(r"(?:x|twitter)\.com/(?:#!/)?@?([A-Za-z0-9_]{1,15})", x or "")
    return m.group(1) if m else None


def plain(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return set(re.findall(r"[a-z]{2,}", s))


def save_jpeg(raw, out):
    with tempfile.NamedTemporaryFile(suffix=".img") as t:
        t.write(raw)
        t.flush()
        subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "82", "-Z", "240", t.name, "--out", str(out)],
                       check=True, capture_output=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    d = json.loads(DATA.read_text(encoding="utf-8"))
    IMG.mkdir(parents=True, exist_ok=True)
    flagged = []
    for i in d["items"]:
        out = IMG / f"{i['slug']}.jpg"
        if out.exists() and i.get("headshot") and not args.refresh:
            continue
        src, url = None, i.get("headshot_url")
        if url:
            src = "headshot_url"
        elif handle(i.get("x")):
            h = handle(i["x"])
            time.sleep(7)  # fxtwitter answers 404 when called too fast
            try:
                u = json.loads(get(f"https://api.fxtwitter.com/{h}")).get("user") or {}
            except Exception as e:
                flagged.append(f"{i['name']}: X lookup failed for @{h} ({e})")
                continue
            if not u.get("avatar_url") or "default_profile" in u["avatar_url"]:
                flagged.append(f"{i['name']}: @{h} has no profile photo")
                continue
            if not (plain(u.get("name")) & plain(i["name"])) and not i.get("x_verified"):
                flagged.append(f"{i['name']}: @{h} is named '{u.get('name')}', check the link, then set x_verified: true")
                continue
            url = re.sub(r"_normal(\.\w+)$", r"_400x400\1", u["avatar_url"])
            src = f"x:@{h}"
        if not url:
            flagged.append(f"{i['name']}: no X account, keeps initials")
            continue
        try:
            save_jpeg(get(url), out)
        except Exception as e:
            flagged.append(f"{i['name']}: download failed ({e})")
            continue
        i["headshot"] = f"img/{i['slug']}.jpg"
        i["headshot_source"] = src
        print(f"saved {out.relative_to(ROOT)} from {src}")
    DATA.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    cells = "".join(f'<figure><img src="{i["slug"]}.jpg" width="120" height="120"><figcaption>{i["name"]}</figcaption></figure>'
                    for i in d["items"] if i.get("headshot"))
    sheet = pathlib.Path(tempfile.gettempdir()) / "mia-headshots-sheet.html"
    sheet.write_text(f"<!doctype html><meta charset=utf-8><meta name=robots content=noindex><style>body{{font:13px system-ui;display:flex;flex-wrap:wrap;gap:12px}}figure{{margin:0;width:120px;text-align:center}}img{{border-radius:50%;object-fit:cover}}</style>{cells}".replace('src="', f'src="{IMG.as_uri()}/'), encoding="utf-8")
    print(f"contact sheet: {sheet}")
    for f in flagged:
        print("check:", f)
    print(f"{sum(bool(i.get('headshot')) for i in d['items'])} of {len(d['items'])} people have a photo")


if __name__ == "__main__":
    sys.exit(main())
