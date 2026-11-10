# ULTRON — current handoff

**Status:** The curated code is on `main`. Branch cleanup is pending tag protection and a separately confirmed workflow run.

## Current repository state

- Repository: `tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS`
- Stable branch: `main`
- Current `main` HEAD: `5f3beeefe7335e967029eaa5a2622ceb4160a8f1` (documentation-only follow-up).
- Promoted application commit: `bd4b43d16fdf27b495209678ed72b41f21408d7c`.
- Curated candidate: `ultron/curated-promotion-2026-11`. Its exact tip is contained in `main`; the branch is one documentation commit behind `main`.
- PR #15 is closed. Its reviewed head is reachable from `main`; the promotion used a direct non-forced fast-forward, not a merge commit.
- PR #16 is closed without merging. Its final web-app tree was copied into the curated candidate and promoted.
- Open pull requests: zero at the latest check.
- Linux and Windows verification passed in run `42699779342`.
- Web type-check and production build passed in run `42699779160`.
- Reviewdog/Ruff completed successfully in run `42699779015`.
- Archive-only workflow run `42760721739` completed successfully. It created and verified ten exact-SHA recovery tags.

## Branch cleanup

- Branch refs: 11 (`main` plus ten reviewed source/staging branches).
- Recovery tags: 10; each was checked against its reviewed full commit SHA.
- Branch refs deleted: zero.
- The latest recorded ruleset check found no repository tag ruleset. Verify the current setting before deletion.

**Required owner step:** In repository Settings → Rules → Rulesets, create an Active tag ruleset for tag names matching `archive/**/*`. Enable **Restrict updates** and **Restrict deletions**. Leave **Restrict creations** disabled. Add no bypass actors.

After confirming that ruleset is active, run Actions → **Archive reviewed branch tips** from `main` with:

- `delete_branches=true`
- `confirm_delete=DELETE ARCHIVED BRANCHES`
- `confirm_archive_tags=ARCHIVE TAGS PROTECTED`

The final phrase is an owner attestation. The workflow checks the exact reviewed branch SHAs, recovery-tag targets, and open PRs. It preserves changed branches, skips branches used by open PRs, and never deletes `main`. Inspect the workflow summary before considering cleanup complete.

Do not delete branch refs before the archive tag ruleset is active. Do not force-update `main`.

## Read these first

1. [Consolidation checkpoint](../docs/MAYBE_COMPLETE.md)
2. [Branch archive and cleanup](../docs/BRANCH_ARCHIVE.md)
3. [Branch review and promotion decisions](../docs/BRANCH_REVIEW.md)
4. [Code review workflow](../docs/CODE_REVIEW.md)
5. [Architecture](../ARCHITECTURE.md)
6. [Recorded decisions](../DECISIONS.md)
7. [Gatekeepers](../GATEKEEPERS.md)

## Curated implementation

- Reviewed branch work was selected and adapted. No competing development branch was merged wholesale.
- Provider imports are lazy on the default Gemini path.
- Saved-session memory search is included.
- Self-change proposals use hash checks and guarded atomic replacement. This is not an OS sandbox.
- Windows NTFS alternate-data-stream path rejection is included.
- MCP schemas and messages are bounded; unsupported schema features and tool-name collisions fail closed.
- Local fallback requires explicit consent and uses loopback-only HTTP without redirects or proxies.
- The dashboard is loopback-only by default. LAN exposure requires explicit permission and HTTPS.
- The public web reader has URL, DNS, redirect, robots, content-type, and response-size checks.
- ULTRON Web is an authentication shell. It does not run the Python agent, and its composer remains disabled.

## Known limits

- General live multi-provider failover is not fully wired into the request path.
- Self-change rehearsal runs with the current user's OS permissions. It is not a security sandbox.
- MCP server processes run with the current user's permissions and inherit ULTRON's environment. They are not sandboxed.
- The signed release verifier is not a complete publisher, downloader, A/B updater, or supervisor/worker update system.
- CI cannot prove every hardware, driver, desktop, microphone, camera, browser, or provider path on the owner's machine.
- Reviewdog/Ruff is static analysis, not a semantic security review. PR-Agent is optional and is not run automatically by GitHub Actions.

## Handoff rules

- Treat `main` as the stable branch.
- Use short-lived `feature/<topic>` and `fix/<topic>` branches for future work.
- Open pull requests to `main`; do not keep permanent branches per agent or coding model.
- Archive reviewed tips before deletion. Never delete `main`.
- If a source branch moves from its reviewed SHA, re-review it. Do not reset it to an earlier SHA.
- Do not claim a feature is complete unless tests and evidence support the claim.
