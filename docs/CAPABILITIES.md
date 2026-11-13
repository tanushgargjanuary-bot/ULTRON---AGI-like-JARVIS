# What Ultron could natively do that it does not yet

Written 2026-11-06. Feature work is paused by decision; this page is a menu for later, not a plan. This is an answer to "what native capabilities can we give
Ultron", not a promise. Every row says what the capability is, what it would buy,
what it costs, and what it risks. Rows marked **built** exist in this tree today.

The organising idea: Windows is not a screen and a keyboard. It is a few hundred
interfaces, most of which have been stable for fifteen years, and most of which
this project has not touched. Everything below is an interface that ships with
the operating system — no model to download, no service to subscribe to, no
network, and nothing that needs a GPU.

---

## 1. Seeing and reading (the biggest untapped bundle)

| Capability | What it is | What it buys | Cost | Risk |
|---|---|---|---|---|
| **UI Automation** | The accessibility tree: roles, names, values, patterns | Acting on named controls instead of coordinates; no focus theft | **Built** (`core/ui_tree.py`, `core/ui_action.py`, `core/ui_windows.py`, `actions/ui_control.py`) — bridge unverified on Windows | Reads whatever is on screen |
| **Windows.Media.Ocr** | The OCR engine built into Windows 10/11, ~50 languages | Text from anything that has no tree: games, images, remote desktops, protected PDFs. Tens of milliseconds, no model download | Small wrapper over WinRT; needs the language pack already installed | A screenshot is still a screenshot — same consent |
| **UI Automation events** | Change notifications pushed by the OS when a window changes | Stop polling. "Tell me when the download finishes" becomes free instead of a loop of screenshots | Event subscription plumbing; must unsubscribe or the OS leaks | Low |
| **Windows Search index** | The property system behind Start-menu and Explorer search | Instant file/email/document lookup by name, author, date, content — including inside Outlook | Query via OLE DB or the `Search.Query` helper | Reads an index of the user's documents |
| **Windows.Media.SpeechRecognition** | On-device speech recogniser with grammar files | Offline wake words and command grammars without the cloud | Lower accuracy than Whisper; grammar work per command | Low |
| **SAPI voices** | Already used for TTS | Phoneme-level timing, bookmark events, SSML control | Already present | Low |

**The first two are the pair worth building.** OCR is the honest answer to "the
app has no accessibility tree" that costs nothing and downloads nothing, and it
sits exactly one rung above vision in `core/ui_ladder.py` — a local, offline,
deterministic replacement for sending a screenshot to a model.

---

## 2. Knowing what the machine is doing

| Capability | What it is | What it buys | Cost | Risk |
|---|---|---|---|---|
| **WMI / CIM** | `Win32_*` classes, `MSAcpi_ThermalZoneTemperature`, battery, disk, GPU | Real answers about the machine, not guesses: why it is slow, what is spinning the fan, what is on the network | Slow calls (100 ms+), must be off the UI thread | Low |
| **Process and app inventory** | The process table plus each program's own version metadata | "Minecraft 1.21.4 is open" instead of "a Java process", and a second copy is never started by accident. **Built** (`core/situation.py`, `actions/situation_report.py`, `background_status`) | One process pass at session start; versions cached by file time | Reads process names. Never window titles, documents or command lines |
| **ETW / `Get-Counter`** | Performance counters, per-process CPU/IO | "What is using my disk right now" answered precisely | Parsing counter names is fiddly | Low |
| **Power and session events** | Lock, unlock, sleep, resume, display off | Ultron stops talking when the screen locks, resumes the digest on unlock, knows why a task failed at 03:00 | Event subscription in `main.py` | Low, and it is privacy-positive |
| **FileSystemWatcher** | Change notifications for a folder | "Tell me when a file lands in Downloads" without polling | Handle lifetime; must not watch the whole drive | Low |
| **Shell COM** | `IShellItem`, jump lists, thumbnails, `IApplicationActivationManager` | Launch modern/UWP apps properly, read recent-document lists, attach to an existing app instead of starting a second copy | COM interop; the second-copy bug is exactly what `open_app` already fights | Low |
| **Toast notifications (WinRT)** | The real Windows notification API | Actionable notifications with buttons ("Undo", "Snooze", "Yes, delete it") instead of only the HUD banner | App identity registration | The confirmation via toast must NOT be trusted as the confirmation token — see `core/confirm.py` |
| **Media session (SMTC)** | Now-playing from any player, with transport controls | "Pause", "next", "what is this song" answered by the OS rather than by pretending to be a keyboard | Small wrapper | Low |

---

## 3. Doing (acting on the machine)

| Capability | What it is | What it buys | Cost | Risk |
|---|---|---|---|---|
| **`SendInput` with scan codes** | Keyboard/mouse at the driver level | Reliable input where `pyautogui`'s virtual keys get dropped by games and remote sessions | ctypes, ~80 lines | It can type anything anywhere — same gate as today |
| **Job Objects + AppContainer** | Already the agreed isolation design | Running a sub-agent's app with no network, no file access beyond its folder | Sandbox profiling per app; some apps refuse to run inside | Approved design, unbuilt |
| **Task Scheduler COM** | Native scheduled tasks | Reminders and digests that survive a reboot without Ultron running | Splitting behaviour between two schedulers | Duplicate scheduling if both fire |
| **Printing / PDF** | `Windows.Graphics.Printing`, `Microsoft Print to PDF` | "Print this", "save as PDF" without a third-party driver | Low | Low |
| **DPAPI** | Per-user encryption of secrets at rest | API keys encrypted with the user's login rather than sitting in `api_keys.json` in clear text | Migration of existing keys | Losing the DPAPI blob means re-entering keys — must be reversible, with a backup |

---

## 4. Being reachable (the input side)

| Capability | What it is | What it buys | Cost | Risk |
|---|---|---|---|---|
| **Global hotkey registration** | Already present (`core/hotkey.py`) | Push-to-talk | Built | Low |
| **Named pipes / local sockets** | A local IPC endpoint | The HUD, the phone dashboard and a coding agent all talk to one assistant instead of three copies | Protocol design | Local impersonation — must check the pipe's owner SID |
| **Clipboard change events** | `AddClipboardFormatListener` | "Make this into a note" on whatever was just copied | Low | The clipboard is one of the most private surfaces on a machine |
| **Shell drag-and-drop / drop target** | Files dropped onto the avatar | Natural intake: drop a PDF, get a summary | Qt side only | Low |

---

## 5. What to build, in order, and why

1. **OCR rung** (`core/ui_ocr.py`, one rung above vision). It converts the biggest
   weakness of structure-first computer use — the app with no tree — into a local,
   offline fallback. No model, no upload, no consent dialog beyond the screenshot
   that a sensor action already requires.
2. **UI Automation events** so "wait for it to finish" stops being a polling loop.
3. **Power/session events** so the assistant is silent when the machine is locked.
   Cheap, and it removes a whole class of "why did it talk at 2am" reports.
4. **DPAPI** for the key file. This is the one security improvement that costs a
   day and removes a permanent embarrassment.
5. **Media session**, because "pause the music" currently goes through a fake key
   press that only works if the right window has focus.
6. **WMI**, for honest answers about why the machine is slow.
7. **Sandbox (Job Object)** — already agreed, still unbuilt, and the largest single
   piece of work on this page.

What is deliberately not on this list: anything that needs a downloaded model
(vision, local LLM) beyond what the user already approved; anything that phones
home; and anything that would let the assistant confirm its own actions — the
confirmation token stays issued by the UI, never by a tool.
