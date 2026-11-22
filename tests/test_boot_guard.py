"""A change Ultron made to its own code has to survive a start, or it is put back.

`core/self_change.py` rehearses a change in a copy and asks twice, and then writes it. A `.py`
change only runs at the next start, so the first real run of the written code was a start with
nobody watching, and a fault the tests could not see left the program unable to open. These tests
pin the safety net (`core/boot_guard.py`): what it records, what it puts back, and what it refuses
to touch, with a small fake project in a temporary folder, never the real tree.

The flow, in the words the tests use:
    apply          -> the change is on disk and under watch, not yet started
    first launch   -> it is marked started, and left alone
    second launch  -> if nothing proved the first start healthy, the old file is put back
    healthy        -> a start that lasted (or ended normally) takes the change off the list
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import bootstrap  # noqa: E402
from core import boot_guard, self_change  # noqa: E402

OLD = "def greeting():\n    return 'hello'\n"
NEW = "def greeting():\n    return 'hello, sir'\n"
FIRST = "c0123456789ab"
SECOND = "c0123456789ac"


def sha(text: str) -> str:
    """Written out here, not taken from the code under test."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class WithAGuardedProject(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.project = Path(self._temp.name) / "project"
        self.store = self.project / "config" / "self_change"
        (self.project / "actions").mkdir(parents=True)
        self.store.mkdir(parents=True)
        self.said: list[str] = []
        boot_guard._FAILED.clear()
        self.addCleanup(boot_guard._FAILED.clear)

    def tearDown(self):
        self._temp.cleanup()

    def applied(self, change=FIRST, relative="actions/greet.py", old=OLD, new=NEW) -> Path:
        """What `core.self_change.apply` leaves behind for a code change."""
        target = self.project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(new, encoding="utf-8")
        (self.store / "backups").mkdir(exist_ok=True)
        (self.store / "backups" / f"{change}.bak").write_text(old, encoding="utf-8")
        boot_guard.watch(self.store, change, relative, sha(old), sha(new))
        return target

    def launch(self) -> dict:
        return boot_guard.check_at_launch(self.project, say=self.said.append)

    def read(self, target: Path) -> str:
        return target.read_text(encoding="utf-8")


