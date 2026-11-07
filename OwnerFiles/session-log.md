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

**Pushed.** `main` is live at GitHub with all seven commits. The blocker was not
the code: a fine-grained token needs **Contents** and **Workflows**, both Read and
write, because GitHub checks the whole push and one CI file has been in the
history since the first commit. A classic token with `repo` and `workflow` worked
at once. Two probe commits from the write test were removed with a lease-pinned
force, and no other work was touched.
**The first real Windows run.** GitHub ran the verifiers on a real Windows machine. The display checks passed 13 of
13 — the window draws, at three sizes, with the log panel inside the frame and text in it. Three areas failed, and
all three were the instrument reporting a missing device as a broken product; that is fixed, and a test now locks
the rule. Two mistakes in the CI file itself were also found by the same run and fixed.
**Green on both machines.** Both CI jobs pass: the Linux one and the Windows one. On Windows the proof gate reads
18 PROVEN, 9 PARTIAL, 0 FAILED, and the suite runs 1,308 tests there. Four defects came out of the round, and every
one of them was invisible from the machine the code was written on. That is the whole argument for running it on
yours, made by the thing that ran on yours.

## 2026-11-06 — session 18 (build 1.2.18)

**Asked for.** A professional, compact repository; a better front page, in simple
words, with a separate section for technical readers; good animations; and an
answer on rewriting in a faster language. Also: one commit per improvement, and
faster work.

**Done.** The front page is one page for people plus one section for engineers.
The HUD core colour fades between states instead of cutting. Line endings are
recorded in `.gitattributes`. The faster-language question is answered with
timings, not opinion: the waiting is the network and the recogniser, and both are
already outside Python. Four separate commits, each with the reason in its
message.

### 2026-11-06 — the front page had to earn its claims

You said: make sure nothing in the readme is invented. You were right to ask.

**What was wrong.** One link pointed at a folder that is not in this repository.
The file counts were out of date. A speed table quoted an earlier measurement
without saying so.

**What stands now.**

| Question | Answer that is true |
|---|---|
| Does the page animate? | Yes — a 40-frame GIF committed in the repository, drawn by a script. |
| Can a reader with ADHD finish it? | One idea per line, the picture first, the long half folded behind one click. |
| Is a faster language worth it? | Measured: the audio leaf is 0.18 % of a frame. C is 36x faster only when nothing is copied. The wait is the model, not the language. |
| Can the page lie again? | No. A test fails if it names a file that is absent or a count that is not in the tree. |

**Still owed to you:** revoke the two GitHub tokens you pasted. They are in this
conversation's history, and a token in a log is a token someone else can use.

### 2026-11-06 — it watches your background jobs now

**What you asked for.** Ultron should know what is running in the background, and
tell you when a job finishes. If you are talking to it, it should wait until you
stop talking.

**What it does now.**

| Situation | What Ultron does |
|---|---|
| An agent in Antigravity finishes while you are quiet | One sentence, at once. |
| It finishes while you are talking to Ultron | The log line appears at once; the voice waits for silence. |
| Three jobs finish at the same time | One sentence, not three. |
| You pause for breath | Still waiting. A pause is not a stop. |
| The process list cannot be read | Nothing is announced. It says "I do not know", not "it finished". |
| Ultron did not start the process | It says "finished", never "succeeded" — no exit code exists to read. |

**The rule that makes it safe.** It only watches. It cannot end, pause or restart
another program, and a test reads the code and fails if that ever becomes
possible. A supervisor that can kill is a supervisor that will one day kill the
wrong thing.

**Tuning it.** Set `ULTRON_WATCH` to a comma-separated list of program names. The
default is one: `antigravity`. It polls every two seconds.

**Your language list.** All 46 are answered in `docs/LANGUAGE_MATRIX.md`. Six are
kept, two are used through libraries, five wait behind a named trigger, and
thirty-three are refused with a reason. Short version: Python is the shell,
numpy is the arithmetic, C is a leaf only when nothing is copied, SQLite is the
memory, Qt is the pixels, PowerShell is the door.

### 2026-11-06 — I tried to make it start faster. The numbers said no.

You said: do what you find safe. So I measured first.

| What I tried | What the measurement said | What I did |
|---|---|---|
| Move a 12–30 ms import out of the window module | 186 ms → 182 ms, and no faster first frame | **Reverted.** The cost moved, it did not go away. |

That is the whole report, and it is the right kind of report. A change that makes
a claim I cannot see in a number does not go in.

Two things did improve:

