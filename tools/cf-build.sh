#!/usr/bin/env bash
# Cloudflare Pages build for marketinginaction.xyz. Cloudflare Pages runs this on every
# push (build command: bash tools/cf-build.sh, output directory: .). A failed check fails
# the build, and Cloudflare keeps the last good deploy live. The GitHub Actions workflow
# and the pre-push hook run the same checks; keep the three lists in step.
set -e
# Full git history, so the sitemap dates each page from its last commit.
if [ "$(git rev-parse --is-shallow-repository 2>/dev/null)" = "true" ]; then git fetch --unshallow --quiet || true; fi
python3 tools/verify-calculators.py
python3 tools/check-wording.py
python3 tools/check-og.py
python3 tools/dime-proof.py
python3 tools/generate-sitemap.py --base-url https://marketinginaction.xyz/ --output sitemap-main.xml
