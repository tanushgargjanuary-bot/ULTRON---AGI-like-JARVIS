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
before a push. `OwnerFiles/ULTIMATE_Context.md` is the same thing applied to today: what
stands, what is open, the first three commands, and the ten traps that already cost time.

`GATEKEEPERS.md` was saying *"there is no CI, so nothing has ever run on Windows"*. That
stopped being true several builds ago and was corrected rather than appended to.

### 2026-11-07 · repository — `copilot` renamed, then one branch kept

The owner asked for the branch called `copilot` to be renamed `ArenaAi`, and for all work to
stay on one branch. Nothing was rewritten and no commit was lost: `ArenaAi` was created at the
exact commit `copilot` pointed at (`8f3f33b`), the two were compared, and only then was the old
name deleted.

That left two names on GitHub — `ArenaAi` and this session's own branch — and the owner chose
one. `ArenaAi` was deleted, and the work lives on `arena/4c973188-ultron-agi-like-jarvis`. The
old `copilot` content is on this branch, at `8f3f33b` and its parent `44ec6db`. `main`,
`chatgpt` and `antigravity` were not touched.

One thing to know before relying on a green tick: `.github/workflows/verify.yml` runs on a push
to `main` and on a pull request. A push to this branch starts no job until it is opened as a
pull request.

### 2026-11-07 · 1.2.37 — the instruments were run, and three of them complained

The owner asked for the two scripts to be dealt with instead of described. Done: the
dependency set was installed into `/tmp` (never into the project), and then
`scripts/verify.py` and `scripts/proof_gate.py` were actually run on this branch.

**Three defects, all of them in the branch before this build.** A truncated
`git diff --name-status` was read as a file with an empty name. One function in
`scripts/agent_workspace.py` was over both of the project's own size ceilings, so the
ceiling test was red — the function was split, the ceiling was not raised. And the same
script died in any shallow clone with *"no merge base"*, which is every CI checkout and
every agent sandbox; it now compares the two tips and says so.

**The size budget is gone**, by his decision. Deleted rather than silenced: the script, its
test, the gate step, and every page that stated the number. `docs/SPACE.md` says why, and
keeps the two habits worth keeping.

**Two smaller things.** CI now runs on a push to the delivery branch, so a green tick means
something. `docs/COPILOT_RECOMMENDATIONS.md` became `docs/BRANCH_REVIEW.md`, with the four
real branch tips measured and the dead `opencode` reference removed.

**New tool:** `scripts/branch_report.py` — every branch, its tip, and which names are the
same commit. It answers the question a branch picker cannot.

What this run measured: 1,577 tests, 15 skipped, 1 error that is the machine and not the
code (`libGL.so.1` is absent here and there is no package manager), the 1,000 stress
scenarios, 15/15 mutations, and a proof gate of **21 PROVEN / 14 PARTIAL / 0 FAILED**. The
`ui` claim is PARTIAL here for the same missing library; CI installs it and reads 22 / 13.

### 2026-11-07 · the Notion space, and the rule for writing in it

The owner attached Notion and asked for it to stay clean and for every agent to write there
the same way. Two pages, and no more: **Agents — one place, one format** (the rules and the
index) and **Ultron — handover and next moves** (the state, the tasks, the traps).

The rule is also a file, because agents read code before they read notes: `docs/AGENT_NOTION.md`,
pointed at from `AGENTS.md`, so it travels with every branch at merge. The other branches were
told through a repository issue, not a push, because this session does not write to them.

### 2026-11-07 · 1.2.38 · what the other two branches ended on

`chatgpt` is idle at `c98ea0f`. Its capability guide and GitHub scout were taken (`5f576d8`),
with their tests rewritten so the suite actually collects them — under `unittest discover`
that file ran zero tests all day.

`antigravity` is not stopped. It moved four times during the session and claimed issues #3 and
#4 within the hour. Its work stays on its own branch until it stops moving.

`scripts/local_model.py` is the setup path for a local model: check, pull, test, write. It
writes nothing until told, and keeps a backup of the config it merges into.

