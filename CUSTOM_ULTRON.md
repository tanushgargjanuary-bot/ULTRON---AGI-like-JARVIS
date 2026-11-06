# Ultron — built on MARK LVI (first integrated release)

## New project base

Our working base is now **FatihMakes/Mark-LVI**, not the previous CustomTkinter application.

- Upstream: https://github.com/FatihMakes/Mark-LVI
- Inspected/pinned commit: `0101e540ac4b16cc3a862d9979e08fefcc1c7a01`
- Upstream author: **FatihMakes**. Original license and attribution remain included.
- License: **Creative Commons Attribution–NonCommercial 4.0**. This derivative is not being represented as commercially licensed. Review `LICENSE` before distribution or commercial plans.
- This is an integration, not a claim that MARK is the most advanced model or that either application has measured “100×” gains.

MARK supplies the application, avatar, lip-sync, Qt HUD, voice sessions, provider settings, native action/plugin ecosystem, native memory, undo and remote dashboard. The old application's UI, audio engine and launchers are not bundled into this new product. Its deterministic evidence/repair components live in the isolated `custom_jarvis/` package so they cannot overwrite MARK's different `core/` package.

The previous project is retained separately as a fallback while Windows acceptance testing remains outstanding. No API keys, old memory databases, screenshots, recordings or personal configuration were silently imported.

## Run on Windows

1. Install **64-bit Python 3.12**. Enable **Add python.exe to PATH**.
2. Extract the **complete** `ultron.zip` into a **new writable folder**. Do not reuse the old application's `.venv`.
3. Double-click the single **`run.bat`**.
4. First run creates `.venv`, installs MARK's dependencies and invokes its setup, including Playwright browser installation. This needs internet access and can download several hundred MB. Installed dependencies are not bundled in the ZIP.
5. Configure your provider through MARK's own setup / **ENGINE & PROVIDERS**. The custom layer does not force Groq or change MARK's model choice.

The launcher accepts Python **3.11–3.13**, preferring **3.12**. It refuses Python 3.14 instead of repeating the earlier incompatible-environment setup. It never deletes an existing environment automatically. On setup failure the console stays open. Requirements changes trigger setup again. To force setup, delete only `.venv\.custom-mark-ready`.

**PyAudio is not a dependency.** MARK uses its existing `sounddevice` audio path. This removes the previous PyAudio/`portaudio.h` build failure path; it is not a guarantee that every microphone, driver or Python dependency works on every Windows machine.

Linux/macOS: use a Python 3.11–3.13 virtual environment, run `python setup.py`, then `python main.py`. Platform-specific permissions and system libraries still apply.

## Where the new capabilities appear

Open MARK's **Controls** drawer. Five additive buttons are available:

- **CUSTOM: SELECT WORKSPACE** — native folder picker, followed by an explicit confirmation before saving the workspace selection.
- **CUSTOM: WORKSPACE SKILLS** — lists the 24 recipes and prerequisite/applicability information.
- **CUSTOM: STATUS / EVIDENCE** — selected workspace, task state/result/error, file transaction, repair catalog, fingerprint and custom-service budget.
- **CUSTOM: INSIGHTS / NEXT STEPS** — menu to view suggestions, review the next preference for approval, dismiss a candidate, or forget saved insight preferences.
- **CUSTOM: STOP TASK** — requests cancellation of the custom task. Completed actions are not undone; this is not a general kill switch for native MARK tools or blocking provider calls.

The `custom_jarvis` plugin is also automatically discovered by MARK. You can ask, for example:

- “Show the custom workspace skills.”
- “Run the custom `orient` skill in my selected workspace.”
- “Preview the custom `python_preflight` skill for `main.py`.”
- “Use the custom file tool to read `README.md`.”
- “Show the custom task's actual verification result.”

These are requests to the model, not guaranteed natural-language routing. The plugin's exact operation/schema remains available to the selected provider. Small local models may route less reliably. Its `tier=core` metadata helps retain it within MARK's local-model tool budget.

