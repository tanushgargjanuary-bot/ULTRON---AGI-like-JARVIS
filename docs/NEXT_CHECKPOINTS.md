# ULTRON — Next checkpoints

**Current candidate:** `ultron/curated-promotion-2026-11`  
**Last fully CI-verified candidate SHA:** `9346f2d50b135384c15bfaf24bb242336d28092c`  
**Active review:** [PR #15](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/pull/15)  
**Rule:** One small checkpoint at a time. Update this file and `MAYBE_COMPLETE.md` when evidence or state changes.

## Checkpoint 1 — Finish candidate verification

**Goal:** Establish that this exact candidate is ready for the owner to review for fast-forward promotion.

| Step | Task | Status |
|---|---|---|
| 1.1 | Confirm PR #15 head SHA matches the candidate SHA | Done — `9346f2d50b135384c15bfaf24bb242336d28092c` |
| 1.2 | Confirm candidate is a fast-forward from main | Done — 170 ahead, 0 behind at last comparison |
| 1.3 | Run Linux suite and proof gate | Passed — CI run `42694718527`; 24 PROVEN, 13 PARTIAL |
| 1.4 | Run Windows suite and proof gate | Passed — CI run `42694718527`; 28 PROVEN, 9 PARTIAL |
| 1.5 | Run ULTRON Web typecheck and production build | Passed — CI run `42694718173` |
| 1.6 | Run Reviewdog / Ruff and inspect warnings | Passed and triaged — CI run `42694718131`; 101 advisory findings recorded in `MAYBE_COMPLETE.md` |
| 1.7 | Inspect Linux and Windows proof-gate reports | Done — both reports inspected; PARTIAL claims remain documented |
| 1.8 | Review PR #15 file inventory and remaining findings | No PR review submissions or review comments found; manual risk review is scoped, not a full line-by-line audit |
| 1.9 | Update checkpoint documents with final evidence | Done; latest repeat run is `42694718527` |
| 1.10 | Correct archive workflow dispatch-input parsing and require tag protection before deletion | Prepared in this update; needs fresh CI |

**Exit condition:** Automated Linux, Windows, and web checks pass; both proof-gate reports are inspected; Reviewdog warnings are triaged; remaining review scope and hardware limits are explicit.

**Do not:** update `main`, close PR #15, or delete branches during this checkpoint.

## Checkpoint 2 — Prepare a Vercel preview

**Goal:** Create a private test deployment. Do not promote production.

| Step | Task | Status |
|---|---|---|
| 2.1 | Approve Vercel team access for the correct team | Waiting for owner approval |
| 2.2 | Discover existing Vercel projects and avoid duplicate project creation | Blocked by team access |
| 2.3 | Link the GitHub repository to a Vercel project with root directory `webapp` | Not started |
| 2.4 | Create/configure Supabase project and Google OAuth provider | Not started; owner credentials/configuration required |
| 2.5 | Set Supabase URL and publishable key in Vercel Preview and Development environments | Not started |
| 2.6 | Create a Preview deployment from the reviewed web branch | Not started |
| 2.7 | Test login, callback, protected route, and sign-out | Not started |

**Security boundary:** The first web slice is an auth shell. It does not run the Python agent or store prompts. Do not enable chat until the authenticated Python worker and per-user database policies are ready. Do not collect or sell raw user conversations or memories.

**Exit condition:** Preview deployment reaches READY and the Google login flow passes. No production domain or production promotion is required for this checkpoint.

## Checkpoint 3 — Promote and archive Git history

**Goal:** Put the exact approved candidate on `main` without a merge commit, then clean the branch list without losing commit history.

| Step | Task | Status |
|---|---|---|
| 3.1 | Owner approves exact candidate SHA on PR #15 | Pending |
| 3.2 | Recheck `main` SHA and fast-forward ancestry | Pending |
| 3.3 | Update `main` to the candidate with a non-forced, expected-SHA update | Pending |
| 3.4 | Close PR #15 without merging | Pending |
| 3.5 | Run archive workflow in archive-only mode | Pending |
| 3.6 | Verify all ten archive tags point to their exact reviewed commits | Pending |
| 3.7 | Add a GitHub tag ruleset for `refs/tags/archive/**` that blocks updates and deletion | Pending — owner action |
| 3.8 | Run deletion mode with both exact confirmation phrases | Pending |
| 3.9 | Verify only `main` remains as a branch, with all historical tips recoverable from protected tags | Pending |

**Deletion requires both exact confirmation phrases:**
- `DELETE ARCHIVED BRANCHES`
- `ARCHIVE TAGS PROTECTED`

The second phrase is an owner attestation. The workflow cannot inspect repository rulesets. Do not supply it until the tag ruleset is active.

**Safety rules:**
- Never delete `main`.
- Never use GitHub's native merge button for PR #15.
- Never force-push or force-update `main`.
- A moved source branch must be re-reviewed; do not reset it to an earlier SHA.
- The cleanup workflow skips branches used by open PRs.
- Archive tags must exist and match exact commit SHAs before branch deletion.
- A GitHub ruleset must block updates and deletion for `refs/tags/archive/**` before branch deletion is enabled.
- The workflow requires the exact owner attestation `ARCHIVE TAGS PROTECTED`; it does not verify the ruleset through API.