- A figure I had written from arithmetic ("0.02 ms per process") is now the
  measured one: **3.4 ms per full process-table sweep**, 0.17 % of the two-second
  poll.
- The tool that measures starts now has tests of its own, so its numbers cannot
  quietly become warm-process numbers wearing cold labels.

**Your performance question, answered plainly.** On memory, start-up and install
size, this stack loses to Go or Rust, and nothing in it will change that. On the
time a turn actually takes — the model answer and speech recognition — the
language does not matter at all. The one place a faster language still wins is a
single audio leaf, and it is 0.005 % of a frame. So the honest answer is: it is
not the fastest stack, it is the fastest stack that also keeps your approvals,
your files and your memory safe — and that trade was made on purpose.

### 2026-11-06 — the one part of Ultron that is not Python

You asked me to start rewriting where Go and Rust win. I found exactly one place,
and I built it.

**The place.** A supervisor cannot live inside the program it supervises. If
Ultron crashes or restarts, a watcher inside it dies — and the notification you
asked for ("the agent finished") is lost at the moment it matters most.

**What it costs now, measured:**

| | Go sidecar | Python watcher |
|---|---|---|
| size | 2.0 MB | an interpreter + psutil |
| start to first look | 3 ms | 26 ms |
| memory while watching | 2.7 MB | 13.6 MB |
| time from job ending to notification | 10 ms | same poll, same table |

**Why not Rust.** Rust is better at hot loops and tight memory promises. This
component does neither; it polls and restarts one child process. Also, the Rust
toolchain could not be installed on my build machine, and I will not ship code I
could not run. Rust stays on the list for the first leaf that is measured hot.

**What did not change.** The shell is still Python, and so is every safety rule:
path confinement, risk tiers, approvals, the evidence trail. That is the part a
rewrite would cost weeks to re-prove, and it would make nothing faster.

**If you want the compiled watcher:** install Go once from go.dev/dl, then run
`.\sidecar\build.ps1`. Without it, everything still works — you lose only the
crash-proof part.

### 2026-11-06 — "why do I still see most of the code in Python?"

Because line count is not time. I now have the measurement instead of an
argument:

| What Python does in one exchange | Time |
|---|---|
| Decide the risk tier of every tool you have | 0.009 ms |
| Describe every tool to the model | 0.028 ms |
| Fill the system prompt | 0.054 ms |
| Read the prompt file | 0.024 ms |
| Read your memory | 0.012 ms |
| **Everything Python does in a turn** | **0.165 ms** |

Your wait is 600–4000 ms of model. **Python is four thousandths of one percent to
three hundredths of one percent of it.** If I rewrote all 84,000 lines in Go, the
change you would feel is zero, and you would lose the files where every safety
rule lives — the ones that stop a tool from writing outside your folder, and ask
you twice before changing code.

**What I did make faster instead:** the one place where a compiled language really
wins, the supervisor that survives a crash (2 MB, 3 ms, 2.7 MB resident, in Go).
And a bug in it that only the tests caught: the binary was built without the
execute bit, so the app quietly used the slower fallback.

**Where the remaining seconds are, honestly:** the model (600–4000 ms), speech
recognition (300–1500 ms), and a connection handshake per turn (100–300 ms). The
last one is ours, in Python, and it is the next thing I would fix.

## 2026-11-06 · 1.44 — the owner's two levers

The owner picked the two owned levers out of the performance table and left for 15
minutes. Both are now closed, and neither was closed the easy way.

The warm connection was real work: seven call sites, a module that keys the pool by
everything that changes behaviour, and an event loop in the key because an async
pool belongs to one loop. It also produced the best measurement mistake of the
session — the benchmark said pooling was *slower*, and the benchmark was wrong.

The shorter prompt was not real work, and saying so is the honest result. 16,620
characters, no duplicated line, nine tenths persona and rules. Cutting it would
change how Ultron behaves, and this project does not change behaviour to win 50 ms.
It is guarded instead, so it cannot grow unnoticed.

Two things were found by not trusting a green run: the sidecar's executable bit
does not survive a snapshot, and the gate's PARTIAL column was a number without a
reason. Both are fixed. A single segfault in a Qt teardown was seen once, could not
be reproduced, and is written down rather than swept.

### 2026-11-06 · 1.2.33 — "how do I make sure the triggers work?"

He asked the question that follows every feature: a skill with no condition is a
skill Ultron will never use. It was not solved. The instruction cut each tool's
one-line description at 150 characters, and on that build **10 of 32 tools lost the
sentence that says when to call them** — the newest and least obvious ones, the
reasoning kernel and the syllabus tool among them. Twelve more had no condition at
all.

