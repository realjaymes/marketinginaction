#!/bin/zsh
# The MIA resources intake, run by the 17:00 job-radar runner on James's Mac
# (~/.claude/skills/job-radar/run-job-radar.sh). It works in its own worktree of
# the website repo, so it never touches uncommitted work in James's copy:
#   1. reset the worktree to origin/main
#   2. intake.py collect: events from MIA Events Watch reports, tools from the
#      n8n feed, MIA Tools Watch reports and the X briefs' Tool launches tables
#   3. if any tools arrived as a name and link only, one Claude step researches
#      them into full rows, and intake.py add checks and adds them
#   4. rebuild, check, commit and push (Netlify deploys the push)
# It prints the digest HTML for the runner. Usage:
#   intake-run.sh [--events "a.md;b.md"] [--tools "c.md"]   (vault-relative report paths)
set -u
REPO="$HOME/Documents/mia-website-directory"
WT="$HOME/.cache/mia-resources-intake"
VAULT="$HOME/Documents/James Obsidian Vault"
OUT="$HOME/.cache/mia-resources-intake-run"   # outside the worktree, so the pre-push checks never see it
FEED="https://n8n.marketinginaction.xyz/webhook/mia-tools-feed-8329306c0b924fd18c40"
CLAUDE_BIN="${CLAUDE_BIN:-$HOME/.local/bin/claude}"
PY=/opt/homebrew/bin/python3   # build.py needs Python 3.12 or later; the system /usr/bin/python3 is 3.9
EVENTS="" TOOLS=""
while (( $# )); do
  case "$1" in
    --events) EVENTS="$2"; shift 2 ;;
    --tools) TOOLS="$2"; shift 2 ;;
    *) shift ;;
  esac
done
paths() { local list="$1" p; local -a out; for p in ${(s:;:)list}; do [[ -n "$p" ]] && out+=("$VAULT/$p"); done; print -l -- $out; }

if [[ ! -d "$WT" ]]; then
  git -C "$REPO" worktree add --detach "$WT" origin/main >/dev/null 2>&1 || { echo "<p>⚠️ MIA resources intake: could not create its worktree.</p>"; exit 1; }
fi
cd "$WT" || exit 1
git fetch -q origin main && git checkout -q --detach origin/main && git reset -q --hard origin/main && git clean -qfd
rm -rf "$OUT" && mkdir -p "$OUT"

args=(collect --out "$OUT" --briefs "$VAULT/Areas/Work/Content/Briefs" --feed "$FEED")
ev=("${(@f)$(paths "$EVENTS")}"); [[ -n "${ev[1]:-}" ]] && args+=(--events "${ev[@]}")
tl=("${(@f)$(paths "$TOOLS")}"); [[ -n "${tl[1]:-}" ]] && args+=(--tools "${tl[@]}")
"$PY" tools/resources/intake.py "${args[@]}" > "$OUT/collect.log" 2>&1 || { echo "<p>⚠️ MIA resources intake failed at collect: $(tail -1 "$OUT/collect.log")</p>"; exit 1; }

if [[ "$("$PY" -c "import json;print(len(json.load(open('$OUT/candidates.json'))))")" != "0" ]]; then
  "$CLAUDE_BIN" -p "You research new tools for the public MIA Marketing & AI Tools directory. Nobody is in this conversation.
Read $OUT/candidates.json (name, website, what_it_does, source) and $WT/data/resources/tool-groups.json (the allowed categories).
For each candidate, open its official website with WebFetch (use WebSearch to find it if the link is missing or wrong) and write one row.
Write a JSON array to $OUT/enriched.json. Each row has: name (official product name), website (official homepage, never an affiliate or referral link),
overview (1 to 2 plain factual sentences about the product, no hype words, no dashes), product_type (a list from \"AI Tool\" and \"Marketing Tool\"),
notion_categories (1 to 3 names copied exactly from tool-groups.json), use_cases (5 to 6 short items, for marketers and founders), source (copy it).
The directory lists only AI tools and marketing tools. For a candidate that is anything else, is not released, is only a new model version of an
existing product, or has no official site, write {\"name\": ..., \"skip\": \"<one-line reason>\"} instead. Do nothing else." \
    --model sonnet --effort low --allowedTools "Read Write WebFetch WebSearch" \
    --settings '{"enabledPlugins":{"telegram@claude-plugins-official":false,"imessage@claude-plugins-official":false}}' \
    < /dev/null > "$OUT/enrich.log" 2>&1
  "$PY" tools/resources/intake.py add "$OUT/enriched.json" --out "$OUT" >> "$OUT/collect.log" 2>&1
fi

"$PY" tools/resources/build.py --write >/dev/null 2>&1
if ! "$PY" tools/resources/build.py --check > "$OUT/check.log" 2>&1; then
  echo "<p>⚠️ MIA resources intake: the rebuilt pages failed the check, so nothing was pushed. $(tail -2 "$OUT/check.log")</p>"
  exit 1
fi
git add data/resources resources/tech-events-calendar resources/marketing-ai-tools
if ! git diff --cached --quiet; then
  git -c user.name="James" -c user.email="realjaymes@gmail.com" commit -q -m "Resources intake $(date +%F)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  git push -q origin HEAD:main 2>"$OUT/push.log" || echo "<p>⚠️ MIA resources intake: the push failed. $(tail -1 "$OUT/push.log")</p>"
fi
cat "$OUT/summary.html"
