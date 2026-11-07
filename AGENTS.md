# Rules for coding agents working on Ultron

The built-in coding agent (`actions/dev_agent.py`) reads this file before every
change it makes to this project, and so should any other agent or contributor.
Each rule below exists because breaking it produced code that looked right,
passed a syntax check and did nothing when used.

**Read [`WORKING-PHILOSOPHY.md`](WORKING-PHILOSOPHY.md) first.** It holds the one rule
this project runs on, how work is done, what is never allowed, and the checklist before a
push. This file is the rule book for the code; that page is the thinking underneath it.

## How the app runs

- `main.py` holds the voice session on an asyncio event loop in a background
  thread. `ui.py` holds the window on the **Qt main thread**.
- Tools — `actions/*.py` and `plugins/*.py` — run on **worker threads**, never
  on the Qt main thread.
- There is exactly **one** `QApplication`, created by `ui.py`.

## Threading: the rule that breaks most generated code

Code in `actions/` and `plugins/` must **never create or touch a Qt widget**.
That means no `QApplication`, `QWidget`, `QMainWindow`, `QDialog`, `QThread` or
anything else from `PyQt6.QtWidgets` or `PyQt6.QtGui`. Creating a widget from a
worker thread prints `QObject::setParent: Cannot set parent, new parent is in a
different thread` and nothing appears on screen.

To show something, call the **thread-safe methods on `player`** (the `JarvisUI`
object passed to every tool). They hand the work to the Qt thread for you. The
current list, with signatures, is appended below this file by the coding agent
automatically. The ones plugins usually need:

| Need | Call |
|---|---|
| A line in the activity log | `player.write_log("text")` |
| Text in the panel under the head | `player.show_content(title, text)` |
| A quiz the user answers on screen | `player.show_quiz(topic, questions, grade=None)` |
| A structured review | `player.show_review(title, summary, findings)` |
| Play a video in the HUD | `player.show_video(path_or_url, title)` |

`show_quiz` takes `questions` as a list of dicts:
`{"question": str, "options": [str, ...] (empty list for a typed answer),
"answer": str, "note": str (shown after answering, optional)}`.
`grade(question, given) -> True | False | None` is optional; `None` means
"let the assistant judge this answer". The user answers at their own pace and
the result comes back to the conversation by itself — `run()` returns at once.

Do **not** start a separate GUI program (`subprocess` running a PyQt script)
to work around this rule. It hides every error from the user, and the app
already has a screen for it.

## Plugins

A plugin is one file `plugins/<name>.py` (no leading underscore) with:

- `PLUGIN = {"name": ..., "description": ..., "parameters": {"type": "OBJECT", ...}}`
- `def run(parameters: dict, player=None, session_memory=None) -> str`

`run()` must:

- return a **short string** — the assistant turns it into speech;
- **never raise** — catch errors and return a sentence saying what went wrong;
- return **within a few seconds** — put slow work on a `threading.Thread`
  and show its result through `player` when it is done;
- treat `player` as possibly `None` (tests and the phone dashboard).

Helper modules may live beside it with a leading underscore
(`plugins/_helper.py`); the loader skips those. See `plugins/_template.py`.

A new plugin is **enabled automatically** the moment its file exists — nothing
needs to be registered or switched on. Never edit `config/api_keys.json` to
"enable" one; that file holds the user's API keys and settings.

## Asking a model for something

Always go through `core.gemini` — it has deadlines, a fallback ladder and the
user's chosen provider:

```python
from core import gemini
text = gemini.text(prompt, tier=gemini.FAST)       # short answers
data = gemini.as_json(prompt, tier=gemini.SMART)    # structured, may return None
```

Every call can fail or return `None`. Code must handle that — for example with
a small built-in fallback — instead of crashing.

## Changing the window (`ui.py`)

- Widgets are created and changed only on the Qt thread.
- To let other threads trigger a change: add a `pyqtSignal` to `MainWindow`,
  connect it to a slot in `__init__`, and add a thin public method on
  `JarvisUI` that only emits the signal. `show_content` / `_content_sig` /
  `_show_content` is the pattern to copy.
- Colours come from the `C` palette class; fonts are `QFont("Courier New", size)`.

## General

- Never send a child process's output to `DEVNULL` without logging it, and
  never report success without checking that the thing actually happened.
- Settings and keys live in `config/api_keys.json` through
  `memory/config_manager.py`; never write that file directly.
