# ULTRON: Autonomous Self-Evolution, Live Code Editing & Self-Updating Architecture Prompt

> **Instructions for the AI:**  
> You are an elite Principal Systems Architect and Compilers/Runtime Engineer.  
> You are designing the **Production-Grade Autonomous Self-Evolution, Live Code-Editing, and Self-Updating Subsystem** for **ULTRON**, an advanced voice-first desktop AI assistant built on Windows using a hybrid Python + Rust architecture.
>
> Read the complete architectural brief, constraints, current implementation details, and failure modes below, and produce an exhaustive, production-grade architectural specification.

---

## 1. Project Background & System Context

ULTRON is a voice-first, multimodal desktop companion and autonomous agent.
- **Operating Environment:** Windows 10/11 x64, Python 3.11/3.12, native Rust companion daemon (`ultron-core.exe`), PyQt6 GUI HUD overlay.
- **Voice & Intelligence:** Real-time bidirectional streaming (Gemini Live API WebSocket + Fallback routing ladder to Claude/OpenAI/Ollama), WASAPI audio I/O, Silero VAD.
- **Autonomous Tool Execution:** 30+ built-in actions and dynamic plugins running on worker threads.
- **Core Philosophy:** Evidence-based execution. The assistant must never claim what it has not proven.

---

## 2. Current Implementation: What Works & How It Operates

ULTRON currently possesses three distinct, verified self-modification components:

### A. The 5-Stage Self-Change Engine (`core/self_change.py`)
1. **`propose(path, reason, diff/new_text)`**: Stages a proposed file modification into `config/self_change/proposals.json` with cryptographic SHA-256 pre-hashes. Refuses to touch **referee files** (`core/policy.py`, `core/confirm.py`, `core/self_change.py`, `scripts/proof_gate.py`, `config/api_keys.json`, and `.github/`).
2. **`rehearse(proposal_id)`**: Copies the repository into an isolated temporary directory (`tempfile.mkdtemp()`), applies the modification, and runs compilation/verification (`scripts/verify.py` or `compileall`) inside the copy. If the test harness fails, the proposal is marked failed and refused.
3. **`confirm(proposal_id, channel)`**: Requires **two independent confirmations across two different channels** (e.g. Channel 1: Voice command; Channel 2: GUI HUD button click or CLI) before any change is permitted to touch live disk.
4. **`apply(proposal_id)`**: Verifies the target file's current SHA-256 matches the expected pre-hash (preventing race overwrites), backs up the existing file to `config/self_change/backups/<id>.bak`, atomically writes the new content, logs the event to `ledger.jsonl`, and writes `restart-required.json` if a Python source file was modified.
5. **`revert(proposal_id)`**: Restores the pre-change backup bytes if regression occurs.

### B. Git Self-Update & Leaf Hot-Reloading (`custom_jarvis/selfupdate.py`)
- Runs `git fetch` and checks if `origin/main` is ahead.
- Executes `git pull --ff-only origin <branch>`.
- **Leaf Node Detection**: Distinguishes "leaf" files (`actions/*.py`, `plugins/*.py`) from "core" engine files (`core/*.py`, `main.py`).
  - If *only* leaf files changed, it queues them for dynamic hot-reloading at the next reconnect boundary (`importlib.reload`) without interrupting the running process or audio loop.
  - If *core* files changed, it marks `restart_required = True`.

### C. In-Memory Tool Parameter Self-Healing (`custom_jarvis/self_healing.py`)
- Monitors tool execution failures. When a tool repeatedly fails due to schema/formatting mismatches (e.g. whitespace in paths, missing units), `RepairLoop` synthesizes an adapter Python program (`def adapt(args): ...`).
- Validates the adapter against past test cases and wraps the active tool in-memory.

---

## 3. The Problem Statement: Why It Is Not Yet a "True Self-Evolving AGI"

While the existing system passes unit tests and protects the machine from unauthorized tampering, it faces five fundamental architectural barriers:

1. **The Python Dynamic State Barrier (Process Restart Requirement):**
   - Python cannot safely hot-reload core runtime code that contains running event loops (`asyncio`), persistent background threads (audio capture/playback), or instantiated PyQt6 C++ Qt widgets without causing dangling pointers or state corruption.
   - Any core improvement currently forces a full process termination and restart, dropping the user's active audio call and GUI window state.

