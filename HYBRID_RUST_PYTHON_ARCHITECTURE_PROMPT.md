# Architecture Design Prompt: Hybrid Rust + Python Desktop AI Operating Layer (ULTRON)

> **Instructions for the User:**  
> Copy the prompt block below and paste it directly into Claude 3.5 Sonnet, GPT-4o, o1, or another advanced AI architecture model.

---

```markdown
You are a Principal Systems Architect and Staff Systems Engineer with deep expertise in high-performance native desktop systems (Rust, Windows APIs, WASAPI, tokio) and AI Agent frameworks (Python, AsyncIO, LLM streaming, dynamic plugins).

I am planning an architectural modernization for **ULTRON**, an open-source, voice-first autonomous desktop agent and AGI-like JARVIS assistant running natively on Windows.

### Current Python Architecture & Pain Points
1. **Tech Stack:** Python 3.11, PyQt6 (main thread HUD & animation), PyAudio / sounddevice, AsyncIO streaming loops for Gemini Live WebSocket / OpenAI / Anthropic APIs, native win32 ctypes/comtypes, and dynamic plugins.
2. **Current Limitations:**
   - **GIL & Thread Contention:** Background agent tasks (file parsing, AST evaluation, tool execution) and audio I/O compete with the Python Global Interpreter Lock (GIL), risking micro-stutters in real-time audio and the 60 FPS PyQt HUD.
   - **Resource Footprint:** Python runtime + Qt6 idle memory footprint sits around 300MB–500MB with slow cold-boot times.
   - **Native Windows Interop Overhead:** Heavy use of ctypes/comtypes for Window management, OCR, and low-level screen capture/WASAPI audio buffers.
3. **What MUST Be Preserved:**
   - **Rapid AI Tooling & Plugin Velocity:** Python's unmatched ecosystem for AI tools, local LLM integrations, dynamic plugins, and self-change/self-healing capabilities (`core/self_change.py` hot code reloading).
   - **Extensibility:** Users and contributors must still be able to write simple Python tools/plugins without needing a Rust toolchain.

---

### Your Objective
Design the ultimate **Production-Grade Hybrid Rust + Python Architecture** for this desktop AI operating layer.

Provide a comprehensive, modular system design addressing:

#### 1. System Boundary & IPC / FFI Strategy
- What should be in **Rust** vs. what stays in **Python**?
  - *Candidate Rust domains:* Real-time audio capture & playback (WASAPI / CPAL), local wake-word engine (ONNX / OpenWakeWord / Rust bindings), screen capture / OCR, Windows OS automation (winapi/windows-rs), process lifecycle manager, local socket/IPC bridge.
  - *Candidate Python domains:* LLM conversation routing, prompt construction, dynamic tool execution, memory/RAG, plugin sandbox, self-change rehearsal logic.
- Compare IPC/FFI integration patterns:
  - **Option A:** Embedded Python inside a Rust binary (`pyo3` / `inline-python`)
  - **Option B:** Rust compiled as native C-ABI extension modules / PyO3 cdylib loaded into Python
  - **Option C:** Dual-Process Architecture (Rust core daemon/host + Python worker process over local IPC: Named Pipes / Domain Sockets / Shared Memory / gRPC / FlatBuffers)
  - Recommend the best pattern for stability, zero-crash fault isolation, and developer experience.

#### 2. Real-Time Audio & Streaming Pipeline
- Detail how bidirectional streaming audio (mic input -> VAD -> WebSocket streaming -> TTS audio playback -> echo cancellation/ducking) should flow between the Rust audio engine and the Python agent with sub-200ms latency.
- How to achieve zero-copy or minimal-overhead audio buffer sharing between the native sound layer and Python.

#### 3. Native UI & Display Layer
- Evaluate replacing or keeping PyQt6:
  - Rust native UI (e.g., Slint, egui, Tauri v2, or WinUI via windows-rs) vs. keeping PyQt6 with Rust backend.
  - How to achieve smooth 60–120 FPS holographic HUD animations without blocking audio or agent turns.

#### 4. Hot-Reloading & Plugin Safety
- How the hybrid architecture preserves Ultron's dynamic plugin capabilities and 5-stage self-change (propose, rehearse in isolated copy, verify, confirm, apply) without requiring user re-compilation of Rust binaries.

#### 5. Step-by-Step Migration Roadmap
- A phased, non-breaking roadmap to transition from the current monolithic Python repository into this hybrid model without halting current product development.
- Key crates, libraries, and design patterns recommended for the Rust core.

Be concrete, provide architecture diagrams (ASCII or Mermaid), define exact data structures/message protocols where relevant, and justify every trade-off with performance and maintainability metrics.
```