A job response of **started** is NOT completion. Final evidence appears in the existing HUD content area; `status` retrieves the actual result. Tasks run on workers, not on the Qt GUI thread. The new controls use Qt signals for worker results and never construct widgets from a tool thread.

## Finding the data in an install folder

`scripts/collect_install.py` (or double-click `collect-data.bat`) scans an install folder, classifies every file
as code / doc / cache / config / data / **unknown**, fingerprints each one, and reports what changed since the
last run. It defaults to `D:\Downloads\mark-custom-jarvis`.

```
python scripts\collect_install.py                                  scan, report, remember fingerprints
python scripts\collect_install.py --watch --interval 5             print files as they appear (Ctrl+C)
python scripts\collect_install.py --bundle data.zip                ZIP of DATA ONLY, secrets blanked
python scripts\collect_install.py --bundle data.zip --include-secrets   keep the key values
```

- **unknown** is a real category, not a failure: a file nothing recognises is exactly what "new stuff" looks like.
- If the bundle leaves a file out, it names the file and the reason. A bundle that silently omits something is
  worse than none, because the manifest is then trusted to be complete.
- The bundle contains only `data/`, `config/` and `unknown` files plus `MANIFEST.json` and `REPORT.txt` — never
  the 120 source files. Oversized files are skipped, not truncated.
- Credential values are blanked by default; field names are still listed so the manifest is useful.
- It never uploads anything, never deletes anything, and never leaves the folder it was given via a symlink.

## What launch costs, and what it used to cost

Measured with `python scripts\bench_startup.py`, medians of three runs, each stage in its own
process (timing imports in one process reports the first stage hot and every later one cold, which
is meaningless):

| Stage | Before | After | |
| --- | --- | --- | --- |
| `import main` | 723 ms | **170 ms** | −76 % |
| action discovery | 185 ms | **117 ms** | −37 % |
| libraries pulled in at launch | `google.genai`, `google.genai.types`, `PIL`, `PIL.Image` | **none** | |
| one turn of local work | 0.7 ms | 0.7 ms | unchanged, and that is the point |

The per-turn work — prompt assembly, history trimming, risk classification, the spoken-register
pass — was already under a millisecond, next to a network round trip in the hundreds. There was
nothing there to win, so nothing there was touched.

The launch was a different story. `from google.genai import types` alone was **507 ms**: it drags
in pydantic, httpx and aiohttp whether or not a model is ever called. Deferred through
`core/lazyimport.py` — the mechanism this project already used for `pyautogui` and OpenCV — it is
paid on the first actual use instead, with the name unchanged at every call site.

Two more, found by scanning the launch path rather than by guessing at it:

- **`actions/youtube_video.py` imported `pyautogui` and `numpy` and never used either.** Only the
  two feature flags were read, and nothing read those. `pyautogui` is ~290 ms on Windows. Deleted,
  not deferred: an import nobody uses is not a cost to postpone.
- **`requests`** in the same file (156 ms) and **`PIL.Image`** in `actions/screen_processor.py`
  (23 ms) moved to first use, keeping their `_REQUESTS_OK` / `_PIL` flags answered by `find_spec`,
  which locates a package without executing it.

The rule that keeps it that way is enforced, not remembered: `tests/test_lazyimport.py` walks the
AST of every file in `actions/` and `plugins/` and fails if a heavy library is imported at module
scope. Timing tests measure the machine they run on; "this file does not import pyautogui at launch"
is true everywhere.

Skipped deliberately: `browser_control.py` already deferred `playwright` itself, and its
`if TYPE_CHECKING:` import is invisible to the check because it never executes.

## Using PowerShell

Both entry points exist as `.ps1` as well as `.bat`, and they do the same things. The PowerShell versions take
the collector's flags **verbatim** — they are passed straight through to the script, so every command above works
by replacing `python scripts\collect_install.py` with `.\collect-data.ps1`. There are no PowerShell-style
parameter names to learn, and no risk of an unrecognised flag being swallowed by parameter binding.

