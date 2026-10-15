# MIA website: working notes for Claude Code

The project notes, status log and lessons live in James's Obsidian vault: `Areas/Work/AI Workflows/MIA Website (Claude Code Build and Maintenance).md`, with page-level notes in `Areas/Work/MIA/Website/`. Read that note before starting, and add a Status Log line to it at the end of every build session.

Netlify serves the live site. `netlify.toml` runs the checks in `tools/` on every build, and the pre-push hook in `.githooks/` runs the same checks (enable it with `git config core.hooksPath .githooks`). Preview locally with `python3 -m http.server 8000`.

## DIME proof figures

James's Selar figures (sales count, naira total, currencies, milestones, best month, top product, ROAS) and the screenshots behind them live in one file, `data/dime-proof.json`. Seven DIME pages read from it: the sales page, Masterclass, Done-For-You, both replay pages and both class pages. Never type one of these figures straight into a page. Wrap text figures in `<span data-proof="key">`, give proof images `data-proof-img` plus a `data-proof-alt="... {key} ..."` template, and keep every proof screenshot in `academy/dime/assets/` (the Masterclass and Done-For-You pages use that folder too).

To update after a new milestone: James drops the new screenshot into `~/Downloads/Screenshots & Visuals/DIME Product Screenshots/`. Read the figures off it, change `values` and `as_of` in the data file, point `screenshots` at the new file name, then run `python3 tools/dime-proof.py --write`. That copies the screenshots into the site, rewrites every marker and alt text, sets each screenshot's `?v=` to a hash of the file, and moves the replaced figures into `retired`. `tools/dime-proof.py` (no flag) runs in the Netlify build, the GitHub Pages workflow and the pre-push hook, and fails when a marker or alt disagrees with the data file, a screenshot's `?v=` is stale, a proof figure appears on a listed page outside a marker, or a retired figure is still live. A new milestone that changes a sentence's meaning (a new badge, a new best month) still needs its copy rewritten by hand, then marked.