2. **The "Human In The Loop" Bottleneck:**
   - The two-channel human confirmation requirement (`confirm()`) was engineered as a safety referee to stop runaway LLM hallucinations.
   - However, this means ULTRON **cannot autonomously self-evolve while the user is away** (e.g., overnight autonomous self-benchmarking, profiling, and iterative optimization).

3. **Shallow Verification in Rehearsal:**
   - Rehearsal currently checks `compileall` or offline test suites. It cannot simulate whether a modified audio buffer size introduces cracking/stuttering, whether a UI refactor causes PyQt6 threading violations (`QObject::setParent`), or whether an LLM prompt modification degrades voice turn-taking.

4. **Absence of Autonomous Experimentation & Rollback Watchdogs:**
   - There is no automated A/B testing or canary execution harness where candidate code runs in an isolated shadow sandbox against benchmark datasets before graduating to the production system.
   - If a self-change causes the app to crash immediately on boot after a restart, there is no external out-of-process supervisor to automatically revert git HEAD to the last known healthy state.

5. **Lack of Autonomous Goal-Driven Self-Improvement:**
   - The system reacts to errors or explicit user prompts, but lacks an autonomous background cognitive loop that:
     a) Analyzes system crash logs and performance bottlenecks.
     b) Formulates hypotheses and writes new capabilities or optimizations.
     c) Writes its own unit tests and benchmarks to prove the improvement.
     d) Safely deploys the verified changes.

---

## 4. Your Architectural Deliverables

Please provide a comprehensive, production-grade architectural specification that addresses these challenges:

### 1. Dual-Tier Process Architecture for Zero-Downtime Hot Swapping
- How the native Rust supervisor (`ultron-core.exe`) and Python worker (`ultron-agent`) should orchestrate zero-downtime hot swapping.
- Designing a **Blue/Green Process Swap**:
  - Worker A (Active) handles the live user voice conversation.
  - Worker B (Candidate) boots in the background with the proposed code changes, warms up LLM routes, connects to the Rust IPC pipe, passes state validation, and smoothly takes over audio streams with `< 5ms` transition jitter before Worker A terminates.
- State serialization protocol: How active conversational memory, pending tool context, and user settings transfer from Worker A to Worker B via shared memory or local IPC.

### 2. Autonomous Closed-Loop Self-Evolution Engine
- Architecture of a background **Evolutionary Engine (Meta-Cognitive Loop)** that can run autonomously without human intervention in an "Unsupervised / Nightly Evolution Mode":
  - **Telemetry & Bottleneck Discovery**: Profiling latency hotspots, tool failure rates, memory growth, and voice turn lag.
  - **Hypothesis & Mutation Generator**: How the LLM proposes surgical code edits and creates new plugins.
  - **Synthetic Test Generation**: The requirement that any proposed code change MUST be accompanied by auto-generated regression and fuzzing tests.
  - **Canary Sandbox Rehearsal**: Executing candidate code inside an isolated sub-process with mock audio and synthetic user interactions.

### 3. Out-of-Process Watchdog & Boot Recovery Protocol
- Implementation specification for the Rust daemon (`ultron-core`):
  - Crash detection and heartbeat pings (`\pipe\ultron-ipc`).
  - **Dead Man's Switch / Boot Loop Guard**: If a newly applied self-change causes the Python worker to crash within 30 seconds of booting 3 consecutive times, the Rust supervisor automatically triggers `git reset --hard` to the last verified release tag and restarts the worker.

### 4. Sandboxed Code Generation & Safety Invariants
- Enforcing non-negotiable boundaries:
  - Strict AST parsing and linting before rehearsal.
  - Preventing access to sensitive OS primitives or unauthorized network destinations during evolution.
  - Immutable Referee Rules: How to cryptographically seal the referee code (`core/policy.py`, `scripts/proof_gate.py`, and the Rust supervisor itself) so that no self-evolving agent can ever compromise its own safety boundaries.

### 5. Concrete Implementation Roadmap
- Break the design into actionable phases:
  - **Phase 1**: Out-of-process Rust watchdog with automated crash rollback.
  - **Phase 2**: Blue/Green worker hot-swapping over local Named Pipes.
  - **Phase 3**: Autonomous nightly benchmarking, test-driven mutation, and evaluation harness.

Provide concrete Rust and Python code signatures, data structures, and state machine diagrams.