Not checked: no model was downloaded and no server was reached from this box.

### 2026-11-07 · 1.2.38, later · LFM2 1.2B as the first local model

Small machine, small model. LFM2 1.2B is under 900 MB, holds 32,000 tokens, and runs on a
processor. Ollama keeps one model loaded and unloads it when idle, so "several models" was
never the cost — context is.

Added `python scripts/local_model.py bench`: three tiny jobs, each timed, each scored. Use it
before trusting a model with a file, and again after every change.

Not checked: no model pulled here, no server reached, bench never run live.

## 2026-11-07 — local quota fallback, memory recency, and owner handover

**Asked for.** Start coding on the arena branch, take both the small wins and the hard ones,
and when Gemini reaches its daily limit, find the owner's installed Ollama models and keep
speaking through one. Also keep a durable project trace in `OwnerFiles/`, so a new chat can
continue from the repository rather than from a temporary workspace.

**Decision.** Gemini's model ladder remains first. Only a quota-classified error after the
ladder wraps triggers Ollama. Do not switch on bad keys, bad tool schemas, network failures,
or model-not-found errors. Do not save a temporary fallback into provider settings: that
would make tomorrow's normal configuration wrong. Keep the previous value and exact update
time when a memory fact changes, but keep that history outside the fact store and bound it
at 50 records.

**Built in the worktree.** `custom_jarvis/local_fallback.py` queries Ollama's loopback
`/api/tags`, prefers Qwen 4B and then LFM 2B, rejects embedding-only models, starts `ollama
serve` without a shell if needed, and warms the chosen model before the app changes engines.
The pipeline uses an available local Whisper recognizer or the configured STT provider. It
says when STT is still cloud-based, and refuses to claim voice continuity if no recognizer
exists. It limits small-model tools to 12. The switch lives in memory, retries Gemini after
24 hours, and throttles failed local scans to once a minute. It does not download a model or
use elevation.

`memory/memory_manager.py` now stores ISO `updated_at` values beside the old date field,
shows the timestamp in recall, and writes bounded `{time, path, from, to}` history under
ignored `state/`. A history write failure does not lose the memory fact. Startup offers an
existing planner checkpoint; it never resumes a plan without the owner's request.
`core/action_audit.py` adds one post-action HUD line for non-read-only tools: policy risk tier
plus the status the tool actually reported. It logs neither arguments nor result contents;
it observes the referee's decision and does not change it.

**Proof.** The latest targeted fallback, memory, plan-state, pipeline-fallback, and action-
audit run: **55 tests passed**. Deep scan reports **0 high findings**; the tracked debts are
unchanged at 108 complex functions, 254 library prints, and 82 discarded typed exceptions.
The latest full suite ran **1,700 tests**, 15 skipped, with one Qt setup error because this
sandbox lacks `libGL.so.1`; no other failures were reported. README's measured test count is
1,715. GitHub CI run `42459569545` passed on **Linux and Windows**. The sandbox had no live
Gemini key, Ollama server, or microphone, so the owner's actual model/audio path is not
hardware-verified.

**Not done yet.** The generation swap and safe leaf reload, worker/supervisor split,
test-carrying proposals, evolution-ledger integration, and OCR rung are still future slices.
The user asked to do all of these; this log does not mark them complete.

**Commits and push.** Local quota fallback: `59c6cfb`. Memory recency/history: `5763c8d`.
Owner handover and project trace: `048aed1`, `5825ad1`. After-action risk line:
`dab95a7`. All are pushed to `origin/arena/4c973188-ultron-agi-like-jarvis`. PR #12 remains
open. At the latest check, Linux and Windows passed; Kilo Code Review returned
`ACTION_REQUIRED`, and CodeRabbit was skipped.

## 2026-11-08 — staged action/plugin generations (pushed for review)

**Asked for.** Continue the approved gradual evolution work: reload action/plugin leaves only at a safe session boundary, retain a usable prior generation, and keep the branch/promotion record factual.

