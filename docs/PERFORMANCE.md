# The performance budget — measured, stage by stage

The owner asked why most of the code is still Python, and whether the code itself
could be faster. This document is the answer in numbers. Every figure below was
measured on this machine with a script that ships in the repository, so anyone can
disagree with it by running it.

## 1. The Python half of one exchange: 0.165 ms

`python scripts/profile_turn.py`, median of 100 runs per stage:

| Stage of a turn | Median | p95 |
|---|---|---|
| `policy.decide` for every tool in the registry | **0.009 ms** | 0.013 ms |
| `_describe_tools` — one line per capability, all of them | **0.028 ms** | 0.041 ms |
| `_render_prompt` — fill the system prompt template | **0.054 ms** | 0.068 ms |
| `_load_system_prompt` — read the template from disk | **0.024 ms** | 0.034 ms |
| memory read — parse the JSON store | **0.012 ms** | 0.017 ms |
| memory read + atomic write | **0.037 ms** | 0.060 ms |
| `_clean_transcript` — scrub control characters | **0.001 ms** | 0.002 ms |
| **Sum** | **0.165 ms** | |

One model round trip is **600–4000 ms**. The Python half of a turn is therefore
**0.004 %–0.03 %** of the time the owner waits.

That number is why the shell stayed in Python. It is not a preference; it is what
the profile says. Writing those seven stages in Go or Rust would save at most
0.165 ms and would remove the file where every safety rule lives.

## 2. The launch: 244 ms, once

`python scripts/bench_startup.py` and a fresh-process harness:

| Layer | Cost | Added |
|---|---|---|
| bare interpreter | 14 ms | — |
| + process watcher (psutil) | 40 ms | +26 ms |
| + window classes (Qt) | 195 ms | +155 ms |
| + first drawn frame | 244 ms | +49 ms |

The 155 ms of Qt is the cost of a real window: the alternative is a native UI in
another toolkit, which would delete a working, tested HUD. The 26 ms of psutil is
paid once and buys the background supervision.

## 3. The leaves that are not Python

| Leaf | Pure Python | numpy | C, copying samples | C, buffer already there |
|---|---|---|---|---|
| One 30 ms audio frame (level, RMS, crossings) | 53.9 µs | 21.9 µs | 56.5 µs | **1.49 µs** |

`scripts/bench_hybrid.py`. C is 36× faster **only** when nothing is copied; with a
copy it is slower than Python.

| Component | Size | Start | Resident | Event latency |
|---|---|---|---|---|
| Go supervisor (`sidecar/watchd`) | 2.0 MB | 3 ms | 2.7 MB | 10 ms |
| Python watcher, for comparison | interpreter + psutil | 26 ms | 13.6 MB | same poll |

`scripts/bench_sidecar.py`.

## 4. Line count is not cost

| Area | Lines | What it is | Time it costs per turn |
|---|---|---|---|
| `core/` (56 files) | 16,963 | policy, evidence, gates, platform bridges | 0.009 ms |
| `actions/` (22 files) | 12,964 | the tools: files, apps, browser, dev tools | 0 on a turn that does not call them |
| `custom_jarvis/` (33) | 11,397 | planner, metacog, decisions, skills, shipping | 0 on a turn that does not call them |
| `providers/` (12) | 5,933 | model and voice transports | network time, not CPU |
| `ui.py` + `main.py` | 11,564 | the window and the turn loop | 0.165 ms of assembly |
| `tests/` (61) | 15,066 | proof, not product | 0 |
| `plugins/`, `dashboard/`, `scripts/` | 9,256 | extensions, web panel, tooling | 0 |

84,541 lines of Python, and **the entire measured Python cost of an exchange is
0.165 ms.** A line of policy is not a line of arithmetic: it is a decision that
runs once and is read by a human. Rewriting it in a compiled language would make
it slower to change and no faster to run.

## 5. The connection, measured and fixed

Every provider call site used to build its own HTTP client inside a `with`. A new
client means a new TCP connection, and on `https` a new TLS handshake — three round
trips before the request itself. It was being paid on every transcription, every
synthesis and every one-shot model call.

`providers/connections.py` pools them. `scripts/bench_connection.py`, loopback, ten
requests:

| Pattern | Connections opened | Median per request |
|---|---|---|
| a client per call | **10** | 6.805 ms |
| pooled | **1** | **0.558 ms** |

Loopback has no TLS and no distance, so 6.2 ms is a floor and not the prize. What
is true everywhere is the count: **nine handshakes removed out of ten.** On a
residential connection to a provider in another country, one handshake is the
100–300 ms the earlier table listed — now paid once per session instead of once
per call.

Two details that keep the pool honest, both tested:

* async clients are keyed by **event loop**, because an httpx async pool belongs to
  one loop; sharing it across two is a fault that shows up only after a reconnect;
* `Pooled` is a context manager that does **not** close the client on exit, so a
  caller that writes `with` out of habit cannot close the pool for everyone else.

A measurement mistake, kept: the first version of this benchmark reported that
pooling was **slower** — 43.9 ms against 7.3 ms. The cause was the server, not the
pool: a keep-alive socket on loopback falls into the Nagle and delayed-ACK trap and
every request waits 40 ms. With `TCP_NODELAY` set on the accepted socket, the real
picture appeared.

