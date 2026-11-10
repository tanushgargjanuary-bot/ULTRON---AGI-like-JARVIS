# ULTRON — checkpoint status and next work

**Last fully verified application/test baseline:** `077793d7fd846f871f269362759d97c198ec61c5`
**Last checked:** 2026-11-10
**Default/permanent integration branch:** `main`
**Live refs:** three branches — `main` plus two merged, archived temporary refs
**Recovery tags:** 12 protected exact-SHA tags
**Open pull requests:** 0

This is the current action list. It does not authorize new product scope. The canonical handoff is `OwnerFiles/ULTIMATE_Context.md`; follow `docs/AGENT_MAINTENANCE.md` before medium or large work.

## Latest verification

| Lane | Run | Result |
|---|---|---|
| Fast branch gate | [42832819956](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42832819956) | Passed 5/5 groups in 13.12 seconds |
| Full Linux/Windows gate | [42832820093](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42832820093) | Both jobs passed; 2,073 tests per platform |
| Archive workflow | [42832819947](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42832819947) | Passed; all 12 exact-SHA archive tags verified |

The fast run parsed 309 Python files. It passed 19 runner edge tests, 30 policy/confirmation tests, 8 README contract tests, and 1,000 seeded stress scenarios. Ruff and the generated module-map check passed.

The full run passed 1,000 stress scenarios and 15 targeted seeded mutations on each platform. Linux proof gate: 24 PROVEN / 13 PARTIAL / 0 FAILED. Windows: 28 PROVEN / 9 PARTIAL / 0 FAILED. Windows native checks: 99 passed / 0 failed. The Linux non-blocking instrument report: 17 passed / 2 failed / 15 skipped. Its two failures were screen capture without a display server and audio initialization without PulseAudio.

## Immediate repository tasks

### 1. Delete the two archived temporary branch refs

**Status: READY FOR GUARDED CLEANUP**

The two refs below belong to merged PRs. Their exact tips are already protected by archive tags.

| Branch | Archived commit | Recovery tag |
|---|---|---|
| `docs/repository-doc-audit-2026-11-10` | `9074b986c9379ff2b2f320916616763a735df972` | `archive/2026-11-10/docs-repository-doc-audit-2026-11-10-9074b986` |
| `ci/fast-branch-gate` | `e0072889ca333f5b8193f7d85b4ef912bf4aa10d` | `archive/2026-11-10/ci-fast-branch-gate-e0072889` |

Use GitHub Actions → **Archive reviewed branch tips**. Select `main` and dispatch with:

- `delete_branches=true`
- `confirm_delete=DELETE ARCHIVED BRANCHES`
- `confirm_archive_tags=ARCHIVE TAGS PROTECTED`

The workflow checks the active archive ruleset, branch SHAs, archive-tag targets, and open PRs. It never deletes `main`. Re-read refs after completion. The target is one branch (`main`) and 12 protected archive tags.

Do not use force-push or a raw ref-delete operation to bypass this workflow.

### 2. Configure merge-blocking status checks on main

**Status: NOT VERIFIED / OWNER OR ADMIN ACTION**

The workflows run automatically. The connected GitHub API returned HTTP 403 when this audit tried to read `main` branch protection. This repository record cannot claim that failed checks block merges.

Configure these exact status checks as required in GitHub branch protection:

- `fast offline gate`
- `linux — suite and instruments`
- `windows — the machine the claims are about`

After saving, read back the settings. Do not report this task complete based only on a green Actions run.

### 3. Verify owner-machine hardware and interactive behavior

**Status: NOT RUN IN THIS HOSTED AUDIT**

Run `python scripts/verify_all.py` on the intended Windows desktop when available. Review microphone, speaker, camera, display, DPI, browser, GPU, and real provider/account checks. Hosted CI cannot close these claims. A skipped check is not a pass.

## Existing owner-gated product work

### 4. ULTRON Web preview

**Status: NOT STARTED; OWNER AUTHORIZATION REQUIRED**

The web application remains an authentication/workspace shell. It does not execute the Python agent, persist chat messages, or provide cross-device memory. The composer remains disabled.

Before deployment, obtain explicit authorization for Vercel team access. Then inspect existing projects before creating anything, confirm the `webapp` root, configure Supabase/Google OAuth, use only required Preview/Development variables, and verify sign-in/callback/workspace/sign-out. Do not enable chat until the separate Python worker, server-side session verification, per-user policies, and retention/export/deletion controls exist.

## Completed historical milestones

- The curated application was promoted to `main` by a direct, non-forced fast-forward. No merge commit was created.
- The initial ten historical branch refs were archived, protected, and deleted in workflow [42779866199](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42779866199).
- PR #17 (documentation handoff) and PR #18 (automatic branch test gate) were merged. Their refs were later archived in the current 12-tag archive set.
- The current fast and full test lanes are active. A fast pass does not replace the full cross-platform gate.

## Operating rules

- Keep `main` as the only permanent integration branch.
- Main-only work is the default for small, low-risk, non-parallel changes when authorized.
- Use short-lived, narrow branches only when isolation, parallel work, or rollback risk gives a clear benefit.
- Do not keep permanent branches per agent or model.
- Never delete `main`, protected archive tags, user data, or historical records as routine cleanup.
- Re-read live refs, PRs, and Actions before acting. This status file is a snapshot.
- Do not treat old roadmap items as permission to build them.
- Read `OwnerFiles/ULTIMATE_Context.md`, `AGENTS.md`, `WORKING-PHILOSOPHY.md`, and `docs/AGENT_MAINTENANCE.md` before medium/large work.
