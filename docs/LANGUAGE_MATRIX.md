# The language filter — 46 names, six keepers, and why

The owner asked for a filter over every language on the list, and for the best
possible language per section of Ultron. This document answers both, in that
order.

Three rules decide every row below. They are not aesthetic preferences; they are
the reasons a language enters a program that a non-technical person has to
install and keep running.

1. **A language earns its place only if it removes a measured cost.** Ultron's
   real waits are the model answer (0.6–4 s) and speech recognition (0.3–1.5 s).
   The hottest thing this program computes itself is 0.18 % of one audio frame.
   There is almost nothing left to speed up, so "faster language" is mostly a
   question about *packaging*, not about code.
2. **Every runtime is a cost the owner pays.** A second toolchain means another
   download, another antivirus conversation, another crash surface, another thing
   that can fail on a machine that is not mine. A 36× speed-up on 0.005 % of a
   frame buys nothing and costs a 600 MB install.
3. **The safety invariants live in the shell.** Path confinement, risk tiers,
   approval gates, the evidence trail — every one of them is Python here, with
   tests. Re-proving them in another language is the most expensive work in this
   repository, and speed is the smallest prize for doing it.

## The 46, one line each

Verdicts: **KEEP** — in the program now. **CONSUME** — its libraries are used,
its source is not ours. **LATER** — worth adding, with a named trigger.
**NO** — with the reason it lost.

