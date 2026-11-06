# HANDOFF — Ultron (built on MARK LVI)

> The assistant is named **Ultron**. Upstream application: MARK LVI by FatihMakes (CC BY-NC 4.0); that
> attribution and licence stay. It answers to "Ultron", "Jarvis" and "Mark" without correcting the user.

**Purpose of this file:** let a *different* AI (or a future me) pick this project up in one read, without
re-opening old conversations and without breaking anything the user already decided.

**Written:** 2026-11-05 · **Author of the current baseline:** previous Arena session
**Current artifact:** `ultron.zip` (see workspace `release.txt` for size / file count / SHA256)
**Active source:** `mark-jarvis/` · **Upstream:** FatihMakes/Mark-LVI @ `0101e540ac4b16cc3a862d9979e08fefcc1c7a01` · **License:** CC BY-NC 4.0

---

## 0. The one-paragraph brief

MARK is a working voice assistant on Windows (PyQt6 HUD, avatar, Gemini Live or any OpenAI-compatible
provider). On top of it we ported a namespaced, deterministic evidence/repair engine (`custom_jarvis/`)
plus consent-first, human-approved preference memory. That baseline is built and offline-verified.
The **next stage is designed but not built**: reviewed self-improvement (propose → approve → isolate →
test → approve → activate), native role-based sub-agents, background desktop operation, risk-tiered
consent, and multi-provider routing. **The user has not authorised implementation.** Do not write code
for it until they say so explicitly.

---

## 1. Rules of engagement (non-negotiable)

1. **No implementation without explicit permission.** The user repeatedly said "discussion only". If in
   doubt, ask. Do not "just prototype it".
2. **Never weaken a test or an assertion** to make something pass. Baseline must hold at
   ≥ 209 tests, 312 ported assertions, 10 exact-anchor mutation gates, 15/15 seeded mutations.
3. **Never bypass the safety path**: `ControlledRegistry.execute`, `EvidenceEngine.prepare_args`,
   `core/custom_gate.dispatch`, `core/confirm.request`. Approval tokens come from the UI, never the model.
4. **No `exec`/`eval`** of model-produced source. Adapters only via `AdapterProgram`.
5. **Preserve CRLF** in `main.py`, `core/prompt.txt`, `actions/proactive.py`, `run.bat` and other files
   created with CRLF — the project is Windows-first.
6. **Do not silently persist inferred preferences, personality, health or mood.** Only approved enums.
7. **RAM warnings stay disabled.** Meter and on-request status stay. Do not re-enable nagging.
8. **Do not claim capabilities you cannot demonstrate.** No AGI language, no "zero issues", no
   "100×", no test-count-as-proof. Windows behaviour is unverified until run on Windows.
9. **Respect licences.** Upstream is CC BY-NC 4.0 and non-commercial; keep attribution to FatihMakes.
   Anything pulled from GitHub needs separate licence and security review, and is never auto-executed.
10. **Do not download large models or add heavy dependencies** without the user's informed consent.

---

## 2. Current state — what exists and is verified

| Component | Status | Evidence |
|---|---|---|
| `custom_jarvis/` engine (37 skills, service, planner, evidence, repair, governance, metacognition) | Built | `tests/test_self_healing.py`, `test_repair_judgment.py`, `test_autonomy_upgrades.py` |
| Human approval gate (`core/custom_gate.py`) | Built | `tests/test_mark_integration.py` |
| Consent-first insights (`core/insights.py`) | Built | `tests/test_insights.py` (23 tests) |
| RAM nag suppression | Built | `tests/test_insights.py` + `actions/system_monitor.py` |
| Five HUD Controls buttons | Built | integration test asserts fifth button |
| Windows `run.bat` + `run.ps1` | Built, **never executed on Windows** | static checks + `pwsh` parse/run on Linux |
| Risk-tiered consent (`core/policy.py`) | **Built 2026-11-05** | `tests/test_policy.py` (27) |
| Capability app resolution (`core/app_resolver.py`) | **Built 2026-11-05** | `tests/test_app_resolver.py` (19) |
| Avatar expressions (`core/expression.py`) | **Built 2026-11-05** | `tests/test_expression.py` (32) |
| Provider routing mechanism (`core/routing.py`) | **Built 2026-11-05, NOT wired to the engine** | `tests/test_routing.py` (35) |
| Workspace → consent policy wiring | **Built 2026-11-05** | `custom_jarvis/service.py::_sync_workspace_policy` |
| Syllabus algorithms (`core/fuzzy.py`, `knapsack.py`, `branchbound.py`, `bandit.py`, `reputation.py`, `audio_features.py`, `numerics.py`, `trie.py`) | **Built 2026-11-06, standard library only** | `tests/test_fuzzy.py` (33), `test_knapsack.py` (25), `test_branchbound.py` (14), `test_bandit.py` (18), `test_reputation.py` (17), `test_audio_features.py` (23), `test_numerics.py` (11), `test_trie.py` (8); numbers in `scripts/bench_algorithms.py` |
| Fuzzy matching on the live app-resolution path | **Built 2026-11-06** | `core/app_resolver.py::_fuzzy_hits`, `tests/test_fuzzy.py::ResolverIntegrationTests` |
| Spectral turn-end detection on the live microphone path | **Built 2026-11-06**, with the level-based detector retained as fallback | `providers/engine_pipeline.py::_watch_for_turn_end`, `tests/test_audio_features.py::EngineWiringTests` |
| Algorithm bench | **Built 2026-11-06** | `scripts/bench_algorithms.py` — `--json`, `--only` |
| Structure-first computer use (`core/ui_tree.py`, `ui_action.py`, `ui_windows.py`, `ui_browser.py`, `ui_ladder.py`, `actions/ui_control.py`) | **Built 2026-11-06. The Windows UIA bridge is UNVERIFIED — never run on Windows** | 126 tests: `test_ui_tree.py` (42), `test_ui_action.py` (31), `test_ui_ladder.py` (35), `test_ui_control_action.py` (18) |
| Self-improvement loop (`core/selfimprove.py`) | **Built 2026-11-06**, not yet pointed at a real artefact | `tests/test_selfimprove.py` (33) |
| Evolution worker / sub-agents / desktop operator / multi-provider UI | **Does not exist** | — |
| Local model | **Not downloaded** | — |
| Vision | **Deferred** | no vision model bundled |

Latest full verification (`mark-jarvis/verification-results.txt`): 152 files parsed · 740 tests passed ·
99 MARK self-checks 0 failed · 1,000 stress · 15/15 mutations · "All migration checks passed.
Native Windows, microphone hardware and live providers were NOT tested."

Re-run with:

```bash
cd mark-jarvis && python scripts/verify.py
```

### Closeout, 2026-11-06: feature work is paused by decision

Three defects were found by driving the layers with a fake adapter and are fixed (see `log.txt`
PHASE 19): refs were unusable across tool calls, a batch could not run more than one step, and the
self-improvement loop had no engine (`scripts\evolve.py` now runs it). If you are about to add a
feature, read that entry first — it records what the audit did and did not cover.

What is true today: the structural layers (refs, staleness, ladder, dispositions) are tested; the
Windows bridge is not; the evolution loop can measure a change and refuse noise, and does not edit
code or run unattended.

### Computer use: structure first, and the ladder when there is no structure

`actions/ui_control.py` is the tool; `core/ui_tree.py` and `core/ui_action.py` are the model and
the discipline. Read `log.txt` PHASE 18 before changing any of it, and note two things:

1. **The Windows bridge (`core/ui_windows.py`) has never been run on Windows.** It is written
   defensively and fails closed, and `ui_control` therefore refuses rather than guessing. Do not
   describe computer use as working on Windows until someone has run it there and fixed what broke.
2. **Refs die after every action.** That is not an inconvenience to be optimised away; it is what
   stops a click landing on a row that was replaced a moment ago.

The ladder in `core/ui_ladder.py` is the answer to the honest weakness of tree-based control: a
window with no tree. Order is tree, drill, DOM, keyboard access key, vision (only if configured and
consented), then ask. Do not add a coordinates fallback to it; that is the bug this project started
by fixing.

### The algorithms are code now, not a reading list

`ACCEPTANCE` unchanged: no assertion was weakened to reach 559; the count grew from 418.
Nine new modules in `core/` implement the AKTU DAA and AIML topics that actually apply, written
from the standard library (numpy only in `audio_features.py`, because the microphone path already
holds it). Two are on live call paths — fuzzy scoring when word overlap fails in
`core/app_resolver.py`, and spectral turn-end detection in
`providers/engine_pipeline.py::_watch_for_turn_end`.

Before extending any of them, read `log.txt` PHASE 17. Four real bugs are recorded there: a
branch-and-bound that asked a question because a parent tied with its own child; a noise floor
that learned from speech and so never heard the user; a maximum-turn check that could not fire
because it sat inside the branch continuous speech never reaches; and a matcher that cost 11.7 ms
per utterance until its per-query work moved to build time.

The next item is **the calibration harness**, deliberately before more algorithms: without it the
predictor's 0.70 threshold is a choice, not a measured probability, and no later claim of
improvement can be checked. Then knapsack into context assembly, branch and bound as the gate
before asking, the bandit in `core/routing.py`, and reputation replacing the flat failure counts
in `custom_jarvis/failure_memory.py`.

(Needs PyQt6 + numpy installed; Qt runs offscreen on Linux. No network calls in the suite.)

---

## 3. File map — where to look for what

