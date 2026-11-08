#!/bin/zsh
# The MIA resources intake, run by the 17:00 job-radar runner on James's Mac
# (~/.claude/skills/job-radar/run-job-radar.sh). It works in its own worktree of
# the website repo, so it never touches uncommitted work in James's copy:
#   1. reset the worktree to origin/main
#   2. intake.py collect: events from MIA Events Watch reports, tools from the
#      n8n feed, MIA Tools Watch reports and the X briefs' Tool launches tables
#   3. if any tools arrived as a name and link only, one Claude step researches
#      them into full rows, and intake.py add checks and adds them
#   3b. thought leaders: James's Thought Leader Candidates.md goes through the same
#      steps (collect, one Claude research step, intake.py add-leaders, headshots
#      for the people added); follow_list.py then refreshes the vault's follow list
#   4. rebuild, check, commit and push (Cloudflare Pages deploys the push)
# It prints the digest HTML for the runner. Usage:
#   intake-run.sh [--events "a.md;b.md"] [--tools "c.md"]   (vault-relative report paths)
# Test mode: INTAKE_WT=<a copy of the repo> uses that tree as it is (no reset to
# origin/main), INTAKE_OUT=<dir> keeps the run files apart, and INTAKE_NO_PUSH=1
# skips the commit and push.
set -u
REPO="$HOME/Documents/mia-website-directory"
WT="${INTAKE_WT:-$HOME/.cache/mia-resources-intake}"
VAULT="$HOME/Documents/James Obsidian Vault"
OUT="${INTAKE_OUT:-$HOME/.cache/mia-resources-intake-run}"   # outside the worktree, so the pre-push checks never see it
LEADERS="$VAULT/Areas/Work/MIA/Resources/Thought Leader Candidates.md"
FOLLOW="$VAULT/Areas/Work/MIA/Resources/Thought Leaders — Follow List.md"
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

if [[ -z "${INTAKE_WT:-}" && ! -d "$WT" ]]; then
  git -C "$REPO" worktree add --detach "$WT" origin/main >/dev/null 2>&1 || { echo "<p>⚠️ MIA resources intake: could not create its worktree.</p>"; exit 1; }
fi
cd "$WT" || exit 1
[[ -z "${INTAKE_WT:-}" ]] && { git fetch -q origin main && git checkout -q --detach origin/main && git reset -q --hard origin/main && git clean -qfd; }
rm -rf "$OUT" && mkdir -p "$OUT"

args=(collect --out "$OUT" --briefs "$VAULT/Areas/Work/Content/Briefs" --feed "$FEED")
[[ -f "$LEADERS" ]] && args+=(--leaders "$LEADERS")
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

if [[ "$("$PY" -c "import json;print(len(json.load(open('$OUT/leader-candidates.json'))))" 2>/dev/null)" -gt 0 ]] 2>/dev/null; then
  "$CLAUDE_BIN" -p "You research people for the public MIA Marketing Thought Leaders directory. Nobody is in this conversation.
Read $OUT/leader-candidates.json (name, links, note, source) and $WT/data/resources/thought-leaders.json (the existing rows show the exact shape and the allowed topic tags).
For each candidate, open their own profile or site with WebFetch (use WebSearch only to find their own site, newsletter or a recent bio) and write one row.
X blocks page fetches, so read an X profile as JSON at https://api.fxtwitter.com/<handle> (name, description, location, website) and treat its bio as their own words. Follow the website it names to confirm role and company.
Write a JSON array to $OUT/leaders-enriched.json. Each row has: name (as the person writes it), role (their current title), company (their current company or empty),
region (one of Africa, North America, Europe, Asia, Latin America, Middle East, Oceania, or empty), country (or empty),
one_liner (one plain sentence on what they write or build about, no hype words, no dashes), domains (1 to 3 topic tags copied exactly from: Growth Marketing, Product Marketing, AI,
GTM Engineering, Automation, Demand Generation, Brand Marketing, Content Marketing, Digital Marketing, Advertising),
x, linkedin, newsletter, website (full URLs the person's own pages confirm, empty when not found, never guessed),
profile_source (the one page that confirms the role and company: their own site, profile or a recent bio).
Every fact must be confirmed on a page you opened. Leave a field empty rather than guess. For a candidate you cannot confirm a role for, or who is not a marketing, growth,
product, GTM or AI-for-marketing operator or writer, write {\"name\": ..., \"skip\": \"<one-line reason>\"} instead. Do nothing else." \
    --model sonnet --effort low --allowedTools "Read Write WebFetch WebSearch" \
    --settings '{"enabledPlugins":{"telegram@claude-plugins-official":false,"imessage@claude-plugins-official":false}}' \
    < /dev/null > "$OUT/enrich-leaders.log" 2>&1
  "$PY" tools/resources/intake.py add-leaders "$OUT/leaders-enriched.json" --out "$OUT" >> "$OUT/collect.log" 2>&1
  added="$("$PY" -c "import json;print(','.join(json.load(open('$OUT/log.json'))['leaders_added']))")"
  [[ -n "$added" ]] && "$PY" tools/resources/headshots.py --slugs "$added" >> "$OUT/collect.log" 2>&1
fi

"$PY" tools/resources/build.py --write >/dev/null 2>&1
if ! "$PY" tools/resources/build.py --check > "$OUT/check.log" 2>&1; then
  echo "<p>⚠️ MIA resources intake: the rebuilt pages failed the check, so nothing was pushed. $(tail -2 "$OUT/check.log")</p>"
  exit 1
fi
"$PY" tools/resources/follow_list.py --out "$FOLLOW" >> "$OUT/collect.log" 2>&1   # James's follow list, in the vault
git add data/resources resources/tech-events-calendar resources/marketing-ai-tools resources/marketing-thought-leaders
if [[ -z "${INTAKE_NO_PUSH:-}" ]] && ! git diff --cached --quiet; then
  git -c user.name="James" -c user.email="realjaymes@gmail.com" commit -q -m "Resources intake $(date +%F)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  git push -q origin HEAD:main >"$OUT/push.log" 2>&1 || echo "<p>⚠️ MIA resources intake: the push failed. $(tail -1 "$OUT/push.log")</p>"
fi
cat "$OUT/summary.html"
