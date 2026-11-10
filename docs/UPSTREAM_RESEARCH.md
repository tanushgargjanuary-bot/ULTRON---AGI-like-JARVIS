# Upstream research — FatihMakes, MARK, and JARVIS

**Audit date:** 2026-11-10  
**Primary source:** [FatihMakes/Mark-LVI](https://github.com/FatihMakes/Mark-LVI)  
**Primary source main commit inspected:** `0101e540ac4b16cc3a862d9979e08fefcc1c7a01` (2026-11-04)  
**ULTRON comparison baseline:** `76484ebc4cbf4b5d4a23889ed6eeddfbf844083c`  
**Purpose:** Preserve upstream research and turn useful MARK/JARVIS work into safe, traceable ULTRON improvements.

## 1. What this audit covers

The user asked ULTRON to make use of the work published by FatihMakes around the MARK/JARVIS assistant.

The audit covered:

- All eight public repositories returned for the FatihMakes GitHub account.
- The current `FatihMakes/Mark-LVI` main tree and README.
- A file-path and blob-SHA comparison between that upstream tree and ULTRON.
- A review sample of 100 MARK-LVI issue-search results.
- A review of 40 MARK-LVI pull-request search results, with detailed review of the most relevant security, gesture, orchestration, audio, and UI proposals.
- A global repository search for `Mark-LVI`, which returned many forks and derivatives. The search is not an exhaustive inventory of every fork or every GitHub mention.

This is a dated snapshot. A later agent must re-check the upstream main SHA, open PRs, license text, issue search, and selected source files before using new material. Do not treat an old PR or issue as current code.

## 2. Project lineage and official repositories

The current project is called **MARK LVI** in the upstream README. JARVIS is the assistant persona and user-facing identity. Earlier public repositories show the earlier Mark X and Mark XXXIX-OR stages. ULTRON is a derivative project with a different product name and a substantially expanded architecture.

| Repository | Observed role | Last inspected push / source state | ULTRON treatment |
|---|---|---|---|
| [Mark-LVI](https://github.com/FatihMakes/Mark-LVI) | Current primary MARK/JARVIS desktop assistant | Main commit `0101e540ac4b16cc3a862d9979e08fefcc1c7a01`, 2026-11-04 | Primary reference for current upstream changes, issues, PRs, and license |
| [Mark-XXXIX-OR](https://github.com/FatihMakes/Mark-XXXIX-OR) | Earlier cross-platform assistant with planner, executor, task queue, and an orchestration experiment | Main commit `eac6378a2411caaca6b382ecc5c04b3c492b5851`, 2026-05-10 | Historical architecture reference; do not copy its older runtime wholesale |
| [Mark-X](https://github.com/FatihMakes/Mark-X) | Earlier Mark X codebase | Main commit `a1868c9cc02165e64f82d54d11a6ab3b6553f362`, 2026-02-01 | Historical reference |
| [Mark-X.1](https://github.com/FatihMakes/Mark-X.1) | Earlier Mark X.1 iteration | Main commit `5dbfff33a65d6970573191aa23ad3b57576642e7`, 2026-02-08 | Historical reference |
| [Mark-X-TR](https://github.com/FatihMakes/Mark-X-TR) | Turkish-language Mark X variant | Main commit `29fbca3fc9a5bc415fe5a6eceffc73eeb7489715`, 2026-02-01 | Historical language/reference material only |
| [Jarvis-Mark-X](https://github.com/FatihMakes/Jarvis-Mark-X) | Earlier Jarvis-branded Mark X snapshot | Main commit `c780b2ef21c18a426b438bc2960ff9c8ffa49220`, 2026-02-01 | Historical reference |
| [AI-Assistant-for-Computer](https://github.com/FatihMakes/AI-Assistant-for-Computer) | Early GUI voice assistant prototype | Main commit `7d14a74ca60175efe054bb39bc591b37042df5e5`, 2025-12-15 | Historical reference |
| [AI-Assistant-1.1](https://github.com/FatihMakes/AI-Assistant-1.1) | Earlier aircraft/voice assistant prototype | Main commit `5d2c052b7052de81fa29fa72e66408656dfd98e4`, 2025-12-15 | Historical reference |

The inspected trees for the older snapshots did not show a root `LICENSE` file. That does not prove that the material is unlicensed or that it has no rights holder. Do not import code from those snapshots until its reuse terms are confirmed.

## 3. Direct source-tree comparison

The direct comparison used the primary MARK-LVI main tree at `0101e540ac4b16cc3a862d9979e08fefcc1c7a01` and the ULTRON main tree at `76484ebc4cbf4b5d4a23889ed6eeddfbf844083c`.

| Measurement | Result |
|---|---:|
| Files in the inspected MARK-LVI tree | 78 |
| Files in the inspected ULTRON tree | 433 |
| Upstream file paths already present in ULTRON | 78 / 78 |
| Upstream paths missing from ULTRON | 0 |
| Shared paths with identical Git blob SHA | 16 |
| Shared paths with different Git blob SHA | 62 |
| Additional ULTRON paths not present in upstream tree | 355 |

**Interpretation:** ULTRON already contains every file path from the inspected current MARK-LVI tree. It is not missing a batch of upstream files. It has diverged in 62 shared files and added 355 paths for its own safety, planning, tests, tooling, desktop/web surfaces, packaging, and documentation.

The 16 identical shared files at the time of comparison were:

- `actions/background_monitor.py`
- `config/__init__.py` and `config/jarvis.ico`
- `core/__init__.py`, `core/code_checks.py`, `core/lazyimport.py`, and `core/platform_support.py`
- `core/stt.py`
- `dashboard/__init__.py`
- `dashboard/static/crypto-js.min.js`
- `memory/__init__.py`
- `plugins/__init__.py` and `plugins/_template.py`
- `providers/__init__.py`, `providers/audio.py`, and `providers/base.py`

The 62 changed shared paths include `main.py`, `ui.py`, `core/`, `actions/`, `providers/`, `memory/`, `dashboard/`, `requirements.txt`, `.gitignore`, and documentation/prompt files. A different SHA does not mean ULTRON is better or worse. It means the content must be reviewed. Eighteen of the 62 changed shared files have now had focused diff comparisons; 44 changed shared paths remain for review. Do not overwrite the ULTRON copy with upstream code simply because it is newer.

### Focused semantic review: 12 changed shared files

A first focused review covered 12 high-risk shared files. It was a targeted comparison of changed lines and responsibilities, not a full independent security review of all 62 files.

| File | Difference found in ULTRON | Decision |
|---|---|---|
| `core/audio_devices.py` | Adds failure telemetry around device probing and endpoint resolution. The main device-selection pattern is already shared. | Keep ULTRON's failure reporting. No upstream port identified. |
| `core/gemini.py` | Records live-turn failures and selects the critic provider through ULTRON's purpose-based routing layer. | Keep ULTRON routing and telemetry. Do not replace them with a direct sidecar selector. |
| `core/wake_word.py` | Records failures from feed, drain, and stop paths. | Keep the extra diagnostics. |
| `memory/config_manager.py` | Uses shared read/modify/write helpers, config-shape validation, and safer write/error handling. The code is larger because it handles failure cases. | Keep ULTRON's managed settings path. **This is not OS credential-manager support**; the credential-store request remains open. |
| `actions/web_search.py` | Records backend failures and gives the model a more specific distinction between search and the policy-aware `web_read` path. | Keep the narrower trigger and failure records. |
| `.gitignore` | Keeps comments on separate lines, ignores temporary/broken config copies, and excludes more local runtime state. | Keep ULTRON's rules. Upstream's inline comments can make secret patterns fail to match. |
| `core/tts.py` | Imports `sounddevice` only when playback is requested, records failures, and falls back to the system voice when primary speech fails. | Keep the lazy-import and fallback behavior. |
| `dashboard/server.py` | Defaults to loopback, requires explicit owner permission and HTTPS for LAN command access, and fixes firewall-status and undefined-port defects. | Keep ULTRON's stricter network boundary. Do not copy upstream firewall-opening behavior. |
| `actions/computer_control.py` | Escapes model-supplied window titles before PowerShell use, records failures, and declares the missing drag coordinates in the schema. | Keep the input escaping and corrected tool contract. |
| `actions/file_controller.py` | Adds a sensitive-directory and sensitive-file deny-list on top of root confinement. It covers credential stores and browser profiles, not just paths outside the workspace. | Keep the stronger data-protection boundary. |
| `core/plugin_loader.py` | Integrates candidate-generation loading, explicit registry inspection, and failure tracking for safe action/plugin refresh. | Keep the ULTRON leaf-generation model. |
| `providers/engine_pipeline.py` | Adds a bounded partial-tool-result grace period and turn-detection/voice-style handling, while recording failures. | Keep the existing pipeline and its regression tests. |

No upstream-only behavior from these 12 focused comparisons was identified as a safe direct copy. The useful result was validation of ULTRON-specific improvements and several concrete tests or threat cases. The next audit still has **50 of the 62 changed shared paths** to inspect. Start with `main.py`, `ui.py`, `core/appidentity.py`, `core/action_loader.py`, `actions/browser_control.py`, and `actions/dev_agent.py`.

### Additional focused diff scan: six integration files

A second pass checked six more large or security-relevant shared files. This scan used exact upstream and ULTRON blobs at the audited commits and compared normalized lines. It identifies differences for follow-up; it is not a full manual audit of every function.

| File | ULTRON difference observed | Decision |
|---|---|---|
| `main.py` | Adds explicit reconnect policy, local fallback state, action audit, declaration sanitization, and a controlled response when a local engine cannot start. | Keep ULTRON's orchestration and failure path. Do not replace it with the upstream lifecycle wholesale. |
| `ui.py` | Uses runtime identity and supports multiple configured provider APIs in first-run setup. It also includes additional UI/threading and recovery behavior. | Keep the provider-flexible UI and existing Qt-thread rules. |
| `core/appidentity.py` | Adds failure records when process/window identity probes fail. | Keep the diagnostics. |
| `core/action_loader.py` | Sanitizes tool declarations to the provider's accepted schema, coerces malformed arguments safely, reports discovery/runtime failures, and supports generation-aware import. | Keep these checks. They address real provider rejection and tool-call faults. |
| `actions/browser_control.py` | Adds failure/timeout reporting and declares parameters the handler already reads, instead of silently forcing defaults. | Keep the corrected schema and failure records. |
| `actions/dev_agent.py` | Resolves the VS Code executable and invokes it with `shell=False`; the upstream version shown in the diff uses `shell=True`. | Keep the shell-free launch. Do not regress to shell interpolation. |

The focused scan has now covered 18 shared files in total. It continues to support selective ULTRON-first integration. **No upstream code from these 18 files has been copied.** The next 44 shared paths still need review.

### Existing capability map

The current upstream README describes features in these areas. These are upstream claims; ULTRON agents must check the implementation and its own tests before repeating a claim.

| Upstream area | Existing ULTRON implementation to inspect first | Intake status |
|---|---|---|
| Voice, wake word, STT/TTS, and audio devices | `providers/`, `core/audio_devices.py`, `core/wake_word.py`, `core/echo.py`, `core/reconnect_policy.py` | Already represented; use upstream issues as regression-test ideas |
| Desktop, window, file, and browser control | `actions/`, `core/ui_*.py`, `core/app_resolver.py`, `core/paths.py` | Already represented; do not replace central policy or path guards |
| Plugin discovery and self-describing tools | `plugins/`, `core/action_loader.py`, `core/plugin_loader.py`, `core/tool_catalog.py`, `core/tool_prompt.py` | Already represented |
| Undo and verified outcomes | `core/undo.py`, `custom_jarvis/evidence.py`, `core/custom_gate.py` | Already represented; compare exact edge cases |
| Local and hosted providers | `providers/`, `core/routing.py`, `core/routing_runtime.py`, `custom_jarvis/local_fallback.py` | Already represented; general live fallback is still a known limit |
| Model/session continuity | `core/reconnect_policy.py`, `custom_jarvis/plan_state.py`, `custom_jarvis/conversation` related modules | Partly represented; verify real session resumption on owner hardware |
| Memory and recall | `memory/`, `custom_jarvis/knowledge.py`, `custom_jarvis/shortlist.py`, `custom_jarvis/metacog.py` | Already represented; no vector-embedding system was confirmed in the inspected ULTRON tree |
| Reminders and background work | `custom_jarvis/schedule.py`, `core/process_watch.py`, `actions/background_monitor.py` | Already represented |
| Public web search and research | `actions/web_search.py`, `actions/web_read.py`, `core/webapi.py`, `core/platforms.py` | Already represented; improve source quality through tests and evaluation, not by importing a PR blindly |
| Dashboard and HUD | `ui.py`, `dashboard/`, `core/themes.py`, `core/avatar.py` | Already represented; upstream UI changes are visual references |
| Multi-agent role delegation | No equivalent general, independently-scoped role-agent product was confirmed in the inspected ULTRON tree | Candidate for a separately designed and evaluated feature; not a direct port |
| Gesture-based mouse control | No equivalent camera gesture controller was confirmed in the inspected ULTRON tree | Candidate only after sensor consent, action policy, emergency stop, model integrity, and tests are designed |
| Google Calendar / Gmail / Drive / Spotify | Check `actions/`, `plugins/`, and connector registry before each proposal | Treat as optional integrations; use least-privilege OAuth and explicit approval |

Do not treat this table as a formal proof of absence. It is a map of where to inspect first and what the tree comparison found.

## 4. Relevant MARK-LVI issues and their ULTRON status

The issue search returned a bounded sample of 100 results. These are user reports and feature requests, not verified defects in ULTRON.

| Upstream issue | Topic | ULTRON status / response |
|---|---|---|
| [#159](https://github.com/FatihMakes/Mark-LVI/issues/159) | MCP, subagents, vector memory, planning, model routing, observability, tool descriptions | MCP, planning, routing, tool trigger descriptions, audit, and meta-learning already exist in ULTRON. General role-agent delegation and vector embeddings need separate design and evidence. |
| [#117](https://github.com/FatihMakes/Mark-LVI/issues/117) | Credential manager and wake-word speed | ULTRON still manages provider settings through `memory/config_manager.py` and local config. A platform credential-store review remains a valid security task. Do not claim Windows Credential Manager support. |
| [#123](https://github.com/FatihMakes/Mark-LVI/issues/123) | Session continuity after disconnect | ULTRON has reconnect and plan-state code. Use this report to expand deterministic reconnect tests and owner-machine checks. |
| [#133](https://github.com/FatihMakes/Mark-LVI/issues/133) | API/MCP integration | MCP client and tool integration already exist in ULTRON. |
| [#134](https://github.com/FatihMakes/Mark-LVI/issues/134), [#145](https://github.com/FatihMakes/Mark-LVI/issues/145), [#162](https://github.com/FatihMakes/Mark-LVI/issues/162), [#160](https://github.com/FatihMakes/Mark-LVI/issues/160) | Wake-word, microphone, and repeated reconnect failures | Treat as regression scenarios for audio lifecycle, missing-device handling, reconnect backoff, and truthful diagnostics. They do not prove ULTRON has these exact failures. |
| [#154](https://github.com/FatihMakes/Mark-LVI/issues/154) | Multiple-monitor viewing | Do not assume all multi-monitor/DPI combinations are proven. Add platform tests and owner-machine validation where relevant. |
| [#110](https://github.com/FatihMakes/Mark-LVI/issues/110) | Home Assistant | Optional integration candidate. Keep Home Assistant as the device-control authority and apply ULTRON's normal policy/confirmation boundary. |
| [#109](https://github.com/FatihMakes/Mark-LVI/issues/109) | Headless/Docker deployment | Separate deployment mode candidate. Do not weaken the desktop product's sensor or tool controls to achieve it. |
| [#107](https://github.com/FatihMakes/Mark-LVI/issues/107) | Camera permission and web-app behavior | Reinforces explicit sensor consent, an active indicator, and a reliable stop path. |
| [#173](https://github.com/FatihMakes/Mark-LVI/issues/173) | Improve computer navigation accuracy | Candidate for evaluation-driven desktop navigation improvements. Measure accuracy and false actions before changing the interaction stack. |
| [#151](https://github.com/FatihMakes/Mark-LVI/issues/151), [#140](https://github.com/FatihMakes/Mark-LVI/issues/140) | Requests for separate commercial licences | No separate commercial grant was found in this audit. The current CC BY-NC terms remain binding unless the relevant rights holder gives written permission. |

## 5. Relevant pull requests: review and decision

The pull-request search returned 40 results. The most relevant candidates were reviewed by title, body, changed-file inventory, status, and selected file contents.

| PR | Proposal | Status | Decision |
|---|---|---|---|
| [#168](https://github.com/FatihMakes/Mark-LVI/pull/168) | Opt-in webcam gesture mouse | Open at audit; adds a plugin and model download; no regression tests in the PR file list | **Do not copy as-is.** It uses direct webcam and PyAutoGUI paths. A ULTRON implementation must use the central sensor/action policy, visible status, reliable release, emergency stop, bounded/checksummed model acquisition, and tests. |
| [#167](https://github.com/FatihMakes/Mark-LVI/pull/167) | Gesture Studio engine and plugin | Open at audit; overlaps PR #168; no regression tests in the PR file list | **Do not merge with #168.** If gesture control is approved later, select one design and rebuild it around ULTRON policy and tests. |
| [#165](https://github.com/FatihMakes/Mark-LVI/pull/165) | Credential manager, Uzbek speech, research, multi-agent analysis, health, packaging | Open and marked non-mergeable at audit; description says compatibility/testing remain unverified | **Reject wholesale import.** Its changed-file list includes a tracked `config/api_keys.json`. Any useful ideas must be reimplemented without tracked credentials, with provider-schema checks and tests. |
| [#121](https://github.com/FatihMakes/Mark-LVI/pull/121) | Capability table, safe paths, safe subprocess, redacted audit | Open and non-mergeable at audit | **Design reference only.** ULTRON already has a policy system, path confinement, evidence, audit, and shipping checks. Compare specific edge cases; do not replace the existing safety stack wholesale. |
| [#112](https://github.com/FatihMakes/Mark-LVI/pull/112) | Arc Sentinel widget, local control channel, Ollama schema bridge | Open and non-mergeable at audit | **Do not import wholesale.** ULTRON already has a Qt HUD, dashboard, provider schemas, and tool policy. Any future local control endpoint needs authentication, origin/CSRF controls, and policy enforcement. |
| [#136](https://github.com/FatihMakes/Mark-LVI/pull/136) | Bluetooth audio and video HUD fixes | Open and non-mergeable at audit | **Use as a regression source.** Compare exact device and playback edge cases against `core/audio_devices.py` and the video path. Require tests before adopting code. |
| [#118](https://github.com/FatihMakes/Mark-LVI/pull/118) | GoAway reconnect and speaking watchdog | Open and non-mergeable at audit | **Compare specific failure handling.** ULTRON already has reconnect policies and voice lifecycle tests. Do not replace them without a reproducible gap. |
| [#147](https://github.com/FatihMakes/Mark-LVI/pull/147) | Fix trailing comments in `.gitignore` patterns | Open at audit | **Already addressed in ULTRON.** Its `.gitignore` keeps comments on separate lines and documents why. |
| [#125](https://github.com/FatihMakes/Mark-LVI/pull/125) | Gesture controller with confirmation and emergency stop | Open and non-mergeable at audit | **Do not import.** The file inventory includes certificate/key assets and a downloaded model. Require full provenance, secret checks, and a new policy-integrated design. |
| [#127](https://github.com/FatihMakes/Mark-LVI/pull/127), [#119](https://github.com/FatihMakes/Mark-LVI/pull/119), [#120](https://github.com/FatihMakes/Mark-LVI/pull/120), [#143](https://github.com/FatihMakes/Mark-LVI/pull/143) | Calendar, Gmail, Drive, Spotify integrations | Open or incomplete at audit | **Optional integration candidates.** Require least-privilege OAuth, local secret storage, explicit write/delete approvals, test doubles, and clear disconnect/data deletion behavior. |

An upstream PR is not a release. An open PR is not an accepted feature. A green check on another branch is not proof that its code is safe or compatible with ULTRON.

## 6. License, attribution, and reuse rules

The inspected MARK-LVI `LICENSE` begins with copyright to FatihMakes and specifies **Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)**. The upstream README also says personal and non-commercial use only. GitHub's repository metadata returned `NOASSERTION` for the SPDX field, so use the actual checked-in `LICENSE` text rather than relying on the metadata classifier.

For this repository:

1. Preserve the upstream attribution and license notices required by the applicable licence.
2. Do not remove copyright headers or pretend upstream-derived work was written from scratch.
3. Do not use this code for commercial distribution or services without separate written permission from the rights holder.
4. Do not assume that every old FatihMakes repository, fork, issue attachment, model file, icon, face mesh, or external dependency has the same licence. Check each asset's source and terms.
5. Treat PR code and community forks as untrusted contributions until their source, authorship, licence, tests, and security properties are reviewed.
6. A model file or binary has its own provenance and licence. A safe Python wrapper does not make an unknown model asset safe.
7. Never import tracked secrets, certificates/private keys, OAuth tokens, personal memory, or another user's data from an upstream branch.

This file is an engineering record, not legal advice. When a material reuse or commercial question is unclear, stop and obtain written permission or legal review.

## 7. Required intake process for future upstream material

Before using any new FatihMakes/MARK/JARVIS resource:

1. Identify the exact repository, commit SHA, branch or PR SHA, file paths, author, date, and status.
2. Read the source file and surrounding callers. Do not rely only on a PR description or README claim.
3. Check the source repository licence, file-level notices, asset/model licences, and attribution requirements.
4. Compare the code with ULTRON's current architecture and find the closest existing implementation. Prefer fixing or extending the existing ULTRON path over adding a parallel subsystem.
5. Review security boundaries: permissions, path confinement, secrets, network, external downloads, sensors, subprocesses, OAuth scopes, user data, and prompt injection.
6. Write deterministic tests first or with the port. Test denial/refusal paths as well as success paths.
7. Integrate only a minimal, self-contained change. Do not merge upstream branches wholesale.
8. Record one of: **adopted**, **already present**, **reimplement**, **deferred**, or **rejected**, with the reason and evidence.
9. Update the canonical handoff, this audit, affected topic docs, and session history under `docs/AGENT_MAINTENANCE.md`.
10. Re-run ULTRON's verification and proof gates. Keep any platform-dependent claim marked PARTIAL until it runs on the target hardware.

## 8. Prioritised follow-up

| Priority | Work | Reason | Acceptance evidence |
|---|---|---|---|
| 1 | Compare the remaining 44 of 62 changed shared files against ULTRON | Eighteen high-risk/integration files have had focused diff scans; the rest of the source delta is not yet audited | Per-file adopt/hold/reject notes, focused tests for any adopted fix |
| 2 | Audit provider credential storage and consider OS credential-store support | Issue #117 raises a valid security concern; ULTRON still uses managed local config | Threat model, migration and rollback, no plaintext leak in logs/commits, platform tests |
| 3 | Add reconnect/audio regression scenarios from issues #123/#134/#160/#162 | These are recurring upstream failure classes | Deterministic fake-device tests plus real owner-machine verification |
| 4 | Design multi-agent role delegation as a separate ULTRON feature | PR #165 is conflicted/unverified; ULTRON has planning but not this full role-agent model | Role-specific tool allowlists, independent budgets, isolated context, audit trail, judge/evaluation tests |
| 5 | Decide whether gesture control is wanted | PRs #167/#168 have no regression tests and need stronger policy integration | Explicit camera consent/indicator, policy-gated input actions, emergency stop, verified model hash, Windows tests |
| 6 | Evaluate Home Assistant/headless/multi-monitor work only when product scope requires it | Upstream issues identify demand, not owner approval | A bounded vertical slice with privacy and platform tests |

Do not start all six tasks in parallel. The first task is the comparative review of the 62 changed shared files. Any new feature still needs explicit scope and the normal ULTRON approval rules.

## 9. Search limits and interpretation

- The account search returned eight public FatihMakes repositories at the time of the audit.
- The MARK-LVI issue review was limited to 100 search results; the PR review sample was 40 results, with detailed source review for selected items.
- The global `Mark-LVI` repository search returned up to 100 repositories, including many apparent forks and derivatives. It did not enumerate all GitHub forks or every project mentioning FatihMakes, Mark, or JARVIS.
- Unreviewed community forks are not approved sources. Do not import from them automatically.
- Re-run this audit after significant upstream releases or when the user identifies a specific fork/resource.

The rule is simple: **use the strongest relevant upstream work, but keep ULTRON's own safety, evidence, tests, and license obligations intact.**