| Path | Why it matters |
|---|---|
| `main.py` | Voice/LLM host. Gemini + PipelineEngine share the gate. Observes typed + completed voice input for insight candidates. Approved profile injected into system context. `_save_session_summary` clears RAM only. |
| `ui.py` | The only `QApplication`. HUD, avatar, Controls drawer, confirmation banner. Five custom buttons. **Never import Qt in tools.** |
| `core/custom_gate.py` | `READ_ONLY` allowlist (4 tools) + frozen-args HUD approval for everything else. Primary cause of over-prompting. |
| `core/confirm.py` | Human-only confirmation tokens. Docstring states the correct policy (irreversible only, undo otherwise). |
| `core/prompt.txt` | System prompt. Line ~195 introduced "confirm even if reversible". Line ~200 describes insights/self-evolution limits. |
| `core/insights.py` | Consent-first enum preference engine + atomic approved store. |
| `core/undo.py` | Reversibility mechanism — the intended alternative to asking. |
| `core/llm_client.py`, `core/gemini.py` | Two provider paths. |
| `providers/` | Engine pipeline, OpenAI-compatible LLM client, registry, schema, STT (whisper), TTS (piper/elevenlabs/system). **Multi-provider already exists here.** |
| `actions/open_app.py` | App launching. `_desktop_search()` (~lines 67–88) is the "opened a folder called browser" bug. |
| `actions/computer_control.py` | pyautogui global input — foreground-only. |
| `actions/browser_control.py` | Playwright browser automation. |
| `actions/dev_agent.py` | MARK's built-in coding agent; reads `AGENTS.md` before editing. |
| `actions/system_monitor.py` | RAM meter, alerts; `notify_ram=False`. |
| `actions/proactive.py` | Background suggestions; no RAM/cleanup nagging. |
| `plugins/custom_jarvis.py` | Lazy bridge exposing the custom package as one MARK tool (payload_json ≤ 64 KiB). |
| `custom_jarvis/service.py` | 37 skills, worker, SQLite, budgets, provider bridge, insight operations, metacog ledger. |
| `custom_jarvis/settings.py` | State dirs, `%LOCALAPPDATA%\CustomMarkJarvis` (XDG fallback). |
| `AGENTS.md` | Hard coding rules for any AI. Read before editing. |
| `CUSTOM_JARVIS.md` | Detailed manual of the custom layer, migration matrix, gaps. |
| `run.ps1` / `collect-data.ps1` | PowerShell launchers, mirroring the `.bat` files. Flags pass through verbatim — no `param()` block, on purpose. See §6h. |
| `scripts/collect_install.py` | Classify / fingerprint / change-track / bundle an install folder. Stdlib only. |
| `scripts/inventory_data.py` | What data does an install hold? Field names and counts, never values. |
| `scripts/migrate_legacy.py` | Old install → Ultron, with backups and redaction. |
| `scripts/verify.py` / `stress_custom.py` / `check_mutations.py` | Verification harness. |
| `docs/` | This README, HANDOFF, log. |

---

## 4. Decisions already made (do not re-litigate)

**Product**
- MARK *is* the application. No second product, no second install the user manages.
- Keep the original look, identity and features. Improve, don't rebrand.
- Windows first. Python/Qt host retained; native components where measured; Rust only for a proven
  bottleneck, never a speculative rewrite.
- Evolution is high-priority; conversation stays smooth; **no fixed daily compute quota**.

**Trust**
- Two human confirmations: (1) approve proposal before building/testing, (2) approve the *exact tested
  artifact* before activation. Any later edit invalidates approval 2.
- Staging ≠ sandbox. Generated code runs isolated: no production keys, no personal memory,
  restricted filesystem, constrained network.
- A small, separately permissioned supervisor owns approval validation, activation, migration and
  rollback. The evolving agent cannot edit it.
- Rollback covers code and DB migrations; it cannot undo external effects, so mutating real-account
  actions stay out of unattended testing.
- Memory provenance is explicit (user-stated / user-approved inference / external claim / hypothesis).
  Retrieved text is data, never authority.
- Capability broker / least privilege; protected policy and test roots; bounded retries, queues, context.

**Model & provider**
- Cloud-first for heavyweight reasoning (16 GB laptop + 4 GB RTX 3050).
- Local small model for cheap sub-tasks; it may never approve or activate; its output is always
  deterministically verified.
- Voice-controlled switching of provider **and** model, per purpose (conversation / evolution / critic).
- Fallback ladder ends local; a capability downgrade is visible, never silent.
- No paid fallback and no privacy-terms-changing fallback without permission.
- Multiple keys are not assumed to multiply quota. Never rotate to evade limits.

**Explicitly rejected by the user**
- Fixed daily evolution budget/quota.
- Pure-Rust rewrite.
- Asking permission for trivial, user-initiated, reversible actions.
- Hardcoded app name lists ("robotic" behaviour).
- Silent inference of personality/preferences; silent conversation-summary persistence.
- RAM nagging (kept disabled even after several re-confirmations).

**Resolved on 2026-11-05 (see log.txt phase 9 for the wording)**

| Was open | Now |
|---|---|
| Which apps the desktop operator supports first | **No fixed list** — learn most-used/most-frequent apps and prioritise those |
| Isolation flavour for generated code | Delegate to engineering: AppContainer + Job Object by default, Windows Sandbox for long unattended runs, VM only for deliberate risk |
| Default provider/model routes | **No named models.** Route by capability tier (local/cheap/strong) + capability flags, per task difficulty |
| Local model budget | 1.5–3B quantized, ~2 GB disk, ~3 GB RAM, cheap sub-agent roles only |
| Activation authority | **Disputed** — user wants a >70% predictor to auto-apply; assistant holds that prediction may set defaults, never permissions (see log.txt `CONFLICT 5`) |
| Camera/mic consent style | Risk-based: low-risk runs with an indicator + stop; the spoken instruction alone is not authorisation |
| Sub-agent shape | Accepted: 5 roles, max 2 concurrent, local model for summarising + first-pass critique |
| UI layout | Accepted: draggable saved widths, 100–200% scale, default 125% |
| Daily digest | At launch after 09:00, and MARK may adjust that time itself as a low-risk preference |
| GitHub token | Not needed; scanner can run unauthenticated at first |
| Vision | **Promoted from "last"** to a capability-tier concern; Gemini's current vision accepted; small local option for offline; accessibility tree preferred where cheaper |

**Still open**
- Exact provider/model defaults for each purpose.
- Whether the desktop operator ships as a separate native helper process (recommended) or in-process.
- How much of the evolution UI lives in the existing Controls drawer vs. a dedicated Evolution pane.

---

## 5. Known defects, with root causes

| Symptom | Root cause | Fix direction |
|---|---|---|
| ~~"Open browser" launched a folder named *browser*~~ **FIXED 2026-11-05** | `actions/open_app.py::_desktop_search()` typed the raw name into Start search and verified nothing | `core/app_resolver.py` resolves category words through the OS handler / installed-app index, rejects directories, asks when ambiguous, and the search-box path is disabled for category words |
| ~~Asks permission for opening a browser~~ **FIXED 2026-11-05** | 4-tool allowlist + a prompt line demanding confirmation "even if reversible" | `core/policy.py` tiers (observe/routine/guarded/sensor) + corrected prompt; camera/screen still ask, or run under a bounded `policy.grant` |
| Apps steal the screen during tasks | `pyautogui` drives the foreground desktop; no background execution path exists | Desktop-operator helper: app API → UI Automation → off-screen Win32 desktop → announced handoff. |
| Native paths not confined to workspace | Confinement exists only inside `custom_jarvis`; native MARK tools rely on the outer approval gate | Capability broker + per-tool path policy. Documented gap, not yet fixed. |
| Deferred native results not reflected in HUD | Native deferred results aren't posted as a second FunctionResponse | Known upstream behaviour. Fix requires care with both engines. |
| ~~Avatar reads as "lip-sync only"~~ **FIXED 2026-11-05** | No semantic channel | `core/expression.py`: 7-parameter vector, tag/state/prosody driven, failure guard, wired through `HudCanvas.set_expression` |
| Cancellation may wait for confirmation timeout | `confirm` design | Needs cancel-aware pending state. |

---

## 6. Ordered work plan (when authorised)

Each phase needs its own approval. Nothing here is started.

**P1 — Consent correctness (smallest, highest value)**
Replace the 4-name allowlist with a risk-tiered policy; drop "even if reversible" from `prompt.txt`;
route reversible actions through `core/undo.py`. Add session/task scopes.
*Acceptance:* opening an app, a browser, or writing a file into the approved task folder requires zero
prompts; deleting/overwriting existing data, sending messages, installing software and camera/screen
capture still require consent. No assertion weakened; new tests prove both directions.

**P2 — Semantic app resolution**
Capability lookup + verification for "browser", "notes", "music", "editor"…; reuse of running instances;
explicit failure reporting. No hardcoded vendor list; a small, user-editable preference file is allowed.
*Acceptance:* the folder-named-browser case is impossible by construction; ambiguous cases ask once.

**P3 — Desktop operator (native helper)**
Separate small Windows helper process, UI Automation + win32 + optional off-screen desktop; IPC with
capability tokens and per-action scopes; structured results with verification (window/control identity,
text actually inserted).
*Acceptance:* a specified app receives dictated text while the user's foreground window is untouched, or
MARK reports honestly that the app cannot be driven in the background. Must be tested on the real laptop.

**P4 — Provider & model routing**
Multi-provider config with Windows-protected secrets (DPAPI/Credential Manager), discovery, capability
validation, per-purpose routes, quota groups, voice switching, visible fallback, local tail.
*Acceptance:* "use Groq for evolution" and "switch conversation to <model>" work from voice and typed
input; the HUD shows the active route; a 429 backs off correctly; no silent paid/privacy change.

**P5 — Native sub-agents**
Role definitions (researcher / planner / implementer / tester / reviewer), scoped context and permissions,
structured evidence, cancellation propagation, Evolution pane visibility, local-model routing for easy roles.
*Acceptance:* a multi-step task completes with per-role artifacts and evidence; no agent can widen its own
permissions; killing the parent cancels children.

**P6 — Reviewed self-improvement**
Proposal → approval 1 → isolated test → evidence → approval 2 (bound to the exact artifact hash) →
activation by the protected supervisor → verification → rollback path.
*Acceptance:* a deliberately bad proposal is rejected by tests and never activates; a good one activates
and can be rolled back; the agent cannot modify the supervisor, the policy, or the test roots.

**P7 — Capability discovery (GitHub)**
Capability-first search, relevance scoring, licence/dependency/security inspection, manual queue, no
auto-execution. Respect API limits and honest index-coverage caveats.

**P8 — UI polish, avatar expressions & vision (last)**
Adjustable text scaling, saved panel widths, Evolution pane; **expressive avatar** (see §6b); richer
avatar rendering. Vision deferred to the very end.

**P9 — Daily "ready to apply" digest (fun, low priority)**
On the first launch of the day, MARK can show a short card listing at most 2–3 proposals that already
passed isolation and tests: one line each, a diff/evidence link, and Approve / Later / Dismiss.
*Hard rules:* nothing activates from the digest; approval 2 is still required per artifact; nothing is
shown if the queue is empty (no manufactured activity); quiet hours and a global off switch; the digest
itself is generated by the local model to save quota, and its summary may not add claims that are not in
the evidence bundle.
*Acceptance:* an empty queue produces no visible change; a rejected proposal never appears again by
default; the digest cannot approve its own items.

---

## 6b. Requirement traceability — every request so far

Use this to check nothing has been quietly dropped. Status values: **DONE** / **PLANNED** / **OPEN**.

