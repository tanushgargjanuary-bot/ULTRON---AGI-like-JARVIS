# OwnerFiles

This folder keeps project context for a new person or agent. It is public. Keep secrets, credentials, private machine details, and other people's personal data out.

## Start here

1. [`ULTIMATE_Context.md`](ULTIMATE_Context.md) — canonical current handoff: product scope, architecture, exact repository state, test evidence, limitations, and agent instructions.
2. [`../docs/NEXT_CHECKPOINTS.md`](../docs/NEXT_CHECKPOINTS.md) — latest verification and ordered next actions. Start here after reading the canonical handoff.
3. [`../docs/AGENT_MAINTENANCE.md`](../docs/AGENT_MAINTENANCE.md) — mandatory process for updating documentation, preserving history, cleaning safely, and keeping repository structure professional.
4. [`../AGENTS.md`](../AGENTS.md) and [`../WORKING-PHILOSOPHY.md`](../WORKING-PHILOSOPHY.md) — binding code, safety, Git, and evidence rules.
5. [`../docs/AGENT_PLAYBOOK.md`](../docs/AGENT_PLAYBOOK.md) and [`../docs/AGENT_WORKSPACE.md`](../docs/AGENT_WORKSPACE.md) — start-of-task inspection, workspace review, implementation, tests, and close-out.
6. [`../docs/TEST_AUTOMATION.md`](../docs/TEST_AUTOMATION.md) — fast branch gate, full Linux/Windows suite, exact required status-check names, and current merge-enforcement limitation.
7. [`../docs/BRANCH_ARCHIVE.md`](../docs/BRANCH_ARCHIVE.md) — reviewed branch tips, 12 exact-SHA archive tags, guarded deletion, and restore commands.
8. [`../docs/UPSTREAM_RESEARCH.md`](../docs/UPSTREAM_RESEARCH.md) — MARK/JARVIS source lineage, repository comparison, upstream issue/PR triage, and reuse decisions.
9. [`../licenses/THIRD_PARTY_NOTICES.md`](../licenses/THIRD_PARTY_NOTICES.md) — third-party licence and asset provenance record.
10. [`../docs/CODE_REVIEW.md`](../docs/CODE_REVIEW.md), [`../ARCHITECTURE.md`](../ARCHITECTURE.md), [`../DECISIONS.md`](../DECISIONS.md), and [`../GATEKEEPERS.md`](../GATEKEEPERS.md) — review process, system shape, owner decisions, and proof status.

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
