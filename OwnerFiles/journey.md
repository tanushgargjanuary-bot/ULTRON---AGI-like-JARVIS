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

## What the owner asked for repeatedly

These are the instructions that shaped the build, in his words where possible:

- "Make sure there are no bugs in this. Work rigorously on fixing bugs."
- "Keep the code simple and optimised and to the best quality."
- "You should make a PROOF GATE."
- "I don't want to rely on hard-coded features — I want Ultron to be able to
  handle things like this itself."
- "Only remember what I approve."
- The assistant must not pretend. A push that did not happen is not a push.

## The pattern worth noticing

Almost every defect in this record has the same shape: **the program said
something it had not checked.** A driver that did not exist. A tally that called
three successes "100%". A tool that was never confined. A surface counted as
passing because it was never asked. The fixes differ; the failure does not. If
you are the next assistant, read a change twice with that question in mind: what
does this make the program say, and what proves it?

8. **1.2.17: it can hand its own work back.** Shipping and self-updating are the
   same discipline in two directions: check before you publish, check after you
   pull, and put it back if it does not hold. The interesting part is not the git
   commands. It is the ordering — the secret scan runs before the commit exists,
   so the leak is never in history, and the verify runs before the restart, so the
   version on disk is always one that starts.