| # | User's request | Status | Where |
|---|---|---|---|
| 1 | Keep MARK as the app, keep its look and features | DONE | baseline |
| 2 | Reviewed self-improvement, not self-rewriting | PLANNED | P6 |
| 3 | Two approvals (before build/test, before activation) | PLANNED | P6 |
| 4 | One visible install, internal staging, bounded rollback | PLANNED | P6 |
| 5 | Only approved memory; humanistic principles; no AGI claims | DONE (memory) / PLANNED (principles) | insights + P6 |
| 6 | Evolution pane left, conversation right, flexible panels | PLANNED | P8 (largest UI item) |
| 7 | Larger, more readable, adjustable UI | PLANNED | P8 |
| 8 | Adaptive resources, no fixed daily quota | PLANNED | P6 |
| 9 | Background-first app use without stealing the screen | PLANNED | P3 |
| 10 | No hardcoded app names; understand "browser" as a capability | **DONE 2026-11-05** | `core/app_resolver.py` |
| 11 | Stop asking permission for trivial, reversible, requested actions | **DONE 2026-11-05** | `core/policy.py` |
| 12 | Native role-based sub-agents | PLANNED | P5 |
| 13 | Local model for easy sub-agent roles (save API quota) | PLANNED | P5 |
| 14 | Use any API; multiple providers at startup; voice model/provider switching | **PARTIAL 2026-11-05** — parser + routing table done; engine pipeline and Providers panel not connected | P4 |
| 15 | Multiple keys/credits for higher usage, honest about shared limits | **DONE (logic)** — quota groups, no key multiplication, 429 blocks the group | P4 |
| 16 | Local model as last fallback | **DONE (logic)** — ladder ends local, no silent paid/data-sharing fallback | P4 |
| 17 | GitHub capability search for JARVIS-like projects, licence/security review | PLANNED | P7 |
| 18 | Specialised tools where foreground input is the limit | PLANNED | P3 |
| 19 | Avatar makes expressions, not just lip-sync | **DONE 2026-11-05** (channel + wiring; needs a Windows look) | `core/expression.py` |
| 20 | Fun: MARK starts the day with ready-to-apply additions | PLANNED | P9 |
| 21 | In-depth README, handoff.md, log.txt for another AI | DONE | docs/ |
| 22 | Clean workspace, current artifacts only | DONE (ongoing) | release.txt |
| 23 | Vision support | DEFERRED | last |
| 24 | Windows acceptance testing of everything above | OPEN | user's machine |

### Avatar expressions — technical note

The renderer already carries far more than lip-sync: `core/avatar.py` drives **brow lift** (`_BROW_LIFT`,
`_brow`), **gaze saccades + a deliberate `glance()`**, **state bias** (thinking → look away, brows down,
fewer blinks; asleep → lids low), **blink**, **lid openness**, and **lip spread/round**. What is missing is
a *semantic* channel: named expressions the conversation can ask for.

Design that fits the existing code:

- Add an `Expression` parameter vector (smile, brow raise, brow furrow, squint, lid widen, lip press,
  asymmetry) applied as a weighted blend inside `step()` before `paint()`; deforming the same landmark
  rings `_paint_features` already draws from.
- Three drivers, blended: (a) existing `state`, (b) an optional tag from the model's reply
  (`amused`, `concerned`, `concentrating`, `reassuring`), (c) prosody from the TTS audio actually being
  played (pitch/energy variance) — no extra model needed.
- Easing must stay **frame-rate independent** (this file already deliberately uses time constants, not
  per-frame lerps) and expression changes must never resize or reposition the HUD.
- Keep amplitudes subtle: Duchenne-style squint with a smile, never a grin after bad news. Add a content
  guard — if the reply is an error/failure/warning, suppress positive expressions.
- Deterministic tests: given (state, tag, prosody), the target vector is exact; blending/easing is
  bounded; neutral is reached after speech ends; no expression during MUTED sleep state.

Reason it is P8 and not P1: cosmetic, isolated to one file, zero security surface — but it should not be
forgotten, and it is cheap once the avatar is touched anyway.

---

## 6c. Shipped on 2026-11-05 (first implementation pass)

Three workstreams, isolated in their own modules so they cannot entangle:

1. **`core/policy.py` — risk-tiered consent.** Four tiers; unknown tools guarded; `grant()` for bounded
   sensor consent; `set_workspace_roots()` so writes inside the chosen folder are routine. `core/custom_gate.py`
   now consults it and the confirmation path is otherwise untouched (frozen args, no banner stacking,
   64 KiB argument ceiling). `core/prompt.txt` corrected so the model stops asking verbally.
   27 tests.
2. **`core/app_resolver.py` — capability resolution.** Category words resolve through the OS handler,
   then the installed-app index (word matching, not substrings), reuse running apps, refuse directories,
   ask when ambiguous, and are never typed into a search box. `actions/open_app.py` consumes it and
   verifies identity as before. 19 tests.
3. **`core/expression.py` — expressive avatar.** Seven bounded parameters with tag/state/prosody drivers,
   a failure guard, and frame-rate-independent easing, wired into `core/avatar.py` and
   `HudCanvas.set_expression`. 32 tests.

Verification after the pass: **107 files parsed, 287 tests, 99 MARK self-checks, 1,000 stress, 15/15
mutations, Ruff clean on the new and changed modules.** No existing assertion was weakened.

What this pass did **not** do: provider routing/voice switching (P4), sub-agents (P5), the desktop operator
(P3), reviewed self-improvement (P6), GitHub discovery (P7), the Evolution pane and adjustable UI (P8),
or the daily digest (P9).

## 6d. Second pass, same day — routing + workspace consent

**`core/routing.py`** (35 tests) — provider/model routes per purpose (conversation / evolution / critic),
quota tracked per **quota group** so two keys are one budget, `Retry-After` blocking the whole group, a
fallback ladder that refuses silent paid or data-sharing switches, a local tail, and a local parser for
"use Groq" / "switch the critic to Groq" / "go local for now". No provider or model name is baked in; no
socket is opened.

**Explicitly not wired:** the engine pipeline (`providers/engine_pipeline.py`), `core/llm_client.py` and
the Providers panel do not consume this table yet. Wiring it is the next P4 step and needs the UI and a
live provider to verify, so it was left alone rather than half-connected.

**`custom_jarvis/service.py`** — `_sync_workspace_policy()` is called when a workspace is restored at
startup and when one is selected, so `core/policy.py` knows which folder the user approved: writes inside
it are routine, everything outside still asks.

Verification after this pass: **109 files parsed, 322 tests, 99 MARK self-checks, 1,000 stress, 15/15
mutations, Ruff clean** on new and changed modules.

## 6e. Migrating data from a previous install

