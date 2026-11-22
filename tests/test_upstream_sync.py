"""`scripts/upstream_sync.py`: it says truthfully what upstream Mark changed, and it changes nothing.

Ultron was copied from FatihMakes' MARK, which has a new version about every two weeks and shares no
history with this repository, so git cannot merge it. The script puts three versions of every file that
changed side by side (upstream when Ultron was copied, Ultron now, upstream now), sorts them into kinds
a person can act on, and `.github/workflows/upstream-watch.yml` turns the answer into one open issue.
What the owner relies on, and what these tests pin:

* each kind of change is told apart correctly, and line endings never count (upstream writes CRLF,
  Ultron writes LF);
* nothing is applied: Ultron's tree and the data files are byte-identical after a run;
* a licence change, a new requirement, a file that steers agents or models, or rewritten history stops
  the report and asks; a check that cannot run says so (exit 2) and a git failure is never read as
  "no such file";
* what the owner excluded (news on open, the 30-minute news watch, tools run by themselves at launch)
  is named whenever upstream touches it, and a tripwire fails if it appears in Ultron's own code;
* text that comes from upstream (a file name, a readme line, a requirement) cannot break the issue;
* the weekly job can read the repository and write issues and nothing else, and it closes its issue
  once the pin has caught up with upstream.

The upstream below is a real git repository in a temporary folder: no network, and no `gh` except the
stand-in the issue-step tests put first on the PATH.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("upstream_sync", ROOT / "scripts" / "upstream_sync.py")
sync = importlib.util.module_from_spec(SPEC)
sys.modules["upstream_sync"] = sync
SPEC.loader.exec_module(sync)

NOT_A_COMMIT = "a" * 40         # shaped like a commit id; no repository has it


# ------------------------------------------------------------------ a fake upstream, and a story around it

def numbered(count: int = 8) -> str:
    return "".join(f"line {number}\n" for number in range(1, count + 1))


def with_line(text: str, number: int, new: str, ending: str = "\n") -> str:
    lines = text.splitlines(keepends=True)
    lines[number - 1] = new + ending
    return "".join(lines)


def write_tree(folder: Path, files: dict) -> None:
    """Write these files under `folder`; a value of None removes the file."""
    for name, content in files.items():
        target = folder / name
        if content is None:
            target.unlink()
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))


def sha256_of(data: bytes | None) -> str:
    """Written out here and not borrowed from the script, so a bug in the script's version shows."""
    return "missing" if data is None else hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


class FakeUpstream:
    """A real git repository standing in for upstream Mark, built from dictionaries of files."""

    def __init__(self, folder: Path):
        self.path = folder / "mark"
        self.path.mkdir()
        nothing = folder / "gitconfig"
        nothing.write_text("", encoding="utf-8")
        # No machine-wide settings: a Windows runner turns line-ending conversion on, and these
        # tests need the bytes they write to be the bytes that are committed.
        self.env = {**os.environ, "GIT_CONFIG_GLOBAL": str(nothing), "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_TERMINAL_PROMPT": "0", "GIT_AUTHOR_NAME": "Upstream", "GIT_COMMITTER_NAME": "Upstream",
                    "GIT_AUTHOR_EMAIL": "upstream@example.invalid", "GIT_COMMITTER_EMAIL": "upstream@example.invalid"}
        self.git("init", "--quiet")

    def git(self, *args: str, input: bytes | None = None) -> bytes:
        done = subprocess.run(["git", *args], cwd=self.path, env=self.env, capture_output=True, input=input,  # noqa: S603, S607
                              timeout=60, check=False)    # a fixed git command in a scratch repository
        if done.returncode:
            raise RuntimeError(f"git {' '.join(args)} failed: {done.stderr.decode('utf-8', 'replace')}")
        return done.stdout

    def commit(self, files: dict, message: str = "a change") -> str:
        """Write these files (None removes one), commit everything, return the commit id."""
        write_tree(self.path, files)
        self.git("add", "--all")
        self.git("commit", "--quiet", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD").decode().strip()

    def commit_entries(self, entries: dict, message: str = "raw entries") -> str:
        """Commit paths exactly as given, without touching the working tree: `{path: (mode, bytes)}`.

        For what a file system may not take (a backslash in a name) or a test must not create (a symlink,
        mode 120000). Nothing may be committed with `commit()` after this, which would stage their removal.
        """
        for path, (mode, content) in entries.items():
            blob = self.git("hash-object", "-w", "--stdin", input=content).decode().strip()
            self.git("update-index", "--add", "--cacheinfo", f"{mode},{blob},{path}")
        self.git("commit", "--quiet", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD").decode().strip()

    def read(self, sha: str, name: str) -> bytes | None:
        try:
            return self.git("show", f"{sha}:{name}")
        except RuntimeError:
            return None


class Outcome:
    """What one run of the script gave back: exit status, what it printed, and the two files it wrote."""

    def __init__(self, code: int, out: str, err: str, markdown: Path, machine: Path):
        self.code, self.out, self.err = code, out, err
        self.markdown = markdown.read_text(encoding="utf-8") if markdown.exists() else None
        self.report = json.loads(machine.read_text(encoding="utf-8")) if machine.exists() else None

    def kinds(self) -> dict:
        return {row["path"]: row["kind"] for row in self.report["files"]}

    def row(self, path: str) -> dict:
        return next(row for row in self.report["files"] if row["path"] == path)


TERMS = {"LICENSE": "terms v1\n", "requirements.txt": "alpha>=1\nbeta>=2\n", "readme.md": "# MARK LVI (56)\nIntro\n"}
EXCLUSIONS = {"exclusions": [
    {"id": "E1", "name": "News on open", "rule": "r", "needles": ["_send_startup_briefing"], "guard": {"kind": "test"}},
    {"id": "E2", "name": "News watch", "rule": "r", "needles": ["news_watch"], "guard": {"kind": "tripwire"}},
]}


class Scenario:
    """Upstream, an Ultron tree and the three data files for one story, in one temporary folder.

    `base` is the whole upstream tree Ultron was copied from, `reviewed` (optional) is what the drop the
    owner last reviewed changed, `now` is what upstream's newest commit changed (None removes a file),
    and `ours` is the whole of Ultron's tree.
    """

    def __init__(self, cleanup, base: dict, now: dict, ours: dict, reviewed: dict | None = None):
        folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.upstream = FakeUpstream(self.folder)
        self.base_sha = self.upstream.commit(base, "the version Ultron was copied from")
        self.reviewed_sha = self.upstream.commit(reviewed, "the drop last reviewed") if reviewed else self.base_sha
        self.head_sha = self.upstream.commit(now, "upstream now")
        self.root = self.folder / "ultron"
        self.root.mkdir()
        write_tree(self.root, ours)
        self.data = self.folder / "data"
        self.data.mkdir()
        self.pin()
        self.ledger([])
        self.write("EXCLUSIONS.json", EXCLUSIONS)

    def write(self, name: str, data: dict) -> None:
        (self.data / name).write_text(json.dumps(data, indent=2), encoding="utf-8")

    def pin(self, reviewed: str | None = None, like: str | None = None, **changes) -> None:
        """Write PIN.json. `like` reads the fingerprints from another commit (for a reviewed one that vanished)."""
        sha = reviewed or self.reviewed_sha
        seen = like or sha
        pin = {"upstream": {"repo_id": 7, "name": "Someone/Mark-LVII", "url": str(self.upstream.path)},
               "base_sha": self.base_sha,
               "reviewed": {"sha": sha, "version": "MARK LVI (56)",
                            "licence_sha256": sha256_of(self.upstream.read(seen, "LICENSE")),
                            "requirements_sha256": sha256_of(self.upstream.read(seen, "requirements.txt"))}}
        self.write("PIN.json", {**pin, **changes})

    def ledger(self, entries: list) -> None:
        self.write("LEDGER.json", {"entries": entries})

    def decide(self, paths: list, disposition: str, reason: str = "decided for the test", **more) -> dict:
        return {"paths": paths, "disposition": disposition, "reason": reason, **more}

    def argv(self, *flags: str, command: str = "check") -> list:
        argv = [command, "--upstream", str(self.upstream.path), "--root", str(self.root), "--data", str(self.data)]
        if command == "check":
            argv += ["--markdown", str(self.folder / "report.md"), "--json", str(self.folder / "report.json")]
        return argv + list(flags)

    def run(self, *flags: str) -> Outcome:
        for name in ("report.md", "report.json"):
            (self.folder / name).unlink(missing_ok=True)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = sync.main(self.argv(*flags))
        return Outcome(code, out.getvalue(), err.getvalue(), self.folder / "report.md", self.folder / "report.json")

    def run_in_a_child(self, *flags: str, command: str = "check") -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "upstream_sync.py"),  # noqa: S603
                               *self.argv(*flags, command=command)],
                              capture_output=True, timeout=120, check=False)    # our own script, our own arguments


def a_story(cleanup, more_now: dict | None = None, more_ours: dict | None = None, reviewed: dict | None = None,
            more_base: dict | None = None) -> Scenario:
    """A small upstream that changed one file Ultron also has, so there is always something to report."""
    base = {**TERMS, "actions/tool.py": numbered(), **(more_base or {})}
    now = {"actions/tool.py": with_line(numbered(), 2, "upstream's edit"), **(more_now or {})}
    ours = {**TERMS, "actions/tool.py": numbered(), **(more_ours or {})}
    return Scenario(cleanup, base, now, ours, reviewed)


# ------------------------------------------------------------------ the kinds of change

