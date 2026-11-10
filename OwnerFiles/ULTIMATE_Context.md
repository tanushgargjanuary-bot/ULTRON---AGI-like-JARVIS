# ULTRON — canonical project handoff

**Last full repository audit:** 2026-11-10

- **Repository:** `tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS`
- **Visibility:** Public
- **Permanent integration branch:** `main`
- **Current main SHA:** `b80919314f391e15ddd86e2860c2e4d66057b15b`
- **Latest full Linux/Windows run:** [42855681003](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42855681003) — both platforms passed.
- **Latest fast branch gate:** [42855680649](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42855680649) — 5/5 groups passed in 12.68 seconds.
- **Latest archive run:** [42855681028](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42855681028) — passed; 12 exact-SHA archive tags verified.
- **Live branches:** three refs — `main` plus two merged temporary refs pending guarded deletion.
- **Open pull requests:** zero.
- **Archive ruleset:** Active ID `26923169`; protects `refs/tags/archive/**/*` from updates and deletion.
- **GitHub About description:** blank (`null` in repository metadata); owner/admin action remains.
- **License:** CC BY-NC 4.0. Attribution to FatihMakes / 0101e5 is required. Commercial use is not permitted; see `LICENSE`.


This file is the durable handoff. A new chat or agent must be able to continue from the repository without access to earlier conversations. Read this page first, then follow the linked source-of-truth documents. Do not infer that every planned capability is complete because the test gates and main integration are complete. Two merged temporary branch refs still need the guarded deletion workflow.

## 1. Current status

This snapshot was read from GitHub on 2026-11-10. The current source of truth is `main` at `b80919314f391e15ddd86e2860c2e4d66057b15b`. Recheck all live state before acting.

- PR #15 was promoted to `main`; PR #16 was closed without merging, but its final web-app tree was included in the promoted candidate.
- Documentation PR #17 and fast-test PR #18 are merged. PR #18 was squash-merged as `eeacaf2ae2224edd91074a3853ae0ecff47c41a7`.
- PR #19, `chore: trigger CodeRabbit review`, is **closed without merging** (`merged=false`). Do not treat it as a durable CodeRabbit integration or assume an AI review check is required.
- The original ten obsolete development branches were archived and deleted in [run 42779866199](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42779866199).
- Three branch refs remain: `main`, `docs/repository-doc-audit-2026-11-10`, and `ci/fast-branch-gate`. The two temporary refs are merged, have protected exact-SHA recovery tags, and have no open PR. Their branch refs have not been deleted.
- There are 12 protected recovery tags. Archive workflow [42855681028](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42855681028) completed successfully on the current main SHA and verified the tag set.
- Archive ruleset **ID 26923169** is Active. It protects `refs/tags/archive/**/*` against updates and deletion, allows tag creation, and has no bypass actors.
- To finish branch cleanup, manually dispatch `Archive reviewed branch tips` from `main` with `delete_branches=true`, `confirm_delete=DELETE ARCHIVED BRANCHES`, and `confirm_archive_tags=ARCHIVE TAGS PROTECTED`. The workflow rechecks the ruleset, exact refs, tag targets, and open PRs. It never deletes `main`.
- Required-check merge blocking is **not verified**. The branch-protection API returned HTTP 403 when this audit tried to read `main` protection. The workflows run, but this audit cannot claim failed checks block merges.
- The GitHub repository About description is blank. Proposed short description: “A voice-first desktop AI agent with computer control, web research, memory, and safety gates.” The connected GitHub tools can read metadata but do not expose a repository-settings write action.
- The separate private owner-development repository exists but is empty. It has no commits or files and is not an active canary channel. The public repository remains the active source of truth.

### Latest verification on the current main SHA

Full Linux/Windows run: [42855681003](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42855681003). Both jobs completed successfully on `b80919314f391e15ddd86e2860c2e4d66057b15b`.

| Evidence | Linux | Windows |
|---|---:|---:|
| Full suite tests | 2,073 passed | 2,073 passed |
| Seeded stress scenarios | 1,000 passed | 1,000 passed |
| Targeted seeded mutations | 15 passed | 15 passed |
| Proof-gate PROVEN | 24 | 28 |
| Proof-gate PARTIAL | 13 | 9 |
| Proof-gate FAILED | 0 | 0 |
| Native checks | 99 passed, 0 failed | 99 passed, 0 failed |

