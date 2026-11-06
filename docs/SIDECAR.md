# The compiled part — `sidecar/watchd`

One component of Ultron is not Python. This document says which one, why, what it
measures, and what it is forbidden to do.

## Why any component at all

`docs/LANGUAGE_MATRIX.md` refuses a rewrite, and the refusal is measured: the
hottest leaf this program computes is 0.005 % of one audio frame, and a turn
waits 0.6–4 s on a model. A second language would buy nothing there.

But there is one job that **cannot live inside the assistant:**

> If the assistant crashes, a supervisor written inside the assistant dies with
> it.

That is not a speed argument, it is a structural one. The job is: watch the
programs the owner cares about, notice when one finishes, and keep the record
even if Ultron itself is restarting.

## Why Go, and not Rust

| Requirement | Go | Rust |
|---|---|---|
| One static binary, no runtime on the owner's machine | `go build`, done | `cargo build`, done |
| Windows cross-build from Linux | `GOOS=windows go build` | needs the target toolchain |
| Poll and supervise at the same time | goroutines, four lines | threads or async, more setup |
| Memory promises and a hot loop | adequate | better |
| Time to a first working version | hours | days |

This component is a poll loop and a child process. It needs neither a hot loop nor
fine-grained memory control, so Rust's advantages do not apply, and its setup cost
does. Rust stays on the LATER list for a leaf that is measured hot.

**Honesty note:** the Rust toolchain could not be installed on the build machine
that produced this file (no root, and a 300 MB download into a scratch directory
that is wiped), so nothing here would have been verified if Rust had been chosen.
An unverified rewrite is worse than no rewrite.

## What it measures

`python scripts/bench_sidecar.py`, this machine, median of fresh processes:

| | Go sidecar | Python watcher |
|---|---|---|
| size on disk | **2.0 MB** | an interpreter plus psutil |
| startup to first sweep | **3 ms** | 26 ms |
| resident memory | **2.7 MB** | 13.6 MB |
| event latency (200 ms poll) | **10 ms** | same poll, same table |

What these numbers do **not** say: that the sidecar computes anything faster. The
process sweep costs the same. It wins startup, footprint, and survival.

## What it does

```
watchd -watch antigravity,cursor -events memory/watch-events.jsonl -poll 2s
watchd -watch antigravity -supervise "python main.py" -restart
watchd -version
```

- **Watches** process names, by substring, case-insensitive.
- **Writes one JSON line** per finished job: `ts`, `pid`, `name`, `seconds`,
  `how`, `watch`. One line, flushed, so `tail` can read it.
- **Optionally supervises** one command with doubling backoff, reset after a clean
  minute. That is the only process it may start.
- **Never signals anything else.** No kill, no pause, no priority change, and the
  proof gate reads the source to keep it that way.

## Two limits it admits

- **Windows has no start stamp** for an unprivileged process. Identity there is the
  PID alone, so a reused PID on Windows is indistinguishable from a running
  process. The Linux build uses PID plus start time.
- **A process it did not start has no exit code.** Events say `"how": "ended"`,
  never "succeeded".

## Building it

Windows, from the repository root:

```powershell
.\sidecar\build.ps1
```

Linux or macOS:

```bash
./sidecar/build.sh
```

Both write `sidecar/bin/watchd-<platform>` and print the SHA-256. The binaries are
**not** committed: a build artifact in a repository is a file nobody can audit.
The source, the tests and the exact command are.

Run the Go tests:

```bash
cd sidecar
go test ./...
```

## What happens without it

Nothing breaks, and that is tested (`tests/test_sidecar.py`, and the proof gate
claim `sidecar`):

| Situation | Behaviour |
|---|---|
| No Go toolchain, no binary | `main.py` uses the in-process psutil watcher |
| Binary present | the sidecar is the source, so watching survives a crash |
| Binary dies mid-run | one log line names the switch, the Python watcher takes over |
| Binary writes a half line | the reader waits for the rest; nothing is announced early |
| Empty watch list | no sidecar is started at all |

The owner asked for supervision, not for a toolchain. That is why the compiled
part is an optimisation and never a requirement.
