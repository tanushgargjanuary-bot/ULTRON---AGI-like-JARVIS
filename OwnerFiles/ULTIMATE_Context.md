# ULTRON — current handoff

**Status:** Consolidation candidate. PR #14 is open against `main`. It has not been merged.

## Live repository state

- Repository: `tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS`
- Stable branch: `main`
- Consolidation branch: `ultron/consolidation-2026-11`
- Promotion PR: [#14 — Maybe Complete checkpoint](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/pull/14)
- The consolidation is curated. It is not a wholesale merge of every agent branch.
- The original development branches remain present. The archive workflow is manual and creates tags only. It does not delete branch refs.
- Do not merge PR #14 until its latest Linux and Windows verification runs pass and the owner reviews the proof-gate output.

## Read these first

1. [Maybe Complete checkpoint](../docs/MAYBE_COMPLETE.md)
2. [Branch review and promotion decisions](../docs/BRANCH_REVIEW.md)
3. [Code review workflow](../docs/CODE_REVIEW.md)
4. [Architecture](../ARCHITECTURE.md)
5. [Recorded decisions](../DECISIONS.md)
6. [Gatekeepers](../GATEKEEPERS.md)

## Included consolidation work

- Curated integration of reviewed branches.
- Provider lazy-import fix for the default Gemini path.
- Saved-session memory search and tested self-change path protections.
- Dashboard loopback default. LAN exposure requires explicit permission and HTTPS.
- Consent-gated local fallback with loopback-only HTTP, disabled redirects/proxies, and bounded responses.
- MCP client with strict supported-schema conversion, collision checks, message-size limits, and guarded tool invocation.
- Public web reader with URL/DNS/redirect/robots/content-size protections.
- Reviewdog + Ruff static checks and cross-platform GitHub Actions verification.
- Manual archive tagging workflow. It never deletes branches.

## Known limits

- General live multi-provider failover is not fully wired into the request path.
- Self-change rehearsal uses a temporary copy, not an OS sandbox. Candidate code runs with the current user's permissions.
- MCP server processes run with the current user's permissions and inherit ULTRON's environment. They are not sandboxed.
- The signed release verifier is not a complete publisher, downloader, A/B updater, or supervisor/worker update system.
- CI cannot prove every hardware, driver, desktop, microphone, camera, or browser path on the owner's machine.
- Reviewdog is static analysis. PR-Agent is optional and is not run automatically by GitHub Actions.

## Handoff rules

- Treat `main` as stable. Keep all preparation on the consolidation branch until the owner approves promotion.
- Do not merge, push to `main`, or delete branch refs without explicit owner approval.
- Do not treat old handovers or archived logs as current test results.
- Inspect the checks attached to the current head of PR #14. A green result on an earlier commit does not verify the latest head.
- The ZIP source snapshot was removed from this candidate because it described an old branch and PR #12. Use the repository files and linked docs instead.
