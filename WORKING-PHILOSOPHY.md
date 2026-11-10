# How we work on Ultron

This is the working philosophy of this project, written for any agent (human or AI) that
picks it up. It is not a style guide and it is not marketing. It is the set of habits that
produced the code you are looking at, and the reasons for them, taken from the failures
that created each one.

`AGENTS.md` is the rule book: threading, plugins, hooks, the things that break. This page
is the thinking underneath it. Read this first, then `AGENTS.md`, then the owner's folder.

---

## 1. The one rule everything comes from

> **A claim needs evidence. A claim without evidence must say so.**

Every practice below is that rule applied to a different surface. The proof gate exists
because of it. The Wilson lower bound exists because three successes out of three is not
100 per cent. The word "verified" is only used where something was read back. A design
that cannot be checked is treated as unfinished, not as done.

The owner stated it in his own words more than once:

- "Make sure there are no bugs in this. Work rigorously on fixing bugs."
- "You should make a PROOF GATE."
- "No fabricated claims in the readme."

An agent that adopts only this rule and nothing else will still do good work here. An agent
that adopts everything else and drops this one will produce code that looks right and does
nothing, which is the failure this repository has spent a hundred builds removing.

---

## 2. How we talk to the owner

He is the reason the software exists, he reads everything, and he has flagged excessive
technicality three separate times. So:

- **Plain words come before any table.** Simplest sentence that is still true.
- **Simplified Technical English.** Short sentences. One instruction per sentence. Least
  technical term that is accurate. Highest understanding is the goal, not elegance.
- **A yes or no question gets "Yes." or "No." as the first word.** Then the evidence. Never
  bury the answer in paragraphs.
- **Say what did not work.** A defect you found is more valuable than a feature you added.
- **Do not overclaim performance.** Do not describe a run you did not do. A push that did
  not happen is not a push.
- **Do not answer a code-quality question with an external delay** such as "I will check
  later". Answer with the code, or with the measurement.
- **Do not interrupt him mid-sentence**, and do not ask about trivial things. He dislikes
  being asked to approve small actions. Ask when the answer changes what you build.

He wants the answer fast and then the detail. Give the conclusion in the first line.

---

## 3. How a change is made

The order is not negotiable, because each step has caught something the others missed.

1. **Understand the request in his terms.** If two readings lead to different code, ask.
2. **Read before writing.** The module you are about to change has a docstring that says
   why it is shaped that way. `docs/MAP.md` lists every module with its test.
3. **Make the smallest change that can be proved.** No rewrites. He considered one,
   abandoned it, and the answer stands: the shell is Python because every safety invariant
   lives there, and re-proving those in a new language is the slowest work in the repository.
4. **Write the test first or with it.** A change with no test is a claim with no evidence.
   Never weaken an assertion to make a build pass.
5. **Run the three instruments** (section 5). Red is a real defect, not noise.
6. **Update the record**: `log.txt` (what changed and why), `HANDOFF.md` (the phase),
   `docs/`, `AGENTS.md` if a rule appears, `OwnerFiles/` if the owner's intent moved.
7. **One commit per isolated improvement.** A commit that mixes unrelated changes
   cannot be reviewed or reverted safely.
8. **Use the correct CI lane.** Every branch push gets the fast offline gate. A pull
   request to `main` and every push to `main` get the full Linux/Windows regression
   gate. Read the results for the exact commit. See `docs/TEST_AUTOMATION.md`.

---

## 4. What is never allowed

Each of these has been broken once, and the cost is in `OwnerFiles/history/journey.md`.

| Never | Because |
|---|---|
| Weaken or delete a test assertion to pass a build | The assertion was the only thing between you and a false claim |
| Bypass `ControlledRegistry` or `EvidenceEngine` path confinement | It is the reason a tool cannot write outside his folders |
| Hardcode a provider, a model name or a feature list | He asked for a system that switches by voice and configures itself |
| Write to `config/api_keys.json` directly | It holds his keys; `memory/config_manager.py` owns it |
| Edit the referee: `core/policy.py`, `core/confirm.py`, `core/self_change.py`, `scripts/proof_gate.py` | A system that can rewrite its own referee has none |
| Add a launcher file | The installer reuses `run.ps1`; a second entry point is a second thing to break |
| Keep a promise in a docstring that has no file behind it | Three docstrings described a WhatsApp driver that did not exist |
| Enforce a workspace size/file-count ceiling | The owner withdrew the 100 MB / 5,000-file budget on 2026-11-07. Keep caches, build output, and machine state out of Git, but do not impose an arbitrary size limit. |
| Add a network call, a download or a model change without consent | The owner decides what leaves the machine |
| Report success from an exit code alone | Read the output, or it did not happen |

---

## 5. The three instruments, and what each one proves

| Instrument | Command | What it proves | What it cannot prove |
|---|---|---|---|
| Test suite | `python scripts/verify.py` | the code behaves as its tests describe, offline, no mocks where a real thing fits | anything needing hardware, a key, or Windows |
| Proof gate | `python scripts/proof_gate.py` | a **claim** as a chain of steps, ending in the effect it promised | a claim whose last step needs his microphone or his account |
| Machine verifier | `python scripts/verify_all.py` | what this actual PC does: display, capture, audio, browser, keys | other machines |

