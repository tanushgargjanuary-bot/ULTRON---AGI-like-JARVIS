# ULTRON — checkpoint status and next work

**Last checked:** 2026-11-10  
**Stable branch:** `main`  
**Promoted application commit:** `bd4b43d16fdf27b495209678ed72b41f21408d7c`  
**Branch consolidation and cleanup:** Complete — one branch, ten protected recovery tags.

This file records the completed consolidation checkpoints and the next explicit owner-gated deployment work. It is not blanket authorization to add product scope.

## Checkpoint 1 — Promote the curated code

| Step | Task | Status |
|---|---|---|
| 1.1 | Verify candidate head and latest CI | Complete — Linux/Windows suite run 42699779342; web type-check/build run 42699779160; Reviewdog/Ruff run 42699779015 |
| 1.2 | Confirm candidate fast-forward ancestry | Complete — 173 ahead, 0 behind before promotion |
| 1.3 | Fast-forward `main` with expected-SHA guard | Complete — promoted application commit `bd4b43d16fdf27b495209678ed72b41f21408d7c` |
| 1.4 | Avoid native merge / merge commit | Complete — direct non-forced ref update |
| 1.5 | Close PR #15 after promotion | Complete — exact PR head became reachable from `main` |
| 1.6 | Archive reviewed branch tips | Complete — ten exact-SHA recovery tags created |
| 1.7 | Verify the ten recovery tags | Complete — all ten full SHAs matched |
| 1.8 | Verify open pull requests | Complete — zero |

## Checkpoint 2 — Protect tags and delete old branch refs

**Status: COMPLETE.** The repository now has one permanent branch (`main`) and ten protected historical recovery tags.

| Step | Task | Status |
|---|---|---|
| 2.1 | Create a GitHub tag ruleset for `archive/**/*` | Complete — ruleset ID `26923169` |
| 2.2 | Enable Active enforcement, restrict updates/deletions, allow creation, no bypass actors | Complete — configuration read back from GitHub |
| 2.3 | Dispatch the guarded cleanup workflow from `main` | Complete — run `42779866199` |
| 2.4 | Check workflow completion | Complete — Actions conclusion `success` |
| 2.5 | Verify refs and recovery tags | Complete — one branch, ten protected tags, zero open PRs |

The workflow reads the live ruleset itself before deletion. It also checks the exact reviewed source SHAs, archive-tag targets, and open PRs. It never deletes `main`. See [Branch archive and cleanup](BRANCH_ARCHIVE.md) for the audit and restore commands.

## Checkpoint 3 — Vercel preview (not started)

| Step | Task | Status |
|---|---|---|
| 3.1 | Obtain owner authorization for Vercel team access | Pending — required before project discovery |
| 3.2 | Inspect existing projects and avoid duplicate creation | Blocked by team authorization |
| 3.3 | Confirm `webapp` as the root directory | Not started |
| 3.4 | Configure Supabase and Google OAuth | Not started |
| 3.5 | Configure only the required Preview/Development environment variables | Not started |
| 3.6 | Deploy a Preview and verify sign-in, callback, protected workspace, and sign-out | Not started |

**Web security boundary:** ULTRON Web remains an authentication/workspace shell. It does not run the Python agent, persist chat messages, or provide cross-device memory. Keep the composer disabled until there is a separately hosted Python worker, verified server-side sessions, per-user data policies, and retention/export/deletion controls.

## Safety and operating rules

- Never delete or force-update `main`.
- Never delete or move the protected archive tags as routine cleanup.
- Re-review a branch if its SHA changes; do not reset it to an old reviewed tip.
- Do not create permanent branches per agent or model.
- Do not treat a suggested feature or old roadmap item as owner authorization.
- Keep user conversations, personal memories, credentials, and provider keys out of the public repository.
- Read `OwnerFiles/ULTIMATE_Context.md` and `docs/AGENT_MAINTENANCE.md` before starting a new medium or large task.
