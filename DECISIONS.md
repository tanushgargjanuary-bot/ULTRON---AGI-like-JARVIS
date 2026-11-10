# Decisions — Ultron and the Agentic OS

Everything below is a decision **you** made, in your words where I have them, with what it
means in the code. It exists because a decision that lives only in a chat log gets quietly
undone by the next change — and two of the defects fixed on 2026-11-06 were exactly that: a
requirement ("the interface must be adjustable", "first run must accept several providers")
that had been agreed and then not implemented.

Read this before changing anything. If a change contradicts an entry here, the entry wins
unless you say otherwise — and then this file gets edited on the same day.

Last updated: **2026-11-10** (repository consolidation, proportional branch policy, and automatic test gates).

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

| **An outside project is native, an adaptor, or a name — never a bundle** | Two hundred projects were offered on 7 Nov 2026. Most are servers, not libraries, and every vendored dependency costs startup time, licence work, an update watch and a new way to crash. The rule: native only when Ultron cannot do the job without it and it must work offline; an adaptor when it is already a program on the machine; knowledge otherwise. One protocol beats a hundred integrations — an MCP client is worth more than any single entry on that list. Security and OSINT scanners are catalogue-only, because they act on systems nobody here owns. A second rule was added the same day, after a longer list: a weakness counts only when a file and a line can be shown, and a framework never replaces a layer that already exists. | `docs/ECOSYSTEM.md`, `core/tool_catalog.py`, `custom_jarvis/mcp_client.py` |
| **`main` is the only permanent integration branch.** Main-only is the default for small, low-risk, non-parallel work when the owner authorizes it. Use a short-lived branch only when parallel work, isolation, or rollback risk gives a clear benefit. Keep branches narrow, target `main`, and delete them after successful integration. Never keep permanent branches per agent or model. | `AGENTS.md`, `docs/AGENT_PLAYBOOK.md`, `docs/TEST_AUTOMATION.md` |
| **Every branch push gets a fast offline test gate; full Linux/Windows verification runs on pull requests to `main` and pushes to `main`.** A fast pass gives rapid feedback but does not replace the full suite or hardware proof. | `.github/workflows/fast-checks.yml`, `.github/workflows/verify.yml`, `docs/TEST_AUTOMATION.md` |

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
| **There is no repository size budget** | Withdrawn by the owner on 2026-11-07: the repository is on GitHub, and a 100 MB / 5,000-file ceiling was blocking work it never protected. The script, its test and its step in `scripts/verify.py` were deleted in the same change, so nothing claims a number that nothing enforces. | `scripts/verify.py` (no budget step), `docs/SPACE.md` |

## 7. Repository continuity and agent maintenance

- **`main` is the sole permanent branch after consolidation.** Use short-lived `feature/<topic>` and `fix/<topic>` branches for active work. Do not keep permanent branches per agent or model.
- **Historical branch tips remain protected recovery tags.** The ten 2026-11-10 archive tags are protected by Active ruleset `26923169`; do not move or delete them during routine cleanup.
- **A chat is not a project record.** `OwnerFiles/ULTIMATE_Context.md` is the canonical current handoff. A new agent starts there and checks live Git/PR/CI state before relying on dated facts.
- **Medium and large work must update the durable record.** Agents classify task size, review the documentation impact map, update the affected guides and canonical handoff, review repository hygiene, and record evidence. `docs/AGENT_MAINTENANCE.md` is mandatory and is referenced from `AGENTS.md`, the agent playbook, and the pull-request template.
- **Repository cleanup must be evidence-led.** Do not delete a file because it is large or looks old. Check imports, dynamic discovery, tests, workflows, packaging, docs, and user commands. Preserve logs, backups, history, and owner data.
- **No workspace size or file-count ceiling is active.** The owner withdrew the 100 MB / 5,000-file budget on 2026-11-07. Keep build output, caches, and machine state out of Git without restoring an arbitrary limit.

Enforced/documented by: `AGENTS.md`, `docs/AGENT_MAINTENANCE.md`, `docs/AGENT_PLAYBOOK.md`, `OwnerFiles/ULTIMATE_Context.md`, and `.github/PULL_REQUEST_TEMPLATE.md`.

## 8. Upstream MARK/JARVIS resource intake

