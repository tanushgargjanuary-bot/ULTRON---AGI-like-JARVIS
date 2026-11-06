# Ultron

### A voice assistant that lives on your own computer.

You talk. It answers. It does the work.

![Three states of the Ultron HUD: listening, thinking, speaking](docs/img/hud-states.gif)

<sub>An illustration of the HUD in its three states, drawn from the app's own colours by `scripts/make_banner.py`. The real window is in the app.</sub>

---

## The short version

| | |
|---|---|
| **What** | A voice assistant for Windows. Talk to it, and it acts on your computer. |
| **Where** | On your machine. Your keys, your files, your memory. |
| **Cost** | Free. Bring your own model key. A local model costs nothing at all. |
| **State** | Works, and honest about what is unproven. Every claim is tested by a proof gate. |

---

## What it does

🎙️ **Listens and speaks.** Wake word or a key. Answers out loud.

🧠 **Uses a model you choose.** Gemini, Groq, OpenAI-compatible services, or a model on your own machine.

📁 **Works with files.** Reads and writes inside the folder you choose. Outside it, it refuses — in a sentence, not a stack trace.

🖥️ **Drives your desktop.** Opens apps, reads the accessibility tree, falls back to vision when the tree cannot answer.

👀 **Sees the screen or camera only after you agree.** With an indicator, and a stop button.

🌐 **Looks things up.** Web search, GitHub, Hacker News, Stack Overflow, PyPI, npm.
 
👁️ **Watches your background jobs.** An agent in another window, a long build, a render. Ultron notices when one finishes — and if you are talking to it, it waits until you stop talking. A small compiled watcher keeps noticing even if Ultron restarts.

🧷 **Remembers only what you approve.** One file. Delete it and it forgets everything.

🌱 **Grows.** It can write itself a new skill. It can ship its own changes to GitHub. It can update itself and put the old version back if the new one is broken.

---

## Install — three steps

1. **Unpack** this project into a folder you can write to.
2. **Double-click `run.bat`.** Or in PowerShell: `.\run.ps1`
3. **Wait once.** Ten to twenty minutes. It finds Python, builds a private environment, installs the packages, and starts.

After that, it opens straight away.

Then add **one key**: open `config/api_keys.json` and paste a key for the model you use. You can also do it inside the app on the first screen.

<details>
<summary><b>If something goes wrong</b> (click)</summary>