class Classifying(unittest.TestCase):
    """Three versions of a file decide what kind of change it is. Line endings never count."""

    OLD = b"one\ntwo\nthree\nfour\nfive\nsix\nseven\neight\n"

    def edit(self, number: int, text: str, base: bytes | None = None) -> bytes:
        lines = (base or self.OLD).splitlines(keepends=True)
        lines[number - 1] = text.encode("utf-8") + b"\n"
        return b"".join(lines)

    def kind(self, base, theirs, ours, raw_same: bool = False) -> str:
        return sync.classify(base, theirs, ours, raw_same)

    def test_only_upstream_changed_it_so_the_change_applies_as_it_is(self):
        self.assertEqual(self.kind(self.OLD, self.edit(3, "theirs"), self.OLD), "TAKE")

    def test_both_changed_the_same_place_so_they_collide(self):
        self.assertEqual(self.kind(self.OLD, self.edit(3, "theirs"), self.edit(3, "ours")), "COLLIDES")

    def test_both_changed_different_places_so_the_text_merges_but_still_needs_tests(self):
        self.assertEqual(self.kind(self.OLD, self.edit(1, "theirs"), self.edit(8, "ours")), "MERGES")

    def test_the_same_change_on_both_sides_leaves_nothing_to_do(self):
        both = self.edit(3, "both")
        self.assertEqual(self.kind(self.OLD, both, both), "SAME")

    def test_a_file_upstream_added_that_ultron_never_had_is_new(self):
        self.assertEqual(self.kind(None, b"fresh\n", None), "NEW")

    def test_a_name_upstream_added_that_ultron_uses_for_something_else_is_a_name_clash(self):
        self.assertEqual(self.kind(None, b"theirs\n", b"ours\n"), "NAME_CLASH")
        self.assertEqual(self.kind(None, b"same\n", b"same\n"), "SAME")

    def test_deleting_what_ultron_left_alone_is_clean_and_deleting_what_it_changed_is_not(self):
        self.assertEqual(self.kind(self.OLD, None, self.OLD), "DELETED_CLEAN")
        self.assertEqual(self.kind(self.OLD, None, self.edit(2, "ours")), "DELETED_EDITED")

    def test_a_file_deleted_upstream_that_ultron_does_not_have_is_already_gone(self):
        self.assertEqual(self.kind(self.OLD, None, None), "ALREADY_GONE")

    def test_a_file_ultron_removed_that_upstream_changed_is_ours_gone(self):
        self.assertEqual(self.kind(self.OLD, self.edit(2, "theirs"), None), "OURS_GONE")

    def test_line_endings_alone_are_not_a_change(self):
        self.assertEqual(sync.plain(b"a\r\nb\r\n"), b"a\nb\n")
        self.assertIsNone(sync.plain(None))
        self.assertEqual(self.kind(b"a\nb\n", b"a\nb\n", b"x\n", raw_same=False), "LINE_ENDINGS")
        self.assertEqual(self.kind(b"a\nb\n", b"a\nb\n", b"x\n", raw_same=True), "UNCHANGED")

    def test_a_file_that_is_not_text_collides_whenever_both_sides_changed_it(self):
        self.assertEqual(self.kind(b"\0a", b"\0b", b"\0c"), "COLLIDES")
        self.assertFalse(sync.mergeable(b"\0a", b"\0b", b"\0c"))
        self.assertTrue(sync.mergeable(self.OLD, self.edit(1, "t"), self.edit(8, "o")))

    def test_git_counts_the_places_it_cannot_merge(self):
        self.assertEqual(sync.merge_conflicts(self.OLD, self.OLD, self.OLD), 0)
        self.assertEqual(sync.merge_conflicts(self.edit(3, "ours"), self.OLD, self.edit(3, "theirs")), 1)
        two_ours = self.edit(8, "o8", self.edit(2, "o2"))
        two_theirs = self.edit(8, "t8", self.edit(2, "t2"))
        self.assertEqual(sync.merge_conflicts(two_ours, self.OLD, two_theirs), 2)

    def test_every_kind_the_report_knows_can_happen_and_nothing_else_can(self):
        cases = {
            "COLLIDES": (self.OLD, self.edit(2, "t"), self.edit(2, "o"), False),
            "NAME_CLASH": (None, b"t\n", b"o\n", False),
            "DELETED_EDITED": (self.OLD, None, self.edit(2, "o"), False),
            "MERGES": (self.OLD, self.edit(1, "t"), self.edit(8, "o"), False),
            "TAKE": (self.OLD, self.edit(2, "t"), self.OLD, False),
            "NEW": (None, b"t\n", None, False),
            "OURS_GONE": (self.OLD, self.edit(2, "t"), None, False),
            "DELETED_CLEAN": (self.OLD, None, self.OLD, False),
            "LINE_ENDINGS": (self.OLD, self.OLD, self.OLD, False),
            "SAME": (self.OLD, self.edit(2, "x"), self.edit(2, "x"), False),
            "UNCHANGED": (self.OLD, self.OLD, self.OLD, True),
            "ALREADY_GONE": (self.OLD, None, None, False),
        }
        self.assertEqual(set(cases), set(sync.KINDS), "the table must list exactly the kinds the report names")
        for expected, (base, theirs, ours, raw_same) in cases.items():
            self.assertEqual(self.kind(base, theirs, ours, raw_same), expected)
        self.assertTrue(sync.QUIET <= set(sync.KINDS))
        self.assertEqual(list(sync.KINDS)[:2], ["COLLIDES", "NAME_CLASH"], "the kinds that need a person come first")


class TheLedgerRules(unittest.TestCase):
    """A decision is looked up by path pattern: the first entry that matches wins."""

    def ledger(self, *rows) -> dict:
        return {"entries": [{"paths": list(paths), "disposition": word, "reason": "r"} for paths, word in rows]}

    def test_the_first_matching_entry_wins(self):
        ledger = self.ledger((["core/x.py"], "ours"), (["core/*"], "later"))
        self.assertEqual(sync.ledger_decision(ledger, "core/x.py")["disposition"], "ours")
        self.assertEqual(sync.ledger_decision(ledger, "core/y.py")["disposition"], "later")

    def test_a_star_matches_across_folders(self):
        ledger = self.ledger((["gui/*"], "later"))
        self.assertIsNotNone(sync.ledger_decision(ledger, "gui/widgets/panel.py"))

    def test_a_file_no_entry_matches_has_no_decision_and_is_held(self):
        self.assertIsNone(sync.ledger_decision(self.ledger((["core/*"], "ours")), "actions/x.py"))

    def test_matching_is_case_sensitive_on_every_system(self):
        self.assertIsNone(sync.ledger_decision(self.ledger((["Core/*"], "ours")), "core/x.py"))


# ------------------------------------------------------------------ one whole run

class TheFirstScenario(unittest.TestCase):
    """A drop with one file of every kind that needs a person, run once and read many ways."""

    OLD = numbered()
    EXPECTED = {
        "main.py": "COLLIDES", "actions/notes.py": "MERGES", "actions/clock.py": "TAKE", "core/fresh.py": "NEW",
        "core/clash.py": "NAME_CLASH", "core/twin.py": "SAME", "core/old.py": "DELETED_CLEAN",
        "core/touched.py": "DELETED_EDITED", "core/missing.py": "OURS_GONE", "core/endings.py": "LINE_ENDINGS",
        "core/dropped.py": "ALREADY_GONE",
    }

    @classmethod
    def setUpClass(cls):
        old, crlf = cls.OLD, cls.OLD.replace("\n", "\r\n")
        base = {**TERMS, "main.py": old, "actions/notes.py": old, "actions/clock.py": crlf, "core/old.py": old,
                "core/touched.py": old, "core/missing.py": old, "core/endings.py": "a\r\nb\r\nc\r\n",
                "core/dropped.py": old}
        now = {"main.py": with_line(old, 2, "theirs"), "actions/notes.py": with_line(old, 1, "theirs"),
               "actions/clock.py": with_line(crlf, 4, "theirs", "\r\n"), "core/fresh.py": "print('fresh')\n",
               "core/clash.py": "theirs\n", "core/twin.py": "same\n", "core/old.py": None, "core/touched.py": None,
               "core/missing.py": with_line(old, 3, "theirs"), "core/endings.py": "a\nb\nc\n", "core/dropped.py": None}
        # Ultron keeps LF everywhere, even in the file upstream writes with CRLF (actions/clock.py).
        ours = {**TERMS, "main.py": with_line(old, 2, "ours"), "actions/notes.py": with_line(old, 8, "ours"),
                "actions/clock.py": old, "core/old.py": old, "core/touched.py": with_line(old, 5, "ours"),
                "core/clash.py": "ours\n", "core/twin.py": "same\n", "core/endings.py": "a\nb\nc\n"}
        cls.story = Scenario(cls.addClassCleanup, base, now, ours)
        cls.outcome = cls.story.run()

    def test_every_kind_is_told_apart_even_when_upstream_writes_crlf_and_ultron_lf(self):
        self.assertEqual(self.outcome.kinds(), self.EXPECTED)

    def test_the_counts_add_up_and_follow_the_order_of_the_report(self):
        counts = self.outcome.report["counts"]
        self.assertEqual(counts, {kind: 1 for kind in sync.KINDS if kind in set(self.EXPECTED.values())})
        self.assertEqual(list(counts), [kind for kind in sync.KINDS if kind in counts])

    def test_moved_without_a_gate_is_exit_10_and_nothing_is_decided_yet(self):
        self.assertEqual(self.outcome.code, sync.EXIT_MOVED)
        self.assertEqual({row["decision"] for row in self.outcome.report["files"]}, {"held"})
        self.assertEqual(self.outcome.report["gates"], [])

    def test_the_report_says_yes_and_how_far_it_looked(self):
        text = self.outcome.markdown
        self.assertIn("**Yes, upstream moved.** 1 commit(s) since the drop you last reviewed", text)
        self.assertIn("11 file(s) differ.", text)
        self.assertEqual(text.splitlines()[0], "# Upstream watch: `MARK LVI (56)`, new commits")

    def test_what_needs_a_person_is_listed_by_kind_and_the_quiet_kinds_are_not(self):
        text = self.outcome.markdown
        for line in ("**Both sides changed the same place** (1): `main.py`",
                     "**Upstream added a file whose name ultron already uses for something else** (1): `core/clash.py`",
                     "**Upstream deleted a file ultron has changed** (1): `core/touched.py`",
                     "(the text merges; it still needs tests)** (1): `actions/notes.py`"):
            self.assertIn(line, text)
        self.assertIn("8 file(s) have no ledger decision yet, so they are held and not copied", text)
        self.assertNotIn("core/twin.py", text)             # the same on both sides: quiet
        self.assertNotIn("core/dropped.py", text)          # gone on both sides: quiet

    def test_it_ends_by_saying_that_nothing_was_applied(self):
        self.assertIn("Nothing has been applied. This report only reads.", self.outcome.markdown)
        self.assertEqual(self.outcome.out.strip(), self.outcome.markdown.strip())

    def test_the_machine_copy_holds_the_commits_and_the_scope(self):
        report = self.outcome.report
        self.assertEqual((report["new_sha"], report["scope"]), (self.story.head_sha, self.story.reviewed_sha))
        self.assertEqual((report["commits"], report["moved"], report["full"]), (1, True, False))
        self.assertEqual(report["version"], "MARK LVI (56)")

    def test_a_new_file_has_its_size_counted(self):
        row = self.outcome.row("core/fresh.py")
        self.assertEqual((row["lines_before"], row["lines_after"]), (0, 1))


class TheLedgerAtWork(unittest.TestCase):
    """A decision in the ledger moves a file out of 'needs a decision', and says why."""

    def story(self, entries: list) -> Outcome:
        story = a_story(self.addCleanup, {"core/fresh.py": "print('x')\n", "core/other.py": "print('y')\n"})
        story.ledger([story.decide(*entry[:2], **entry[2]) for entry in entries] if entries else [])
        return story.run()

    def test_a_decided_file_is_reported_under_its_decision_and_not_as_held(self):
        outcome = self.story([(["core/*"], "later", {"reason": "planned slice 3"})])
        self.assertEqual(outcome.row("core/fresh.py")["decision"], "later")
        self.assertEqual(outcome.row("core/fresh.py")["reason"], "planned slice 3")
        self.assertEqual(outcome.row("actions/tool.py")["decision"], "held")
        self.assertIn("## Already decided by the ledger", outcome.markdown)
        self.assertIn("- **later** (2): `core/fresh.py`, `core/other.py`", outcome.markdown)
        self.assertIn("1 file(s) have no ledger decision yet", outcome.markdown)

    def test_a_ledger_that_decides_everything_leaves_nothing_held(self):
        outcome = self.story([(["*"], "parked", {})])
        self.assertNotIn("have no ledger decision yet", outcome.markdown)
        self.assertEqual({row["decision"] for row in outcome.report["files"]}, {"parked"})

    def test_a_decided_collision_is_not_listed_as_needing_one(self):
        story = a_story(self.addCleanup, more_ours={"actions/tool.py": with_line(numbered(), 2, "ours")})
        story.ledger([story.decide(["actions/tool.py"], "merge")])
        outcome = story.run()
        self.assertEqual(outcome.kinds()["actions/tool.py"], "COLLIDES")
        self.assertNotIn("## Needs a decision", outcome.markdown)
        self.assertIn("- **merge** (1): `actions/tool.py`", outcome.markdown)