**Built in the worktree.** `core/leaf_generations.py` fingerprints only `actions/` and `plugins/`, stages fresh registries, refuses a candidate if a previously active tool disappears or discovery gains a new failure, restores the prior `sys.modules` leaf table on refusal, and retains one preceding generation for rollback. `main.py` checks for a new generation only after the preceding provider session and its awaited tool calls have ended. The action/plugin loaders have an explicit `force_reload` path; forced loads discard stale bytecode so rapid same-size edits do not reuse old code. `custom_jarvis/selfupdate.py` now distinguishes these reloadable leaves from core/application code that still needs restart, and `actions/self_change.py` tells the owner that leaves wait for reconnect and can be restarted immediately if desired. No referee or provider module is included.

**Proof run.** The focused combined run of generation/reload, tool-contract, trigger, provider-schema, quota-fallback, memory, audit, planner, and pipeline-fallback tests ran **134 tests: all passed**; the updater tests and self-change action tests then ran **16 more: all passed**. `compileall` passed. The deep scan reports **0 high findings**, 108 complex functions, 254 library prints, and 82 discarded typed exceptions. During implementation the scan flagged direct dynamic `exec`; forced reload now uses the import loader after invalidating the leaf cache, and the high finding is gone. The final broad suite ran **1,714 tests, skipped 15, and had one setup error**: `AvatarIntegrationTests` cannot import Qt because `libGL.so.1` is absent. No code-test failures remained. The initial run found a stale README count and duplicated test cleanup; both were corrected. Expected loader logs mention deliberately broken actions and the missing optional Playwright dependency. The proof gate still reports **21 PROVEN / 14 PARTIAL / 0 FAILED**; the proof gate and compile pass. The first CI run (`42464304549`) failed both suite jobs; after documenting both the live local count and last recorded count in the README, run `42464882412` passed on Linux and Windows. The later handover-only commit was also verified by run `42465596629` on both platforms. No code changed after the README correction.

**Still unverified.** CI run `42464882412` passed on Windows and Linux, but no live UI session has exercised a generation swap. Rollback is available on the manager but is not yet exposed as a user control or automatically triggered by later runtime failures. This is a staged loader change, not a supervisor/worker process and not test-carrying proposals.

**Branch review.** Current remote refs were rechecked: `main` `44ec6db`; `ArenaAi` `7dcf2d6`; `chatgpt` `c98ea0f`; `antigravity` `b8e9334`. PR #12 (arena → `ArenaAi`) and PR #8 (`ArenaAi` → `main`) are both open. `ArenaAi` must remain while both depend on it. The `chatgpt` endpoint still has unique detector/router work not present at the `ArenaAi` tip; `antigravity` has not been selectively audited enough to delete. No branch was deleted. See `docs/BRANCH_REVIEW.md` for the reviewed OCR/router/plugin-forge caveats.

**Commit/push state.** Generation code, tests, and initial handover update were committed as `e763747`; the cross-platform README count correction is `f5a090b`. Both are pushed only to `arena/4c973188-ultron-agi-like-jarvis`; PR #12 remains open for review. No code was merged or pushed to `main`.

## Follow-up: CodeRabbit and manual reload review

CodeRabbit completed a review of PR #12, covering the diff from `8f4803b` through `657b73b`. It posted **23 actionable comments** (10 major, 7 minor, 4 nitpicks) plus failed pre-merge checks. The review did not include later commits `ae838e2` or `983a9f6`; the latest head still has no follow-up CodeRabbit review. Kilo review remains blocked by insufficient account credits.

**In-scope findings and changes.** CodeRabbit's major comment found that the initial `tree_signature()` call could abort startup on an `OSError`. The manager now preserves discovered registries with an unknown signature and retries during a later safe refresh; a regression covers transient failure. Its mixed-update comment found that leaves could reload at reconnect while changed core code still required restart. The updater now records a leaf-defer marker, `main.py` skips reload while that marker is active, and a fresh process consumes the flag after loading the updated tree. The reviewer also asked for behavioral verification of protected referee identity and a valid helper-signature baseline; both tests are now behavioral. Separately, manual review reproduced stale parent-package attributes and split sibling module identities; those were fixed in `ae838e2`.

