# Ultron changing its own code

Ultron can now change its own source file, and it does it in the open: five stages, a rehearsal in a copy, two confirmations from two places (the second is a button only you can press), and the bytes it replaced are always kept. If a change to its code stops it from starting, the next start puts the old file back.

## The plain version

Say what is wrong. Ultron stages a change. You watch it try the change in a copy of itself. Then you say yes, and press CONFIRM on a banner that lists every changed line. Then it applies — and if it breaks, one word puts it back, and if it breaks the start-up, the next start puts it back by itself.

| You say | Stage | What has actually happened |
|---|---|---|
| "Change that so it stops printing twice." | **propose** | A diff is written down. **Your program is untouched.** |
| "Try it." | **rehearse** | The action runs the full repository test harness in a temporary copy. There is no model-controlled compile-only shortcut. Your program is still untouched. |
| "Yes." | **confirm** | Your yes is recorded (the model reports that you said it; the program never hears the audio) and a CONFIRM banner goes up with every changed line. Pressing it records the second confirmation. See "What the two places are" below |
| "Apply it." | **apply** | The file is written in one atomic step, the old bytes are saved, the ledger gets a line |
| "Put that back." | **revert** | The exact bytes from before are restored |

## What the two places are, and what actually holds

Every call to the `self_modify` tool — propose, rehearse, confirm, apply, revert — is itself held
behind the approval banner on the HUD (`core/policy.py` lists it as a guarded tool, and
`tests/test_self_modify_gate.py` checks that it asks every time, for every action). That banner
shows the call's arguments, which is not the same as showing the change.

The two confirmations are now two different things:

1. **Your yes.** The model calls `confirm` and the program records "voice". This is the model's
   report that you said yes; nothing here hears the audio, so it is the weaker of the two.
2. **Your press.** The same `confirm` call puts a **CONFIRM banner** on the screen
   (`core/confirm.py`) that lists the file, the reason (only its first 200 characters, because the
   model writes it), what was run in the copy, and **every changed line**, written out
   (`core/display_text.py`), in a box that scrolls (`ui.py`). The second confirmation is recorded only when you press that
   button, and only if the staged change is still the one that was on the banner (a digest of the old
   and new text is checked at the press). The model's own call cannot record it: the tool takes no
   `channel` argument any more, and a `channel` a model sends is ignored
   (`tests/test_self_change.py`, `TheSecondConfirmationIsAPress`).

A change with more than 8,000 characters of difference is **refused**, before your yes is recorded
and before any button goes up, with a request for several smaller changes: a button for something
you cannot fairly read is not a confirmation. It is the same gate the system prompt has
(`docs/PROMPT.md`).

**What this does and does not stop.** It stops the three-call sequence that used to apply a change
with no person involved beyond the per-call banners (`propose`, `confirm voice`, `confirm panel`,
`apply`). It does not stop a program that can press a button for you. While a confirmation is waiting,
`core/custom_gate.py` now refuses every tool call that is not read-only, so the model's own click and
key-press tool (`computer_control`, which runs with no banner of its own) cannot press the button or
tab to it. That check has two gaps, both stated in the file: a call the model sends in the **same
message** as the call that raises the banner is dispatched before the banner exists, and anything that
does not come through that dispatcher is not covered. A change to `ui.py` or `main.py` (where the
banner is drawn and wired) is not blocked by the referee list; reading the banner when the change
touches them is the check. Nothing here has been run on Windows with the real window.

## Why a copy is the whole idea

A rehearsal that runs in your folder is not a rehearsal — it is the change with extra steps. So the trial runs in a **temporary copy of the tree**: the same files, in a scratch folder, thrown away afterwards.

A draft that does not compile fails there. A draft that breaks a test fails there. Your program never knows either of them happened. The full harness is a minimum gate, not a proof of correctness: model confidence or a second model's review cannot override a failure, missing verifier, or the separate two-channel approval. A green run still needs human scrutiny of the diff and the actual behavior.

What the copy holds: the source, your data files and the `.github` folder (a few kilobytes of workflow text that tests read; writes there are still refused). It leaves out `.git`, `.venv`, `node_modules`, `uploads` and the caches. It gets a repository of its own with one commit of what it holds, so the tests that ask git which files are ignored or tracked get the answer a clean checkout gives; no history is copied, and nothing is signed or pushed. Until this was done a full rehearsal of this very repository failed 9 tests and errored on 6 more, so the "full test harness passed in the copy" sentence could not be true of it. Measured in a Linux copy of this tree, `rehearse(full=True)` now passes (see the CHANGELOG for the run).

Two things the rehearsal cannot see: a fault that only appears when the program starts (an import that fails on Windows, a start-up path no test reaches) and anything that differs between the sandbox and your machine. The first has a net now (below).

**Important security limit:** the temporary folder is not an OS security sandbox. The rehearsal subprocess runs with the same user permissions as Ultron. Candidate code can still access other files that user can access and can use the network. The copy protects the active project files from direct rehearsal writes; it does not contain hostile code. Only rehearse code from a source you trust. Do not treat two apply confirmations as a sandbox. A real sandbox needs OS-enforced filesystem, process and network restrictions; that is not implemented here.

## The referee is off limits

These files decide *whether* a change is allowed, or record *that* it happened:

```
core/policy.py          what needs your approval
core/confirm.py         the confirmation gate itself
core/self_change.py     this pipeline
core/boot_guard.py      the net that puts a change back if it stops the program from starting
scripts/bootstrap.py    the launcher step that runs that net
run.bat, run.ps1        the two launchers that run the step
scripts/proof_gate.py   the harness that judges the claims
config/api_keys.json    your keys and settings
```