`scripts/migrate_legacy.py` (17 tests) copies an older install's state into a new Ultron folder:
`config/api_keys.json` (settings + provider config), `memory/long_term.json`, and
`%LOCALAPPDATA%\CustomMarkJarvis\` (`knowledge.sqlite3`, `workspace.json`, `approved-insights.json`).
Credential-looking fields are blanked by default and reported by name only; `--include-keys` overrides.
Name migration JARVIS -> Ultron unless `--keep-name`. Dry run, per-file backups, atomic writes, source read-only.

**State map, for anything this script misses:** nothing else in the install folder is identity — screenshots,
`backups/`, `repairs/` and the Playwright profile are caches or history and are intentionally not migrated.

**Observed on the user's machine (screenshot, 2026-11-05):** the pre-rename build *does* launch and render on
Windows, assistant name JARVIS, but the provider connection fails repeatedly ("NET: Connection failed —
retrying in 6s. (a VPN may be required)"). That is a network/provider issue, not a UI or packaging one, and it
is the first thing to diagnose on the real machine.

## 6f. Where user data lives, and what this build does not store

| Path | Contents |
|---|---|
| `<install>/config/api_keys.json` | settings: name, voice, colour, wake word, wake-word choice, provider config, plugin settings, **credentials** |
| `<install>/memory/long_term.json` | facts only: `identity`, `preferences`, `projects`, `relationships`, `wishes`, `notes` (and `sessions` in older/upstream builds) |
| `%LOCALAPPDATA%\CustomMarkJarvis\` | `knowledge.sqlite3` (custom tasks), `workspace.json`, `approved-insights.json` |

Everything in `actions/`, `core/`, `providers/`, `plugins/` is code and holds no user data — a user asked whether
their conversations were in those files; they are not.

**This build stores no conversation transcript.** `main.py::_save_session_summary` clears the in-RAM log rather
than persisting it (manual-memory policy). `memory_manager.save_session_summary` still exists and would append a
1–2 sentence summary to `long_term.json["sessions"]`, but nothing calls it. Consequence for migration: an install
that only ever ran this build has nothing to carry over except explicitly saved facts, settings and workspace state.

`scripts/inventory_data.py` (10 tests) reports what is actually present — sizes, key names, record counts, sqlite
row counts — and never prints a value it finds. Use it before migrating or before sending anything for diagnosis.

**Open decision:** opt-in local conversation archive with retention and a delete command, or remain
manual-memory-only.

## 6g. Install collector, and a measured Qt ceiling

`scripts/collect_install.py` + `collect-data.bat` (20 tests): classifies every file in an install folder
(code/doc/cache/config/data/**unknown**), fingerprints them, reports NEW/CHANGED/GONE against the last run,
supports `--watch`, and can write a data-only ZIP (manifest + report, secrets blanked) for diagnosis. Default
target is the user's own folder, `D:\Downloads\mark-custom-jarvis`.

**Measured, worth keeping:** PyQt6 **6.12.0** segfaults when `QAudioOutput()` is constructed with no audio
backend; 6.8.2 does not. `requirements.txt` is pinned to `PyQt6>=6.6,<6.12` with the reason written beside it.
Re-test before raising that ceiling.

## 6h. PowerShell entry points

The user works in PowerShell, so every launcher now exists twice. `run.ps1` and `collect-data.ps1` mirror
`run.bat` and `collect-data.bat`.

- **Flags pass through verbatim.** `collect-data.ps1` deliberately has **no `param()` block**, so
  `.\collect-data.ps1 --bundle data.zip` reaches the collector unchanged. A `[CmdletBinding()]` + `param()`
  wrapper would make PowerShell try to bind `--bundle` as a parameter and fail, and any "helpful" renaming of
  flags into `-Bundle` would fork the documented interface in two.
- **Python discovery order:** `.venv\Scripts\python.exe` if present (the interpreter the app itself uses), else
  the first working `py -3.12 / -3.13 / -3.11 / -3 / python / python3` that reports **3.8+**. The collector is
  stdlib-only, so a bare machine can run it *before* `.venv` exists — that is the whole point.
- **`run.ps1` never upgrades an existing `.venv`**, same as `run.bat`. It also refuses 3.14.
- **Exit codes survive the wrapper** (0 ok / 2 not a folder / 3 no Python or missing script), so
  `$LASTEXITCODE` and scheduled tasks behave. A non-zero exit holds the window open when launched by
  right-click → *Run with PowerShell*; a success never waits for a keypress.
- **Encoding:** the launchers set `PYTHONIOENCODING=utf-8` and console UTF-8 so redirected output is not mangled,
  but Windows PowerShell 5.1 still writes files as UTF-16LE — the docs tell the user to use
  `| Set-Content -Encoding utf8`.
- **Tests:** `tests/test_launchers.py` (11). Static layer always runs (CRLF, pure ASCII, names the script it
  launches, no install commands, documents the execution-policy trap). The live layer parses both files with
  PowerShell's own `Parser::ParseFile`, runs the collector through the wrapper and asserts exit-code
  passthrough, and checks the *missing script* branch — and **skips** rather than fails where PowerShell is
  absent. A missing tool is not a defect in the file.


## 6i. Launch-path optimisation (measured, not asserted)

`scripts/bench_startup.py` runs each stage in its own subprocess and reports medians. Before and
after, on the same machine, same bench:

| Stage | Before | After |
|---|---|---|
| `import main` | 723 ms | 170 ms |
| action discovery | 185 ms | 117 ms |
| heavy libraries loaded at launch | genai, genai.types, PIL, PIL.Image | none |
| one turn of local work | 0.7 ms | 0.7 ms (untouched on purpose) |

What changed:

- `main.py`: `from google import genai` + `from google.genai import types` (590 ms, of which
  `types` alone was 507 ms) became `LazyModule("google.genai")` / `LazyModule("google.genai.types")`,
  plus `_GENAI_INSTALLED = installed("google.genai")` so "is it installed?" still answers without an
  import. **Three return annotations had to be quoted** (`-> "types.LiveConnectConfig"`): without
  `from __future__ import annotations`, an annotation is evaluated when the function is *defined*,
  which is during module import, which would have quietly undone the whole deferral.
- `actions/youtube_video.py`: deleted `import pyautogui` and `import numpy as np` — both dead
  (no `pyautogui.` call, no `np.` use, flags unread anywhere in the repo). `requests` → `LazyModule`,
  `youtube_transcript_api` → imported where used. Also dropped dead `import time`, `import shutil`,
  `get_os`.
- `actions/screen_processor.py`: `PIL.Image` → `LazyModule("PIL")` with a configure hook that binds
  the submodule, because the call sites say `PIL.Image.open(...)` and importing `PIL` alone does not
  bind `Image`.
- `main.py` `_build_config`: config read through a context manager (the old `open(...).read()` left
  the handle to the GC, and on Windows an open file is one the settings dialog cannot rewrite), and
  the `except` fallback `self._asst_name = "JARVIS"` → `identity.NAME`. That literal renamed the
  assistant back to a name this build stopped using, exactly when something else had already failed.

Enforced by `tests/test_lazyimport.py` (15 tests): behaviour of `LazyModule` (a probe module that
records whether it executed — a deferral that silently resolves looks identical and is only slower),
and an AST scan of `actions/` + `plugins/` that fails on module-scope imports of heavy libraries.
`TYPE_CHECKING` blocks are excluded because they never execute; `actions/screen_processor.py`
(numpy) and `actions/system_monitor.py` (psutil) are allow-listed with reasons.

Not touched, deliberately: per-turn Python work (0.7 ms — no win available), `_trimmed()`'s
per-message `json.dumps` (147 µs for a 250-message history; caching it would add state for a
rounding error), and `browser_control.py`, which already deferred `playwright` correctly.

## 7. Verified external facts (as of 2026-11-05) — re-check before relying on them

- **Gemma 4 family** (official overview): E2B / E4B / 12B / 26B-A4B MoE / 31B dense. Approx Q4 load memory
  including 20 % overhead: 2.9 / 4.5 / 6.7 / 14.4 / 17.5 GB. MoE does **not** mean 4 B of weights resident.
- **Google API pricing:** Gemma 4 family input/output/cache listed as free; free-tier content is used to
  improve Google's products. Exact 31B/26B endpoint IDs and per-account quotas **unverified**.
- **OpenRouter:** `google/gemma-4-31b-it:free` exists (262 K context, tool calling). Free-model limits:
  20 req/min, **50 req/day** below the credit threshold; 1,000/day at ≥ ~10 credits purchased.
- **Groq:** `qwen/qwen3.8-27b` — **Preview**, 131,072 context, 16,384 max output, tool use, JSON schema,
  reasoning, vision, ~450 tok/s advertised, $0.80/M input, $4/M output. Published rate table is not proof
  of free entitlement for this user's account.
- **Colab:** free GPUs/resources not guaranteed; managed-runtime rules restrict service hosting and
  notebook-bypass use. Not a dependable always-on backend.

Rule: prefer official docs over third-party "unlimited free" claims. Never present a published table as a
guarantee for the user's account.

---

## 8. Environment facts about the user's machine

- Ryzen 7 7445HS (6C/12T, 3.2 GHz), **16 GB DDR5-5600** (15.3 GB usable, 1 of 2 SODIMM slots used).
- **RTX 3050 Laptop 4 GB** dedicated + Radeon 740M iGPU (~459 MB reserved, uses shared RAM).
  Not pooled: AMD and NVIDIA memory is not additive. Shared GPU memory is system RAM.
- NVMe 477 GB, ~313 GB used (~164 GB free at time of observation).
- Observed under load: 13.6 GB RAM used / 1.7 GB available; 26 GB of 41.2 GB committed; ~68 °C.
- Consequence: a 27–31 B model is not comfortable locally. Cloud-first for heavy reasoning, small local
  model for cheap roles, and internal adaptation without RAM nagging.

---

## 9. How to work on this without breaking it

1. Read `AGENTS.md` (threading, one QApplication, tools never touch widgets).
2. Change code in `mark-jarvis/`, not in the ZIP.
3. Run `python scripts/verify.py` before and after. Compare counts — they must not drop.
4. Keep CRLF where it already exists. Check `run.bat` stays the single launcher and stays CRLF.
5. Add tests for new behaviour; never edit an existing assertion to fit new code.
6. Update `verification-results.txt`, `readme.md`/`CUSTOM_JARVIS.md`, this file and `log.txt`.
7. Rebuild the ZIP with the existing top-level `mark-custom-jarvis/` folder, verify CRC, single `run.bat`,
   no caches, no keys. Record size/files/SHA256 in the workspace `release.txt` (a ZIP cannot contain its
   own hash).
8. Keep the workspace clean: current source, current ZIP, current verification output, documentation.
   Delete superseded artifacts as you go.

---

## 10. Open questions to put to the user before P3–P6

1. **Which apps must the desktop operator support first?** (Notes/Notepad, Word, browser, Spotify, …)
   Each needs its own automation path and test.
2. **Acceptable isolation for testing generated code:** Windows Sandbox, Hyper-V VM, or a restricted
   local process? (VM = strongest, slowest; Sandbox = good, needs Windows Pro.)
3. **Default routes:** which provider/model for conversation, evolution and critic — and is free-tier
   data-sharing acceptable for *private* code, or only for public/synthetic content?
4. **Local model budget:** maximum disk and RAM you will allocate for the local fallback model.
5. **Activation authority:** should activation ever happen without you being present, or always require
   approval 2 while you are there?
6. **Camera/microphone policy:** does the spoken instruction alone authorise camera use, or do you want a
   persistent on-screen indicator plus a one-tap stop in every case?

---

## 6j. Launch path — made to be one double-click (2026-11-06)

The rule from the owner: *"make the setup easiest possible, so I can just run the
bat file."* Three defects in the launch path were the reason it was not.

1. **Python was a manual prerequisite.** `run.bat` printed a web address and
   exited. It now looks for 3.11–3.13 (`py -3.12`, `-3.13`, `-3.11`, then
   `python`), and if none is there, offers to install 3.12 through winget —
   one question, default yes, per-user install, no administrator prompt. If
   winget is absent it falls back to the old message and the python.org link.
   Version 3.14 is still refused rather than risk a half-built venv.

2. **A broken `.venv` bricked the launcher.** A `.venv` outlives the Python that
   made it: uninstall, upgrade, or copy the folder to another machine, and every
   launch died inside pip. The launcher now runs a one-line version check against
   the existing interpreter and, on failure, moves `.venv` to `.venv.old` —
   moved, never deleted — and builds a fresh one.

3. **One bad package took the whole install down.** `scripts/bootstrap.py` ran a
   single `pip install -r requirements.txt`; a failure there (a wheel missing for
   a new Python, a corporate proxy, an optional extra) aborted everything and the
   window closed before the reason could be read. It now: streams output to the
   console *and* to `setup-log.txt`; falls back to one-package-at-a-time on
   failure so the other forty still install; reports which packages are missing
   and what stays switched off; proves the app can start by importing the
   third-party modules `main.py` imports at module level (read out of `main.py`,
   not hardcoded) plus `PyQt6.QtWidgets`; retries a `--force-reinstall` once for
   anything that fails; and only then writes the ready marker. The marker is
   keyed on a hash of `requirements.txt`, the Python version and bootstrap's own
   version, so any change triggers a re-run and a satisfied install costs nothing.

Also fixed on the way, because it is a security defect and not a preference:
**`.gitignore` ignored nothing.** Every pattern carried a trailing `# comment`,
which git reads as part of the pattern. `config/api_keys.json`, `config/certs/`
and the WhatsApp session directory were all *not* ignored on a project whose own
header says committing them publishes the key. Comments moved to their own lines;
`git check-ignore` now confirms all of them, and `tests/test_bootstrap.py` asserts
it with real git so it cannot rot again.

Verification: 153 Python files, **767 tests** (27 new in `tests/test_bootstrap.py`),
offline, exit 0. **Not verified: cmd.exe itself.** The `.bat` is checked for the
things that stop it running — bare LF, non-ASCII bytes, a `goto` with no label, a
launcher that grows its own pip call — and everything it calls is tested, but this
sandbox is Linux, so the first real execution of `run.bat` is on the owner's
machine.

## 6k. Interface scale, provider-first setup, and the reconnect hot loop (2026-11-06)

Reported from a screenshot of the running app, in the owner's words: the GUI is
"still small and I can't edit it", the first launch "didn't have the multiple API
thing we decided", and the activity log was a column of identical
`SYS: JARVIS online.` lines.

| # | Defect | Cause | Fix |
|---|---|---|---|
| 1 | Interface too small, not adjustable | `ui_scale` was read at launch but nothing in the UI wrote it; auto value was `screen/900` = 1.20 on 1080p | Scale buttons (100–185 %) in ⚙ → Customise, RESTART TO APPLY; auto baseline now `/760` = 1.42 |
| 2 | First run demanded Gemini | `SetupOverlay` had one field; `_check_config` required `gemini_api_key` | Overlay rebuilt: Gemini **or** any number of OpenAI-compatible services from the provider's own `CATALOG`; gate is now `has_a_brain()` |
| 3 | Re-opening setup erased settings | `_on_setup_done` wrote a two-key dict over `api_keys.json` | `config_manager.apply_first_run()` merges; blank fields never delete |
| 4 | Hot reconnect loop | The handle-rejected branch matched the **substring** `"handle"` in any error and set backoff to 0 then `continue` — which skips the loop's sleep | `core/reconnect_policy.py`: specific markers, one drop per streak, delay never zero, 3→30 s backoff, error shown once with credentials redacted |
| 5 | Greeting said JARVIS | Two literal strings in `main.py` | `_assistant_name()` reads config, falls back to `identity` |
| 6 | First-run panel at (-10, -90) | Geometry computed before the window laid out | `_place_overlay()` centres and clamps, now and on the next event-loop turn |
| 7 | A ghost provider row drawn twice | `takeAt()` unparents nothing; `deleteLater()` only queues | `hide()` + `setParent(None)` before `deleteLater()` |