Every tool now reads `- name: WHEN — what`. The condition is taken from the tool's
own description, never written twice, and it goes first, so the cap can only cost a
description. Every call is counted, so asking *"what can you do"* also answers
*which of these have I never reached for*. Measuring the prompt also showed the old
budget test measured the wrong list: 16,620 characters was the inline tools only,
22,320 is what the app actually sends.

### 2026-11-06 · 1.2.34 — a crash that leaves a record

Under `pythonw` there is no console, and there was no `sys.excepthook`, no
`threading.excepthook`, no unraisable hook and no `faulthandler` anywhere in 93,000
lines. A bug reached him as a window that disappeared.

`core/crash.py` catches all four kinds of death: the main thread, a worker thread, an
object dying in a destructor, and a native fault inside a Qt or audio DLL that Python
never sees. A report holds the time, the build, the kind, the message, the traceback,
and **the last notes the assistant made before it fell**, which is usually where the
cause is. Secrets are removed before the file is written. Twenty reports are kept.

Self-repair now starts from the report: a proposal carries the crashes known at the
time, and *"why did you crash"* reads the newest one.

The Windows runner then found two real bugs in that build, which is exactly what it
is for: the open fault-handler stopped a temporary folder being deleted, and a test
that used `chmod` to make a folder unwritable was a **false pass** on Windows, because
Windows ignores `chmod`. Both fixed, and the second one now blocks a write by pointing
at a file instead of a folder — a failure every platform agrees on.

### 2026-11-07 · 1.2.35 — it stopped blaming the API key

He pasted his activity log. The session would not stay up, and the log said:

```
APIError: 1007 ... function_declarations[40].parameters.required[0]:
property is not defined
ERR: API key invalid - please re-enter your key.
```

He re-entered a key that was already right, more than once. There were two faults.

**One field of one tool stopped everything.** Five bridge plugins said *"action is
required"* and never declared `action`. Google does not ignore a schema it dislikes:
it refuses the whole tool list and closes the session with 1007. Every retry sent the
same list and was refused the same way.

**The number was read as an answer.** The reconnect loop tested `"1007" in err_str`,
and 1007 covers a bad key, a bad model name and a bad schema alike — so a schema fault
opened the re-key panel.

Both fixed, and both guarded: `core/action_loader.py` repairs a bad declaration at
start and says what it repaired, so one bad field costs one argument instead of the
session; `core/close_codes.py` reads the message before the number and names the tool
that was refused. `tests/test_provider_schema.py` has 18 tests, and his own log line is
one of the fixtures. The gate now proves *"the provider accepts the list"*.

### 2026-11-07 · 1.2.36 — the pages a new agent needs

He is handing this project to other tools, so the documents were brought up to date and
one new page was written: `WORKING-PHILOSOPHY.md`. It holds the one rule, how we talk to
him, how a change is made, what is never allowed, the failure patterns, and the checklist
before a push. `OwnerFiles/for-the-next-agent.md` is the same thing applied to today: what
stands, what is open, the first three commands, and the ten traps that already cost time.

`GATEKEEPERS.md` was saying *"there is no CI, so nothing has ever run on Windows"*. That
stopped being true several builds ago and was corrected rather than appended to.


## 2026-11-07 — capability awareness work

**Asked for.** Find relevant native tools and skills from a user's goal, improve awareness when a needed capability is unknown, clarify self-evolution, and investigate useful GitHub repositories for possible native additions.

**Built so far.** Added `actions/capability_guide.py` on `chatgpt`. It reads the live tool catalog and installed skill recipes, ranks text matches, reports availability, and explains the existing `self_modify` workflow. It does not install or execute repository code.

**Still open.** The tool descriptor now exposes the guide to the action loader, but discovery/callability has not been verified. GitHub repository research, tests, and explicit prompt wording about self-evolution remain to be completed.


### 2026-11-07 — Harness² follow-up

**Asked for.** Apply Harness²'s recursive-harnessing principle to Ultron, close the gap between its actual self-change abilities and what it says about itself, and explain a practical path for detecting useful tools when the user is stuck.

**Reviewed.** The Harness² README describes task-level Propose–Probe–Compose edits to prompts, guardrails, memory, tool guidance, subagents, skills, scripts, and plugins, plus a persistent improvement harness that retains adopted harnesses and evidence-supported lessons. It is a research/benchmark framework, not a drop-in runtime for Ultron.

