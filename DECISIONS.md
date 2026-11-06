# Decisions — Ultron and the Agentic OS

Everything below is a decision **you** made, in your words where I have them, with what it
means in the code. It exists because a decision that lives only in a chat log gets quietly
undone by the next change — and two of the defects fixed on 2026-11-06 were exactly that: a
requirement ("the interface must be adjustable", "first run must accept several providers")
that had been agreed and then not implemented.

Read this before changing anything. If a change contradicts an entry here, the entry wins
unless you say otherwise — and then this file gets edited on the same day.

Last updated: **2026-11-06**.

---

## 1. Identity

| Decision | Where it lives |
|---|---|
| The product is named **Ultron** and must recognise its own name. | `core/identity.py` (`NAME`), window title, greeting, `_assistant_name()` in `main.py` |
| The persona is a **robotic assistant in the manner of J.A.R.V.I.S.** — dry, precise, present. | Voice/tone in `core/identity.py`, `providers/`, the log's voice |
| The **original MARK look is kept**: the HUD, the head, the layout. Not a redesign. | `ui.py` (`HudWidget`, palettes) |
| The avatar should be **richer**, and expressions **subtle**; it must **never smile through a failure**. | `HudWidget` expression states; `_apply_state` |

Not negotiable in passing edits: renaming the assistant, changing the window chrome, or a
new visual language need to be asked for, not assumed.

## 2. Models and providers

- **No named-model policy, and no provider or model names hardcoded.** Choices come from
  configuration and from each provider module's own `CATALOG`.
- **Any provider API, or several at once.** A Gemini Live key *or* any number of
  OpenAI-compatible services; **switchable by voice**.
- **No key rotation to evade rate limits.** Ever. An exhausted key is reported, not dodged.
- **Local models only after informed consent**, quantized, **1.5–3B**, vision opt-in.
  **Cloud-first for heavy reasoning.**
- First run must offer the **multiple-provider setup** — agreed, and shipped in 1.2.3.

## 3. Safety, consent, and the limits on autonomy

- **Only remember what you approve.** Nothing inferred is persisted silently.
- **Camera and screen capture need consent**, an on-screen indicator, and a stop that works.
- **Risk-based sensor consent**: the more invasive the sensor, the more explicit the gate.
- **Background work must not disturb the screen**: no pointer movement, no focus theft.
  Ref-based actions are headless by default.
- **Accessibility tree before vision.** Vision is the fallback, and only when configured and
  consented. Implemented in `core/ui_ladder.py`.
- **No self-rewriting code.** `core/selfimprove.py` measures and reports; it does not edit
  source. It does not retune its own weights.
- **Two human confirmations for any change to code.** A calibrated predictor that clears 70%
  may auto-apply *reversible, non-protected* actions only — never code.
- **Never weaken a test assertion** to make a build pass, and **never bypass**
  `ControlledRegistry` or `EvidenceEngine` path confinement.
- **Evolution is high importance, with no fixed resource budget** — but that is permission to
  spend effort, not permission to change behaviour without agreement.

## 4. Working style

- **Be honest about what does not exist.** Unrun code is called unrun. A pass is not a proof.
- **Rigorous testing; "zero performance issues"** as the aim, with no impossible guarantees
  claimed.
- **Keep the workspace clean**: `log.txt` (the engineering log), `readme.md` (the guide),
  `HANDOFF.md` (state and takeover). One of each.
- **No stray launchers.** You work from PowerShell; **do not add launcher files.**
  `run.bat` and `run.ps1` are the launchers and they stay as they are.
- **Don't ask about trivia.** A confirmation prompt for something reversible and obvious is
  friction, and it teaches you to click through the ones that matter.
- **Keep Windows and Ultron intact.** Nothing in either project may require giving them up.
- **RAM warnings are disabled in Ultron.** A background assistant that nags about memory is
  worse than one that does not. (The *OS* is the opposite case, below.)

## 5. The interface (decided and corrected 2026-11-06)

- **The interface scale must be adjustable inside the app**, not by editing
  `config/api_keys.json`. Implemented: ⚙ → Customise → `− 145% +`, presets, `AUTO`,
  `Ctrl+=` / `Ctrl+-` / `Ctrl+0`, and `⟲ RESTART TO APPLY` / `Ctrl+Shift+R`.