class TheScopeOfACheck(unittest.TestCase):
    """The default measures from the drop last reviewed; `--full` measures from the copy."""

    def story(self) -> Scenario:
        old = numbered()
        return Scenario(self.addCleanup, {**TERMS, "a.py": old, "b.py": old},
                        {"b.py": with_line(old, 5, "newest")}, {**TERMS, "a.py": old, "b.py": old},
                        reviewed={"a.py": with_line(old, 3, "already reviewed")})

    def test_by_default_only_what_changed_since_the_reviewed_drop_is_listed(self):
        outcome = self.story().run()
        self.assertEqual(outcome.kinds(), {"b.py": "TAKE"})
        self.assertIn("1 commit(s) since the drop you last reviewed", outcome.markdown)

    def test_full_lists_everything_since_the_copy_and_says_so(self):
        outcome = self.story().run("--full")
        self.assertEqual(outcome.kinds(), {"a.py": "TAKE", "b.py": "TAKE"})
        self.assertEqual(outcome.report["commits"], 2)
        self.assertTrue(outcome.report["full"])
        self.assertEqual(outcome.markdown.splitlines()[0], "# Upstream watch: `MARK LVI (56)`, everything since the copy")
        self.assertIn("**Full comparison.**", outcome.markdown)

    def test_full_reports_even_when_the_pin_is_up_to_date(self):
        story = self.story()
        story.pin(story.head_sha)
        outcome = story.run("--full")
        self.assertTrue(outcome.report["moved"])
        self.assertEqual(outcome.code, sync.EXIT_MOVED)

    def test_a_new_version_name_is_read_from_the_first_line_of_the_readme(self):
        story = a_story(self.addCleanup, {"readme.md": "# MARK LVII (57)\nIntro\n"})
        outcome = story.run()
        self.assertEqual(outcome.report["version"], "MARK LVII (57)")
        self.assertEqual(outcome.markdown.splitlines()[0], "# Upstream watch: `MARK LVI (56)` -> `MARK LVII (57)`")

    def test_a_file_reconciled_to_a_later_commit_is_measured_from_there(self):
        old = numbered()
        story = Scenario(self.addCleanup, {**TERMS, "x.py": old, "y.py": old},
                         {"x.py": with_line(with_line(old, 2, "v2"), 6, "v3")},
                         {**TERMS, "x.py": with_line(old, 2, "v2"), "y.py": with_line(old, 2, "v2")},
                         reviewed={"x.py": with_line(old, 2, "v2"), "y.py": with_line(old, 2, "v2")})
        without = story.run("--full")
        self.assertEqual(without.kinds(), {"x.py": "MERGES", "y.py": "SAME"})
        story.ledger([story.decide(["x.py", "y.py"], "take", reconciled=story.reviewed_sha)])
        with_it = story.run("--full")
        self.assertEqual(with_it.kinds(), {"x.py": "TAKE", "y.py": "UNCHANGED"},
                         "measured from the reconciled commit, Ultron already has v2 and upstream moved on only in x.py")


# ------------------------------------------------------------------ what upstream's new lines are about

class WhatTheChangeIsAbout(unittest.TestCase):
    """Pointers for the reader, drawn from the lines upstream added or changed, not a verdict."""

    def outcome(self, files: dict) -> Outcome:
        return a_story(self.addCleanup, files).run()

    def test_a_new_tool_is_named(self):
        outcome = self.outcome({"actions/shiny.py": 'TOOL = {\n    "name": "shiny_tool",\n}\n'})
        self.assertEqual(outcome.row("actions/shiny.py")["tool"], "shiny_tool")
        self.assertIn("- New tools: `actions/shiny.py` (tool shiny_tool)", outcome.markdown)

    def test_a_name_outside_the_tool_folders_is_not_taken_for_a_tool(self):
        outcome = self.outcome({"core/shiny.py": 'TOOL = {\n    "name": "shiny_tool",\n}\n'})
        self.assertEqual(outcome.row("core/shiny.py")["tool"], "")

    def test_new_capabilities_are_pointed_out_from_the_added_lines(self):
        outcome = self.outcome({"core/net.py": "import socket\ns = socket.socket()\nsubprocess.run(['x'])\nimport winreg\n"})
        self.assertEqual(sorted(outcome.row("core/net.py")["risks"]),
                         ["opens network connections", "runs other programs", "uses the Windows registry"])
        self.assertIn("- New code that runs other programs: `core/net.py`", outcome.markdown)

    def test_only_the_lines_upstream_added_count_not_the_ones_that_were_already_there(self):
        old = "import subprocess\nsubprocess.run(['x'])\n" + numbered()
        story = Scenario(self.addCleanup, {**TERMS, "core/old.py": old},
                         {"core/old.py": old + "print('only this was added')\n"}, {**TERMS, "core/old.py": old})
        self.assertEqual(story.run().row("core/old.py")["risks"], [])

    def test_strings_that_name_the_old_brand_are_counted(self):
        outcome = self.outcome({"core/voice.py": 'SAY = "Hello, I am JARVIS, MARK LVII"\nOTHER = "Jarvis"\n'})
        self.assertEqual(outcome.row("core/voice.py")["brand"], 3)
        self.assertIn("3 added string(s) say JARVIS or MARK/Mark LVII; Ultron's name is Ultron.", outcome.markdown)

    def test_a_file_upstream_cut_to_less_than_half_while_ultron_changed_it_is_flagged(self):
        big, small = numbered(120), numbered(40)
        story = Scenario(self.addCleanup, {**TERMS, "core/big.py": big, "core/same.py": big}, {"core/big.py": small, "core/same.py": small},
                         {**TERMS, "core/big.py": with_line(big, 60, "ours"), "core/same.py": big})
        outcome = story.run()
        self.assertTrue(outcome.row("core/big.py")["restructured"])
        self.assertFalse(outcome.row("core/same.py")["restructured"], "Ultron never touched it, so nothing is lost")
        self.assertIn("- Restructured upstream (lost over half its lines while Ultron changed it): `core/big.py`", outcome.markdown)

    def test_a_file_that_is_not_text_is_classified_but_not_read_for_signals(self):
        story = Scenario(self.addCleanup, {**TERMS, "assets/logo.png": b"\x89PNG\0old"}, {"assets/logo.png": b"\x89PNG\0new"},
                         {**TERMS, "assets/logo.png": b"\x89PNG\0old"})
        outcome = story.run()
        self.assertEqual(outcome.kinds(), {"assets/logo.png": "TAKE"})
        self.assertEqual((outcome.row("assets/logo.png")["risks"], outcome.row("assets/logo.png")["lines_after"]), ([], 0))


class Unwired(unittest.TestCase):
    """New upstream code that upstream's own program never imports is probably not part of the product."""

    MAIN = "from core import helper\n"
    NEW = {
        "main.py": MAIN,
        "core/__init__.py": "",
        "core/helper.py": "from . import sibling\nfrom .deep import thing\n\n\ndef later():\n    import core.late\n",
        "core/sibling.py": "X = 1\n",
        "core/deep/__init__.py": "",
        "core/deep/thing.py": "from .. import extra\nfrom ..extra2 import value\n",
        "core/extra.py": "X = 2\n",
        "core/extra2.py": "value = 3\n",
        "core/late.py": "X = 5\n",
        "core/orphan.py": "X = 4\n",
        "core/chain.py": "from core import orphan\n",
        "actions/tool.py": "X = 6\n",
    }

    def outcome(self) -> Outcome:
        story = Scenario(self.addCleanup, {**TERMS, "main.py": "print('hi')\n"}, self.NEW, {**TERMS, "main.py": "print('hi')\n"})
        return story.run()

    def test_only_what_nothing_reaches_is_flagged(self):
        outcome = self.outcome()
        flagged = sorted(row["path"] for row in outcome.report["files"] if row["unwired"])
        self.assertEqual(flagged, ["core/chain.py", "core/orphan.py"],
                         "orphan.py is imported only by chain.py, and nothing imports chain.py")

    def test_an_import_with_dots_counts_like_any_other(self):
        # Review finding 1: `from . import x`, `from .x import y` and `from ..x import y` were skipped, so
        # a file used only that way was reported as code nothing imports.
        outcome = self.outcome()
        for path in ("core/sibling.py", "core/deep/thing.py", "core/extra.py", "core/extra2.py"):
            self.assertFalse(outcome.row(path)["unwired"], f"{path} is reached through a relative import")

    def test_the_tool_folders_are_entry_points_and_a_late_import_inside_a_function_counts(self):
        outcome = self.outcome()
        self.assertFalse(outcome.row("actions/tool.py")["unwired"])
        self.assertFalse(outcome.row("core/late.py")["unwired"])

    def test_the_report_names_them(self):
        self.assertIn("- New code that nothing in upstream's own program imports: `core/chain.py`, `core/orphan.py`",
                      self.outcome().markdown)

    def test_relative_names_are_resolved_against_the_importing_module(self):
        table = [("from . import a", "pkg", {"pkg", "pkg.a"}),
                 ("from .b import c", "pkg", {"pkg.b", "pkg.b.c"}),
                 ("from ..d import e", "pkg.sub", {"pkg.d", "pkg.d.e"}),
                 ("from .. import f", "pkg.sub", {"pkg", "pkg.f"}),
                 ("from .. import g", "top", {"g"}),               # above the top package the names are bare
                 ("from ... import h", "pkg", set()),              # past the top: not a real import
                 ("import a.b.c\nfrom x import y", "", {"a.b.c", "x", "x.y"})]
        for source, package, expected in table:
            self.assertEqual(sync.imported_names(source, package), expected, source)


class AFileThatCannotBeParsed(unittest.TestCase):
    """Review finding 3: one strange file in upstream must not stop the weekly report."""

    NUL = "x = 1\0\n"
    DEEP = "x = " + "-" * 5000 + "1\n"
    TOO_DEEP = "x = " + "-" * 100000 + "1\n"

    def test_the_reader_of_imports_says_a_file_is_unreadable_and_nothing_else(self):
        for label, source in (("a NUL byte", self.NUL), ("5,000 nested operators", self.DEEP),
                              ("100,000 nested operators", self.TOO_DEEP), ("a syntax error", "def (:\n")):
            with self.subTest(label), self.assertRaises(sync.Unreadable):
                sync.imported_names(source)
        self.assertEqual(sync.imported_names("import os\n"), {"os"})

    def test_the_report_still_comes_and_says_which_files_it_could_not_read(self):
        # Only files upstream's own program can reach are read (the tool folders always count), so the strange
        # ones sit there; the one nothing imports is never opened and is not mentioned.
        story = Scenario(self.addCleanup, {**TERMS, "main.py": "print('hi')\n"},
                         {"actions/strange.py": self.DEEP, "actions/nul.py": self.NUL, "actions/fine.py": "X = 1\n",
                          "core/unused_and_strange.py": self.DEEP}, {**TERMS, "main.py": "print('hi')\n"})
        outcome = story.run()
        self.assertEqual(outcome.code, sync.EXIT_MOVED, outcome.err)
        self.assertEqual(outcome.err, "")
        notes = " ".join(outcome.report["notes"])
        self.assertIn("2 Python file(s) in upstream could not be read to see what they import", notes)
        self.assertIn("`actions/nul.py`, `actions/strange.py`", notes)
        self.assertNotIn("fine.py", notes)
        self.assertNotIn("unused_and_strange", notes)
        self.assertIn("## Notes", outcome.markdown)