Linux also reports 17 instrument checks passed, 2 failed, and 15 skipped. The two non-blocking failures are screen capture without a display server and audio initialization without PulseAudio. These are hosted-runner limits. They do not prove the owner's actual display or audio setup.

Fast branch gate: [42855680649](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42855680649). It parsed 309 Python files and passed 19 fast-runner edge tests, 30 policy/confirmation tests, 8 README contract tests, and 1,000 deterministic stress scenarios. Changed-file Ruff, Git diff checks, and generated `docs/MAP.md` validation passed. All five fast-gate groups passed in 12.68 seconds. The stress suite made no live model or provider request.

The archive workflow [42855681028](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42855681028) passed and verified all 12 exact-SHA archive tags.

**Evidence limits:** PARTIAL and SKIPPED are not passes. Hosted CI cannot prove the owner's microphone, speaker, camera, GPU, display scaling, browser installation, provider credentials, or interactive workflows. Run `python scripts/verify_all.py` on the target Windows machine when authorized.

Historical promotion evidence remains in `docs/MAYBE_COMPLETE.md`; those runs are not the latest verification.


## 2. What ULTRON is

ULTRON is a voice-first, agentic desktop application built on the upstream MARK-LVI/JARVIS codebase. It adds a policy-controlled tool system, memory with owner approval, planning and decision logic, evidence checks, diagnostics, self-change proposals, local integrations, and a separate web shell.

It is **not** a replacement kernel or a new operating system. It is an application/control layer over the host OS. It does not have unrestricted autonomy. The host OS permissions still define the outer security boundary.

### Product surfaces

1. **Desktop assistant:** primary product, launched through `run.bat` or `run.ps1`; `main.py` runs the session and `ui.py` owns the Qt window.
2. **Local dashboard:** separate local dashboard surface under `dashboard/`; network exposure is loopback-only by default. LAN exposure requires explicit owner configuration and HTTPS.
3. **ULTRON Web:** separate Next.js application under `webapp/` with Supabase authentication scaffolding. It is currently an authentication/workspace shell. It does not execute the Python agent, persist chat messages, provide cross-device memory, or enable its composer.
4. **Go sidecar:** optional watcher/supervisor component under `sidecar/`; Python fallback remains available. It is not a complete worker/supervisor architecture.

## 3. Main capability areas

- **Morning briefing:** opt-in by default. A fresh install stays silent until the owner enables the HUD toggle. Existing saved boolean choices are preserved; malformed values fail closed to off.


These are capability areas in the repository, not blanket claims that every hardware- or provider-dependent path has been proven on the owner's machine.

- Voice session, provider selection, speech input/output, and reconnect handling.
- Desktop/window control, accessibility-tree-first interaction, keyboard/mouse operations, and application launch.
- Browser automation and bounded public-web search/reading.
- Workspace-scoped file operations and file processing.
- Action and plugin capability loading, tool catalog, capability descriptions, and usage telemetry.
- Policy tiers, explicit confirmations, sensor consent, and evidence checks.
- Planning, bounded tool workflows, task state, recovery proposals, and goal verification.
- Approved memory, session recall, knowledge, learning curriculum, and skill packs.
- Meta-cognition, lesson recall, decision scoring, algorithmic helpers, and reminder scheduling.
- Health/crash reporting, process monitoring, self-change proposals, leaf reload staging, shipping, and update checks.
- Native/public platform readers and bounded MCP integration.
- Separate web UI authentication shell and local dashboard.

Detailed contracts live in `docs/CAPABILITIES.md`, `docs/SKILLS.md`, `docs/TRIGGERS.md`, `docs/MENTAL.md`, `docs/PHILOSOPHY.md`, `docs/HEALTH_CENTER.md`, `docs/SELF-CHANGE.md`, and `docs/ECOSYSTEM.md`. The generated module/test map is `docs/MAP.md`.

## 4. Architecture and where work belongs

The governing design is in `ARCHITECTURE.md`.

| Layer | Location | Responsibility |
|---|---|---|
| Host | `main.py`, `ui.py`, `dashboard/` | session, UI, and user-facing surfaces |
| Providers | `providers/` | model, speech, audio, and transport adapters |
| Safety | `core/policy.py`, `core/custom_gate.py`, evidence components | action permission, confirmation, and proof |
| Capability | `actions/`, `plugins/`, bridge helpers | bounded tools that perform one job |
| Judgement | `custom_jarvis/` | plans, decisions, verification, memory workflows, and skills |
| State | `memory/`, `config/`, state helpers | persisted user-approved settings and data |

