# ULTRON — canonical project handoff

**Last full repository audit:** 2026-11-20 — a review pass on branch `arena/850afbc9-ultron-agi-like-jarvis`, cut from `main` at `cf02c0e`, followed on 2026-11-21 by a second review whose twelve findings were all fixed, and then by the self-change work that was left (the button, the boot guard, the referee file `core/self_change.py`). See "Review pass 2026-11-20 and its follow-ups 2026-11-21" below for where the changes are. On 2026-11-22 that branch was merged as PR #22 (`df115bb`), and a follow-up branch, `arena/8c75f708-ultron-agi-like-jarvis`, added the way new Mark releases are followed (section 10).

- **Repository:** `tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS`
- **Visibility:** Public
- **Permanent integration branch:** `main`
- **Current `main` HEAD:** `2f16a98` (2026-11-25 15:23 UTC, the merge of PR #37; read from GitHub on 2026-11-25, before the pull request that carries this change was merged).
- **Last green full `verify` run on `main`:** [45644578999](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/45644578999) on `2f16a98` (2026-11-25, the merge of PR #37): Linux and Windows both passed, and so did the fast gate. The Linux job had crashed with a segmentation fault (exit -11, shown by the runner as 245) in the provider self-test on the first attempt of two runs, [45007979707](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/45007979707) on `df115bb` and [45459189900](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/45459189900) on PR #36, and passed when re-run (2 of 29 Linux runs from 2026-11-21 to 2026-11-25). The cause was found and reproduced on 2026-11-25: a background voice-list download that finished after its settings panel had been destroyed emitted a signal on freed memory (`ui.py` `ProvidersOverlay`, `providers/tts_piper.py` line 170). PR #37 fixed it (`ui.py` `_LiveRelay`) and added `tests/test_providers_panel_threads.py`. The Linux jobs since then (the pull request's two runs and the merge's run) all passed, which at the earlier rate (2 of 29) is weak evidence, so that the crash is gone from CI is still not known and needs more Linux runs. The last green run before 45007979707 was [43485438663](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/43485438663) on `252a299` (2026-11-13, PR #20); every push to `main` from 2026-11-15 to 2026-11-20 had a failed or cancelled `verify` run (14 failed, 8 cancelled). Two causes were found by running the suite: from `60ee7a3` the provider self-test counted writes that the atomic settings writer no longer makes, and from `c57d0e4` every plugin call raised in the dispatcher. Both were fixed in PR #22, and 45007979707 was the first green full run on GitHub since.
- **Withdrawn:** this page used to call `c57d0e4` the "last fully verified baseline" and run 43012781547 "current `main`". The `verify` run for `c57d0e4` was cancelled by the next push, and 43012781547 ran on `2b31d77` (2026-11-11).
- **Latest fast branch gate:** `fast-checks` passed on `main` at `cf02c0e` while `verify` failed on the same commit: none of its groups called a tool or ran the provider self-test, which is where the two faults were (the review branch adds a dispatch smoke group; the provider self-test stays in `verify`). The last fully verified fast gate on `main` before that is [42876494264](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42876494264) (5/5 groups).
- **Live branches (read 2026-11-25, after #37 was merged):** `main`; `feat/computer-use-skills` (open as PR #21, "Know what is open, and load the written skills"); `arena/850afbc9-ultron-agi-like-jarvis` (merged as PR #22 and kept, because delete-branch-on-merge is off in the repository settings, which the account this work runs under cannot change: HTTP 403); `arena/8c75f708-ultron-agi-like-jarvis` (PRs #33 and #35 were merged from it on 2026-11-24 and #36 and #37 on 2026-11-25, and it carries the next piece of work). Dependabot's branch for PR #34 was removed by Dependabot when that pull request was closed. PR #20 was merged on 2026-11-13, PR #22 on 2026-11-22, PRs #33 and #35 on 2026-11-24, and PRs #36 and #37 on 2026-11-25.
- **Open pull requests (read 2026-11-25, after #37 was merged):** #21, and the pull request that carries this change. Dependabot's #34 (one grouped update of 24 Python requirement lower bounds, opened minutes after #33 was merged) was read and closed without merging on 2026-11-25: on Python 3.11, which the readme supports, `pip install -r requirements.txt` from it stops at `numpy>=2.5.5` (numpy 2.5 needs Python 3.12); it moved the PyQt6 ceiling that `requirements.txt` keeps below Qt 6.12 on purpose; and it jumped whole major versions of `google-genai`, `opencv-python`, `cryptography` and `pillow`. Its checks were green because CI installs its own short list and never reads `requirements.txt`. Dependabot's #23 to #32 were closed without merging at the owner's request; `.github/dependabot.yml` allows one grouped pull request per ecosystem. Closing a pull request by hand records no ignore, so Dependabot could propose the same update again; the pull request that carries this change makes its pip entry keep to the pins (`increase-if-necessary`, and PyQt6 minor and major releases ignored) and adds `.github/workflows/install-check.yml`, which installs the real `requirements.txt` on Windows for each Python the launcher accepts. Neither has run on GitHub yet.
- **Archive ruleset:** Active ID `26923169`; protects `refs/tags/archive/**/*` from updates and deletion.
- **GitHub About description:** set on 2026-11-12 to "A voice-first desktop AI agent with computer control, web research, memory, and safety gates." Read back verified.
- **License:** CC BY-NC 4.0. Attribution to FatihMakes / 0101e5 is required. Commercial use is not permitted; see `LICENSE`.


This file is the durable handoff. A new chat or agent must be able to continue from the repository without access to earlier conversations. Read this page first, then follow the linked source-of-truth documents. Do not infer that every planned capability is complete because the test gates and main integration are complete.

## 1. Current status

This snapshot was read from GitHub on 2026-11-20. The current source of truth is `main` at `cf02c0ec75fef95068ce89832175c242b0c9f834`. The last green full `verify` run on it is for `252a299` (2026-11-13). The last application/test baseline recorded with counts below is `b80919314f391e15ddd86e2860c2e4d66057b15b` (2026-11-10), which predates the failing runs. The facts about the 2026-11-12 state that follow are kept where they are still true.

- PR #15 was promoted to `main`; PR #16 was closed without merging, but its final web-app tree was included in the promoted candidate.
- Documentation PR #17 and fast-test PR #18 are merged. PR #18 was squash-merged as `eeacaf2ae2224edd91074a3853ae0ecff47c41a7`.
- PR #19, `chore: trigger CodeRabbit review`, is **closed without merging** (`merged=false`). Do not treat it as a durable CodeRabbit integration or assume an AI review check is required.
- The original ten obsolete development branches were archived and deleted in [run 42779866199](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42779866199).
- The last two merged temporary refs (`docs/repository-doc-audit-2026-11-10`, `ci/fast-branch-gate`) were deleted by the guarded `Archive reviewed branch tips` workflow on 2026-11-12, [run 43080080807](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/43080080807). It PASSED, deleted exactly those two refs, and kept all 12 archive tags. Branch list on 2026-11-20: `main` plus `feat/computer-use-skills` (open as PR #21); PR #20 was merged on 2026-11-13.
- There are 12 protected recovery tags. They were re-verified by the guarded cleanup run above.
- Archive ruleset **ID 26923169** is Active. It protects `refs/tags/archive/**/*` against updates and deletion, allows tag creation, and has no bypass actors.
- Required-check merge blocking is **verified** (2026-11-12): `main` protection was written and read back through the GitHub API with the three required checks `fast offline gate`, `linux — suite and instruments`, and `windows — the machine the claims are about`; `enforce_admins` is false. Re-read on 2026-11-20 through `GET /branches/main` (same three checks, `enforcement_level: non_admins`). See `docs/TEST_AUTOMATION.md`.
- The GitHub repository About description was set on 2026-11-12 to "A voice-first desktop AI agent with computer control, web research, memory, and safety gates." and read back verified from the repository metadata.
- The separate private owner-development repository exists but is empty. It has no commits or files and is not an active canary channel. The public repository remains the active source of truth.

### Latest full application/test verification

Full Linux/Windows run: [42876494213](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42876494213). Both jobs completed successfully on current `main` SHA `e1237d2e82ad7b981362f009baf568f7873415ea`. The three commits after application/test baseline `b80919314f391e15ddd86e2860c2e4d66057b15b` were documentation-only. The baseline measured 2,073 tests per platform, 1,000 stress scenarios, and 15 targeted mutations per platform; the current full workflow reran the same verification scripts successfully.

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

Fast branch gate: [42876494264](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42876494264). It parsed 309 Python files and passed 19 fast-runner edge tests, 30 policy/confirmation tests, 8 README contract tests, and 1,000 deterministic stress scenarios. Changed-file Ruff, Git diff checks, and generated `docs/MAP.md` validation passed. All five fast-gate groups passed. The stress suite made no live model or provider request.

The archive workflow [42876494242](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42876494242) passed and verified all 12 exact-SHA archive tags. It ran archive-only mode and preserved all branch refs.

**Evidence limits:** PARTIAL and SKIPPED are not passes. Hosted CI cannot prove the owner's microphone, speaker, camera, GPU, display scaling, browser installation, provider credentials, or interactive workflows. Run `python scripts/verify_all.py` on the target Windows machine when authorized.

Historical promotion evidence remains in `docs/MAYBE_COMPLETE.md`; those runs are not the latest verification.

### Review pass 2026-11-20 and its follow-ups 2026-11-21 (branch `arena/850afbc9-ultron-agi-like-jarvis`)

What changed and where it lives: `CHANGELOG.md` ("Second Windows run", "First Windows run of this pull request", "Follow-up: what was left", "Follow-up to the review pass" and "Review pass, 2026-11-20"), the new rows in `DECISIONS.md`, and the account in `docs/engineering/SESSION_LOG.md` (four entries). The last follow-up is the self-change work that was left: the second confirmation of `self_modify` is a button press on a banner listing every changed line; `diff()`, the rehearsal copy (it now has `.github` and a repository of one commit) and line endings were fixed in `core/self_change.py` (a referee file, edited with the owner's go-ahead); a new `core/boot_guard.py` puts back a code change that stops the program from starting (run by `scripts/bootstrap.py`, so only a start made with `run.bat` or `run.ps1`); `core/custom_gate.py` refuses every call that is not read-only while a confirmation is waiting; `config/self_change/` is ignored by git and `ship` refuses stray data in `memory/` and `config/`. The follow-up fixed twelve findings from a second review of the first pass (read by the same agent that wrote it, with open-code-review's checklist; 55 of the 103 changed paths, mostly tests and documents, were set aside by the tool and not reviewed). Linux, Python 3.11.2, this sandbox; nothing here ran on GitHub, Windows, macOS, Rust or Go.

| Check | Result |
|---|---|
| `scripts/verify.py`, the package set `verify.yml` installs | exits 0: suite 2,754 tests, 0 failed, 39 skipped; provider and UI self-tests 108 passed, 0 failed; 1,000 stress scenarios passed; 15 of 15 seeded mutations detected; no new module-map gap (22 inherited); migration checks passed |
| `scripts/verify.py`, full package set | exits 0: suite 2,754 tests, 0 failed, 10 skipped |
| Proof gate | 24 PROVEN, 13 PARTIAL, 0 FAILED (37 claims), the same as the last hosted Linux run |
| Hosted Windows run 45003997382 (commit `2377b3a`) | suite 2,754 tests, 0 failed, 71 skipped; provider and UI self-tests 108 passed; 1,000 scenarios; 15 of 15 mutations; proof gate 28 PROVEN, 8 PARTIAL, **1 FAILED** (`acts`: the file tool wrote outside the owner's folders) |
| Drive-wide file access made opt-in (`actions/file_controller.py`) | four new tests in `tests/test_file_controller_hardening.py` red on the old file, green now; bare Python 3.11 with none of the repository's packages installed: 2,072 tests before, 2,076 after, the same 30 environment failures in both; the full chain was not re-run here and the hosted run on the pushed commit is the record |
| Fast gate (`scripts/fast_verify.py`) | 6 of 6 groups, 357 Python files parsed |
| Lint ratchet against `cf02c0e` | 146 findings in the 88 touched Python files, 156 at the base: nothing got worse |
| Debt ceilings (`tests/test_suite_assistant.py`) | all within; at their ceilings: `long-function` 97, `typed-exception-discarded` 82, `hardcoded-address` 37, `deep-nesting` 26, `address-in-constant` 19, `duplicate-body` 11, `dangerous-call` 1 |
| AST guardian over this repository's Python | refuses 117 of 357 files, 116 under the original; the one newly refused is `custom_jarvis/addon_runtime.py` |
| A full rehearsal of this tree (`core.self_change.rehearse(full=True)`, in a copy of it) | passes: exit code 0 in 112 s, run in a Linux copy of this tree (before the fix: 9 failures and 6 errors in 74 s) |
| Before (`cf02c0e`, same two environments) | cf02c0e ran 2,101 tests and 32 failed in both environments (29 from the plugin dispatcher fault, 3 from the repository's own debt-ceiling tests) |

Known limits: **Windows has been red twice on this pull request, for different reasons** (first run, 2026-11-21, 44930501422: 2,751 tests, 8 failures and 1 error, all in tests written on Linux, fixed in `2377b3a`; second run, 2026-11-22, 45003997382: the whole suite step passed on Windows, 2,754 tests with 71 skipped, self-tests 108 of 108, 1,000 scenarios and 15 of 15 mutations, and then the Windows proof gate, which had never run there in this pull request, failed one claim: 28 PROVEN, 8 PARTIAL, 1 FAILED, `acts`, because the file tool's drive-wide access was on by default; the change that follows from it is in `CHANGELOG.md`, "Second Windows run", and has not been run on Windows: the pull request's checks are the record of the next run); the fast gate, the Linux job and the web checks passed on the first run, and the workflow edits (`fast-checks.yml`, `verify.yml`, `webapp.yml`, `reviewdog.yml`, `archive-reviewed-branches.yml`) have therefore run once on GitHub (the `verify.yml` proof-gate step was simulated under `bash -eo pipefail` before that; with it, a failing gate now fails the Linux job, which used to hide it); `native/ultron-core/src/ipc/server.rs` and `native/ultron-core/src/process/supervisor.rs` were edited by reading and have never been compiled (the supervisor is called by nothing; its Job Object limits are one call now, and `tests/test_supervisor_source.py` checks only the shape of the source); the new prompt-change banner was drawn and read on an offscreen display only; the self-change button, the boot guard (never run through `run.bat` or `run.ps1`) and the dispatcher check were tested with fakes and real child processes on Linux, not with the real window on Windows; CI uses Python 3.12 and 3.13 is supported, and only 3.11 was run; the Windows-only download-name fix in `dashboard/server.py` was found by reading.

Decisions needed from the owner: (1) read the referee-file edits first: `core/policy.py` (one row) and `core/ast_guardian.py` (edited in both passes; its header now lists what it cannot see); (2) whether administrators may bypass the required checks (`enforce_admins` false, so a failing commit can still reach `main` by direct push); (3) keep or revert the lint ratchet (it counts per file and rule, so fixing one finding and adding another of the same rule passes); (4) `laptop_wide_access` (every drive, Windows only) is now off unless the settings hold a saved `true`, after the Windows proof gate showed that a write outside your folders was not refused while it was on: confirm that, or tell me to restore the old default and change the proof gate's `acts` claim instead (a referee-file edit I will not make without your word; `DECISIONS.md`, open question 4); (5) whether to close the two gaps left in the dispatcher check (a call sent in the same message as the call that raises a banner; anything that does not come through `core/custom_gate.py`), which `DECISIONS.md` lists as open question 5; (6) the archive workflow's push trigger; (7) lower the debt ceilings to the new measures, or not; (8) delete or keep the unused `dashboard/static/crypto-js.min.js`; (9) read the edits to `core/self_change.py` (a referee file; edited with your go-ahead in the third pass: `diff()`, the rehearsal copy, line endings, a UTF-8 check, the new off-limits files, the watch for the boot guard) and the new `core/boot_guard.py`, which are the part of this branch that decides what the program may do to itself; (10) which "100%" you mean by the question left open since the RSI assessment.

Next actions: read the third Windows run and fix what it shows; the Notion handover page was not updated. Do not merge before the three required checks (the Windows one included) are green: `main` is protected.


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
- `docs/specifications/` & `docs/engineering/`: technical system overview and historical records.

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
- **Referee files:** `core/policy.py`, `core/confirm.py`, `core/self_change.py`, `core/boot_guard.py`, `scripts/proof_gate.py`, `scripts/bootstrap.py`, `run.bat`, `run.ps1`, and secret-bearing config are protected by the project change rules (the last four, and `boot_guard`, are the net that puts a bad self-change back; `core/self_change.py` refuses to write any of them). Do not weaken their controls or bypass rehearsal/confirmation.
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
- `.github/workflows/install-check.yml`: not a required check. Installs the real `requirements.txt` on a clean Windows machine for each Python the launcher accepts (3.11 to 3.13), runs `scripts/check_install.py` after the launcher's own setup, and runs the whole suite on Linux with every package installed. Runs when a requirements or launcher file changes, on the 15th of each month, and by hand.
- `.github/workflows/upstream-watch.yml`: read-only. Compares Mark LVII with the pin nine times a month and keeps one issue open when it moved (see the following-Mark paragraph below).
- `.github/workflows/webapp.yml`: webapp checks.
- `.github/workflows/reviewdog.yml`: static Reviewdog/Ruff reporting.
- `.github/workflows/archive-reviewed-branches.yml`: guarded exact-SHA archive workflow. Pushes to `main` run archive-only mode; manual deletion mode checks the live tag ruleset, reviewed refs, tags, and open PRs, and never deletes `main`. After branch cleanup, archive-only runs resolve the curated candidate from its protected archive tag and verify its exact promotion SHA.

## 7. Repository hygiene

- `main` is the only permanent integration branch. Merged short-lived refs are deleted by the guarded archive workflow once their recovery tags exist; the last two went on 2026-11-12 (run 43080080807). The open feature branch `feat/provider-failover-wiring` is temporary work for PR #20.
- Twelve protected recovery tags remain under `archive/2026-11-10/`. They are history/recovery refs, not active branches.
- Do not delete or rewrite recovery tags, `main`, project history, tests, or user-owned state as generic cleanup.
- No workspace size/file-count budget is active. Keep caches, build outputs, temporary test files, and machine state out of Git because they are not auditable and may contain private data.
- Do not remove tracked historical records such as `log.txt`, `HANDOFF.md`, or `verification-results.txt` merely because they are large. Check their role and references first.
- Root pointer files `ALGORITHMS.md`, `CUSTOM_ULTRON.md`, and `PUBLISH.md` intentionally preserve old links and packaging contracts. Their full guides live under `docs/reference/`.
- `docs/MAP.md` is generated. Regenerate only when source modules/tests change.
- The repository's public landing page is `readme.md` (lowercase).

## 8. Current limitations and unfinished work

These limits matter. Do not advertise the product beyond them.

1. **Provider failover (conversation path):** wired on 2026-11-12, pending merge, consent-first. `RoutedLLM.chat` walks the routing table's candidates: a rung that fails before it answers is rested (quota 5 min, gone-for-today, unavailable 30 min — the one-shot ladder's rests) and the next allowed rung answers; a rung that fails after words were spoken raises instead of switching. `main.py` registers every other configured LLM as a fallback rung (local first) and reads `paid_fallback_consent` / `data_fallback_consent` / `local_fallback_consent` from `config/api_keys.json`; a paid, data-sharing, or on-this-machine rung never answers without its flag, and an explicitly chosen local primary does not need one. Every cloud catalog row carries `shares_data: True` until the service's training policy is verified (fail-closed; `providers/llm_openai.py`). Provider failure text is URL/credential-scrubbed before it reaches the log (`core/routing_runtime.py` `_scrub`). Offline tests prove the logic; a live outage across real providers is still unproven (owner-machine evidence). One consent flag still covers all hosted accounts; there is no per-provider consent. PR #20.
2. **ULTRON Web:** authentication/workspace shell only; no Python worker, chat persistence, cross-device memory, or enabled composer. Sign-in also depends on Supabase/Google OAuth configuration.
3. **Deployment:** no confirmed Vercel project/preview deployment in this handoff. Team authorization is needed before discovery/configuration.
4. **Self-change security:** temporary rehearsal is not OS-level isolation; hostile candidate code can use the current user's permissions.
5. **MCP process security:** external MCP processes are not sandboxed and inherit the parent environment.
6. **Release updates:** no complete signed publisher/downloader, production keyring, A/B updater, or supervisor/worker handoff.
7. **Hardware proof:** CI cannot verify every actual owner device, microphone, speaker, camera, GPU, DPI, browser installation, or real provider/account workflow.
8. **Independent review:** Reviewdog/Ruff are static checks. They are not a full semantic security audit or independent human review.
9. **Code review depth:** previous promotion review was risk-focused, not a line-by-line independent review of every changed line.
10. **Private owner-development repository:** it exists but is empty (no commits or files). No private development or canary workflow is active. The public repository remains the active source of truth.
11. **Merge enforcement:** verified on 2026-11-12. `main` protection was configured and read back through the GitHub API: `fast offline gate`, `linux — suite and instruments`, and `windows — the machine the claims are about` are required status checks; `enforce_admins` is false, so an administrator can push a failing commit to `main`; that is how `verify` stayed red from 2026-11-15. See `docs/TEST_AUTOMATION.md`.

## 9. Project history and branch consolidation

- The project started from `FatihMakes/Mark-LVI` and evolved through multiple feature, agent, and integration branches.
- Branch adoption/rejection rationale is preserved in `docs/BRANCH_REVIEW.md`.
- The curated candidate `ultron/curated-promotion-2026-11` was promoted as application commit `bd4b43d16fdf27b495209678ed72b41f21408d7c`.
- The original ten historical non-main tips were preserved as exact-SHA tags, then their refs were deleted in workflow run 42779866199. Two later merged PR branch tips were added to the archive list and verified in run 42830329517.
- The two merged temporary branch refs were deleted by the guarded archive workflow on 2026-11-12, [run 43080080807](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/43080080807) (PASSED; 12 recovery tags preserved). Branch list now: `main` plus the open PR #20 feature ref. Manual guarded deletion remains the only sanctioned way to remove a branch ref.
- Full SHA evidence and restore instructions are in `docs/BRANCH_ARCHIVE.md`. The adoption/rejection audit is in `docs/BRANCH_REVIEW.md`.

The GitHub About description was set on 2026-11-12 to "A voice-first desktop AI agent with computer control, web research, memory, and safety gates." and read back verified from the repository metadata.
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

**Following new Mark releases (added 2026-11-22).** Mark moves about every two weeks (the first line of its `readme.md` changed 12 times between 2026-06-06 and 2026-11-11) and ULTRON is a copy, not a GitHub fork, so git has no shared history to merge. `scripts/upstream_sync.py` reads upstream and says what changed and where it collides with ULTRON; a scheduled job, `.github/workflows/upstream-watch.yml` (nine times a month, on days 1, 4, 7, 10, 13, 16, 19, 22 and 25 at 06:17 UTC; the owner changed it from weekly on 2026-11-24), keeps one issue open with the answer. It applies nothing: porting waits for the owner's go, one tested slice at a time, switched off by default. Three features stay out whatever a new Mark brings (E1 news read out when ULTRON opens, E2 a news check every 30 minutes, E3 routines that run tools by themselves at launch), and the window layer (`gui/`) is adopted last. The pin, the ledger and the exclusions are `docs/upstream/PIN.json`, `docs/upstream/LEDGER.json` and `docs/upstream/EXCLUSIONS.json`; the guide is [`docs/UPSTREAM_SYNC.md`](../UPSTREAM_SYNC.md). Mark LVII (`752ff61`, 2026-11-11) was reviewed on 2026-11-22: 54 files differ. On 2026-11-24 the owner said go and four small pieces were taken (the wake word forgets what it heard, Windows scroll units, Piper voices downloaded whole or not at all, and mute that means muted: "unmute" no longer mutes); `docs/UPSTREAM_RESEARCH.md` section 10 lists what was taken and what is deferred, and the rest waits for the owner's go, a piece at a time.

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
8. The two repository-maintenance actions this handoff used to list — deleting the two archived merged branch refs and configuring/reading back the three required `main` status checks — are both complete and GitHub-verified (2026-11-12, runs and read-backs recorded in sections 1 and 9). Re-check the live refs before acting on any older snapshot.

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