| Problem | Fix |
|---|---|
| "Python 3.14 is not supported" | Install Python 3.12 from python.org. Ultron refuses 3.14 on purpose rather than half-install. |
| PowerShell refuses `run.ps1` | That is the execution policy, not the file. See **Using PowerShell** in [CUSTOM_ULTRON.md](CUSTOM_ULTRON.md#using-powershell). |
| A package failed | The rest still installs. That one feature is off, and the full pip output is in `setup-log.txt`. |
| Want to skip the browser engines | Set `ULTRON_SKIP_BROWSERS=1` before the first run. |

</details>

---

## What it cannot do yet

Say it plainly, so nothing is oversold.

- ❌ **It has not run on your PC yet.** The GitHub build machine runs the tests on Windows and passes. Your microphone, your camera and your apps are yours.
- ❌ **No screen or camera without your consent.** Some machines say no. Ultron will say so.
- ❌ **The browser tool needs Playwright.** Without it, the tool tells you what to install.
- ❌ **It cannot rewrite its own program code.** It writes data skills, not code. Code changes ask you twice.
- ❌ **The compiled watcher needs Go to build.** Without it, Ultron uses the in-process watcher and loses only the crash-proof part. See [docs/SIDECAR.md](docs/SIDECAR.md).
- ❌ **Not for sale.** The licence forbids it.

---

## Your privacy, in four lines

- 🔑 Your keys sit in `config/api_keys.json` on your disk.
- 🏠 With a **local** model, nothing leaves your computer.
- ☁️ With a **cloud** provider, your voice and text go to that company — and the panel says which.
- 🧽 `memory/long_term.json` is everything it knows about you. Delete it and it forgets.

---

## Try this first

```
"Ultron, what can you do?"
"Ultron, open the browser."
"Ultron, how many open issues do I have on GitHub?"
"Ultron, remember that I like short answers."
"Ultron, add a skill that checks my downloads folder for big files."
```

---

<details>
<summary><h2>🔧 For engineers (click to open)</h2></summary>

### Shape of the system

```
ui.py                 window, HUD, animation, voice loop
main.py               the turn: hear → understand → plan → act → speak
core/                 policy, evidence, tools, platforms, avatar, gates
actions/  plugins/    the work: files, apps, browser, dev tools
custom_jarvis/        service, registry, planner, metacog, decisions,
                      skills, schedule, ship, selfupdate
memory/ providers/    keys, facts, model and voice transports
scripts/              verify.py, proof_gate.py, verify_all.py, map.py, bench
tests/                no network, no hardware, no mocks where a real thing fits
```

**218 Python files. 86,664 lines. 1,410 tests.** That count is the last green run's own count; `scripts/verify.py` prints the number it just measured, and a few tests exist only when an optional package is missing, so two machines can differ by a handful. Proof gate, this build, Linux: **16 PROVEN / 13 PARTIAL / 0 FAILED**. It also says why each one is open — `Windows 4, audio or display 3, keys 3, hardware 1, packages 1, your voice 1` — because a bare count is not an explanation. The Windows runner closes the Windows-only claims too; the last artifact said 18 / 9, measured on commit `23e120e`, and has not been re-measured since.

### Five invariants, and what enforces each

| Invariant | Enforced by |
|---|---|
| A tool cannot leave the workspace | `addon_runtime.PATH_ARGUMENTS`, `prepare_args` |
| A tool has a risk tier, or it asks | `tests/test_suite_safety.py` |
| A promise in a docstring needs a file | `scripts/proof_gate.py` — `NOT PRESENT` is a verdict |
| A secret never reaches a commit | `ship.py:scan`, gate claim `shipping` |
| A version that does not parse is put back | `selfupdate.py:apply`, gate claim `self_update` |

### Shipping and updating

`ship.py` runs one fixed order: **scan → guard → syntax → optional gate → commit → push**. The first refusal returns `{ok: false, stage, note}` and names the stage. Push is fast-forward only; a moved remote is a refusal, never a force. `selfupdate.py` refuses a dirty tree, pulls `--ff-only`, verifies every `.py` parses, and resets to the previous commit when one does not.

### Would a faster language help? Measured answer

`python scripts/bench_hybrid.py` — the same audio-frame calculation three ways, on a 30 ms frame:

| Way | Time per frame | Of the audio | Speed-up |
|---|---|---|---|
| pure Python | 53.9 µs | 0.180 % | 1.0× |
| numpy | 21.9 µs | 0.073 % | 2.5× |
| C through ctypes, copying samples | 56.5 µs | 0.188 % | 1.0× |
| C, pointer already in the buffer | **1.5 µs** | 0.005 % | **36×** |

Read the last two rows together. **C is 36× faster only when the samples are already where C can reach them.** Copying them across the boundary costs more than the arithmetic, which is why "rewrite it in C" is not automatically a win.

**What the wait actually is:** the model answer (0.6–4 s) and speech recognition (0.3–1.5 s). Both are outside Python already. Measured with `scripts/profile_turn.py`, the entire Python half of an exchange — policy for every tool, tool description, prompt assembly, memory read — is **0.165 ms**, or 0.004 % of a turn. A rewrite of the shell would move that number, and only that number.

**The hybrid this project would use, in order:** keep the Python shell; profile with `cProfile` or `py-spy`; move a *measured* hot leaf into a small C or Rust module behind the same interface, with the same tests (`native/frame.c` is the worked example, built by `gcc` in one line); add a compiled sidecar only if a whole step is hot. The shell stays Python because the shell is where every safety invariant lives — path confinement, risk tiers, approval gates — and re-proving those in a new language is the slowest work in the repository.

Full reasoning and the earlier version of this answer: [docs/LANGUAGE_DECISION.md](docs/LANGUAGE_DECISION.md). The full filter over 46 languages, section by section, is [docs/LANGUAGE_MATRIX.md](docs/LANGUAGE_MATRIX.md).

### Animation

The HUD draws at 60 Hz and repaints at 30 Hz active, 20 Hz idle, and never when the window is hidden. State colours **cross-fade** over about a sixth of a second instead of switching. The face has a breathing halo, blinking, glances, visemes driven by live amplitude, and expressions that ease rather than snap.

### Verify it yourself

```powershell
python scripts\verify.py        # the suite, the self-checks, the module map
python scripts\proof_gate.py    # the claims, step by step, with verdicts
python scripts\verify_all.py    # the same questions on YOUR machine
python scripts\bench_hybrid.py  # the table above, on your hardware
python scripts\bench_startup.py # what a launch costs, layer by layer
python scripts\profile_turn.py   # the Python half of a turn, stage by stage
python scripts\bench_connection.py # handshakes per call, removed
```

A `SKIP` is never counted as a pass and never as a failure. CI runs all three on `ubuntu-latest` and `windows-latest`: [`.github/workflows/verify.yml`](.github/workflows/verify.yml).

### Documents

| Document | What it answers |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | the six layers, one turn end to end, where a change belongs |
| [docs/INDEX.md](docs/INDEX.md) | every document, one line each |
| [docs/MAP.md](docs/MAP.md) | every module, generated by `scripts/map.py` |
| [GATEKEEPERS.md](GATEKEEPERS.md) | what stands between this and a working Ultron on your machine |
| [DECISIONS.md](DECISIONS.md) | every choice, with the file that enforces it |
| [docs/LANGUAGE_MATRIX.md](docs/LANGUAGE_MATRIX.md) | 46 languages filtered to seven keepers, and the best language per section |
| [docs/SIDECAR.md](docs/SIDECAR.md) | the one Go component: why it exists, what it measures, what it may never do |
| [docs/PERFORMANCE.md](docs/PERFORMANCE.md) | every measured stage: 0.165 ms of Python per turn, 244 ms of launch, 1.5 µs of C, and the handshake removed from every call |
| [HANDOFF.md](HANDOFF.md) | where the work stopped and what is next |
| [log.txt](log.txt) | the build log, mistakes included |
| [OwnerFiles/](OwnerFiles) | the owner's session log and journey, published on purpose |

</details>

---

## Credits

Ultron is a derivative of **[FatihMakes/Mark-LVI](https://github.com/FatihMakes/Mark-LVI)**, pinned at commit `0101e540ac4b16cc3a862d9979e08fefcc1c7a01`. MARK is the application, the HUD, the voice stack and the provider host. Ultron is the layer built on top. This repository is not affiliated with upstream and is not an official release.

**Licence: [Creative Commons BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) — personal and non-commercial use, with attribution.** Keep `LICENSE` and this credit. Selling it is not allowed; publishing it, with these words, is.

With thanks to **FatihMakes** for building MARK in public — [YouTube](https://www.youtube.com/@FatihMakes) · [Instagram](https://www.instagram.com/fatihmakes).
