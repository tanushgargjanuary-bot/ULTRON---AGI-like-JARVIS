# Ultron

**An assistant on your own computer. You talk. It answers, and it does the work.**

Ultron is a voice assistant for Windows. It listens, it speaks, it looks at your screen when you allow it, and it uses tools — files, apps, the web, GitHub — to finish what you asked. It remembers only what you approve. It can add new skills to itself. And it can send its own improvements to GitHub, then take them back again.

Built on the open-source [Mark-LVI](https://github.com/FatihMakes/Mark-LVI) app by FatihMakes. Personal and non-commercial use only. See [Credits](#credits).

---

## What it looks like

A holographic face sits in the middle of the window and reacts while Ultron works: it listens, it thinks, it speaks. Around it are the panel, the activity log and the tools.

| | |
|---|---|
| **Talk** | Press the talk key or say the wake word. Ultron hears you and answers out loud. |
| **Watch it think** | The face and the ring around it change with the state: listening, thinking, speaking. |
| **See what it did** | Every action is written in plain words in the activity log, including what it refused and why. |
| **Ask for more** | The tools panel shows everything it can do, grouped in tabs. Greyed items show what is missing. |

Short screen recordings live in [`renders/`](renders) once you run the app on your own machine.

---

## Install (Windows)

1. Download this project as a ZIP file and unpack it into a folder you can write to.
2. Double-click **`run.bat`**. Or open PowerShell in that folder and type `.\run.ps1`.
3. Wait ten to twenty minutes on the first run. It finds Python, builds a private environment, installs the packages, fetches the browser engines, and starts.

Later runs go straight to the app. Nothing else is needed. If PowerShell refuses the `.ps1` file, see **Using PowerShell** in [CUSTOM_ULTRON.md](CUSTOM_ULTRON.md#using-powershell) — it is a Windows setting, not a broken file.

You need **Python 3.11, 3.12 or 3.13**. Version 3.14 is refused on purpose, so you never get half a build. Then add one model key: open `config/api_keys.json` and paste a key for the provider you use. You can also do it inside the app.

---

## What Ultron can do

**Talk and listen**
- Voice in, voice out, in many languages.
- Any provider you like: Google, Groq, OpenAI, or a model on your own machine. You switch by voice or in the panel. No provider name is fixed in the code.

**Work on your computer**
- Read and write files inside the workspace you choose. Outside it, it refuses, in a sentence.
- Open apps, drive the accessibility tree, fall back to vision when the tree cannot answer.
- See the screen or the camera only after you agree, with an indicator, and you can stop it.

**Look things up**
- Web search and page reading.
- GitHub: your repositories, issues, pull requests, CI results, notifications, and what is new among recently created projects.
- Hacker News, Stack Overflow, PyPI and npm.

**Remember, carefully**
- It stores a fact only after you confirm it. Nothing is remembered in the background.
- The daily digest tells you what it knows, without touching anything.

**Grow**
- It can write a new **skill** for itself as a small data file. A skill may only use read-only tools and may not leave the workspace.
- It can **ship its own changes** to GitHub: scan for secrets, check the ignore rules, check that every changed file still parses, then commit and push. If anything looks wrong, it stops and says which step failed.
- It can **update itself** from GitHub, check the new version, and put the old one back if the new one is broken. Your conversation does not restart.

**Be honest**
- Every claim in this project is checked by `scripts/proof_gate.py`, which reports `PROVEN`, `PARTIAL`, `FAILED` or `NOT PRESENT`. A claim with no code behind it is reported as `NOT PRESENT`, not rounded up.

---

## What Ultron cannot do yet

- **Nothing here has run on your Windows PC yet.** The GitHub build machine runs the tests on Windows and passes, but your microphone, your camera, your screen and your apps are your own.
- **No camera or screen without your consent.** Some machines will say no, and Ultron will say so.
- **The browser tool needs Playwright.** Without it, the tool says what to install instead of failing quietly.
- **No rewriting of code by itself.** It can write data skills, not new program code. Code changes go through you, twice.
- **Not for sale.** The licence forbids it. See [Credits](#credits).

---

## Your privacy, in plain words

- Your keys live in `config/api_keys.json` on your own disk. They are never sent anywhere except to the provider you chose.
- If you use a **local** model, nothing leaves your computer at all.
- If you use a **cloud** provider, your voice and text go to that company. The panel tells you which is which, and it never switches without saying so.
- What Ultron remembers about you is one file: `memory/long_term.json`. Delete it and it forgets everything.
- The secret scan runs before every push, so a key cannot reach GitHub by accident.

---

# For technical readers

Everything below is for people who read code.

## Shape of the system

Six layers, one turn end to end, and one rule for where a change belongs — written out in [ARCHITECTURE.md](ARCHITECTURE.md).

```
ui.py                 window, HUD, animation, voice loop
main.py               the turn: hear → understand → plan → act → speak
core/                 policy, evidence, tools, platforms, avatar, gates
actions/  plugins/    the actual work: files, apps, browser, dev tools
custom_jarvis/        the added layer: service, registry, planner, metacog,
                      decisions, skills, schedule, ship, selfupdate
memory/ providers/    keys, facts, model and voice transports
scripts/              verify.py, proof_gate.py, verify_all.py, map.py, bench
tests/                1,308 tests, no network, no real hardware
```

**Sizes:** 224 Python files, 82,317 lines. **Tests:** 1,308, six skipped here. **Gate:** `14 PROVEN / 13 PARTIAL / 0 FAILED` on Linux, `18 PROVEN / 9 PARTIAL / 0 FAILED` on the Windows runner.

## The five invariants that matter

| Invariant | Enforced by |
|---|---|
| A tool cannot leave the workspace | `addon_runtime.PATH_ARGUMENTS`, `prepare_args`, one test per tool |
| A tool has a risk tier, or it asks | `tests/test_policy_new_tools.py` |
| A promise in a docstring needs a file | `scripts/proof_gate.py`; `NOT PRESENT` is a verdict |
| A secret never reaches a commit | `custom_jarvis/ship.py:scan`, gate claim `shipping` |
| A version that does not parse is put back | `custom_jarvis/selfupdate.py:apply`, gate claim `self_update` |

## Shipping and updating

`ship.py` runs one fixed order: **scan → guard → syntax → optional gate → commit → push**. The first refusal returns `{ok: false, stage, note}` and names the stage, so a failure is never a mystery. Push is fast-forward only; a moved remote is a refusal, never a force. Attempts are recorded in `ship_log.json` (last 100). `selfupdate.py` refuses a dirty tree, pulls `--ff-only`, verifies every `.py` parses, and resets to the previous commit when one does not. A changed `.py` writes `restart-required.json`; data-only changes need no restart, because skills and config are read from disk on demand.

## Speed, and the question of a faster language

Measured on this machine, not guessed:

| Hot path | Cost | Share of real time |
|---|---|---|
| Audio frame classification (30 ms frame) | 39.5 µs/frame | **0.13 %** |
| Turn reply, in process | ~8 ms | — |
| Tool catalog build | 25 ms | — |
| Panel repaint | ~30 Hz active, ~20 Hz idle | throttled when hidden |

The heavy work is elsewhere: the network round trip to a model, and speech recognition. Those are remote or C code already. **A rewrite would not make Ultron answer faster.** What a faster language *would* buy is a smaller download and no Python requirement, at the cost of a year of work and the loss of the provider ecosystem.

The honest plan, if portability or start-up ever becomes the bottleneck, is a narrow one: keep the Python shell and move a measured hot loop into a small compiled module behind the same interface. That is a decision for data, not taste. The reasoning and the numbers are in [docs/LANGUAGE_DECISION.md](docs/LANGUAGE_DECISION.md).

## Animation

The HUD draws at 60 Hz and repaints at 30 Hz when active, 20 Hz when idle, and never when the window is hidden. State colours now **cross-fade** instead of switching, so a change of state is a movement and not a glitch. The face has a breathing halo, blinking, glances, visemes driven by the live amplitude, and expression targets that ease rather than snap.

## Test and prove it yourself

```powershell
python scripts\verify.py        # the suite, the self-checks, the module map
python scripts\proof_gate.py    # the claims, step by step, with verdicts
python scripts\verify_all.py    # the same questions on YOUR machine (Windows, mic, screen)
```

A `SKIP` is never counted as a pass and never as a failure: a question that does not apply here is not evidence either way. CI runs all three on `ubuntu-latest` and `windows-latest` — see [`.github/workflows/verify.yml`](.github/workflows/verify.yml).

## Project documents

| Document | What it answers |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | the six layers, one turn end to end, where a change belongs |
| [docs/INDEX.md](docs/INDEX.md) | every document, one line each |
| [docs/MAP.md](docs/MAP.md) | every module, generated by `scripts/map.py` |
| [GATEKEEPERS.md](GATEKEEPERS.md) | what stands between this and a working Ultron on your machine |
| [DECISIONS.md](DECISIONS.md) | every choice you made, with the file that enforces it |
| [HANDOFF.md](HANDOFF.md) | where the work stopped and what to do next |
| [log.txt](log.txt) | the build log, including the mistakes |
| [OwnerFiles/](OwnerFiles) | the owner's own session log and journey, published on purpose |
| [PUBLISH.md](PUBLISH.md) | how the repository is pushed, and which token settings work |

## Contributing and licence

This is a personal project and it accepts its own rules: every claim needs a test, every fix needs a note in `log.txt`, and a defect is written down with the same care as a feature. Read [AGENTS.md](AGENTS.md) before changing anything.

---

## Credits

Ultron is a derivative of **[FatihMakes/Mark-LVI](https://github.com/FatihMakes/Mark-LVI)**, pinned at commit `0101e540ac4b16cc3a862d9979e08fefcc1c7a01`. MARK is the application, the HUD, the voice stack and the provider host; Ultron is the layer built on top of it. The upstream project is not affiliated with this repository, and this is not an official release.

**Licence: [Creative Commons BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/).** Personal and non-commercial use only, with attribution. That licence travels with this repository: keep `LICENSE` and this credit. Selling it is not allowed; publishing it, with these words, is.

With thanks to **FatihMakes** for building MARK in public — [YouTube](https://www.youtube.com/@FatihMakes), [Instagram](https://www.instagram.com/fatihmakes).