Other important areas:
- `core/`: shared runtime, policy, memory consent, tool registry, UI bridges, networking, and platform support.
- `curriculum/`: sourced syllabus data; course facts belong in data, not hard-coded prose.
- `native/` and `sidecar/`: narrow native components and the optional Go watcher.
- `scripts/`: bootstrap, migration, verification, proof gate, map generation, profiling, and maintenance tools.
- `tests/`: unit, contract, security, integration, and platform-aware tests.
- `packaging/`: packaging and release assets.
- `docs/`: guides, indexes, generated maps, and technical decisions.
- `OwnerFiles/`: public owner context and project history. Never put secrets or private personal data here.

Do not move source directories for visual tidiness. Existing launchers, discovery rules, tests, package metadata, and the installer depend on established paths. Any structural move must include a complete reference search, compatibility decision, tests, and same-change documentation updates.

## 5. Non-negotiable engineering and safety rules

- **Evidence first:** a claim needs evidence. A claim without evidence must say so.
- **Consent:** do not capture screen, camera, or microphone without relevant user consent, indicator, and stop path.
- **Memory:** persist only what the owner approved. Do not infer and silently save user facts.
- **Tool policy:** tools must pass the central policy/confirmation path. Never let the planner or a model-supplied value grant its own permissions.
- **Workspace confinement:** file tools must remain inside the allowed workspace. Preserve backups and evidence where the design requires them.
- **Threading:** Qt widgets are created/changed on the Qt main thread. Actions and plugins run on workers and use thread-safe `player` methods/signals.
- **Provider boundary:** validate provider schemas and responses. Handle timeout, `None`, malformed output, quota, and network errors without inventing success.
- **Secrets:** use `memory/config_manager.py` and OS credential mechanisms. Never print, commit, or place keys in docs or tests.
- **Referee files:** `core/policy.py`, `core/confirm.py`, `core/self_change.py`, `scripts/proof_gate.py`, and secret-bearing config are protected by the project change rules. Do not weaken their controls or bypass rehearsal/confirmation.
- **Self-change limitation:** rehearsal in a temporary copy runs with the current user's OS permissions. It is not a sandbox against hostile code.
- **MCP limitation:** configured MCP child processes run with the current user's permissions and inherit the app environment. Use only trusted server commands.
- **Updates:** signed verifier utilities do not constitute a complete unattended release/update pipeline. Keep unattended core-code updates disabled.
- **No fake green:** CI success, a proof-gate PARTIAL, a skipped device test, and a live owner-machine result are different evidence levels.

See `AGENTS.md`, `WORKING-PHILOSOPHY.md`, `DECISIONS.md`, and `GATEKEEPERS.md` for binding detail.

## 6. Verification and engineering workflow

Primary commands:

```powershell
python scripts/agent_workspace.py
python scripts/fast_verify.py
python scripts/verify.py
python scripts/proof_gate.py
python scripts/verify_all.py
python scripts/map.py --write
```

- `agent_workspace.py` reports local commits, branch/base differences, paths, and uncommitted changes. It does not fetch, merge, edit, or test.
- `fast_verify.py` is the offline preflight for branch pushes: syntax for every discovered Python file, focused edge/policy/README regressions, and deterministic stress. It is not a full platform proof.
- `verify.py` runs syntax checks, unit/regression tests, stress scenarios, mutation checks, and the module organization/map check.
- `proof_gate.py` verifies capability claims and emits PROVEN/PARTIAL/FAILED/NOT PRESENT.
- `verify_all.py` checks the current machine's real platform/hardware capabilities and reports non-applicable checks as SKIP.
- `map.py --write` regenerates `docs/MAP.md` from Python source docstrings and tests. Do not hand-edit that generated file.

GitHub Actions:
- `.github/workflows/fast-checks.yml`: fast offline gate on every branch push; changed-file Ruff, diff checks, whole-tree Python syntax, focused regressions, stress, and generated-map validation.
- `.github/workflows/verify.yml`: full Linux and Windows tests, proof gates, mutation checks, and non-blocking instrument reports on PRs to `main` and pushes to `main`.
- `.github/workflows/webapp.yml`: webapp checks.
- `.github/workflows/reviewdog.yml`: static Reviewdog/Ruff reporting.
- `.github/workflows/archive-reviewed-branches.yml`: guarded exact-SHA archive workflow. Pushes to `main` run archive-only mode; manual deletion mode checks the live tag ruleset, reviewed refs, tags, and open PRs, and never deletes `main`. After branch cleanup, archive-only runs resolve the curated candidate from its protected archive tag and verify its exact promotion SHA.

