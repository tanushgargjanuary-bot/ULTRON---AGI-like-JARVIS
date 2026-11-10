# ULTRON — Next checkpoints

**Production branch:** `main`  
**Promoted commit:** `bd4b43d16fdf27b495209678ed72b41f21408d7c`  
**Promotion method:** Non-forced fast-forward using the prior `main` SHA as an expected-SHA lease. No merge commit was created. GitHub closed PR #15 as merged because its head became reachable from `main`.  
**Archive run:** [42760721739 — Archive reviewed branch tips](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42760721739)  
**Current cleanup state:** Ten exact-SHA recovery tags created and verified; 11 branch refs remain; zero branches deleted.

## Checkpoint 1 — Promote the curated code

| Step | Task | Status |
|---|---|---|
| 1.1 | Verify candidate head and latest CI | Done — Linux passed; Web CI passed; Reviewdog passed; Windows post-promotion suite still running at time of update |
| 1.2 | Confirm candidate fast-forward ancestry | Done — 173 ahead, 0 behind before promotion |
| 1.3 | Fast-forward `main` with expected-SHA guard | Done — `main` is now `bd4b43d16fdf27b495209678ed72b41f21408d7c` |
| 1.4 | Avoid native merge / merge commit | Done — direct ref update; promoted commit has its original candidate parent |
| 1.5 | Close PR #15 after promotion | Done automatically when its head became part of `main` |
| 1.6 | Archive reviewed branch tips | Done — run `42760721739` succeeded |
| 1.7 | Verify the ten recovery tags | Done — every tag points to its reviewed full SHA |
| 1.8 | Verify open pull requests | Done — zero open PRs |

## Checkpoint 2 — Protect tags and delete old branch refs

**Goal:** Leave only `main` as a branch, while retaining the ten old tips as protected recovery tags.

| Step | Task | Status |
|---|---|---|
| 2.1 | Create a GitHub tag ruleset for tag names matching `archive/**/*` | Pending — no ruleset exists yet |
| 2.2 | Set enforcement to Active; enable Restrict updates and Restrict deletions; leave Restrict creations off; add no bypass actors | Pending — owner action |
| 2.3 | Manually run the archive workflow from `main` with deletion enabled and both confirmation phrases | Pending |
| 2.4 | Check the workflow summary for deleted and skipped branches | Pending |
| 2.5 | Verify only `main` remains and all ten tags remain | Pending |

Required inputs:
- `delete_branches=true`
- `confirm_delete=DELETE ARCHIVED BRANCHES`
- `confirm_archive_tags=ARCHIVE TAGS PROTECTED`

The last phrase is an owner attestation. The workflow does not query ruleset configuration. Do not enter it until the tag ruleset is active.

### Create the tag ruleset

1. Open repository **Settings → Rules → Rulesets**.
2. Select **New tag ruleset**.
3. Name it `ULTRON archive tag protection`.
4. Add an inclusion pattern for tag names: `archive/**/*`.
5. Set enforcement to **Active**.
6. Enable **Restrict updates** and **Restrict deletions**.
7. Leave **Restrict creations** disabled so the workflow can create future recovery tags.
8. Add no bypass actors. Save the ruleset.

### Run branch cleanup

1. Open **Actions → Archive reviewed branch tips**.
2. Select **Run workflow** from branch `main`.
3. Set `delete_branches` to `true`.
4. Enter `DELETE ARCHIVED BRANCHES`.
5. Enter `ARCHIVE TAGS PROTECTED` only after confirming the ruleset is active.
6. Run the workflow and inspect its summary.

The workflow rechecks exact branch SHAs, archive tag targets, and open PRs. It never deletes `main`.

## Checkpoint 3 — Vercel preview

| Step | Task | Status |
|---|---|---|
| 3.1 | Approve Vercel team authorization | Pending — owner approval |
| 3.2 | Discover existing projects and avoid duplicates | Blocked by team authorization |
| 3.3 | Set root directory to `webapp` | Not started |
| 3.4 | Configure Supabase and Google OAuth | Not started |
| 3.5 | Set Supabase URL and publishable key in Preview/Development | Not started |
| 3.6 | Deploy a Preview and test sign-in, callback, protected workspace, and sign-out | Not started |

**Web security boundary:** The web client remains an authentication shell. It does not run the Python agent or store prompts. Keep chat disabled until a secure Python worker, per-user database policies, retention, export, and deletion controls exist.

## Safety rules

- Never delete `main`.
- Never force-push or force-update `main`.
- Do not delete a branch with a changed SHA or active PR.
- Protect archive tags before deleting branch refs.
- Keep user conversations and memories private; do not sell raw user data.
