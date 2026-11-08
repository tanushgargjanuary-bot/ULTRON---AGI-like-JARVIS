# OwnerFiles

This folder keeps the project context a new person or agent needs, alongside the code. It is public. Keep secrets, credentials, private machine details, and other people's personal data out.

## Start here

1. [`ULTIMATE_Context.md`](ULTIMATE_Context.md) — current handoff, download command, archive provenance, and immediate status.
2. [`../WORKING-PHILOSOPHY.md`](../WORKING-PHILOSOPHY.md) — how the owner wants changes made and communicated.
3. [`../AGENTS.md`](../AGENTS.md), [`../ARCHITECTURE.md`](../ARCHITECTURE.md), [`../DECISIONS.md`](../DECISIONS.md), and [`../GATEKEEPERS.md`](../GATEKEEPERS.md) — hard constraints, system shape, decisions, and proof status.

## Folders

- [`history/`](history/) — project journey, dated session log, and superseded handovers. These preserve earlier evidence; do not treat old status lines as current.
- [`owner/`](owner/) — the owner's recorded preferences and notes.
- [`reviews/`](reviews/) — focused review follow-ups and triage records.

## Portable context

[`ULTIMATE_Context.zip`](ULTIMATE_Context.zip) packages a tracked source snapshot plus the OpenMausBot handoff notes and backlog. The archive excludes `.git`, credentials, local runtime state, and the archive itself. See `ULTIMATE_Context.md` for provenance, the PowerShell download command, and the current SHA-256. The embedded snapshot cannot contain its own final checksum.

## Keeping the folder useful

- Update current facts instead of adding another dated handover page.
- Keep chronology and detailed session evidence in `history/session-log.md`.
- Preserve older records under `history/`; label them as historical rather than silently deleting them.
- Keep every claim scoped to what was actually tested. A skipped test, a headless Windows runner, and the owner's interactive PC are different evidence levels.
- The owner reviewed the public nature of this folder. Do not add keys, tokens, passwords, account details, private repositories, or data that only belongs to one machine.