- **Use FatihMakes MARK/JARVIS work as a source, not as an automatic merge base.** Review the exact repository, commit SHA, issue/PR status, file contents, and licence before adopting it.
- **ULTRON's current safety and evidence architecture remains authoritative.** Do not replace `core/policy.py`, path confinement, evidence, confirmations, proof gates, or ULTRON's tests with an older upstream implementation.
- **Port the smallest useful change.** Prefer one tested improvement to a wholesale branch merge or a parallel subsystem.
- **Preserve licence and attribution.** The checked-in MARK-LVI licence specifies CC BY-NC 4.0. Commercial use is not permitted without separate written permission. Check older repositories and third-party models/assets separately.
- **No blind community-fork imports.** A fork or PR is a candidate, not a trusted release. Check code, author, licence, tests, secrets, model provenance, and security boundaries.
- **Record the decision.** Mark every reviewed proposal as adopted, already present, reimplemented, deferred, or rejected in `docs/UPSTREAM_RESEARCH.md`.

Enforced by: `docs/AGENT_MAINTENANCE.md`, `docs/UPSTREAM_RESEARCH.md`, and the source-level rules in `AGENTS.md`.

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
| **CI is the cheapest way to close a PARTIAL** | CI runs a fast offline gate on every branch push. The full regression and proof gates run on pull requests to `main` and pushes to `main`, on Ubuntu and Windows. A fast pass is not a full pass; hosted PARTIAL/SKIP results remain visible. | `.github/workflows/fast-checks.yml`, `.github/workflows/verify.yml`, `docs/TEST_AUTOMATION.md` |
| **Publishing is allowed, selling is not** | Ultron is a derivative of FatihMakes/Mark-LVI under CC BY-NC 4.0. A public repository is fine with attribution; `LICENSE` and the attribution paragraph stay. | `PUBLISH.md`, `LICENSE`, `tests/test_publishing.py:Licence` |

| **Confidence is a lower bound, not a ratio** | Three successes in three attempts is not 100%. It is a Wilson lower bound of 0.439 and the verdict "not yet evidence — ask, or go and check". Forty of forty earns 0.912. A metric that flatters the machine is worse than no metric. | `custom_jarvis/metacog.py:calibration`, `tests/test_metacog.py` |
| **A lesson without a rule is refused** | "The tests failed" teaches nothing. A lesson is trigger + mistake + **rule**, and `record_lesson` raises if the rule is blank. The rule is what changes the next attempt. | `custom_jarvis/metacog.py:record_lesson` |
| **An untried strategy goes first, once** | A strategy that worked once would otherwise become policy on a sample of one. `choose_strategy` prefers an option with no record before the best-scoring one, which is the exploration that keeps a lucky guess from hardening into a habit. | `custom_jarvis/metacog.py:choose_strategy` |
| **Meta-cognition is arithmetic on a record, never a mood in a prompt** | There is no "be humble" instruction anywhere in the build. There is a ledger: claim, confidence stated, outcome later, three scores. If it is not measured it is not claimed. | `custom_jarvis/metacog.py`, `custom_jarvis/metacog_tools.py` |
| **The ledger records the assistant, not the owner** | Predictions, lessons and strategy attempts are the machine's own reliability, kept in one JSON file beside the state. Personal memory stays behind the approval rule; the two stores are deliberately separate files for that reason. | `custom_jarvis/service.py`, `metacog.json` |
| **A skill that needs `.git` says so instead of failing mid-run** | `debug_context` and `release_checklist` declare `.git` as a required marker, so `list_skills` reports them as not applicable in a plain folder with the reason attached. The alternative — failing at step two of five — teaches the user nothing. | `custom_jarvis/skills.py`, `tests/test_metacog_service.py` |

| **A decision is arithmetic, and it can refuse** | Score = chance x value - cost - risk. When every option is below zero the answer is "do none of these"; an assistant that always has a recommendation is performing, not deciding. A `blocked` option never wins on value alone. | `custom_jarvis/decision.py`, `tests/test_decision_layers.py` |
| **The least-tried option gets one fair trial** | UCB1 over the attempt record, not a raw ratio: 1 of 1 is explored once and then loses to 12 of 12. This is the same rule the provider bandit uses, so the project has one exploration policy rather than three. | `custom_jarvis/metacog.py:choose_strategy`, `core/bandit.py` |
| **Relevance is BM25, not shared words** | A word in every lesson ("tests") ranks nothing; a rare word that appears three times ranks more; a long lesson does not win by being long. An unrelated question returns no advice instead of noise. | `custom_jarvis/shortlist.py`, `metacog.lessons_for` |
| **Normal is measured, not declared** | A fixed "6 s is slow" alarm is wrong on both kinds of machine. The governor keeps an exponentially weighted mean and flags a turn by z-score, so a slow PC is not nagged and a sudden fivefold slowdown is caught. | `custom_jarvis/telemetry.py`, `AutonomyGovernor.status` |
| **No algorithm ships before the feature that needs it** | Priority scheduling of reminders is specified and not built, because no queue of reminders exists yet. Unused code is a liability that looks like progress. | this build, `docs/SKILLS.md` |

