# Following upstream Mark

**What this is.** Ultron began as a copy of FatihMakes' MARK (licence CC BY-NC 4.0). It is not a GitHub fork, so the two
share no history, and git cannot merge a new Mark into Ultron. Mark gets a new version about every two weeks. This page
describes the tool that tells you, in plain words, what a new Mark changed and which parts clash with Ultron. **The tool
only reads. It never edits, pushes or merges.** Taking anything in is a separate change that you approve
(`DECISIONS.md` section 8, `docs/AGENT_MAINTENANCE.md` section 7).

Words used below:

- **Upstream**: FatihMakes' Mark repository, the original. **Drop**: one Mark version. A new drop is the first line of its
  `readme.md` changing (12 times between 2026-06-06 and 2026-11-11).
- **Pin**: `docs/upstream/PIN.json`, a note of two upstream commits: the one Ultron was copied from (the **base**) and the
  newest drop a person has looked at (the **reviewed** drop).
- **Ledger**: `docs/upstream/LEDGER.json`, one decision for each kind of upstream file.
- **Slice**: one small change that takes one idea from upstream, with its test, and nothing else.

## Running it

    python scripts/upstream_sync.py check                 # what moved since the reviewed drop
    python scripts/upstream_sync.py check --full          # everything since the copy
    python scripts/upstream_sync.py check --markdown report.md --json report.json
    python scripts/upstream_sync.py pin                   # the PIN.json block for upstream's newest commit

It needs `git`. It asks GitHub (`gh api repositories/1170311800`) what the repository is called now, because upstream is
one repository that is renamed with every Mark; the number stays. If `gh` cannot answer, it uses the address in the pin
and says so in the report. `--upstream DIR_OR_URL` reads a local clone instead, `--no-api` never asks GitHub.

| Exit | Meaning |
|---:|---|
| 0 | Upstream has not moved past the reviewed drop. The report says "No." |
| 10 | It moved. The report lists what changed. |
| 20 | It moved, and a stop sign needs a person first (below). |
| 2 | The check could not be made: a data file is wrong, upstream cannot be fetched, the pinned base commit or a `reconciled` commit is gone. No report is written. A check that cannot run has not passed. |

Any other number is a crash in the script itself, and a scheduled run treats it as a failure too. One Python file in
upstream that cannot be read (a NUL byte, nesting too deep, a link, a folder named like a module) does not stop the
report: it is named under Notes.

## Reading the report

Three versions of each changed file are compared: upstream when Ultron was copied, Ultron now, upstream now. Line endings
are ignored (upstream writes CRLF, Ultron LF).

| Kind | What it means | What to do |
|---|---|---|
| `COLLIDES` | Both changed the same place. | By hand, in a slice, test first. |
| `NAME_CLASH` | Upstream added a file with a name Ultron uses for something else. | Rename or merge by hand. |
| `DELETED_EDITED` | Upstream deleted a file Ultron has changed. | Usually keep Ultron's; decide on purpose. |
| `MERGES` | Both changed it, in different places. The text combines; the behaviour still needs tests. | A slice with tests. |
| `TAKE` | Only upstream changed it. | Apply after a test. |
| `NEW` | Upstream added it; Ultron has nothing of that name. | Read it; adopt in a slice or park it. |
| `OURS_GONE` | Ultron removed it; upstream changed it. | Usually nothing. |
| `DELETED_CLEAN` | Upstream deleted a file Ultron never changed. | Follow, if Ultron does not need it. |
| `LINE_ENDINGS`, `SAME`, `UNCHANGED`, `ALREADY_GONE` | Nothing to do. Not listed in the text. | None. |

Pointers from upstream's added or changed lines are not verdicts: new tools, new capabilities (network, other programs, the
registry), strings that say JARVIS or MARK, files cut to under half while Ultron changed them, and new modules that
nothing in upstream's own program imports.

**Stop and ask.** Exit 20 and a section at the top of the report when: the licence file changed or is gone; `requirements.txt`
changed (a new dependency needs your consent); a file that steers agents or models, or a referee file, changed (`AGENTS.md`,
`DECISIONS.md`, `core/policy.py` and the rest of the `STEERING` list in the script); or the reviewed commit is no longer in
upstream (history was rewritten; the report then measures from the copy).

**Text from upstream is untrusted.** File names, the readme title and requirement lines come from someone else. They are
shown only inside code spans, the readme title is cut to 60 printable characters, and nothing from upstream is ever pasted
into a shell command. A name that is not a plain relative path (a `..`, a backslash, a colon, a character that is not
valid text) is left out and listed under Notes: Windows would read it as another folder, another drive or a hidden
stream of another file. A link in upstream is never followed.

## The three data files

- `docs/upstream/PIN.json`: the base, the reviewed drop, and two fingerprints (SHA-256 of upstream's `LICENSE` and
  `requirements.txt` with line endings made LF). The `pin` command prints a new block. Change the pin in the same pull
  request that adopts or sets aside a drop, never on its own.
