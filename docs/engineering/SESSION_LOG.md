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

**Direct comparison.** At ULTRON main `76484ebc4cbf4b5d4a23889ed6eeddfbf844083c`, the MARK-LVI tree had 78 files and every path already existed in ULTRON. Sixteen shared paths were byte-identical; 62 shared paths differed; ULTRON had 355 additional paths. No upstream source file was missing by path. The remaining code intake task is a semantic review of the 62 shared files, starting with credentials/config, provider lifecycle, audio, reconnect, browser, and UI control.

**Important upstream candidates.** MCP, planning, routing, audit, and tool-selection triggers already exist in ULTRON. Issue #117 makes credential-store support a valid security review. Issue #123 and microphone/wake-word reports provide regression scenarios. Multiple-monitor support still needs target-machine proof. Gesture PRs #167/#168 have no regression tests in their file lists and need stronger policy integration. Multi-agent PR #165 was open/non-mergeable at audit, says testing is unverified, and includes a tracked `config/api_keys.json`. PR #121 overlaps ULTRON's existing safety layer. None was merged or copied wholesale.

**Licence and provenance.** MARK-LVI's checked-in `LICENSE` names FatihMakes and CC BY-NC 4.0. Commercial use is prohibited without separate written permission. GitHub's SPDX metadata says NOASSERTION; the checked-in text is the source to preserve. Older repositories and separate model/binary assets need their own provenance checks.

**Durable record.** `docs/UPSTREAM_RESEARCH.md` records the repository list, source commit, file-tree comparison, issue/PR triage, licence controls, intake process, and search limits. It is indexed in `docs/INDEX.md`, linked from the README and owner handoff, and required by `docs/AGENT_MAINTENANCE.md` for future upstream intake. No new product code was imported in this audit.

**Verification state.** Main `76484ebc4cbf4b5d4a23889ed6eeddfbf844083c` passed Linux and Windows in run [`42786030989`](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42786030989). Archive-only workflow run [`42786030636`](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42786030636) also passed. Linux proof gate: 24 PROVEN / 13 PARTIAL / 0 FAILED. Windows: 28 PROVEN / 9 PARTIAL / 0 FAILED. Hardware/environment limits remain unchanged.


### 2026-11-10 — six more MARK-LVI file comparisons

The next six changed shared paths reviewed were `actions/code_helper.py`, `actions/open_app.py`, `actions/send_message.py`, `core/llm_client.py`, `core/confirm.py`, and `core/outcome.py`.

ULTRON keeps the shell-free app resolver, the explicit confirmed/unverified message outcome, failure telemetry for LLM calls and confirmation handling, and the UI-owned confirmation boundary. `core/outcome.py` has identical normalized lines to upstream. `actions/code_helper.py` is nearly identical, with no material upstream safety behavior identified. No code was copied.

The focused review now covers 34 of the 62 changed shared paths. Twenty-eight remain. This was a focused diff and source-path review, not a full security audit. The broad test suites exist, but a dedicated test module for each of these six files was not found in the test tree.

**GitHub About description.** The repository metadata still has a blank description. Proposed short text: “A voice-first desktop AI agent with computer control, web research, memory, and safety gates.” The connected GitHub tools expose metadata reads and file writes, but not repository-settings writes. The About field remains an owner action.


### 2026-11-10 — six more MARK-LVI runtime and media comparisons

The next six changed shared paths reviewed were `core/installer.py`, `actions/desktop.py`, `actions/proactive.py`, `actions/reminder.py`, `actions/screen_processor.py`, and `actions/youtube_video.py`.

ULTRON includes the Windows `uiautomation` dependency used by its accessibility-tree driver; it applies explicit consent limits to proactive suggestions; and it uses lazy optional imports for PIL, requests, and YouTube transcript support. The reminder improvement is limited to clearer tool wording. No upstream code was imported.

The focused review now covers 40 of 62 changed shared paths. Twenty-two remain. This was a focused diff comparison, not a full security audit. Hardware-specific behavior still requires the normal ULTRON verification on the target machine.


### 2026-11-10 — six more MARK-LVI system and playback comparisons

The next six changed shared paths reviewed were `actions/flight_finder.py`, `actions/game_updater.py`, `actions/system_monitor.py`, `actions/video_player.py`, `actions/weather_report.py`, and `core/hotkey.py`.

The normalized flight-finder and game-updater code is effectively the same. ULTRON keeps the first-alert correction in the system monitor, validates video-player arguments and records failures, declares the requested forecast day in the weather tool schema, and records keyboard-hook failures. No upstream source code was copied.

The focused review now covers 46 of 62 changed shared paths. Sixteen remain. This was a focused diff comparison, not a full security audit.


### 2026-11-10 — six more MARK-LVI safety, test, and install comparisons

The next six changed shared paths reviewed were `core/undo.py`, `core/echo.py`, `providers/_tests.py`, `core/_smoke_harness.py`, `setup.py`, and `requirements.txt`.

ULTRON's undo registration reports success/failure to its caller. It also records echo-reference failures, retires Qt widgets before the provider-test process exits, validates smoke-harness arguments before loading target code, protects setup output encoding, and pins PyQt6 below a measured headless startup crash release. No upstream code was imported.

The focused review now covers 52 of 62 changed shared paths. Ten remain. This was a source-delta review, not a full independent security audit. The test runner's platform and hardware limits remain explicit.


### 2026-11-10 — six more MARK-LVI public-facing and dashboard comparisons

The next six changed shared paths reviewed were `AGENTS.md`, `LICENSE`, `core/prompt.txt`, `dashboard/static/app.html`, `dashboard/static/login.html`, and `readme.md`.

ULTRON retains its expanded agent-governance rules, its policy/consent/untrusted-content prompt, an authenticated dashboard session with AES-GCM client encryption, and a shorter README that states limitations. The `LICENSE` file is identical to upstream after normalization and continues to attribute FatihMakes under CC BY-NC 4.0. No upstream code or licence change was applied.

The focused review now covers 58 of 62 changed shared paths. Four visual files remain: avatar code, avatar mesh, face model, and viseme. Dashboard review was a source comparison, not a penetration test. Licence review confirmed the text, but does not resolve rights for separate assets or binaries.


### 2026-11-10 — completed the 62-file MARK-LVI source comparison

The final four shared paths were `core/avatar.py`, `core/avatar_mesh.py`, `core/face_model.obj`, and `core/viseme.py`.

ULTRON's avatar renderer adds persona-specific movement and semantic facial expressions. The mesh builder and viseme implementation are identical to upstream after line-ending normalization. The face model contains 468 vertices and 898 faces, with the same face indices as the inspected MediaPipe source. Coordinates are stored to four decimal places; the maximum coordinate difference is 0.00005.

The source asset header identifies MediaPipe and Apache 2.0. The full MediaPipe root `LICENSE` bundle from commit `e1e239ad86fc9ee4e6c65e573924c45c0176d5c6` is now copied to `licenses/MEDIAPIPE-LICENSE.txt`; `licenses/THIRD_PARTY_NOTICES.md` records provenance, the geometry extraction, the separate licence boundary, and its limitations. The root CC BY-NC licence was not changed.

**Comparison complete.** All 78 paths in the inspected MARK-LVI main tree were present in ULTRON. Sixteen shared paths had identical Git blob SHAs; the other 62 were reviewed by focused source-delta comparisons. No whole upstream branch or code batch was imported. This is not a full independent security audit of every function, dependency, fork, or issue in the upstream ecosystem.

**GitHub About description.** The metadata remains blank. Proposed text: “A voice-first desktop AI agent with computer control, web research, memory, and safety gates.” The connected interface still lacks a repository-settings write operation, so the About field remains an owner action.


### 2026-11-10 — verification and handoff close-out

The final upstream research, MediaPipe licence copy, third-party notice, and owner-handoff update were committed on main at `8154ad553f94190c0f84dc7cbf8ec0dc2e4c3abf`.

- Cross-platform verification run [42799637908](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42799637908) completed successfully. Both Linux and Windows jobs passed.
- Archive-only workflow run [42799637975](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42799637975) completed successfully.
- GitHub reports one branch (`main`), ten archive tags, zero open pull requests, and an Active tag ruleset ID 26923169. It blocks updates and deletions and has no bypass actors.
- All 62 changed shared paths in the inspected MARK-LVI tree have focused diff records. This does not cover every global fork or every GitHub mention.
- The GitHub About description remains blank. The connected GitHub write tools do not expose repository-settings updates.

This log entry records the verified baseline. A follow-up documentation commit must be treated as unverified until its own Actions run completes.


## 2026-11-10 — repository documentation accuracy audit

**Request.** Refresh the repository docs so the source of truth reflects the latest verified project state and a new chat can continue without this conversation.

**Audit baseline.** The audit read the repository tree, README, architecture, owner decisions, proof-status guide, agent rules, documentation maintenance process, branch/archive records, canonical handoff, and project history. At the time of audit, `main` was `116b0317fdd5eec654ff009ee65281fff27e34ec`. Verification run [42803012589](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42803012589) passed on Linux and Windows. Archive workflow [42803012590](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42803012590) passed. The live branch list contained only `main`; there were no open pull requests.

**Findings.** The README repeated its branch instructions and said the private owner-development repository had not been created. The private repository does exist, but it is empty and has no active development/canary workflow. The canonical handoff and `GATEKEEPERS.md` cited an older verification run. Their current proof counts were rechecked against the latest workflow logs.

**Changes prepared.** The README's private-development statement and branch workflow were corrected. `GATEKEEPERS.md` now cites the latest inspected verification run and its proof counts. `OwnerFiles/ULTIMATE_Context.md` now records the current verified baseline, archive run, and private-repository limitation. This session log records the reason for the documentation refresh.

**Not changed.** No application source, owner decision, architecture, permission rule, or capability claim was changed. The existing maintenance system remains the required process; no duplicate continuity guide was added. `docs/MAP.md` was not regenerated because no Python module or test changed. `docs/INDEX.md` needed no change because no document was added, moved, or renamed. Historical build records and the project journey were preserved.

**Verification limits.** A local checkout was not available in this execution environment, so no local Python test command or workspace report is claimed. The documentation PR's GitHub Actions checks are the verification for these changes. Do not treat the pre-change main verification run above as evidence that this documentation patch itself passed.

## 2026-11-10 — automatic branch-update tests and hard regression gate

**Request.** Add a subsystem that automatically runs checks within seconds or minutes whenever a branch is updated. Break the work into small phases, test it rigorously, and preserve a handoff that a new chat can continue from.

**Design.** The repository now has two test lanes. `.github/workflows/fast-checks.yml` runs on every branch push. It checks the exact update diff, runs Ruff on changed Python files, parses the discovered Python tree, runs focused edge/policy/README regressions, executes the deterministic stress suite, and verifies generated `docs/MAP.md`. The job has an eight-minute hard limit and per-branch concurrency; a newer push cancels a superseded run. `.github/workflows/verify.yml` retains the full Linux/Windows suite and proof gates for pull requests to `main` and pushes to `main`. No full test group was removed.

**Implementation and defects found.**
- Added `scripts/fast_verify.py` and `tests/test_fast_verify.py`.
- The fast runner rejects malformed NUL-delimited Git path output, invalid UTF-8 paths, duplicate/missing paths, traversal, drive-relative paths, file and directory symlink escapes, empty Python inventories, invalid source encodings, command failures, missing executables, and timeouts.
- The first full PR run found that the new runner exceeded ULTRON's existing function-size and complexity ceilings. The runner was refactored into smaller functions; the ceilings were not raised.
- The Windows run found a path-format difference: `Path.resolve()` returned a short Windows path alias, so `relative_to()` raised while reporting a syntax error. The diagnostic now falls back to a safe basename, and a regression test covers an external path with a different spelling.
- The expanded runner test count is 19. It also runs 30 policy/confirmation tests, 8 README contract tests, and 1,000 seeded repair stress scenarios.
- The generated module map check found stale `docs/MAP.md`; the map was regenerated with `scripts/map.py`, not hand-edited.

**Evidence.**
- PR #18 merged by squash as `eeacaf2ae2224edd91074a3853ae0ecff47c41a7`.
- Latest full main run [42830329187](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42830329187), on main baseline `4934d605fb1f3dbc332393191af083022162214b`: Linux and Windows passed. Each ran 2,073 tests, 1,000 stress scenarios, and 15 targeted seeded mutations. Proof gate: Linux 24 PROVEN / 13 PARTIAL / 0 FAILED; Windows 28 PROVEN / 9 PARTIAL / 0 FAILED. Windows native checks: 99 passed / 0 failed. Linux non-blocking instrument report: 17 passed / 2 failed / 15 skipped (no display server and no PulseAudio).
- Latest fast gate [42830329236](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42830329236): 309 Python files parsed; 19 + 30 + 8 focused tests passed; 1,000 stress scenarios passed; generated map check passed; 5/5 groups in 11.31 seconds.
- Archive run [42830329517](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42830329517) succeeded. It verified 12 exact-SHA archive tags, including the two later merged branch tips. Active tag ruleset `26923169` protects archive tags against updates and deletion.

