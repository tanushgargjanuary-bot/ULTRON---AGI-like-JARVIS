# Skills: what Ultron should be able to do, and how it should know that it can

Written 2026-11-06 for build 1.2.14. It answers one question — which skills belong
in Ultron — with a special section on the two the owner named: **meta-learning**
and **meta-cognition**.

## What a skill is here

A skill in this project is one of two things, and the difference is deliberate:

- a **deterministic recipe**: a named list of tool calls with fixed arguments.
  It is not generated code, it is not a prompt, and it cannot do anything a tool
  cannot already do. `plugins/custom_jarvis.py` exposes them as `list_skills`,
  `run_skill` and `preview_skill`.
- a **written skill**: a Markdown document at `skills/<name>/SKILL.md` that says
  when a procedure applies and how to do it well. It grants nothing. It is read
  on demand by `core/skill_docs.py` through the `skill_guide` tool.

A recipe without a document is a plan with no judgement. A document without a
recipe is advice with no hands. Both live here, and neither can widen a
permission.

Three rules follow, and they are why skills are safe to add quickly:

1. A skill inherits the tool's risk. If the tool needs approval, the skill needs
   approval, once per call.
2. A skill that reads is free of prompts. This is why most of them read.
3. A skill is testable without a model: the plan is data, so a test can assert
   its steps and its tools.

## The two families the owner asked for

### Meta-cognition — knowing what it knows

The failure this fixes is not ignorance. It is **confidence without evidence**: an
assistant that says "done" with the same tone whether it checked or guessed.

The rule taken here: meta-cognition must be **arithmetic on a record**, never a
mood in a prompt. There is no "be humble" instruction. There is a ledger.

`custom_jarvis/metacog.py` records each claim with the confidence it was stated
at, and later records what happened. From those pairs:

| Question | Answer | Why not the obvious version |
| --- | --- | --- |
| How often am I right? | accuracy over resolved claims | a raw ratio over 3 claims is noise |
| How sure am I *really*? | **Wilson lower bound** | 3-for-3 is "at least 44%", not "100%" |
| Am I overconfident? | Brier score plus per-bucket calibration | the bucket says "you said 90%, you were 60%" |
| Should I answer or check? | a verdict from the bound | a number is actionable; a feeling is not |

The single most important line in the module is that a perfect record of three is
**not** reported as reliable. That is the difference between a metric and flattery.

### Meta-learning — changing behaviour after a mistake

The failure this fixes is **repeating a mistake with full confidence**, because
nothing recorded why the last attempt failed.

`metacog.py` has two stores for it:

- **Lessons**: trigger, mistake, rule. A lesson without a rule is refused, because
  "the tests failed" teaches nothing. `recall_lessons(task)` ranks rules against a
  new task by token overlap, and counts use, so the rules that keep applying rise.
- **Strategies**: for each task type, which approach was tried and whether it
  worked. `choose_strategy` picks by the same lower bound, and **prefers an untried
  strategy once** before trusting the rest — the exploration that stops a lucky
  first guess becoming policy.

## What ships in this build

**Eleven new tools** (in the `custom_jarvis` registry the model already calls):

| Tool | Reads/writes | What it is for |
| --- | --- | --- |
| `record_prediction` | writes | a claim, with the confidence it was stated at |
| `resolve_prediction` | writes | correct / partly / wrong — the only way a record becomes evidence |
| `open_predictions` | reads | what it still owes an answer to |
| `calibration_report` | reads | accuracy, lower bound, Brier, overconfident buckets |
| `self_review` | reads | calibration + applicable lessons + the buckets to watch |
| `record_lesson` | writes | one mistake, one rule |
| `recall_lessons` | reads | rules ranked against a task about to start |
| `record_attempt` | writes | which strategy worked, per task type |
| `choose_strategy` | reads | the best record, with an untried option first |
| `search_text` | reads | literal or regex search over the workspace, `file:line` |
| `measure_code` | reads | files, lines, languages, biggest files |

Both workspace readers are in the confinement table and the read-only set, so they
cannot leave the selected folder and never prompt.

**Thirteen new skills** (24 → 37):

| Skill | Family | Steps |
| --- | --- | --- |
| `meta_preflight` | meta-cognition | `self_review`, `calibration_report`, `recall_lessons` |
| `meta_confidence` | meta-cognition | `calibration_report`, `open_predictions` |
| `meta_debrief` | meta-cognition | unresolved claims, calibration, review |
| `meta_lessons_digest` | meta-learning | lessons for the three commonest task families |
| `meta_strategy_brief` | meta-learning | `choose_strategy` for triage and review |
| `code_size` | inspection | `measure_code` |
| `biggest_files` | inspection | structure plus the heaviest files |
| `todo_scan` | inspection | `TODO` and `FIXME`, by file and line |
| `secret_scan` | security | assignment-shaped secrets, by file and line |
| `test_gap_scan` | inspection | test files against total files |
| `debug_context` | inspection | structure, diff, lessons (needs `.git`) |
| `release_checklist` | inspection | status, log, size, dependency list (needs `.git`) |
| `docs_freshness` | inspection | documents, their size, unanswered markers |

## The next tier, and why each is worth it

Ordered by value per hour of work. None is built yet; none is promised.

1. **`post_mortem`** — draft a lesson automatically when a plan fails. The planner
   already sees the failing step; today that knowledge dies with the turn. This is
   the single highest-value meta-learning addition, and it needs one hook.