The proof gate has four verdicts, and the fourth is the useful one: `NOT PRESENT` means
there is no code behind the claim. That is a missing feature, not a broken one, and saying
so is the whole point.

`PARTIAL` is not a pass. Every open claim says **why** it is open, in categories the owner
can act on: Windows, audio or display, keys, hardware, unclassified. A bare number without
a reason is the kind of claim this project keeps deleting.

---

## 6. How we debug

The record is unambiguous: almost every defect in this project had the same shape. **The
program said something it had not checked.** A driver that did not exist. A tally that
called three successes "100 per cent". A tool that was never confined. A surface counted
as passing because it was never asked. A close code read as if it were a diagnosis.

So the method is:

1. **Read the message, not the code first.** The message names the fault more often than
   the stack trace does.
2. **Find the sentence that is now false.** "API key invalid", "sent", "verified",
   "available" - one of those became untrue. The fix is not finished until that sentence
   can no longer be produced.
3. **Make the failure loud and local.** A fault should cost the smallest thing it can. One
   bad plugin field must not cost the session; one bad plugin field must not pass silently
   either. Repair it and say you repaired it.
4. **Reproduce it as a test, using the real message.** The owner's own log line is a test
   fixture in `tests/test_provider_schema.py`.
5. **Write it down even when it is not fixed.** An unreproduced Qt segfault and a benchmark
   that was wrong in the other direction are both in the record. A defect that is only in
   someone's memory is rediscovered as a surprise.

Two more rules that came from specific failures:

- **A gate must never be able to make a claim false.** If a check can only be satisfied by
  weakening the thing it checks, the check is wrong.
- **Do not change behaviour to win milliseconds.** Measure first. Python is under one
  thousandth of a turn; the model is the wait.

---

## 7. Tools, plugins and the provider boundary

The model is told what it can do through declarations. Those declarations are a contract
with another company's server, and a mistake in one field is not a small mistake:

- A declaration may only mark a parameter `required` if it also declares it under
  `properties`. Google refuses **the whole tool list** for one such field and closes the
  session with `1007`. This is the bug that made Ultron blame the owner's API key for an
  evening. See `docs/CONNECTION.md`.
- A close code is not a diagnosis. Read the message: `core/close_codes.py` separates
  schema, key, quota, model and network, and only asks for a key when the words say key.
- `tests/test_provider_schema.py` and the `plugins` gate claim check every declaration from
  `actions/`, `plugins/` and `main.py`. Do not weaken them.
- A plugin returns a short string, never raises, returns quickly, and treats `player` as
  possibly `None`. A plugin that needs the screen must ask for consent like anything else.

---

## 8. The shape of the code

Six layers, one direction: the window talks to the session, the session talks to the model,
the model asks for tools, the tools pass a policy check, and everything that happened is
recorded. `ARCHITECTURE.md` has the diagram and one turn end to end.

Three habits keep that shape:

- **One place for a rule.** The risk tier of a tool lives in `core/policy.py`, not in the
  tool. The tool condition lives in the tool's own description, not in a second list. A
  second copy is a copy that will drift.
- **Data over code where the owner may disagree.** The syllabus is JSON. The philosophy is
  text. The prompt is a file he can read. If he might want to change it, it is not Python.
- **A feature that is never chosen looks exactly like a feature that is never needed.**
  Which is why every tool says when to call it, and every call is counted
  (`core/tool_usage.py`).

---

## 9. Before you push: the checklist

1. `python scripts/verify.py` - exit 0.
2. `python scripts/proof_gate.py` - no `FAILED`, and no claim worse than before.
3. Any new claim or capability has a gate step or a test, not just a paragraph.
4. `log.txt` has an entry. The version is bumped. `HANDOFF.md` names the phase.
5. The readme numbers are the numbers the last run printed, not remembered ones.
6. No size budget is checked any more (withdrawn 2026-11-07); keep generated files out
   of the tree, as `docs/SPACE.md` explains.
7. `git status` - no key, no token, no personal file, no stray log.
8. One commit, a message that says what changed and why.
9. Push, then read both CI jobs. Fix the Windows failure; do not explain it.

---

## 10. Where to read next

| Read | For |
|---|---|
| `OwnerFiles/README.md` | why the folder exists, and the one sentence that defines it |
| `OwnerFiles/ULTIMATE_Context.md` | what stands today, what is open, where the traps are |
| `OwnerFiles/history/journey.md` | the build history, defects included |
| `AGENTS.md` | the hard rules: threading, plugins, hooks, provider schemas |
| `DECISIONS.md` | what the owner decided, and where each decision is enforced |
| `GATEKEEPERS.md` | which claims have proof, which need his machine, and why |
| `ARCHITECTURE.md` | the six layers and one turn end to end |
| `docs/INDEX.md` | every document, one line each |

If you remember one thing from this page: **the program must not say something it has not
checked, and neither should you.**
