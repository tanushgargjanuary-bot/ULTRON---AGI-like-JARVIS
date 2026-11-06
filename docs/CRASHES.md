# When it falls over

Before this build, a crash left nothing. Ultron runs with its console hidden, so there
was no message. There was no crash handler in 93,000 lines. The list of small failures
it keeps lived in memory, so the process died and took the list with it.

What you saw was this: the window disappears.

## What happens now

Four kinds of death are caught, because they are four different ways to die:

| How it dies | What catches it |
|---|---|
| An error that reaches the top of the main thread | `sys.excepthook` |
| An error inside a worker thread | `threading.excepthook` |
| An error inside `__del__` or a dying generator | `sys.unraisablehook` |
| A native fault in a Qt or audio library | `faulthandler` |

Each one writes a small text file in `logs/`:

```
time: 2026-11-06 19:02:42
build: 1.2.34
kind: KeyError
where: main thread
message: 'missing'
traceback:
  File "main.py", line 1530, in _execute_tool_approved
  ...
what it was doing just before:
  audio_devices.open: OSError: no device
```

That last block matters most. It is the list of small failures that came before the big
one, which is usually where the real cause is.

## What is kept out of it

Anything shaped like a key. A report can hold the arguments of the call that died, and
an argument can be a credential. The patterns are removed before the file is written.

The reports are in `logs/`, which the repository ignores. They are yours.

## The next run

If the last run died, the next one says so once, in the activity log:

> I crashed on 2026-11-06 19:02 — KeyError at main thread. Say "why did you crash" to see it.

Ask that, and Ultron reads the report. Not its memory of the report: the file. Add
"with the traceback", and it shows the part that names the fault.

## Why self-evolution needs this

Changing your own code from a hunch is guessing. The crash reports are evidence:

- **A proposal carries them.** Every change staged by `self_modify` records the crashes
  that were known when it was proposed, in the ledger entry. Months later, "why was
  this changed" has an answer that is a fact.
- **A repair starts there.** The tool has an action, `crashes`, that reads the newest
  reports so a fix can begin at the fault instead of at the symptom.
- **Older crashes are not forgotten.** The last 20 reports are kept. A fault that comes
  back next week is recognised, not rediscovered.

## The limits, stated plainly

- It cannot catch a native fault that kills the process before `faulthandler` can flush.
  That case leaves the `faulthandler.log` file or nothing at all.
- It keeps the last 20 reports. The oldest is deleted when the twenty-first arrives.
- A hard power loss leaves nothing. Nothing can prevent that.
