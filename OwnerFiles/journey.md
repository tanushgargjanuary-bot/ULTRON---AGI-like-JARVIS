# The journey

The build history of Ultron, in plain language, newest first. It is written from
the build record (`log.txt`, `HANDOFF.md`), so every entry has an artifact behind
it. It is not a marketing page: the defects are in here too, including the ones
the assistant caused.

## Where this started

Ultron is built on **FatihMakes/Mark-LVI**, an open-source voice assistant with a
HUD, a model-provider system and a plugin architecture, licensed CC BY-NC 4.0.
The starting point was not "write an assistant". It was "take a working assistant
and make it worth trusting" — with a rule that has not changed since the first
session: **a claim needs evidence, and an unverified claim must say so.**

That single rule explains almost every decision in this repository. The proof
gate exists because of it. The Wilson lower bound exists because 3 of 3 is not
100%. The `decisions` layer can refuse because "do nothing" is sometimes the
honest answer. The word "verified" is only used where something was read back.

## 2026-11-06 — sixteen builds in one day

The owner worked in long sessions and asked for a lot at once. The order below is
the order the work happened.

1. **1.2.4 – 1.2.8: making the assistant honest.** Credential stores refused by
   name and extension. A turn can no longer stay open for ever. The interface
   size became adjustable from 85% to 250%, with keyboard control, because the
   owner could not read it. First run accepts any provider, because hardcoding
   one was never allowed.

2. **1.2.9 – 1.2.11: instruments instead of opinions.** `scripts/verify_all.py`
   answers "does this machine actually do it" for Windows, display, capture,
   audio and browser. `scripts/proof_gate.py` proves a claim as a **chain of
   steps** and reports `NOT PRESENT` where there is no code. Memory writes began
   parking behind the HUD confirmation instead of persisting silently. A daily
   digest was built so that it **cannot act** — proven inert, not merely
   restrained.

3. **1.2.12: five external tools, honestly integrated.** REA, HyperFrames,
   Hindsight, VoiceStudio and Hypit became **bridges**, not vendored code: the
   assistant knows the name, probes whether the tool is really here, and says in
   one sentence what is missing. A tool list that reads its own sources
   (`core/tool_catalog.py`) arrived with it.

4. **1.2.13: four defects, all from using the last build.** A promised WhatsApp
   driver that did not exist. A regex that froze the window for ninety seconds.
   A UUID described as "base64, 27 bytes". No CI. All four fixed, and the
   repository became able to prove it.

5. **1.2.14: meta-cognition and meta-learning.** A ledger of the assistant's own
   claims: confidence stated, outcome recorded, and an honest **lower bound**
   where a raw ratio would flatter it. Lessons that must carry a rule. Thirteen
   new skills, and a document — `docs/SKILLS.md` — that says which skills should
   exist next and which must never exist.

6. **1.2.15: the decision layer.** Expected value, and the refusal that makes it
   a decision system. UCB1 for strategy choice, BM25 for recall, a z-score pace
   monitor. Two bugs of the assistant's own were caught by its own tests, which
   is the system working.

7. **1.2.16: native platforms and self-extension.** GitHub, Hacker News, Stack
   Overflow, PyPI and npm, all read-only and cached. Skill **packs**, so Ultron
   can add a skill to itself as data without gaining the ability to write code.
   A reminder queue where silence is a valid answer. `ARCHITECTURE.md`, a
   document index, and a module map generated from the code.

8. **1.2.17: it can hand its own work back.** Shipping and self-updating are the
   same discipline in two directions: check before you publish, check after you
   pull, and put it back if it does not hold. The interesting part is not the git
   commands. It is the ordering — the secret scan runs before the commit exists,
   so the leak is never in history, and the verify runs before the restart, so the
   version on disk is always one that starts.

## 2026-11-06 and 07 — from 1.2.18 to 1.2.36

The rest of the run, in order. Each line is a build with a `log.txt` entry and a
commit behind it.

9. **The honest front page (1.2.19).** The readme was audited line by line and
   rebuilt: a link to a folder that was not in the repository, and a claim about a
   feature nobody had run, both removed. The page stopped describing the project
   and started reporting it.

10. **Supervision without a console (1.2.20 and 1.2.22).** Background supervision
    that is read-only, and the first compiled component: a small Go supervisor that
    survives a crash and does not flash a window. Go because it builds on both
    machines with no toolchain argument, and Rust only once a measured hot leaf
    exists. Its first bug was a missing execute bit, hidden perfectly by the Python
    fallback working.

11. **Measured change (1.2.21, 1.2.23, 1.2.24, 1.2.25).** A safe change became a
    measured change. A profile of one turn showed Python at **0.165 ms** against
    600 to 4,000 ms of model, which answered "why is it still Python" with a number
    instead of an argument. Two levers were then closed honestly: a warm connection
    pool (6.8 ms to 0.56 ms per request) and a prompt that was measured, not cut —
    and the benchmark that first said pooling was *slower* was itself wrong.

12. **CI on both machines (1.2.26).** The one structural gate — "nothing has ever
    run on Windows automatically" — stopped being a gate. The workflow runs the
    suite, the machine verifier and the proof gate on `ubuntu-latest` and
    `windows-latest`, and it found bugs on the first night that Linux could not see:
    a workflow flag no script declared, a report folder missing on a fresh clone,
    three instruments calling a missing device a broken product, and a claim whose
    code called a method that was never written.

