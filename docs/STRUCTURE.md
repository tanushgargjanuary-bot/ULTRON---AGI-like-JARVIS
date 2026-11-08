# Repository structure

This guide explains where code and project records belong. The current package layout is already grouped by responsibility. Keep those paths stable unless a move has a tested benefit; the launchers and discovery rules depend on some of them.

## At a glance

```text
.
├── main.py, ui.py                 Supported application entry points
├── actions/                       Model-callable actions
├── plugins/                       Small auto-discovered capability plugins
├── core/                          Shared runtime, policy, evidence, UI bridges
│   └── mental/                    Bounded reasoning and curriculum registry
├── providers/                     Model, speech, audio, and transport adapters
├── custom_jarvis/                 Planning, service, bounded skills, state logic
├── memory/                        User-approved memory and persistence helpers
├── config/                        Configuration templates and managed settings
├── dashboard/                     Local dashboard server and static UI
├── curriculum/                    Syllabus data, not hard-coded course content
├── native/, sidecar/              Small native integrations and watcher
├── scripts/                       Verification, diagnostics, packaging, benchmarks
├── tests/                         Regression, contract, and platform tests
├── state/                         Runtime-managed state; do not commit private data
├── packaging/                     Release metadata and packaging assets
├── .github/                       CI workflows and issue templates
├── docs/                          Guides, maps, and technical records
│   └── reference/                 Long-form algorithms, user, and publishing guides
├── OwnerFiles/                    Owner-authored project context and history
└── run.bat, run.ps1, setup.py, requirements*.txt
                                  Install and launch contracts
```

## Where a change belongs

| Change | Put it in | Keep in mind |
|---|---|---|
| A user-facing operation | `actions/` or `plugins/` | Follow the tool contract in `AGENTS.md`; actions and plugins run away from the Qt main thread. |
| Shared safety, evidence, or runtime behavior | `core/` | Read `ARCHITECTURE.md` and `DECISIONS.md` first. The referee files listed in `WORKING-PHILOSOPHY.md` are protected. |
| A model or audio integration | `providers/` | Keep provider-specific transport behind the provider interface. |
| Planning, bounded skills, or assistant state logic | `custom_jarvis/` | Route actions through the existing registry and policy. |
| UI or dashboard behavior | `ui.py` or `dashboard/` | Keep widget changes on the Qt thread; the dashboard has its own browser-facing static assets. |
| Course facts and syllabus material | `curriculum/` | Store sourced facts as data; do not bury syllabus content in Python. |
| Verification or development tooling | `scripts/` | A verifier should report what it cannot check; do not weaken a gate to make it green. |
| A behavior guarantee | `tests/` | Add the closest regression/contract test and preserve existing assertions. |
| A guide or operating record | `docs/`, `HANDOFF.md`, or `OwnerFiles/` | `docs/INDEX.md` is the documentation entry point; `docs/MAP.md` is generated. |

## Root files that intentionally stay at the root

- `main.py` and `ui.py` are the established application entry points. The Windows launchers, installer, tests, and verification tools refer to these paths.
- `run.bat` and `run.ps1` are the supported launchers. Do not add another launcher or move these files.
- `AGENTS.md`, `WORKING-PHILOSOPHY.md`, `DECISIONS.md`, `ARCHITECTURE.md`, and `GATEKEEPERS.md` are prominent contributor and safety references; current instructions and links use their root paths.
- `readme.md`, `LICENSE`, `setup.py`, and the requirements files are standard repository entry points.
- `ALGORITHMS.md`, `CUSTOM_ULTRON.md`, and `PUBLISH.md` remain as short pointers for old links; the first two also remain in the installer manifest. Their full guides live in `docs/reference/`.
- `HANDOFF.md` and `log.txt` are project records. Keep the log append-only and update the handoff rather than creating competing status files.

## Why this pass does not move source files

The source is already separated into packages, but it is not a conventional `src/` tree. Several paths are runtime contracts: launch scripts expect `main.py`; tool discovery expects the established `actions/` and `plugins/` locations; tests and gates inspect some source paths directly. Moving files for appearance alone would add import shims, change discovery behavior, and make the existing uncommitted work harder to preserve. This change therefore improves the map and navigation while leaving source paths and runtime behavior unchanged.

Before any future move, search code, tests, scripts, workflows, docs, packaging metadata, and user-facing launch commands for the old path. Move only a clean, independently testable unit; retain a compatibility import if callers require it; regenerate `docs/MAP.md`; and run the relevant tests plus the Windows CI job. Do not move or edit protected safety files as part of a layout cleanup.

## Reading and verification path

1. Start with [`readme.md`](../readme.md) for product and setup context.
2. Read [`WORKING-PHILOSOPHY.md`](../WORKING-PHILOSOPHY.md), [`AGENTS.md`](../AGENTS.md), and [`DECISIONS.md`](../DECISIONS.md) before changing behavior.
3. Use [`ARCHITECTURE.md`](../ARCHITECTURE.md) to choose the responsible layer and [`docs/MAP.md`](MAP.md) to locate modules and tests.
4. Inspect the target module and its tests, then run the narrow regression suite before broader verification.
5. Use [`GATEKEEPERS.md`](../GATEKEEPERS.md) and the verification scripts to distinguish a pass from a limitation or a skipped check.