Defects 6 and 7 were found by rendering the interface off-screen; 7 was found by
the test written for 6. Both are the class of bug that a screenshot reports
faster than a test suite does — which is why the HUD is now rendered and looked
at, not just constructed.

**Where the reconnect policy lives:** `core/reconnect_policy.py`, 15 tests, no
asyncio, no Qt, no network. `main.py` calls `classify()` in both the resumption
branch and the generic handler and sleeps for the returned delay before
`continue`.

**Interface evidence:** rendered with Qt's offscreen platform at 1920×1080 at
100 % and 145 % — `renders/hud-at-145-percent.png`, `renders/setup-multi-provider.png`,
`renders/customise-ui-scale.png` in the workspace. Geometry, sizing and colour are
checkable this way; **how it looks on the owner's actual panel is not**, and the
first real launch is still the acceptance test.

Verification: 157 files, **818 tests**, 99 MARK self-checks, 15/15 mutations,
exit 0.

## 6l. The bug hunt, and a size you can set (2026-11-06)

Same day, after 1.2.3. The instruction was "make sure there are no bugs in this";
the suite was green and two of the worst defects were inside 1.2.3's own fixes,
so this was a read-the-source pass, not a run-the-tests pass.

Twenty-two defects, each with a test that fails without its fix
(`tests/test_bugfix_pass.py`, 56 tests):

| # | Defect | Why it mattered |
|---|---|---|
| 1 | `resizeEvent` forced the setup panel to 460x390 | undid the centring added in 1.2.3 on the first resize |
| 2 | The relaunch inherited `QT_SCALE_FACTOR` | "restart to apply" applied nothing; now strips it and checks the result |
| 3 | Scale docstring said 1.45, maths gives 1.40 | and three documents repeated 1.42 |
| 4 | A damaged `api_keys.json` was overwritten by the next save | data loss disguised as a settings change; kept as `.broken-<epoch>` |
| 5 | Config writes were not atomic | truncate-then-write is how a config gets damaged |
| 6 | Stored scale up to 3.0, no way back | the panel that would fix it goes off the screen; clamped 0.85–2.50, AUTO added |
| 7 | `apply_first_run` indexed `providers[0]` past skipped rows | AttributeError inside the save path |
| 8 | Empty provider CATALOG | IndexError on first click |
| 9 | A QSS rule appended per failed click | stylesheet growth, red border never cleared |
| 10 | `SetupOverlay` had no `hideEvent` | ghost frame over the HUD |
| 11 | Save failure printed to a console; `_ready = True` regardless | looked like success, then setup again next launch |
| 12 | Reconnect markers included `invalid_argument` / `not_found` | my own regression: a bad model name was treated as a dead session and the repair branch was skipped |
| 13 | The "N attempts failed" summary repeated every attempt | the wall of lines again |
| 14 | Net backoff doubled a stored 0; capped at 60; never reset | hot retry by another road, and a minute-long delay after one blip |
| 15 | `prompt_reconfig` stacked setup panels | hidden panel still wired to the same handler |
| 16 | `dashboard/server.py` used an undefined `port` (9 places) | NameError on any Linux box with a firewall running |
| 17 | `"active" in "Status: inactive"` | an inactive firewall treated as active |
| 18 | `load_api_keys` returned non-dict JSON | AttributeError at start-up |
| 19 | `save_api_keys` still open-coded its own write | had 4 and 5 |
| 20 | `.gitignore` missed the new backup files | they contain the keys |
| 21 | 820x580 minimum larger than a scaled-down screen | window could not fit; microphone button off-screen |
| 22 | Provider address accepted without a scheme | failed later, where nothing could explain it |

**Sizing, as it stands:** − / + steppers in 5% steps from 85% to 250%; presets
100–185; AUTO; `Ctrl+=` / `Ctrl+-` / `Ctrl+0` / `Ctrl+Shift+R`; the window
remembers its size and clamps to the screen. Qt still only takes a global scale
factor at start-up, so applying it is a relaunch — one that now works.

**Not verified:** any of this on Windows. Fixed and tested on Linux, off-screen.
`core/ui_windows.py` has still never run on Windows.

## 11. Prompt to paste into another AI

> You are taking over a Windows-first Python/PyQt6 voice assistant called MARK (derived from
> FatihMakes/Mark-LVI, CC BY-NC 4.0). The active source is `mark-jarvis/`; the delivered ZIP is
> `ultron.zip`. Read `readme.md`, `HANDOFF.md`, `log.txt`, `AGENTS.md` and `ALGORITHMS.md` before
> anything else; `docs/CAPABILITIES.md` is a menu of what is not built. A deterministic evidence/repair
> layer already exists in `custom_jarvis/` and is verified offline (880 tests, 15/15 mutations, 1,000
> stress scenarios). Built and wired: risk-tiered consent, capability-based app resolution, avatar
> expressions, the syllabus algorithms, structure-first computer use, and an evolution loop that
> measures before it keeps anything. Still absent: role-based sub-agents, the desktop sandbox, local
> vision, the 09:00 digest, app-usage learning. **Feature work is paused by decision** — fix defects,
> add nothing. Do not weaken tests, do not bypass the approval/registry gates, and do not describe the
> Windows UI Automation bridge as working until it has been run on Windows. Respect §1 and §4.

---

## 12. Glossary

- **MARK** — upstream application (HUD, avatar, voice, tools, providers).
- **custom_jarvis** — our namespaced package; cannot shadow MARK's `core/`.
- **ControlledRegistry** — per-invocation tool registry inside the custom engine.
- **EvidenceEngine.prepare_args** — validates/normalises tool arguments before execution.
- **Confirmation token** — HUD-issued approval object; the model cannot construct one.
- **Insight candidate** — temporary, RAM-only preference suggestion; expires after 1 h.
- **Approved store** — `approved-insights.json`, enum values only, no transcript text.
- **Activation supervisor** — planned protected component that owns release/migration/rollback.
- **Desktop operator** — planned native helper for background app control.

## 6m. Bug hunt round three — the paths nobody walks (2026-11-06, build 1.2.5)

Feature freeze holds: nine defects in this pass, thirteen in the build (the four
earlier ones — a key getter, a prompt fallback, a doubly-reported failure, a
run loop with no session — are in `log.txt`). Nothing was designed. The three earlier passes
took what the user could see; this one went to the code that runs once (start-up),
the code that guards the disk, and the engine that only runs on a non-Gemini
provider. All measured before changing.

| # | Defect | Why it mattered |
|---|---|---|
| 1 | Four tool schemas did not declare the parameters their handlers read | a model cannot pass an argument that is not declared: `drag` had no box, `append` overwrote |
| 2 | `traceback.print_exc()` inside action discovery | under pythonw `sys.stderr` is None, so the error handler raised and took start-up with it |
| 3 | A capability could vanish with only a console line | missing playwright removes `browser_control`; looked like the assistant refusing. Now named in the activity log |
| 4 | `core/policy.py` named `system_monitor` / `screen_processor`, not `screen_process` | the sensor tier and its consent wording applied to nothing real |
| 5 | The file-safety test was "inside home", and home holds every credential | `~/.ssh/id_rsa` and the program's own `config/api_keys.json` were readable on request |
| 6 | A turn could stay open for ever when a tool call had no result | consent refused / tool raised / interrupt: the UI sat in THINKING until the watchdog |
| 7 | The test suite wrote the user's real `config/api_keys.json` | building a `MainWindow` saves the window size; running the verification changed the size the user's window reopens at |
| 8 | `code_helper` base64-encoded the screenshot twice, read neither | dead work on every visual question |
| 9 | `_smoke_harness` raised IndexError when imported | it is a program; it now says so and exits 2 |

**The turn-end fix, precisely.** `_PARTIAL_TOOL_GRACE = 1.5 s`, armed when the
calls are emitted (not only when a result arrives), restarted per result. What
has not answered is written into the history as *"No result came back from X."*
rather than dropped — an assistant turn announcing two calls and answering one is
a transcript the vendor's API rejects on the next request, which converts a
missing result into a dead session.

**Measured pipeline matrix** (fake model, documented protocol, no network):
text turn · call-only · text-then-call · both keys in one event · text without a
full stop · two calls answered twice / once / never · the same call twice ·
text after calls · empty batch → **eleven scenarios, all end**. The earlier note
that a text+tool_calls batch hung was a defect in the probe, not in the engine;
the real hang was a partial tool response.

**Verification:** 162 files parsed · 939 tests (6 skipped) · 99 MARK self-checks ·
1,000 stress scenarios · 15/15 mutations · `verify.py` exit 0.
New tests: `test_live_config.py` (17 — the real `google.genai.Tool` build, the
provider path end to end), `test_file_safety.py` (12), `test_tool_contract.py`
(19 total).

**Open, and deliberately not decided here:** `browser_control` without
playwright. Install it with the app, or remove the tool. Both are product
decisions; neither is a bug fix.

**Still not verified:** Windows. Everything above ran on Linux, off-screen.

## 6n. Driving it, not reading it (2026-11-06, build 1.2.6)

The instruction was "make sure Ultron works just as intended, that all features
work, and that the possible edge cases work too". A green suite does not answer
that, so this pass called every tool with hostile input and started both engines
from a dozen config states. Nine defects, each with a test
(`tests/test_edge_cases.py`, 18 tests).

| # | Defect | Why it mattered |
|---|---|---|
| 1 | `"action": null` crashed 6 of 17 actions | `dict.get(k, default)` returns the default only when the key is ABSENT; the model gets "NoneType has no attribute 'lower'" |
| 2 | Wrong-typed arguments crashed tools (`"action": 5`, `"volume": "loud"`) | values are now coerced to the type the declaration already promised |
| 3 | Concurrent memory writes lost facts — 53 of 180 survived | read and write were locked separately, so the whole read-merge-write was not atomic |
| 4 | `update_memory({"notes": "x"})` replaced a whole category | every entry in it was deleted by one malformed update |
| 5 | A config write could abort the app | read-only folder → `OSError` out of a Qt slot → PyQt6 abort |
| 6 | `"model": 123` in the config crashed the provider build | at start-up, where the only symptom is "it never starts" |
| 7 | A non-string provider id raised TypeError | now LookupError with a clear message |
| 8 | An unreachable model server erased the stored vision decision | cold Ollama → `vision: ""` over a stored yes → screen/camera tools withdrawn every launch |
| 9 | `save_memory` answered "ok" when it saved nothing | the model told the user it had remembered something |