**Other review comments.** The remaining CodeRabbit comments cover plan-state validation/resume, planner persistence, local fallback, MCP robustness, memory-write atomicity, and other broader PR content. The review also flagged PR scope, linked-issue checks, and docstring coverage. These were not part of the requested action/plugin reload follow-up and are not marked resolved; keep them visible for owner triage rather than silently expanding or splitting the open PR.

**Verification and promotion.** Focused reload/self-change tests: **52 passed**; updater tests: **8 passed**; `compileall` and `git diff --check` passed. The bare system-Python full-suite attempt remained incomplete due missing optional packages and is not a clean broad-suite result. README's discovered count is **1,732**. The review-driven fixes are committed/pushed as `983a9f6` on the Arena branch; PR #12 remains open. Run `42469609070` passed on Linux and Windows for this commit. No change was merged or pushed to `main`. See `OwnerFiles/reviews/reload-review-follow-up.md` for exact triage and next steps.

## OwnerFiles organization and context archive

The owner asked for the context folder to be less cluttered and easier for agents to navigate. The five older handover/history/notes/review documents are now grouped under `history/`, `owner/`, and `reviews/`; the old handover is explicitly marked historical. `OwnerFiles/README.md` is now a short index, and `OwnerFiles/ULTIMATE_Context.md` is the single current entry point. Existing references were updated rather than leaving broken links. No historical note was deleted.

The portable `ULTIMATE_Context.zip` remains in the folder as a tracked deliverable. It was rebuilt from source snapshot `d7abf40` after checking the organized tree, excludes itself and credentials, and passed `unzip -t`. Its SHA-256 is recorded in the live metadata page. The current PR/CI state remains open/red: run `42529553481` failed Linux suite/self-checks and Windows native checks; exact runner logs still need human/agent review.


## 2026-11-10 — final branch cleanup and durable project handoff

**Asked for.** Finish consolidation so `main` is the only branch. Then make the repository self-explanatory enough that a new chat can continue after the old chat is deleted. Add a mandatory agent procedure that updates documentation and performs safe repository cleanup after meaningful medium/large work.

**Repository result.** The curated application had already been promoted to `main` by a direct non-forced fast-forward. Ten obsolete branches were removed only after their full commit SHAs were preserved in ten archive tags and an Active tag ruleset was verified. Ruleset `26923169` protects `refs/tags/archive/**/*`: update and deletion are blocked, tag creation is allowed, and no bypass actor is present. Cleanup workflow [`42779866199`](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42779866199) completed successfully. The live post-cleanup audit found one branch (`main`), ten archive tags, all ten expected recovery SHAs, and zero open pull requests.

**Verification evidence.** Cross-platform verification run [`42775101593`](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42775101593) completed on Linux and Windows. Linux proof gate: 24 PROVEN, 13 PARTIAL, 0 FAILED. Windows: 28 PROVEN, 9 PARTIAL, 0 FAILED. Separate instrument scans were non-blocking and recorded environment/hardware gaps. These results do not prove every owner-machine hardware path.

**Documentation and agent governance.** The canonical project handoff is `OwnerFiles/ULTIMATE_Context.md`. The new `docs/AGENT_MAINTENANCE.md` defines task classification, required documentation impact review, canonical handoff format, safe cleanup checks, structure rules, and a close-out checklist. Root `AGENTS.md` and `docs/AGENT_PLAYBOOK.md` make it mandatory. `docs/INDEX.md`, `OwnerFiles/README.md`, `readme.md`, and `.github/PULL_REQUEST_TEMPLATE.md` point agents to the process. Historical branch and release status docs were reconciled with the final cleanup.

**Decisions recorded.** `main` is the only permanent branch. Feature/fix branches are short-lived. The ten archive tags are protected historical recovery points. No workspace size/file-count ceiling is active; the owner withdrew the 100 MB / 5,000-file budget on 2026-11-07.

**Still open.** Vercel team authorization and preview setup remain owner-gated. ULTRON Web remains an authentication/workspace shell, not a deployed Python agent. General provider failover, an OS-level rehearsal sandbox, fully sandboxed MCP processes, and a complete signed update pipeline remain unverified or incomplete. Do not treat this documentation milestone as product completion.