## 7. Repository hygiene

- `main` is the only permanent integration branch. Two merged short-lived refs remain pending guarded deletion: `docs/repository-doc-audit-2026-11-10` and `ci/fast-branch-gate`.
- Twelve protected recovery tags remain under `archive/2026-11-10/`. They are history/recovery refs, not active branches.
- Do not delete or rewrite recovery tags, `main`, project history, tests, or user-owned state as generic cleanup.
- No workspace size/file-count budget is active. Keep caches, build outputs, temporary test files, and machine state out of Git because they are not auditable and may contain private data.
- Do not remove tracked historical records such as `log.txt`, `HANDOFF.md`, or `verification-results.txt` merely because they are large. Check their role and references first.
- Root pointer files `ALGORITHMS.md`, `CUSTOM_ULTRON.md`, and `PUBLISH.md` intentionally preserve old links and packaging contracts. Their full guides live under `docs/reference/`.
- `docs/MAP.md` is generated. Regenerate only when source modules/tests change.
- The repository's public landing page is `readme.md` (lowercase).

## 8. Current limitations and unfinished work

These limits matter. Do not advertise the product beyond them.

1. **General provider failover:** routing primitives exist, but general live fallback/quota handling is not fully wired into the application request path.
2. **ULTRON Web:** authentication/workspace shell only; no Python worker, chat persistence, cross-device memory, or enabled composer. Sign-in also depends on Supabase/Google OAuth configuration.
3. **Deployment:** no confirmed Vercel project/preview deployment in this handoff. Team authorization is needed before discovery/configuration.
4. **Self-change security:** temporary rehearsal is not OS-level isolation; hostile candidate code can use the current user's permissions.
5. **MCP process security:** external MCP processes are not sandboxed and inherit the parent environment.
6. **Release updates:** no complete signed publisher/downloader, production keyring, A/B updater, or supervisor/worker handoff.
7. **Hardware proof:** CI cannot verify every actual owner device, microphone, speaker, camera, GPU, DPI, browser installation, or real provider/account workflow.
8. **Independent review:** Reviewdog/Ruff are static checks. They are not a full semantic security audit or independent human review.
9. **Code review depth:** previous promotion review was risk-focused, not a line-by-line independent review of every changed line.
10. **Private owner-development repository:** it exists but is empty (no commits or files). No private development or canary workflow is active. The public repository remains the active source of truth.
11. **Merge enforcement:** Automatic workflows run, but required status-check enforcement for `main` is not verified. The branch-protection API returned HTTP 403. Require `fast offline gate`, `linux — suite and instruments`, and `windows — the machine the claims are about` in GitHub branch protection. See `docs/TEST_AUTOMATION.md`.

## 9. Project history and branch consolidation

- The project started from `FatihMakes/Mark-LVI` and evolved through multiple feature, agent, and integration branches.
- Branch adoption/rejection rationale is preserved in `docs/BRANCH_REVIEW.md`.
- The curated candidate `ultron/curated-promotion-2026-11` was promoted as application commit `bd4b43d16fdf27b495209678ed72b41f21408d7c`.
- The original ten historical non-main tips were preserved as exact-SHA tags, then their refs were deleted in workflow run 42779866199. Two later merged PR branch tips were added to the archive list and verified in run 42830329517.
- Active archive ruleset is ID 26923169. Current branch state: `main` plus two archived temporary refs, 12 archive tags, zero open PRs. Manual guarded deletion remains. The latest full, fast, and archive workflows passed on `b80919314f391e15ddd86e2860c2e4d66057b15b`: full [42855681003](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42855681003), fast [42855680649](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42855680649), and archive [42855681028](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42855681028).
- Full SHA evidence and restore instructions are in `docs/BRANCH_ARCHIVE.md`. The adoption/rejection audit is in `docs/BRANCH_REVIEW.md`.

The GitHub About description was blank at the latest metadata check. Proposed short description: “A voice-first desktop AI agent with computer control, web research, memory, and safety gates.” The connected GitHub interface can read metadata but does not expose the repository-settings write needed to change this field; owner action remains required.
- The separate private owner-development repository exists but is empty. It has no commits or files and is not an active canary channel. The public repository remains the active source of truth until the private workflow is deliberately configured and verified.

## 10. Upstream MARK/JARVIS resources