| Task | PowerShell |
| --- | --- |
| Start Ultron | `.\run.ps1` |
| Scan the install folder | `.\collect-data.ps1` |
| Scan a different folder | `.\collect-data.ps1 --path "D:\Downloads\mark-custom-jarvis"` |
| Bundle the data only | `.\collect-data.ps1 --bundle data.zip` |
| Bundle including key values | `.\collect-data.ps1 --bundle data.zip --include-secrets` |
| Watch for new files | `.\collect-data.ps1 --watch --interval 5` |
| Machine-readable report | `.\collect-data.ps1 --json \| Set-Content -Encoding utf8 report.json` |
| What data exists | `.\.venv\Scripts\python.exe scripts\inventory_data.py --install "C:\ultron"` |
| Migrate an old install | `.\.venv\Scripts\python.exe scripts\migrate_legacy.py --from "C:\old" --to "C:\ultron" --dry-run` |
| Run the full check | `.\.venv\Scripts\python.exe scripts\verify.py \| Tee-Object verification-results.txt` |

The `.bat` launchers still work from a PowerShell prompt (`.\run.bat`, `.\collect-data.bat`); they are for
double-clicking.

Three PowerShell-specific facts worth knowing, because each one produces an error that looks like a broken app:

1. **Execution policy.** If PowerShell refuses a `.ps1` with *"running scripts is disabled on this system"*, that
   is the policy, not the file. For the current window only:
   `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`. Or launch without changing anything:
   `powershell -ExecutionPolicy Bypass -File .\collect-data.ps1`. `-Scope Process` reverts when the window closes;
   avoid setting it machine-wide for a script you have not read.
2. **Mark of the web.** A file extracted from a downloaded ZIP is blocked even with the policy set. `Unblock-File`
   clears it: `Get-ChildItem -Recurse -Include *.ps1,*.bat | Unblock-File`. Both launchers say this in their help.
3. **Redirection encoding.** Windows PowerShell 5.1 writes files as UTF-16LE by default, so
   `.\collect-data.ps1 --json > report.json` produces a file other tools cannot read. Use
   `| Set-Content -Encoding utf8`, or PowerShell 7 where the default is already UTF-8.

Exit codes survive the wrapper, so a scheduled task or a script can branch on them: **0** success, **2** the folder
is not a folder, **3** no usable Python or the collector script is missing. A non-zero exit also holds the window
open when the script was run by right-click → *Run with PowerShell*, so the message is readable instead of
flashing past; a successful run never waits for a keypress.

`run.ps1` is the same logic as `run.bat`: reuse `.venv` if it exists, otherwise create it from Python 3.11–3.13,
run `scripts\bootstrap.py`, then `main.py`. It never upgrades an existing environment — a working install outranks
a current one.

## What data exists (and what does not)

Run this on any install before migrating or sending files for diagnosis:

```
python scripts/inventory_data.py --install "C:\path\to\install"
```

It reports which data files exist, their sizes, the keys and record counts inside them, and opens the custom
SQLite store read-only to count rows. It prints **no values** — no memory text, no names, no keys — only field
names and numbers.

Two facts worth stating plainly:

- Everything in `actions/`, `core/`, `providers/` and `plugins/` is **code**. Copying those files transfers no
  data at all.
- **This build stores no conversation transcript.** End-of-session summaries were deliberately disabled in favour
  of manual, approved memory. An install that only ran this build holds saved facts, settings and workspace
  state — not the talks themselves.

## Carrying an older install's data across

Rename, same file formats. Run once, with the old build closed:

```
python scripts/migrate_legacy.py --from "C:\path\to\old\install" --to "C:\path\to\ultron" --dry-run
python scripts/migrate_legacy.py --from "C:\path\to\old\install" --to "C:\path\to\ultron"
```