| **GitHub reads are routine; GitHub writes will ask** | "What is trending" behind a confirmation banner is the excessive prompting you rejected. Reading a public API changes nothing, so it does not ask. Any writing action added later goes in the action table at guarded, and a name missing from that table stays guarded — forgetting an entry fails safe. | `core/policy.py`, `tests/test_policy_new_tools.py` |
| **The token lives in config and nowhere else** | `github_token` in `config/api_keys.json`, sent as one bearer header. Never a log line, never a prompt, never the cache file — and the gate asserts the cache file does not contain it. A leaked token has to be revoked, so the design is that it cannot leak. | `core/github.py`, gate claim `github` |
| **A trending list must say it is an approximation** | GitHub publishes no trending API. Ultron searches recently created repositories sorted by stars and states that in the answer, because an approximation presented as an official list is exactly the kind of unearned claim this project keeps removing. | `core/github.py:trending` |
| **Ultron may add skills to itself, and only as data** | A skill pack is JSON naming read-only tools. It cannot add a tool, run code, reach the network or leave the workspace, and it cannot take a built-in id. Adding one asks for approval, because a skill runs later when nobody is watching. Anything that needs new code goes through repair with two confirmations, not through a pack. | `custom_jarvis/skillpacks.py`, gate claim `self_extension` |
| **Silence is a decision, including for reminders** | A card is shown only if its expected value beats the cost of interrupting you, and not twice inside its cooldown. Quiet hours hold everything except an emergency. An assistant that always has something to say is not attentive. | `custom_jarvis/schedule.py`, gate claim `reminders` |
| **Startup morning brief is opt-in** | A fresh install or a config with no saved choice must not speak an automatic briefing. Only an explicit saved boolean enables it; the owner can change it with the HUD toggle. A malformed value fails closed to off. | `memory/config_manager.py:get_brief_enabled`, `main.py`, `ui.py`, `tests/test_suite_assistant.py:BriefingOptInTests` |
| **An old success must be allowed to expire** | Strategy attempts carry timestamps and are replayed with a 30-day half-life, so a method that worked in March does not outrank one that works now. | `custom_jarvis/metacog.py:choose_strategy` |
| **The map is generated, not remembered** | `scripts/map.py` reads the docstrings and the tests and writes `docs/MAP.md`; `verify.py` runs it and fails on a new module with no docstring or no test. Upstream modules with no test are listed rather than hidden. | `scripts/map.py`, `docs/MAP.md` |

| **A tool schema is a contract with a provider, not a suggestion** | A declaration may only mark a parameter `required` if it declares it under `properties`. Google refuses the **whole tool list** for one such field and closes the session with `1007`; retrying cannot help, because the same list is re-sent. Five plugins did this and the owner spent an evening re-entering a key that was already right. | `core/action_loader.py:sanitize_declarations`, `tests/test_provider_schema.py`, gate claim `plugins` |
| **A close code is not a diagnosis** | `1007` means "I closed this session" and covers a bad key, a bad model name and a bad schema alike. The reconnect loop tested `"1007" in err_str` and asked for a key every time. The message decides now; the number only breaks a tie. | `core/close_codes.py`, `tests/test_provider_schema.py:ARejectedToolListIsNotABadKey` |
| **One bad field costs one argument, never the session** | A repair pass runs on every start: an undeclared `required` name is dropped, a property with no known type is given one, and each repair is printed and written to the activity log. Silence would be worse than either failure. | `core/action_loader.py:sanitize_declarations` |
| **A crash leaves a file, and a repair starts from it** | Four deaths, four hooks: main thread, worker thread, unraisable, and a native fault Python never sees. A report carries the build, the kind, the traceback and the last notes before the fall, with credentials replaced. The next start says it crashed; a proposal carries the crashes it was made from. | `core/crash.py`, `tests/test_crash.py`, gate claim `crash_record` |
| **Every tool says when to call it, and every call is counted** | A tool with no condition is a tool that is never chosen, and a feature that is never chosen looks exactly like a feature that is never needed. The condition comes first in the line the model reads, because the cap can only cost a description. | `core/tool_prompt.py`, `core/tool_usage.py`, gate claim `triggers` |
| **A yes or no question gets Yes or No first** | A direct answer buried in paragraphs is not an answer to a person who asked a direct question. | how the assistant reports to the owner, recorded in `WORKING-PHILOSOPHY.md` |
| **Plain words before any table** | He flagged excessive technicality three times. Simplified Technical English, one instruction per sentence, the least technical term that is still accurate. | every reply, `WORKING-PHILOSOPHY.md` section 2 |
| **The working philosophy is a file, not a habit** | A handover to another agent cannot rely on a conversation that no longer exists. The one rule, the process, the red lines, the failure patterns and the checklist live in one page any agent can read in ten minutes. | `WORKING-PHILOSOPHY.md`, `OwnerFiles/ULTIMATE_Context.md` |

