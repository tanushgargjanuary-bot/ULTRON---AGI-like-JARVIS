# Agent documentation and repository maintenance system

**Status:** Mandatory project-wide procedure  
**Applies to:** Codex, the built-in ULTRON coding agent, other AI agents, and human contributors  
**Authority:** The user's current explicit request, owner decisions, root `AGENTS.md`, and the safety rules in this repository

## Purpose

A conversation is temporary. The repository is the durable project record.

Every agent must leave the project in a state that the next agent can understand without reading the previous chat. Documentation must describe the code that exists, the tests that ran, the limits that remain, and the decisions the owner made. Repository cleanup must reduce confusion without deleting useful history or changing runtime contracts.

This is an impact-based maintenance system. It does **not** require rewriting every Markdown file after every edit. The agent must inspect the full documentation map, update every affected source of truth, and leave unrelated documents unchanged.

## 1. Classify the work before editing

Use the highest applicable class.

| Class | Trigger | Required documentation action |
|---|---|---|
| Small | One local defect or wording change; one module; no API, data, policy, workflow, or public-claim change | Update the affected module/docstring and test. Add or update a guide only when the current guide becomes false. Review the handoff when the change alters a current fact. |
| Medium | Two or more modules; new or changed capability; new tool/action/plugin; interface or config change; new workflow; notable test or CI change; a public claim changes | Complete the documentation impact review in section 3. Update the canonical handoff and every affected topic guide. Review repository hygiene and structure. |
| Large or sensitive | Architecture, public API, data model/migration, provider/auth flow, permissions, privacy, consent, security, release/update, major dependency, repository layout, or multi-phase milestone | Complete all medium requirements plus architecture, decisions, gatekeepers, security/operations, README, and history updates as applicable. Include explicit risk and rollback notes. Seek independent review where practical. |

A user may explicitly request a documentation-only task. It still needs this classification. Do not wait for the user to remind you to update documentation.

## 2. Mandatory start-of-task procedure

1. Read `OwnerFiles/ULTIMATE_Context.md`. It is the current cross-chat handoff.
2. Read root `AGENTS.md`, `WORKING-PHILOSOPHY.md`, and `docs/AGENT_PLAYBOOK.md`.
3. Read `docs/AGENT_WORKSPACE.md` and run `python scripts/agent_workspace.py`. Review commit, path, base-difference, and uncommitted-work reports. This tool is read-only. It does not fetch, merge, test, or edit.
4. Check `git status --short`, current branch, recent commits, remote refs, open PRs, and latest relevant CI. Do not assume an earlier chat's state is current.
5. Inspect relevant source, callers, tests, and existing documentation before changing behavior.
6. Write a short plan: requested outcome, affected components/docs, safety constraints, tests, and acceptance evidence.
7. Preserve unrelated work. Do not stage, reset, overwrite, or delete another agent's work.

## 3. Documentation impact review

After implementation, review every surface below. Update only the surfaces affected by the work, but consider every row.

| Surface | Update when |
|---|---|
| `readme.md` | Product scope, setup, user-visible behavior, requirements, license statement, or public claims change |
| `OwnerFiles/ULTIMATE_Context.md` | Any medium/large task, milestone, branch/PR/release state change, new limitation, or next-action change |
| `ARCHITECTURE.md` | Responsibilities, data flow, trust boundary, threading, runtime lifecycle, or extension point changes |
| `DECISIONS.md` | The owner makes a new durable decision or changes an existing one |
| `GATEKEEPERS.md` | Proof claims, verdicts, test mechanisms, or known machine-dependent gaps change |
| `AGENTS.md` | A rule every future agent must follow changes. Keep root instructions short and link to detail. |
| Topic guide in `docs/` | A documented behavior, operation, security constraint, API, or implementation detail changes |
| `docs/INDEX.md` | A new, renamed, or retired guide changes navigation |
| `docs/MAP.md` | A Python module is added, removed, renamed, or its docstring/test relationship changes. Regenerate with `python scripts/map.py --write`. |
| `OwnerFiles/history/journey.md` | A major milestone or important turn in the project history occurs |
| `OwnerFiles/history/session-log.md` | A meaningful work session finishes. Record the request, changes, evidence, and unresolved work. |
| `log.txt` and `HANDOFF.md` | The established build/phase record requires a new entry. Preserve their historical role. Do not create competing status files. |
| `.github/PULL_REQUEST_TEMPLATE.md` | Keep documentation, tests, and repository hygiene visible during future reviews |

### Required current-handoff format

For medium/large work, update `OwnerFiles/ULTIMATE_Context.md` with relevant facts:

1. Last audit date and repository/main state.
2. Product scope and system boundaries.
3. What changed and where it lives.
4. Verification results with CI run IDs and exact verdict counts.
5. Known limits, failed/skipped checks, and unverified behavior.
6. Decisions made, risks, and rollback/recovery paths.
7. Next actions, blockers, and owner approvals required.
8. Links to detailed source documents instead of duplicating long guides.

The handoff records current state, not a diary. Put chronology in `journey.md` and `session-log.md`. Do not create a second competing project-context file.