It copies `config/api_keys.json`, `memory/long_term.json` and the custom state folder
(`%LOCALAPPDATA%\CustomMarkJarvis\`). It **blanks every credential-looking field** unless you pass
`--include-keys`, renames the assistant to Ultron unless you pass `--keep-name`, backs up any file it
overwrites, writes atomically, and only ever reads the old install. Screenshots, backups, repair history and
the browser profile are deliberately left behind.

## Risk-tiered consent — routine actions no longer ask

*Updated: the custom service now calls `policy.set_workspace_roots()` whenever a workspace is selected
or restored, so writes inside the folder you picked are routine and everything outside it still asks.*


The gate used to allow four observational tools and put **everything else** behind a HUD banner, so
opening a browser cost the same confirmation as shutting the machine down. Asking that often destroys the
value of the prompt: the user starts pressing CONFIRM without reading it.

`core/policy.py` now classifies every call into four tiers:

| Tier | Examples | Behaviour |
|---|---|---|
| **observe** | memory recall, system status, web search, file read/list | runs immediately |
| **routine** | open an app, browser navigation, typing/clicking, media, reminders, volume, writes **inside** the approved workspace | runs immediately |
| **guarded** | delete/move/rename, send message, install, close an app holding unsaved work, shutdown/restart, code self-editing, unclassified tools | real HUD confirmation |
| **sensor** | screenshot, screen reading, camera | confirmation, or a bounded task grant |

- **Unknown tools are guarded.** Adding a tool does not add trust; a plugin cannot exempt itself.
- `policy.grant("sensor", seconds)` pre-authorises a sensor for one task and expires on its own.
- `policy.set_workspace_roots([...])` is what makes writes inside the chosen folder routine; with no
  workspace, every write still asks.
- The confirmation path itself is unchanged: frozen argument snapshot, a token only the UI can issue,
  no stacking of two pending banners.

The system prompt was corrected to match, so the model stops asking verbally for things the gate already
permits.

## Provider routing — mechanism ready, engine wiring still to do

`core/routing.py` implements the agreed routing rules as pure, tested logic. **It is not yet connected to
MARK's engine pipeline**, so today's provider choice is still whatever `⚙ → ENGINE & PROVIDERS` holds.
Saying so plainly matters more than the module looking finished.

What it already does:

- **Three purposes** — conversation, evolution/repair, critic — each with its own provider and model.
- **Quota is tracked per quota group**, not per key: two keys on one account share one budget, because
  that is how providers apply limits. Nothing multiplies an allowance by the number of keys, and key
  rotation to escape a limit is not implemented.
- **`Retry-After` blocks the whole group**, not the one key that hit the 429.
- **A fallback ladder** that will not take a **paid** or **data-sharing** fallback unless that was
  explicitly allowed; choosing a paid provider as your *primary* is fine, being switched to one silently
  is not.
- **Local tail** — the ladder ends at your local model, and a capability downgrade is visible.
- **Voice/typed switching parser** — "use Groq", "switch the critic to Groq",
  "use Groq with qwen3.8-27b", "go local for now". Only providers you configured are recognised, so an
  unconfigured name is a question for the model, not a silent switch. Parsed locally: it costs no request
  from the quota it is trying to conserve.

## Semantic application resolution — "browser" is a capability, not a filename

Reported: *"I told it to open browser, it searched Windows search, found a folder named browser and opened
that."* The cause was `actions/open_app.py` typing the raw word into the Start-menu search box and trusting
whatever the shell matched.

`core/app_resolver.py` now answers the question properly:

1. **Category words** (`browser`, `email`) resolve through the operating system's own handler registration —
   the `http` handler *is* the default browser, whoever makes it.
2. **Other categories** (`notes`, `editor`, `music`, `terminal`) match installed application names on
   **words**, not substrings, so "notes" does not match "Notepad++ Helper Logs".
3. **Running applications are reused** before anything is launched.
4. **One winner** is resolved; **several comparable candidates** produce one short question and no launch;
   **nothing** is an honest `unknown`.
5. **A directory is never an application**, however well its name matches.

The Start-menu typing path is disabled entirely for category words, so the reported failure cannot recur
by construction. No browser or vendor name is stored anywhere in the project.

## Expressive avatar — meaning, not just loudness

`core/avatar.py` already rigged brows, gaze, blink, lids and lip shape from loudness and app state.
`core/expression.py` adds the semantic channel: a bounded seven-parameter expression vector
(smile, brow raise, brow furrow, squint, lid widen, lip press, asymmetry) blended into the same channels.

- Sources: app state, an optional tag from the reply (`amused`, `concerned`, `concentrating`,
  `reassuring`…), and voice prosody — no extra model, no API call.
- **Guard:** a positive expression is suppressed when the sentence reports a failure, so the face never
  smiles through an error.
- Amplitudes are capped well below the mathematical maximum; a low-poly face at full amplitude reads as a
  mask.
- Timing stays frame-rate independent, so the face behaves the same at 20, 30 and 60 fps.
- `HudCanvas.set_expression(tag, spoken, hold)` is the wiring point for the model and for future tools.

## Consent-first insights and anticipation

The selected policy is **remember only what the human approves**. This is reviewed adaptation, not uncontrolled autonomous code rewriting or permission expansion.

- The existing conversational model can reason about the current conversation. A new lightweight local layer detects a limited set of explicit phrasing preferences (concise/detailed answers, friendly/professional tone, checklist/step-by-step style). It does not infer personality, health, emotions or hidden intentions.
- Typed messages and completed voice transcripts feed temporary proposals. Nothing is written by observation alone. Candidates/evidence remain in RAM and expire after one hour; they are lost when the app closes.
- Use **Controls → CUSTOM: INSIGHTS / NEXT STEPS → Review next preference for saving**. The real confirmation banner shows the exact preference and supporting phrase. Only confirming saves the small enum preference. It contains no raw transcript or evidence quote. Dismissal does not save anything.
- Approved preferences live in `approved-insights.json` inside the custom state directory and inform the next session's style prompt. Explicit requests in the current conversation take precedence. The same menu supports forgetting them, with confirmation.
- Mentioning a meeting/interview, presentation, release/deployment or study task can produce a **temporary three-item checklist suggestion**. These are simple phrase-triggered readiness templates, not evidence that files were prepared or dates inferred. They do not create documents, schedule reminders, execute actions or run additional provider requests.
- Existing proactive check-ins may use these suggestions, with their existing silence/cooldown gates. Prompt guidance asks for at most one useful recommendation and silence when nothing is useful; actual model responses are not guaranteed.
- Reusable procedures can still be proposed and reviewed through the existing procedure tools. There is no silent application self-modification, model fine-tuning or automatic unreviewed workflow activation.
- Native `save_memory` still requires the HUD gate. **Automatic conversation-summary saving is now disabled** to avoid silently persisting discussed preferences. Existing approved native memory is not erased. This layer does not write raw transcripts; existing host/provider logging and privacy policies still apply.

Plugin operations: `insights` / `recommendations` view temporary state; `review_insight` takes an optional `id` (otherwise the next candidate) and asks human permission to save; `reject_insight` dismisses one; `forget_insights` requires confirmation to delete the insight profile. These are separate from the seven-table evidence-store `forget` operation.

### RAM reminders

JARVIS's background **RAM threshold alerts are disabled by default in code**. The proactive prompt also forbids unsolicited RAM/memory-cleanup nags. The original dashboard RAM meter and explicit `system_status` RAM answers remain. CPU-temperature and other non-RAM alerts were not removed. This does not alter Windows's own notifications, and a generative model cannot be guaranteed never to phrase an unsolicited remark incorrectly.

## Capability comparison and migration status

| Capability | MARK already provides | Added from our JARVIS |
| --- | --- | --- |
| Voice, animated avatar, HUD | Kept native | No competing UI/audio stack |
| Provider selection and background requests | Kept native | Repair generation routes through `core.gemini.as_json`, using MARK's selected background provider |
| Memory and undo | Native memory/undo retained | Separate seven-table evidence store, approved procedures and opt-in checkpoints |
| Confirmation | Existing irreversible-action banner retained | Strict top-level mutating/unknown-tool confirmation; custom tools additionally use per-invocation registry approvals |
| Action evidence | Native outcome conventions retained | Workspace-confined read-back verification, SHA/JSON/Python/Git assertions and explicit goal-vs-step distinction |
| Project workflows | Native actions retained | All 24 auditable skill recipes, applicability/preflight and approved-procedure compiler |
| Recovery | Native undo retained | File backups, conflict-checked multi-file LIFO rollback and independently reverified checkpoint resume |
| Repair | Native coding agent retained, not replaced | Pure bounded argument-adapter DSL, exact reviewed contracts, schema/workspace/handler scope, fingerprints, five-success canaries, quarantine, shadow replay and rollback |
| Repair-loop controls | Native provider routing retained | Custom repair circuit breaker and persisted custom-service budget ledger |

### Exposed custom operations

Call `custom_jarvis` with `operation` and a JSON-object string `payload_json` (maximum 64 KiB):

- `status`, `stop`, `list_skills`, `list_tools`, `knowledge_status`, `procedures`
- `set_workspace`: `{"path":"C:/Projects/MyApp"}`
- `tool`: `{"name":"read_file","arguments":{"path":"README.md"}}`
- `preview_skill` / `run_skill`: `{"id":"python_preflight","target":"main.py"}`
- `verify_goal`: `{"assertions":[{"kind":"json_valid","target":"config.json"}]}`
- `rollback_transaction`: `{"transaction_id":"ID_FROM_STATUS"}`
- `repair_test`: `tool`, `source`, `contracts` (each contract has `input` and `expected` objects)
- `repair_generate`: reviewed `contracts`; requires a captured custom-tool failure and human approval before provider use
- `repair_shadow`: `tool`, `source`, `replay_inputs`; no tool execution or promotion
- `repair_activate`: activates the previously tested candidate only after human review/approval
- `repair_rollback`: `{"tool":"read_file"}`
- `breaker_reset`: requires approval
- `procedure_propose`: `title`, `instructions`; `procedure_approve` / `run_procedure`: `id`
- `resume_checkpoint`: `{"checkpoint":{...}}`; completed artifacts must independently match before skipping
- `forget`: approval required; clears only the custom service's seven tables, not MARK memory or file backups

For `run_skill`, `save_checkpoint:true` separately asks permission to retain task arguments/outputs. Checkpoints are otherwise off. Read operations can still expose selected data to the model when the host sends tool results, as with MARK's native tools.

## Safety and privacy boundaries

1. **Custom tools** always dispatch through `ControlledRegistry.execute` and `EvidenceEngine.prepare_args`. Managed file paths reject traversal and resolved outside-workspace symlinks. Writes get read-back evidence and, when enabled, pre-write backups.
2. The shared MARK tool entry now gates unknown and mutating **top-level** calls with the actual HUD confirmation. A model supplying `confirmed=yes` cannot approve an action. The request's arguments are copied before displaying approval. Missing confirmation UI fails closed.
3. Observational allowlisted tools bypass that outer gate; the custom plugin manages its own per-action approvals. Existing native irreversible-action gates are retained, so some operations can show a second confirmation.
4. **This is not an OS sandbox.** Native MARK actions/plugins, their internal steps, the coding agent and remote-dashboard administrative endpoints have not all been rewritten to use the custom registry or selected workspace. The new outer gate does not make an arbitrary third-party plugin safe. Approved code/shell operations can access resources beyond their working directory.
5. Repairs are **argument adapters**, not automatic edits to MARK's application, plugins, security code or UI. They use the bounded `AdapterProgram` interpreter, never `exec`/`eval`. A passing contract, model confidence or shadow result never auto-promotes a candidate.
6. Native MARK undo and custom backup transactions are distinct recovery systems. Custom transaction grouping is process-local; restarting loses group membership, although the individual backups persist. Shell/desktop/remote effects are not reversible file transactions.
7. Custom breaker/budget accounting currently governs the **custom repair/workflow service**, not the whole Gemini Live conversation, provider account, native coding agent or all dashboard requests. Routing identity `mark-selected-provider` is not a measured underlying-model ID. Verified runtime success attribution to individual remote models remains incomplete.
8. Goal assertions verify only supported deterministic artifact conditions, not arbitrary user intent. Native MARK actions retain their own evidence conventions. Foreground-window drift enforcement is still incomplete; observed-file drift blocking exists in the custom layer.
9. No local vision model was installed or bundled. MARK's existing vision features are retained; configuring or evaluating vision remains a separate step.
10. Old API keys and memory were not auto-migrated. Custom state is stored under `%LOCALAPPDATA%\CustomMarkJarvis` on Windows, or the XDG data directory / `~/.local/share/CustomMarkJarvis` elsewhere. Workspace selection is saved after approval. Keep this state private and use one app process per state directory.

## Measured verification

See the single current `verification-results.txt`:

> The four bullets below are kept as they were written, because they describe the
> **first port** and the number of tests has grown by an order of magnitude since. The
> current figures are at the top of this list, the old ones are in the sentence that
> follows each, and `scripts/verify.py` prints the real number every time it runs.

- **251 Python files syntax-parsed** (101 at the first port).
- **1,737 unit/integration tests passed, 8 skipped, 0 failed** (209 at the first port),
  including the ported deterministic engine tests, repair lifecycle tests, actual
  confirmation-gate tests, service dispatch/backup checks and original MARK window
  construction with the custom controls. This is not the old application's 210-test UI
  suite; its old UI was intentionally not transplanted. The instrument that grew most is
  the proof gate: 35 claims, 22 PROVEN on a Linux machine with no display and no hardware,
  0 FAILED.
- MARK's unchanged **provider self-test reported 99 passed, 0 failed**, including its offscreen settings-panel checks. Optional Piper-specific paths report skipped when Piper is not installed; those paths were not exercised as live synthesis.
- **1,000 offline stress scenarios passed**: original 550 plus isolated repeated workspace/canary/breaker/shadow/transaction lifecycle checks. These are not 1,000 unique fuzz inputs.
- **15/15 targeted seeded mutation defects detected**. This is not comprehensive mutation coverage.
- Ruff selected correctness/import checks passed for added/ported code and tests.

All tests used local mocks and/or loopback servers. There was **no live provider call, real microphone recording, Windows accessibility test or native Windows launcher execution**. Tests ran on Linux/Python 3.13 with Qt offscreen. Full Windows install, live voice and representative real tasks are the next acceptance stage, not claimed as done.

Reproduce after installing the app dependencies:

```sh
python -m pip install -r requirements-dev.txt
python scripts/verify.py > verification-results.txt 2>&1
```

## What was added after the first port

These are the capabilities that did not exist when this document was written, each with the
file that holds it. The full history is in `log.txt`, newest first.

| Capability | Where | What it means in use |
|---|---|---|
| A crash leaves a record | `core/crash.py`, `logs/` | four kinds of death are caught, the report holds the last thing it was doing, and the next start mentions it. "Why did you crash" answers from the file |
| Self-repair starts from that record | `core/self_change.py` | a proposal carries the crashes it was made from, so "why was this changed" has evidence |
| Every tool states when to call it | `core/tool_prompt.py`, `core/tool_usage.py` | the condition comes first in the line the model reads; every call is counted, so a declared-and-dead feature is a number |
| A tool schema must be one the provider accepts | `core/action_loader.py`, `tests/test_provider_schema.py` | one bad field used to cost the whole session; now it costs one argument, and the repair is reported |
| A close code is read as words | `core/close_codes.py` | `1007` no longer means "wrong key" by itself, which is what it wrongly meant for one evening |
| The seven minds | `core/philosophy.py`, `docs/PHILOSOPHY.md` | methods, not permissions, and no voice can widen what the assistant may do |
| The syllabus as logic | `core/mental/`, `curriculum/*.json` | 18 of 284 course topics cite themselves from the code that runs them |

## Next integration work

- Windows install / microphone / live-provider acceptance with the user, then fix any platform-specific issues before retiring the fallback.
- Unify native MARK file/coding actions and remote entry points with per-step workspace/evidence/approval protections, rather than overstating the current top-level gate.
- Add richer native repair/procedure management screens; this first release uses the existing HUD content view and plugin operations, not the old Tk panels.
- Complete restart-persistent transaction membership, account-wide budget scope and verified model-outcome attribution only with corresponding tests.

Upstream attribution, assets and existing capabilities remain. No old project ZIP, installed environment, model weights, screenshots, patch history, credential files or generated caches are included in the new source archive.