**The two boundary fixes are structural, not spot patches.** `_clean_parameters`
drops explicit nulls and `_coerce_parameters` applies the declared type, both in
`core/action_loader.run()` — so every action, including ones written later, is
covered; the eight inline tools in `main.py` get the same treatment where their
arguments arrive. `save_memory` and `manage_monitor`/`screen_process` were also
made null-safe at their own read sites.

**What was driven:** all 26 declarations through the real SDK (24 for a text-only
provider — screen and camera withheld); every action through the real loader with
null, wrong-typed, oversized and empty arguments; all 8 inline tools through
`main._execute_tool_approved`; window states, log with None/20k chars/emoji,
mute, camera stream, resizes to 0x0 and 4000x3000, scale floor/ceiling/AUTO,
missing face model; unicode and 5 MB files, name-too-long, directory-as-file,
copy/move/rename collisions, delete-to-trash + undo, undo cap; corrupt and
list-shaped memory files, six concurrent writers; five provider kinds, all three
tool-schema dialects, prompt-mode parsing on garbage; startup from no config,
empty config, junk mode, unknown provider and creds-as-a-list.

**Verification:** 163 files · 957 tests (6 skipped) · 99 MARK self-checks ·
1,000 stress scenarios · 15/15 mutations · `verify.py` exit 0.

**Not verified, and specifically:** Windows; screen capture (mss absent here);
browser automation (no Playwright); any live provider (no network, no keys); a
real microphone and speaker; rendering on a real display.

**Note for whoever continues:** to run anything that imports `main.py` on Linux
you need two things this sandbox is missing — `libportaudio` (extract
`libportaudio2` from Debian into the library path) and a stand-in
`sounddevice` module. With both, `import main` works and the inline tools and
startup path are testable without hardware.

## 6o. Six beliefs turned into instruments (2026-11-06, build 1.2.7)

Six claims were true statements about code and unproven facts about a machine.
This section is the instrument panel for the ones a suite cannot settle.

**One command:** `python scripts/verify_all.py`. It runs five verifiers as separate
processes, so a missing Qt, a dead driver or a broken browser cannot take the rest
down with it, and prints one table:

| verdict | meaning |
| --- | --- |
| WORKS | every check that applies passed |
| PARTLY TESTED | everything that ran passed, but some checks do not apply on this platform |
| BROKEN | at least one check failed — the line above says why |
| NOT TESTED HERE | nothing could run here |

Exit code is 1 only when something failed. **A SKIP is never a failure** — it is a
question that does not apply, and it always prints its reason. `--json` writes the
full evidence to `verification/capabilities.json`; `--only display,audio` runs a
subset.

**The five verifiers:**

- `scripts/verify_windows.py` — 16 native checks (DPI, window fits, no console
  flashes, audio devices, mic records, speaker tone, screen capture, camera, UIA
  tree, volume and brightness round-trips, browser discovery, app resolution,
  ASCII PowerShell, `run.bat` preflight). Three run on every platform.
- `scripts/verify_display.py` — renders the real `ui.MainWindow` at 980x700,
  1280x800 and 1600x900 and inspects the pixels: something is drawn, the log panel
  is inside the frame, text is painted inside it. Saves the renders.
- `scripts/verify_capture.py` — through `actions.screen_processor`, so it tests the
  code the app uses, not a library demo.
- `scripts/verify_audio.py` — devices, a real recording with peak and RMS, output
  latency, optional 440 Hz tone. Silence is not failure; an exception is.
- `scripts/verify_browser.py` — Playwright launch/load/read/click/type/screenshot,
  plus `actions/browser_control` itself. If a browser binary will not start it
  reads `ldd` and names the missing libraries instead of "closed".

**Four real defects they found** (all invisible to the suite, all fixed, all with a
test): a repeated streamed tool name welded itself into `open_appopen_app`; a
refused image was never recorded because the status code lives inside a
`RuntimeError` message, so `can_see()` stayed `None` for ever; an HTML gateway error
page was logged verbatim; and `xdg-mime`'s "No default applications for …" sentence
was accepted as an app with 0.95 confidence, so "open the browser" reported success
and opened nothing.

**On this Linux container:** display 12/12 pass; platform 2 pass / 14 skip; capture,
audio and browser fail with the real reason (no display, no PortAudio, a Chromium
missing `libavahi`/`libxkbcommon`). Those three are hardware and OS facts, not
Ultron defects — they are precisely what the user's Windows machine will answer.

**Gate:** 172 files · 983 tests (6 skipped) · 99 MARK self-checks · 1,000 stress
scenarios · 15/15 mutations · `verify.py` exit 0. `tests/test_verifiers.py` keeps the
instruments from rotting: each must parse, answer `--help`, and be wired into the
runner, and `verdict_for()` is asserted so SKIP can never quietly become a pass.

**Sandbox warning for whoever continues here:** `/tmp` is a 992 MB tmpfs. A
Chromium download filled it and every later `pip install --target /tmp/...` failed
with `No space left on device`, which looks like a missing package rather than a
full disk. Delete browser debris first; `pip install --target /tmp/qtlibs PyQt6`
plus a `libxkbcommon.so.0` copy is the minimum to render the UI.

## 6p. The capability that was lying about itself (2026-11-06, build 1.2.8)

An audit of "what else gates this build" turned into the worst defect of the run.
`core/ui_windows.available()` answered **usable, pywinauto** whenever pywinauto
was importable — which it always is here, because three plugins import it
directly — while the driver's pywinauto branch raises `NotImplemented`. The tool
ladder therefore preferred the accessibility tree over vision, as required, and
the first action raised an error naming a package the user had never installed.

Fixed: `uiautomation` is a declared Windows dependency (`requirements.txt`) and
known to `core/installer.py`; `available()` reports usable only for a backend
that can be driven and otherwise says exactly what to install; `verify_windows.py`
now asks `core.ui_windows.available()` instead of hand-importing its own copy of
the dependency; `tests/test_ui_bridge.py` (9 tests) locks the invariant.

See **`GATEKEEPERS.md`** for the full register: six build gates, the proof gates
only the user's machine can clear, the licence constraint on shipping, the
decision gates, and the structural one that matters — **there is no CI, so nothing
has ever run on Windows automatically**. A `windows-latest` job running
`verify.py` + `verify_all.py` is the cheapest unlock in the project.

Gate: 173 files · 992 tests (6 skipped) · 99 self-checks · exit 0.

## 6q. The proof gate (2026-11-06, build 1.2.9)

`scripts/proof_gate.py` — sixteen **claims**, each a chain, four verdicts
(`PROVEN` / `PARTIAL` / `FAILED` / `NOT PRESENT`). This is the instrument for the
only thing still in the way: nothing here has ever run on Windows.

```powershell
python scripts\proof_gate.py
python scripts\proof_gate.py --live            # your key / local model
python scripts\proof_gate.py --only voice_in,acts --json proof.json
python scripts\proof_gate.py --budget-startup 20 --budget-ram 900 --budget-turn 4
```

Exit code is 1 when any claim is `FAILED` or `NOT PRESENT`, 0 otherwise, so it can
gate a release — and `PARTIAL` never reads as a pass.

**Two claims are `NOT PRESENT`, and they are the finding of this build:**

1. **Memory is not approval-only.** `save_memory` writes immediately and answers
   `silent: true`; the model can persist an inferred preference without asking.
   The standing rule is "only remember what the user approves". Building it is a
   behaviour change — a confirmation on every inferred memory would fight the
   "do not prompt me for trivia" rule — so it is flagged, not silently added.
2. **There is no daily digest in Ultron.** The only "digest" in the tree is an
   md5 hash. It belongs to the Agentic OS milestone, not this app.