- `docs/upstream/LEDGER.json`: entries with `paths`, `disposition`, `reason`, `decided`. The first entry that matches a path
  wins; `*` matches anything, `/` included; matching is case-sensitive. Dispositions: `ours` (Ultron's version always wins;
  upstream's is read, not applied), `take`, `merge`, `later` (wanted, in a planned slice), `parked`, `rejected`. A file no
  entry matches is **held**: reported, never copied. An entry may carry `reconciled`, a full upstream commit id: once a
  file has been brought up to that version, the next check measures it from there, so it is not reported again.
- `docs/upstream/EXCLUSIONS.json`: what must stay out whatever a new Mark brings (next section).

## What stays out

| | Excluded | How it is held |
|---|---|---|
| E1 | News when Ultron opens | `tests/test_upstream_sync.py` reads every place the briefing is started and fails if one is not behind `get_brief_enabled()`; `tests/test_suite_assistant.py` (`BriefingOptInTests`) tests the default. |
| E2 | A news watch on a 30-minute timer | A tripwire: a test fails if the word `news_watch` appears in Ultron's own code. |
| E3 | Routines that run tools by themselves at launch | A tripwire on a routine of type `startup`. |

Every check also names the upstream files whose new or changed lines mention an exclusion, so a clash is seen before
anyone ports. The tripwire reads the folders in `tripwire_scope`, including `gui/`, which does not exist yet: the day the
window layer arrives it is already watched. Add an exclusion only with your word.

The owner's own data never comes from upstream: `config/api_keys.json`, `memory/long_term.json`, `config/self_change/`,
`state/`, `plugins/`.

## Taking something in (a slice)

1. You say which slice. Nothing is ported before that.
2. Read upstream's version next to Ultron's. Do not drop a file in. Measured on 2026-11-22 in a scratch tree and not re-run
   since: upstream's files took nine of twelve debt ceilings over, upstream's `actions/desktop.py` failed 44 of Ultron's
   wallpaper checks, and upstream's routine engine falls back to a news briefing.
3. Write the test first and watch it fail. Port the smallest change that makes it pass. Reuse Ultron's own guards (for
   example `actions/web_read.fetch_public_bytes`) instead of a second copy.
4. Anything that adds behaviour ships switched off, with its setting added through `memory/config_manager.py` only.
5. In the same pull request: the ledger entry (and `reconciled`), the pin when the whole drop is dealt with, and a row in
   `docs/UPSTREAM_RESEARCH.md` (adopted, already present, reimplemented, deferred or rejected).
6. Linux and Windows green, your OK, then merge.

**Rollback.** Revert the slice's commit, or switch its setting off. The ledger entry stays, so the file is reported again.

## The scheduled job

`.github/workflows/upstream-watch.yml` runs the check nine times a month, on days 1, 4, 7, 10, 13, 16, 19, 22 and 25 at
06:17 UTC (11:47 in India), and can be started by hand (Actions tab, "Upstream watch", Run workflow). It may read the
repository and write issues, and nothing else (`contents: read`, `issues: write`); a test holds it to that, and every
action in it is pinned to a commit.

Why named days and not "every three days": cron cannot say "nine a month", and a step such as `*/3` is ten or eleven days
in a long month. The list stops at the 25th so that February has all nine, and the longest wait between two looks is seven
days (the 25th to the 1st of a 31-day month), no longer than the weekly check this replaced (you changed it from weekly on
2026-11-24, before the first run). A test counts the looks in every month and the longest wait, and does not care which
nine days they are: to move them, change the list in the workflow file and in this paragraph.

- Upstream moved (exit 10 or 20): it keeps **one** open issue labelled `upstream-watch` and rewrites it, so there is never a
  pile of them.
- The pin has caught up (exit 0): it closes that issue with a comment. Without this the issue would go on saying "Yes,
  upstream moved" after you had adopted or set aside the drop.
- The check could not be made (exit 2 or a crash): the run fails, red, and the issue is left as it was.

GitHub runs a schedule only from the default branch, can delay or drop a run (06:17 is off the hour on purpose: the start
of an hour is when it is busiest), and switches schedules off in a public repository after 60 days without activity. So
every check compares with the pin, never with "the last look": a missed run loses nothing, and the next one reports the
whole gap. To switch the schedule off, delete the workflow file; the tool stays.

## Licence and attribution

CC BY-NC 4.0: publishing is allowed, selling is not, and the attribution in `LICENSE` and the readme stays. Taking material
means saying it was modified (CC BY-NC 4.0 section 3(a)(1)(A)(ii)). A changed licence file stops the check.

## Not verified yet

- The tool's tests have run on Linux and on Windows (the pull request's hosted runs: the first found three faults in the tests
  themselves, which were fixed, and the next passed on both). The seven tests of the workflow's steps skip on Windows on
  purpose, because they need a POSIX `bash` and `jq`. macOS has not been run at all.
- The workflow has not run on GitHub. Its issue steps were run only with a stand-in `gh` that records what it is asked, and
  the schedule has not fired (GitHub's documentation allows a list of days in the day-of-month field, read 2026-11-24; a run
  on the named days has not been seen). One GitHub behaviour was checked on the real repository on 2026-11-22: `gh issue list --label X`
  for a label that does not exist yet prints nothing and exits 0, which is what the first scheduled run meets.
- What the report says about upstream's code comes from reading its files and the lines it added. None of upstream's code
  was run.