**Current branch state.** Three refs remain: `main`, `docs/repository-doc-audit-2026-11-10`, and `ci/fast-branch-gate`. Both temporary refs belong to merged PRs, have exact-SHA protected archive tags, and have no open PR. Their branch refs have not yet been deleted. To finish, manually run `Archive reviewed branch tips` from `main` with `delete_branches=true`, `confirm_delete=DELETE ARCHIVED BRANCHES`, and `confirm_archive_tags=ARCHIVE TAGS PROTECTED`. The workflow checks the live ruleset and ref state before deletion; `main` is not deletable.

**Scope and limits.** No application runtime source changed in this work. The fast lane runs on Ubuntu/Python 3.12 and is a preflight, not a Windows or hardware proof. Package installation needs runner network access; test execution makes no live model or provider calls. PARTIAL and SKIPPED results are not passes. The GitHub connector used in this session did not expose workflow dispatch or branch deletion, so the final two-ref deletion is an owner UI action. The branch-protection endpoint also returned HTTP 403, so required-check merge blocking remains unverified. The required check names are documented in `docs/TEST_AUTOMATION.md`.


## 2026-11-10 — second-agent documentation handoff refresh

**Request.** Update the project documentation so a different AI agent can continue from the repository without access to this conversation.

**Live baseline inspected.**
- Main SHA before this documentation-only pass: `077793d7fd846f871f269362759d97c198ec61c5`.
- GitHub branch refs: `main`, `docs/repository-doc-audit-2026-11-10`, and `ci/fast-branch-gate`.
- Pull requests open: 0.
- Protected archive tags: 12, under Active ruleset `26923169`.
- PRs #17 and #18 are merged. The two temporary branch refs are exact-SHA archived but have not been deleted.
- Full verification [42832820093](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42832820093) passed on Linux and Windows: 2,073 tests per platform, 1,000 seeded stress scenarios and 15 targeted mutations per platform. Proof gate: Linux 24 PROVEN / 13 PARTIAL / 0 FAILED; Windows 28 PROVEN / 9 PARTIAL / 0 FAILED.
- Fast gate [42832819956](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42832819956) passed 5/5 groups in 13.12 seconds: 309 Python files parsed, 19 runner edge tests, 30 policy tests, 8 README tests, 1,000 stress scenarios, Ruff, and generated-map validation.
- Archive workflow [42832819947](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42832819947) passed and rechecked all 12 archive tags.

**Documentation updated.**
- Canonical handoff: `OwnerFiles/ULTIMATE_Context.md`.
- Agent entry points: `OwnerFiles/README.md`, `AGENTS.md`, `docs/AGENT_MAINTENANCE.md`, `docs/AGENT_PLAYBOOK.md`.
- Test and review operating guides: `docs/TEST_AUTOMATION.md`, `docs/CODE_REVIEW.md`, `GATEKEEPERS.md`.
- Current next actions: `docs/NEXT_CHECKPOINTS.md`.
- Branch history and cleanup: `docs/BRANCH_ARCHIVE.md`, `docs/BRANCH_REVIEW.md`.
- Historical checkpoint explicitly superseded: `docs/MAYBE_COMPLETE.md`.
- Navigation/public development guidance: `docs/INDEX.md`, `readme.md`.
- Durable decisions and chronology: `DECISIONS.md`, `OwnerFiles/history/session-log.md`, and `OwnerFiles/history/journey.md`.

**Explicit unresolved actions.**
1. Delete the two already-archived branch refs using the manual `Archive reviewed branch tips` workflow and its exact confirmation inputs. Do not delete `main` or any archive tag.
2. Configure and read back required branch-protection checks on `main`: `fast offline gate`, `linux — suite and instruments`, and `windows — the machine the claims are about`. The GitHub branch-protection API returned HTTP 403. Automatic workflow runs do not prove merge blocking.
3. Run `python scripts/verify_all.py` on the owner's Windows machine for hardware and interactive checks when available.
4. Vercel preview remains owner-authorized work, not an approved automatic task. The web client is still an authentication/workspace shell with a disabled composer.

**Scope.** This was documentation and repository-governance work. No application runtime source changed. `docs/MAP.md` was not regenerated because no Python module or test relationship changed. The old `HANDOFF.md` and `OwnerFiles/history/previous-handover.md` remain historical/superseded records; `OwnerFiles/ULTIMATE_Context.md` is the current handoff. PARTIAL and SKIPPED are not passes.


### Fast-gate formatting correction — 2026-11-10

Fast gate [42854158231](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42854158231) caught two trailing newline characters at the end of `OwnerFiles/history/journey.md` (`git diff --check`: “new blank line at EOF”). The extra blank line has been removed. No test assertion, source code, or workflow rule was changed. The full verification run [42854158323](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42854158323) passed Linux; Windows was still running when this correction was prepared. Fresh Actions runs will verify the corrected head.


## 2026-11-10 — full documentation refresh for handoff to another AI agent

**Request.** Update the project documentation so another AI coding agent can take over without relying on this conversation.

**Live state checked from GitHub.**
- Main SHA: `b80919314f391e15ddd86e2860c2e4d66057b15b`.
- Branch refs: `main`, `docs/repository-doc-audit-2026-11-10`, and `ci/fast-branch-gate`.
- Open PRs: zero. PR #17 and #18 are merged. PR #19 (`chore: trigger CodeRabbit review`) is closed without merge.
- Archive tags: 12 exact-SHA tags. Active ruleset `26923169` protects `refs/tags/archive/**/*` from updates and deletion.
- The two temporary branch refs are already archived and merged, but their refs remain pending guarded deletion.
- The repository About description is blank (`description: null`).
- The branch-protection endpoint returned HTTP 403. Required status-check enforcement remains unverified.

**Latest verification on the exact main SHA.**
- Fast gate [42855680649](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42855680649): success; 5/5 groups in 12.68 seconds; 309 Python files parsed; 19 runner edge tests, 30 policy tests, 8 README tests, and 1,000 seeded stress cases passed.
- Full Linux/Windows [42855681003](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42855681003): both jobs passed; 2,073 tests, 1,000 seeded stress cases, and 15 targeted mutations per platform. Proof gate: Linux 24 PROVEN / 13 PARTIAL / 0 FAILED; Windows 28 PROVEN / 9 PARTIAL / 0 FAILED. Windows native checks 99 passed / 0 failed. Linux instrument report 17 passed / 2 failed / 15 skipped (no display server and no PulseAudio).
- Archive [42855681028](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42855681028): success; 12 archive tags verified.

**Documentation reviewed and updated.**
- `OwnerFiles/ULTIMATE_Context.md`: current main SHA, runs, branch and PR state, proof counts, known limits, and next-agent instructions.
- `docs/NEXT_CHECKPOINTS.md`: ordered repository and owner-gated actions.
- `GATEKEEPERS.md`, `docs/TEST_AUTOMATION.md`, and `docs/CODE_REVIEW.md`: current test evidence, required-check limitation, and PR #19 status.
- `docs/BRANCH_ARCHIVE.md`: current branch refs, archive tags, and guarded deletion procedure.
- `readme.md`: project map now links directly to the agent playbook and test automation guide.
- Existing root `AGENTS.md`, `WORKING-PHILOSOPHY.md`, `docs/AGENT_MAINTENANCE.md`, `docs/AGENT_PLAYBOOK.md`, `docs/AGENT_WORKSPACE.md`, `docs/AGENT_NOTION.md`, `docs/INDEX.md`, and `OwnerFiles/README.md` were read and found consistent with the current main-only default, mandatory handoff, and test lanes. They were not rewritten unnecessarily.
- `HANDOFF.md`, `docs/MAYBE_COMPLETE.md`, and `docs/BRANCH_REVIEW.md` remain historical records. Their older SHAs are not current status claims.

**Next actions for the incoming agent/owner.**
1. Delete `docs/repository-doc-audit-2026-11-10` and `ci/fast-branch-gate` through the guarded archive workflow. Preserve `main` and all 12 archive tags.
2. Configure and read back the required `main` checks: `fast offline gate`, `linux — suite and instruments`, and `windows — the machine the claims are about`. Do not claim merge blocking until the settings are verified.
3. Set the GitHub About description using repository settings; suggested text is in the canonical handoff.
4. Run `python scripts/verify_all.py` and the live proof gate on the actual owner Windows machine when authorized.
5. Treat Vercel preview as owner-authorized work only. Do not create projects or add secrets without approval.

**Scope.** Documentation and handoff only. No application runtime source or test code changed. `docs/MAP.md` was not regenerated because no Python module/test relationship changed. No branch refs or archive tags were deleted. No external AI review integration was enabled.


## 2026-11-11 — ULTRON repository coherence and live-state audit

**Request.** Audit whether the repository's code and documentation agree. Correct stale handoff and navigation details without inventing completion or removing history.

**Live state checked.** Current `main`: `e1237d2e82ad7b981362f009baf568f7873415ea`. Branch refs: `main`, `docs/repository-doc-audit-2026-11-10` (`9074b986c9379ff2b2f320916616763a735df972`), and `ci/fast-branch-gate` (`e0072889ca333f5b8193f7d85b4ef912bf4aa10d`). There are 12 exact-SHA archive tags and zero open PRs. All three workflow runs succeeded on current main: full Linux/Windows [42876494213](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42876494213), fast gate [42876494264](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42876494264), archive-only [42876494242](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/42876494242).

**Findings corrected.**
- Current handoff, next-checkpoint, test automation, and branch archive guides cited an older main/test run and did not separate the live HEAD from the application/test baseline.
- The successful archive workflow was archive-only. The two temporary branch refs still exist; they were not deleted.
- `docs/INDEX.md` used `docs/CAPABILITY_AWARENESS.md` from inside `docs/`, which pointed to a non-existent `docs/docs/` path.

**Changes.** Updated current commit and workflow references in `OwnerFiles/ULTIMATE_Context.md`, `docs/NEXT_CHECKPOINTS.md`, `docs/TEST_AUTOMATION.md`, and `docs/BRANCH_ARCHIVE.md`. Clarified that the application/test baseline remains `b80919314f391e15ddd86e2860c2e4d66057b15b`, while the current documentation-only HEAD is `e1237d2e82ad7b981362f009baf568f7873415ea`. Fixed the capability-guide link in `docs/INDEX.md`.

**Evidence and limits.** The fast gate passed 5/5 groups: 309 Python files parsed, 19 runner edge tests, 30 policy/confirmation tests, 8 README tests, 1,000 seeded stress scenarios, Ruff, whitespace checks, and generated-map validation. Current full Linux and Windows jobs both passed. The baseline ran 2,073 tests per platform, 1,000 stress scenarios, and 15 targeted mutations per platform; the current full workflow reran the same verification scripts after documentation-only commits. Proof counts: Linux 24 PROVEN / 13 PARTIAL / 0 FAILED; Windows 28 PROVEN / 9 PARTIAL / 0 FAILED. Hosted Linux instruments: 17 passed / 2 failed / 15 skipped (display server and PulseAudio unavailable).

**Still open.** Two temporary branch refs are archived and merged, but remain present. Delete them only through the documented manual workflow after its explicit confirmations and ruleset checks. Branch-protection read returned HTTP 403, so merge-blocking enforcement is unverified. GitHub About description remains blank. Owner-machine hardware/provider checks were not run. No application source or tests changed; `docs/MAP.md` was not regenerated. Historical records remain untouched.

---

## 2026-11-12 — provider failover wired into the conversation path

**Asked for.** A fresh plan after the upstream changes, then wire general
provider failover into the live conversation request path (the handoff's
standing general-failover limitation), with real applied results and minimal
words. Forge's monthly quota was exhausted, so the work was done directly.