class TheFlow(WithAGuardedProject):
    def test_a_change_that_was_never_started_is_marked_started_and_left_alone(self):
        target = self.applied()
        outcome = self.launch()
        self.assertEqual(outcome["started"], [FIRST])
        self.assertEqual(self.read(target), NEW)
        self.assertEqual([row["started"] for row in boot_guard.pending(self.store)], [1])
        self.assertIn(FIRST, " ".join(self.said))
        self.assertIn("puts the old file back", " ".join(self.said), "it says what the next start does")

    def test_a_start_that_never_proved_itself_is_followed_by_a_start_that_puts_the_file_back(self):
        target = self.applied()
        self.launch()                                  # the first start of the new code; it dies
        outcome = self.launch()                        # the next start
        self.assertEqual(self.read(target), OLD)
        self.assertEqual([item["change"] for item in outcome["put_back"]], [FIRST])
        self.assertEqual(boot_guard.pending(self.store), [], "nothing is left to put back twice")
        said = " ".join(self.said)
        self.assertIn("actions/greet.py", said)
        self.assertIn("taken back", said)

    def test_a_start_that_stayed_up_keeps_the_change(self):
        target = self.applied()
        self.launch()
        self.assertEqual(boot_guard.mark_healthy(self.project), 1)
        outcome = self.launch()
        self.assertEqual(self.read(target), NEW)
        self.assertEqual(outcome["put_back"], [])
        self.assertEqual(boot_guard.pending(self.store), [])

    def test_a_change_applied_during_a_run_is_not_proved_by_that_runs_health(self):
        self.applied(FIRST, "actions/a.py")
        self.launch()
        self.applied(SECOND, "actions/b.py")           # applied while the program was running
        self.assertEqual(boot_guard.mark_healthy(self.project), 1, "only the first had been started")
        rows = boot_guard.pending(self.store)
        self.assertEqual([row["change"] for row in rows], [SECOND])
        self.assertEqual(rows[0]["started"], 0)

    def test_two_changes_to_one_file_unwind_newest_first(self):
        target = self.applied(FIRST, "actions/v.py", old="v = 1\n", new="v = 2\n")
        self.applied(SECOND, "actions/v.py", old="v = 2\n", new="v = 3\n")
        self.launch()
        outcome = self.launch()
        self.assertEqual(self.read(target), "v = 1\n")
        self.assertEqual([item["change"] for item in outcome["put_back"]], [SECOND, FIRST])

    def test_a_change_made_after_the_failing_one_is_put_back_too_and_the_start_says_it_never_ran(self):
        target = self.applied(FIRST, "actions/v.py", old="v = 1\n", new="v = 2\n")
        self.launch()                                  # the first change is started, and dies
        self.applied(SECOND, "actions/v.py", old="v = 2\n", new="v = 3\n")    # made during that run
        outcome = self.launch()
        self.assertEqual(self.read(target), "v = 1\n", "the second builds on the first: both go")
        self.assertEqual([item["change"] for item in outcome["put_back"]], [SECOND, FIRST])
        said = " ".join(self.said)
        self.assertIn("never started", said)
        self.assertEqual(said.count("never started"), 1, "only the second one is said to have never run")

    def test_a_ledger_that_is_a_hard_link_is_not_replaced_by_a_one_line_file(self):
        target = self.applied()
        other = self.project / "somebody_elses_notes.jsonl"
        other.write_text('{"keep": "me"}\n', encoding="utf-8")
        try:
            os.link(other, self.store / "ledger.jsonl")
        except (OSError, NotImplementedError, AttributeError):
            self.skipTest("this machine will not make a hard link")
        self.launch()
        outcome = self.launch()
        self.assertEqual(self.read(target), OLD, "the file is still put back")
        self.assertEqual(other.read_text(encoding="utf-8"), '{"keep": "me"}\n')
        self.assertEqual((self.store / "ledger.jsonl").read_text(encoding="utf-8"), '{"keep": "me"}\n')
        self.assertIn("ledger", " ".join(outcome["notes"]))

    def test_a_file_that_changed_since_is_left_alone_and_the_start_says_so(self):
        target = self.applied()
        self.launch()
        target.write_text("def greeting():\n    return 'someone edited this'\n", encoding="utf-8")
        outcome = self.launch()
        self.assertIn("someone edited this", self.read(target))
        self.assertEqual([item["change"] for item in outcome["left"]], [FIRST])
        said = " ".join(self.said)
        self.assertIn("NOT put back", said)
        self.assertIn("backups", said, "it says where the kept copy is")

    def test_the_ledger_and_the_proposals_say_who_put_it_back(self):
        self.applied()
        (self.store / "proposals.json").write_text(
            json.dumps({FIRST: {"id": FIRST, "stage": "applied", "path": "actions/greet.py"}}),
            encoding="utf-8")
        self.launch()
        self.launch()
        entries = [json.loads(line) for line in
                   (self.store / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(entries[-1]["event"], "reverted")
        self.assertEqual(entries[-1]["by"], "boot guard")
        self.assertEqual(entries[-1]["id"], FIRST)
        proposals = json.loads((self.store / "proposals.json").read_text(encoding="utf-8"))
        self.assertEqual(proposals[FIRST]["stage"], "reverted")
        self.assertEqual(proposals[FIRST]["reverted_by"], "boot guard")

    def test_the_restart_note_is_cleared_when_the_change_it_names_is_put_back(self):
        marker = self.project / "restart-required.json"
        self.applied()
        marker.write_text(json.dumps({"change": FIRST}), encoding="utf-8")
        self.launch()
        self.launch()
        self.assertFalse(marker.exists(), "the note said a restart was needed for a change that is gone")

    def test_a_restart_note_for_another_change_is_left_alone(self):
        marker = self.project / "restart-required.json"
        self.applied()
        marker.write_text(json.dumps({"change": SECOND}), encoding="utf-8")
        self.launch()
        self.launch()
        self.assertTrue(marker.exists())

    def test_a_launch_with_nothing_under_watch_says_nothing(self):
        outcome = self.launch()
        self.assertEqual((outcome["started"], outcome["put_back"], outcome["left"]), ([], [], []))
        self.assertEqual(self.said, [])

    def test_the_default_store_is_the_one_apply_uses(self):
        target = self.applied()
        boot_guard.check_at_launch(self.project)       # no store given
        boot_guard.check_at_launch(self.project)
        self.assertEqual(self.read(target), OLD)


class TheGuardCannotBeAimedAtAnotherFile(WithAGuardedProject):
    """The watch file is a file. A tampered one must not become a way to overwrite anything."""

    def plant(self, row_path: str, change=FIRST, content="original\n") -> Path:
        """A watch row an attacker made consistent: the digests match what is on disk."""
        target = (self.project / row_path) if not Path(row_path).is_absolute() else Path(row_path)
        with contextlib.suppress(OSError, ValueError):
            target.parent.mkdir(parents=True, exist_ok=True)
        if target.parent.exists() and not target.exists():
            target.write_text(content, encoding="utf-8")
        (self.store / "backups").mkdir(exist_ok=True)
        if _id_ok(change):
            (self.store / "backups" / f"{change}.bak").write_text("evil\n", encoding="utf-8")
        row = {"change": change, "path": row_path, "old_sha256": sha("evil\n"),
               "applied_sha256": sha(content), "started": 1}
        (self.store / "boot-watch.json").write_text(json.dumps({"changes": [row]}), encoding="utf-8")
        return target

    def test_a_path_outside_the_project_is_not_written(self):
        outside = Path(self._temp.name) / "outside.txt"
        outside.write_text("keep me\n", encoding="utf-8")
        for path in ("../outside.txt", str(outside)):
            with self.subTest(path=path):
                self.plant(path, content="keep me\n")
                outcome = self.launch()
                self.assertEqual(self.read(outside), "keep me\n")
                self.assertEqual(len(outcome["left"]), 1)

    def test_the_referee_files_are_not_written(self):
        for path in boot_guard.PROTECTED:
            with self.subTest(path=path):
                target = self.plant(path)
                outcome = self.launch()
                self.assertEqual(self.read(target), "original\n")
                self.assertEqual(len(outcome["left"]), 1)

    def test_a_folder_a_change_may_never_write_through_is_not_written(self):
        for path in (".github/workflows/verify.yml", ".git/hooks/pre-commit", "node_modules/x/index.js"):
            with self.subTest(path=path):
                target = self.plant(path)
                outcome = self.launch()
                self.assertEqual(self.read(target), "original\n")
                self.assertEqual(len(outcome["left"]), 1)

    def test_a_path_through_a_link_is_not_written(self):
        real = self.project / "real"
        real.mkdir()
        (real / "f.py").write_text("original\n", encoding="utf-8")
        try:
            (self.project / "linked").symlink_to(real, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("this machine will not make a symlink")
        self.plant("linked/f.py")
        outcome = self.launch()
        self.assertEqual(self.read(real / "f.py"), "original\n")
        self.assertEqual(len(outcome["left"]), 1)

    def test_an_id_that_is_not_the_shape_propose_makes_is_not_used_as_a_path(self):
        self.applied(FIRST, "actions/a.py")
        for change in ("../../outside", "c1", "C0123456789AB", "c0123456789abc", ""):
            with self.subTest(change=change):
                self.plant("actions/a.py", change=change)
                outcome = self.launch()
                self.assertEqual(len(outcome["left"]), 1)
                self.assertIn("id", outcome["left"][0]["why"])

    def test_a_kept_copy_that_is_not_what_was_recorded_is_not_used(self):
        target = self.applied()
        self.launch()
        (self.store / "backups" / f"{FIRST}.bak").write_text("import os\nos.system('x')\n", encoding="utf-8")
        outcome = self.launch()
        self.assertEqual(self.read(target), NEW)
        self.assertIn("kept copy", outcome["left"][0]["why"])

    def test_a_missing_kept_copy_is_said_not_guessed(self):
        target = self.applied()
        self.launch()
        (self.store / "backups" / f"{FIRST}.bak").unlink()
        outcome = self.launch()
        self.assertEqual(self.read(target), NEW)
        self.assertEqual(len(outcome["left"]), 1)


def _id_ok(change: str) -> bool:
    return bool(change) and "/" not in change and ".." not in change


class TheGuardNeverStopsALaunch(WithAGuardedProject):
    def test_garbage_in_the_watch_file_is_not_an_error(self):
        (self.store / "boot-watch.json").write_text("{not json", encoding="utf-8")
        outcome = self.launch()
        self.assertEqual(outcome["put_back"], [])

    def test_rows_that_are_not_objects_are_ignored(self):
        (self.store / "boot-watch.json").write_text(json.dumps({"changes": [1, "x", None, []]}),
                                                    encoding="utf-8")
        self.assertEqual(self.launch()["put_back"], [])

    def test_a_count_that_is_not_a_number_counts_as_not_started(self):
        target = self.applied()
        rows = boot_guard.pending(self.store)
        rows[0]["started"] = "twice"
        (self.store / "boot-watch.json").write_text(json.dumps({"changes": rows}), encoding="utf-8")
        outcome = self.launch()
        self.assertEqual(outcome["started"], [FIRST])
        self.assertEqual(self.read(target), NEW)

    def test_a_store_that_is_a_file_is_not_an_error(self):
        shutil.rmtree(self.store)
        self.store.write_text("not a folder", encoding="utf-8")
        outcome = self.launch()
        self.assertEqual(outcome["put_back"], [])

    def test_a_file_that_cannot_be_written_is_said_and_the_launch_goes_on(self):
        target = self.applied()
        self.launch()
        with mock.patch.object(boot_guard, "_write", side_effect=OSError("disk is full")):
            outcome = self.launch()
        self.assertEqual(self.read(target), NEW)
        self.assertIn("disk is full", outcome["left"][0]["why"])
        self.assertIn("NOT put back", " ".join(self.said))

    def test_a_failure_nobody_foresaw_is_said_not_raised(self):
        self.applied()
        with mock.patch.object(boot_guard, "_load", side_effect=RuntimeError("something odd")):
            outcome = self.launch()
        self.assertIn("something odd", " ".join(outcome["notes"]))
        self.assertIn("something odd", " ".join(self.said))

    def test_mark_healthy_with_nothing_to_mark_is_zero(self):
        self.assertEqual(boot_guard.mark_healthy(self.project), 0)


class TheTimer(WithAGuardedProject):
    def test_a_start_that_lasts_is_proved_after_the_time(self):
        self.applied()
        self.launch()
        self.assertTrue(boot_guard.arm(self.project, after=0.05))
        deadline = time.time() + 5
        while boot_guard.pending(self.store) and time.time() < deadline:
            time.sleep(0.02)
        self.assertEqual(boot_guard.pending(self.store), [])

    def test_there_is_nothing_to_prove_before_a_change_has_been_started(self):
        self.assertFalse(boot_guard.arm(self.project))
        self.applied()
        self.assertFalse(boot_guard.arm(self.project), "applied is not started")

    def test_the_timer_never_keeps_the_program_open(self):
        self.applied()
        self.launch()
        self.assertTrue(boot_guard.arm(self.project, after=300))
        timers = [thread for thread in threading.enumerate() if thread.name == "boot-guard-timer"]
        try:
            self.assertTrue(timers)
            self.assertTrue(all(thread.daemon for thread in timers))
        finally:
            for thread in timers:
                thread.cancel()


class AStartWhoseAssistantDiedIsNotHealthy(WithAGuardedProject):
    """The window can stay open over an assistant that is not running: that start proves nothing."""

    def test_after_fail_a_start_does_not_vouch_for_the_change_however_long_it_lasts(self):
        target = self.applied()
        self.launch()
        boot_guard.fail()
        self.assertEqual(boot_guard.mark_healthy(self.project), 0)
        self.assertEqual([row["change"] for row in boot_guard.pending(self.store)], [FIRST])
        self.launch()                                  # the next start
        self.assertEqual(self.read(target), OLD)

    def test_the_timer_does_not_vouch_after_fail_either(self):
        self.applied()
        self.launch()
        boot_guard.fail()
        self.assertTrue(boot_guard.arm(self.project, after=0.05))
        for timer in [thread for thread in threading.enumerate() if thread.name == "boot-guard-timer"]:
            timer.join(timeout=5)                      # it has fired, and has been refused
        self.assertEqual(len(boot_guard.pending(self.store)), 1)

    def test_a_start_that_did_not_fail_still_vouches(self):
        self.applied()
        self.launch()
        self.assertEqual(boot_guard.mark_healthy(self.project), 1)


class TheGuardIsNotSomethingTheProgramCanBreak(unittest.TestCase):
    def test_the_referee_lists_match_the_pipeline_it_serves(self):
        self.assertEqual(tuple(boot_guard.PROTECTED), tuple(self_change.PROTECTED))
        self.assertEqual(set(boot_guard.NEVER_THROUGH), set(self_change.SKIP_DIRS))

    def test_the_guard_and_its_launcher_are_themselves_off_limits_to_a_change(self):
        self.assertIn("core/boot_guard.py", self_change.PROTECTED)
        self.assertIn("scripts/bootstrap.py", self_change.PROTECTED)

    def test_the_guard_imports_only_the_standard_library(self):
        tree = ast.parse((ROOT / "core" / "boot_guard.py").read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module.split(".")[0])
        self.assertTrue(imported)
        self.assertEqual({name for name in imported if name not in sys.stdlib_module_names}, set(),
                         "the guard exists for a program that cannot start; it cannot need the program")

    def test_the_id_shape_is_the_one_propose_makes(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "project"
            project.mkdir()
            (project / "app.py").write_text(OLD, encoding="utf-8")
            self_change.set_root(project)
            self_change.set_store(Path(temp) / "store")
            try:
                proposal = self_change.propose("app.py", "a test", find="'hello'", replace="'hi'")
            finally:
                self_change.set_root(None)
                self_change.set_store(None)
        self.assertTrue(boot_guard._ID.match(proposal["id"]), proposal["id"])


class WithTheRealPipeline(unittest.TestCase):
    """`core.self_change` writes the watch and the guard reads it: the two must agree."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.project = Path(self._temp.name) / "project"
        (self.project / "scripts").mkdir(parents=True)
        (self.project / "scripts" / "verify.py").write_text("print('full verification passed')\n",
                                                            encoding="utf-8")
        (self.project / "app.py").write_bytes(OLD.replace("\n", "\r\n").encode("utf-8"))   # a Windows file
        self.store = Path(self._temp.name) / "store"
        self_change.set_root(self.project)
        self_change.set_store(self.store)
        boot_guard._FAILED.clear()
        self.addCleanup(self._clean)

    def _clean(self):
        self_change.set_root(None)
        self_change.set_store(None)
        self._temp.cleanup()

    def applied(self) -> str:
        proposal = self_change.propose("app.py", "politer", find="'hello'", replace="'hello, sir'")
        self_change.rehearse(proposal["id"], full=True)
        self_change.confirm(proposal["id"], "voice")
        self_change.confirm(proposal["id"], "panel")
        self_change.apply(proposal["id"])
        return proposal["id"]

    def test_apply_puts_a_code_change_under_watch_with_digests_the_guard_agrees_with(self):
        change = self.applied()
        rows = boot_guard.pending(self.store)
        self.assertEqual([row["change"] for row in rows], [change])
        self.assertEqual(rows[0]["path"], "app.py")
        self.assertEqual(rows[0]["old_sha256"], sha(OLD))                 # the text, line ends as read
        self.assertEqual(rows[0]["applied_sha256"], sha(NEW))
        self.assertEqual(rows[0]["started"], 0)

    def test_the_whole_way_round_the_second_start_puts_the_file_back(self):
        change = self.applied()
        said: list[str] = []
        boot_guard.check_at_launch(self.project, self.store, said.append)
        outcome = boot_guard.check_at_launch(self.project, self.store, said.append)
        self.assertEqual([item["change"] for item in outcome["put_back"]], [change])
        self.assertEqual((self.project / "app.py").read_text(encoding="utf-8"), OLD)
        self.assertEqual((self.project / "app.py").read_bytes(), OLD.replace("\n", "\r\n").encode("utf-8"),
                         "a Windows file comes back with its Windows line ends")
        entry = self_change.ledger(limit=1)[0]
        self.assertEqual((entry["event"], entry["by"]), ("reverted", "boot guard"))
        self.assertEqual(self_change.pending()[0]["stage"], "reverted")
        self.assertEqual(self_change.restart_required(), None, "the note about a restart is gone too")

    def test_the_guard_and_revert_leave_the_same_bytes(self):
        self.applied()
        boot_guard.check_at_launch(self.project, self.store)
        boot_guard.check_at_launch(self.project, self.store)
        by_the_guard = (self.project / "app.py").read_bytes()
        change = self.applied()                         # the same change again, then put back by hand
        self.assertIn("Put back", self_change.revert(change))
        self.assertEqual((self.project / "app.py").read_bytes(), by_the_guard)

    def test_revert_by_hand_takes_it_off_the_list(self):
        change = self.applied()
        self_change.revert(change)
        self.assertEqual(boot_guard.pending(self.store), [])

    def test_a_data_change_is_not_watched(self):
        (self.project / "notes.md").write_text("# notes\n", encoding="utf-8")
        proposal = self_change.propose("notes.md", "a note", find="# notes", replace="# my notes")
        self_change.rehearse(proposal["id"], full=True)
        self_change.confirm(proposal["id"], "voice")
        self_change.confirm(proposal["id"], "panel")
        result = self_change.apply(proposal["id"])
        self.assertFalse(result["boot_watch"])
        self.assertEqual(boot_guard.pending(self.store), [])

    def test_a_code_change_is_not_written_when_the_net_cannot_be_set(self):
        proposal = self_change.propose("app.py", "politer", find="'hello'", replace="'hello, sir'")
        self_change.rehearse(proposal["id"], full=True)
        self_change.confirm(proposal["id"], "voice")
        self_change.confirm(proposal["id"], "panel")
        with mock.patch.object(boot_guard, "watch", side_effect=OSError("store is read-only")):
            with self.assertRaises(OSError):
                self_change.apply(proposal["id"])
        self.assertEqual((self.project / "app.py").read_bytes(), OLD.replace("\n", "\r\n").encode("utf-8"),
                         "a change that could not be put under watch was written anyway")

    def test_a_write_that_fails_takes_the_change_off_the_list(self):
        proposal = self_change.propose("app.py", "politer", find="'hello'", replace="'hello, sir'")
        self_change.rehearse(proposal["id"], full=True)
        self_change.confirm(proposal["id"], "voice")
        self_change.confirm(proposal["id"], "panel")
        real = self_change._atomic_write_text
        calls = []

        def second_write_fails(path, text, *args, **kwargs):
            calls.append(Path(path).name)
            if Path(path).name == "app.py":
                raise OSError("disk went away")
            return real(path, text, *args, **kwargs)

        with mock.patch.object(self_change, "_atomic_write_text", side_effect=second_write_fails):
            with self.assertRaises(OSError):
                self_change.apply(proposal["id"])
        self.assertIn("app.py", calls)
        self.assertEqual(boot_guard.pending(self.store), [], "a change that was never written is not watched")


class TheWholeStory(unittest.TestCase):
    """The failure this exists for, played through with real processes and the real pipeline.

    A change that compiles, passes the rehearsal and is confirmed twice, but cannot be imported once
    the program starts: the one thing a rehearsal in a copy cannot tell. Without the guard, every
    start after it fails until a person puts the file back.
    """

    MAIN = "from actions import greet\nprint(greet.greeting())\n"
    GOOD = "def greeting():\n    return 'hello'\n"
    POLITE = "def greeting():\n    return 'hello, sir'\n"
    BAD = "import a_module_that_does_not_exist\n\ndef greeting():\n    return 'hello, sir'\n"

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.project = Path(self._temp.name) / "project"
        (self.project / "actions").mkdir(parents=True)
        (self.project / "core").mkdir()
        (self.project / "scripts").mkdir()
        (self.project / "main.py").write_text(self.MAIN, encoding="utf-8")
        (self.project / "actions" / "__init__.py").write_text("", encoding="utf-8")
        (self.project / "actions" / "greet.py").write_text(self.GOOD, encoding="utf-8")
        (self.project / "scripts" / "verify.py").write_text("print('ok')\n", encoding="utf-8")
        shutil.copyfile(ROOT / "core" / "boot_guard.py", self.project / "core" / "boot_guard.py")
        self_change.set_root(self.project)
        self_change.set_store(self.project / "config" / "self_change")
        boot_guard._FAILED.clear()
        self.addCleanup(self._clean)

    def _clean(self):
        self_change.set_root(None)
        self_change.set_store(None)
        boot_guard._FAILED.clear()
        self._temp.cleanup()

    def apply_a_change_the_rehearsal_cannot_see(self, new_text: str) -> str:
        proposal = self_change.propose("actions/greet.py", "politer", new_text=new_text)
        # The copy compiles it: the failure is at import, which the check run in the copy does not do.
        self.assertTrue(self_change.rehearse(proposal["id"], command=[sys.executable, "-m", "compileall",
                                                                      "-q", "actions"])["ok"])
        self_change.confirm(proposal["id"], "voice")
        self_change.confirm(proposal["id"], "panel")
        self_change.apply(proposal["id"])
        return proposal["id"]

    def start(self) -> tuple[subprocess.CompletedProcess, str]:
        """What run.bat and run.ps1 do: the launcher's check, then the program in a new process."""
        said = io.StringIO()
        with mock.patch.object(bootstrap, "ROOT", self.project), contextlib.redirect_stdout(said):
            bootstrap.check_the_last_self_change()
        done = subprocess.run([sys.executable, "main.py"], cwd=self.project, capture_output=True,
                              text=True, timeout=60, check=False)
        return done, said.getvalue()

    def current(self) -> str:
        return (self.project / "actions" / "greet.py").read_text(encoding="utf-8")

    def test_a_change_that_cannot_be_imported_costs_one_failed_start_and_not_every_start(self):
        self.apply_a_change_the_rehearsal_cannot_see(self.BAD)
        first, _ = self.start()
        self.assertNotEqual(first.returncode, 0, "the new code cannot start")
        self.assertIn("a_module_that_does_not_exist", first.stderr)
        self.assertEqual(self.current(), self.BAD, "the first start only marks it")
        second, said = self.start()
        self.assertEqual((second.returncode, second.stdout.strip()), (0, "hello"))
        self.assertEqual(self.current(), self.GOOD)
        self.assertIn("taken back", said)
        self.assertIn("actions/greet.py", said)
        third, said = self.start()
        self.assertEqual((third.returncode, third.stdout.strip(), said), (0, "hello", ""))

    def test_a_change_that_starts_and_stays_up_is_kept(self):
        self.apply_a_change_the_rehearsal_cannot_see(self.POLITE)
        first, said = self.start()
        self.assertEqual((first.returncode, first.stdout.strip()), (0, "hello, sir"))
        self.assertIn("starting code it changed itself", said)
        self.assertEqual(boot_guard.mark_healthy(self.project), 1, "main() does this when the window closes")
        second, said = self.start()
        self.assertEqual((second.returncode, second.stdout.strip(), said), (0, "hello, sir", ""))
        self.assertEqual(self.current(), self.POLITE)

    def test_a_change_the_owner_reverts_by_hand_is_not_put_back_twice(self):
        change = self.apply_a_change_the_rehearsal_cannot_see(self.POLITE)
        self.assertIn("Put back", self_change.revert(change))
        for _ in range(2):
            done, said = self.start()
            self.assertEqual((done.returncode, done.stdout.strip(), said), (0, "hello", ""))
        self.assertEqual([entry["event"] for entry in self_change.ledger(limit=10)
                          if entry.get("by") == "boot guard"], [])


class TheLauncherAsksFirst(WithAGuardedProject):
    def with_the_guard_in_the_project(self):
        (self.project / "core").mkdir(exist_ok=True)
        shutil.copyfile(ROOT / "core" / "boot_guard.py", self.project / "core" / "boot_guard.py")

    def test_the_launcher_runs_the_guard_and_the_second_start_puts_the_file_back(self):
        self.with_the_guard_in_the_project()
        target = self.applied()
        shown = io.StringIO()
        with mock.patch.object(bootstrap, "ROOT", self.project), contextlib.redirect_stdout(shown):
            bootstrap.check_the_last_self_change()
            self.assertEqual(self.read(target), NEW, "the first start only marks it")
            bootstrap.check_the_last_self_change()
        self.assertEqual(self.read(target), OLD)
        self.assertIn("taken back", shown.getvalue(), "the person at the console is told")

    def test_a_project_without_the_guard_is_not_an_error_and_prints_nothing(self):
        shown = io.StringIO()
        with mock.patch.object(bootstrap, "ROOT", self.project), contextlib.redirect_stdout(shown):
            bootstrap.check_the_last_self_change()
        self.assertEqual(shown.getvalue(), "")

    def test_a_guard_that_will_not_load_does_not_stop_the_launch(self):
        (self.project / "core").mkdir()
        (self.project / "core" / "boot_guard.py").write_text("def broken(:\n", encoding="utf-8")
        shown = io.StringIO()
        with mock.patch.object(bootstrap, "ROOT", self.project), contextlib.redirect_stdout(shown):
            bootstrap.check_the_last_self_change()
        self.assertIn("could not run", shown.getvalue())
        self.assertIn("Starting anyway", shown.getvalue())

    def test_the_check_runs_before_the_fast_path_that_returns_early(self):
        prefix = Path(self._temp.name) / "venv"
        prefix.mkdir()
        requirements = self.project / "requirements.txt"
        requirements.write_text("requests\n", encoding="utf-8")
        with mock.patch.object(bootstrap, "ROOT", self.project):
            (prefix / bootstrap.MARKER_NAME).write_text(bootstrap.ready_marker(requirements),
                                                        encoding="ascii")
            with mock.patch.object(sys, "prefix", str(prefix)), \
                 mock.patch.object(bootstrap, "check_the_last_self_change") as check:
                code = bootstrap.main([])
        self.assertEqual(code, 0, "this is the launch that skips the install")
        check.assert_called_once_with()


class TheAppSaysHowTheStartIsGoing(unittest.TestCase):
    """`main.py` cannot be imported without a window, so its shape is read, not run."""

    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))

    def function(self, name: str) -> ast.FunctionDef:
        return next(node for node in self.tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == name)

    def test_main_arms_the_timer_once_the_window_exists_and_marks_a_normal_end(self):
        steps = []
        for statement in self.function("main").body:
            text = ast.unparse(statement)
            if text.startswith("ui = JarvisUI"):
                steps.append("window")
            elif text == "_boot_guard('arm')":
                steps.append("arm")
            elif text == "ui.root.mainloop()":
                steps.append("loop")
            elif text == "_boot_guard('mark_healthy')":
                steps.append("healthy")
        self.assertEqual(steps, ["window", "arm", "loop", "healthy"])

    def test_a_dead_assistant_thread_is_reported_and_still_raises(self):
        runner = next(node for node in ast.walk(self.function("main"))
                      if isinstance(node, ast.FunctionDef) and node.name == "runner")
        tries = [node for node in runner.body if isinstance(node, ast.Try)]
        self.assertEqual(len(tries), 1, "the whole body of the thread is under one try")
        handlers = tries[0].handlers
        self.assertEqual([ast.unparse(handler.type) for handler in handlers], ["BaseException"])
        text = [ast.unparse(statement) for statement in handlers[0].body]
        self.assertEqual(text, ["_boot_guard('fail')", "raise"])

    def test_a_spoken_shutdown_is_a_normal_end_and_says_so_before_it_exits(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        exit_at = source.index("_os._exit(0)")
        healthy_at = source.rindex('_boot_guard("mark_healthy")', 0, exit_at)
        self.assertGreater(healthy_at, source.rindex("async def _do_shutdown", 0, exit_at))
        self.assertLess(exit_at - healthy_at, 400, "the call is next to the exit it is for")

    def test_a_failure_of_the_guard_cannot_stop_the_app(self):
        body = self.function("_boot_guard").body
        tries = [node for node in body if isinstance(node, ast.Try)]
        self.assertEqual(len(tries), 1)
        caught = [ast.unparse(handler.type) for handler in tries[0].handlers]
        self.assertEqual(caught, ["Exception"])

    def test_the_guard_is_imported_inside_the_function_not_at_the_top_of_main(self):
        top_level = [ast.unparse(node) for node in self.tree.body
                     if isinstance(node, (ast.Import, ast.ImportFrom))]
        self.assertFalse([line for line in top_level if "boot_guard" in line],
                         "a safety net that can fail to import is a reason the app does not open")


if __name__ == "__main__":
    unittest.main()