13. **An installer, and a prompt he can read (1.2.27, 1.2.28).** One path to install,
    no administrator password, and no second launcher. His instructions became a file
    he can open, edit on instruction, and put back — with a validator, so a prompt
    that would be refused at runtime is refused at save time instead.

14. **A ceiling, and a philosophy (1.2.29, 1.2.30).** The folder is checked against
    100 MB and 5,000 files, because a save once silently dropped 6,352 files. And
    seven minds were added as **methods, not permissions** — the thinking of
    analytical characters, with no voice acting and no voice able to widen what the
    assistant may do.

15. **The syllabus as logic (1.2.31, 1.2.32).** He said it plainly: he did not want
    the syllabus stored, he wanted the topics *implemented as logic*. So 18 of 284
    topics now cite themselves from the code that runs them, and the citation is
    checked against the syllabus file, so a citation for code that is not there
    cannot pass.

16. **Every skill gets a reason (1.2.33).** Ten of 32 tools had lost the sentence that
    says when to call them, because the instruction cut each line at 150 characters.
    The condition goes first now, and every call is counted, so a feature that is
    declared and dead is a number he can ask for.

17. **A crash that leaves a record (1.2.34).** Four kinds of death, four hooks, and a
    report that holds the last thing the assistant was doing. Self-repair starts from
    that report instead of a hunch.

18. **It stopped blaming the API key (1.2.35).** Five plugins broke one rule of the
    provider's format, the provider refused the whole tool list, and the reconnect
    loop read the close code as "wrong key" — so he re-entered a key that was already
    right. Both faults fixed, and both guarded by tests and by the gate. This is the
    clearest example in the record of the pattern below: the program said something it
    had not checked.

19. **The pages a new agent needs (1.2.36).** `WORKING-PHILOSOPHY.md` and
    `OwnerFiles/for-the-next-agent.md`, plus every stale page corrected — including
    one that still said there was no CI.



## 2026-11-07 — the cloud can run out; the laptop should keep talking

The owner corrected a central assumption: Ollama is already on his PC, with LFM 2B and
Qwen 4B installed. The fallback therefore belongs on that laptop, not on an Oracle server.
The cloud ladder stays first. When Gemini reports quota and the ladder is exhausted, Ultron
checks Ollama's local model list, prefers the known small models, warms one, then moves the
conversation into the existing speech → model → speech pipeline. It does not alter saved
provider settings, download a model, or request administrator rights. If speech recognition
is not available, it says so; an LLM alone cannot hear a voice. The local path is slower than
Live, and the project record must keep that difference visible.

The same session made memory more temporal: a fact now has an exact update time, and an
edit records what it replaced in a bounded history under ignored `state/`. That gives a
future answer a trail instead of pretending the old fact never existed. A saved planner
checkpoint is offered at startup, but still waits for the owner's explicit request.

The after-action line was then added as its own small slice: `core/action_audit.py` reads
the existing policy tier and the tool's reported status. It does not authorize anything or
copy arguments/results into the HUD. Fallback is `59c6cfb`, memory recency is `5763c8d`, and
the audit is `dab95a7`; all are pushed on the arena branch. GitHub CI run `42459569545` passed
on Linux and Windows. The sandbox's own full run still has one Qt setup error because
`libGL.so.1` is absent; no live Ollama/Gemini/microphone was available to test the owner's
hardware path. The large self-evolution steps remain open: safe generation swaps,
supervisor/worker, test-carrying proposals, evolution-ledger integration, and OCR.

## 2026-11-08 — action and plugin leaves can stage a new generation

The first safe-reload slice is in the arena worktree, not yet committed. It fingerprints only
`actions/` and `plugins/`, builds candidate registries at a reconnect boundary, and keeps the
active registries and module table if an active tool disappears or a new discovery failure
appears. One preceding generation is retained for rollback. Fresh source loading also clears
stale bytecode, because same-second, same-size edits once loaded old code. It does not reload
the referee or change a running tool call. The updater now treats changed action/plugin
leaves as waiting for that reconnect boundary; core/application Python still requests a
process restart.

The focused combined test run passed **134 tests**, and the deep scan returned **0 high
findings** (108 complex functions). The latest full run executed **1,714 tests**, skipped 15,
and stopped on one Qt setup error because this sandbox lacks `libGL.so.1`; no code-test
failures remained after updating the README's live counts and removing duplicated test
cleanup. This is not a separate worker process; it does not rehearse generated proposals
before approval, and the rollback is not yet an owner-facing control. No live UI session,
Windows run, or GitHub CI run has tested this worktree change. See `OwnerFiles/session-log.md`
for the exact scope and branch state.

## What has not changed

The shell is still Python. The referee is still off limits. Nothing is remembered
without his approval. And the rule from the first session is still the rule: **a claim
needs evidence, and an unverified claim must say so.**

## The pattern worth noticing

Almost every defect in this record has the same shape: **the program said
something it had not checked.** A driver that did not exist. A tally that called
three successes "100%". A tool that was never confined. A surface counted as
passing because it was never asked. The fixes differ; the failure does not. If
you are the next assistant, read a change twice with that question in mind: what
does this make the program say, and what proves it?

## What the owner asked for repeatedly

These are the instructions that shaped the build, in his words where possible:

- "Make sure there are no bugs in this. Work rigorously on fixing bugs."
- "Keep the code simple and optimised and to the best quality."
- "You should make a PROOF GATE."
- "I don't want to rely on hard-coded features — I want Ultron to be able to
  handle things like this itself."
- "Only remember what I approve."
- The assistant must not pretend. A push that did not happen is not a push.