- It **had to be bigger by default**: the automatic scale is `screen_height / 760`, so 1.40 at
  1080p (it was 1.20).
- **First startup must offer several providers**, not just a Gemini key.
- **Feature freeze.** Nothing new is added to Ultron; the exception is a feature that does not
  work — then it gets fixed properly.

## 6. The Agentic OS

- **Debian-based distribution**, not a from-scratch kernel, not a Windows shell, not
  "agent-first".
- **Dual-boot beside Windows**, keeping Windows and Ultron intact. ~10–12 GB.
- **Lowest idle RAM, measured** (target ≤350 MB), fast boot (4–6 s).
- **Import all data from Windows**, fast in extraction and transfer: in-kernel `ntfs3`,
  **not FUSE**.
- **Setup must be easy.**
- **Interconnection with Ultron = a shared memory format plus an export bundle**
  (`agentic-os/osbridge/`), *not* a live LAN bridge. A bridge is a possible later project.
- Agentic capabilities to match Ultron's preferences: accessibility tree before vision,
  headless ref actions, consent gates, approval-only memory, no self-rewriting, **voice-first**.
- Milestone 1 (the memory contract) is complete; **nothing else exists yet**, including a
  bootable image.

---

## Where a decision is enforced in code

| Decision | Enforced by |
|---|---|
| Approve-before-remember | `memory/memory_manager.py`: memory is written only by an explicit `remember`/`forget` tool call or a session summary the user ended — nothing infers and persists on its own. **There is no separate approve-the-write dialog**; if you want one, it is a new gate, not an existing one. |
| Tree before vision | `core/ui_ladder.py`, `actions/ui_control.py` |
| No self-rewriting | `core/selfimprove.py` returns `needs_human` for protected artefacts |
| Path confinement | `ControlledRegistry` in `custom_jarvis/runtime.py` and `EvidenceEngine` in `custom_jarvis/addon_runtime.py` — that is where the policy runs, and neither may be bypassed. |
| **Credential stores are never read, written, moved or listed** — `~/.ssh`, `~/.aws`, `~/.gnupg`, browser profiles, `.env`, key material by extension, and this program's own `config/api_keys.json`. Refusal names the reason instead of saying "Access denied". | `actions/file_controller.py` (`_SENSITIVE_DIR_PARTS`, `_SENSITIVE_FILE_NAMES`, `_SENSITIVE_SUFFIXES`, `_denial_message`), asserted by `tests/test_file_safety.py` |
| **A capability that does not load is said out loud**, once, in the activity log — never left as a silent absence the user reads as a refusal. | `core/action_loader.ActionRegistry.failures()`, `main.py` at discovery time |
| **A turn always ends.** A tool call with no result (consent refused, tool raised, interrupted) is recorded as unanswered after 1.5 s and the model carries on. | `providers/engine_pipeline.py` `_PARTIAL_TOOL_GRACE`, `_release_partial`; `tests/test_live_config.py` |
| **A tool never crashes on a badly-typed argument.** Explicit nulls are dropped and values are coerced to the type the declaration names, at the dispatcher. | `core/action_loader._clean_parameters`, `_coerce_parameters`; `main.py` for the inline tools; `tests/test_edge_cases.py` |
| **A remembered fact is never lost to a concurrent write, and one bad update cannot delete a category.** | `memory/memory_manager.py` `_write_lock`, category guard |
| **A setting that cannot be saved says so and does not crash.** | `memory/config_manager.ensure_config_dir`/`_write_config` return False; the scale panel verifies its save |
| **"Could not ask" is never recorded as "cannot".** An unreachable model server leaves the stored vision decision alone. | `providers/llm_openai.can_see` (tri-state), `_refused_the_image` |
| **Nothing is claimed to work on Windows until it has run on Windows.** | this file, `HANDOFF.md` §6m, `release.txt` |
| Any provider | `providers/registry.py`, `providers/llm_openai.CATALOG` |
| Adjustable scale | `ui.py` `CustomizeOverlay`, `memory/config_manager.save_ui_scale` |
| Multi-provider first run | `ui.SetupOverlay`, `config_manager.apply_first_run` |
| No hardcoded model names | `providers/*` declarations and `_gemini` model lists |

## Open questions (deliberately unanswered)

