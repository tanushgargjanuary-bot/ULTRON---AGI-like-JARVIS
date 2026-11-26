# Upstream research — FatihMakes, MARK, and JARVIS

**Audit date:** 2026-11-10  
**Primary source:** [FatihMakes/Mark-LVI](https://github.com/FatihMakes/Mark-LVI)  
**Primary source main commit inspected:** `0101e540ac4b16cc3a862d9979e08fefcc1c7a01` (2026-11-04)  
**ULTRON comparison baseline:** `76484ebc4cbf4b5d4a23889ed6eeddfbf844083c`  
**Purpose:** Preserve upstream research and turn useful MARK/JARVIS work into safe, traceable ULTRON improvements.

**Later review:** [section 10](#10-mark-lvii-reviewed-2026-11-22), Mark LVII (head `752ff618a4e6a4bf2e675866b993071d739cfce2`, 2026-11-11), reviewed 2026-11-22. Nothing from it has been adopted.

**Other sources:** [section 11](#11-advice-from-other-developers-repositories-read-2026-11-25), advice from other developers' repositories (Matt Pocock's skills and others), read 2026-11-25.

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

The 62 changed shared paths include `main.py`, `ui.py`, `core/`, `actions/`, `providers/`, `memory/`, `dashboard/`, `requirements.txt`, `.gitignore`, and documentation/prompt files. A different SHA does not mean ULTRON is better or worse. It means the content must be reviewed. All 62 of the 62 changed shared files have now had focused diff comparisons. The four visual files have been reviewed separately; the MediaPipe-derived asset now has its own licence copy and provenance notice. Do not overwrite the ULTRON copy with upstream code simply because it is newer.

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

No upstream-only behavior from these 12 focused comparisons was identified as a safe direct copy. The useful result was validation of ULTRON-specific improvements and several concrete tests or threat cases. At the first 12-file checkpoint, **50 of the 62 changed shared paths** remained to inspect. Start with `main.py`, `ui.py`, `core/appidentity.py`, `core/action_loader.py`, `actions/browser_control.py`, and `actions/dev_agent.py`.

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

At the 18-file checkpoint, the review continued to support selective ULTRON-first integration. **No upstream code from those 18 files was copied.** Forty-four changed shared paths remained at that point.

### Additional focused review: ten provider, memory, speech, and desktop files

This pass checked ten more shared files by exact source blobs. The comparison used normalized line endings. It remains a focused diff review, not a complete independent audit of each file.

| File | ULTRON difference observed | Decision |
|---|---|---|
| `providers/schema.py` | Normalized text is identical to upstream. The blob SHA differs, but no content-line difference remains after line-ending normalization. | Already present. No change required. |
| `providers/llm_openai.py` | Adds repair for repeated streamed tool names, validation for malformed config values, image-refusal classification, failure notes, and pooled connections. | Keep ULTRON's defensive provider path. Review proxy/environment behavior separately before changing transport settings. |
| `memory/memory_manager.py` | Adds a read-modify-write lock, atomic storage, a separate bounded 50-entry change history, timestamp-aware sorting, and defensive handling of malformed nested values. | Keep ULTRON's concurrency and recovery behavior. |
| `providers/registry.py` | Converts provider IDs to strings and replaces malformed provider config blocks with an empty object rather than failing during startup. | Keep the defensive input handling. |
| `actions/computer_settings.py` | Converts model-supplied actions safely and declares parameters already read by the handler, including text, key, and press-enter. | Keep the schema/handler contract fix. |
| `actions/file_processor.py` | Adds bounded undo snapshots, output fingerprints, conflict-safe undo registration, and rollback if the write path fails. | Keep the reversible output path. |
| `providers/tts_piper.py` | Reuses the shared connection pool and records failures in voice-directory and prefetch paths. | Keep pooled transport and visible failure records. |
| `providers/stt_whisper.py` | Reuses the connection pool and adds `ensure_ready()` so a local speech model can be checked before the caller relies on it. | Keep the readiness check and shared transport. |
| `providers/tts_system.py` | Records failures in the prefetch path instead of silently swallowing the exception. | Keep failure visibility. |
| `providers/tts_elevenlabs.py` | Uses the shared connection pool for synchronous and asynchronous requests. | Keep connection reuse. |

The focused diff review now covers **28 of 62** changed shared paths. **34 changed shared paths remain**. No code from these ten upstream files was copied because the ULTRON versions already contain the relevant changes or have the same normalized content.

### Additional focused review: six actions and client files

This pass checked six more changed shared files by exact upstream and ULTRON blobs. It compared normalized lines and inspected relevant code paths. It remains a focused source-delta review, not a full independent security audit.

| File | ULTRON difference observed | Decision |
|---|---|---|
| `actions/code_helper.py` | Core implementation is nearly identical in the normalized comparison. Differences are limited to the tool description and a small image/screenshot path detail; no new upstream safety behavior was identified. | No upstream port identified. Keep the ULTRON-specific tool description. |
| `actions/open_app.py` | ULTRON resolves the target and uses direct executable/shortcut launching. It avoids the upstream `shell=True` launch pattern and reports when the target cannot be confirmed as open. | Keep the shell-free resolver path. Do not restore shell-based launch. |
| `actions/send_message.py` | ULTRON distinguishes confirmed completion from unverified typing/delivery, and avoids claiming a message was sent when it cannot confirm the result. | Keep the explicit outcome contract. A message action needs trustworthy confirmation, not just successful keystrokes. |
| `core/llm_client.py` | Adds failure notes for one-shot, text, and streamed provider calls. | Keep failure visibility. |
| `core/confirm.py` | Retains the interface-issued confirmation path that the model cannot forge and adds failure notes for logging and resolution errors. | Keep the UI-owned confirmation boundary and diagnostics. |
| `core/outcome.py` | The normalized source lines are identical to upstream; the different blob SHA is explained by formatting/line-ending differences. | Already present. No change required. |

The six-file pass found no upstream-only implementation that should be copied directly. It brings the focused review total to **34 of 62** changed shared files. **Twenty-eight changed shared paths remain**. No source code was imported in this pass.

The current test tree has broad provider, safety, tool-contract, and assistant suites, but it does not have a dedicated test module for each of these six files. Treat dedicated regression coverage for these exact file-level differences as unconfirmed, not as proven.

### Additional focused review: six runtime and media files

This pass compared six more changed shared paths by exact Git blobs and normalized lines. It is a focused source-delta review, not a full independent security audit.

| File | ULTRON difference observed | Decision |
|---|---|---|
| `core/installer.py` | The Windows package list includes `uiautomation`, which ULTRON's `core/ui_windows.py` uses as its accessibility-tree driver. The upstream package list includes `pywinauto` but not this driver. | Keep the dependency required by ULTRON's actual Windows backend. |
| `actions/desktop.py` | Coerces model-supplied action values safely and narrows the tool trigger description to wallpaper, desktop cleanup, and desktop inspection tasks. | Keep the safer parameter handling and explicit tool-selection description. |
| `actions/proactive.py` | Adds explicit limits against unsolicited memory/cleanup reminders, restricts suggestions, and treats inferred preferences as unapproved hypotheses. | Keep the privacy and consent language. |
| `actions/reminder.py` | Adds clearer trigger wording for reminder, alarm, and scheduled-task requests. The implementation is otherwise nearly identical in the normalized comparison. | Keep the clearer tool description; no runtime port required. |
| `actions/screen_processor.py` | Replaces eager PIL import with an installed-package check and lazy submodule binding. | Keep the startup-cost reduction and lazy import design. |
| `actions/youtube_video.py` | Removes unused `pyautogui` and `numpy` imports; checks optional packages without importing them and lazily loads `requests` and transcript support. | Keep the removal of unused imports and lazy optional dependencies. |

No upstream-only runtime behavior from these six files was identified as a safe direct port. This pass brings the focused review total to **40 of 62** changed shared paths. **Twenty-two changed shared paths remain**. No source code was copied in this pass.

### Additional focused review: six system and playback files

This pass checked six more changed shared files by exact blobs and normalized lines. It is a focused comparison, not a full independent security audit.

| File | ULTRON difference observed | Decision |
|---|---|---|
| `actions/flight_finder.py` | The normalized implementation is effectively the same; the small line differences do not identify a new upstream capability. | Already present. No port required. |
| `actions/game_updater.py` | The normalized source is effectively the same. | Already present. No port required. |
| `actions/system_monitor.py` | Allows the first alert for a monitor key immediately. The upstream cooldown check compares against a default timestamp of zero, which can suppress the first alert during the first cooldown interval after system start. | Keep the first-alert correction. |
| `actions/video_player.py` | Adds failure telemetry and rejects malformed non-text action/source arguments instead of continuing with invalid values. | Keep the error visibility and input validation. |
| `actions/weather_report.py` | Declares the requested day in the tool schema, matching a value the handler already reads. This prevents tomorrow/other-day requests from silently becoming today's forecast. | Keep the corrected schema/handler contract. |
| `core/hotkey.py` | Records failures from the held-key setter rather than silently swallowing them. | Keep failure telemetry. |

No upstream-only runtime feature from these six files was identified for direct import. The focused review now covers **46 of 62** changed shared paths. **Sixteen changed shared paths remain**. No source code was copied in this pass.

### Additional focused review: six safety, test, and install files

This pass checked six more changed shared paths by exact source blobs and normalized lines. It is a focused comparison, not a full independent security audit.

| File | ULTRON difference observed | Decision |
|---|---|---|
| `core/undo.py` | Changes `push_undo()` to return whether registration succeeded. This lets callers know whether a supposedly reversible operation has a rollback record. | Keep the success signal; callers must not claim an operation is reversible when its undo record was not registered. |
| `core/echo.py` | Records errors from echo-reference output handling rather than silently swallowing them. | Keep failure telemetry. |
| `providers/_tests.py` | Explicitly retires test widgets and the Qt application before process exit, and records cleanup faults. | Keep the deterministic Qt teardown path. The runner already isolates risky provider/UI checks from the main app. |
| `core/_smoke_harness.py` | Validates command-line arguments and JSON structure before loading target code. It records harness errors and states that it must run as a subprocess, not as an imported module. | Keep the input validation and subprocess-only contract. |
| `setup.py` | Reconfigures terminal output to UTF-8 with replacement handling where supported, so non-ASCII setup messages do not abort installs on restricted consoles. | Keep the non-fatal console setup. |
| `requirements.txt` | Pins PyQt6 below 6.12 due to a measured Qt 6.12.0 audio-output construction crash in headless/no-audio environments, and adds the directly imported `jsonschema` dependency. | Keep the tested Qt ceiling and direct dependency declaration. |

No upstream-only code from these six files was identified as a safe direct port. The focused review now covers **52 of 62** changed shared paths. **Ten changed shared paths remain**. No upstream source code was copied in this pass.

### Additional focused review: six public-facing and dashboard files

This pass checked six more changed shared paths by exact blobs, normalized lines, and targeted inspection of public-facing and session-security code. This is not a full penetration test or independent licence opinion.

| File | ULTRON difference observed | Decision |
|---|---|---|
| `AGENTS.md` | Expands the coding-agent rules. It points agents to the canonical handoff, mandatory documentation/cleanup procedure, workspace inspection script, and ULTRON-specific safety and tool-contract rules. | Keep the ULTRON project instructions. They are the operating rules for this repository, not a copy of the upstream guide. |
| `LICENSE` | Normalized text is byte-for-byte identical to the upstream file. It names FatihMakes and CC BY-NC 4.0. | Preserve the complete licence and attribution unchanged. |
| `core/prompt.txt` | Adds ULTRON's controlled self-change procedure, policy-based action approval, human-confirmed memory writes, and explicit refusal to obey instructions inside untrusted tool content. It removes the upstream instruction to save preferences silently. | Keep the consent and untrusted-content rules. They are core runtime safety requirements. |
| `dashboard/static/app.html` | Reworks the remote console UI and adds UI variants, session-token authentication, authenticated WebSocket setup, and AES-GCM encryption using the browser's Web Crypto API. The dashboard now depends on a secure context rather than an insecure fallback. | Keep the ULTRON interface and authenticated/encrypted client path. Pair this review with the server-side checks; this is not a full penetration test. |
| `dashboard/static/login.html` | Reworks the login screen while retaining six-character session-key login and paired-device reconnection. It stores session credentials in session storage and retries a saved device token. | Keep the ULTRON login flow. Review token lifetime and device-token revocation with the server implementation. |
| `readme.md` | Replaces the long upstream release-style README with a shorter ULTRON scope page. It documents actual desktop/web behavior, consent controls, platform limits, security caveats, setup, and license. | Keep the scoped claims and explicit limitations. Do not restore upstream feature claims unless ULTRON has current proof. |

### Final focused review: avatar and viseme files

The final four changed shared paths were reviewed against the same MARK-LVI main tree.

| File | Comparison | Decision |
|---|---|---|
| `core/avatar.py` | ULTRON adds persona-specific animation settings and a semantic-expression channel. It blends expression targets into the existing face animation instead of replacing the renderer. | Keep the ULTRON persona/expression integration. |
| `core/avatar_mesh.py` | Normalized source content is identical to upstream. | Already present. No change required. |
| `core/viseme.py` | Normalized source content is identical to upstream. | Already present. No change required. |
| `core/face_model.obj` | Both assets contain 468 vertices and 898 faces. Face indices match exactly. ULTRON coordinates differ by at most 0.00005 because they are stored to four decimal places. The file header identifies MediaPipe and Apache 2.0. | Keep the geometry. Preserve its separate attribution and licence. A complete copy of the inspected MediaPipe `LICENSE` bundle and a dedicated provenance notice are recorded under `licenses/`. |

**Comparison complete:** all **62 of 62** shared file paths with different blob SHAs have had focused diff comparisons. This is not a full independent security audit of every function. A different blob SHA can reflect line endings or formatting rather than a semantic change. All 78 upstream file paths were present in ULTRON. No whole upstream branch or code batch was imported. The only upstream-derived resource added in this task is the complete MediaPipe licence bundle and its provenance notice: [`../licenses/MEDIAPIPE-LICENSE.txt`](../licenses/MEDIAPIPE-LICENSE.txt) and [`../licenses/THIRD_PARTY_NOTICES.md`](../licenses/THIRD_PARTY_NOTICES.md).



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
| [#169](https://github.com/FatihMakes/Mark-LVI/pull/169) | Default startup briefing to off | Open at audit; one-line default-only change | **Adopted independently.** ULTRON now defaults missing/malformed values to off, preserves explicit saved booleans, and tests the HUD setting path. No cherry-pick; see `BriefingOptInTests`. |
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
| 1 | Re-run the source comparison after a meaningful upstream release or an owner-identified issue, PR, fork, or asset | All 62 changed shared paths and all 78 upstream paths were reviewed at the audited SHAs | Record exact SHAs, licence terms, adoption decision, and relevant verification |
| 2 | Audit provider credential storage and consider OS credential-store support | Issue #117 raises a valid security concern; ULTRON still uses managed local config | Threat model, migration and rollback, no plaintext leak in logs/commits, platform tests |
| 3 | Add reconnect/audio regression scenarios from issues #123/#134/#160/#162 | These are recurring upstream failure classes | Deterministic fake-device tests plus real owner-machine verification |
| 4 | Design multi-agent role delegation as a separate ULTRON feature | PR #165 is conflicted/unverified; ULTRON has planning but not this full role-agent model | Role-specific tool allowlists, independent budgets, isolated context, audit trail, judge/evaluation tests |
| 5 | Decide whether gesture control is wanted | PRs #167/#168 have no regression tests and need stronger policy integration | Explicit camera consent/indicator, policy-gated input actions, emergency stop, verified model hash, Windows tests |
| 6 | Evaluate Home Assistant/headless/multi-monitor work only when product scope requires it | Upstream issues identify demand, not owner approval | A bounded vertical slice with privacy and platform tests |

Do not start all six tasks in parallel. Treat the source comparison as complete for the audited SHAs; re-open it when upstream changes or the owner identifies a specific resource. Any new feature still needs explicit scope and the normal ULTRON approval rules.

## 9. Search limits and interpretation

- The account search returned eight public FatihMakes repositories at the time of the audit.
- The MARK-LVI issue review was limited to 100 search results; the PR review sample was 40 results, with detailed source review for selected items.
- The global `Mark-LVI` repository search returned up to 100 repositories, including many apparent forks and derivatives. It did not enumerate all GitHub forks or every project mentioning FatihMakes, Mark, or JARVIS.
- Unreviewed community forks are not approved sources. Do not import from them automatically.
- Re-run this audit after significant upstream releases or when the user identifies a specific fork/resource.

The rule is simple: **use the strongest relevant upstream work, but keep ULTRON's own safety, evidence, tests, and license obligations intact.**

## 10. Mark LVII, reviewed 2026-11-22

**Source.** [FatihMakes/Mark-LVII](https://github.com/FatihMakes/Mark-LVII), GitHub repository id 1170311800. It is the repository audited above, renamed: upstream publishes a new Mark by renaming the repository, and a new Mark is the first line of `readme.md` changing (12 times between 2026-06-06 and 2026-11-11, read through the GitHub API on the day of the review). There are no tags or releases. Head: `752ff618a4e6a4bf2e675866b993071d739cfce2` (2026-11-11, "Add files via upload"), one commit after `0101e540ac4b16cc3a862d9979e08fefcc1c7a01`, the commit ULTRON was copied from (still the base; the pin is `docs/upstream/PIN.json`).

**How it was measured.** `python scripts/upstream_sync.py check --full --upstream <a clone of 752ff61> --no-api`, which only reads, on the day of the review and again after the script was corrected (the same answer both times). Three versions of every changed file are compared: upstream at the copy, ULTRON now, upstream now. The comparison read upstream's files and the lines it added. **None of upstream's code was run.** Exit 20: two stop signs.

**Licence and dependency.** `LICENSE` is unchanged (its fingerprint equals the pinned one): CC BY-NC 4.0, "Copyright (c) 2026 FatihMakes". Attribution stays. `requirements.txt` gains `certifi>=2024.2.2`. The new `core/tls.py` (74 lines) makes HTTPS trust the system's roots plus certifi's list; certifi is already installed with `requests`, but listing it is a dependency change and needs the owner's consent. The other stop sign: upstream changed `AGENTS.md`, which steers agents; its version is read and never applied.

**What differs: 54 files.**

| Kind | Files | Which |
|---|---:|---|
| Collides (both changed the same place) | 12 | `main.py` (8 places git cannot combine; E1 and E2 are in its new lines), `ui.py` (upstream cut it from 7,505 to 384 lines because the window moved to `gui/`), `memory/config_manager.py`, `core/gemini.py`, `actions/browser_control.py`, `actions/computer_settings.py`, `actions/desktop.py`, `actions/video_player.py`, `providers/llm_openai.py`, `providers/_tests.py`, `AGENTS.md`, `readme.md` |
| Combines as text, still needs tests | 8 | `actions/computer_control.py`, `actions/proactive.py`, `actions/reminder.py`, `core/appidentity.py`, `core/wake_word.py`, `providers/tts_elevenlabs.py`, `providers/tts_piper.py`, `requirements.txt` |
| New | 31 | `gui/` 10 files, 8,976 lines; `core/cloud.py`, `core/screenview.py`, `core/screenact.py`, `core/tls.py` 6,271 lines; `core/tasks/` 9 files, 2,193 lines; `core/routines/` 4 files, 693 lines; `actions/background_tasks.py` and `actions/routines.py` 329 lines; `agents/` 2 files, 39 lines (18,501 lines in all) |
| Line endings only | 3 | `core/_smoke_harness.py`, `core/code_checks.py`, `providers/registry.py` |

**The five decisions, as of this review.**

| Decision | What |
|---|---|
| Adopted | Nothing at the time of the review (see "Taken since the review" below). |
| Already present | The three files that differ only in line endings. |
| Reimplemented | Nothing yet. The plan for background tasks is to reuse ULTRON's public-address guard (`actions/web_read.fetch_public_bytes`) instead of keeping upstream's second copy. |
| Deferred | Everything wanted, in slices that wait for the owner's go. (1) Small fixes found by reading the diff, not run: wake-word reset, Windows scroll units, volume, brightness and seek, video seek, the Gemini fallback ladder, speech output, shutdown (which touches the boot guard, a referee file) and the TLS file (which needs the `certifi` consent). (2) Background tasks and deep research: `core/tasks/`, `actions/background_tasks.py`, `agents/`. (3) Routines, only in a form that satisfies E1 to E3. (4) `gui/`, last: ULTRON's own window work lives in `ui.py`, and the proof gate and three test files read `ui.py` as text. Each is in `docs/upstream/LEDGER.json` as `later`; 17 files have no decision yet and are held. |
| Parked (neither adopted nor rejected) | `core/cloud.py`, `core/screenview.py`, `core/screenact.py` (6,197 lines): nothing in upstream's own program imports them, which the script found and a plain `grep` of upstream confirmed (the three are mentioned only in each other and in comments). They open sockets, deploy to a server over SSH and talk to Telegram. Not copied until upstream wires them in and the owner agrees. |
| Rejected | The owner's three exclusions, chosen on 2026-11-22 (strictest option): **E1** news read out when ULTRON opens, **E2** the news check every 30 minutes, **E3** routines that run tools by themselves at launch. Five upstream files mention one of them: `main.py` (E1, E2), `core/cloud.py` (E1), `actions/routines.py` (E2, E3), `core/routines/desktop.py` (E1, E2, E3), `core/routines/engine.py` (E3). Upstream's own `AGENTS.md`, `readme.md` and the referee files are decided `ours` and never applied. |

**Worth knowing.** Upstream's routine engine falls back to a news briefing when a routine does not say otherwise, and its `actions/desktop.py` failed 44 of ULTRON's wallpaper checks: both were measured on 2026-11-22 in a scratch tree and not re-run since, which is why files are never dropped in unchanged (upstream's files also took nine of twelve debt ceilings over). The new tools are `background_tasks` and `routines`. 98 added strings say JARVIS or MARK; ULTRON's name is ULTRON. New code that runs other programs is in 8 files, that opens network connections in 4, that uses the Windows registry in 2, that installs packages in 1, and that deploys over SSH in 1 (`core/cloud.py`).

**Announced, not code.** Upstream's readme roadmap names, for LVIII and later: MCP tools, an approval policy for actions, event-driven proactivity, a knowledge folder, conversation history and interrupt by voice. That is a plan, and it was not reviewed. An MCP client (`custom_jarvis/mcp_client.py`; issues #133 and #159 in section 4) and an approval policy (`core/policy.py`) already exist in ULTRON; check before building a second copy.

**Not reviewed.** Mark-LVII's issues and pull requests (only the code drop was compared); `gui/` line by line (it was measured and sorted, not read); community forks. The scheduled report (`docs/UPSTREAM_SYNC.md`) will say when upstream moves again.

**Taken since the review.** The owner said "go" on 2026-11-24 for the small fixes. They are taken a piece at a time, each with its tests written first (every behaviour test was red on the old code), and every decision is in `docs/upstream/LEDGER.json`. Pull request #35 carried the first three and was merged on 2026-11-24; the mute words are the next pull request.

| Piece | Decision | What |
|---|---|---|
| Windows scroll units, `actions/computer_control.py` | Adopted | `_scroll` counts wheel notches (120 units each on Windows), never turns round for a negative amount, and holds the amount between 1 and 60. Upstream's only hunk in this file. `tests/test_scroll_units.py`. |
| Wake-word reset, `core/wake_word.py` and `JarvisLive.sleep` in `main.py` | Adopted | The detector clears the model after a detection, and `sleep()` asks it to forget what it heard. Upstream's silent `except Exception: pass` became `failures.note`. `tests/test_wake_word.py`. |
| Piper voice download, `providers/tts_piper.py` | Reimplemented | A voice downloads into a scratch folder and moves in only when both files are whole, the model last. Unlike upstream's: one scratch folder and one lock per voice, so a second voice is not held up and no voice name can point the folder elsewhere. `tests/test_piper_download.py`. |
| Mute, unmute and toggle (`actions/computer_settings.py`: `mute_get`, `mute_set`, the three actions, undo, the answer, and the word `unmute` shown to the model) | Reimplemented | Mark's idea (set the state asked for, never flip, read it back), written test first (`tests/test_mute_state.py`). Different: `pactl` is asked in plain English; a toggle from an unknown start is not called confirmed; `toggle_mute` is not added to the model's word list. |
| Piper `certifi` retry (macOS) | Deferred | Waits for the owner's consent about `certifi`. |
| `focuses` in `actions/proactive.py` | Deferred | A hook for routines; it goes with the routines slice. |
| Not going to sleep when no detector can wake it (`_run_sleep_watch`, `_ui_wake_toggle` in `main.py`) | Deferred | The next small piece; not yet read against Ultron's tests. |
| ElevenLabs voice name to voice ID (`providers/tts_elevenlabs.py`) | Deferred | Not yet read against how Ultron's settings panel saves the voice. |
| The rest of `actions/computer_settings.py` after the mute words (483 changed lines in all: `volume_set` switching the sound on, the volume-key fallback, step sizes, brightness on macOS and Linux), video seek (`actions/video_player.py`, 286), the Gemini ladder (`core/gemini.py`, 127), shutdown (`main.py`), `actions/reminder.py` (55), `core/appidentity.py` (117) | Deferred | The next pieces. Each is larger than these three, so each is read and split before it is taken. |

**Found while reading, not changed.** On Windows pyautogui's `hscroll` is the vertical scroll (its docstring: horizontal scrolling is "currently just Linux"), so "scroll left" and "scroll right" move the page down and up there. `WakeWordDetector._drain` records the `queue.Empty` that ends every drain as a failure, so the failure trail gets one false entry per wake.

## 11. Advice from other developers' repositories, read 2026-11-25

**Asked for.** The owner wrote: "Use Matt's repo skills and he is very experienced developer, and try to research more people who have good advice lying in their github repos." This is the intake record that section 7 asks for, for sources that are not FatihMakes. Section 6 (licence) applies, and the dispositions are the same five words.

**Method.** I read the files named below through the GitHub API, and found the best-known repositories with a web search, on 2026-11-25. I ran no installer, no plugin command and no script from any of them, copied no file, and added no dependency. Matt Pocock's `SCOPE.md` sets a bar, and I used it too: an idea is taken only if it answers a failure that really happened to us. Each adopted item below names ours.

### 11.1 What was read

| Repository | Whose | Stars | Licence, as GitHub shows it | Head read | What I read |
|---|---|---:|---|---|---|
| `mattpocock/skills` | Matt Pocock | 332,758 | MIT | `6f7f7831a6` | 39 skills in four folders (20 engineering, 7 productivity, 4 misc, 8 in progress). Most of: `grilling`, `grill-me`, `tdd`, `diagnosing-bugs`, `codebase-design`, `domain-modeling`, `grill-with-docs`, `retro`, `handoff`, `wait-what`. The first lines of: `writing-for-agents`, `improve-codebase-architecture`, `triage`, `code-review`, `to-questionnaire`, `wizard`. Also its `AGENTS.md`, `CONTRIBUTING.md`, `GLOSSARY.md` and `SCOPE.md`. The other skills by their one-line descriptions only. |
| `obra/superpowers` | Jesse Vincent | 326,453 | MIT | `22f0b463e7` (2026-11-03) | 15 skills. The first 34 lines of `brainstorming`, `test-driven-development`, `verification-before-completion` and `systematic-debugging`; the others by name only. On 2026-11-26 also the rationalization tables of `test-driven-development`, the claim, requires and not-sufficient table of `verification-before-completion`, "Size the Work" in `brainstorming`, the head of `using-superpowers` and the contributor guide in its `AGENTS.md`. |
| `multica-ai/andrej-karpathy-skills` | Named for Andrej Karpathy's observations; written by others | 235,668 | none shown | `2c60614193` (2026-04-20) | `CLAUDE.md`, whole: four principles. Ideas only, because there is no licence file. |
| `ayghri/i-have-adhd` | ayghri | 62,291 | MIT | `f3e783bae5` | The first 60 lines of its skill. |
| `openclaw/openclaw` | The OpenClaw project | 395,193 | MIT | `3ee8fc5376` | The first 40 lines of `AGENTS.md`, and the headings of `SECURITY.md`. |
| `humanlayer/12-factor-agents` | HumanLayer | 27,420 | not one licence (GitHub says NOASSERTION) | `d20c728368` (2025-09-21) | The list of twelve factors in the README. Nothing copied. |
| `mitsuhiko/agent-stuff` | Armin Ronacher | 3,227 | Apache-2.0 | `0865c849be` | The README, which describes a `/discuss` command. |
| `steipete/agent-scripts` | Peter (steipete) | 7,564 | MIT | `deb19f5896` | The README's first lines. Nothing used. |
| `trailofbits/skills` | Trail of Bits | 8,427 | CC-BY-SA-4.0 | `149d7b21f4` | Directory names only. Share-alike, so nothing copied. Worth a later look: `mutation-testing`, `property-based-testing`, `differential-review`, `insecure-defaults`, `sharp-edges`. |
| `garrytan/gstack` | Garry Tan | 142,641 | MIT | `8aafd408e2` | The README's first lines. Not relevant to this project. |
| `anthropics/skills` | Anthropic | 200,401 | none shown for the repository (each skill has its own) | `e4bb5d960d` (2026-11-16) | `skills/skill-creator/SKILL.md`: the first 90 lines and the guidance on descriptions, size and writing style. Read 2026-11-26. |
| `coleam00/context-engineering-intro` | Cole Medin | 13,927 | MIT | `a2d84b021c` (2026-03-16) | `PRPs/templates/prp_base.md`: the first 100 lines and the validation loop. Read 2026-11-26. |
| `agentsmd/agents.md` | The AGENTS.md project | 25,715 | MIT | `d001185d79` (2026-09-10) | The README and its sample file. Read 2026-11-26. |

Already our method since 2026-11-24: `addyosmani/agent-skills` (MIT) and `anthropics/skills`.

Listed from GitHub's data only, **not read**: `affaan-m/ECC`, `github/spec-kit`, `bmad-code-org/BMAD-METHOD`, `eyaltoledano/claude-task-master`, `hesreallyhim/awesome-claude-code`, `VoltAgent/awesome-agent-skills`, `vercel-labs/agent-skills`, `NousResearch/hermes-agent`, `earendil-works/pi`, `ghuntley/how-to-ralph-wiggum`, `ykdojo/claude-code-tips`. For the product itself, and not for the way of working, `pipecat-ai/pipecat` and `livekit/agents` are voice-agent frameworks worth reading on a later day.

### 11.2 Where independent developers agree

1. **Ask before building.** Matt's `grilling`, Jesse Vincent's `brainstorming`, Armin Ronacher's `/discuss`, and "Think Before Coding" in the Karpathy-derived file.
2. **Test first, and watch the test fail.** Matt's `tdd`, Jesse Vincent's `test-driven-development`, and "Goal-Driven Execution".
3. **No claim without fresh evidence.** Jesse Vincent's `verification-before-completion`: "If you haven't run the verification command in this message, you cannot claim it passes."
4. **Find the cause before the fix.** Matt's `diagnosing-bugs` (a loop that can go red on this very bug) and Jesse Vincent's `systematic-debugging`.
5. **Small, surgical changes.** "Surgical Changes" and "Simplicity First" in the Karpathy-derived file; "Choose good compromises" in OpenClaw's agent rules.
6. **Keep the agent rules short, point to documents, and let a new rule cite an incident.** OpenClaw's `AGENTS.md` (a 20,000-character cap) and Matt's `retro` and `writing-for-agents`.
7. **One shared vocabulary.** Matt's `domain-modeling`.
8. **Shape the answer for the reader.** ayghri's rules, and Matt's `wait-what` (Simplified Technical English).
9. **Do not ask what you can decide, and keep working.** OpenClaw's working agreement: "Resolve routine, reversible choices with reasonable assumptions; ask only about consequential decisions context cannot resolve. Continue independent authorized work meanwhile. Silence never authorizes gated action."

Most of this the owner already wrote in `WORKING-PHILOSOPHY.md` and `docs/MAINTAINERS.md` before these repositories were read. The table shows what was new.

### 11.3 What we did with each idea

| # | Idea | From | Where we stood | Disposition |
|---|---|---|---|---|
| 1 | Ask all independent questions in one round, each with a recommended answer worded so that "yes" accepts it; look up facts yourself | Matt `grilling`; Armin `/discuss`; Jesse `brainstorming` | `WORKING-PHILOSOPHY.md` said "Ask when the answer changes what you build", with no form | **Reimplemented**: section 2, "Ask in one round" |
| 2 | Do not end a message with a request to approve a small step; ask once for a standing permission | The owner's notes (`docs/MAINTAINERS.md`: "ask me about trivial actions"); OpenClaw | The rule existed. It was broken: many messages ended in a request to merge, and on 2026-11-25 the owner wrote "you keep giving merges" | **Reimplemented** as a rule that names the incident |
| 3 | Keep working while a question is open; silence is never a yes to a gated action | OpenClaw | Not written | **Reimplemented**: section 2 |
| 4 | A test must be able to fail for the reason its claim could be false; the expected value comes from something independent | Matt `tdd` (the "tautological" anti-pattern) | Two incidents on 2026-11-25: `widen` (#38) and the Qt `update-types` rule (#40) | **Adopted**: section 3, step 4 |
| 5 | Evidence before a claim | Jesse `verification-before-completion` | `WORKING-PHILOSOPHY.md` section 1 | **Already present** |
| 6 | Root cause first | Matt `diagnosing-bugs`; Jesse `systematic-debugging` | Section 6, "How we debug". Two details are not in it: rank three to five falsifiable hypotheses before testing any; tag temporary debug output with a unique prefix | **Already present**; the two details **deferred** |
| 7 | A glossary in plain words, tied to the program's own words | Matt `domain-modeling` | None, and the owner asked for plain words three times | **Adopted**: `GLOSSARY.md` and `tests/test_glossary.py` |
| 8 | "Wait what": stop, give one line of context, say it again in the glossary's words | Matt `wait-what` | Simplified Technical English was already required | **Adopted** the trigger phrase; the language rule is **already present** |
| 9 | Lead with the answer, number the steps, end with one next action | ayghri | "Yes" or "No" first, and the conclusion in the first line | **Adopted** the last two parts; the first is **already present** |
| 10 | Short agent rules; a new rule names its incident | OpenClaw; Matt `retro`, `writing-for-agents` | `AGENTS.md` is about 200 lines | **Adopted** the incident rule; pruning **deferred** |
| 11 | A retro after each piece: what went wrong, and which fix goes in the environment | Matt `retro` | "Mistake" notes in the session log, with no form | **Adopted**: section 3, step 9 |
| 12 | Surgical changes; simplicity first | The Karpathy-derived file | "The smallest change that can be proved", section 3 | **Already present** |
| 13 | A handoff points to other records and does not copy them | Matt `handoff` | Records that copy facts held elsewhere drifted three times on 2026-11-25: a commit count, a "two days" and an undated count | **Deferred**: its own piece |
| 14 | Deep modules, the deletion test, a scan of the places that change most | Matt `codebase-design`, `improve-codebase-architecture` | Not done | **Deferred**: proposed below |
| 15 | Issue triage with durable briefs for an agent; a record of rejected ideas | Matt `triage` | Issues #2 to #7 are loose notes | **Deferred**: proposed below |
| 16 | A wizard for steps only a human can do | Matt `wizard` | The owner's Windows run (issue #6) is still open. The rule "do not add launcher files" means a script run from PowerShell, not a file to double-click | **Deferred**: proposed below |
| 17 | A written trust model | OpenClaw's `SECURITY.md` | No single document found | **Deferred**: proposed below |
| 18 | Twelve factors for LLM applications | HumanLayer | Partly present: tool declarations are checked against the provider's rules, and risky actions need a click on the HUD | **Deferred**, as a lens for item 14 |
| 19 | Specs, plans, subagents and worktrees as a pipeline | Jesse, Addy, Matt | One agent session at a time; Addy's lifecycle is already our method | **Rejected for now** |
| 20 | TypeScript, Husky and Claude-Code-only hooks; writing and course skills | Matt's `misc` and `in-progress` folders | Not our stack | **Rejected** |

### 11.4 What this research cannot show

- **Stars measure attention, not quality.** I read only the parts named in 11.1. The skills I did not read were judged by one line each.
- **Nothing here is measured.** I did not test whether the added rules improve the work. The first test is whether the next pieces show fewer mistakes of these two kinds: a test that holds a belief, and a request to approve a small step.
- **Most of these skills are written for AI coding tools and for TypeScript.** What applies to a Windows voice assistant written in Python is a judgement, and it is mine.

### 11.5 Proposed next pieces, not started

1. A scan of the code for the places where one change needs many files (items 14 and 18).
2. Briefs for issues #3, #4 and #5, so an agent can start each without a new conversation (item 15).
3. A script for the owner's Windows computer that runs the proof gate and says in plain words what to send back (item 16).
4. A written trust model for Ultron: who is trusted, and where plugins, memory and models stop being trusted (item 17).
5. A handoff header that points to the records and does not copy them (item 13).

### 11.6 A pasted coding-agent playbook, reviewed 2026-11-26

The owner pasted a "Vibe Coding Agent Master Playbook" and asked for it to be improved. The result is `docs/reference/CODING_AGENT_PLAYBOOK.md` (v2) and `tests/test_agent_playbook.py`. It is a proposal: it changes nothing in `AGENTS.md` or in any rule of Ultron. Three more repositories were read for it (the last three rows of 11.1), and more of `obra/superpowers`.

| Idea | From | Disposition |
|---|---|---|
| The SKILL.md shape: a description that says what and when, a short body, the reason with the rule | `anthropics/skills` | **Adopted** into the playbook's skills. |
| Three validation levels, references with a reason, known gotchas in a plan | the PRP template | **Reimplemented** as the playbook's plan template. |
| The claim, requires, not-sufficient table; the rationalization tables; sizing the work; contributor rules for agents | `obra/superpowers` | **Adopted** into the playbook. |
| Which tool reads which file | four third-party posts | **Recorded as not verified**: they are not the vendors' documentation. |
| Credits and statistics in v1 that nothing could be found behind | the pasted text | **Rejected**, and listed in Appendix A of the playbook. |
| Moving any of it into `AGENTS.md` | | **Deferred**: the owner decides. |