| # | Language | Verdict | Why, in one line |
|---|---|---|---|
| 1 | Rust | **LATER** | The first compiled choice if a leaf ever needs it: memory-safe, one static binary, no GC pause. No measured hot path today. |
| 2 | C | **KEEP, sparingly** | The smallest possible leaf behind an interface. `native/frame.c` exists as the template — 60 lines, 36× faster **only** when nothing is copied. |
| 3 | C++ | **CONSUME** | Already ships inside this program: Qt (the HUD), PortAudio (the microphone), llama.cpp (local models). Writing new C++ here would buy nothing and cost a manual memory audit. |
| 4 | Zig | **NO** | The right answer to C's footguns, the wrong time to bet the installer on it: no stable cross-compilation story for our target and no ecosystem for what we need. |
| 5 | Odin | **NO** | Excellent for games and tools, zero libraries for voice, Qt or Windows accessibility. |
| 6 | Nim | **NO** | Python-like syntax with native speed sounds ideal until the packaging: a second toolchain, a small community, and no gain at 0.18 %. |
| 7 | D | **NO** | A fine language that never found its niche; nothing here needs what it uniquely offers. |
| 8 | Go | **LATER** | The best candidate for a *single-binary sidecar* (a tray app, a file watcher that survives the Python process crashing). Trigger: when Ultron must run a component that outlives the app. |
| 9 | Ada | **NO** | Built for proof-grade correctness in systems where a bug kills someone. The invariants here are enforced by tests, and a compiler cannot check "ask the owner twice". |
| 10 | C3 | **NO** | A promising evolution of C, far too young to be a dependency. |
| 11 | V | **NO** | Same answer as C3, with a smaller standard library. |
| 12 | Assembly | **NO** | No section of this program is instruction-bound. Where it matters — FFT, mixing, dot products — numpy and the C leaf already issue it. Hand-written SIMD is a maintenance bill paid forever for a gain measured in microseconds. |
| 13 | Swift | **NO** | A macOS/iOS language. Ultron is a Windows-first program; porting the HUD to SwiftUI would delete the platform it ships on. |
| 14 | Objective-C | **NO** | Same target problem, plus an ageing toolchain. |
| 15 | Python | **KEEP, the shell** | Where every invariant, tool, test and gate lives. Slow at arithmetic, instant at orchestration, and the only language here that non-technical owners can read and correct. |
| 16 | Mojo | **NO, watch** | The most interesting language on the list for numerical work, and not yet open enough to be a dependency of a program that must install on a stranger's PC. Revisit when the toolchain ships and the licence allows redistribution. |
| 17 | Julia | **NO** | Magnificent for statistics and simulation. Ultron does neither; it asks a model and moves a file. Add it if the owner ever wants local data analysis. |
| 18 | CUDA C++ | **CONSUME** | Real, and already in play through llama.cpp and whisper.cpp. Hand-written kernels only pay off when training, and this program does not train. |
| 19 | Triton | **NO** | A tool for writing training kernels. Nothing here trains. |
| 20 | SYCL | **NO** | Cross-vendor GPU programs, an ecosystem that is still maturing, and no kernel of ours to port. |
| 21 | OpenCL C | **NO** | The vendor-neutral option nobody maintains; llama.cpp's backends cover more hardware with less work. |
| 22 | Fortran | **NO** | Still unbeaten for dense numerical arrays. Ultron has none; the audio math is 480 integers at a time. |
| 23 | Chapel | **NO** | Parallel HPC, a small community, no fit. |
| 24 | Java | **NO** | A JVM in the install for no capability Python lacks here. Accessibility bridging is available through `uiautomation` and PowerShell instead. |
| 25 | Scala | **NO** | Its best idea — typed functional design — is a style, not a speed-up. |
| 26 | C# | **NO, with a trigger** | The one Windows-native language that could replace parts of the desktop automation (WinRT, UI Automation, WPF). Trigger: when the accessibility tree stops being enough. Until then it is a second runtime for one bridge. |
| 27 | Elixir | **NO** | Built for millions of concurrent connections across a cluster. Ultron is one user, one machine, one conversation. |
| 28 | Erlang | **NO** | The parent of Elixir, with the same mismatch and a syntax that would cost the owner's ability to read the code. |
| 29 | TypeScript | **LATER** | The dashboard is a browser app served by `dashboard/server.py`. It is plain JavaScript today and that is sufficient. Trigger: when the dashboard passes roughly 2,000 lines, types start paying for the build step. |
| 30 | JavaScript | **KEEP, existing** | It is what the dashboard already uses. No new JavaScript; TypeScript when the dashboard grows. |
| 31 | OCaml | **NO** | Type inference and pattern matching are pleasures, not capabilities here; the team that must read this code is the owner. |
| 32 | Haskell | **NO** | Same, with a steeper on-ramp. A laziness bug in a real-time audio path is a worst-case scenario. |
| 33 | Kotlin | **NO** | Its strength is Android and the JVM. Neither is a target. |
| 34 | Dart | **NO** | Flutter is a good UI toolkit, and the HUD is already written in Qt with animation and tests. Rewriting it would delete working work. |
| 35 | F# | **NO** | .NET again, for a syntax benefit that does not move a number. |
| 36 | R | **NO** | Statistics, plots, and an install the owner does not need. |
| 37 | Prolog | **NO, tempting** | A rule engine for consent and risk tiers is genuinely attractive — and the existing Python rules are already declarative, deterministic, and covered by tests. A second engine adds a second way for the same decision to be made. |
| 38 | Lisp | **NO** | Homoiconic macros are the best answer to a problem this codebase does not have. |
| 39 | Scheme | **NO** | Interesting as a *scripting sandbox* for generated skills; WebAssembly does that job with a real security boundary. |
| 40 | APL | **NO** | Array notation that a non-technical owner cannot read, for arrays that numpy already handles. |
| 41 | VHDL | **NO** | Hardware description. Nothing here is a chip. |
| 42 | Verilog | **NO** | Same, with a different vendor accent. |
| 43 | PowerShell | **KEEP** | The Windows launcher, the diagnosis scripts, the accessibility bridge. `run.ps1` and `collect-data.ps1` are already in the tree. |
| 44 | Bash | **KEEP** | CI steps, release glue, and the leak scan. The GitHub workflow uses `shell: bash` on purpose, because the Windows shell was lying about exit codes. |
| 45 | SQL | **KEEP** | SQLite holds the state that must survive a crash: approvals, evidence, the queue, the schedule. |
| 46 | WebAssembly | **LATER** | The right sandbox for a *generated* skill: a skill that can only touch what it is given. Trigger: the first skill pack that runs code I did not write. |

Tally: **6 keep** (Python, C, PowerShell, Bash, SQL, JavaScript), **2 consume**
(C++, CUDA through llama.cpp), **5 later** (Rust, Go, TypeScript, WebAssembly,
and Mojo on watch), **33 no** — each with a reason, not a shrug.

## Section by section: the best language for each part of Ultron