| **Capabilities are proven by instruments that ship with the app**, not by the suite | A green suite says the logic is right; it cannot say the machine has a microphone. `scripts/verify_all.py` plus five verifiers ask the hardware directly, and their output is the evidence. | `scripts/verify_*.py`, `tests/test_verifiers.py` |
| **SKIP is not FAIL** | The Windows checks run on Linux as SKIP with a reason. Treating that as a failure would make the instrument useless on every machine that is not the target one; treating it as a pass is how "it works" becomes a lie. Both are refused. | `scripts/verify_all.py:verdict_for`, asserted in `tests/test_verifiers.py` |
| **A verifier reports the cause, not the symptom** | "Browser has been closed" says nothing. The browser check reads the binary's own error and `ldd`, and names missing libraries. Same for audio (PortAudio) and capture (no display). | `scripts/verify_browser.py:_binary_problem` |
| **Backend prose is never an application** | `xdg-mime` prints "No default applications for …" and exits 0. Any line that is a sentence is rejected, everywhere a handler is read, so "open the browser" fails honestly instead of reporting a false success. | `core/app_resolver.py:_handler_from` |

| **A capability may not report itself ready and then throw** | `available()` returned usable for pywinauto, which has no driver in this codebase, so the accessibility tree was offered, chosen over vision, and failed on first use. Availability now means a driver exists *and* its package is installed. | `core/ui_windows.py:available`, `tests/test_ui_bridge.py` |
| **An instrument must ask the product's question** | `verify_windows.py` hand-imported `uiautomation`, so it could report SKIP while the app believed the tree worked. It calls `core.ui_windows.available()` now. | `scripts/verify_windows.py:accessibility_tree` |

| **A claim is proven as a chain, never as a component** | "The microphone records" and "I was heard and answered" are different questions. `scripts/proof_gate.py` runs the chain and prints every step, so a break at step three says so. | `scripts/proof_gate.py`, `tests/test_proof_gate.py` |
| **`NOT PRESENT` is a verdict, not an omission** | A claim with no code behind it must read as missing, not as untested or broken. Rounding it up is exactly how "works" becomes a lie. | `scripts/proof_gate.py:Claim.verdict` |
| **Licence terms on distribution do not gate private use** | CC BY-NC 4.0 constrains redistribution and sale; a private Ultron on the user's own machine is neither. Removed from the gatekeeper register at the user's direction. | `GATEKEEPERS.md` |

| **Memory writes are approval-gated at the call site, with no intent heuristic** | `policy` said GUARDED all along; `main.py` wrote without asking. Now `core/memory_consent.request_write` parks the write behind the HUD confirmation. No "the user already said remember" shortcut: guessing intent wrong writes something permanent silently. | `core/memory_consent.py`, `main.py` save_memory branch, `tests/test_memory_consent.py` |
| **One pending decision at a time, and it says so** | The confirm gate holds a single banner; a second memory write would have replaced the first and lost the fact with no error. It refuses aloud instead. | `core/memory_consent.py`, `OneBannerAtATimeTests` |
| **A claim that belongs to another project is removed, not faked** | The daily digest is an Agentic OS milestone property with no Ultron requirement. It was dropped from the Ultron proof gate rather than built into a frozen app. | `scripts/proof_gate.py` |

| **The digest activates nothing, by construction** | Its module reads files and returns words; the only write is one date. News checks and reminders stay in their own modules, so an inert report cannot quietly become an acting one. | `core/digest.py`, `tests/test_digest.py:InertTests` |
| **The digest does not create folders or import side effects** | `actions/reminder.py` creates its folder on import, so the digest builds that path itself. A test asserts a missing folder stays missing. | `core/digest.py:reminder_dir` |
| **A machine that cannot answer is a SKIP, never a FAILED** | "No display" is not "screen capture is broken". The gate asks `_has_display()` before judging, and keeps FAILED for a machine that has a screen and returns no frame. | `scripts/proof_gate.py:_has_display` |
| **The digest is delivered, not announced** | A tool for when the user asks, and a log line once a day at the configured hour. It never speaks over the user. | `main.py:_digest_loop`, `config_manager.get_digest_hour` |