The refusal is code, not advice. Ultron cannot propose a change to any of them, so the change never reaches rehearsal. Ultron refuses any path that crosses a file symlink or directory junction, even when the target is an ordinary project file. It checks the resolved target against the referee list and stores the canonical project-relative path. Replacing a normal target with a symlink after approval also blocks apply and revert.

**A system that can rewrite its own referee has no referee.** That is the exact failure the films this assistant borrows from are about — and giving it real power everywhere *except* here is the difference between a tool that evolves and a tool that unshackles.

## The honest limit: a restart

Python cannot replace a method inside a living object. Anyone who says otherwise is describing a development server that restarts.

A change to core/application code is **on disk but not running** until the process starts again. The action/plugin leaves have a narrower path: after the current session ends, the generation manager stages and validates them at the next provider reconnect boundary. They are never reloaded in the middle of a tool call. The self-change action says which case applies; a restart remains available for immediate activation.

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

The **session survives** the restart, because the session lives in files — memory, the ledger, the workspace. Data changes (a `.md` file, a JSON file) need no restart at all, and Ultron says that too.

## When the new code will not start: the boot guard

The first real run of a changed `.py` file is the next start, on your machine, with nobody watching. A fault the rehearsal could not see used to leave Ultron unable to open, and the only way back was a person with a terminal. `core/boot_guard.py` closes that for starts made with `run.bat` or `run.ps1`:

1. **`apply`** writes down the file, the digest of the old text and the digest of the new text in a watch file (`boot-watch.json`, in the self-change folder) *before* it writes the code. If that cannot be written, the change is not made.
2. **The first start** after that (the launcher runs `scripts/bootstrap.py`, which runs the guard before anything else) marks the change as started and says so on the console.
3. **The window comes up**, and a timer starts. After 45 seconds, or when you close the window or say "shut down", the change is trusted and taken off the list. If the thread that runs the assistant dies, the start does **not** vouch for the change, however long the window stays open.
4. **The next start** finds a change that was started and never proved itself, and puts the old file back from the kept copy, writes `reverted` (by `boot guard`) in the ledger, removes the "restart required" note, and tells you on the console what it did and what it could not do.

So a bad change costs one failed start, not every start.

What it does not do, and says:

- It cannot tell the change from another cause. A start that fails because of a missing package or a full disk is treated the same, and the change is put back. The message says so. A second launch made while the first is still inside its first 45 seconds is read as the first having failed.
- `python main.py` skips `bootstrap.py`, so a change that stops *that* start from opening is not caught.
- "Healthy" means the process stayed up and the assistant's thread did not die. A change that starts fine and misbehaves later is for `revert`.
- It puts a file back only if the file is exactly what the change wrote (digest checked), the kept copy is exactly what was recorded, the path is not a referee file and does not cross a link, and the change id has the shape `propose` makes. A tampered watch file cannot aim it at another file.
- It imports nothing of the program, so a change that broke `core.failures` or `core.self_change` cannot break the guard with it. It is itself on the referee list.
- It has been run on Linux only, with real processes in a test (`tests/test_boot_guard.py`, `TheWholeStory`). Nobody has run it through `run.bat` or `run.ps1` on Windows.
- It is not `native/ultron-core/src/watchdog/boot_guard.rs`, a design in the Rust crate that is not part of what runs. The Python file is what runs.

A line ending is not a change: a file with Windows line ends stays all Windows after a change, and comes back byte for byte after a put-back (by hand or by the guard). A file that is not valid UTF-8 is refused at the door, because the program could not put back exactly what it had been given.

## What it cannot do, by design

| Not allowed | Why |
|---|---|
| Edit `core/policy.py`, `core/confirm.py`, `core/boot_guard.py`, `scripts/bootstrap.py`, `run.bat` or `run.ps1` | That is the referee, and the net under it |
| Use a path that crosses a symlink or junction | Symlink and junction paths are refused; the resolved target is checked against the referee list |
| Edit `scripts/proof_gate.py` | That is the judge |
| Write outside the project | A self-change tool that can reach `C:\Windows` is not a self-change tool |
| Write into `.git` | History is not a scratch pad |
| Skip the rehearsal or downgrade it to compile-only through the action | An unrehearsed or weakly checked change is a guess. The action always requests the full verification harness. |
| Apply on one confirmation | One yes can be a reflex. Two places mean it was read twice |
| Record the second confirmation itself | It is recorded only by pressing the button; a `channel` the model sends is ignored |
| Put up a button for a change you cannot read | More than 8,000 characters of difference is refused, not cut |
| Change more than 400,000 characters at once | That is a database, not a source file |

## Where it lives

| File | What it holds |
|---|---|
| `core/self_change.py` | the five stages, the referee list, the ledger, the restart marker, the rehearsal copy, the difference |
| `core/boot_guard.py` | the net that puts a change back if the start it ran in did not stay up |
| `core/display_text.py` | what the banner draws: written-out invisible characters, every changed line |
| `actions/self_change.py` | the tool the model calls: propose, rehearse, confirm (with the button), apply, revert, pending, history, rules |
| `core/custom_gate.py` | the dispatcher; refuses every call that is not read-only while a confirmation is waiting |
| `tests/test_self_change.py` | the five-stage gate, the button, the difference, the rehearsal copy, line endings |
| `tests/test_boot_guard.py` | the net, including a bad change played through two real starts |
| `tests/test_gate_holds_input.py` | the dispatcher while a confirmation waits |
| `config/self_change/` | proposals, the ledger, the kept copies of what each change replaced, and the boot-watch file. Ignored by git (it was not; `ship` runs `git add -A`) |

## The one question to ask of any change

**Would I still ship this if the owner were watching?** Every stage is written so that the answer is visible: the diff, the rehearsal output, the two confirmations, the ledger line. If a step cannot be shown, it does not happen.
