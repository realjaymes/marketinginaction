# GitHub Pages Deploy — Runbook

What to do when the **Deploy static content to Pages** workflow goes red.

## First: is it actually broken?

A red X in Actions does **not** always mean the deploy failed. GitHub Pages can finish the
deployment but report "built" back to the Action *after* its 10-minute timeout — so the Action
aborts with `Timeout reached, aborting!` while the site actually updated fine.

Check before doing anything:

1. Load the live page that should have changed and confirm your change is present:
   ```bash
   curl -s https://marketinginaction.xyz/<path>/ | grep -i "<something from your change>"
   ```
2. Or ask GitHub whether the deployment finished — if it's done, cancel returns a 400 saying so:
   ```bash
   gh api --method POST repos/realjaymes/marketinginaction/pages/deployments/<SHA>/cancel
   # "Unable to cancel deployment <SHA> as it's finished." == the deploy landed. You're done.
   ```

If the change is live, **stop** — nothing is wrong. The red X was a slow report, not a failure.

## The two real failure modes

### 1. GitHub Pages queue stall (their infrastructure)
Symptom in the deploy log: `Current status: deployment_queued` repeating until `Timeout reached`.
The deployment never gets picked up. This is a GitHub-side backend stall — their status page
often still shows Pages "operational." Nothing in this repo causes it.

Fix: wait for the queue to drain (usually minutes), then re-trigger (see below). Confirm on
https://www.githubstatus.com if it persists.

### 2. Self-blocking stuck deployment (the cascade)
Symptom: `Deployment request failed for <newSHA> due to in progress deployment. Please cancel
<oldSHA> first or wait for it to complete.`

A previous stalled deploy left a zombie in-progress deployment for `<oldSHA>`. Because the Pages
deployment ID **is** the commit SHA, that zombie blocks every later run — including fresh commits.

The workflow now auto-clears this (the **Clear any stuck in-progress Pages deployment** step), so
it should self-heal. If it ever slips through, clear it by hand:
```bash
gh api --method POST repos/realjaymes/marketinginaction/pages/deployments/<oldSHA>/cancel
```

## How to re-trigger (correctly)

**Do NOT use "Re-run failed jobs."** Re-running only the failed deploy job leaves the original
artifact in place and registers a second one, producing:
`Multiple artifacts named "github-pages" were unexpectedly found ... Artifact count is 2.`

Instead, start a clean run (one run = exactly one artifact):
```bash
# preferred: manual dispatch (no code change)
gh workflow run static.yml --repo realjaymes/marketinginaction --ref main

# or: force a fresh SHA with an empty commit (also dodges same-SHA collisions)
git commit --allow-empty -m "Force Pages redeploy" && git push origin main
```

Watch it:
```bash
rid=$(gh run list --repo realjaymes/marketinginaction --workflow static.yml -L 1 --json databaseId -q '.[0].databaseId')
gh run view "$rid" --repo realjaymes/marketinginaction --json jobs \
  -q '.jobs[0].steps[] | .name+" -> "+.status+" / "+(.conclusion//"running")'
```

## Quick reference

| Symptom | Meaning | Action |
|---|---|---|
| Change is live but Actions is red | Slow report, deploy landed | None — ignore the red X |
| `deployment_queued` until timeout | GitHub queue stall | Wait, then dispatch a fresh run |
| `due to in progress deployment` | Zombie deployment from a prior stall | Auto-cleared now; else cancel `<oldSHA>` |
| `Multiple artifacts named "github-pages"` | Someone hit "Re-run failed jobs" | Dispatch a fresh run instead |
