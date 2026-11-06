# Should Ultron be rewritten in another language?

## Update, 2026-11-06 — asked again, with fresh measurements

The owner asked a second time whether to start rewriting in a faster language. The
answer is the same, and it is stronger now, because the slow paths have been
timed instead of estimated.

| Hot path | Measured cost | Share of real time |
| --- | --- | --- |
| Audio frame classification (30 ms frame) | 39.5 µs per frame | **0.13 %** of the audio |
| Turn reply, in process (no network) | ~8 ms | negligible |
| Tool catalog build | 25 ms | once, on demand |
| HUD repaint | 30 Hz active, 20 Hz idle, none when hidden | throttled by design |
| Model answer (cloud) | 0.6–4 s | **almost all of the wait** |
| Speech recognition | 0.3–1.5 s | the rest of the wait |

**The waiting is the network and the recogniser. Both are already outside Python.**
A rewrite in Rust, C++ or Go would leave those two numbers exactly where they are,
so the owner would wait just as long, in a language that has no provider ecosystem,
after a year of work and the loss of 1,308 tests.

### What a faster language would actually buy

| Gain | Worth it? |
| --- | --- |
| Smaller download than Python + PyQt6 | Partly — solved by packaging, not by rewriting (see the installer plan) |
| No Python requirement on the owner's PC | Solved by PyInstaller one-folder, which is already the plan |
| Faster start-up | Measurable, and solvable with a splash screen and lazy imports |
| Faster drawing | The HUD is 30 Hz and CPU-light; the GPU is idle |
| Memory | 55 MB peak. Not a problem on any machine that runs Windows 11. |

### The narrow plan, if a real hot leaf ever appears

1. **Profile, do not guess.** `python -m cProfile` on a full turn, or `py-spy` on a
   running app. The measurement goes in this file.
2. **Rewrite that one function** in Rust as a loadable module (`maturin`), behind the
   same Python interface, with the same tests. Nothing else changes.
3. **Add a compiled sidecar only if a whole step is hot** — a small binary the app
   starts once and talks to over a pipe.
4. **Never rewrite the shell.** The shell is where every safety invariant lives:
   path confinement, risk tiers, approval gates, and the evidence engine. Rewriting
   it means rewriting and re-proving all of it, and the proof gate is the slowest
   thing in this repository to earn back.

`scripts/bench_algorithms.py` is the instrument. If it ever shows a Python function
above 5 % of a turn, that function is the candidate. Today nothing is.



Asked on 2026-11-06. This is the answer with numbers, and the one case where a
rewrite is worth it.

## The answer in one paragraph

No. Keep Python and PyQt6 for the application shell. A rewrite would cost about
seven months of one person's work, throw away 1,108 tests, and buy nothing the
owner can feel, because Ultron's time is not spent in Python. It is spent waiting
for a model to answer and drawing a window. Both costs stay the same in every
candidate language. If a slow leaf ever appears, rewrite **that function** in Rust
as a loadable module, not the application.

## What is actually here

Measured on this tree today.

| Measure | Value |
| --- | --- |
| Python files | 197 |
| Lines of Python | 75,369 |
| `ui.py` | 8,328 lines — the HUD, overlays, avatar, drawer |
| `main.py` | 2,969 lines — the session, tools, loops |
| `core/` | 15,729 lines in 50 modules |
| `actions/` | 12,964 lines |
| `providers/` | 5,933 lines |
| `tests/` | 12,044 lines, **1,108 tests** |
| `plugins/` | 909 lines, 12 plugins |
| Third-party surface | PyQt6, httpx, google-genai, sounddevice, mss, pywinauto, playwright |
| Startup, measured here | PyQt6 + `QApplication` 32 ms, `import ui` 113 ms, the new TOOLS panel 111 ms |
| Catalog build | 25 ms for 45 tools |
| Peak memory, headless | 87 MB (no full window, no audio stack) |

Those last four rows are the argument. A 111 ms panel and a 32 ms toolkit import
are not a language problem.

## Where the time really goes

A voice turn is: listen (300–900 ms), transcribe (200–1500 ms), call a model
(800–4000 ms), speak (400–2000 ms). The Python in between — dispatch a tool, walk
a dict, build a prompt — is single-digit milliseconds and appears in no profile.
Rewriting the 2% does not improve the 98%.

Two exceptions are real and both are addressed without a rewrite:

- **File scanning and hashing** over a large folder can spend seconds in Python.
  If the owner feels it, that is a Rust extension via PyO3, one module, same
  tests, no migration.
- **Startup** is dominated by imports of Qt and the provider SDKs, not by
  arithmetic. The fix is lazy imports, which this tree already uses for the
  plugin manager, the provider picker and now the tool catalog.

## The candidates, honestly

| Language | Gain | Cost | Verdict |
| --- | --- | --- | --- |
| **Python + PyQt6** (stay) | none needed; every test, plugin and provider already works | the honest cost: no static types, packaging is a zip + venv + winget Python | **keep** |
| **Rust** | 10–50× on CPU-bound leaves; one static `.exe`; memory safety | 6–9 months; Qt has no mature Rust binding with the same widget coverage; PyO3 for leaves instead | **leaves only** |
| **C# / .NET + WPF or WinUI** | best native Windows accessibility and input; single-file publish; strong types | 5–7 months; every action module rewritten; the model and provider layer rewritten; the Linux side of Agentic OS loses its shared code | **no** |
| **Go** | simple binaries, easy concurrency | the weakest desktop UI story of the five; 5–6 months | **no** |
| **TypeScript + Electron or Tauri** | best UI iteration; huge ecosystem | 900 MB Electron runtime, or a Rust core anyway; audio and Windows automation are worse; 5–7 months | **no** |
| **C++** | maximum control | slowest to write, slowest to fix; 9–12 months | **never** |

The one genuinely attractive alternative is **C# with WPF**. It is the only
candidate that beats Python on a Windows-only assistant's hard problems: native
UI Automation, native audio, and a single-file deploy. It also has the biggest
hidden cost: Ultron's whole tool layer, 27 action modules, speaks HTTP JSON to
whichever provider is configured. That layer is the most valuable and the least
language-dependent part of the code, and it would have to be ported, not kept.

## What a rewrite would destroy

- **1,108 tests.** They encode defects that were found the hard way: a tool name
  welded into `open_appopen_app`, a refused image never recorded, `xdg-mime`
  accepting an error sentence as an application at 0.95 confidence, a memory
  write that never asked. A rewrite starts with none of that knowledge.
- **Twelve plugins**, written to one contract, with a loader that validates them.
- **Seven proof-gate claims** and the habit of stating PARTIAL as PARTIAL.
- **The consent, memory and policy tables** — 300 lines of judgement about what
  needs a confirmation, which a rewrite would re-derive from zero.

## When to revisit

Reopen this decision if any one of these becomes true, and only then:

1. A hot path is measured above 500 ms of pure Python in a normal turn.
2. Packaging friction stops more than one install in ten.
3. The assistant needs a UI that PyQt6 cannot draw (multi-touch, 120 fps 3D).
4. Someone other than the owner has to maintain it, and needs typed interfaces.

None of these is true today. The cheapest improvement available now is not a
language. It is a **Windows CI job** that runs the three verification scripts on
every change, so that the 1,108 tests stop depending on my memory of how to run
them.