**Live state checked (2026-11-12).** `main` at
`2b31d7723baf85fbfd439aab00df44306575b0cb`. The last two merged temporary
branch refs were deleted by the guarded archive workflow
([run 43080080807](https://github.com/tanushgargjanuary-bot/ULTRON---AGI-like-JARVIS/actions/runs/43080080807))
with all 12 recovery tags kept. The three required `main` status checks were
configured and read back as enforced. The GitHub About description was set and
read back. All recorded in the handoff.

**Built.** Branch `feat/provider-failover-wiring`, open as PR #20 against
`main`, two commits. `548ea66`: `core/routing_runtime.py` — `RoutedLLM.chat`
walks `RoutingTable.candidates()`; a rung that fails before it answers is
rested (quota 5 min, gone-for-today, unavailable 30 min — the one-shot
ladder's rests, reusing its classifiers) and the next allowed rung answers; a
rung that fails after words were spoken raises instead of switching; usage is
recorded only when a route actually answers. `main.py` registers every other
configured LLM as a fallback rung (local first) and reads
`paid_fallback_consent` / `data_fallback_consent` from `config/api_keys.json`
into the table's consent flags; paid and data-sharing rungs stay silent
without them. Five new tests in `tests/test_routing_runtime.py`;
`docs/MAP.md` regenerated. `38c87d8`: fixed a live bug found while passing the
gate — a local shadow in `_execute_tool_approved` made `tool_usage.note(name)`
raise `UnboundLocalError` on every approved tool call since 2026-11-06 (proven
by an AST scope check), and `outcome.unwrap` failed on `web_search` mirror
results; shadow renamed, `ruff.toml` scopes E402 for `main.py` (46 pre-existing
false findings), and `ToolPathScopeTests` pin the tool path.

**Evidence.** Local on the branch:
`pytest tests/test_routing_runtime.py tests/test_routing.py -q` — 48 passed;
`scripts/fast_verify.py` — PASS 5/5 (309 Python files, 1,000 stress scenarios,
0 live provider requests); full offline suite — 104 passed / 2 skipped; Ruff —
0 findings (was 48 on `main.py`). The PR runs the fast gate plus the full
Linux/Windows verification; merge is blocked until the three required checks
are green, by the now-verified branch protection.

**Still open.** Merge PR #20 only when all three required checks pass, then
remove the branch ref through the guarded archive workflow. A live outage
across real providers is still unproven (owner-machine `verify_all.py`).
Version numbering stays 1.2.38; bumps accompany owner build commits on
`main`.

**Consent gaps closed (2026-11-12, later the same day).** Sentinel's review of
PR #20 HEAD `b31ce5a` returned BLOCK with two medium findings; both were
verified in the code and fixed on the same branch. (1) Automatic failover onto
this machine skipped `local_fallback_consent`: `RoutingTable.candidates()`
gated only paid and data-sharing rungs, so a hosted outage could silently move
the conversation to an unapproved local model. `candidates()` now also
requires `allow_local_fallback`, wired from `local_fallback_consent` in
`main.py`; a locally chosen primary is unaffected. (2) `shares_data` was read
from the catalog but no catalog row set it, so the data-sharing gate never
fired; every cloud row in `providers/llm_openai.py` now carries
`shares_data: True` until the service's training policy is verified
(fail-closed; a verified service may set False in its own row). (3) Provider
failure text reached the log unscrubbed; `core/routing_runtime.py` now masks
URLs and credential-like runs (`_scrub`). Known limitation recorded: one
paid/data consent flag covers all hosted accounts (no per-provider consent).
Evidence: routing tests 52 passed; `scripts/fast_verify.py` PASS 5/5; Ruff
(E4,E7,E9,F) clean on all changed files; `docs/MAP.md` regenerated.

The branch's first full verify run (43084080659) failed on both OS jobs for
one reason only: `RealPolicyTests.test_main_py_routes_save_memory_through_the_gate`
grepped a fixed 1,200-character window of `main.py`, and the tool-path
rename's comments pushed `request_memory_write` past the window. The test now
reads the whole `save_memory` branch up to the next dispatch entry, so the
assertion is about the call site, not about comment length. Both OS jobs
failed only on this test (failures=1; 2,080 tests each). The gate also flagged
31 pre-existing duplicate-import findings in `tests/test_suite_safety.py`
(each merged section re-imported its stdlib/core names); those lines are now
removed, ruff is clean on the file, and the 69 tests still pass.

---

## 2026-11-15 — Swarm Bug Hunting, Core & System Hardening, README 100x

**Asked for.** Run a comprehensive multi-agent swarm to audit the codebase for bugs, verify and eliminate false positives, patch confirmed defects directly on `main`, update documentation, and upgrade `README.md` into a high-impact, visual showcase suitable for professional presentation.

**Built & Fixed.**
1. **Critical Dashboard 8-char Key Pairing (BUG-CRIT-01):** Fixed `dashboard/static/login.html` where input hardcoded `maxlength="6"` and auto-submitted 6 chars against `server.py`'s 8-character pairing secrets, eliminating the 100% 401 pairing lockout.
2. **Critical MCP Subprocess EOF Unhandled Hang (BUG-CRIT-02):** Fixed `custom_jarvis/mcp_client.py` where reader thread exited on subprocess termination/EOF without setting pending request events, eliminating the 120-second thread freeze.
3. **Provider Failover Timeout & Network Errors (BUG-HIGH-01):** Expanded `is_unavailable_error` in `core/gemini.py` to match timeouts, connect errors, 500, and 502 Bad Gateway responses, ensuring failing upstream routes rest appropriately rather than stalling loops.
4. **Next.js App Router Middleware Invariant (BUG-HIGH-03):** Renamed `webapp/proxy.ts` to `webapp/middleware.ts` with standard `middleware()` export, enabling Supabase silent session token refreshes.
5. **Config Manager Atomic Isolation (BUG-HIGH-05):** Refactored 9 public setters in `memory/config_manager.py` that open-coded `write_text` with empty dict fallback to use `_load_for_write()` and `_write_config()`, eliminating risk of catastrophic API key wipeouts.
6. **Action Mutex Bypass (BUG-HIGH-08):** Fixed `actions/screen_processor.py` to route camera index changes through `config_manager` rather than writing `config/api_keys.json` directly.
7. **Plugin Error Safety (BUG-HIGH-07):** Added `parameters = parameters or {}` defensive guard across 15 plugins to adhere strictly to the invariant that `run()` must never raise.
8. **UI Shutdown Thread Crash:** Protected `MainWindow` wake state emitter against `RuntimeError` on C++ object deletion during application termination (`ui.py`).
9. **README Overhaul:** Transformed `README.md` with visual architecture flowcharts, badges, feature matrices, quick starts, and verified contract assertions (all passing `tests/test_readme.py`).
10. **Swarm Bug Dossier:** Consolidated all findings into durable artifact `ULTRON_BUG_DOSSIER.md`. Verified with `scripts/fast_verify.py` passing 5/5 groups (309 Python files, 1,000 stress scenarios).

---

## 2026-11-20 — a review pass: two red gates, the safety gaps, and what the code really runs

**Asked for.** A review of the repository (bugs, risky code, missing tests, documentation gaps,
developer-experience faults, highest value first); then "fix all this and do an even deeper search
for more problems and feature malfunctions". Nothing was to be committed, pushed or merged. The
work is in the working tree of branch `arena/850afbc9-ultron-agi-like-jarvis`, cut from `main` at
`cf02c0e`.

**Method.** Read first, then ran. The suite and `scripts/verify.py` were run in clean copies of the
tree, with the full package set and with the lean set `verify.yml` installs (the lean run caught a
test of mine that needed FastAPI, which that job does not install). Every new test was also run
against the code it replaces and fails there. Besides the suite: a probe that calls every dashboard
route with malformed bodies, one that sends every bundled plugin junk arguments (it found nothing in
the plugins; the dispatcher raises on non-object arguments, which `main.py` never sends), the repository's debt scanner against its ceilings, and the real ruff on every touched file.

**Built & fixed** (detail and file names: `CHANGELOG.md`, "Review pass, 2026-11-20"):
1. **The gates.** The plugin dispatcher fault (every plugin call raised) and the provider self-test that
   `verify` has failed since `60ee7a3`; a dispatch smoke group in the fast gate; live workflow badges
   in the README; a lint step that fails a change for the findings it adds (`scripts/lint_ratchet.py`),
   Actions pinned to commits, Ruff pinned to `requirements-dev.txt`, upper bounds on every requirement,
   `webapp/package-lock.json` with `npm ci`, `.github/dependabot.yml`.
2. **Safety.** The system prompt can no longer be changed by the model alone (the second confirmation
   is the owner's click on a banner); `self_modify` asks on every call; the AST guardian's bypasses;
   `file_controller`'s credential deny-list and overwrite-on-copy/move; local-model failover needs
   `local_fallback_consent`; the dashboard (every JSON route, both sockets, downloads, `/auto-login`,
   the TLS key); AppleScript quoting; skill-pack ids; `tempfile.mktemp`.
3. **Data.** Settings and memory writes are atomic and never made from a failed read; `remember`,
   `forget` and the approved memory write say so when they did not save; the persona and identity paths
   in `ui.py` and `scripts/local_model.py` no longer write the settings file themselves.
4. **Honesty of claims.** The Rust core's status (a section in the evolution spec, a test that fails when
   `main.rs` and the sentence disagree), the sealer marked experimental, the pipe name, test files named
   in `DECISIONS.md` and `ARCHITECTURE.md` that do not exist, `GATEKEEPERS.md`' stale claim count, the
   merge-enforcement text (read from GitHub: required checks exist and bind everyone but administrators).
5. **Smaller:** the IPC frame cap, the loops started inside the dashboard's `try`, a file handle in
   `measure_code`, child output logged instead of discarded for the two programs the app depends on,
   `scripts/map.py`'s closing line, dead code in `scripts/verify.py`, a CryptoJS licence notice.

**Evidence.** Linux, Python 3.11.2: full suite 2,442 tests, 0 failed, 9 skipped; `scripts/verify.py`
with the CI package set exits 0 (suite 2,442 / 48 skipped, provider and UI self-tests 99 of 99, 1,000
stress scenarios, 15 of 15 mutations detected, no new module-map gap, migration checks passed); proof gate
24 PROVEN, 13 PARTIAL, 0 FAILED over 37 claims (the same as the last hosted Linux run); fast gate 6 of 6
groups over 345 Python files; lint ratchet against `cf02c0e`: 141 findings in the 68 touched files, 151 at
the base. Before: cf02c0e ran 2,101 tests and 32 failed in both environments (29 from the plugin dispatcher fault, 3 from the repository's own debt-ceiling tests). Debt measures are all within their ceilings (swallowed 152 of 157,
print-in-library 252 of 254, complex 107 of 108, no-timeout 43 of 45, no-module-docstring 16 of 18).

**Not checked.** Windows, macOS, GitHub Actions (workflow edits parse and have not run), the Rust and Go
code (no toolchain; the one Rust edit is uncompiled), Python 3.12 and 3.13, real keys, audio and display.
Found by reading and not reproduced: the Job Object limits in `native/ultron-core/src/process/supervisor.rs`
(a second `SetInformationJobObject` call can replace the first call's limits; the code was left unchanged
at this point and is changed in the follow-up entry below, still uncompiled) and the Windows
drive-relative download name.

**Left for the owner** (`DECISIONS.md`, "Open questions"; `docs/specifications/SYSTEM_OVERVIEW.md`):
whether administrators may bypass the required checks (`enforce_admins` is false; only the owner can
change it); whether to keep the lint ratchet; `laptop_wide_access` defaulting to on; a real panel button
for `self_modify`'s second confirmation (a referee file); what to do with the archive workflow that runs
on every push to `main`; whether to lower the debt ceilings to the new measures; the unused vendored
`crypto-js.min.js`; and the two referee-file edits above, which should be read before anything else.

## 2026-11-21 — follow-up: twelve findings from a second review of the review pass

**Asked for.** "Use this repo to code review" (github.com/alibaba/open-code-review) on the working tree, then
"Dont ask before making a fix". Same constraints as the entry above: nothing committed, pushed or merged; the
work is in the working tree of `arena/850afbc9-ultron-agi-like-jarvis`.

**Method.** The tool (npm package 1.14.0, installed with `--ignore-scripts`; its release binary's checksum matched the
npm copy) was run in *delegation* mode: it lists the changed files, prepares each file's diff and prints its
rules; it has no model of its own in that mode, so the reading and every finding were done by the agent that wrote
the first pass: a second look with a checklist, not an outside reviewer. It set 55 of
the 103 changed paths aside (31 tests, a lockfile, 23 documents); those were not reviewed. The other 48 were all
read. The tool's update check was switched off and it ran with a scratch home folder. Its own claims
(benchmarks, telemetry) were not checked. The report was written to a scratch folder outside the repository,
which a sandbox reset has since removed; the twelve findings are recorded here and in `CHANGELOG.md` instead.

**The twelve, highest first, and what was done** (detail: `CHANGELOG.md`, "Follow-up to the review pass"):
1. HIGH — the prompt-change banner dropped lines starting `++`/`--`, cut at 900 characters, drew the model's
   reason as HTML, and the window clipped every banner silently. Fixed (`core/display_text.py`, `ui.py`,
   `actions/prompt_editor.py`); a change over 4,000 characters of difference is refused, not shown in part.
2. HIGH — `.gitignore` missed the memory store's set-aside and temporary files, and `ship` runs `git add -A`. Fixed.
3. MEDIUM — `scripts/local_model.py` left the key file (and its backup) readable by other users. Fixed.
4. MEDIUM — the Linux proof-gate step could not fail the job (`| tee`). Fixed, simulated, not run on GitHub.
5. MEDIUM — the AST guardian's header said it "can only over-report". Rewritten, the code made to match, each
   remaining limit named and pinned by a test. **Referee file.**
6. LOW — `core/tool_usage.py` wrote settings on the event loop. A writer thread now, `main.py` untouched.
7. LOW — `wallpaper_url` followed `file://` and local addresses. Now the page reader's checks.
8. LOW — the Job Object supervisor (Rust). Rewritten by reading; uncompiled, unrun, and nothing calls it.
9. LOW — `verify.yml` had no `permissions:` and cancelled runs on `main`. Fixed.
10. LOW — the dashboard login throttle never forgot an address. Bounded.
11. LOW — dead stores in `_select_persona_theme`. Removed; the switch has a test now.
12. LOW — the lint ratchet's description promised more than it checks. Weakened to what is true, with a test.

**Method for the fixes.** Every new test was also run against the code it replaces and fails there; where a test
could not fail on the old code because the old code's behaviour was identical (the dead stores, who the throttle
blocks) it is a structural or an equivalence test, and says so. The guardian's tests were run against the original
file as well: 9 of the 27 tests fail (119 sub-cases). The refusal count was measured before and after each guardian change.
Failures found on the way: the repository's debt ceilings caught six new "no-timeout" findings (49 against a ceiling
of 45: three `put` calls on a queue, which the scanner reads as an HTTP verb, and three `mock.patch("...")` calls,
which it reads as HTTP PATCH) and two over-deep functions in the guardian (28 against 26); the lint ratchet caught a
new unused local and an import after code. All of them were fixed in the code, not by raising a ceiling.

**Evidence** (Linux, Python 3.11.2, a clean two-commit copy: the base tree, then the working tree):
- package set `verify.yml` installs: `scripts/verify.py` exits 0; 2,631 tests, 0 failed, 39 skipped; provider and UI
  self-tests 108 of 108; 1,000 stress scenarios; 15 of 15 seeded mutations detected; no new module-map gap (22 inherited);
- full package set: `scripts/verify.py` exits 0; 2,631 tests, 0 failed, 10 skipped;
- proof gate 24 PROVEN, 13 PARTIAL, 0 FAILED (37), unchanged; `self_modify`, `triggers` and `procwatch` PROVEN, so
  the gate's checks of `tool_usage.note(name)` in `main.py` and of the counter still pass;
- fast gate 6 of 6, 354 Python files parsed;
- lint ratchet against `cf02c0e`: 141 findings in 78 touched Python files, 151 at the base: nothing got worse;
- debt ceilings: all within; at the ceiling: `long-function` 97, `typed-exception-discarded` 82, `hardcoded-address` 37,
  `deep-nesting` 26, `address-in-constant` 19, `duplicate-body` 11, `dangerous-call` 1, `high` 0.
- the guardian refuses 116 of 354 Python files now and 115 under the original; the one newly refused is
  `custom_jarvis/addon_runtime.py` (`marshal`, `__code__`).

**Not checked.** Windows, macOS, GitHub Actions (the `verify.yml` change parses as YAML and was simulated under
`bash -eo pipefail`; it has not run), the Rust (`supervisor.rs`, and `ipc/server.rs` from the entry above; no
toolchain), the banner on a real screen (offscreen only), Python 3.12 and 3.13, real keys, audio.

**Found, not changed at the time (a referee file; done in the next entry).** `core/self_change.py` `diff()`: a line
added a second time elsewhere is not shown; a line removed from one place that still stands in another is reported as
"only the order of lines changes"; past 40 lines (20 when proposing) the rest is cut with no marker. Probed in a
scratch copy. The `self_modify` banner shows the call's arguments, not the change. Untouched then because the file is
a referee file.

**Left for the owner at the end of this entry** (all but the first and the last were done in the next entry): read
the referee edits (`core/policy.py` and `core/ast_guardian.py` twice); the `diff()` problem and whether
`core/self_change.py`'s rehearsal copy (it skips `.git` and `.github`, so a full rehearsal fails) may be edited; a real
second-confirmation button for `self_modify`; the earlier open questions; and whether to commit and open a pull
request.

## 2026-11-21 — follow-up: what was left (the self-change pipeline, a referee file)

**Asked for.** "Do everything that's left, and give me a small CEO note." The owner had been left five questions at
the end of the entry above; four of them were work (the referee file `core/self_change.py` and a real second
confirmation for `self_modify`, a guard that puts back a self-change that stops the program from starting, an
optional check in `custom_jarvis/ship.py`), plus commit and pull request. The fifth, which "100%" he means, is a
question and stays open. I read "everything that's left" as the go-ahead to edit `core/self_change.py`. It is a
referee file: every edit to it is flagged here, in `CHANGELOG.md` and in `DECISIONS.md`.

**What was done** (detail: `CHANGELOG.md`, "Follow-up: what was left"):
1. `core/self_change.py`: `diff()` is a real diff (written once, in `core/display_text.py`, and shared with the
   system-prompt banner), says how many rows it did not show; the rehearsal copy keeps `.github` and gets a one-commit
   repository of its own (a full rehearsal of this repository used to fail 9 tests and error on 6); a file's line
   endings survive a change and a put-back (`revert` said "exactly what it was" over a different file for Windows
   line ends); a file that is not valid UTF-8 is refused; four more files are off limits (`core/boot_guard.py`,
   `scripts/bootstrap.py`, `run.bat`, `run.ps1`).
2. `actions/self_change.py`: the second confirmation is a button press on a banner that lists every changed line. The
   tool takes no `channel` and ignores one. On HEAD the sequence propose, rehearse, confirm voice, confirm panel, apply
   printed `Applied: app.py` with no person involved beyond the per-call banners; it is refused now.
3. New `core/boot_guard.py`, run first by `scripts/bootstrap.py`, armed and cleared by `main.py`: a code change is
   recorded before it is written, marked started on the next launch, put back at the launch after if it never proved
   itself (45 seconds up, or a normal end, and not if the assistant's thread died).
4. `custom_jarvis/ship.py` `guards()`, `.gitignore`: `config/self_change/` was not ignored while `ship` runs
   `git add -A`; it is now, and `guards()` refuses a ship while git would add any non-source file in `memory/` or
   `config/`.
5. **Found while building the button, and fixed:** the model's own click and key-press tool (`computer_control`, a
   routine tool, no banner) could answer any confirmation banner with `press tab` then `press space`. The banner
   defaults to CANCEL, which stops Enter, not that. `core/custom_gate.py` now refuses every call that is not
   read-only while a confirmation is waiting. Two gaps are left and named (open question 5 in `DECISIONS.md`): a call in
   the same message as the one that raises the banner, and anything that does not come through the dispatcher.
   `docs/PROMPT.md` and `DECISIONS.md` said the model "cannot press" the button; they say what is true now.

**Method.** Every new group of tests was run against HEAD's version of the file it covers and fails there (CHANGELOG
has the counts). Four of my own mistakes were caught by the checks, not by reading: the debt scanner counted two
duplicated function bodies (`_diff_rows` copied into `core/self_change.py`, and a button helper copied into the test)
and then the `.put(...)` calls of a test helper as HTTP calls without a timeout; the lint ratchet counted two
more imports after code; and a rehearsal copy test showed I had read the original file after opening it for writing, which
emptied it. A first version of the rehearsal repository (`git init` only) made `ship.guards()` fail in the copy,
because nothing was tracked; the copy gets one commit. Probed, not guessed: the line-ending fault (a Windows file
came back with Unix line ends), the missing ignore rule (`git check-ignore` on the real names), and the two-call
button press (the dispatcher test refuses `press tab` and `press space` while a banner waits).

