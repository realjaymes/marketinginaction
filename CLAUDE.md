# MIA website: working notes for Claude Code

The project notes, status log and lessons live in James's Obsidian vault: `Areas/Work/AI Workflows/MIA Website (Claude Code Build and Maintenance).md`, with page-level notes in `Areas/Work/MIA/Website/`. Read that note before starting, and add a Status Log line to it at the end of every build session.

Netlify serves the live site. `netlify.toml` runs the checks in `tools/` on every build, and the pre-push hook in `.githooks/` runs the same checks (enable it with `git config core.hooksPath .githooks`). Preview locally with `python3 -m http.server 8000`.