### Follow-up — archive workflow remains valid after branch deletion

The first documentation push after branch cleanup exposed a workflow assumption: push-triggered archive-only runs still tried to read the now-deleted curated candidate branch. GitHub returned 404 and the archive job failed before it could complete its no-deletion path. The workflow now falls back only to the protected candidate archive tag and verifies that it still points to the exact reviewed promotion SHA `bd4b43d16fdf27b495209678ed72b41f21408d7c`. Any other missing-ref error or unexpected tag target stops the run. This preserves the one-branch end state and keeps future `main` pushes idempotent.


## 2026-11-10 — FatihMakes MARK/JARVIS upstream resource audit

**Asked for.** Use the resources published around FatihMakes, MARK, and JARVIS to improve ULTRON. Preserve the original lineage while avoiding blind code imports.

**Sources reviewed.** Eight public repositories were returned by the FatihMakes account search: Mark-LVI, Mark-XXXIX-OR, Mark-X, Mark-X.1, Mark-X-TR, Jarvis-Mark-X, AI-Assistant-for-Computer, and AI-Assistant-1.1. The current primary source was MARK-LVI main commit `0101e540ac4b16cc3a862d9979e08fefcc1c7a01`. The review also searched 100 issue results and 40 pull-request results, then read selected PR source files. A global Mark-LVI repository search returned many forks; it was not an exhaustive fork audit.

**Direct comparison.** At ULTRON main `76484ebc4cbf4b5d4a23889ed6eeddfbf844083c`, the MARK-LVI tree had 78 files and every path already existed in ULTRON. Sixteen shared paths were byte-identical; 62 shared paths differed; ULTRON had 355 additional paths. No upstream source file was missing by path. The remaining code intake task is a semantic review of 50 shared files. A first focused comparison of 12 high-risk files found ULTRON-specific improvements: failure telemetry, purpose-based provider routing, config recovery/validation, safe PowerShell quoting, sensitive-file denial, generation-aware plugin reload, partial tool-result handling, lazy audio imports and TTS fallback, stricter web-search triggers, safer dashboard binding, and corrected `.gitignore` rules. No safe upstream-only implementation was identified for direct copying in those 12 files. This was a focused diff review, not a full independent security audit.

**Important upstream candidates.** MCP, planning, routing, audit, and tool-selection triggers already exist in ULTRON. Issue #117 makes credential-store support a valid security review. Issue #123 and microphone/wake-word reports provide regression scenarios. Multiple-monitor support still needs target-machine proof. Gesture PRs #167/#168 have no regression tests in their file lists and need stronger policy integration. Multi-agent PR #165 was open/non-mergeable at audit, says testing is unverified, and includes a tracked `config/api_keys.json`. PR #121 overlaps ULTRON's existing safety layer. None was merged or copied wholesale.

**Licence and provenance.** MARK-LVI's checked-in `LICENSE` names FatihMakes and CC BY-NC 4.0. Commercial use is prohibited without separate written permission. GitHub's SPDX metadata says NOASSERTION; the checked-in text is the source to preserve. Older repositories and separate model/binary assets need their own provenance checks.

**Durable record.** `docs/UPSTREAM_RESEARCH.md` records the repository list, source commit, file-tree comparison, issue/PR triage, licence controls, intake process, and search limits. It is indexed in `docs/INDEX.md`, linked from the README and owner handoff, and required by `docs/AGENT_MAINTENANCE.md` for future upstream intake. No new product code was imported in this audit.

**Verification state.** Main `76484ebc4cbf4b5d4a23889ed6eeddfbf844083c` passed Linux and Windows in run [`42786030989`](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42786030989). Archive-only workflow run [`42786030636`](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42786030636) also passed. Linux proof gate: 24 PROVEN / 13 PARTIAL / 0 FAILED. Windows: 28 PROVEN / 9 PARTIAL / 0 FAILED. Hardware/environment limits remain unchanged.
