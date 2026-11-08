# Ultron changing its own code

Ultron can now change its own source file, and it does it in the open: five stages, a rehearsal in a copy, two confirmations from two places, and the bytes it replaced are always kept.

## The plain version

Say what is wrong. Ultron stages a change. You watch it try the change in a copy of itself. Then you say yes twice. Then it applies — and if it breaks, one word puts it back.

| You say | Stage | What has actually happened |
|---|---|---|
| "Change that so it stops printing twice." | **propose** | A diff is written down. **Your program is untouched.** |
| "Try it." | **rehearse** | The change runs in a temporary copy of the whole project, with the compiler or the 1,500-test suite. Your program is still untouched. |
| "Yes." then a click in the panel | **confirm** | Two yeses, from two different places |
| "Apply it." | **apply** | The file is written in one atomic step, the old bytes are saved, the ledger gets a line |
| "Put that back." | **revert** | The exact bytes from before are restored |

## Why a copy is the whole idea

A rehearsal that runs in your folder is not a rehearsal — it is the change with extra steps. So the trial runs in a **temporary copy of the tree**: the same files, in a scratch folder, thrown away afterwards.

A draft that does not compile fails there. A draft that breaks a test fails there. Your program never knows either of them happened.

## The referee is off limits

These files decide *whether* a change is allowed, or record *that* it happened:

```
core/policy.py          what needs your approval
core/confirm.py         the confirmation gate itself
core/self_change.py     this pipeline
scripts/proof_gate.py   the harness that judges the claims
config/api_keys.json    your keys and settings
```

The refusal is code, not advice. Ultron cannot propose a change to any of them, so the change never reaches rehearsal.

**A system that can rewrite its own referee has no referee.** That is the exact failure the films this assistant borrows from are about — and giving it real power everywhere *except* here is the difference between a tool that evolves and a tool that unshackles.

## The honest limit: a restart

Python cannot replace a method inside a living object. Anyone who says otherwise is describing a development server that restarts.

A change to core/application code is **on disk but not running** until the process starts again. The action/plugin leaves have a narrower path: after the current session ends, the generation manager stages and validates them at the next provider reconnect boundary. They are never reloaded in the middle of a tool call. The self-change action says which case applies; a restart remains available for immediate activation.

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

The **session survives** the restart, because the session lives in files — memory, the ledger, the workspace. Data changes (a `.md` file, a JSON file) need no restart at all, and Ultron says that too.

## What it cannot do, by design

| Not allowed | Why |
|---|---|
| Edit `core/policy.py` or `core/confirm.py` | That is the referee |
| Edit `scripts/proof_gate.py` | That is the judge |
| Write outside the project | A self-change tool that can reach `C:\Windows` is not a self-change tool |
| Write into `.git` | History is not a scratch pad |
| Skip the rehearsal | An unrehearsed change is a guess, and guesses are what this pipeline exists to remove |
| Apply on one confirmation | One yes can be a reflex. Two places mean it was read twice |
| Change more than 400,000 characters at once | That is a database, not a source file |

## Where it lives

| File | What it holds |
|---|---|
| `core/self_change.py` | the five stages, the referee list, the ledger, the restart marker |
| `actions/self_change.py` | the tool the model calls: propose, rehearse, confirm, apply, revert, pending, history, rules |
| `tests/test_self_change.py` | 37 tests, run against a fake four-file project |
| `config/self_change/` | proposals, the ledger, and the kept copies of what each change replaced |

## The one question to ask of any change

**Would I still ship this if the owner were watching?** Every stage is written so that the answer is visible: the diff, the rehearsal output, the two confirmations, the ledger line. If a step cannot be shown, it does not happen.
