# Documentation map

Ultron's source is split by responsibility. Use this page to find the right guide without moving files or breaking links that tools, releases, and older notes may rely on.

## Start here

| Read | For | Answers |
|---|---|---|
| [`../readme.md`](../readme.md) | Everyone | What Ultron does, setup, privacy, and supported capabilities |
| [`../OwnerFiles/for-the-next-agent.md`](../OwnerFiles/for-the-next-agent.md) | New agents | Current state, first verification commands, and known traps |
| [`../WORKING-PHILOSOPHY.md`](../WORKING-PHILOSOPHY.md) | Contributors | Evidence-first work, debugging, and contribution process |
| [`../AGENTS.md`](../AGENTS.md) | Coding agents | Hard coding, threading, plugin, and safety rules |
| [`AGENT_WORKSPACE.md`](AGENT_WORKSPACE.md) | Agents resuming work | How to inspect commits, branch differences, and local edits |
| [`AGENT_PLAYBOOK.md`](AGENT_PLAYBOOK.md) | Coding agents | Safe task planning, implementation, testing, and reporting |
| [`AGENT_NOTION.md`](AGENT_NOTION.md) | Every agent | How to write a Notion page another agent can use in ten seconds |
| [`LOCAL_MODEL.md`](LOCAL_MODEL.md) | Owner, agent | Which local model this machine can run, and the four commands that set it up |
| `docs/CAPABILITY_AWARENESS.md` | Owner, agent | The capability guide and the GitHub scout, what is tested, and what is not |
| [`../ARCHITECTURE.md`](../ARCHITECTURE.md) | Developers | System layers, one request end-to-end, and extension points |
| [`../DECISIONS.md`](../DECISIONS.md) | Anyone proposing a change | Owner decisions and where they are enforced |
| [`../GATEKEEPERS.md`](../GATEKEEPERS.md) | Anyone making a claim | What is proven, partial, missing, or machine-dependent |

**Recommended order for a code change:** workspace report → working philosophy → agent rules → decisions → architecture → target module and tests → relevant gatekeepers.

## Product and capability guides

| Guide | Subject |
|---|---|
| [`CAPABILITIES.md`](CAPABILITIES.md) | Candidate capabilities that are designed but not necessarily built |
| [`SKILLS.md`](SKILLS.md) | Skill families, bounded learning, and extension limits |
| [`TOOL_SUGGESTIONS.md`](TOOL_SUGGESTIONS.md) | Tools considered, accepted, or refused, with reasons |
| [`CURRICULUM.md`](CURRICULUM.md) | Subjects, syllabus sources, units, and reading paths |
| [`MENTAL.md`](MENTAL.md) | Curriculum topics implemented as algorithms and their code locations |
| [`TRIGGERS.md`](TRIGGERS.md) | When tools should be selected and how usage is measured |
| [`PHILOSOPHY.md`](PHILOSOPHY.md) | Assistant styles, methods, and boundaries |
| [`PROMPT.md`](PROMPT.md) | User-readable system prompt and its guarded editing path |

## Reliability, safety, and operations

| Guide | Subject |
|---|---|
| [`CONNECTION.md`](CONNECTION.md) | Provider errors, tool-schema faults, and reconnect diagnosis |
| [`CRASHES.md`](CRASHES.md) | Crash records, redaction, and repair evidence |
| [`SELF-CHANGE.md`](SELF-CHANGE.md) | Guarded source-change process and protected referee files |
| [`INSTALL.md`](INSTALL.md) | Installation, setup, and troubleshooting |
| [`SIDECAR.md`](SIDECAR.md) | Go watcher responsibilities, build, and fallback behavior |
| [`SPACE.md`](SPACE.md) | Workspace size/file-count limits and enforcement |

## Engineering evidence and decisions

| Guide | Subject |
|---|---|
| [`MAP.md`](MAP.md) | Generated module/test map; regenerate with `python scripts/map.py --write` |
| [`PERFORMANCE.md`](PERFORMANCE.md) | Measured launch, turn, audio, and connection performance |
| [`LANGUAGE_DECISION.md`](LANGUAGE_DECISION.md) | Why the current implementation language is retained |
| [`LANGUAGE_MATRIX.md`](LANGUAGE_MATRIX.md) | Language comparison and measured selection rationale |
| [`BRANCH_REVIEW.md`](BRANCH_REVIEW.md) | What each branch holds, what is worth taking; recommendations are not authorization |
| [`../ALGORITHMS.md`](../ALGORITHMS.md) | Algorithms in use, syllabus links, and deferred algorithms |
| [`../CUSTOM_ULTRON.md`](../CUSTOM_ULTRON.md) | Changes from upstream MARK and user guide |
| [`../PUBLISH.md`](../PUBLISH.md) | Publishing steps, attribution, and license requirements |

## Project records

| File | Purpose |
|---|---|
| [`../HANDOFF.md`](../HANDOFF.md) | Current handoff and chronological engineering history |
| [`../log.txt`](../log.txt) | Append-only build and investigation log |
| [`../OwnerFiles/journey.md`](../OwnerFiles/journey.md) | Owner-facing project journey, including defects and corrections |
| [`../OwnerFiles/session-log.md`](../OwnerFiles/session-log.md) | Dated task and handoff notes |
| [`../OwnerFiles/owner-notes.md`](../OwnerFiles/owner-notes.md) | Owner's recorded preferences and unresolved prompts |
| [`../verification-results.txt`](../verification-results.txt) | Output from the last recorded full verification; rerun before relying on it |

## Scripts and the evidence they produce

| Command | Purpose |
|---|---|
| `python scripts/agent_workspace.py --base origin/main` | Report local branch changes, incoming base commits, and uncommitted edits |
| `python scripts/branch_report.py` | Every branch, its tip, and which names point at the same commit — read-only |
| `python scripts/verify.py` | Offline tests, stress checks, mutation checks, and module organization |
| `python scripts/proof_gate.py` | Verify capability claims and report `PROVEN`, `PARTIAL`, `FAILED`, or `NOT PRESENT` |
| `python scripts/verify_all.py` | Check capabilities on the current machine; hardware/platform gaps remain explicit |
| `python scripts/map.py --write` | Regenerate `docs/MAP.md` from source modules and tests |
| `python scripts/profile_turn.py` / `python scripts/bench_startup.py` | Measure turn and startup costs before optimization |

## Repository layout

- `actions/`, `plugins/` — user-facing capabilities. Tools must follow the policy and worker-thread rules.
- `core/` — shared policy, providers' orchestration, safety, UI/accessibility helpers, and utilities.
- `providers/` — model, audio, speech, and transport implementations.
- `custom_jarvis/` — planner, evidence, bounded skills, state, and guarded automation.
- `memory/`, `config/` — user-approved memory and managed configuration. Never commit private state or keys.
- `tests/` — regression and contract tests; `scripts/` — verification, packaging, diagnostics, and benchmarks.
- `dashboard/`, `curriculum/`, `native/`, `sidecar/`, `packaging/` — focused application assets and support components.
- `OwnerFiles/` — owner context and project history; read before changing behavior or scope.

## Organization rule

Keep files in their existing locations unless a move has a verified benefit and every code, documentation, packaging, test, and release reference is updated in the same change. The repository has many documents because they record separate decisions, proofs, and operating procedures. This map groups them by task without deleting history or breaking established paths. Generated files such as `docs/MAP.md` must be regenerated, not hand-edited.