class UpstreamEntriesThatAreNotOrdinaryFiles(unittest.TestCase):
    """Upstream is somebody else's repository: a name, a symlink or a folder in it is not trusted to be a plain file."""

    NAMES = {
        "core/x.py": True, "a/b/c.txt": True, "name with spaces.py": True, "dots.in.name.py": True,
        ".github/workflows/x.yml": True,
        "": False, ".": False, "..": False, "../x": False, "a/../x": False, "a/..": False, "/etc/passwd": False,
        "a\\..\\b": False, "a\\b": False, "C:/x": False, "C:x": False, "x.txt:stream": False, "a\0b": False, "a\ufffdb": False,
    }

    def tree(self, folder: str) -> Path:
        tree = Path(folder, "tree")
        (tree / "actions").mkdir(parents=True)
        (tree / "core").mkdir()
        (tree / "main.py").write_text("", encoding="utf-8")
        (tree / "core" / "orphan.py").write_text("X = 1\n", encoding="utf-8")
        return tree

    def test_only_names_that_stay_inside_the_folder_are_read(self):
        # Git allows names that Windows reads as something else (`a\\..\\b` leaves the folder, `C:x` is another
        # drive, `x.txt:stream` is a hidden stream), and this script runs there too.
        for name, expected in self.NAMES.items():
            self.assertEqual(sync.safe_path(name), expected, repr(name))

    def test_a_name_that_could_leave_the_folder_is_left_out_and_the_report_says_so(self):
        story = a_story(self.addCleanup)
        try:
            story.upstream.commit_entries({"core\\..\\..\\outside.py": (100644, b"X = 1\n"), "fine/inside.py": (100644, b"X = 2\n")})
        except RuntimeError as refused:
            self.skipTest(f"this git will not store that name here, so only the table above runs: {refused}")
        outcome = story.run()
        self.assertEqual(outcome.code, sync.EXIT_MOVED, outcome.err)
        self.assertIn("fine/inside.py", outcome.kinds())
        self.assertEqual([name for name in outcome.kinds() if "outside" in name], [], "the unsafe name is not described")
        notes = " ".join(outcome.report["notes"])
        self.assertIn("1 path(s) in upstream were left out because their names are not plain relative paths", notes)
        self.assertIn("outside.py", notes)

    def test_a_folder_named_like_a_module_is_unreadable_and_nothing_more(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            tree = self.tree(folder)
            (tree / "actions" / "dir.py").mkdir()
            (tree / "actions" / "ok.py").write_text("import core.orphan\n", encoding="utf-8")
            seen, unreadable = sync.reachable(tree)
        self.assertEqual(unreadable, ["actions/dir.py"])
        self.assertIn("core.orphan", seen, "the readable file next to it still counts")

    def test_the_report_still_comes_when_upstream_has_a_folder_named_like_a_module(self):
        story = a_story(self.addCleanup, {"actions/dir.py/inner.txt": "not python\n", "actions/ok.py": "X = 1\n"})
        outcome = story.run()
        self.assertEqual(outcome.code, sync.EXIT_MOVED, outcome.err)
        self.assertEqual(outcome.err, "")
        self.assertIn("`actions/dir.py`", " ".join(outcome.report["notes"]))

    def test_a_file_the_system_will_not_open_is_unreadable_and_not_a_crash(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            target = Path(folder, "locked.py")
            target.write_text("X = 1\n", encoding="utf-8")
            with mock.patch.object(Path, "read_text", side_effect=PermissionError("denied")):
                with self.assertRaises(sync.Unreadable):
                    sync.read_source(target)
            self.assertEqual(sync.read_source(target), "X = 1\n", "the same file reads normally when nothing stops it")

    def test_a_symlink_in_upstream_is_not_followed_out_of_the_clone(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            tree = self.tree(folder)
            outside = Path(folder, "outside.py")
            outside.write_text("import core.orphan\n", encoding="utf-8")       # what a followed link would read
            try:
                os.symlink(outside, tree / "actions" / "link.py")
            except (OSError, NotImplementedError) as refused:
                self.skipTest(f"this system will not make a symlink here: {refused}")
            seen, unreadable = sync.reachable(tree)
        self.assertNotIn("core.orphan", seen, "the link's target was read")
        self.assertEqual(unreadable, ["actions/link.py"])


# ------------------------------------------------------------------ stop and ask, and the errors

class TheGatesAndTheErrors(unittest.TestCase):
    """A person must look before anything is taken, and a check that cannot run has not passed."""

    def gates(self, outcome: Outcome) -> str:
        return " ".join(outcome.report["gates"])

    def test_a_changed_licence_stops_and_asks(self):
        outcome = a_story(self.addCleanup, {"LICENSE": "terms v2\n"}).run()
        self.assertEqual(outcome.code, sync.EXIT_STOP)
        self.assertIn("The licence changed", self.gates(outcome))
        self.assertIn("## Stop and ask", outcome.markdown)
        self.assertIn(sha256_of(b"terms v2\n")[:12], self.gates(outcome))

    def test_a_licence_that_disappeared_stops_too(self):
        outcome = a_story(self.addCleanup, {"LICENSE": None}).run()
        self.assertEqual(outcome.code, sync.EXIT_STOP)
        self.assertIn("or its file is gone", self.gates(outcome))

    def test_a_new_requirement_stops_and_is_named(self):
        outcome = a_story(self.addCleanup, {"requirements.txt": "alpha>=1\nbeta>=2\ngamma>=3\n"}).run()
        self.assertEqual(outcome.code, sync.EXIT_STOP)
        self.assertIn("added or changed: `gamma>=3`", self.gates(outcome))
        self.assertIn("A new dependency needs your consent.", self.gates(outcome))

    def test_a_requirements_file_with_only_comments_changed_still_asks_and_says_so(self):
        outcome = a_story(self.addCleanup, {"requirements.txt": "# a note\nalpha>=1\nbeta>=2\n"}).run()
        self.assertEqual(outcome.code, sync.EXIT_STOP)
        self.assertIn("only comments or ordering.", self.gates(outcome))

    def test_a_steering_file_stops_and_is_never_applied(self):
        outcome = a_story(self.addCleanup, {"AGENTS.md": "new rules\n"}, {"AGENTS.md": "our rules\n"},
                          more_base={"AGENTS.md": "old rules\n"}).run()
        self.assertEqual(outcome.code, sync.EXIT_STOP)
        self.assertIn("Upstream changed `AGENTS.md`. These steer agents, models or the rules here", self.gates(outcome))

    def test_a_steering_file_whose_line_endings_alone_changed_does_not_stop(self):
        outcome = a_story(self.addCleanup, {"AGENTS.md": "rules\n"}, {"AGENTS.md": "rules\n"},
                          more_base={"AGENTS.md": "rules\r\n"}).run()
        self.assertEqual(outcome.kinds()["AGENTS.md"], "LINE_ENDINGS")
        self.assertEqual(outcome.code, sync.EXIT_MOVED)

    def test_a_workflow_file_counts_as_steering(self):
        outcome = a_story(self.addCleanup, {".github/workflows/x.yml": "on: push\n"}).run()
        self.assertEqual(outcome.code, sync.EXIT_STOP)
        self.assertIn("`.github/workflows/x.yml`", self.gates(outcome))

    def test_the_terms_are_compared_with_the_reviewed_drop_and_under_full_with_the_copy(self):
        story = Scenario(self.addCleanup, {**TERMS}, {"readme.md": "# MARK LVI (56)\nmore\n"}, {**TERMS},
                         reviewed={"LICENSE": "terms v2\n"})
        self.assertEqual(story.run().code, sync.EXIT_MOVED, "the licence changed before the reviewed drop, not since")
        self.assertEqual(story.run("--full").code, sync.EXIT_STOP, "since the copy it did change")

    def test_a_reviewed_commit_that_vanished_is_a_gate_and_everything_since_the_copy_is_listed(self):
        story = a_story(self.addCleanup)
        story.pin(NOT_A_COMMIT, like=story.base_sha)
        outcome = story.run()
        self.assertEqual(outcome.code, sync.EXIT_STOP)
        self.assertEqual(len(outcome.report["gates"]), 1)
        self.assertIn(f"The reviewed commit {NOT_A_COMMIT[:12]} is no longer in upstream", self.gates(outcome))
        self.assertEqual(outcome.report["scope"], story.base_sha)
        self.assertIn("actions/tool.py", outcome.kinds())

    def test_a_vanished_reviewed_commit_does_not_hide_a_new_requirement(self):
        # A guard against a fix going too far: with the reviewed commit gone there is nothing to read the
        # old requirements from, and that must not turn the report into an error.
        story = a_story(self.addCleanup, {"requirements.txt": "alpha>=1\nbeta>=2\ngamma>=3\n"})
        story.pin(NOT_A_COMMIT, like=story.base_sha)
        outcome = story.run()
        self.assertEqual(outcome.code, sync.EXIT_STOP, outcome.err)
        self.assertIn("added or changed: `gamma>=3`", self.gates(outcome))
        self.assertNotIn("alpha", self.gates(outcome), "measured from the copy: only what is new is new")

    def test_a_pinned_base_that_vanished_is_exit_2_not_a_guess(self):
        story = a_story(self.addCleanup)
        story.pin(base_sha=NOT_A_COMMIT)
        outcome = story.run()
        self.assertEqual(outcome.code, sync.EXIT_ERROR)
        self.assertIn("the pinned base commit is no longer in upstream", outcome.err)
        self.assertIsNone(outcome.markdown, "a check that could not run writes no report to be mistaken for an answer")

    def test_upstream_that_has_not_moved_is_exit_0_and_says_no(self):
        story = a_story(self.addCleanup)
        story.pin(story.head_sha)
        outcome = story.run()
        self.assertEqual(outcome.code, sync.EXIT_SAME)
        self.assertTrue(outcome.markdown.startswith("**No.** Upstream has not moved past the drop last reviewed"))
        self.assertFalse(outcome.report["moved"])
        self.assertEqual(outcome.report["reviewed_sha"], story.head_sha)

    def test_an_upstream_that_cannot_be_fetched_is_exit_2(self):
        story = a_story(self.addCleanup)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = sync.main(["check", "--upstream", str(story.folder / "nowhere"), "--root", str(story.root), "--data", str(story.data)])
        self.assertEqual(code, sync.EXIT_ERROR)
        self.assertIn("could not fetch upstream", err.getvalue())

    def test_a_data_file_that_is_wrong_is_exit_2_with_a_reason_and_no_report(self):
        good = {"upstream": {"repo_id": 7, "name": "A/B", "url": "u"}, "base_sha": NOT_A_COMMIT,
                "reviewed": {"sha": NOT_A_COMMIT, "version": "v", "licence_sha256": "x", "requirements_sha256": "y"}}
        entry = {"paths": ["a"], "disposition": "take", "reason": "because"}
        needles = {"id": "E9", "name": "n", "rule": "r", "needles": ["x"], "guard": {"kind": "tripwire"}}
        cases = [
            ("PIN.json", {**good, "base_sha": "abc"}, "is not a full commit id"),
            ("PIN.json", {k: v for k, v in good.items() if k != "reviewed"}, "is missing reviewed"),
            ("PIN.json", [1], "must hold one JSON object"),
            ("LEDGER.json", {}, "is missing entries"),
            ("LEDGER.json", {"entries": 5}, "entries must be a list"),
            ("LEDGER.json", {"entries": "abc"}, "entries must be a list"),
            ("LEDGER.json", {"entries": [{**entry, "paths": "abc"}]}, "needs a list of path patterns"),
            ("LEDGER.json", {"entries": [{**entry, "paths": 5}]}, "needs a list of path patterns"),
            ("EXCLUSIONS.json", {"exclusions": 5}, "exclusions must be a list"),
            ("LEDGER.json", {"entries": [{**entry, "disposition": "maybe"}]}, "'maybe' is not one of"),
            ("LEDGER.json", {"entries": [{**entry, "reason": "  "}]}, "has no reason"),
            ("LEDGER.json", {"entries": [{**entry, "paths": []}]}, "needs a list of path patterns"),
            ("LEDGER.json", {"entries": [{**entry, "paths": [7]}]}, "needs a list of path patterns"),
            ("LEDGER.json", {"entries": [{k: v for k, v in entry.items() if k != "paths"}]}, "is missing paths"),
            ("LEDGER.json", {"entries": [{**entry, "reconciled": "abc"}]}, "reconciled must be a full commit id"),
            ("EXCLUSIONS.json", {"exclusions": [needles, needles]}, "appears twice"),
            ("EXCLUSIONS.json", {"exclusions": [{**needles, "needles": []}]}, "needs a list of needles"),
            ("EXCLUSIONS.json", {"exclusions": [{**needles, "needles": ["("]}]}, "is not a regular expression"),
            ("EXCLUSIONS.json", {"exclusions": [{**needles, "needles": [3]}]}, "every needle must be text"),
            ("EXCLUSIONS.json", {"exclusions": [{**needles, "guard": {"kind": "hope"}}]}, "guard kind must be one of"),
        ]
        story = a_story(self.addCleanup)
        for name, content, fragment in cases:
            with self.subTest(name=name, fragment=fragment):
                story.pin()
                story.ledger([])
                story.write("EXCLUSIONS.json", EXCLUSIONS)
                story.write(name, content)
                outcome = story.run()
                self.assertEqual(outcome.code, sync.EXIT_ERROR)
                self.assertIn(fragment, outcome.err)
                self.assertTrue(outcome.err.startswith("upstream_sync: "))
                self.assertIsNone(outcome.markdown)

    def test_a_data_file_that_is_not_json_or_is_missing_is_exit_2(self):
        story = a_story(self.addCleanup)
        (story.data / "LEDGER.json").write_text("{not json", encoding="utf-8")
        self.assertIn("cannot read", story.run().err)
        (story.data / "LEDGER.json").unlink()
        self.assertEqual(story.run().code, sync.EXIT_ERROR)

    def test_a_file_is_its_bytes_and_a_name_the_commit_does_not_have_is_none(self):
        story = a_story(self.addCleanup)
        self.assertEqual(sync.blob(story.upstream.path, story.head_sha, "LICENSE"), b"terms v1\n")
        self.assertIsNone(sync.blob(story.upstream.path, story.head_sha, "no/such/file.py"))
        self.assertIsNone(sync.blob(story.upstream.path, story.head_sha, "actions"), "a folder is not a file")

    def test_a_missing_commit_is_never_read_as_no_such_file(self):
        # Review finding 4: blob() turned every git failure into None, "the file is not there", so a missing
        # commit made every file look new.
        story = a_story(self.addCleanup)
        with self.assertRaises(sync.CannotRun):
            sync.blob(story.upstream.path, NOT_A_COMMIT, "LICENSE")

    def test_a_folder_that_is_not_a_repository_is_never_read_as_no_such_file(self):
        story = a_story(self.addCleanup)
        with self.assertRaises(sync.CannotRun):
            sync.blob(story.data, story.head_sha, "LICENSE")

    def test_a_reconciled_commit_upstream_does_not_have_is_exit_2_not_a_silent_misreading(self):
        story = a_story(self.addCleanup)
        story.ledger([story.decide(["actions/*"], "take", reconciled=NOT_A_COMMIT)])
        outcome = story.run()
        self.assertEqual(outcome.code, sync.EXIT_ERROR, "it used to carry on and call every such file new")
        self.assertIn("LEDGER.json entry 1", outcome.err)
        self.assertIn(NOT_A_COMMIT[:12], outcome.err)


class TheScriptOnlyReads(unittest.TestCase):
    """The docstring says it never edits, pushes or merges. Here is what makes that true."""

    def test_nothing_in_ultrons_tree_or_the_data_folder_changes(self):
        story = a_story(self.addCleanup, {"core/new.py": "X = 1\n", "LICENSE": "terms v2\n"})

        def snapshot() -> dict:
            return {str(path.relative_to(story.folder)): hashlib.sha256(path.read_bytes()).hexdigest()
                    for folder in (story.root, story.data) for path in sorted(folder.rglob("*")) if path.is_file()}

        before = snapshot()
        self.assertEqual(story.run().code, sync.EXIT_STOP)
        self.assertEqual(story.run("--full").code, sync.EXIT_STOP)
        self.assertEqual(snapshot(), before)

    def test_it_uses_no_git_command_that_changes_anything_and_asks_github_only_to_read(self):
        tree = ast.parse((ROOT / "scripts" / "upstream_sync.py").read_text(encoding="utf-8"))

        def words_of(program: str) -> set:
            """Every word given to `program`: the lists that start with its name, and calls of the git() helper."""
            found = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.List) and node.elts and getattr(node.elts[0], "value", None) == program:
                    found |= {item.value for item in node.elts if isinstance(item, ast.Constant) and isinstance(item.value, str)}
                if program == "git" and isinstance(node, ast.Call) and getattr(node.func, "id", None) == "git":
                    found |= {item.value for item in node.args if isinstance(item, ast.Constant) and isinstance(item.value, str)}
            return found

        writing = {"push", "commit", "merge", "checkout", "reset", "rebase", "add", "rm", "mv", "pull", "apply",
                   "cherry-pick", "revert", "clean", "restore", "switch", "stash", "tag", "branch", "update-ref"}
        git_words = words_of("git")
        self.assertIn("clone", git_words, "this test is reading the wrong thing if it finds no git command")
        self.assertEqual(git_words & writing, set(), "a git command that writes: decide on purpose, and change this test with it")
        gh_words = words_of("gh")
        self.assertIn("api", gh_words)
        self.assertEqual(gh_words & {"--method", "-X", "-f", "-F", "--field", "--raw-field", "--input"}, set(),
                         "an option that makes `gh api` write")

    def test_the_exit_status_reaches_the_shell(self):
        story = a_story(self.addCleanup)
        self.assertEqual(story.run_in_a_child().returncode, sync.EXIT_MOVED)
        story.pin(base_sha=NOT_A_COMMIT)
        broken = story.run_in_a_child()
        self.assertEqual(broken.returncode, sync.EXIT_ERROR)
        self.assertIn("upstream_sync:", broken.stderr.decode("utf-8", "replace"))

    def test_pin_prints_the_block_to_paste_for_upstreams_head(self):
        story = a_story(self.addCleanup, {"readme.md": "# MARK LVII (57)\nIntro\n"})
        done = story.run_in_a_child(command="pin")
        self.assertEqual(done.returncode, 0, done.stderr)
        block = json.loads(done.stdout.decode("utf-8"))["reviewed"]
        self.assertEqual(block, {"sha": story.head_sha, "date": block["date"], "version": "MARK LVII (57)",
                                 "licence_sha256": sha256_of(b"terms v1\n"),
                                 "requirements_sha256": sha256_of(b"alpha>=1\nbeta>=2\n")})
        self.assertRegex(block["date"], r"^\d{4}-\d{2}-\d{2}$")


# ------------------------------------------------------------------ asking GitHub what the repository is called now

class AskingGitHub(unittest.TestCase):
    """Upstream is one repository renamed with each Mark, so it is asked for by number, never by name."""

    PIN = {"upstream": {"repo_id": 1170311800, "name": "FatihMakes/Mark-LVII", "url": "https://example.invalid/pinned.git"}}

    def answer(self, stdout: bytes = b"", code: int = 0, stderr: bytes = b"", raises: Exception | None = None):
        done = subprocess.CompletedProcess(["gh"], code, stdout, stderr)
        return mock.patch.object(sync.subprocess, "run", side_effect=raises, return_value=done)

    def test_it_asks_by_the_repository_number(self):
        with self.answer(b'{"name": "A/B", "url": "https://x.invalid/a.git"}') as fake:
            found, why = sync.asked_github(1170311800)
        self.assertEqual((found, why), ({"name": "A/B", "url": "https://x.invalid/a.git"}, ""))
        command = fake.call_args.args[0]
        self.assertEqual(command[:3], ["gh", "api", "repositories/1170311800"])

    def test_every_way_the_answer_can_fail_is_a_reason_and_not_a_guess(self):
        cases = {
            "gh says no": (self.answer(b"", 1, b"HTTP 404: Not Found"), "gh said: HTTP 404"),
            "gh is not installed": (self.answer(raises=FileNotFoundError("gh")), "gh could not be run"),
            "gh takes too long": (self.answer(raises=subprocess.TimeoutExpired("gh", 30)), "gh could not be run"),
            "gh prints junk": (self.answer(b"<html>"), "not JSON"),
            "gh names nothing": (self.answer(b"{}"), "did not name the repository"),
            "gh prints a list": (self.answer(b"[1]"), "did not name the repository"),
        }
        for label, (patched, fragment) in cases.items():
            with self.subTest(label), patched:
                found, why = sync.asked_github(1)
                self.assertIsNone(found)
                self.assertIn(fragment, why)

    def args(self, **given) -> object:
        return type("Args", (), {"upstream": None, "no_api": False, **given})()

    def test_a_rename_is_found_and_its_new_address_is_used(self):
        answer = {"name": "FatihMakes/Mark-LVIII", "url": "https://x.invalid/new.git"}
        with mock.patch.object(sync, "asked_github", return_value=(answer, "")):
            source, found, notes = sync.choose_source(self.args(), self.PIN)
        self.assertEqual((source, found, notes), ("https://x.invalid/new.git", answer, []))
        self.assertIn("renamed: FatihMakes/Mark-LVII is now FatihMakes/Mark-LVIII", sync.rename_notes(found, self.PIN)[0])
        self.assertEqual(sync.rename_notes({"name": "FatihMakes/Mark-LVII"}, self.PIN), [])
        self.assertEqual(sync.rename_notes({}, self.PIN), [])

    def test_when_github_cannot_be_asked_the_pinned_address_is_used_and_it_says_so(self):
        with mock.patch.object(sync, "asked_github", return_value=(None, "gh said: HTTP 502")):
            source, found, notes = sync.choose_source(self.args(), self.PIN)
        self.assertEqual((source, found), ("https://example.invalid/pinned.git", {}))
        self.assertIn("Could not ask GitHub what the repository is called now (gh said: HTTP 502)", notes[0])

    def test_no_api_never_asks(self):
        with mock.patch.object(sync, "asked_github", side_effect=AssertionError("asked")):
            source, _found, notes = sync.choose_source(self.args(no_api=True), self.PIN)
        self.assertEqual(source, "https://example.invalid/pinned.git")
        self.assertIn("--no-api", notes[0])

    def test_a_local_folder_is_used_as_an_absolute_path_and_anything_else_as_an_address(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            source, found, notes = sync.choose_source(self.args(upstream=folder), self.PIN)
            self.assertEqual((source, found, notes), (str(Path(folder).resolve()), {}, []))
        source, _found, _notes = sync.choose_source(self.args(upstream="https://example.invalid/x.git"), self.PIN)
        self.assertEqual(source, "https://example.invalid/x.git")

    def test_a_renamed_upstream_is_fetched_from_where_github_says_it_is_and_the_report_mentions_it(self):
        story = a_story(self.addCleanup)
        answer = {"name": "Someone/Mark-LVIII", "url": str(story.upstream.path)}
        out, err = io.StringIO(), io.StringIO()
        argv = ["check", "--root", str(story.root), "--data", str(story.data), "--json", str(story.folder / "r.json")]
        with mock.patch.object(sync, "asked_github", return_value=(answer, "")), redirect_stdout(out), redirect_stderr(err):
            code = sync.main(argv)
        self.assertEqual(code, sync.EXIT_MOVED, err.getvalue())
        self.assertIn("The upstream repository was renamed: Someone/Mark-LVII is now Someone/Mark-LVIII.", out.getvalue())


# ------------------------------------------------------------------ what the owner excluded

def files_in_scope(root: Path, scope: list) -> list:
    """Every Python file under the named folders and files; a name that is not there is skipped.

    Python only: the same folders can hold the owner's own data (`memory/long_term.json`, `plugins/` of
    his own), which a tripwire must not read as if it were the program.
    """
    found = []
    for name in scope:
        target = root / name
        if target.is_file():
            found.append(target)
        elif target.is_dir():
            found += [path for path in sorted(target.rglob("*"))
                      if path.is_file() and path.suffix == ".py" and "__pycache__" not in path.parts]
    return found


def tripwire_hits(root: Path, exclusions: dict) -> tuple[list, int]:
    """Where an excluded thing guarded by a tripwire appears in these files, and how many files were read."""
    wires = [item for item in exclusions["exclusions"] if item["guard"]["kind"] == "tripwire"]
    files = files_in_scope(root, exclusions["tripwire_scope"])
    hits = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for item in wires:
            for needle in item["needles"]:
                for match in re.finditer(needle, text):
                    hits.append(f"{item['id']} {path.relative_to(root).as_posix()}:{text.count(chr(10), 0, match.start()) + 1}")
    return hits, len(files)


def uses_of(source: str, name: str, guard: str) -> list:
    """Each place `name` is used in this source, as True when it sits in the body of an `if` that needs `guard()`."""
    found: list[bool] = []

    def needs(test: ast.expr) -> bool:
        parts = test.values if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And) else [test]
        return any(isinstance(part, ast.Call) and getattr(part.func, "id", None) == guard for part in parts)

    def visit(node: ast.AST, guarded: bool) -> None:
        if isinstance(node, ast.If):
            visit(node.test, guarded)
            for child in node.body:
                visit(child, guarded or needs(node.test))
            for child in node.orelse:
                visit(child, guarded)
            return
        if getattr(node, "attr", None) == name or getattr(node, "id", None) == name:
            found.append(guarded)
        for child in ast.iter_child_nodes(node):
            visit(child, guarded)

    visit(ast.parse(source), False)
    return found


class ExcludedFeatures(unittest.TestCase):
    """What the owner excluded from Mark stays out, and a change that touches it is named in the report."""

    @classmethod
    def setUpClass(cls):
        cls.exclusions = json.loads((ROOT / "docs" / "upstream" / "EXCLUSIONS.json").read_text(encoding="utf-8"))

    def test_the_briefing_is_only_started_behind_the_owners_choice(self):
        # E1. Mark starts a spoken news briefing when it opens; Ultron does it only when the owner saved
        # the morning brief on (the setting reads False when missing: tests/test_suite_assistant.py,
        # BriefingOptInTests). This reads the code that starts it, so a new call site cannot slip in.
        total = 0
        for path in files_in_scope(ROOT, self.exclusions["tripwire_scope"]):
            text = path.read_text(encoding="utf-8", errors="replace")
            if "_send_startup_briefing" not in text:
                continue
            uses = uses_of(text, "_send_startup_briefing", "get_brief_enabled")
            self.assertTrue(all(uses), f"{path.relative_to(ROOT).as_posix()} starts the briefing without get_brief_enabled()")
            total += len(uses)
        self.assertGreaterEqual(total, 1, "main.py starts the briefing; if no file does, this test reads the wrong thing")

    def test_the_reader_of_calls_knows_a_guarded_call_from_an_unguarded_one(self):
        guarded = "if not done and get_brief_enabled() and awake:\n    start(self._send_startup_briefing())\n"
        either = "if get_brief_enabled() or awake:\n    start(self._send_startup_briefing())\n"
        unguarded = "start(self._send_startup_briefing())\n"
        elsewhere = "if get_brief_enabled():\n    pass\nelse:\n    start(self._send_startup_briefing())\n"
        passed_along = "if awake:\n    loop.call_soon(self._send_startup_briefing)\n"
        for source, expected in ((guarded, [True]), (either, [False]), (unguarded, [False]), (elsewhere, [False]),
                                 (passed_along, [False])):
            self.assertEqual(uses_of(source, "_send_startup_briefing", "get_brief_enabled"), expected, source)

    def test_no_tripwire_exclusion_appears_in_ultrons_own_code(self):
        # E2 and E3: no news watch on a timer, no routine of type "startup". A needle in these folders
        # means something that was kept out has come back.
        hits, read = tripwire_hits(ROOT, self.exclusions)
        self.assertEqual(hits, [], "an excluded feature is in Ultron's code; see docs/upstream/EXCLUSIONS.json")
        self.assertGreater(read, 100, "the tripwire read almost nothing, so it proves almost nothing")

    def test_a_tripwire_really_fires(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            root = Path(folder)
            (root / "core").mkdir()
            (root / "core" / "x.py").write_text('a = 1\nroutines = [{"id": "news_watch"}]\n', encoding="utf-8")
            (root / "core" / "y.py").write_text('{"type": "startup"}\n', encoding="utf-8")
            (root / "core" / "data.json").write_text('{"id": "news_watch"}\n', encoding="utf-8")
            (root / "core" / "z.py").write_text('{"type": "interval"}\n', encoding="utf-8")
            exclusions = {"tripwire_scope": ["core", "missing_folder"],
                          "exclusions": [item for item in self.exclusions["exclusions"] if item["guard"]["kind"] == "tripwire"]}
            hits, read = tripwire_hits(root, exclusions)
        self.assertEqual(sorted(hits), ["E2 core/x.py:2", "E3 core/y.py:1"], "a data file is not read")
        self.assertEqual(read, 3)

    def test_each_needle_matches_a_line_of_the_kind_it_is_there_to_catch_and_not_an_innocent_one(self):
        samples = {
            "E1": ["await self._send_startup_briefing()", 'prompt = "Read me the top world news today"',
                   "enabled = cfg.get('morning_brief_enabled', True)", 'builtin = "briefing"', "builtin='briefing'"],
            "E2": ['{"id": "news_watch", "every": 1800}', "def news_watch(self):"],
            "E3": ['{"type": "startup", "prompt": "run tools"}', "{'type':'startup'}", '"type" : "startup"'],
        }
        innocent = ['"type": "interval"', "the app's startup sequence", "news", 'builtin = "weather"', "def watch_news(self):"]
        self.assertEqual(set(samples), {item["id"] for item in self.exclusions["exclusions"]})
        for item in self.exclusions["exclusions"]:
            for line in samples[item["id"]]:
                self.assertEqual(sync.excluded_ids(line, self.exclusions), [item["id"]], line)
        for line in innocent:
            self.assertEqual(sync.excluded_ids(line, self.exclusions), [], line)

    def test_a_change_that_touches_an_exclusion_is_named_in_the_report(self):
        story = a_story(self.addCleanup,
                        {"core/watch.py": 'ROUTINES = [{"id": "news_watch", "type": "startup"}]\n',
                         "core/brief.py": "await self._send_startup_briefing()\n", "core/fine.py": "print('hello')\n"})
        story.write("EXCLUSIONS.json", self.exclusions)
        outcome = story.run()
        self.assertEqual(outcome.row("core/watch.py")["excluded"], ["E2", "E3"])
        self.assertEqual(outcome.row("core/brief.py")["excluded"], ["E1"])
        self.assertEqual(outcome.row("core/fine.py")["excluded"], [])
        self.assertIn("- **E1 News on open** stays out (test guard): upstream's new or changed lines mention it in `core/brief.py`.",
                      outcome.markdown)
        self.assertIn("- **E2 News watch every 30 minutes** stays out (tripwire guard)", outcome.markdown)
        self.assertIn("## Touches what you excluded", outcome.markdown)

    def test_a_line_upstream_already_had_does_not_raise_the_alarm_again_every_week(self):
        old = "ROUTINES = [{'id': 'news_watch'}]\n" + numbered()
        story = Scenario(self.addCleanup, {**TERMS, "core/r.py": old}, {"core/r.py": old + "print('x')\n"}, {**TERMS, "core/r.py": old})
        story.write("EXCLUSIONS.json", self.exclusions)
        self.assertEqual(story.run().row("core/r.py")["excluded"], [])


# ------------------------------------------------------------------ the three data files, as they are

class TheDataFiles(unittest.TestCase):
    """The pin, the ledger and the exclusions are read by the script and by the owner; they must agree."""

    @classmethod
    def setUpClass(cls):
        cls.pin, cls.ledger, cls.exclusions = sync.load_data(sync.DATA)

    def doc(self, name: str) -> str:
        return (ROOT / name).read_text(encoding="utf-8")

    def test_the_three_files_load_and_pass_every_check_the_script_makes(self):
        self.assertEqual(self.pin["upstream"]["repo_id"], 1170311800)
        self.assertEqual({item["id"] for item in self.exclusions["exclusions"]}, {"E1", "E2", "E3"})
        self.assertGreaterEqual(len(self.ledger["entries"]), 6)

    def test_the_copy_commit_is_the_one_the_documents_record(self):
        for name in ("HANDOFF.md", "docs/UPSTREAM_RESEARCH.md"):
            self.assertIn(self.pin["base_sha"], self.doc(name), f"{name} records a different commit as the source of the copy")

    def test_the_fingerprints_have_the_shape_of_a_sha256(self):
        for key in ("licence_sha256", "requirements_sha256"):
            self.assertRegex(self.pin["reviewed"][key], r"^[0-9a-f]{64}$")

    def test_everything_that_steers_agents_or_the_rules_is_decided_ours_in_the_ledger(self):
        for pattern in sync.STEERING:
            entry = sync.ledger_decision(self.ledger, pattern)
            self.assertIsNotNone(entry, f"{pattern} steers agents here but has no ledger decision")
            self.assertEqual(entry["disposition"], "ours", f"{pattern}: upstream's version of it is never taken")

    def test_every_file_the_self_change_referee_protects_is_steering_here_too(self):
        tree = ast.parse((ROOT / "core" / "self_change.py").read_text(encoding="utf-8"))
        protected = next(ast.literal_eval(node.value) for node in tree.body
                         if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "PROTECTED")
        for name in protected:
            if name != "config/api_keys.json":          # the owner's own settings: not a file upstream has
                self.assertIn(name, sync.STEERING, f"{name} is protected from the in-app agent but not from upstream")

    def test_every_exclusion_tells_the_truth_about_how_it_is_guarded(self):
        for item in self.exclusions["exclusions"]:
            guard = item["guard"]
            if guard["kind"] == "tripwire":
                self.assertNotIn("tests", guard)
                continue
            self.assertTrue(guard["tests"], f"{item['id']} says a test guards it and names none")
            for cited in guard["tests"]:
                path, _, where = cited.partition("::")
                text = self.doc(path)
                for part in where.split("."):
                    self.assertRegex(text, rf"(?m)^\s*(?:class|def) {re.escape(part)}\b", f"{item['id']} cites {cited}, which is not there")

    def test_the_tripwire_scope_names_the_places_that_exist_today_and_the_folder_that_adoption_will_add(self):
        scope = self.exclusions["tripwire_scope"]
        for name in ("main.py", "ui.py", "core", "actions", "plugins", "providers", "custom_jarvis", "memory"):
            self.assertIn(name, scope)
            self.assertTrue((ROOT / name).exists(), f"{name} is in the tripwire scope but not in the tree")
        self.assertIn("gui", scope, "the window layer is adopted last; the day it arrives it is already watched")

    def test_the_guide_names_every_kind_decision_exit_status_and_exclusion(self):
        guide = self.doc("docs/UPSTREAM_SYNC.md")
        for word in (*sync.KINDS, *sync.DISPOSITIONS, "held", "E1", "E2", "E3", "PIN.json", "LEDGER.json",
                     "EXCLUSIONS.json", "reconciled", "`pin`", "--full"):
            self.assertIn(word, guide, f"docs/UPSTREAM_SYNC.md never mentions {word}")
        for code in (sync.EXIT_SAME, sync.EXIT_MOVED, sync.EXIT_STOP, sync.EXIT_ERROR):
            self.assertRegex(guide, rf"\b{code}\b")


# ------------------------------------------------------------------ text that comes from upstream

def read_code_spans(markdown: str) -> tuple[list, str]:
    """The code spans of some Markdown and everything outside them, by CommonMark's rule.

    A run of N backticks closes at the next run of exactly N backticks; a run that never closes is plain text.
    """
    runs = [(match.start(), match.end()) for match in re.finditer(r"`+", markdown)]
    spans, outside, cursor, index = [], [], 0, 0
    while index < len(runs):
        start, end = runs[index]
        closing = next((later for later in range(index + 1, len(runs)) if runs[later][1] - runs[later][0] == end - start), None)
        if closing is None:
            index += 1
            continue
        outside.append(markdown[cursor:start])
        body = markdown[end:runs[closing][0]].replace("\n", " ")
        if len(body) > 1 and body[0] == " " == body[-1] and body.strip(" "):
            body = body[1:-1]
        spans.append(body)
        cursor, index = runs[closing][1], closing + 1
    outside.append(markdown[cursor:])
    return spans, "".join(outside)


class StrangersText(unittest.TestCase):
    """Review finding 5. A file name, a readme line and a requirement come from upstream into an issue."""

    HOSTILE = "we`ird@octocat/x.py"

    def test_the_reader_of_code_spans_follows_the_rule_it_claims_to(self):
        self.assertEqual(read_code_spans("a `b` c ``d`e`` f ` `` ` g"), (["b", "d`e", "``"], "a  c  f  g"))
        self.assertEqual(read_code_spans("`never closed and ``also`` open"), (["also"], "`never closed and  open"))

    def test_a_readme_line_cannot_become_a_long_or_many_lined_title(self):
        for label, first in (("very long", "# " + "words of a very long title " * 40), ("many roman numerals", "# MARK " + "I" * 500 + " (57)"),
                             ("control characters", "# Some\x00\x1b[31m\u2028name")):
            with self.subTest(label), tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
                upstream = FakeUpstream(Path(folder))
                sha = upstream.commit({"readme.md": first + "\nIntro\n"})
                title = sync.version_of(upstream.path, sha)
                self.assertLessEqual(len(title), 60)
                self.assertTrue(title.isprintable(), repr(title))
                self.assertTrue(title)

    def test_an_ordinary_title_is_read_as_before(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            upstream = FakeUpstream(Path(folder))
            self.assertEqual(sync.version_of(upstream.path, upstream.commit({"readme.md": "# MARK LVII (57)\nIntro\n"})), "MARK LVII (57)")
            self.assertEqual(sync.version_of(upstream.path, upstream.commit({"readme.md": "# Some Other Name\n"})), "Some Other Name")
            self.assertEqual(sync.version_of(upstream.path, upstream.commit({"readme.md": None})), "unknown")

    def test_a_name_in_code_style_cannot_end_the_code_style_early(self):
        for text in (self.HOSTILE, "plain.py", "`", "``", "a``b", "x`", "`y", "a ` b `` c", " spaced "):
            with self.subTest(text):
                spans, outside = read_code_spans(sync.code(text))
                self.assertEqual((spans, outside), ([text], ""))

    def test_a_name_with_a_line_break_in_it_stays_on_one_line(self):
        for text in (sync.code("a\nb.py"), sync.names(["a\n# Heading\n@octocat", "c\r\nd"]), sync.code("tab\there\x1b[0m")):
            self.assertNotRegex(text, r"[\n\r\t\x1b]")
        self.assertEqual(sync.joined(["a", "b", "c"], limit=2), "a, b and 1 more")

    def test_nothing_from_upstream_reaches_the_report_outside_code_style(self):
        hostile = self.HOSTILE
        rows = [sync.FileChange(hostile, "COLLIDES"), sync.FileChange(f"{hostile}2", "NEW", lines_after=9, tool="t"),
                sync.FileChange("we`ird@octocat/y.py", "NEW", unwired=True, risks=["runs other programs"])]
        report = {"new_sha": "b" * 40, "date": "2026-11-20", "version": "@octocat [x](https://example.invalid)",
                  "reviewed_version": "MARK `LVII` @hubot", "reviewed_sha": "a" * 40, "base_sha": "c" * 40,
                  "gates": sync.steering_gates([sync.FileChange(".github/we`ird@octocat.yml", "TAKE")]),
                  "notes": [], "full": False, "moved": True, "files": [dataclasses.asdict(row) for row in rows],
                  "counts": sync.summarise(rows), "commits": 3, "scope": "a" * 40}
        spans, outside = read_code_spans(sync.render(report, EXCLUSIONS))
        for stranger in ("octocat", "hubot", "example.invalid", "we`"):
            self.assertNotIn(stranger, outside)
        self.assertIn(hostile, spans)
        self.assertIn("@octocat [x](https://example.invalid)", spans, "the version is upstream's text too")
        self.assertIn("MARK `LVII` @hubot", spans)
        self.assertIn(".github/we`ird@octocat.yml", spans)

    def test_a_readme_title_that_pings_someone_stays_inside_code_style_in_the_report(self):
        outcome = a_story(self.addCleanup, {"readme.md": "# @octocat read [this](https://example.invalid)\nIntro\n"}).run()
        spans, outside = read_code_spans(outcome.markdown)
        self.assertNotIn("octocat", outside)
        self.assertNotIn("example.invalid", outside)
        self.assertIn("@octocat read [this](https://example.invalid)", spans)

    def test_a_requirement_line_from_upstream_stays_text_in_the_stop_and_ask(self):
        evil = "evil`@octocat>=1 [click](https://example.invalid)"
        outcome = a_story(self.addCleanup, {"requirements.txt": f"alpha>=1\nbeta>=2\n{evil}\n"}).run()
        spans, outside = read_code_spans(outcome.markdown)
        self.assertNotIn("octocat", outside)
        self.assertNotIn("example.invalid", outside)
        self.assertIn(evil, spans)

    def test_a_file_with_an_odd_name_is_reported_safely_end_to_end(self):
        outcome = a_story(self.addCleanup, {f"{self.HOSTILE}": "X = 1\n", "we`ird@octocat/dir/z.py": "X = 2\n"}).run()
        self.assertEqual(outcome.code, sync.EXIT_MOVED, outcome.err)
        spans, outside = read_code_spans(outcome.markdown)
        self.assertNotIn("octocat", outside)
        self.assertIn("we`ird@octocat", spans, "the folder is named in code style too")

    def test_a_report_longer_than_an_issue_can_hold_is_cut_and_says_so(self):
        rows = [sync.FileChange("core/x.py", "NEW", lines_after=1)]
        report = {"new_sha": "b" * 40, "date": "2026-11-20", "version": "v", "reviewed_version": "w", "reviewed_sha": "a" * 40,
                  "base_sha": "c" * 40, "gates": [], "notes": ["n" * (sync.ISSUE_LIMIT + 5000)], "full": False, "moved": True,
                  "files": [dataclasses.asdict(row) for row in rows], "counts": sync.summarise(rows), "commits": 1, "scope": "a" * 40}
        text = sync.render(report, EXCLUSIONS)
        self.assertIn("(cut: longer than an issue can hold; run the script for all of it)", text)
        self.assertLess(len(text), sync.ISSUE_LIMIT + 200)


class TheReportAsAWhole(unittest.TestCase):
    """The writing of the report, from a hand-made result, without git."""

    def report(self, *changes: sync.FileChange, **more) -> dict:
        base = {"new_sha": "b" * 40, "date": "2026-11-20", "version": "MARK LVIII (58)", "reviewed_version": "MARK LVII (57)",
                "reviewed_sha": "a" * 40, "base_sha": "c" * 40, "gates": [], "notes": [], "full": False, "moved": True,
                "files": [dataclasses.asdict(row) for row in changes], "counts": sync.summarise(list(changes)),
                "commits": 4, "scope": "a" * 40}
        return {**base, **more}

    def test_a_report_that_found_nothing_to_do_has_no_empty_headings(self):
        text = sync.render(self.report(sync.FileChange("x.py", "LINE_ENDINGS")), EXCLUSIONS)
        self.assertNotIn("## Needs a decision", text)
        self.assertNotIn("## Stop and ask", text)
        self.assertIn("## What changed", text)
        self.assertEqual(text.splitlines()[0], "# Upstream watch: `MARK LVII (57)` -> `MARK LVIII (58)`")

    def test_when_nothing_moved_it_says_no_in_one_line(self):
        text = sync.render({"moved": False, "reviewed_version": "MARK LVII (57)", "reviewed_sha": "a" * 40}, EXCLUSIONS)
        self.assertEqual(text, "**No.** Upstream has not moved past the drop last reviewed (`MARK LVII (57)`, `aaaaaaa`).\n")

    def test_the_stop_and_ask_comes_before_everything_else(self):
        text = sync.render(self.report(sync.FileChange("x.py", "COLLIDES"), gates=["Read the licence."]), EXCLUSIONS)
        self.assertLess(text.index("## Stop and ask"), text.index("## What changed"))
        self.assertIn("- Read the licence.", text)

    def test_a_long_list_is_cut_with_a_count_of_the_rest(self):
        rows = [sync.FileChange(f"core/f{number:02}.py", "COLLIDES") for number in range(15)]
        text = sync.render(self.report(*rows), EXCLUSIONS)
        self.assertIn("`core/f11.py` and 3 more", text)
        self.assertNotIn("core/f12.py", text)

    def test_new_code_is_summed_by_folder_biggest_first(self):
        rows = [sync.FileChange("gui/a.py", "NEW", lines_after=900), sync.FileChange("core/b.py", "NEW", lines_after=50),
                sync.FileChange("gui/c.py", "NEW", lines_after=100)]
        self.assertIn("- New code by folder: `gui` 1,000 lines, `core` 50 lines", sync.render(self.report(*rows), EXCLUSIONS))

    def test_a_file_with_no_folder_is_called_top_level(self):
        self.assertIn("`(top level)` 1", sync.render(self.report(sync.FileChange("main.py", "COLLIDES")), EXCLUSIONS))


# ------------------------------------------------------------------ the weekly workflow

WORKFLOW = ROOT / ".github" / "workflows" / "upstream-watch.yml"

CLOSE = "Close the issue once the pin has caught up"
GH = """#!/bin/sh
# Stands in for `gh`: records each call on one line (arguments split by a unit separator, so spaces
# survive) and answers `issue list` with the number of the open issue the test chose, if any.
printf 'gh' >> "$FAKE_LOG"
for argument in "$@"; do printf '\\037%s' "$argument" >> "$FAKE_LOG"; done
printf '\\n' >> "$FAKE_LOG"
if [ "$1 $2" = "issue list" ]; then printf '%s' "$FAKE_OPEN_ISSUE"; fi
"""
PYTHON = """#!/bin/sh
# Stands in for `python scripts/upstream_sync.py check ...`: writes the report when asked, exits as told.
if [ -n "$FAKE_REPORT" ]; then printf '%s' "$FAKE_REPORT" > "$RUNNER_TEMP/report.md"; fi
exit "${FAKE_CODE:-0}"
"""


def a_bash_we_can_drive() -> str | None:
    """The `bash` these tests run, or None where there is not one they can drive (a Windows PATH's `bash` is
    usually the launcher for the Linux subsystem; tests/test_workflow_hygiene.py learned that the hard way).
    The steps only ever run on the Linux runner, and the Linux job runs these tests."""
    return None if os.name == "nt" else shutil.which("bash")


def step_named(name: str) -> list:
    """The lines of the workflow step with this name, up to the next step."""
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    start = next((index for index, line in enumerate(lines) if line.strip() == f"- name: {name}"), None)
    if start is None:
        raise LookupError(f"{WORKFLOW.name} has no step named {name!r}")
    end = next((index for index in range(start + 1, len(lines)) if lines[index].startswith("      - ")), len(lines))
    return lines[start:end]


def script_of(name: str) -> str:
    """The shell text of a step's `run: |` block, dedented."""
    lines = step_named(name)
    run = next(index for index, line in enumerate(lines) if line.strip() == "run: |")
    margin = len(lines[run]) - len(lines[run].lstrip())
    body = []
    for line in lines[run + 1:]:
        if line.strip() and len(line) - len(line.lstrip()) <= margin:
            break
        body.append(line)
    inner = min(len(line) - len(line.lstrip()) for line in body if line.strip())
    return "\n".join(line[inner:] for line in body) + "\n"


def condition_of(name: str) -> str:
    return next(line.split("if:", 1)[1].strip() for line in step_named(name) if line.strip().startswith("if:"))


class TheWeeklyWorkflow(unittest.TestCase):
    """It reads upstream and writes one issue. It cannot change the repository, and nothing a stranger wrote runs."""

    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def under(self, key: str) -> list:
        """The lines indented under a top-level key."""
        lines = self.text.splitlines()
        found = []
        for line in lines[lines.index(f"{key}:") + 1:]:
            if line.strip() and not line.startswith(" "):
                break
            if line.strip() and not line.strip().startswith("#"):
                found.append(line)
        return found

    def test_it_may_read_the_repository_and_write_issues_and_nothing_else(self):
        self.assertEqual([line.strip() for line in self.under("permissions")], ["contents: read", "issues: write"])
        self.assertEqual(len(re.findall(r"(?m)^\s*permissions:", self.text)), 1, "a block inside the job could widen it")

    def test_it_starts_on_a_schedule_or_by_hand_and_by_nothing_a_stranger_can_do(self):
        triggers = {line.strip().rstrip(":") for line in self.under("on") if not line.startswith("    ")}
        self.assertEqual(triggers, {"schedule", "workflow_dispatch"})

    def test_the_schedule_is_weekly(self):
        crons = re.findall(r'cron:\s*"([^"]+)"', self.text)
        self.assertEqual(len(crons), 1)
        minute, hour, day, month, weekday = crons[0].split()
        self.assertTrue(minute.isdigit() and hour.isdigit() and weekday.isdigit(), crons[0])
        self.assertEqual((day, month), ("*", "*"))

    def test_every_action_is_pinned_to_a_commit_and_checkout_keeps_no_credentials(self):
        uses = re.findall(r"(?m)^\s*- uses:\s*(\S+)(.*)$", self.text)
        self.assertGreaterEqual(len(uses), 2)
        for target, rest in uses:
            self.assertRegex(target, r"^[\w.-]+/[\w.-]+@[0-9a-f]{40}$", "a tag can be moved; a commit cannot")
            self.assertRegex(rest, r"#\s*v\d", "say which release the commit is")
        self.assertRegex(self.text, r"persist-credentials:\s*false")

    def test_the_only_things_pasted_into_a_script_are_the_token_and_our_own_exit_status(self):
        self.assertEqual(set(re.findall(r"\$\{\{\s*(.*?)\s*\}\}", self.text)), {"github.token", "steps.check.outputs.code"})

    def test_it_has_no_way_to_change_the_repository(self):
        for forbidden in ("git push", "git commit", "git add", "contents: write", "pull-requests: write",
                          "gh pr ", "gh release", "gh api", "secrets."):
            self.assertNotIn(forbidden, self.text)

    def test_each_step_acts_on_the_exit_status_the_script_documents(self):
        moved = {str(sync.EXIT_MOVED), str(sync.EXIT_STOP)}
        tolerated = set(re.findall(r"!= '(\d+)'", condition_of("Fail if the check could not be made")))
        self.assertEqual(tolerated, {str(sync.EXIT_SAME)} | moved, "any other status means the check could not be made")
        self.assertEqual(set(re.findall(r"== '(\d+)'", condition_of("Keep one issue open"))), moved)
        self.assertEqual(set(re.findall(r"== '(\d+)'", condition_of(CLOSE))), {str(sync.EXIT_SAME)})


@unittest.skipUnless(a_bash_we_can_drive() and shutil.which("jq"), "needs a POSIX bash and jq (Windows skips; the Linux job runs it)")
class TheStepsOfTheWorkflow(unittest.TestCase):
    """The shell of each step, run as GitHub runs it, with a stand-in `gh` that records what it was asked to do."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(folder.cleanup)
        self.work = Path(folder.name)
        self.runner, self.bin = self.work / "runner", self.work / "bin"
        self.runner.mkdir()
        self.bin.mkdir()
        self.log = self.work / "calls.log"
        self.log.write_text("", encoding="utf-8")
        for name, text in (("gh", GH), ("python", PYTHON)):
            (self.bin / name).write_text(text, encoding="utf-8", newline="\n")
            (self.bin / name).chmod(0o755)

    def run_step(self, name: str, code: str = "0", **environment) -> subprocess.CompletedProcess:
        script = script_of(name).replace("${{ steps.check.outputs.code }}", code)
        env = {**os.environ, "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}", "RUNNER_TEMP": str(self.runner),
               "GITHUB_OUTPUT": str(self.work / "output"), "GITHUB_STEP_SUMMARY": str(self.work / "summary"),
               "FAKE_LOG": str(self.log), **environment}
        # The flags GitHub runs `shell: bash` with.
        return subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script],  # noqa: S603, S607
                              cwd=self.work, env=env, capture_output=True, text=True, timeout=60, check=False)

    def calls(self) -> list:
        return [line.split("\x1f")[1:] for line in self.log.read_text(encoding="utf-8").splitlines() if line]

    def with_report(self, moved: bool) -> Outcome:
        """A real report from the script, put where the steps look for it."""
        story = a_story(self.addCleanup)
        if not moved:
            story.pin(story.head_sha)
        outcome = story.run()
        (self.runner / "report.md").write_text(outcome.markdown, encoding="utf-8")
        (self.runner / "report.json").write_text(json.dumps(outcome.report), encoding="utf-8")
        return outcome

    def title(self, outcome: Outcome) -> str:
        return f"Upstream moved: {outcome.report['version']} @ {outcome.report['new_sha'][:7]}"

    def test_a_move_with_no_issue_open_opens_one_with_the_report_as_its_body(self):
        outcome = self.with_report(moved=True)
        done = self.run_step("Keep one issue open", FAKE_OPEN_ISSUE="")
        self.assertEqual(done.returncode, 0, done.stderr)
        label, listing, create = self.calls()
        self.assertEqual(label[:3], ["label", "create", "upstream-watch"])
        self.assertIn("--force", label, "the label is made again without failing when it exists")
        self.assertEqual(listing[:2], ["issue", "list"])
        self.assertEqual(create, ["issue", "create", "--title", self.title(outcome), "--label", "upstream-watch",
                                  "--body-file", str(self.runner / "report.md")])

    def test_a_move_with_an_issue_already_open_updates_that_one_and_opens_no_second(self):
        outcome = self.with_report(moved=True)
        self.assertEqual(self.run_step("Keep one issue open", FAKE_OPEN_ISSUE="12").returncode, 0)
        edit = self.calls()[-1]
        self.assertEqual(edit, ["issue", "edit", "12", "--title", self.title(outcome), "--body-file", str(self.runner / "report.md")])
        self.assertNotIn(["issue", "create"], [call[:2] for call in self.calls()])

    def test_when_the_pin_has_caught_up_the_open_issue_is_closed_with_the_reason(self):
        # Review finding 2: nothing closed the issue, so after the owner adopted or set aside a drop it
        # went on saying "Yes, upstream moved" until someone noticed.
        outcome = self.with_report(moved=False)
        self.assertEqual(self.run_step(CLOSE, FAKE_OPEN_ISSUE="12").returncode, 0)
        closing = self.calls()[-1]
        self.assertEqual(closing[:3], ["issue", "close", "12"])
        self.assertEqual(closing[3], "--comment")
        self.assertIn(outcome.report["new_sha"][:7], closing[4])
        self.assertIn("Nothing is waiting", closing[4])

    def test_when_the_pin_has_caught_up_and_no_issue_is_open_nothing_is_opened_or_closed(self):
        self.with_report(moved=False)
        self.assertEqual(self.run_step(CLOSE, FAKE_OPEN_ISSUE="").returncode, 0)
        self.assertEqual([call[:2] for call in self.calls()], [["issue", "list"]])

    def test_the_check_step_never_fails_by_itself_and_hands_on_the_exit_status(self):
        for code in ("0", "10", "20", "2", "1", "127"):
            with self.subTest(code):
                (self.work / "output").write_text("", encoding="utf-8")
                done = self.run_step("Compare with upstream", FAKE_CODE=code, FAKE_REPORT="the report text")
                self.assertEqual(done.returncode, 0, "a later step decides what is a failure")
                self.assertEqual((self.work / "output").read_text(encoding="utf-8").strip(), f"code={code}")
                self.assertIn("the report text", (self.work / "summary").read_text(encoding="utf-8"))

    def test_the_check_step_copes_with_a_script_that_wrote_no_report(self):
        done = self.run_step("Compare with upstream", FAKE_CODE="2")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertFalse((self.work / "summary").exists() and (self.work / "summary").read_text(encoding="utf-8"))

    def test_the_step_that_fails_the_job_fails_and_names_the_status(self):
        done = self.run_step("Fail if the check could not be made", code="2")
        self.assertEqual(done.returncode, 1)
        self.assertIn("exit 2", done.stdout)


if __name__ == "__main__":
    unittest.main()