**Evidence** (Linux, Python 3.11.2, a clean two-commit copy: the base tree, then the working tree; the first run of
this chain failed one test, which was a document naming a runtime file; fixed and re-run):
- package set `verify.yml` installs: `scripts/verify.py` exits 0; 2,751 tests, 0 failed, 39 skipped; provider and UI
  self-tests 108 of 108; 1,000 stress scenarios; 15 of 15 seeded mutations detected; no new module-map gap (22 inherited);
- full package set: `scripts/verify.py` exits 0; 2,751 tests, 0 failed, 10 skipped; self-tests 108 of 108;
- proof gate 24 PROVEN, 13 PARTIAL, 0 FAILED (37), unchanged; `self_modify` PROVEN (the gate checks the counting rule
  in `core/self_change.py` directly, not the button; the button is tested in `tests/test_self_change.py`);
- fast gate 6 of 6, 357 Python files parsed;
- lint ratchet against `cf02c0e`: 146 findings in 88 touched Python files, 156 at the base: nothing got worse;
- debt ceilings: all within; at the ceiling: `long-function` 97, `typed-exception-discarded` 82, `hardcoded-address` 37,
  `deep-nesting` 26, `address-in-constant` 19, `duplicate-body` 11, `dangerous-call` 1, `high` 0; `no-timeout` 43 of 45;
- the guardian refuses 117 of 357 Python files now and 116 under the original; the one newly refused is still
  `custom_jarvis/addon_runtime.py`;
- a full rehearsal of this tree (`core.self_change.rehearse(full=True)`, run in a copy of it): exit 0 in 112 seconds.
  On the same repository before the copy fix: 9 failures and 6 errors, 74 seconds;
- the count of tests: 2,101 at `cf02c0e` (32 failing), 2,442 after the first pass, 2,631 after the second, 2,751 now.