Proven here without hardware: `consent` and `persona` (PROVEN); `acts` (PARTIAL —
write and read-back in `~/Documents`, a `/tmp` write refused, an SSH key path
refused as credentials, the model's tool declared and callable). Everything else
is PARTIAL with the exact missing step printed.

`tests/test_proof_gate.py` (13 tests) pins the verdict arithmetic so a claim can
never round up: FAILED > NOT PRESENT > PARTIAL > PROVEN, and one skipped step
stops a PROVEN.

Gate: 175 files · 1,005 tests (6 skipped) · 99 self-checks · `verify.py` exit 0.

## 6r. Memory now asks (2026-11-06, build 1.2.10)

The proof gate's `NOT PRESENT` for "approval-only memory" is fixed, and the defect
was not where the claim was. `core/policy.py` has always classified `save_memory`
as **GUARDED** ("memory is permanent — remembering is approval-gated"); the inline
tool path in `main.py` never consulted the policy and called `update_memory`
directly. The rule existed and nothing enforced it.

`core/memory_consent.py` is the enforcement — one small module, called where the
write used to be. `save_memory` now parks behind `core/confirm.request`, the same
banner the shutdown path uses, already bound to the HUD in `run()`. The banner
shows the fact verbatim; nothing is stored until CONFIRM; the model gets a
`[CONFIRMATION_PENDING]` sentence and is told not to claim success.

Three deliberate choices, all defended in the module docstring:

1. **No "the user already said remember" shortcut.** Classifying intent from an
   utterance makes "do you remember what I told you?" a silent write when it
   guesses wrong, and the wrong direction is permanent.
2. **One banner at a time.** The gate holds a single pending decision; a second
   memory write would have replaced the first and lost it silently. It now says so.
3. **Fail closed.** No interface bound means nothing is written — `request_write`
   returns `confirm.request`'s refusal unchanged.

The digest claim was **removed** from `scripts/proof_gate.py`, not built: a daily
digest is an Agentic OS milestone property, and inventing one in a frozen app to
satisfy an instrument would be the wrong fix.

Gate: 177 files · 1,016 tests (6 skipped) · 99 self-checks · `verify.py` exit 0.
Proof gate: 3 PROVEN (consent, memory_approval, persona) · 11 PARTIAL · 1 FAILED
(no display here) · 0 NOT PRESENT.

## 6s. The daily digest, and a test that blamed the machine (2026-11-06, build 1.2.11)

**`core/digest.py`** — the digest is built, and it is inert by construction:
`build()` reads local files and returns a dict, `render_*()` make words,
`should_run()` decides if it is due. None opens a socket, starts a process, calls
a tool or writes a file. The one write is `save_last_run()`, a single date.

Reports: facts remembered today, count of older facts, watched topics, reminder
names. Delivery twice — the `daily_digest` tool, and `_digest_loop` in `main.py`
which writes the report to the activity log at `digest_hour` (default 20:00, set
in `memory/config_manager.py`) and never speaks.

Three deliberate details: it does **not** import `actions/reminder.py` (that
module creates its folder — a digest that creates a folder changed the machine);
watched topics are excluded from the fact count because they are machine state;
the spoken form is capped at 240 characters.

**`sees_screen` was FAILED and should have been SKIP.** Screen capture raised
"Cannot connect to display" on a container with no screen: the question did not
apply. The gate now asks `_has_display()` first — no display is SKIP with the
reason, a display that returns no frame is still FAILED. A report that cries
failure on a machine that could not answer teaches the user to ignore the colour.

Gate: 179 files · 1,038 tests (6 skipped) · 99 self-checks · `verify.py` exit 0 ·
proof gate 4 PROVEN / 12 PARTIAL / 0 FAILED / 0 NOT PRESENT (exit 0).

## 6t. Five tools, a tablist, and an assistant that can read its own hands (2026-11-06, build 1.2.12)

Asked for: integrate **REA, HyperFrames, Hindsight, VoiceStudio, Hypit** natively;
give the Dashboard a **tablist** for them; make Ultron **self-aware of its tools**;
**add plugins** ("I dont see any plugins"); suggest more tools; and answer whether
a language rewrite pays.

**What "native" means now, as code.** `core/bridges.py` defines it: a `Bridge` has
a `probe()` returning `(ready, sentence)` and `run(op, **kwargs)` returning honest
text. Both helpers are bounded — `run_cli` uses a list of arguments with
`shell=False`, `stdin=DEVNULL`, no console window, a 25 s timeout and a
4,000-character cap; `http_json` is one request with a 4 s timeout and never
raises. Endpoints are **configuration** (`hindsight_url`, `voicestudio_url`,
default loopback), because an invented `/v1/recall` that returns 404 is worse than
being told to set a path.

**Self-awareness.** `core/tool_catalog.py` builds the list from the four places
tools come from — inline declarations in `main.py` (read with `ast`, never
imported), `actions/`, `plugins/`, and the bridges — so it cannot drift. The new
`tools_status` tool answers "what can you do?" from that list, and `core/prompt.txt`
now tells the model to call it rather than claim a capability it has not seen.

**The defect this build found.** The first smoke run raised
`TypeError: 'method' object is not iterable`. `ActionRegistry.failures` is a
method returning `{file: reason}`, not a list of objects; the catalog iterated it.
Fixed, and the failure is now *useful*: `browser_control` appears in the panel,
greyed, with the loader's sentence about playwright. A tool the model expects and
cannot call used to vanish.

**Plugins: 1 → 12.** Six local ones (`dev_json`, `dev_regex`, `dev_hash`,
`dev_cron`, `crypto_ident`, `net_check`) and five bridges (`rea_bridge`,
`hyperframes_bridge`, `hindsight_bridge`, `voicestudio_bridge`, `hypit_bridge`).
`net_check` is the dual-use one and is built accordingly: DNS and headers are
reads, a port check needs `allow_public` for a non-private host, and the risk
table guards it independently. `core/policy.py` gained per-action tiers for all
twelve, so a JSON format is ROUTINE and a video render is GUARDED — the owner's
standing objection to prompts for trivial actions, encoded.

**Dashboard.** `ToolsOverlay` in `ui.py`: nine tabs from `grouped()`, a live count,
a CLOSE button, the drawer button `🛠 TOOLS` and **Ctrl+T**. It reads the catalog
on open, never at import, so a slow plugin cannot delay the window.

**Two documents.** `docs/TOOL_SUGGESTIONS.md` — Tier A/B/C/D candidates with the
risk tier each needs, CyberChef as the highest-value single addition, and the list
a cool Ultron needs. `docs/LANGUAGE_DECISION.md` — keep Python; 197 files,
75,369 lines, 1,108 tests; a TOOLS panel costs 111 ms and a catalog build 25 ms;
rewrite **leaves** in Rust only if a hot path is ever measured.

Gate: 197 files · 1,108 tests (6 skipped) · 99 self-checks · `verify.py` exit 0 ·
proof gate **7 PROVEN / 12 PARTIAL / 0 FAILED / 0 NOT PRESENT** (exit 0).

**Still open, in order:** Windows CI (`windows-latest` running the three scripts)
would settle the twelve PARTIAL claims at once; `plugins/_whatsapp_core` is
referenced by two modules and does not exist; and the four "cool Ultron" projects
(offline mode, cost meter, memory timeline, plugin store) are weeks each.

## 6u. Four defects fixed, one of them mine (2026-11-06, build 1.2.13)

Every item was found by using or testing 1.2.12.

**1. `plugins/_whatsapp_core.py` did not exist.** Three docstrings described it —
`actions/send_message.py`, `core/appidentity.py` twice, `core/lazyimport.py` — and
the import in `send_message.py` is wrapped in `try/except`, so the absence was not
a crash: every WhatsApp send silently fell back to the blind keystroke path, which
presses Win, types the contact name and reports "typed, unverified". So on every
machine shipped so far, WhatsApp was the one platform the code claimed was
verified and the only platform that was not.

The module is written now, against the contract the docstrings implied:
`get() -> (transport | None, why)`, `transport.send_message_to(receiver, message)
-> (sent, failure)`, plus `fold()` and `name_in_phrase()` — the two string rules
`core/appidentity.py` says it borrowed from here. The send is tree-driven through
`core.ui_action.Session`: find the search box, open the conversation **that folds
to the named person**, refuse if two match or none does, type, press Send (or
Enter *only* into a box whose content was just verified), then read the box back
and refuse to say "sent" unless it emptied.

What is proven: the discipline, against a fake tree (`tests/test_whatsapp_core.py`,
12 tests) — stranger refused, ambiguity refused, disabled Send is a failure, a
driver crash becomes a sentence. What is **not** proven: a real WhatsApp window.
No Windows machine was available, so the last step of the new proof-gate claim is
a SKIP and the claim reads PARTIAL. It fails closed, which is the honest direction.

**2. A regex could freeze the window for ninety seconds.** `re` has no timeout.
`dev_regex` ran the match in-process, so `(a+)+$` against forty characters of "a"
blocked the turn — and the HUD thread with it. Measured: 90 s. Matching now runs
in a child process through a fixed script with JSON on stdin, under a two-second
deadline, and answers "that pattern took longer than 2 seconds. It is almost
certainly catastrophic backtracking — rewrite the nested quantifiers."
`RegexIsBounded` fails if the deadline is ever lost.

**3. A UUID was reported as "base64, 27 bytes".** True, and useless. A UUID is
valid base64, so the base64 branch caught it first. Recognised before base64 now,
and named as a UUID with its version.

**4. The project had no CI.** Thirteen proof-gate claims said PARTIAL or SKIP
because no Windows machine had ever run them. `.github/workflows/verify.yml` runs
`verify.py`, `proof_gate.py` and `verify_all.py` on `ubuntu-latest` **and**
`windows-latest`, uploads both report folders, and installs a deliberately lean
dependency set so a red build stays readable.

**A defect I introduced, caught by the project's own test.** While setting up the
repository I overwrote `.gitignore` with a new one. `tests/test_bootstrap.py:
GitignoreTests` went red in the same run — it asserts `log.txt` and
`verification-results.txt` stay visible, and `config/certs/` is ignored. The
overwritten file had all three wrong. Restored from the shipped archive and
appended with tool caches only. The test did its job; the lesson is that the
repository's rules live in the repository's tests, not in my head.

Gate: 200 files · 1,145 tests (6 skipped) · 99 self-checks · `verify.py` exit 0 ·
proof gate **7 PROVEN / 13 PARTIAL / 0 FAILED / 0 NOT PRESENT**.

**Publishing.** `PUBLISH.md` carries the two PowerShell commands. The GitHub
connection is not available in this session, so the push needs the owner's
credentials; the commit, the ignore rules and the CI job are ready. CC BY-NC 4.0
allows this publication with attribution and does not allow selling it.

## 6v. Keeping score on itself (2026-11-06, build 1.2.14)

You asked for a lot of skills, with meta-learning and meta-cognition named as the
priority. The temptation was to add a prompt that says "be honest about what you
don't know", which is free and does nothing. What was built instead is a record.

**`custom_jarvis/metacog.py`, one JSON file, no model, no network.** A claim is
stored with the confidence it was stated at, and later resolved `correct`,
`partly` or `wrong`. Three scores come out: accuracy, Brier, and a per-bucket
table. The single most important line in the file is that a perfect record is
**not** reported as reliable: the Wilson lower bound of 3 of 3 is **0.439**, and
the verdict is "not yet evidence — ask, or go and check". The same perfection,
forty times, earns **0.912**. That is the whole difference between a metric and
flattery, and it is the one property the proof gate now checks by name.

**Meta-learning has two stores.** Lessons are trigger + mistake + **rule**, and a
lesson whose rule is blank is refused — otherwise the store fills with diary
entries. `recall_lessons(task)` ranks rules against the task about to start by
token overlap and counts how often each rule is used, so rules that keep applying
rise. Strategies are per task type, and `choose_strategy` prefers an **untried**
option once before trusting the best record: a strategy that worked once is a
sample of one, and letting it become policy is how an assistant stops learning.

**Thirteen skills, 24 → 37.** Five meta (`meta_preflight`, `meta_confidence`,
`meta_debrief`, `meta_lessons_digest`, `meta_strategy_brief`) and eight inspection
skills that each replace a guess with a measurement (`code_size`,
`biggest_files`, `todo_scan`, `secret_scan`, `test_gap_scan`, `debug_context`,
`release_checklist`, `docs_freshness`). `docs/SKILLS.md` is the reasoning behind
the set: what a skill is allowed to be, the next eight meta skills and seven
domain skills in value order, and the four things that must never become a skill
(anything that generates and runs code, anything that changes its own
permissions, anything that records personal memory without approval, and any
"skill" that is a single tool call under another name).

**Three defects found while testing it, all fixed here.**

1. `secret_scan` **lost `regex=True`** when its pattern was repaired in the same
   session, so it searched for a literal backslash-`s` and found nothing. The
   tool was right; the skill was wrong. A test that only asserted "the skill
   runs" would have passed.
2. `search_text` and `measure_code` were **not in `addon_runtime.PATH_ARGUMENTS`**,
   so `prepare_args` never confined them and a path outside the workspace was
   accepted. The confinement test caught it. Both are now in that table and in
   the read-only `INSPECTION_TOOLS` set.
3. **My own test was wrong**: it asserted that every skill is applicable in a
   plain folder, when `debug_context` and `release_checklist` genuinely need
   `.git`. Replaced with two honest tests — the ones that need nothing are
   applicable, and the two that need `.git` say so in their reason.

Two hardcoded counts (`len(SKILLS) == 24`) were replaced earlier in the same
pass with structural assertions: unique ids, every `calls` entry resolving to a
live tool, the `meta_*` family present. A count says nothing about the set it
counts, and the next skill would have broken the test without saying anything
true.

Gate: 204 files · **1,195 tests** (6 skipped) · 99 self-checks · `verify.py`
exit 0 · proof gate **8 PROVEN / 13 PARTIAL / 0 FAILED** — the new claim is
`metacognition`, proven in eight steps. The thirteen PARTIAL claims are the same
ones as 1.2.13: each needs Windows, a microphone, a display or a live provider.

**Where the next gain is.** `post_mortem`: the planner already sees the failing
step of a plan, and today that knowledge dies with the turn. Recording it as a
draft lesson — with the owner's approval, since it writes — is the cheapest real
improvement in the meta-learning family, and it is one hook rather than a
subsystem.

## 6w. Four algorithms, and the one that was not built (2026-11-06, build 1.2.15)

You asked for the algorithms whose verdict was "yes". Four shipped, each wired to
a place where the program actually chooses. The fifth is deliberately absent, and
the reason is at the end.

**A decision system** — `custom_jarvis/decision.py` and the `decide` tool. A
candidate is scored `chance x value - cost - risk`. The chance comes from the
metacog calibration record, which is why that ledger was built first: the
decision layer needs an honest `p`, and a model's opinion of its own accuracy is
not one. The rule that earns the word "system" is the **refusal**: when every
option scores below zero, the answer is "do none of these". An assistant that
always has a recommendation is performing, not deciding. A `blocked` option never
wins on value alone, so a force-push at value 9 loses to a pull request at value
1. A chance of 1.7 raises rather than being clamped — a probability outside 0..1
is a caller bug, and hiding it would make the arithmetic a rumour.

**UCB1 for strategy choice** — `core/bandit.py` was written and tested in an
earlier phase and never wired. Now `choose_strategy` replays the aggregate
wins/tries into it as individual rewards, so a 1-of-1 option is explored once
instead of being trusted, and the reply says "chosen by UCB1, which pays a bonus
to the option tried least". One exploration policy in the project instead of
three.

**BM25 for lesson recall** — `custom_jarvis/shortlist.py`. Counting shared words
ranked "tests" (in every lesson) as highly as "cors" (in one). Inverted document
frequency and a length correction fix both, and a lesson with no matching word is
now left out instead of scored zero, which is what turns recall from noise into
advice.

**Pace telemetry** — `custom_jarvis/telemetry.py`, wired into `status()`. A fixed
threshold is wrong twice: it fires for ever on a slow machine and stays silent on
a fast one that just got slower. The governor keeps an exponentially weighted
mean and a spread, and reports the last turn as a z-score. The wording is capped
at "more than ten standard deviations" because a figure of 395 informs nobody.

**Two defects the tests caught, both mine.** The monitor first computed the
z-score *after* updating the mean and spread — so the outlier widened the spread
that judged it and a real slowdown hid itself. And a test asserted that 1-of-1
never beats 12-of-12; UCB1 disagrees on purpose. The test was rewritten to the
true property (explored once, then dropped after failures) rather than the code
being bent to the test.

**Not built: priority scheduling of reminders.** It needs a queue of pending
reminders to order, and no such queue exists yet. It arrives with the GitHub
trending-repository reminders. Shipping it now would be unused code that looks
like progress.

Gate: 208 files · **1,219 tests** (6 skipped) · 99 self-checks · `verify.py` exit
0 · proof gate **9 PROVEN / 13 PARTIAL / 0 FAILED** (new claim: `decisions`).

**Order agreed with the owner:** these algorithms, then the deep scan, then
native GitHub (with the trending-repository reminders), then the push — the push
last of all, and with the owner's own credentials.

## 6x. Native GitHub, self-extension, and a project that can be read (2026-11-06, build 1.2.16)

Four asks in one build. In order of how much they change the product.

**GitHub is native.** `core/webapi.py` is one bounded JSON reader — deadline,
ETag cache, 2 MB cap, gzip, and a failure phrased as a sentence. `core/github.py`
adds the token and the endpoints; `plugins/github_tool.py` turns them into the
tool the model calls. The token is `github_token` in `config/api_keys.json`, it
travels in exactly one header, and the gate asserts it is **not** in the cache
file. ETag caching is not tidiness: a `304` does not count against the hourly
quota, so a watch list of twenty repositories fits inside one quota instead of
blowing it six times over. "Trending" is a search for recently created
repositories sorted by stars, and the answer says so, because GitHub publishes no
trending API and an approximation labelled as official is the exact defect this
project keeps removing.

**Four more platforms, one pattern.** `core/platforms.py` and
`plugins/tech_platforms.py` add Hacker News, Stack Overflow, PyPI and npm. All
public, all keyless, all cached. An unreachable platform says so; it does not
return an empty list that reads like "nothing is happening".

**Ultron adds features to itself.** `custom_jarvis/skillpacks.py` lets it write a
**skill pack**: JSON naming read-only tools and their arguments. It validates
every step against the live registry, saves atomically with a `.bak`, and the
skill is available at once and again after a restart. The limits are the safety
story, and they are short enough to remember: **no writing tool, no built-in id,
no path outside the workspace, at most eight steps.** A bad pack is a bad recipe,
not a breach. `add_skill` asks for approval because a skill runs later, when
nobody is watching. This is the answer to "I want it to add features itself"
that does not also hand it the ability to rewrite its own safety.

**Interruption is earned.** `custom_jarvis/schedule.py` is the queue behind the
reminders. A card is scored by **the same expected-value arithmetic** that chooses
an action — that is why the decision layer came first — and then four rules
apply: quiet hours hold everything except an emergency, a per-card cooldown stops
repetition, a card worth less than the interruption is dropped, and state is one
small JSON file so a reminder shown at 09:00 is remembered after a restart.

**The two algorithms from last build got smarter.** Strategy choice replays the
last twenty attempts with a **30-day half-life**, so a method that worked in
March loses to one that works now. Lesson recall weights a lesson's **trigger**
above its prose (2.0 / 1.0 / 0.5). `decision.from_record()` turns wins/tries into
a **Wilson lower bound**, so a decision can be built on a record instead of a
ratio — the metacog ledger and the decision layer now share one honest number.

**And it is readable.** `ARCHITECTURE.md` gives the six layers, one turn end to
end, where each kind of change belongs, and every invariant with the test that
enforces it. `docs/INDEX.md` lists every document. `docs/MAP.md` is **generated**
by `scripts/map.py`, which now runs inside `verify.py`: a new module with no
docstring or no test fails the build. The map separates the folders this project
owns from the inherited upstream ones — eleven upstream `core/` modules with no
test are listed, not hidden, and do not fail the build.

**Two defects, both mine, both caught by a test.** `github_tool` was
"unclassified" in the policy table, which means every call would have asked
permission for ever — caught by `tests/test_policy_new_tools.py`. And the
reminder tests failed at 01:00 local time because quiet hours were doing their
job; the code was right and the test was wrong, which is worth saying plainly
because it is the second time this week. The two bugs from 1.2.15 are covered by
`tests/test_decision_layers.py` and pass.

Gate: 220 files · **1,267 tests** (6 skipped) · 99 self-checks · `verify.py` exit
0 · proof gate **12 PROVEN / 13 PARTIAL / 0 FAILED** (new: `github`,
`self_extension`, `reminders`).

**What is deliberately still absent.** GitHub *writes* (comment, pull request,
merge): those change an account other people can see, so they arrive with an
approval that names the exact action. Packs that call writing tools: the same
reason. Repositories bought in from a trending list as new tools: that is
`docs/SKILLS.md` Level 2, generated code, and it needs the repair pipeline with
two confirmations. The order agreed with the owner is unchanged: this, then the
deep scan, then GitHub writes, then the push.

## 6y. Shipping itself, and updating from GitHub (2026-11-06, build 1.2.17)

**What exists now.** Three modules and four tools. `custom_jarvis/ship.py` (`Shipper`): `scan()` for assignment-shaped secrets and token shapes, `guards()` asserting the config and memory files are still ignored AND untracked, `check_syntax()` on the changed files, `commit()` with `Why:` / `Evidence:` / files in the message, `push()` fast-forward only, and a `ship_log.json` of the last 100 attempts. `custom_jarvis/selfupdate.py` (`Updater`): `check()`, `apply()` (dirty refuse → fetch → `pull --ff-only` → optional verify → `reset --hard` back on failure → reload hooks), and `restart_marker()`. `custom_jarvis/ship_tools.py`: `ship_status`, `ship_now`, `check_update`, `apply_update` — the two readers are in `AddonRegistry.READ_ONLY`, the two actors are not, so publishing and pulling ask.

**The order is the safety story.** scan → guard → syntax → optional gate → commit → push. Every stage returns `{ok, stage, note, files}`; the first refusal names itself, so "it did not ship" is never a mystery. The gate claim `shipping` proves all seven steps against a real bare remote in a temp folder, and `self_update` proves the revert.

**Two defects this build found in itself, both worth remembering.**
1. `changed()` sliced `git status --porcelain` at a fixed offset. `git()` returns stripped output, so the first line lost its leading space and `app.py` became `pp.py`: the syntax check guarded a file that does not exist, and a broken module shipped. It is parsed by a pattern that accepts either shape now.
2. The restart marker was written into the repository. Untracked file → dirty tree → the NEXT update refuses. It lives in the state folder now, and `.gitignore` names it.

**Solved, and the rule that solved it (2026-11-06).** The push is live: `main` at the repository below carries
the full history, seven commits. Three tokens were tried; the third worked:

- a fine-grained token with `Contents: Read` — `GET` fine, `PUT contents` **403 "Resource not accessible by personal access token"**;
- a fine-grained token with `Contents: Read and write` — writes fine, `git push` **refused: workflow
  `.github/workflows/verify.yml` … without `workflow` scope**;
- a **classic token with `repo` + `workflow`** — accepted.

**The rule to remember:** GitHub checks the whole push for workflow files, so one `.github/workflows/*.yml`
anywhere in the history makes the **Workflows** permission mandatory for every push. A fine-grained token needs
`Contents` **and** `Workflows`, both Read and write; a classic token needs `repo` and `workflow`. A refusal names the
file but not the permission, which is why this cost three attempts.

Two probe commits were created on the remote by the write test (`4274c94`, `d7c02ac`) and removed by a
`--force-with-lease` push pinned to the exact probe sha. No work of anyone else was touched, and the lease means the
refusal would have been automatic if the remote had moved. `origin` is set **without** a token in the URL; the token
comes from `GITHUB_TOKEN` or `config/api_keys.json: github_token`.

**What the next person should not do.** Do not make the push automatic by default. Do not add a force path "just for recovery". Do not call a reload an update — imported modules keep their old code, so the honest contract is: files updated, data reloaded, restart asked for only when `.py` changed.

**The token fix, exactly.** Two settings decide a fine-grained token: *Repository access* (Only select repositories → this repository) and *Permissions → Repository permissions → Contents* (Read and write). A token made as *Public repositories (read-only)* reads every public repository and writes none, which is the symptom seen twice on 2026-11-06.