- Keep to the libraries already in `requirements.txt`.
- **A change to its own source goes through `core/self_change.py`, in five stages, or
  it does not go.** Propose, rehearse in a copy, two confirmations from two channels,
  apply, revert. Never write `core/policy.py`, `core/confirm.py`, `core/self_change.py`,
  `scripts/proof_gate.py` or the settings file — those are the referee. Never add a
  shortcut around a rehearsal, and never say a `.py` change is running before the
  process has restarted.
- **Syllabus topics live in `curriculum/*.json`, not in Python.** A university fact
  belongs in a file the owner can read and correct. Every subject says where its
  syllabus came from, and a reading link is written down only after it has been
  opened.
- **A syllabus topic that Ultron can do cites its unit, in the code that does it.**
  `@implements("DAA", 4, "Branch and bound")` attaches the citation to the function;
  `core/mental/registry.py` checks it against the syllabus file. Never write a citation
  for code that is not there, never cite a topic the unit does not contain, and never
  let the decorator change behaviour. The course is meant to run in the assistant, not
  sit on a shelf.
- **A crash must leave a record, and a repair must start from it.** `core/crash.py` is
  installed at the top of `main.py`, before anything that can fail. Never remove that
  call, never let a report keep a credential, never delete the reports on the owner's
  behalf, and never let self-change propose a fix without the crashes it is working
  from. `logs/` is the owner's machine and is git-ignored on purpose.
- **Every tool must say when to call it, and its calls are counted.** The condition is
  the sentence in the tool's own description that starts with a cue such as "Use it
  when"; `core/tool_prompt.py` puts it at the front of the line the model reads, because
  the line is capped and whatever comes last is what gets cut. Never add a tool with no
  condition, never keep a second copy of a description, and never remove
  `tool_usage.note(name)` from the call path: without it a feature that is never chosen
  looks exactly like a feature that is never needed.
- **A mind in `core/philosophy.py` is text, and it states its bound.** Every voice
  arrives with a maxim, a stance and a limit it may never cross; the limit is rendered
  into the instruction with the maxim. Never give a voice a code path, never let one
  add a permission, and never remove the ceiling on the adversary voice (40%) without
  the owner saying so in his own words.
- **Repository and workspace hygiene is maintained.** While the project is hosted
  on GitHub and no longer constrained by local ZIP limits, keep file hygiene clean:
  install packages with `--target` to a temporary folder or virtualenv, keep generated
  caches ignored, and verify clean workspace boundaries via `scripts/workspace_budget.py`.

## Token efficiency & agent skills (Mandatory for all coding agents)

All AI coding agents (Antigravity, OpenCode, Claude Code, Cursor, Copilot, Cline)
must read and enforce [`SKILLS.md`](SKILLS.md):

- **Caveman Mode**: Zero conversational filler, pleasantries, or preamble. Start directly
  with the answer, diff, or action. Retain 100% technical and typed precision.
- **ADHD Focus Mode**: Zero walls of text (max 2-3 sentences per block). Use bold keywords,
  clean visual hierarchy, and atomic task chunking (3-5 steps max) for instant 3-second scanability.
- **Diff Minimalist**: Never reprint untouched code. Use surgical replacements targeting only
  the modified lines.
- **Context Economy**: Never dump unbounded terminal logs into the conversation context;
  use shell-level filtering (`grep`, `Select-String`, `-Tail`). Offload heavy dumps to `scratch/`.
- **Cross-Branch Pair Review**: When reviewing between `antigravity` and `opencode`, provide
  dense, objective, invariant-based reviews without conversational padding.

## Read these first, in this order

1. `OwnerFiles/README.md` — why the repository exists and what it is for.
2. `ARCHITECTURE.md` — the six layers, where a change belongs, and every
   invariant with the test that enforces it.
3. `DECISIONS.md` — what the owner decided. If a change contradicts an entry,
   the entry wins until the owner says otherwise.
4. `GATEKEEPERS.md` — which claims already have proof, and which need his machine.
5. `docs/MAP.md` — every module, its purpose and its test. Generated; do not edit.

## The one question to ask of any change

**What does this make the program say, and what proves it?** Most of the defects
in this repository had the same shape: the program claimed something it had not
checked. If your change makes a new sentence appear — in a tool result, a status
line, a document, a commit message — add the check that makes it true, or make
the sentence weaker.

## A tool schema is validated by the provider, not by hope

- A declaration may only mark a parameter `required` if it also declares that parameter
  under `properties`. Google refuses the whole tool list — not the tool — with `1007`.
- Never test a close code alone. `1007` also covers a bad model name and a bad schema.
  Read the message: `core/close_codes.py`.
- `tests/test_provider_schema.py` and the `plugins` proof-gate claim check every
  declaration from `actions/`, `plugins/` and `main.py`. Do not weaken them.