| **"Native" has a definition, and absence is part of it** | A tool is native when Ultron knows it, exposes it as a tool and a tab, **probes** it, states what is missing, and is tested with the dependency gone. A vendored README is not an integration. | `core/bridges.py`, `tests/test_bridges.py` |
| **A service endpoint is configuration, never a guess** | The five tools are other people's software with other people's routes. Ultron performs the request; the path comes from the user or from `hindsight_url` / `voicestudio_url`. Inventing `/v1/recall` produces a 404 dressed up as an integration. | `core/bridges.py:_hindsight_request`, `_voicestudio_request` |
| **A tool that cannot load is shown, not hidden** | A capability that silently vanishes is the defect this panel exists to stop. The catalog reads the loader's own `{file: reason}` map and displays the sentence. | `core/tool_catalog.py:_action_entries` |
| **Self-knowledge comes from the sources, not from prose** | The catalog is built from `TOOL_DECLARATIONS` (parsed with `ast`, never imported), `actions/`, `plugins/` and the bridges, so it cannot drift from reality. `tools_status` answers from it. | `core/tool_catalog.py`, `main.py:tools_status` |
| **A trivial local transform does not ask permission** | `dev_json`, `dev_regex`, `dev_hash`, `dev_cron`, `crypto_ident` are ROUTINE: they read a string and return a string. `net_check` port and every bridge `command`/`request` are GUARDED. A tool with no action is guarded, not trusted. | `core/policy.py`, `tests/test_policy_new_tools.py` |
| **A dual-use tool is limited in code and in the risk table** | `net_check` refuses a public host unless the caller passes `allow_public`, and the policy tier guards the same action independently. Two locks, because one of them is a paragraph of text a model can be talked past. | `plugins/net_check.py`, `core/policy.py:_ACTION_TIERS` |
| **The tool panel reads the catalog on open, never at import** | A slow plugin must not delay the window. Same rule as the plugin manager and the provider picker. | `ui.py:ToolsOverlay.reload` |
| **No language rewrite; rewrite a measured leaf instead** | 197 files, 75,369 lines, 1,108 tests; a turn waits on a model, not on Python. A TOOLS panel costs 111 ms. If a hot path ever exceeds 500 ms of Python, that function goes to Rust via PyO3 — not the application. | `docs/LANGUAGE_DECISION.md` |
| **CyberChef before any other security tool** | A static page on loopback replaces a hundred hand-written decoders and cannot reach the network. Highest value, lowest risk. | `docs/TOOL_SUGGESTIONS.md` |
| **Attack tooling that cannot verify its target is refused** | Metasploit, sqlmap, Hydra and mass scanners are out. A voice assistant cannot confirm authorisation, and one wrong target is a criminal act. | `docs/TOOL_SUGGESTIONS.md` |

| **A promise in a docstring is a defect until the file exists** | Three docstrings described `plugins/_whatsapp_core.py`; the file was absent, so `send_message` fell back to blind keystrokes on every send. The driver is written now, and it fails closed: no conversation, no send; no read-back, no "sent". | `plugins/_whatsapp_core.py`, `tests/test_whatsapp_core.py` |
| **A user-supplied pattern runs where it can be killed** | `re` has no timeout and `(a+)+$` froze a turn for ninety seconds. Matching runs in a child process with a two-second deadline; the child executes a fixed script and takes JSON on stdin, so no pattern is ever built into a command line. | `plugins/dev_regex.py`, `tests/test_plugins_bundle.py:RegexIsBounded` |
| **The build record is tracked; the keys are not** | `log.txt` and `verification-results.txt` stay visible in the repository — `tests/test_bootstrap.py` has asserted that since they were named. `config/api_keys.json`, `config/certs/` and `memory/long_term.json` never are. | `.gitignore`, `tests/test_publishing.py` |
| **CI is the cheapest way to close a PARTIAL** | Thirteen claims said "needs your machine". `.github/workflows/verify.yml` runs the three gates on ubuntu-latest and windows-latest on every push. A red first run is information, not embarrassment. | `.github/workflows/verify.yml` |
| **Publishing is allowed, selling is not** | Ultron is a derivative of FatihMakes/Mark-LVI under CC BY-NC 4.0. A public repository is fine with attribution; `LICENSE` and the attribution paragraph stay. | `PUBLISH.md`, `LICENSE`, `tests/test_publishing.py:Licence` |

1. Which provider you actually use day to day — the runtime works with any, and the honest
   default is "whichever key you paste".
2. Whether the Agentic OS gets a live bridge to Ultron later. Bundle first was the decision;
   the bridge was not rejected, only deferred.
3. Which of `docs/CAPABILITIES.md` gets built next. That page is a menu, not a plan.
