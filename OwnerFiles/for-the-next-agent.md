# For the next agent

You have been handed a working voice assistant and a long record of how it got here. This
page is the short version: what stands today, what is open, where the traps are, and the
first three things to run.

Read `OwnerFiles/README.md` next, then `WORKING-PHILOSOPHY.md` at the top of the
repository. Everything else is referenced from there.

---

## 1. What stands, today

| Item | State |
|---|---|
| Build | **1.2.36** (`packaging/version.txt`) |
| Repository | `github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS`, branch `main` |
| CI | `.github/workflows/verify.yml`, two jobs: `linux` and `windows`. Both green |
| Tests | 1,737 passed, 8 skipped, on Linux with the optional packages installed |
| Proof gate | 35 claims: 21 PROVEN, 14 PARTIAL, 0 FAILED on a Linux box without hardware, display or `libGL`; 22 / 13 where the Qt libraries are installed |
| Workspace | no size budget (withdrawn 2026-11-07 by the owner); generated files stay out of Git |
| Machine | Windows is the primary target; Linux is where the work is built |

The 13 open claims are open for a reason the gate prints: Windows-only, audio or display,
a real key, real hardware, one unclassified, and the owner's own voice. `GATEKEEPERS.md`
lists them. None of them can be closed from a Linux build machine.

## 2. What was finished most recently

- **1.2.33** every tool states when to call it, and every call is counted.
- **1.2.34** a crash writes a file, and self-repair starts from that file.
- **1.2.35** one malformed plugin field used to stop the session and blame the API key.
  Fixed, guarded, and proved.
- **1.2.36** the documents a new agent needs, brought up to date (this pass).

`log.txt` has the detail of each. `HANDOFF.md` has the phase record.

## 3. The first three things to run

```powershell
.\.venv\Scripts\Activate.ps1
python scripts\verify.py
python scripts\proof_gate.py
python scripts\verify_all.py
```

`verify.py` runs the suite, the stress scenarios, the mutations and the workspace budget.
`proof_gate.py` proves the claims. `verify_all.py` answers what **this** PC actually does -
display, capture, audio, browser, keys - and reports SKIP where a question does not apply.
Run all three on the owner's Windows machine before you claim anything works there.

## 4. Where the traps are

These are the mistakes that already happened here. They are cheap to avoid and expensive
to repeat.

1. **The tool list is a contract with a provider.** A `required` name that is not declared
   under `properties` makes Google refuse the whole list with `1007`, and the session never
   connects. `core/action_loader.py:sanitize_declarations()` repairs it and reports the
   repair; `tests/test_provider_schema.py` checks it. Do not remove either.
2. **A close code is not a diagnosis.** `1007` also means "bad model" and "bad schema".
   Read the words: `core/close_codes.py`.
3. **Never import `main.py` in a test.** It starts a GUI and installs crash hooks. Read its
   text instead: `tests/test_provider_schema.py` shows how.
4. **`main.py`, `actions/*.py` and `core/prompt.txt` are CRLF.** Read bytes or use
   `newline=""`. A text-mode rewrite changes every line.
5. **Windows keeps a handle open.** `crash.disarm()` before deleting a folder that held a
   report, or the delete fails with `WinError 32`.
6. **`core.crash` cannot be imported at module level by `core/self_change.py`.** It is a
   cycle; import inside the function.
7. **A `chmod(0o500)` folder is not a write barrier on Windows.** Use a file path instead.
8. **The proof gate refuses functions over about twenty branches.** Build a claim from
   small functions and a context manager.
9. **`git commit -m` with quotes breaks in the CI shell.** Write the message to a file and
   use `-F`. Two pushes in a row cancel the first run.
10. **The save after a message keeps about 128 MB and drops the rest.** Keep the workspace
    small; `docs/SPACE.md` explains the incident that taught this.

## 5. What the owner has asked for, and does not want repeated

His words, where they are short enough to quote directly:

- "Only remember what I approve." Nothing inferred is persisted silently.
- "I dont need voice of these fictional characters. Right now I just want the thinking to
  be like these characters - analytical, calculative and scientific."
- "I didn't want the syllabus as stored, but I wanted the topics implemented as logic of
  the ULTRON." Code, not notes.
- "Make sure there are no bugs in this. Work rigorously on fixing bugs."
- "Keep the code simple and optimised and to the best quality."
- "We should never overgo over 100MBs."
- Do not add launcher files. The installer reuses `run.ps1`.
- Give PowerShell syntax for anything he will type.
- A yes or no question gets Yes or No first, then the evidence.
- Plain words before any table. He has said this three times.

He **considered and abandoned** a rewrite. Do not propose one. The measurements are in
`docs/PERFORMANCE.md`: Python is under 0.2 ms of a turn whose wait is 600 to 4000 ms.

## 6. How decisions are protected

- `DECISIONS.md` - his decisions, with where each one is enforced. An entry wins over your
  change until he says otherwise, and then the entry is edited the same day.
- `core/policy.py` - the risk tier of every tool. A name missing from the table stays
  guarded: forgetting fails safe.
- `core/confirm.py` and `core/self_change.py` - two confirmations from two channels for any
  change to its own source, rehearsed in a copy first, always revertible.
- The referee (`core/policy.py`, `core/confirm.py`, `core/self_change.py`,
  `scripts/proof_gate.py`) cannot be edited by the assistant at all.

## 7. The tone of the record

This project writes its own history honestly, and the defects the assistant caused are in
it. `OwnerFiles/journey.md` is not a success story; it is a list of things the program said
that it had not checked, and what it cost. Keep writing it that way. If you fix something,
say what it was. If you could not reproduce something, say that too - there is already one
unreproduced Qt teardown segfault in the record, and it stays there on purpose.

## 8. If you are an AI continuing this work

Say what you did, not what you would like to have done. Run the instruments. Quote the
numbers the last run printed. Push in one commit per improvement, and read the Windows job
before you call the build green.

That is the whole of it. Everything else is in the files.
