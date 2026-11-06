# Session log

Short, dated, newest last. One entry per working session: what was asked, what
was built, and what is left. The owner can append to this file; so can any
assistant, in the same shape.

---

## 2026-11-06 — sessions 1–16 (builds 1.2.4 → 1.2.16)

**Asked for.** A production-quality assistant built on MARK-LVI: fix bugs
rigorously, keep the code simple and optimised, prove claims with a proof gate,
and add capabilities that make it a serious agent. Then, in order: many skills
with meta-learning and meta-cognition as the centrepiece; a decision system;
algorithms that actually pay; native GitHub and other technical platforms; the
ability to add features to itself; and a repository organised well enough for
another AI to continue the work.

**Built.** Seven builds, all in one day (see `journey.md` for the list). The
short version: honest error reporting, instruments that ask the machine itself,
five bridged external tools, a metacognitive ledger with an honest lower bound,
an expected-value decision layer that can refuse, five native platform readers,
skill packs for self-extension, and an architecture page plus a generated module
map.

**Two mistakes the assistant made, on the record.** A pace monitor that judged an
outlier after widening its own baseline, and a test that expected a bandit not to
explore. Both were caught by the test suite, both were fixed in the next build,
and both are named in `log.txt`.

**Left.** The deep scan (static invariants: tiers, confinement, secrets, caps,
dead code, claims in documents that the code cannot support), then GitHub writes
with approval, then a packaged Windows installer.

## 2026-11-06 — session 17 (build 1.2.17)

**Asked for.** Ship the work to GitHub, carefully, and make Ultron update itself
from GitHub afterwards without losing the session.

**Built.** `ship.py` (the six-stage ship, a secret scanner that tells a key from a
fixture, a fast-forward-only push, a ship log), `selfupdate.py` (dirty refuse,
verify, revert, restart marker), `ship_tools.py` (four tools, two of them
read-only), and `ship_auto` — off unless the owner writes it, because a push is
public.

**Two defects the build found in itself.** `git status --porcelain` was sliced at
a fixed offset, so the first line lost a character and `app.py` became `pp.py`;
the syntax check then guarded a file that does not exist. And the restart marker
was written into the repository, which made the tree dirty and would have stopped
the next update. Both fixed, both tested, both in `log.txt`.

**Blocked, and not by code.** The token carries Contents: Read but not Read and
write, so GitHub answers 403 on every write while the repository reports
`push: true`. The owner must edit the token. Nothing was stored in this tree.