## 4. Keep documentation truthful and non-duplicated

- A claim must point to code, a test, a CI run, or an explicitly named owner-machine check.
- Separate implemented, tested, partially verified, planned, blocked, and rejected work.
- Record exact run IDs, commit SHAs, dates, and counts only after reading the source result.
- A green CI job does not prove hardware that was not attached. PARTIAL and SKIPPED are not passes.
- Do not copy a whole topic guide into the handoff. Link to the detailed source of truth.
- Do not use a chat transcript as the only record of a design decision, unresolved defect, or project limitation.
- Keep historical documents historical. Add a dated correction or a current-state pointer when old facts remain useful. Do not silently rewrite the past.
- Put new docs in the existing documentation layout. Add them to `docs/INDEX.md`. Avoid new root-level Markdown files unless the file is a conventional repository entry point or an existing code/tool contract requires it.

## 5. Repository hygiene and structural review

Run a cleanup review on every medium/large task. Do not perform destructive cleanup just to make a file list shorter.

### Classify before removal

| File type | Default action |
|---|---|
| Source, tests, configuration templates, workflows, packaging inputs | Keep. Change only with a tested reason. |
| Current docs and owner handoff | Keep. Update the authoritative copy. |
| Generated files with a documented generator | Regenerate. Ignore local output. Remove tracked generated output only after checking every consumer and existing policy. |
| Machine-specific state, credentials, caches, temporary files | Keep out of Git. Never delete owner data automatically. |
| Historical logs, build records, review evidence, archived guides | Preserve unless the owner explicitly authorizes deletion or a verified retention policy applies. |
| Duplicate, dead, or obsolete source | Prove no callers, imports, tests, packaging references, workflows, docs, or user commands depend on it before removal. |

### Cleanup checks

1. Inspect `git status --short` and the full diff. Preserve user/agent changes outside the task.
2. Check `.gitignore` for secrets, state, caches, build output, and local reports. Never add a broad ignore pattern that hides source or tests.
3. Search references before removing or moving a file: imports, dynamic discovery, tests, scripts, CI, packaging, docs, and documented CLI commands.
4. Remove only artifacts created by this task or files proven to be unused and safe to remove. Never delete user files, secrets, logs, backups, or project history as generic cleanup.
5. Keep root paths stable. Move source only for a verified architectural benefit and update every reference in the same task.
6. Do not add placeholder files, duplicate launchers, redundant docs, dead abstractions, unnecessary dependencies, or generated snapshots that can be rebuilt.
7. Do not restore a workspace size/file-count budget. The owner withdrew that limit on 2026-11-07. Keep the tree auditable by excluding build noise and machine state, not by an arbitrary ceiling.

### Existing files that need deliberate treatment

- `docs/MAP.md` is generated by `scripts/map.py`. Do not hand-edit it.
- `ALGORITHMS.md`, `CUSTOM_ULTRON.md`, and `PUBLISH.md` are intentional root pointers for old links and packaging contracts. Their full guides live under `docs/reference/`.
- `log.txt`, `HANDOFF.md`, `verification-results.txt`, and the large technical catalog are historical/project records. Their size alone is not evidence that they are unnecessary.
- `state/`, `logs/`, credentials, and user-approved memory are machine/user data. Do not commit or delete them as cleanup.

## 6. Repository structure standards

Keep the current responsibility-based layout. Put work where it belongs:

- `actions/`, `plugins/`: model-callable capabilities and their contracts.
- `core/`: shared runtime, policy, evidence, tool registry, provider helpers, and UI bridges.
- `providers/`: model, speech, audio, and transport adapters.
- `custom_jarvis/`: planning, decisions, skill packs, metacognition, and bounded agent services.
- `memory/`, `config/`: managed settings and persistence. Secrets remain local.
- `dashboard/`, `webapp/`: distinct local and web surfaces. Do not merge their trust boundaries.
- `curriculum/`: sourced curriculum data.
- `native/`, `sidecar/`: narrow native integrations and optional watcher.
- `scripts/`, `tests/`: tools and evidence.
- `docs/`, `OwnerFiles/`: technical guides, current handoff, and historical records.

Follow `docs/STRUCTURE.md` for current paths and stable root contracts. Do not restructure to match a fashionable template when it adds import shims, launch changes, or risk without a measured benefit.

## 7. Required close-out

Before saying the task is complete:

- [ ] Implementation matches the user's request and existing owner decisions.
- [ ] Relevant tests and quality checks ran. Failures and skips are recorded honestly.
- [ ] Public and technical claims match the actual code and evidence.
- [ ] Documentation impact was reviewed using section 3.
- [ ] The canonical handoff is current for medium/large work.
- [ ] New/renamed docs are indexed. Generated docs are regenerated where needed.
- [ ] Repository cleanup and structure were reviewed. No unrelated files were removed.
- [ ] Secrets, credentials, local state, and generated build noise are not staged.
- [ ] Commit/PR/CI state and unresolved risks are recorded.

A task is not complete because code passes tests while the docs, runbook, handoff, or repository structure still describes an older system.