**Not checked.** Windows, macOS, GitHub Actions (this branch's pull request will trigger them), the Rust and the Go,
the banner and the dispatcher check with the real window, `run.bat` and `run.ps1` with the boot guard (only the
launcher's Python step and real child processes were run), Python 3.12 and 3.13, real keys, audio.

**Left for the owner** (`docs/specifications/SYSTEM_OVERVIEW.md`): read the referee edits (`core/self_change.py` this
time, with the new four off-limits files; `core/policy.py`; `core/ast_guardian.py`); whether to close the two gaps in
the dispatcher check; which "100%" he means; and the earlier open questions.

## 2026-11-21 — follow-up: the first Windows run of the pull request

**Asked for.** Nothing new: the previous entry listed Windows under "Not checked", and the owner's standing
instruction is to fix without asking first. This is what the first Windows run said, and the fix.

**What the run said.** Pull request #22, run 44930501422, the Windows job: 2,751 tests, 8 failures and 1 error, in
five test files. Four of the files are new in this branch (`tests/test_verify_script.py`,
`tests/test_workflow_hygiene.py`, `tests/test_config_safety.py`, `tests/test_applescript_quoting.py`); the fifth,
`tests/test_self_change.py`, broke because this branch made `run.ps1` a protected file and its fake project writes
every protected file. The suite never got as far as the steps after it or the proof gate, so what they do on Windows
is still unknown. The log was read from the job's own log (the run's artifact could not be downloaded from this
sandbox).

**What was done** (table and reasons: `CHANGELOG.md`, "First Windows run of this pull request"):
1. `scripts/verify.py` returns forward-slash names (four failing tests), with a new test that is red on the old file
   on any system (a real path whose `relative_to` answers like Windows).
2. The restart-line test was replaced by three that pin `os.name`; the program is unchanged.
3. Two workflow tests skip on Windows, one wallpaper test skips where a file name cannot hold a double quote.
4. The burst test's reader pauses 5 ms on Windows. This one is a reading, not a reproduction.

**Evidence** (Linux, Python 3.11.2): the five changed modules ran 145 tests at the previous commit and 148 now; the new
`scripts/verify.py` test fails against the old file; three probes made Linux behave like the Windows run (the file
system refusing a quoted name gives a skip, not an error; the bash helper answers "none" on `nt`; the old restart
assertion fails under `nt` with a launcher present, which is the message the Windows log showed).

**Whole tree** (Linux, Python 3.11.2, a clean two-commit copy, the same chain as the entry above): `scripts/verify.py`
in the package set `verify.yml` installs exits 0 with 2,754 tests, 0 failed, 39 skipped, provider and UI self-tests
108 of 108, 1,000 stress scenarios and 15 of 15 seeded mutations; the full package set exits 0 with 2,754 tests, 0
failed, 10 skipped; the proof gate is 24 PROVEN, 13 PARTIAL, 0 FAILED; the fast gate is 6 of 6; the lint ratchet
against `cf02c0e` is 146 findings against 156; the module map is fresh.

**Not checked.** All of it on Windows: it is only run by a push. The burst-test cause is inferred. The `bash` that
failed on the runner is inferred from an exit code. Whatever the steps after the suite do on Windows is unknown, so a
second Windows failure after this one would not be a surprise.

**Left for the owner.** The same list as the entry above, and one thing more: whether the branch may be pushed again to
let GitHub run Windows (no push has been made since the pull request was opened).

## 2026-11-22 — follow-up: the second Windows run, and the proof gate's first word on Windows

**Asked for.** "Yes, push and watch Windows": the owner's answer to the first step of the plan for following upstream Mark
releases (finish pull request #22 first). The nine test fixes were committed (`2377b3a`) and pushed, and the run was read.

**What the run said.** Run 45003997382, the Windows job. The suite step passed for the first time on Windows: 2,754 tests,
71 skipped, 353 s; self-tests 108 of 108; 1,000 scenarios; 15 of 15 mutations; the module map. The proof gate, which had
never run on Windows in this pull request, then reported 28 PROVEN, 8 PARTIAL and 1 FAILED. The failed claim is `acts`: a
write to a path outside the owner's folders was not refused. The log was read through the job's log (the artifact cannot be
downloaded from this sandbox). Linux, the fast gate, reviewdog, web-checks and CodeFactor passed; Kilo's review did not run
("insufficient credits"; not a required check).

**Cause.** The file tool adds every existing drive to its folders on Windows unless `laptop_wide_access` is `false`. That
was added in `cf02c0e` (2026-11-15) with the default on. The Windows gate last passed on `e1237d2` (run 42876494213, 2026-11-10) and has not
run on `main` since, because the suite step failed first. The question was already in `DECISIONS.md` (open question 4)
and was unanswered. Read from the code, not reproduced on Windows: the runner's `/tmp/x` is `D:\tmp\x`, and `D:/` is a root.

**What was done.** `actions/file_controller.py`: the drives are added only when the settings hold a saved boolean `true`.
Four tests in `tests/test_file_controller_hardening.py` (`TheRoots`), red on the old file. `DECISIONS.md` question 4 now says
what happened and that it is the owner's to overrule. No referee file was edited, no test loosened, the proof gate untouched
(it was right: its claim was false as shipped).

**Evidence** (Linux, a copy of the tree, bare Python 3.11.2 with none of the repository's packages installed): the four new tests fail against the old
`actions/file_controller.py` and pass now; the whole suite ran 2,072 tests at the previous commit and 2,076 now, with the
same 30 environment failures (missing packages, no repository in the copy) in both.

**Not checked.** Windows after this change. The full chain on Linux was not re-run here; the hosted run on the pushed commit
is the record. A Windows test that passed only because D: was a permitted root would show up in the next run.

**Left for the owner.** Keep the opt-in default, or restore the old default and change the proof gate's claim (a referee
file). The merge of pull request #22, once the three required checks are green. The plan for following upstream Mark releases
(the four answers are in the conversation: nothing that speaks news or runs by itself at launch; the new window layer last;
a weekly read-only report; finish this pull request first).

## 2026-11-22 — following upstream Mark: a read-only check, a weekly report, and what stays out

**Asked for.** The original Mark was updated (it is now Mark LVII). The owner wants its newest features in Ultron, with excluded features such as news read out when the assistant opens kept out, and wants Ultron to follow every future Mark "with a system which handles the feature collision and bugs". A plan came first; his answers were the strictest exclusions, the new window layer (`gui/`) last, "report only", and drive-wide file access staying opt-in. Then he asked for `addyosmani/agent-skills` and `anthropics/skills` to be used as the working method (state assumptions, test first, small commits, a review before each pull request) and `alibaba/open-code-review` for that review.

**What was done.** Ten commits on `arena/8c75f708-ultron-agi-like-jarvis`, cut from `main` at `df115bb`:

1. `b8bef93`, `scripts/verify.py` keeps the report and the last line when a step dies of a native crash. The hosted run of PR #22's merge had ended with one line, "exit -11". The cause is **not** found.
2. `0404fb0`, `docs/MAP.md` for that tree. The fast gate had gone red on the previous commit because the map was stale.
3. `836ec7d`, `scripts/upstream_sync.py` with its tests and guide, and the pin, ledger and exclusions in `docs/upstream/`.
4. `b57f806`, the weekly workflow `.github/workflows/upstream-watch.yml`, its tests and the guide's weekly section.
5. `e892999`, names, links and folders that come from upstream are not trusted (below).
6. `548d1c7`, the record: changelog, decisions (section 8, open question 4 answered, five table rows), the maintenance procedure, the index, the Mark LVII review in `docs/UPSTREAM_RESEARCH.md`, this entry, `log.txt` and the handoff.
7. `c3e6b09`, the fix for what the first hosted run found (below): three faults in the new tests.
8. `1abb11f`, four sentences corrected once the run on `c3e6b09` had passed.
9. The fix for one test that failed by chance on Windows (below).
10. The Dependabot limit and the branch clean-up (the entry after this one).

**Review of the finished work.** A first read found five faults, all fixed test first (the old script and workflow showed 41 red items): relative imports were not followed; the weekly job never closed its issue; one unparsable Python file stopped the report; a git failure was read as "no such file"; and text from upstream could break the report's formatting. A second read, against the rules `ocr delegate rule` prints for these file types (that mode calls no model: it prints the rules, and the reading was done by hand), found three more: a path check that knew only POSIX rules (Windows reads `a\..\b`, `C:x` and `x.txt:stream` differently), a symlink followed out of the clone and a folder named like a module that crashed the run, and data-file lists that were not lists. Fixed test first; a mutation check of those guards caught 15 of 15 after a first run that caught 11 of 14 (a redundant condition removed, an unreachable branch given a test).

**What the first hosted run said.** The pull request's first run (run 45033789440, `548d1c7`) failed on both systems in the suite step, three faults in the new tests and none in the script. Local runs had used Python 3.11 on Linux; CI uses 3.12 on Linux and Windows. (1) A fixture of 5,000 nested operators, meant to be too deep to parse: CPython 3.12.16 on Linux parses it (100,000 raises `MemoryError`), Windows 3.12.10 and 3.11 refuse it. Reproduced on a 3.12.16 built from source with the old tests, the same two failures by name. (2) A fixture named `actions/nul.py`: a device name on Windows, so git could not add it. (3) The control for the `verify.py` change used `ctypes.string_at(0)` to crash, which on Windows raises an `OSError` instead of crashing, so the child flushed its line. Fixed: no test needs a depth any more, a device name is refused by the fixture writer on every system, and the child calls `faulthandler._read_null()`. That the last one crashes for real on Windows was a reading of CPython when it was written, and it held. `verify.py` stops at the first failing step, so the later steps had not run on this pull request until the next run. **The run on the fixed commit** (`c3e6b09`, run 45036131001) passed on Linux (Python 3.12.16) and Windows (3.12.10) in every step, the proof gate on Windows included (28 PROVEN, 9 PARTIAL, as on the merge of pull request #22).

**One test failed by chance on Windows.** The run on `1abb11f` (run 45037801726, documents only) was green on Linux and red on Windows in `test_gemini_resilience.LadderBehaviour.test_an_exhausted_model_is_rested_for_the_quota_time`: `300.00000000000006 not less than or equal to 300`. The test is from pull request #22. It reads a rest time back as `deadline - now`; Python 3.12's Windows clock moves in 15.6 ms steps, so two reads can agree, and `(t + 300) - t` is not always exactly 300 in floating point (212.007 s gives the failing value; 23% of ticks between 212 and 512 s of uptime do). The sibling test for the 30-minute rest has the same fault (13 to 25% of ticks between 212 and 2,048 s). Fixed in the test file only: `core/gemini.py` sees a clock standing at 1,000.0, and two `assertLessEqual` became `assertEqual` (**replaced assertions, flagged**; each is stricter). Old tests at the bad seconds: the same message; new tests: pass. Six planted wrong rest times: the new tests catch six, the old three. How often it fails is not measured, and Windows itself has not run the fix yet.

**Evidence.** Linux, Python 3.11.2, a copy of the tree with the CI package set: `unittest discover` runs 2,730 tests on this branch's code and 2,597 on pristine `main`, with the same three failures in both (inherited, not touched here), 59 skipped. `tests/test_upstream_sync.py` has 130 tests, each against a real git repository built in a temporary folder, and it and `tests/test_verify_script.py` also pass (145 tests) on a CPython 3.12.16 built from source. The check on a clone of Mark LVII's head (`752ff61`): exit 20, 54 files differ, 17 held, two stop signs (`certifi`, `AGENTS.md`); the same answer before and after the script was corrected. The hosted fast gate: red on `b8bef93` (stale map), green on `b57f806` (run 45031276946).

**Not checked.** The seven workflow-step tests on Windows (they skip there on purpose and ran on Linux). The schedule, which only runs from `main`. The issue steps on GitHub, which were run with a stand-in `gh`. macOS, Rust, Go. None of Mark LVII's code was run, because none was taken.

**Left for the owner.** "Go" for the first catch-up slice (small proven fixes, test first, switched off by default). Merging this pull request (pull request #33; read the latest run on it first). Dependabot's ten pull requests (#23 to #32) were closed on 2026-11-24 (next entry). Pull request #21. Questions 5 and 6 in `DECISIONS.md`. The three referee files edited in PR #22 (`core/self_change.py`, `core/policy.py`, `core/ast_guardian.py`) are still waiting to be read by the owner.

## 2026-11-24 — branch clean-up: fourteen branches to four

**Asked for.** "Why are there a lot of branches? Is everything okay? How will we fix this?", then "Fix this."

**What was found.** Fourteen branches: `main`; this pull request's branch; `arena/850afbc9-ultron-agi-like-jarvis` (merged as #22, kept because "Automatically delete head branches" is off; GitHub says 0 commits in it that `main` lacks); `feat/computer-use-skills` (#21, opened 2026-11-13, 2 commits, 22 files, 26 commits behind `main`); and ten `dependabot/*` branches for #23 to #32, all opened at 09:32 on 2026-11-22 by the `.github/dependabot.yml` that #22 added. The file's comment said "one pull request per ecosystem at a time", its limits said 2, 3 and 3, and Dependabot opened 4, 4 and 2; why is not known. The twelve `archive/…` names are tags (five fully inside `main`, seven holding commits `main` lacks), not branches.

**What was done.** #23 to #32 closed without merging, with a comment, their branches deleted (14 became 4, read back). `.github/dependabot.yml` now has `open-pull-requests-limit: 1` and one catch-all group per ecosystem. Deleting it was the first plan and was not done: `DECISIONS.md` ("a pin has a reason") and `test_dependabot_keeps_the_pins_moving` name the file. A new test, `test_dependabot_opens_one_grouped_pull_request_per_ecosystem`, is red on the old file and green on the new; it catches six of six planted faults, the older test one (unchanged). Documents that said the ten were open were corrected.

**Could not be done.** "Automatically delete head branches": HTTP 403 "Resource not accessible by integration" for this account. Still off.

**Left for the owner.** The switch (Settings, General, Pull Requests). "Delete branch" on pull request #22. Pull request #21: keep or archive (the guarded archive workflow only handles its fixed list of reviewed branches, so archiving #21 means adding it there or tagging its tip by hand). Checked: Dependabot's own check on the pull request ("Dependabot config file validation: All changes look good") accepted the file. Not verified: what it opens after the merge (up to three grouped pull requests, once); whether security fixes are on for this repository.

## 2026-11-24 — the upstream check looks nine times a month

**Asked for.** He said yes to merging pull request #33, "but instead of weekly check, it should check 9 times in a month."

**Assumptions.** (1) Nine looks in every calendar month, spread through it. (2) Cron cannot say "nine a month", so nine days are named, at the same 06:17 UTC: 1, 4, 7, 10, 13, 16, 19, 22 and 25. They stop at the 25th so February has all nine; a step such as `*/3` would be ten or eleven days in a long month. (3) The days are cheap to move, so no question was asked first. (4) His "yes" covers the merge once the change is in and the required checks are green.

**What was done.** Test first. `test_the_schedule_is_weekly` asserted the old behaviour and was **replaced (flagged)** by two tests in the class now named `TheScheduledWorkflow`: nine looks in every month of 2026 to 2033, and no wait longer than seven days. Both were red on the weekly line (`Tuples differ: ('*', '1') != ('*', '*')`) and green after the change to `.github/workflows/upstream-watch.yml`. A class, a docstring, a section comment and a test name that said "weekly" or "every week" were renamed. Documents corrected: `CHANGELOG.md`, `DECISIONS.md` (section 8 and the row on a check that cannot run), `docs/UPSTREAM_SYNC.md`, `docs/AGENT_MAINTENANCE.md`, `docs/INDEX.md`, `docs/UPSTREAM_RESEARCH.md`, `docs/specifications/SYSTEM_OVERVIEW.md` and `docs/MAP.md` (line counts). Entries above this one that say "weekly" were true when they were written. The guide said to switch the schedule off by reverting the commit that added the workflow; a later commit now changes that file, so it says to delete the file.

**Evidence.** 17 planted wrong schedules were all refused and four right ones passed (the list is in `CHANGELOG.md`). From GitHub's documentation, read on docs.github.com on 2026-11-24: the comma is a list operator in any of the five fields; a schedule runs only from the default branch; it can be delayed, most at the start of an hour; a public repository's schedules are switched off after 60 days with no repository activity. The hosted run on the pushed commit is the record for the rest.

**Not checked.** A scheduled run on GitHub (it runs only from `main`, so the first is after the merge).

## 2026-11-24 — first pieces of Mark LVII: three small fixes

**Asked for.** "go" (the first piece of Mark LVII's changes, after pull request #33 was merged as `346f7db`), "and also use the 3 github repos for code review and skills".

**Assumptions.** (1) The three repositories are `addyosmani/agent-skills`, `anthropics/skills` and `alibaba/open-code-review`, and the request repeats the owner's choice of 2026-11-22: work as they teach, review with `open-code-review`; nothing is installed inside Ultron. (2) "go" starts the first piece, not all of it: `docs/UPSTREAM_RESEARCH.md` section 10 lists about eight small items and `actions/computer_settings.py` alone is 483 changed lines, so this pull request takes the three that are small, independent, Windows-relevant and reproducible from the code, and the rest follow one piece at a time. (3) The branch was fast-forwarded to `main` first (`main` held the branch's tip plus the merge commit).

**What was done.** Mark LVII's files were read next to Ultron's (`git diff 0101e54 752ff61` in a fresh clone; the library sources of pyautogui 0.9.54, piper-tts 1.8.0 and openwakeword 0.6.0 were downloaded from PyPI and read, not installed). Each of three fixes was written test first, watched red on the old code, then made green, one commit each, with `docs/MAP.md` regenerated from the staged tree in each: `b1c9882` (Windows scroll units), `6309fd1` (the wake word forgets), `0f2c42e` (Piper voices whole or not at all). Then this record.

**Review.** `ocr delegate preview` listed four reviewable files (the tests are excluded by its default path rules) and `ocr delegate rule` printed the rules for Python; the reading was done by hand against those and the five axes of `code-review-and-quality` from `agent-skills`. Found and fixed before anything was pushed: (1) one lock for every Piper voice would hold a second voice up behind a stalled first (a new test, `test_a_voice_stuck_on_a_slow_network_does_not_hold_up_another`, was red on that draft); (2) the scratch folder's name has to be escaped because Piper's own voice-name check lets `/` and `..` through and the folder is deleted afterwards (`test_a_voice_name_cannot_point_the_scratch_folder_outside_the_voices_folder`); (3) `getattr(self, "_wake_detector", None)` in `sleep()` could hide a renamed attribute, and `sleep()` is only reached after `__init__`. A trial run of the whole suite caught a fourth thing: my first test of `sleep()` ran the method with `exec`, which took `TheCeilings`'s `dangerous-call` from 1 to 2; the checks now read the source structurally. One of my tests also let a planted fault through (removing the "no model" guard in `_reset_model`: the error was swallowed and recorded, so nothing failed); it now asserts that nothing is recorded.

**Evidence.** 25 new tests, 19 red on the original code and 6 guards; 34 planted faults, all refused (11 scroll, 12 wake word and sleep, 11 Piper); `ruff --select E4,E7,E9,F` is clean on every changed file apart from one older finding in `providers/tts_piper.py` (`json` imported but unused) that is not mine. Not run here: the hosted Linux and Windows jobs (see the pull request).

After the push, CodeFactor (not a required check) read three lines of `_scroll` as new E221 findings, because they kept the column alignment of the old lines; `6df44bd` uses single spaces there and changes nothing else. reviewdog shows one warning on the added lines: the broad `except Exception` in `WakeWordDetector._reset_model`, kept on purpose (a model that fails to reset must not skip the wake; a test holds it, and the file already has ten like it).

**Found while reading, not changed.** pyautogui's `hscroll` is the vertical scroll on Windows; `WakeWordDetector._drain` records a `queue.Empty` as a failure on every wake; voices truncated by a download that failed before this change are not repaired.

**Not checked.** A real scroll on a real Windows desktop; the real wake-word model (no `openwakeword` here); a real Piper download. None of Mark LVII's code was run.

**Left for the owner.** His OK to merge this pull request once the required checks are green. The `certifi` consent (it unlocks Mark's TLS file and Piper's macOS retry). "go" for the next piece (my guess: the volume and mute fixes in `actions/computer_settings.py`). Dependabot's pull request #34 (24 Python requirement lower bounds in one; opened minutes after #33 merged; not reviewed). The leftover branches of #22 and #33.

## 2026-11-24 — fourth piece of Mark LVII: mute means muted

**Asked for.** "Do the next piece, and I've got a prompt generated below for you too." The next piece is the mute fix that was proposed at the end of the last one. The prompt is a long brief for a different project (see the third assumption).

**Assumptions.** (1) "The next piece" is the mute half of the volume and mute piece, the one proposed with a guess of "yes". (2) As with the last piece, "do" covers pushing and opening a new pull request, because the Windows run only happens on GitHub; nothing merges without the owner's OK. (3) The pasted prompt (slices W0 to W12 of a Linux-laptop project, with `bin/ultronctl`) is not this repository. Its rule six says the right repository contains `bin/ultronctl` and `organs/sandbox/trial.py`. Neither exists here, in any of the 25 public repositories of the account (git trees read through the API, searched for `ultronctl`, `organs/sandbox/trial.py`, `ultron.toml`, `HANDOFF_NOTES.md` and `STATE.md`), or on any branch or archive tag of this repository. The handle in the prompt (`tanushgargjanuarybot`, no hyphen) does not exist on GitHub, and the only public GitHub hit for `ultronctl` is another person's repository. So no audit was written and no `docs/STATE.md` was added: an audit of a different project would be wrong in this repository. The owner was asked where that project lives.

**Found on the way.** The sandbox was reset first: the checkout's HEAD pointed at the old base commit `df115bb` while the files were current (the ten files git called missing were exactly the untracked ones that `main` tracks). `git reset --mixed origin/main` moved the pointer without touching a file, and `git status` was clean afterwards. The scratch tools were rebuilt from CI's package list.

**What was done.** Mark's `actions/computer_settings.py` was read next to ULTRON's (a three-way read; his file has Windows line endings). `tests/test_mute_state.py` was written first and run against the unchanged code (13 of its 18 tests fail); then the change was made. The code: `mute_get`, `mute_set`, `volume_unmute`, `volume_toggle_mute`, three actions that set a state, a reading before the change for undo and for the answer, an answer read back from the mute flag, and the word `unmute` in the list shown to the model.

**Review.** `ocr delegate rule` printed the Python rules and the reading was done by hand against them and the five axes of `code-review-and-quality` from `addyosmani/agent-skills`; `ocr delegate preview` lists nothing until the work is committed. Found before the commit: (1) `pactl` prints yes or no in the user's language (`pa_yes_no_localised`, read in `pactl.c`), so it is asked in plain English; (2) the word `unmute` has to be shown to the model in the same change, or the fix makes "unmute" mute; (3) a toggle from an unknown start must not be called confirmed (Mark's code does); (4) one planted fault got through on the first run (the toggle with no reading at all) and a new test closed it, and two other gaps were closed before that run by thinking it through (the exact sentence for "cannot read it", and commands aimed at the wrong audio device); (5) the planted-fault program passed 29 of 29 while the unmutated code was failing, because Python reused a cached compile of the previous fault (same size, same second). It was repaired, and the previous piece's 34 faults were re-run with the repaired program against the merged code: all caught.

**Evidence.** 18 new tests, 13 fail on the original code and 5 are guards; 29 planted faults, all refused. See `CHANGELOG.md` for the list of what was wrong.

**Found while reading, not changed.** The policy table names (`core/policy.py`): "volume up" should ask for a confirmation click because the table says `volume`, `set_volume` and `brightness` where the actions are `volume_up`, `volume_set`, `brightness_up`. Read in the code and run through `policy.classify`; not seen in the running app. A referee file: not edited. The prompt's project: not found, see above.

**Not checked.** A real Windows audio device, a real PulseAudio or PipeWire server, a real Mac, the confirmation banner in the running app.

**Left for the owner.** His OK to merge this pull request once the required checks are green. Whether the policy names should be made routine (a referee file). Where the W0 to W12 project lives. The `certifi` consent. Dependabot's #34. "go" for the next piece (my guess: `volume_set` switching the sound on, and the volume-key fallback).

## 2026-11-25 — the Linux crash: found, reproduced, fixed

**Asked for.** "Is this done? then what now? Merge this PR, and now make it so that this REPO is considered 100% ready to use." The merge is done: `gh pr merge 36 --merge` gave `9f2e803`, whose tree is identical to the tested tip `002037b`; the fast gate, Linux, Windows and the archive check are all green on it (verify run 45622893802). "100% ready" is not defined anywhere in the repository, so it was split into things that can be measured.

**Assumptions.** (1) "Ready" means: everything that can be run here is green and the green can be trusted; a fresh install is proven; the records are true; and what only the owner's machine and keys can prove is listed by name. It cannot mean "all 9 PARTIAL proof-gate claims are proven": they need his microphone, speaker, camera, browser and keys. (2) The first piece is the one that makes the checks untrustworthy: the Linux crash. (3) As before, "make it ready" covers pushing and opening a pull request; merging waits for his OK.

**Found on the way.** The sandbox was reset again (HEAD at the old base with current files): `git reset --mixed` to the pushed tip, then a fast-forward to `main` after the merge. The scheduled "Upstream watch" has not run: at 13:22 UTC, seven hours after its first tick (2026-11-25 06:17 UTC), GitHub listed 0 scheduled runs of any workflow and 0 runs of that one. GitHub can drop scheduled runs. I then ran the job once by hand (`workflow_dispatch`, run 45629120807): it passed, Mark had not moved (his head `752ff61` is the pin), no issue was opened and none was open to close, so the job works and the skipped tick is GitHub's. The next tick is 2026-12-01 06:17 UTC. The scratch folder was gone again and was rebuilt.

**What was done.** The Linux crash was taken apart. Both crashed first attempts ended with exit code 245 (256 - 11, a segmentation fault); the one other red Linux run in the last 29 was a plain test failure of mine, long fixed. The earlier hosted dump showed a Piper thread at `providers/tts_piper.py` line 170 and the main thread building a widget. This sandbox lacks four system libraries Qt wants (`libGL`, `libEGL`, `libxkbcommon`, `libdbus`), so the Qt sections of the suite could never run here. Four tiny stand-in libraries (every function returns 0) were generated from the symbols Qt asks for, in the scratch folder only; with them Qt starts and 161 more tests run. Then the failure was reproduced: hold the voice-list download at a gate, drop the panel, let the download finish. Original code: 20 runs out of 20 died. Keep the panel alive: 0 of 5. Drop it but give the thread a callback that touches nothing: 0 of 5. With the panel inside a window (the app's shape) and the window destroyed: 5 of 5 died, after `sip.isdeleted` said the panel was gone. That is the mechanism: a thread emitting a signal of a panel that no longer exists. One reading on the way was wrong and was corrected: a "destroyed" handler printed "not destroyed yet", but the handler was itself torn down with the panel, so it proved nothing.

The fix is in `ui.py`: `_LiveRelay` and `_live_relay()`, one object that outlives the panels. `tests/test_providers_panel_threads.py` was written first and run on the unchanged code (the survival test fails with exit code -11; the other two pass), then the change was made.

**Measured for "ready".** All read or run here; nothing was installed on a real Windows machine. (1) The whole `requirements.txt` resolves with no conflict on Python 3.11 (pip's dry run, 99 packages), and in a brand-new environment the project's own `scripts/bootstrap.py` installed all of it in about two minutes. Its start-up check covers three modules (`PyQt6.QtWidgets`, `numpy`, `sounddevice`) and flagged only `sounddevice`, which on Linux needs the PortAudio system library (the Windows wheel carries it). (2) 40 of the 42 requirement lines that apply on Windows have a ready-made wheel for the newest release usable on Python 3.11, 3.12 and 3.13, read from PyPI; `pyautogui` and `pygetwindow` are source-only there (pure Python, so pip builds them on the user's machine with no compiler). (3) CI installs a short list written into `verify.yml` and never reads `requirements.txt`, so no CI run has installed the real file on Windows. That is the gap the next piece is meant to close. (4) Dependabot's #34, read: on Python 3.11 its `requirements.txt` cannot be installed (`numpy>=2.5.5`, checked with pip's resolver); it moves the PyQt6 ceiling that `requirements.txt` keeps below Qt 6.12 on purpose; and it jumps whole majors (`google-genai` 2 to 3, `opencv-python` 4 to 5, `cryptography` 49 to 50, `pillow` 12 to 13). Its checks were green only because CI never installs those lines. Closed without merging, with the evidence in a comment. (5) Issues #9, #10 and #11 were already done on `main` and still open; each is now closed with the test or proof-gate claim that meets its acceptance list (`policy_grants` and `mcp` are PROVEN, and the restart-at-step-three test is in `tests/test_autonomy_upgrades.py`). #2 to #7 stay open: #3, #4 and #5 are real unfinished features (their own last comments say so), #6 is the owner's Windows run of the proof gate, #2 and #7 are handoff conventions. (6) The Windows proof gate, as last read (CI on `5a18a2b`, 2026-11-24, not re-read for `9f2e803`): 28 PROVEN, 9 PARTIAL, 0 failed; the 9 need the owner's microphone, speaker, camera, browser and keys.

**Review.** `ocr delegate preview` listed `ui.py` as the one reviewable file (+35/-6) and `ocr delegate rule` printed the Python rule groups. It calls no model, so the reading was done by hand against those rules and the five axes of `code-review-and-quality` from `addyosmani/agent-skills`. It is the smallest change that removes the cause (one new class and its getter, three changed lines, one removed signal), with no new dependency and the slot name kept. One behaviour difference: every panel that exists now hears every voice-list arrival, where each used to hear only its own. A hidden panel ignores it (`_on_live_ready` does nothing while the panel is hidden), and closing the panel only hides it. A per-panel guard (`sip.isdeleted` before emitting) was rejected: it checks and then acts, and the panel can go in between. Ruff on the changed files (the project's own configuration): `ui.py` 175 findings on `main` and 174 now, the new test file 0.

**Evidence.** The 3 new tests: red on the old code, green on the new, 20 more runs clean. Four planted mistakes, all caught. The earlier reproductions on the fixed code: 20 of 20 clean in each of the three shapes. Whole suite in a scratch copy: 2,939 tests (2,936 plus the 3). In a real git clone of `main` with the stand-ins, before the change: 2,936 tests, OK, 39 skipped.

**A correction to every earlier report.** The "3 failures that only happen here" were this sandbox's: one error from the missing graphics libraries and two failures from copies that had no `.git` folder. They are not in the repository.

**Not checked.** That the hosted crash is this one (it matches; the next Linux runs are the test). This scenario on Windows. Closing the program mid-download on a real machine.

**Found while reading, not changed.** `providers/_tests.py` says it needs no network and its panel section starts the Piper download. `_models_ready` has the same hand-a-signal-to-a-thread shape in `ProvidersOverlay._fetch_models`; not seen to crash. Closing the engine panel only hides it (`close.clicked.connect(self.hide)`) and `_open_providers` builds a new panel on every opening, so hidden panels pile up for as long as the window lives.

**Left for the owner.** His OK to merge this pull request once the required checks are green. What "ready" should mean beyond the list in the reply. Dependabot proposing the same update again, the old #21, "Delete branch" on the merged branches, the `certifi` consent, the policy names in `core/policy.py`, and a run of `python scripts/proof_gate.py --live` on his own Windows machine, which is the only thing that can close the 9 PARTIAL claims.

## 2026-11-25 (afternoon) — a fresh install is checked, and Dependabot keeps to the pins

**Asked for.** "Please merge the pull request." That is #37, and my last message had said that "merge" would also start the next piece. #37 was merged with `gh pr merge 37 --merge` as `2f16a98` (parents `9f2e803` and the tested tip `448ae5f`, tree identical); the fast gate and Linux were green on it.

**Assumptions.** (1) "Merge" covers the merge and the piece I named in the same message: a Windows install check and Dependabot keeping to the pins. (2) The install check must not be a required check, so a slow install can never block an unrelated merge. (3) Dependabot's strategy is the owner's in the end (`DECISIONS.md` row 136): the change is in this pull request and does nothing until he merges it.

**Found on the way.** The sandbox was reset again (HEAD at the base with current files, scratch folder gone): `git reset --mixed` to the pushed tip, the checks re-read on the right commit (the first listing had been for the old base), then the merge, then a fast-forward to `main`. `scripts/bootstrap.py`'s `main` ignores the list of packages that `install_requirements` could not install (by design) and exits 0 unless a critical import fails, so on its own it cannot say that a line of `requirements.txt` did not install; that is why a second, strict step exists. In a brand-new environment the launcher installed the whole file in about two minutes on Linux and exited 1 only because `sounddevice` needs the PortAudio system library there (a real exit code this time: earlier a `$?` inside double quotes had printed 0). The suite in that environment: 2,939 tests OK with 21 skips, against 39 in CI's short list, so the 29 dashboard tests that need `fastapi` ran and passed. `pip check` there: "No broken requirements found".

**What was done.** `tests/test_check_install.py` first (13 tests, red until `scripts/check_install.py` existed), then the script. The workflow and Dependabot tests first (29 red), then `.github/workflows/install-check.yml` and the `.github/dependabot.yml` change. The documentation of `versioning-strategy` and `ignore` was read before choosing: both are supported for pip, `widen` only raises a maximum, and `increase`, the default for an app, raises every minimum, which is what #34 shows. I chose `widen` over `increase-if-necessary` because the documentation is not consistent about what the latter does outside the range (its table says it widens, its example shows it increasing). That choice was wrong, and GitHub caught it (next paragraph).

**A mistake, caught by GitHub before the merge.** The first push had `versioning-strategy: widen`. GitHub's own check of `dependabot.yml` (a check run named after the file, from the Dependabot app) failed on the pull request: `The property '#/updates/1/versioning-strategy' value "widen" did not match one of the following values: lockfile-only, auto, increase, increase-if-necessary`. I had read that the option is supported for pip and assumed that covered every value in the table; it does not. The test I wrote asserted `widen`, so it passed: it encoded my belief, not the fact. Corrected to `increase-if-necessary` in a new commit (the pushed history is kept), and the test now also holds the value to the list GitHub printed. Had it been merged, Dependabot would have refused the whole file, silently, and nothing would have been updated: the very thing row 136 warns about.

**A GitHub fault, and what got round it.** The push of the correction failed once with `Internal Server Error`. The retry landed (the branch moved), but for thirteen minutes GitHub did not update the pull request's head (`refs/pull/38/head` stayed on the old commit) and started no workflow for the next two pushes, push-triggered ones included, while a manual dispatch started within seconds. `gh pr close` got a 502. Closing and reopening the pull request through the REST API (`PATCH /pulls/38`, state `closed`, then `open`) made GitHub pick the new head up and start the checks. The fast gate skips its pull-request copy by design (the push copy covers it) and that head had no push copy, so it was started by hand with `workflow_dispatch` on the branch. Worth knowing for next time: a pull request that shows an old head after a push has not failed any check; the event was lost.

**Review.** `ocr delegate preview` listed three reviewable files (the workflow, `dependabot.yml` and `scripts/check_install.py`; tests are excluded) and `ocr delegate rule` printed the workflow and Python rules. It calls no model, so the reading was by hand, with the five axes of `code-review-and-quality`. Found and fixed before the push: `main(argv)` never read `argv` (parameter removed, the tests follow). The rule on uncached dependencies is answered with a comment in the workflow, because a cache would hide what a fresh machine downloads today. Workflow rules checked: `pull_request` only (never `pull_request_target`), `permissions: contents: read`, every action pinned to a commit with its release, no event data in any `run:` block, timeouts, concurrency, `fail-fast: false`.

**Evidence.** 28 planted mistakes in the workflow, the Dependabot file, the Qt ceiling and the script, among them the real one (`widen`): all caught. The script on a real fresh environment: exit 0; with one package removed: exit 1 naming it; on Dependabot's rejected #34 file with Python 3.11: pip's "No matching distribution found for numpy<3,>=2.5.5", exit 1. Whole chain on the finished tree: 2,967 tests OK, the provider self-test 108 passed, the fast gate 6 of 6.

**First run on GitHub** (run 45648162971): Windows with Python 3.11, 3.12 and 3.13 and the Linux suite all passed. I read the Python 3.13 log: the launcher installed the whole file in 81 seconds (numpy 2.5.5, PyQt6 6.11.0, opencv-python 4.14.0.94, fastapi 0.165.0, pywin32 312; `pyautogui`, `pygetwindow` and their helpers built from source with no compiler), "Startup check: 3 required modules import cleanly", then "Every line of requirements.txt that applies here is installed. No broken requirements found." The Linux job installed everything in 31 seconds and ran the whole suite in 95. The Python 3.11 and 3.12 logs were not read, only their results.

**Not checked.** The monthly schedule and the manual trigger (the pull-request trigger has run). That the window opens and the voice works on that machine: the check installs and imports three modules, it does not start the app. What Dependabot proposes under `increase-if-necessary`. Python 3.12 and 3.13 on a real Windows machine.

**Left for the owner.** His OK to merge this pull request once its checks are read. Whether `increase-if-necessary` and the PyQt6 rule are the Dependabot policy he wants (`DECISIONS.md` row 136). The rest of the last entry: a run of the proof gate on his own Windows machine, #21, deleting the merged branches and the setting that does it by itself, the `certifi` consent, the policy names.

## 2026-11-25 (evening) — Dependabot's Qt rule did nothing, and the test that holds the ceiling caught it

**Asked for.** "Merge" (#38), together with a question about reading a YouTube channel, which is answered in the reply and changed nothing here. #38 was merged with `gh pr merge 38 --merge` as `8d92278` (parents `2f16a98` and the tested tip `6543606`; tree identical; 7 commits, 12 files). Every check on `main` passed: `verify` 45657403509 (Linux and Windows), the fast gate 45657403504, and the install check 45657403619, which ran because the merge touched a requirements or launcher path.

**Found.** Dependabot read the new file and, three minutes after the merge (16:48 UTC), opened #39, "bump the python-all group with 6 updates". It raises the PyQt6 ceiling in `requirements.txt` from `<6.12` to `<6.13`, although #38 had told it to ignore PyQt6 minor and major releases. It also raises the ceilings of google-genai (`<4`), Pillow (`<14`), OpenCV (`<6`) and cryptography (`<51`) and moves the ruff pin to 0.17.6. Raising a ceiling that the newest release is outside of is what `increase-if-necessary` does, and it is "the one case that needs a person to decide"; the Qt line is the one that must not go through.

**What the checks said.** #39 is red, on one test. I read the three failed jobs: the Linux job with every package, Linux `verify` and Windows `verify` each ran 2,967 tests, and the only failure in each is `test_the_qt_ceiling_stays_below_the_release_that_crashes_and_dependabot_is_told` ("the PyQt6 ceiling moved"). The three Windows installs passed. So the test written to hold the ceiling held it, and the new install check ran on a Dependabot proposal as intended. None of the other 2,966 tests failed with all five newer libraries installed (Linux, every package), which says nothing about the live Gemini call, the camera or the screen on his machine.

**A mistake of mine, the second of its kind.** The rule that was meant to stop the proposal had no effect, and its test could not tell: it asserted that the words `version-update:semver-minor` and `-major` were in the file. As with `widen` in #38, a test that repeats its author's belief is not evidence. Why Dependabot ignored the rule is not known: its own job log could not be read (the log server answered HTTP 500 twice). Every requirement in the file is a range and the rule rested on update types; I did not put a guess about the mechanism in the records as a fact.

**Assumptions.** (1) A defect in what was just merged is a fix, so it was made without asking (standing instruction), but it is not merged: that waits for the owner. (2) The first fix was a bare `dependency-name` (GitHub's documentation: "ignore all updates"). Before the pull request was opened a search of the documentation showed that such a rule also silences security updates for the package, and that a rule on `versions` reaches them only for the versions it names, so the rule names `>=6.12`, the ceiling. A Qt security release that needs 6.12 or later gets no pull request and has to be noticed by hand. Moving the ceiling stays a by-hand act after a re-test, as `requirements.txt` already says, and the number is lifted with it: a test holds the two together. (3) The other four ceiling raises are not touched: whether to accept them is the owner's decision (DECISIONS row 136), and #39 is left open, with a comment, so the evidence stays visible.

**Change.** `.github/dependabot.yml` (the PyQt6 rule), `tests/test_dependency_policy.py` (the Qt test now fails on a rule that rests on update types: its old last assertion is **replaced**, and said so here; the same test requires the versions rule to carry the ceiling's number; a new test refuses an update-types rule for any requirement that is not an exact pin; a small reader of the `ignore:` list fails closed), `DECISIONS.md` row 136, the handoff, `CHANGELOG.md`, `log.txt`, this file.

**Evidence.** The two tests are red on the old file and green on the new. Eleven planted cases behave as required: nine mistakes caught (the old form, the rule removed, the wrong Qt, the reason deleted, the ceiling raised, the ignored versions out of step with the ceiling, a bare rule, update types for another range such as google-genai, a list the checker cannot read) and two valid variants green (a space in `>= 6.12`; update types for `ruff`, an exact pin).

**Not checked.** That Dependabot now leaves Qt out: it reads the file only when it reaches `main`, so it can be seen only after the merge, in its next run or in the update of #39.

**Left for the owner.** His OK to merge this pull request; and, after it, what to do with #39 and the other four ceiling raises.

## 2026-11-25 (night) — advice from other developers, a glossary, and how we ask the owner

**Asked for.** "Use Matt's repo skills and he is very experienced developer, and try to research more people who have good advice lying in their github repos. BTW are you even working because you keep giving merges." The reply to it asked for no merge. #40 stays open and not merged.

**What I read.** Matt Pocock's `mattpocock/skills` and nine more repositories. The list, with commits, licences and what was read, is `docs/UPSTREAM_RESEARCH.md`, section 11. No installer, plugin command or script from any of them was run, and no file was copied. Two have no licence file and one is share-alike, so those were read for ideas only.

**What I found.** The advice converges on nine points (section 11.2). Most of it the owner had already written in `WORKING-PHILOSOPHY.md` and `docs/MAINTAINERS.md`. Two lines there bear on his complaint: "Fast. Do the work, then explain it", and, among the things he never wants, "ask me about trivial actions". My working notes did not carry them.

**What changed.** `GLOSSARY.md` and `tests/test_glossary.py` (new); five habits, the tautological-test rule and a retro step in `WORKING-PHILOSOPHY.md`; pointers in `AGENTS.md`, `docs/INDEX.md` and `tests/test_doc_references.py`; section 11 of `docs/UPSTREAM_RESEARCH.md`; one row in `DECISIONS.md` (the owner's file). No change to the app.

**Retro** (step 9 of `WORKING-PHILOSOPHY.md`, section 3).
- *Many messages ended with a request to merge.* Cause: my working notes did not carry the owner's line about trivial actions, and I did not re-read `WORKING-PHILOSOPHY.md`, which `AGENTS.md` says to read first. Kind of fix: a rule at the point of use (section 2 now names this incident) and one question to the owner about a standing permission. No program can tell a trivial question from a consequential one, so this is not a check.
- *Two tests held a belief and not a fact* (`widen`, then the Qt rule). Kind of fix: a rule (section 3, step 4). A program cannot tell a belief from a fact; the independent source is the other system's own answer.
- *Three records that copy facts held elsewhere drifted* (a commit count, a "two days", an undated count). Kind of fix: a pointer. The handoff should point to the records and not copy them (item 13 of section 11.3, deferred).

**Assumptions.** (1) "Use Matt's repo skills" means: apply what fits, in our words, and say what does not. It does not mean install them. (2) The work went onto the branch that carries #40, because only one pull request can be open from it. That pull request now holds two unrelated pieces, each in its own commits. (3) A glossary comes first, because he asked for plain words three times.

**Evidence.** The 11 glossary tests were red before the file existed. 17 planted cases behave as required: 15 caught (four of them where the program's words change and the glossary does not) and 2 valid edits green.

**Not checked.** Whether the new habits improve the work. The one-round question format has been used on the owner once, in the reply to this request.

**Left for the owner.** One question: may small green changes (documents, tests, checks) be merged without asking him? My guess is yes. I would still ask before anything that changes how Ultron behaves.

## 2026-11-25 (late night) — the Linux crash came back; the first fix was not enough

**Found.** The Linux check of this pull request failed on `855f6c6` (run 45679604007, 18:54 UTC). I read the log before any re-run. The 2,979 unit tests passed. Then the provider self-test died with `Fatal Python error: Segmentation fault`: the main thread was building a widget in the confirmation-banner test, and a worker thread was at `providers/tts_piper.py` line 170, the call that reports a finished read. Windows passed on the same commit.

**How it was found** (Matt Pocock's `diagnosing-bugs`: first a loop that can go red on this very bug). I ran the real self-test functions in a scratch copy with a random delay on the voice-list read. 2 of 20 runs, then 9 of 60, crashed. Bisecting the real sequence: the panel test alone 1 of 60, the banner test alone 0 of 60, the panel then the banner 9 of 60. A control, with the worker calling a plain no-op, gave 0 of 80: the crash needs the Qt call. Four invented shapes did NOT reproduce it (a storm of emits from long-lived threads, from fresh threads, and with the real banner work): every one kept the application alive. The cause showed in a traceback from a second pass of the sequence: "wrapped C/C++ object of type _LiveRelay has been deleted". A direct test then: keep the application alive and the relay survives; let the test drop it and the relay is deleted. A deterministic replay (the application destroyed, a late read reports in) crashed 20 of 20.

**Why #37 missed it.** It put the relay in a module variable and wrote "not deleted while the program runs". The relay is a Qt object, and Qt objects go when the application goes. The self-test holds its application in a local variable, so the application, and the relay with it, are destroyed when the test returns. #37's tests destroyed the panel and the window and kept the application. Closing the program does the same as the self-test.

**What changed.** `ui.py`: no worker thread touches Qt. A finished read calls `_LiveMailbox.announce()`, which adds one to a plain counter; each panel looks at the counter on a timer of its own, and the timer is destroyed with the panel. `tests/test_providers_panel_threads.py`: the first scenario waits for the timer (the same checks); 4 new tests replay the crash. `AGENTS.md` (threading) and `WORKING-PHILOSOPHY.md` (section 6, step 4) carry the lesson.

**Retro** (step 9 of `WORKING-PHILOSOPHY.md`, section 3).
- *The first fix was not enough.* Cause: #37 asserted a lifetime that no test tried to break, and I wrote "fixed" on the strength of six green runs that I had myself called weak. Kind of fix: a test (done: the application is destroyed too) and a rule (section 6, step 4: try the larger lifetime). The rule is not a check, because no program knows which object is the outermost.
- *Four reproductions did not crash.* Each shared one unexamined assumption, that the application stays alive. Bisecting the real sequence and a no-op control found the missing ingredient faster than more invented shapes. Kind of fix: none; it is recorded here.
- *A thread called Qt.* Kind of fix: a rule in `AGENTS.md` (threading), with this incident.

**Assumptions.** (1) The fix goes into the same pull request (#40): only one can be open from this branch, and the crash blocks its required check. (2) Looking every 250 ms is acceptable for a settings panel, and the change cannot be seen by the owner. (3) `ProvidersOverlay._fetch_models` is not changed here: it has the same shape (a signal of the panel handed to a thread) and has not been seen to crash.

**Evidence.** The 4 new tests are red on the old code and green on the new. The real sequence: 100 runs, no crash (old: 5 to 15 in 100). The late report: 20 of 20 survive, nothing raised (old: 20 of 20 crashed). 5 planted regressions caught, 2 valid changes green.

**Not checked.** That the Linux check no longer crashes: only many GitHub runs can show it. A real Windows machine closing the program mid-download.

## 2026-11-26 — a coding-agent playbook, rewritten and held to its own rules

**Asked for.** "Improve this Playbook." The owner pasted a "Vibe Coding Agent Master Playbook". No question was left open: nothing here needs his approval, and the answer carries no request to merge.

**What I read first.** The primary sources the playbook leans on, through the GitHub API, and a web search for which tool reads which file. New this time: `anthropics/skills` (the skill-creator guide), `coleam00/context-engineering-intro` (the PRP template), `agentsmd/agents.md`, and more of `obra/superpowers` (the claim, requires, not-sufficient table; the rationalization tables; "Size the Work"; the contributor guide for agents). Commits, licences and what was read are in `docs/UPSTREAM_RESEARCH.md`, 11.1 and 11.6.

**What I found in v1.** It broke its own rules, in ways a program can find (the list is Appendix C of the playbook): two file-length limits, a "3-strike" rule that rolled back after two, `git checkout -- .` after "never run destructive git commands", placeholders after a ban on them, LaTeX, a nested code fence. Some advice was risky (`-y` and `-f` always; kill a silent process after 30 seconds). A statistic and several credits could not be checked, and I removed them rather than repeat them. It had gaps: outside text as instructions, who may approve what, tests that restate the code, and a skill format that would not load as a skill.

**What changed.** `docs/reference/CODING_AGENT_PLAYBOOK.md` and `tests/test_agent_playbook.py` (new); one row in `docs/INDEX.md`; three sources and 11.6 in `docs/UPSTREAM_RESEARCH.md`; one sentence in `WORKING-PHILOSOPHY.md`, section 3, step 4 (the owner's file). It is a proposal. It does not change `AGENTS.md`.

**Retro** (step 9 of `WORKING-PHILOSOPHY.md`, section 3).
- *My new test skipped most of the file it was written to check.* Cause: I split the file into sections at every line that starts with `## `, and Template E, inside a code fence, has such lines. The split swallowed the template's closing fence, so everything after it counted as "inside a fence" and sections 6 to 8 were never scanned. It passed on the real file. Only the planted-mistake run showed it: a destructive command and a placeholder, planted in sections 6 and 7, were not caught. Kind of fix: the test (headings inside a fence are ignored) and a rule (a new check is not trusted until it has failed, step 4).
- *Two of my first checks were too literal* (the words "use when" in every description, and a pattern that read "20,000 characters" as "000"). Both failed on the real file and were fixed there. Kind of fix: the test.
- *Two claims in the playbook's own introduction were wrong*: "about thirty lines" for a core of 17 lines and 13 rules, and "every number" for a table that holds only the limits. A careful read found them, not a test. Kind of fix: a test for the one that can drift (the count of rules), and a wording fix for the other.
- *The playbook gave numbers to quote that were not its own* (other tools' size limits). The test flagged them. They moved to the sources appendix, where they are marked as reported.

**Assumptions.** (1) "Improve" means: find what is wrong, verify what can be verified, remove what cannot, and keep what was good (the loop, red then green, surgical edits, the templates, the pre-flight list). (2) The result goes in the repository as a reference document, because that is where this session's files persist, and it says at the top that it is not a rule file of this repository. (3) No part of it goes into `AGENTS.md` unasked: those are binding rules.

**Evidence.** The 22 tests written first were red, and one more was written red first for a stale claim. Then 24 tests, green. 22 planted cases behave as required: 19 flaws caught (six of them v1's own) and 3 valid edits green.

**Not checked.** That agents follow it better. The blog reports on which tool reads which file. The core block in a real tool. OCR was not run: no code file changed.

## 2026-11-26 (later) — pull requests are merged without asking, and each can be reversed

**Asked for.** "Always merge PR's. But they should be flexible to reverse." It answers the question I put to him at the end of 2026-11-25: may small green changes be merged without asking.

**What I did.** I checked #40 (head `48fb283`, every required check green, nothing new said on it) and rehearsed its reversal in a scratch clone, then merged it with `gh pr merge 40 --merge` (`dc1f66e`, parents `8d92278` and `48fb283`, tree identical to the head's). The rehearsal: reverting the whole pull request is one command and gives back the earlier tree exactly; one piece alone is clean for the playbook, and conflicts in the shared notes for the others (the crash fix's code commit conflicts only in the generated map). Then I watched Dependabot: it closed #39 ten seconds after the merge and opened #41 with five updates and no PyQt6, so the `versions` rule works.

**Retro** (step 9 of `WORKING-PHILOSOPHY.md`, section 3).
- *Stacking four pieces on one pull request made undoing one of them costly.* Cause: only one pull request can be open from this branch, and while merges waited for his OK I stacked pieces on it. Kind of fix: a rule now that merges need no asking (one piece per pull request, in `DECISIONS.md`) and the procedure in `docs/AGENT_MAINTENANCE.md`, section 9. The conflicts were in notes that copy facts held elsewhere (the handoff header above all): item 13 of `docs/UPSTREAM_RESEARCH.md`, 11.3, stays deferred and is now the next thing that would make reversal easier.
- *The question I asked was narrower than the answer.* I asked about documents, tests and checks. He said "Always". I recorded his words and did not narrow them, and I kept the limits that follow from what the permission is for (the merge of the agent's own pull requests; not another party's; not his "go" for porting from Mark).

**Assumptions.** (1) "Always merge PR's" covers the pull requests I make. It does not cover Dependabot's #41 (it raises the Gemini library to a new major version, and the tests cannot show the live call) or the old #21: those still need his word. (2) "Flexible to reverse" means: a merge commit, one piece per pull request, the rollback path named in the pull request and repeated in the merge commit, new behavior switchable off, and the permission itself can be withdrawn. (3) His "go" before anything is ported from Mark is a different decision and stays.

**Evidence.** The rehearsal (scratch clone, the commands in `docs/AGENT_MAINTENANCE.md`); the merge checks (merged, parents, tree); the checks on `main`; Dependabot's behavior after the merge, read from GitHub.

**Not checked.** A real reversal on the real repository. That the Linux crash is gone: four Linux jobs on four heads passed since the fix, and the one on the merge, which at the earlier rate is weak evidence.

## 2026-11-26 (later still) — the text client names its Gemini API version

**Asked for.** Nothing new. I merged #42 (the permission) under the permission it records, then read Dependabot's #41 before answering the one question that is still the owner's: take it or not.

**What I did.** I read Google's notes for `google-genai` 3.0.0 against the code. The default API version moved from `v1beta` to `v1`, and the `-latest` model names, some `-preview` models and the Live API exist only on `v1beta`. The Live session (`main.py`) and the one-shot Live turn (`core/gemini.py`) name `v1beta` (or `v1alpha`) themselves. `core.gemini.client()`, the REST client, did not. I measured the real function in three scratch virtual environments: 2.8.0 (the lowest the requirements allow) and 2.34.0 give `v1beta`, 3.6.1 gives `v1`. I wrote two checks first and watched them fail on the old code (the one place that was missing was named by the scan: `core/gemini.py:421`), made the one-constant fix, and planted 15 mistakes.

**Retro** (step 9 of `WORKING-PHILOSOPHY.md`, section 3).
- *A ceiling with no reason next to it, and a reason I had only believed.* In #42 I gave the reason for holding `<3` as "the tests cannot show the live Gemini call". It was true and it told nobody anything. Cause: the pin was set in #38 as a ceiling, and no reason was written beside it (DECISIONS row 136 says a pin has a reason). Kind of fix: the check now carries the reason in executable form, and the constant's comment says it in words. The habit: before answering "take it or not" for a Dependabot pull request, read the vendor's list of breaking changes against our code, and measure the one line that matters.
- *The one line I did not measure would have been a guess.* Google's note says the default moved. Whether our call was affected needed the real function run against both versions. It took two minutes, offline.

**Assumptions.** (1) Passing `v1beta` explicitly changes nothing for the library installed today, because it already picks `v1beta` (measured on 2.34.0). (2) `HttpOptions` accepts `api_version` in every release the requirements allow (`>=2.8.0,<3`): measured at both ends (2.8.0 and 2.34.0) and on 3.6.1, not on the releases between. (3) This does not make #41 safe. It removes one known reason against it. The decision stays the owner's.

**Evidence.** The measurement on three library versions; the checks red on the old code and green on the new; 62 Gemini tests; 15 planted mistakes (11 caught, 4 valid edits green).

**Not checked.** That Google's live service answers on `v1beta` today, which needs his key. The other 3.x changes: the default HTTP client is now `httpx2` and `httpx` is no longer installed with the library; Ultron's requirements still ask for `httpx`.