**Direction.** Adapt the loop, not the framework: capability-match the user's goal against the live tool and skill catalogs; if a gap remains, research candidate repositories without installing them; propose one bounded change to a prompt, skill, or tool guide; probe the same task before and after; retain only evidence-backed lessons. Keep source changes behind the existing self_modify rehearsal and two-channel confirmation. No self-install or unattended source changes.

**State.** The capability guide is present on `chatgpt`, but still needs runtime verification, repository research integration, explicit prompt routing, and tests. This entry records design guidance; it does not claim Harness² recursion is implemented.


## 2026-11-07 — capability awareness and Harness² design

**Asked for.** Make Jarvis recognize unstated tool needs, help when the user is stuck, know and state its self-evolution ability, find promising native skills/tools and GitHub projects, and apply Google's Harness² recursive-improvement principle.

**Built.** Improved `actions/capability_guide.py` with deterministic outcome synonyms (including compress/zip/archive), live tool availability, skill matches, and explicit safe next steps for missing capabilities. Updated `core/prompt.txt` to route uncertain or stuck requests through the guide and accurately describe controlled self-change plus a same-task probe. Changes are on `chatgpt` only.

**Harness² adaptation.** Use a bounded Propose–Probe–Compose cycle: identify the task and baseline; propose one change to tool guidance, prompt, skill, or script; rehearse and compare on the same task; adopt only an evidence-supported improvement; retain the lesson for later changes. Repository candidates are researched and reviewed before any native implementation. This adapts the principle; it does not import Google's benchmark framework or implement autonomous recursive optimization.

**Follow-up built.** Added `actions/github_repo_scout.py`, a standard-library-only, read-only GitHub repository search that ranks a short public-project list by stars, maintenance recency, and metadata, reports licenses, and never downloads code. The prompt now routes a capability gap to this scout after checking native tools. Changes remain on `chatgpt` only.

**Still open.** Runtime discovery/callability and an actual same-task before/after probe have not been verified. The scout ranks repository metadata, not source-code quality; a human-reviewed integration proposal and evidence-backed adoption loop are still needed. No tests were run in this session.


## 2026-11-07 — native capability routing follow-through

**Asked for.** Make existing native abilities easier to find and more reliable, with flexible wording, and keep changes easy to take selectively into a future branch.

**Built.** The capability guide now filters generic-only matches and applies a small task-cue map (compression, conversion, summarizing, transcription, search, screenshots, and self-change) to the live tool catalog. The catalog remains the source of truth for whether a named tool exists and is currently available. The GitHub scout and prompt routing remain separate changes, so they can be selected independently. All edits are on `chatgpt`.

**Baseline inspection.** The file processor declares image compression and video compression. The capability catalog intentionally shortens tool descriptions, so a literal search for “compress” could miss that ability. The new task cue addresses this mismatch. The plan's representative cases are: compression (should suggest file_processor), workspace review (should use review_changes), and an unsupported task (should show no ready match and offer repository research).

**Verification limit.** Source inspection supports those expected routes, but I could not execute the app or its tests because this workspace has no repository checkout. Runtime discovery, actual routing, and availability on the owner's machine remain unverified. Do not describe those as verified until run in the app. The scout evaluates public metadata only, not source safety or suitability.


**Completion follow-through.** Added focused routing checks in `tests/test_capability_guide.py` for indirect compression wording, skill-name matching, generic requests, unavailable tools, and unsupported tasks. Refined the compression phrases to avoid treating every mention of a large item as compression, and made underscore-based internal skill names match normal user wording.

**Execution status.** The tests were not executable in this environment: the workspace has no repo checkout, GitHub network cloning failed, and the available `python.exe` launcher could not start. The tests are committed for the next environment with Python and the project checkout. This means routing is source-reviewed, not runtime-verified.


## 2026-11-07 — read-only branch review

**Asked for.** Make the untested status clear in the docs and inspect other branches for useful capability ideas without editing them.

**Reviewed.** Compared `chatgpt` with `antigravity` and `arena/4c973188-ultron-agi-like-jarvis`. The first has a context detector and a large repository-candidate catalog; the second has a read-only agent workspace report and a test-first playbook. Only read access was used on those branches.

**Updated on `chatgpt`.** Added `docs/CAPABILITY_AWARENESS.md` with a prominent NOT TESTED status, scope and limitations, concrete verification steps, and the read-only inspiration review. Linked it from `docs/INDEX.md`. No files on other branches were changed.
