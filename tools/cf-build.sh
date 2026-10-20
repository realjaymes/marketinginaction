#!/usr/bin/env bash
# Cloudflare Pages build for marketinginaction.xyz. It runs the same checks as the
# pre-push hook and the GitHub Pages workflow; keep the three lists in step. A failed
# check fails the build, and Cloudflare keeps the last good deploy live.
set -e
# Full git history, so the sitemap dates each page from its last commit.
if [ "$(git rev-parse --is-shallow-repository 2>/dev/null)" = "true" ]; then git fetch --unshallow --quiet || true; fi
python3 tools/verify-calculators.py
python3 tools/check-wording.py
python3 tools/check-og.py
# The ad-bridge check joins the build the day its script is committed.
if [ -f tools/check-bridges.py ]; then python3 tools/check-bridges.py; fi
python3 tools/dime-proof.py
python3 tools/generate-sitemap.py --base-url https://marketinginaction.xyz/ --output sitemap-main.xml