| **A push is allowed only in one direction** | The ship pushes `main` to `origin` and nothing else: no force, no tag, no other branch, no rewrite of history. A remote that has moved is a refusal sentence, because the alternative is destroying work that someone else published. | `custom_jarvis/ship.py:push`, gate claim `shipping` |
| **A secret is caught before the commit exists** | The scan runs first, so a leak is never in a local commit that someone might push later out of habit. The trade is a slower ship and the risk of a false alarm, which is why the scanner knows the placeholder shapes this repository's own tests use. | `custom_jarvis/ship.py:scan`, `find_secret` |
| **Publishing every change is the owner's switch, not a default** | `ship_auto` is off unless he writes it, because a push is public and this machine cannot un-publish it. With it on, each self-evolution ships itself in one background thread; with it off the change waits in `ship_pending.json` and `ship_status` reports it. | `custom_jarvis/service.py:_note_change`, `tests/test_shipping.py:AutoShip` |
| **An update that does not verify is undone, not explained** | `apply_update` pulls, checks that every `.py` parses, and on failure resets to the commit it came from. A version that cannot start must not be the version on disk, even if the report would be clearer. | `custom_jarvis/selfupdate.py:apply`, gate claim `self_update` |
| **Private development and public promotion are separate** | Personal self-edits and canary releases belong in a private owner-development repository whose credential stays on the owner's machine. The existing public repository remains the professional upstream; promote only reviewed changes through a PR. The owner's installation may follow private `owner-canary`; public installations receive curated stable releases. | `docs/UPDATE_ARCHITECTURE.md` |
| **Model confidence cannot waive a quality gate** | Treat generated source as an untrusted proposal. Self-modify rehearsal must run the full verification harness in a scratch tree; failure, timeout, or missing harness blocks the action. Keep the diff review and two-channel human approval. A green test suite is necessary but not a correctness proof; independent model review is advisory only. | `actions/self_change.py`, `core/self_change.py`, `docs/SELF-CHANGE.md` |
| **Rust ports are selective and evidence-led** | Keep Python as Ultron's GUI, orchestration, provider and policy control plane. Port only a measured, isolated leaf when end-to-end results justify FFI/build complexity; retain Python fallback and parity tests, and preserve all permission gates. No blanket rewrite or Rust target is approved by language preference alone. | `docs/RUST_MIGRATION.md`, `scripts/profile_turn.py`, `scripts/bench_hybrid.py` |
| **Core updates switch workers, never live modules** | Keep the UI/control process available, start and health-check a versioned worker, switch at a safe boundary, let old work drain, and retain rollback. Until that supervisor exists, core changes still require the existing restart marker; do not claim full no-shutdown updates. | `docs/UPDATE_ARCHITECTURE.md`, `custom_jarvis/selfupdate.py`, `core/leaf_generations.py` |
| **Only changed code asks for a restart** | Skills, packs, config and data are read from disk when needed, so a documentation or data change is live at once. Action/plugin leaves reload at a safe reconnect boundary. Other `.py` changes still require a process restart until the approved worker-handoff design is implemented. | `custom_jarvis/selfupdate.py:apply`, `restart-required.json` |
| **The restart marker lives beside the state** | A marker written into the repository is untracked, which makes the tree dirty, which makes the next update refuse — and it could be shipped by accident. It lives in the state folder, and `.gitignore` names it as a second lock. | `custom_jarvis/selfupdate.py:_default_marker` |
| **A plan is written down between steps** | The planner keeps the running plan in memory, so a restart or a crash loses the work and the record of it. Each step transition writes `state/active_plan.json`: the goal, the steps, the index. It holds no output and no capture, and a step whose argument names a secret stops the record instead of writing a hole. Nothing resumes on its own — one line at start offers it, and `resume_checkpoint` reads the same file. Systems that carry a server for this (Temporal, Restate, DBOS) are the wrong size for one desktop. | `custom_jarvis/plan_state.py:save` |
1. Which provider you actually use day to day — the runtime works with any, and the honest
   default is "whichever key you paste".
2. Whether the Agentic OS gets a live bridge to Ultron later. Bundle first was the decision;
   the bridge was not rejected, only deferred.
3. Which of `docs/CAPABILITIES.md` gets built next. That page is a menu, not a plan.
