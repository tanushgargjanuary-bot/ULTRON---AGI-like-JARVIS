# Changelog

All notable changes to the ULTRON project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- **Native Rust Core Daemon (`native/ultron-core`)**: Phase 1 of high-performance hybrid architecture.
  - Inter-process communication over Windows Named Pipes (`\\.\pipe\ultron-ipc`) with 6-byte framing protocol (`0xA1` magic + channel byte + uint32 payload length).
  - Sub-microsecond shared memory circular audio ring buffer (`Local\UltronAudioRing`) for real-time PCM audio streaming.
  - Windows Job Object supervisor for worker lifecycle isolation and crash recovery.
- **Python Hybrid IPC Layer**: `core/ipc_client.py` and `core/audio_ring.py` for sub-millisecond bidirectional communication with the native daemon.
- **Enterprise Documentation Hierarchy**: Restructured legacy context stores into standard `docs/specifications/`, `docs/engineering/`, `docs/audits/`, and `docs/MAINTAINERS.md`.
- **Autonomous Self-Evolution Specification (`docs/specifications/AUTONOMOUS_EVOLUTION_SPEC.md`)**: Complete architectural specification for Blue/Green worker hot-swapping, out-of-process Rust watchdog with automated Git rollback, canary sandbox under Windows Job Objects, AST Guardian, and hardware-sealed referee integrity.

### Changed
- **Dynamic Vision Resolution (`core/routing_runtime.py`)**: Vision capability now reflects active conversation route dynamically instead of requiring all configured fallback routes to support vision.
- **Plugin Parameter Hardening (`core/plugin_loader.py`)**: Integrated defensive `_clean_parameters` and schema `_coerce_parameters` into plugin execution.
- **Self-Change Concurrency (`core/self_change.py`)**: Serialized all 5 lifecycle stages (`propose`, `rehearse`, `confirm`, `apply`, `revert`) under re-entrant mutex `_change_lock`. Added CI workflow protection (`.github/` added to `SKIP_DIRS`).
- **Plan Resumption (`custom_jarvis/planner.py`)**: Restores non-mutating inspection steps (`list_dir`, `execute_command`) cleanly without requiring artifact digests.
- **Self-Update Untracked Files (`custom_jarvis/selfupdate.py`)**: Ignored untracked files via `git status --porcelain -uno` so test scratch files do not block updates.

### Fixed
- **Memory Concurrency (`memory/memory_manager.py`)**: Thread-safe synchronization across `forget()`, `save_session_summary()`, and `pop_last_session()` with `_write_lock`.
- **MCP Client EOF Lockup (`custom_jarvis/mcp_client.py`)**: Resolved 120s thread freeze by setting pending events on subprocess disconnect.
- **Web Dashboard Key Truncation (`dashboard/static/login.html`)**: Corrected key truncation to 8 characters resolving 401 lockout.

---

## [1.2.36] - 2026-11-12

### Added
- Provider failover ladder and dynamic routing engine (`core/routing_runtime.py`).
- Fast offline test runner and gatekeeper verification workflows.
- Thread-safe UI signal architecture on PyQt6 HUD overlay.
- Dual-channel confirmation protocol for autonomous self-modification.

### Fixed
- Provider schema validation strictly enforcing Google API requirements.
- Memory corruption prevention on simultaneous read/write cycles.
