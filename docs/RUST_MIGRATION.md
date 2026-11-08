# Selective Rust migration

## Direction

Use Rust selectively for **measured, isolated native leaves**. Do not rewrite Ultron wholesale. Python remains the control plane for the Qt HUD, provider/session orchestration, dynamic actions and plugins, policy/approval gates, and most I/O. Those areas are integration-heavy, and changing language does not make model or network waits faster.

Rust is a good candidate when profiling shows a deterministic CPU-bound component, a platform primitive that benefits from native packaging, or a long-running worker with a strong isolation boundary. A Rust port is not justified by language preference alone.

## Candidate policy

Before a port:

1. Record representative baseline timings and end-to-end impact with the existing profiling/benchmark scripts. Include realistic inputs, not only microbenchmarks.
2. Define the Python implementation as the behavior reference and write contract, edge-case, and property/fuzz tests.
3. Require a meaningful user-visible gain (latency, memory, startup, or reliability) after accounting for FFI and packaging costs.
4. Keep the Python implementation available as a fallback until the Rust build is present and passes parity tests.
5. Run the same tests on supported Windows and Linux targets, and exercise install/uninstall and missing-binary behavior.
6. Keep OS permissions and approvals in Python. Native code must not gain broader file, process, network, or credential access than the feature needs.
7. Avoid `unsafe` by default. If it is necessary at an FFI boundary, isolate it, document the invariant, and test the boundary explicitly.

## Current candidates and non-candidates

- `native/frame.c` already demonstrates a narrow native leaf. Its benchmark shows the benefit depends on using the existing audio buffer without copying; do not port it just to replace C with Rust.
- `sidecar/watchd` is already a small Go supervisor. Do not create a second Rust watcher unless a measured requirement justifies replacing it.
- `core/fuzzy.py` is a possible profiling candidate because edit distance has a bounded dynamic-programming matrix. Its hard cell budget is a correctness/safety property and must remain in every implementation. No Rust port is approved until end-to-end profiling shows it matters.
- `ui.py`, provider clients, policy/confirm gates, `actions/web_read.py`, and the health ledger are not current Rust targets: they are mainly GUI, network, orchestration, or safety logic rather than measured CPU hot paths.

For a frequent small function, prefer a narrow Python extension (for example, PyO3 with a reproducible maturin build) only if packaging can be tested on every target. For a long-running background worker, a separate process with a versioned, bounded protocol may make more sense. Do not spawn a process for every tiny function call.

## Current status

This is a staged migration policy, not a claim that Rust code has been added. The current sandbox has no `rustc` or `cargo`, so Rust builds and cross-platform measurements were not performed. The next practical step is to profile representative Ultron turns and choose one isolated leaf only if the result justifies the additional toolchain and maintenance cost.
