# OwnerFiles

This folder keeps project context for a new person or agent. It is public. Keep secrets, credentials, private machine details, and other people's personal data out.

## Start here

1. [`ULTIMATE_Context.md`](ULTIMATE_Context.md) — canonical current handoff for a new chat or agent: product scope, architecture, repository state, verification evidence, limitations, and next actions.
2. [`../docs/AGENT_MAINTENANCE.md`](../docs/AGENT_MAINTENANCE.md) — mandatory process for updating documentation, preserving history, cleaning safely, and keeping repository structure professional.
3. [`../docs/UPSTREAM_RESEARCH.md`](../docs/UPSTREAM_RESEARCH.md) — MARK/JARVIS source lineage, repository comparison, upstream issue/PR triage, and reuse decisions.
4. [`../docs/MAYBE_COMPLETE.md`](../docs/MAYBE_COMPLETE.md) — consolidation checkpoint and remaining limits.
5. [`../docs/BRANCH_REVIEW.md`](../docs/BRANCH_REVIEW.md) — reviewed branch graph and promotion decisions.
6. [`../docs/CODE_REVIEW.md`](../docs/CODE_REVIEW.md) — CI, static review, and manual review rules.
7. [`../WORKING-PHILOSOPHY.md`](../WORKING-PHILOSOPHY.md), [`../AGENTS.md`](../AGENTS.md), [`../ARCHITECTURE.md`](../ARCHITECTURE.md), [`../DECISIONS.md`](../DECISIONS.md), and [`../GATEKEEPERS.md`](../GATEKEEPERS.md) — work rules, system shape, decisions, and proof status.

## Folders

- [`history/`](history/) — dated project history and superseded handovers. These are historical evidence, not live status.
- [`owner/`](owner/) — the owner's recorded preferences and notes.
- [`reviews/`](reviews/) — focused review follow-ups and triage records.

## Keeping the folder useful

- Update current facts in `ULTIMATE_Context.md` when branch or PR status changes.
- Keep chronology and detailed session evidence in `history/session-log.md`.
- Preserve older records under `history/`; label them as historical.
- Keep every claim scoped to what was actually tested. A skipped test, a headless Windows runner, and the owner's interactive PC are different evidence levels.
- Keep keys, tokens, passwords, account details, private repositories, and machine-specific data out of this public folder.
- Do not add source ZIP snapshots. They become stale and are harder to review than the repository files.