## 6. The prompt, measured and guarded

The system instruction is not a Python cost; it is a token cost that the provider
pays on **every** request. Measured with `scripts/profile_turn.py`:

| Part | Characters | Share |
|---|---|---|
| hand-written template (`core/prompt.txt`, 234 lines) | 15,534 | 93 % |
| tool descriptions, one line per tool | 1,669 | 10 % |
| the limits block | 1,107 | 7 % |
| **assembled** | **16,620** (≈ 4,155 tokens) | |

There is nothing to cut safely. The template has **no duplicated line**, and nine
tenths of it is persona, rules and refusal policy — the part a rewrite would gamble
on without an evaluation that can tell whether the assistant still behaves. Cutting
1,000 tokens here would save tens of milliseconds at the provider and could change
how Ultron answers, which is a trade this project does not take blind.

So the prompt is **guarded instead of trimmed**:
`tests/test_performance_budget.py::PromptBudget` fails if the assembled prompt
passes 20,000 characters, if the hand-written template passes 18,000, if a tool is
missing from the list or appears twice, or if any `{placeholder}` is left unfilled.

## 7. What would actually make it faster

| Lever | Effect | Owner | How to know |
|---|---|---|---|
| A closer or faster model provider | **300–1000 ms** | the network | measured by the app's own turn timer |
| Smaller speech recogniser | 200–700 ms | the recogniser | `--live` run of the gate |
| Warm connection, no handshake per turn | **100–300 ms — done** | us (Python) | 9 of 10 handshakes removed; see §5 |
| Shorter prompt per turn | 50–200 ms | us (Python) | measured: 4,155 tokens, no duplicated line; guarded, not trimmed blind — see §6 |
| Lazy action loading | **0 ms** — the tool list is needed to build the prompt at launch, so the work has to happen anyway | us | `bench_startup.py` |
| Compiling the hot leaf with mypyc/Cython | 1.5–4× on that leaf, which is 0.005 % of a frame | us | not worth it yet |
| Rewriting the shell in Go or Rust | **0.165 ms** | — | this document |

The honest ranking is: everything that matters is outside the language. Of the two
levers that were ours, the warm connection is **done and measured**, and the prompt
is **measured and guarded** — trimming it is a behaviour change, and behaviour
changes here need the live harness, not a benchmark.


## 10. If most of this were Rust

A fair question, and the answer is measurable rather than a matter of taste.

**What a rewrite would gain.** Python's share of one turn is **0.165 ms**. Against
600–4,000 ms of model time that is 0.004 %–0.03 %. Rust is roughly 10–50× faster on
the kind of code here, so the Python share would fall to something like 0.02 ms —
about **0.145 ms saved**, which changes no measurement a person can feel.

**What it would cost.** 85,674 lines and 1,388 tests would be rewritten. The
interface would have to leave Qt, because the HUD, the avatar and the settings panel
are Qt widgets and painting; there is no Rust toolkit that gives the MARK look
without being a different product. Every provider (ElevenLabs, Whisper, Gemini,
OpenAI-compatible, Ollama, Piper) would become a hand-written HTTP client instead of
a maintained SDK, which is the opposite of "any provider, switchable by voice".

**Where a systems language does win, with numbers.**

| Work | Measured as Python | At C speed (numpy as the stand-in) | Worth it? |
|---|---|---|---|
| top-5 recall over 2,000 vectors × 384 dims | **55.3 ms per query** | **0.14 ms** (404×) | yes, when the store is that big |
| one video frame's encoding (`native/frame.c`) | 53.9 µs | 1.5 µs (36×) | already done in C |
| the sidecar (Go) | — | 3 ms start, 2.0 MB RSS | already done in Go |
| the turn itself | 0.165 ms | ~0.02 ms | no |

So the honest split is the one this project already follows: orchestration, provider
adapters and the interface stay Python because that is where the ecosystem is; the
few pure number-crunching loops that are measurably slow move out one at a time,
behind a stable interface, with a before-and-after measurement. The first candidate
is not the turn — it is **memory recall at 55 ms**, which is the only figure in this
document a person can actually feel.

## 8. The budget is enforced

`tests/test_performance_budget.py` holds four ceilings, each at least twenty times
the measured value:

    policy over every tool     < 5 ms   (measured 0.009)
    describe every tool        < 5 ms   (measured 0.028)
    render the system prompt   < 5 ms   (measured 0.054)
    memory read                < 5 ms   (measured 0.012)

A ceiling that loose cannot catch a 20 % regression, and is not meant to. It
catches the mistake that actually happens: a config file read on every turn, a
regex compiled inside a loop, a JSON parse per tool. Two further tests assert the
structural version of the same rule — the policy tables are module constants, and
the transcript pattern is compiled once.

## 9. Reproduce it

```powershell
python scripts\profile_turn.py    # the 0.165 ms table
python scripts\bench_startup.py   # the launch
python scripts\bench_hybrid.py    # the audio leaf
python scripts\bench_sidecar.py   # the Go supervisor
python scripts\bench_connection.py # connections opened: per call vs pooled
```
