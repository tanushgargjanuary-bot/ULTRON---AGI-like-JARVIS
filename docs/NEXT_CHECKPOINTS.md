# ULTRON — live checkpoint status and next actions

**Snapshot date:** 2026-11-11
**Current main HEAD:** `e1237d2e82ad7b981362f009baf568f7873415ea`
**Last fully verified application/test baseline:** `b80919314f391e15ddd86e2860c2e4d66057b15b`
**Default/permanent integration branch:** `main`
**Live refs:** three — `main` plus two merged temporary refs
**Archive tags:** 12 protected exact-SHA tags
**Open pull requests:** 0
**PR status:** #17 and #18 merged; #19 closed without merge.

This file is the live action list, not permission to add product scope. The canonical handoff is `OwnerFiles/ULTIMATE_Context.md`. Follow `AGENTS.md`, `WORKING-PHILOSOPHY.md`, and `docs/AGENT_MAINTENANCE.md` before any medium or large task. The HEAD above was read from GitHub on 2026-11-11. Refresh it before every later task.

## 1. Latest full application/test verification

| Lane | Run | Result |
|---|---|---|
| Fast branch gate | [42876494264](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42876494264) | Passed 5/5 groups on current main |
| Full Linux/Windows gate | [42876494213](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42876494213) | Both jobs succeeded on current main |
| Archive workflow | [42876494242](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42876494242) | Passed; 12 exact-SHA tags re-verified; archive-only mode |

Fast gate: 309 Python files parsed; 19 runner edge tests, 30 policy/confirmation tests, 8 README tests, and 1,000 seeded stress scenarios passed. Ruff, Git diff checks, and generated-map validation passed.

Full gate: Linux and Windows each passed 2,073 tests, 1,000 seeded stress scenarios, and 15 targeted mutations. Linux proof gate: 24 PROVEN / 13 PARTIAL / 0 FAILED. Windows: 28 PROVEN / 9 PARTIAL / 0 FAILED. Windows native checks: 99 passed / 0 failed. Linux's non-blocking instrument report: 17 passed / 2 failed / 15 skipped; the two failures were lack of a display server and PulseAudio on the hosted runner.

## 2. Immediate repository maintenance

### 2.1 Delete the two merged, archived temporary branch refs

**Status: READY FOR GUARDED CLEANUP**

| Branch | Exact archived commit | Recovery tag |
|---|---|---|
| `docs/repository-doc-audit-2026-11-10` | `9074b986c9379ff2b2f320916616763a735df972` | `archive/2026-11-10/docs-repository-doc-audit-2026-11-10-9074b986` |
| `ci/fast-branch-gate` | `e0072889ca333f5b8193f7d85b4ef912bf4aa10d` | `archive/2026-11-10/ci-fast-branch-gate-e0072889` |

Use GitHub Actions → **Archive reviewed branch tips**. Select branch `main` and dispatch with:

- `delete_branches=true`
- `confirm_delete=DELETE ARCHIVED BRANCHES`
- `confirm_archive_tags=ARCHIVE TAGS PROTECTED`

The workflow checks the active archive ruleset, exact branch SHAs, archive-tag targets, and open PRs. It never deletes `main`. Re-read refs after the run. Expected end state: one branch (`main`) and 12 protected archive tags.

Do not use force-push or an unguarded ref-delete operation.

### 2.2 Configure merge-blocking status checks on main

**Status: NOT VERIFIED — OWNER/ADMIN ACTION**

The automatic workflows run. The connected GitHub API returned HTTP 403 when this audit tried to read branch protection. This repository must not claim that failed checks block merges until an admin has configured and read back the required checks.

Require these exact check names in GitHub branch protection:

- `fast offline gate`
- `linux — suite and instruments`
- `windows — the machine the claims are about`

After saving, read the settings back. A green Actions run does not prove merge blocking.

### 2.3 Set the GitHub About description

**Status: NOT SET — OWNER/ADMIN ACTION**

GitHub repository metadata currently returns `description: null`.

Suggested description:

> A voice-first desktop AI agent with computer control, web research, memory, and safety gates.

Set it in the repository's About/settings UI. The connected GitHub tools used for this audit do not expose a repository-description write operation.

### 2.4 Verify the actual owner machine

**Status: NOT RUN IN THIS HOSTED AUDIT**

On the intended Windows desktop, run:

```powershell
python scripts/verify_all.py
python scripts/proof_gate.py --live
```

Review display/DPI, microphone, speaker, camera, browser, GPU, installed applications, and real provider/account checks. Use appropriate consent before any sensor check. Hosted CI cannot close these claims. A skipped check is not a pass.

## 3. Owner-gated product work

### 3.1 ULTRON Web preview

**Status: NOT STARTED — OWNER AUTHORIZATION REQUIRED**

The web application remains an authentication/workspace shell. It does not execute the Python agent, persist chat messages, provide cross-device memory, or enable the composer.

Before deployment:
1. Obtain explicit authorization for Vercel team access.
2. Inspect existing projects before creating anything.
3. Confirm the `webapp` root and current build scripts.
4. Configure Supabase and Google OAuth using only required Preview/Development variables.
5. Verify sign-in, callback, workspace, and sign-out.
6. Do not enable chat until a separate Python worker, server-side session verification, per-user policies, and retention/export/deletion controls exist.

Do not deploy, create a project, or add secrets without owner authorization.

## 4. Review and automation status

- PR #19 (`chore: trigger CodeRabbit review`) is closed without merge. It does not establish that CodeRabbit is configured or that AI review is required.
- Reviewdog/Ruff is static analysis. It is advisory and is not a semantic AI review.
- PR-Agent is documented as an optional local workflow. Do not send repository code to an external model endpoint without checking the owner's authorization and data-handling requirements.
- Branch-protection enforcement remains unverified until the required checks are configured and read back.

## 5. Rules for the next agent

1. Re-read the live main SHA, branch refs, tags, PRs, repository metadata, and Actions before acting. This file is a dated snapshot.
2. Read `OwnerFiles/ULTIMATE_Context.md`, `AGENTS.md`, `WORKING-PHILOSOPHY.md`, `docs/AGENT_MAINTENANCE.md`, and `docs/AGENT_PLAYBOOK.md`.
3. Run `python scripts/agent_workspace.py` and inspect all changed and uncommitted paths. Preserve other agents' work.
4. Main-only is the default for small, low-risk, non-parallel work when authorized. Use a short-lived branch only when isolation, parallel work, or rollback risk gives a clear benefit. Never keep permanent per-agent branches.
5. Do not treat old roadmap items as authorization. No new product scope is implied by this checkpoint.
6. Do not claim a test passed unless the exact run and commit show success. PARTIAL, SKIPPED, and untested hardware are not passes.
7. Update the handoff, affected topic guides, session log, and engineering log after medium or large work. Do not hand-edit `docs/MAP.md`; regenerate it only when Python modules/tests change.

## 6. Completed historical milestones

- The curated application was promoted to `main` by a direct, non-forced fast-forward.
- The initial ten historical branch refs were archived, protected, and deleted in [42779866199](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42779866199).
- PR #17 (handoff documentation) and PR #18 (automatic branch test gate) were merged.
- Twelve archive tags are verified by the current archive workflow.
- The fast and full verification lanes passed on current main SHA `e1237d2e82ad7b981362f009baf568f7873415ea` in runs 42876494264 and 42876494213. The application/test code is unchanged from baseline `b80919314f391e15ddd86e2860c2e4d66057b15b`.