The original project lineage and current upstream material are documented in [`docs/UPSTREAM_RESEARCH.md`](../docs/UPSTREAM_RESEARCH.md).

Key facts from the 2026-11-10 audit:

- Eight public repositories were returned by the FatihMakes account search. The primary current source is [`FatihMakes/Mark-LVI`](https://github.com/FatihMakes/Mark-LVI), main commit `0101e540ac4b16cc3a862d9979e08fefcc1c7a01`.
- The inspected MARK-LVI tree had 78 files. All 78 paths already existed in ULTRON. Sixteen shared files had identical blob SHAs; 62 shared files differed. All 62 changed shared paths have had focused comparisons. The four visual files are included. MediaPipe face geometry has a separate Apache 2.0 licence copy and provenance notice in `licenses/`. No whole upstream code batch was imported.
- ULTRON had 355 additional paths at the compared baseline. Its safety, planning, verification, and documentation layers must not be replaced by older upstream implementations.
- The audit covered a sample of 100 issue results and 40 PR results. It also found many community forks, but it did not review every fork or every GitHub mention.
- The current source licence is CC BY-NC 4.0. The checked-in `LICENSE` attributes the source to FatihMakes and prohibits commercial use. Preserve notices. Do not assume older snapshots or third-party assets have the same licence.
- Gesture PRs #167/#168 are candidates only. Their PR file lists did not include regression tests; they need central policy/sensor consent and model-integrity work.
- Multi-agent PR #165 was open/non-mergeable at audit and included a tracked `config/api_keys.json`. Do not import it wholesale.
- MCP, tool routing, multi-step planning, audit, and tool-description triggers already exist in ULTRON. Do not build duplicates merely because an upstream proposal asks for them.
- Upstream PR #169's morning-brief change was adopted independently: startup briefing now defaults off, saved boolean choices are preserved, and malformed values fail closed. Regression tests are in `tests/test_suite_assistant.py`.

Third-party asset provenance is kept separately in [`licenses/THIRD_PARTY_NOTICES.md`](../licenses/THIRD_PARTY_NOTICES.md), with the full MediaPipe licence bundle in [`licenses/MEDIAPIPE-LICENSE.txt`](../licenses/MEDIAPIPE-LICENSE.txt). Do not assume the root CC BY-NC licence replaces a third-party component's own terms.

The strategy is selective reuse. Review the exact source SHA and licence, compare the code against ULTRON, port the smallest useful change, and test it. See the upstream research file for the repository list, PR/issue decisions, risks, and next priorities.

## 11. Agent operating instructions for a new chat

1. Read this file, then `AGENTS.md`, `docs/AGENT_MAINTENANCE.md`, `WORKING-PHILOSOPHY.md`, `DECISIONS.md`, `ARCHITECTURE.md`, and `GATEKEEPERS.md`.
2. Inspect current main SHA, branch refs, worktree, PRs, and latest Actions results. Do not trust dates/counts copied from older handovers without rechecking.
3. Run `python scripts/agent_workspace.py` and inspect all changed/uncommitted paths before editing.
4. Follow the task-size and documentation-impact system. Medium/large work must update the canonical handoff and every affected guide before completion.
5. Preserve owner decisions and existing work. Do not add scope because an older roadmap suggested it.
6. Report exact commands, commits, CI run IDs, proof counts, failures, skipped checks, known limits, and what was not inspected.
7. No secrets, tokens, local personal files, or private machine data belong in this public repository.
8. Before product work, complete the two visible repository-maintenance actions in this handoff: delete the two already-archived merged branch refs through the guarded archive workflow, and configure/read back the three required `main` status checks. Do not claim either action is complete until GitHub confirms it.

## 12. Read-first navigation

1. [Repository README](../readme.md)
2. [Agent maintenance system](../docs/AGENT_MAINTENANCE.md)
3. [MARK/JARVIS upstream research](../docs/UPSTREAM_RESEARCH.md)
4. [Architecture](../ARCHITECTURE.md)
5. [Owner decisions](../DECISIONS.md)
6. [Proof status](../GATEKEEPERS.md)
7. [Documentation index](../docs/INDEX.md)
8. [Branch review and archive](../docs/BRANCH_REVIEW.md), [archive restore details](../docs/BRANCH_ARCHIVE.md)
9. [Engineering journey](history/journey.md), [session record](history/session-log.md)

A new chat must be able to delete its predecessor without losing project knowledge. This file and the linked repository records are the handoff.