2. **Windowed calibration** — "has my accuracy fallen in the last 30 days?" The
   ledger keeps timestamps; the report needs a window argument. Cheap, and it is
   how a drift becomes visible before it becomes a habit.
3. **Coverage map** — which domains have no record at all. "I have never been
   checked on Windows automation" is useful, and it is one query.
4. **`estimate_then_check`** — record an estimate (lines changed, minutes, number
   of files) as a prediction, compare later. Same ledger, different claim type.
   This is what turns "it will take a minute" into a calibrated sentence.
5. **`ambiguity_check`** — before acting, list the readings of a request and ask if
   more than one is plausible. Needs a planner hook and a rule for when to ask;
   the risk of over-asking is real, which is why it comes after the ledger.
6. **`contrastive_review`** — two candidate answers, one recorded choice, later one
   resolved outcome. This is how a preference becomes evidence.
7. **Strategy transfer** — the same task type across projects. The store is keyed
   by task type already; it needs a rule for when two projects are similar enough.
8. **`quiz_me`** — Ultron quizzes the owner on a topic he is learning, and records
   *his* answers. Meta-learning for the human, which is arguably the point of a
   personal assistant.

## Domain skills worth adding after that

These are ordinary skills, chosen because each replaces a guess with a measurement:

- **`review_diff`** — `git_inspect` diff, then the largest changed files, then the
  test files that cover them.
- **`dependency_audit`** — requirement and lock files, then a version-conflict scan.
- **`test_triage`** — the failing test file, its source, and the last diff.
- **`config_audit`** — `inspect_json` across configuration files, flagging keys that
  look like credentials (`secret_scan` already covers the hard part).
- **`git_hygiene`** — large files, committed secrets, a stale `.gitignore`.
- **`handoff_pack`** — the existing `handoff` skill plus `measure_code`, so the next
  session knows the size of what it inherits.
- **`release_notes`** — the commits since the last tag, grouped, with the files each
  touched. Read-only, and it removes a recurring chore.

## What must never become a skill

- **Anything that generates and runs code.** A skill is a recipe; the moment it
  generates Python it is no longer auditable, and the whole design is that it is.
- **Anything that changes its own permissions or the risk tables.** That is the
  owner's decision, twice confirmed.
- **Anything that records memory about the owner without approval.** The metacog
  ledger records the *assistant's* accuracy, which is not personal data; the
  distinction matters and it is why the ledger is a separate file.
- **A skill whose only step is one tool call.** Call the tool. A one-step skill is
  a synonym, and synonyms are how a tool list becomes unreadable.

## How to add one

Twelve lines in `custom_jarvis/skills.py`:

```python
Skill(
    "identity",                      # unique, lowercase, verb-shaped
    "Title in eight words or fewer",
    "One sentence: what it is for and why it exists.",
    (
        call("tool_name", arg="value"),
        call("other_tool", path="@workspace"),      # @workspace and @target only
    ),
),
```

Then three things, or it does not count:

1. **A test** in `tests/test_metacog_service.py` (or a sibling) that the skill is
   listed, applicable in a plain folder, and that its steps complete.
2. **The risk check**: if any step writes, say in the purpose that approval will be
   asked for.
3. **The honesty check**: if a step needs `.git`, Windows, or a package, declare it
   (`required_markers`, `platform_required`) so `list_skills` reports it as not
   applicable instead of failing at step two of five.

## The written layer (2026-11-14)

Before this date `skills/<name>/SKILL.md` was decoration: ten files in the tree
and no reader. `core/skill_docs.py` now loads them, and `skill_guide` lists and
reads them during a session. The rules that keep that safe:

| Rule | Why |
|---|---|
| Only `skills/<simple-name>/SKILL.md`, no `..`, no drive letter | A name is not a path |
| Reads stop at 12,000 characters, files at 64 KB | A skill is context, and context is the budget |
| A document is text, never code | Nothing here imports or executes it |
| A broken document is skipped, not raised | A bad file must not take the session down |

### Installed documents

| Document | Applies to |
|---|---|
| `computer-use` | Tree before pixels, act once, verify every time, stop on private screens |
| `background-awareness` | Know what is open without being told, and never touch it |
| `dev-methodology` | Plan, test, build small, review, report |
| `coding-guardrails` | No wrong assumptions, no overcomplication, no unrequested edits |
| `security-review` | Secrets, boundary input, authority, dependencies |
| `documents` | Real `.docx`, `.xlsx`, `.pptx`, `.pdf` files with the installed libraries |

### Recipes added with them

| Skill | Steps |
|---|---|
| `background_awareness` | `background_status` - front app, running apps, versions |
| `computer_preflight` | `get_active_window`, `inspect_accessibility`, `vision_capability_status` |
| `desktop_evidence` | `get_active_window`, `take_screenshot`, `vision_capability_status` |

All three read. None clicks, focuses or closes anything, because a recipe that
acts cannot be undone by the model that ran it.

### The awareness read

`core/situation.py` answers "what is open right now". It names the app in front
and the other known programs, with a version where the program records one.
Minecraft is the case that motivated it: the version comes from the running
game's `--version` argument or the launcher's last-used profile, so the answer is
"Minecraft 1.21.4" rather than "a Java process".

It never collects window titles, documents or command lines outside that one
Java case. `background_status` exposes the same read inside the skill engine, and
`main.py` puts one compact line into the session prompt, so the assistant starts
each session knowing what is open instead of asking.