| Section of Ultron | Today | Best fit | Why the best fit is not "a rewrite" |
|---|---|---|---|
| The turn: hear → understand → plan → act → speak | Python (`main.py`) | **Python** | The time is spent waiting on the network. An async runtime is the right shape, and the invariants live here. |
| Policy, risk tiers, approvals, evidence | Python (`core/`, `custom_jarvis/`) | **Python** | This is judgement written as rules and tests. It is read by humans and audited by the gate. |
| Audio leaves: level, visemes, resampling | Python + **numpy** | **C behind a zero-copy pointer** | Measured: 53.9 µs → 21.9 µs with numpy, and 1.49 µs in C **when the buffer is already there**. With a copy, C is 56.5 µs — slower than Python. So: numpy now, C only at the boundary where the buffer already lives. |
| Speech recognition and synthesis | Python, provider-side | **Python** | The work happens on someone else's GPU. |
| Local models | llama.cpp / whisper.cpp | **C++ and CUDA, consumed** | These are the fastest thing available on a laptop, already written, already buildable. Writing our own kernel would be slower than these and slower to maintain. |
| The HUD, avatar, animation | Python + **Qt (C++)** | **Qt**, kept | 60 Hz drawing in a tested Python file. A Rust `wgpu` rewrite becomes right only if the window must hold 120 fps in 3D. |
| Background supervision | Python + **psutil** | **Python**, with **Go** as the escape hatch | One pass over the whole process table every two seconds was measured at **3.4 ms** — 0.17 % of the interval — so the watcher costs less than the poll loop that drives it. Trigger for Go: a component that must survive the app crashing. |
| Memory and state | **SQLite (SQL)** + JSON | **SQLite** | Already transactional, already on every machine, already atomic. |
| Dashboard | Python server + **JavaScript** | **TypeScript** later | One page, served locally. Types start paying at around 2,000 lines. |
| Installer and launchers | **PowerShell** + batch + Inno Setup | **PowerShell** + Inno Setup | The owner's platform is Windows; these are its native tools. |
| CI, leak scan, release | **Bash** + Python | **Bash** | Already fixed a real bug: a Windows shell that reported success after failure. |
| Generated skills | Python, in-process | **WebAssembly** later | A generated skill should not have the same reach as the program. A WASM boundary is a real fence; an in-process import is not. |
| Numerical research, plotting | none | **Julia** or **R**, on demand | If the owner asks for analysis, install it then. Not before. |

## The hybrid, in one paragraph

**Python is the shell, numpy is the arithmetic, C is the leaf, SQLite is the
memory, Qt is the pixels, PowerShell is the door, and Bash is the conveyor.**
Everything else on the list is a tool this program either already consumes
(C++, CUDA through llama.cpp), will adopt behind a named trigger (Rust, Go,
TypeScript, WebAssembly), or has no use for.

## How a leaf gets promoted (the rule that keeps this honest)

1. **Measure first.** `cProfile`, `py-spy`, or a script like
   `scripts/bench_hybrid.py` with a median over thousands of rounds. Never a
   single stopwatch, never a feeling. This rule already paid for itself: deferring
   `psutil` out of `ui.py` looked like a 22 ms saving on a noisy harness, and
   measured properly — seven fresh processes each — it was 186 ms to 182 ms, with
   no faster first frame, because the window builds the system monitor anyway. The
   change was reverted rather than kept for the story.
2. **Move one leaf, behind the same interface.** The function keeps its name, its
   arguments and its tests. `native/frame.c` is the worked example: same inputs,
   same outputs, and `bench_hybrid.py` checks that all four implementations agree
   on peak, RMS and zero crossings.
3. **Never copy across the boundary.** The measured table is the reason: 56.5 µs
   with a copy, 1.49 µs without. If the data has to be copied, do not promote.
4. **Ship the toolchain only when it earns its install.** C is already on every
   Linux machine and in MSVC on Windows. Rust is not, which is why it is LATER and
   not KEEP.
5. **Delete the leaf if it stops paying.** The fastest code is the code that is
   not in the build.

## What this filter refuses, in one line each

- **A full rewrite in any language on the list.** The shell is not the slow part,
  and re-proving the invariants is the expensive part.
- **A second runtime for a fraction of a percent.** 0.005 % of a frame is not a
  reason to ship a compiler.
- **A language that the owner cannot read.** The owner maintains this. A program
  they cannot read is a program they cannot trust, and trust is the feature.

## Evidence

- `scripts/bench_hybrid.py` — the four-way measurement, reproducible on any
  machine.
- `native/frame.c` — the leaf template, 60 lines, integer square root, no libm.
- `docs/LANGUAGE_DECISION.md` — the longer reasoning and the earlier numbers.
- `scripts/proof_gate.py` — claim `budgets` measures the hot path rather than
  quoting an opinion.
