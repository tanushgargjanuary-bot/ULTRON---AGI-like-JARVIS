"""A crash leaves a record, and the next run reads it.

The failure this file exists for is the quietest one in the project: Ultron runs with
its console hidden, `sys.stderr` is not a console, and the failure trail keeps its
notes in memory. Before `core/crash.py` there was no crash handler anywhere, so the
owner's experience of a bug was a window that disappeared.

    a record is written   time, build, kind, message, traceback, and the notes made
                          just before the fall — redacted, rotated, and inside a folder
                          the repository ignores;
    the hooks are armed   main thread, worker thread, unraisable, and a native fault;
    the next run knows   self-evolution starts from the fault rather than from a guess.

Every test points the module at a throwaway folder, so nothing here writes the owner's
`logs/` and no test depends on the order another test ran in.
"""

from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import crash, failures, self_change
from actions import self_change as tool


class WithAFolder(unittest.TestCase):
    """A throwaway project root, and the real one put back afterwards."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self._saved = crash._state["root"]
        crash._state["root"] = self.root
        failures.clear()

    def tearDown(self):
        # Let go of the native-fault file first: on Windows an open handle blocks the
        # delete, and the temporary folder then fails to clean up — which is how the
        # Windows runner found this.
        crash.disarm()
        crash._state["root"] = self._saved
        failures.clear()
        self._temp.cleanup()

    def folder(self) -> Path:
        return self.root / "logs"


class ARecordIsWritten(WithAFolder):
    def test_a_report_is_a_file_that_exists(self):
        path = crash.report(ValueError("bad value"), where="test")
        self.assertTrue(Path(path).exists())
        self.assertTrue(Path(path).name.startswith("crash-"))

    def test_the_report_says_when_what_and_where(self):
        path = crash.report(KeyError("missing"))
        text = Path(path).read_text()
        for wanted in ("time:", "build:", "kind: KeyError", "message:", "traceback:"):
            self.assertIn(wanted, text)

    def test_the_traceback_is_in_it(self):
        try:
            {}["absent"]
        except KeyError as error:
            path = crash.report(error, where="here")
        self.assertIn("KeyError", Path(path).read_text())
        self.assertIn("test_crash.py", Path(path).read_text())

    def test_two_crashes_in_one_second_are_two_files(self):
        first = crash.report("one")
        second = crash.report("two")
        self.assertNotEqual(first, second)
        self.assertTrue(Path(first).exists() and Path(second).exists())

    def test_the_notes_from_just_before_are_in_the_report(self):
        failures.note("audio_devices.open", OSError("no device"))
        path = crash.report("fell over")
        self.assertIn("audio_devices.open", Path(path).read_text())

    def test_a_report_with_no_notes_says_so_rather_than_showing_nothing(self):
        path = crash.report("fell over")
        self.assertIn("no note was left", Path(path).read_text())

    def test_a_credential_in_the_message_is_removed(self):
        path = crash.report("token github_pat_11BZOGZLY0NW6ftNVlHd0K_abcdefgh")
        self.assertNotIn("github_pat_11BZOG", Path(path).read_text())
        self.assertIn("<removed>", Path(path).read_text())

    def test_bearer_authorization_token_is_removed(self):
        token = "abcdef.fedcba-123456"
        cleaned = crash.redact(f"Authorization: Bearer {token}")
        self.assertNotIn(token, cleaned)
        self.assertIn("Authorization: Bearer <removed>", cleaned)

    def test_a_key_named_in_a_dictionary_is_removed(self):
        text = crash.compose('{"api_key": "abcdef1234567890"}')
        self.assertNotIn("abcdef1234567890", text)

    def test_composing_writes_no_file(self):
        crash.compose("just text")
        self.assertFalse(self.folder().exists())

    def test_a_folder_that_cannot_be_made_returns_nothing_instead_of_raising(self):
        # A path that is a FILE, not a folder: `mkdir` fails on every platform. The
        # earlier version of this test used chmod, which Windows ignores — so it passed
        # on Linux and was a false pass on the machine that matters.
        blocked = self.root / "blocked"
        blocked.write_text("not a folder", encoding="utf-8")
        self.assertEqual(crash.report("x", root=blocked), "")

    def test_only_the_newest_reports_are_kept(self):
        for index in range(crash.KEEP + 5):
            crash.report(f"crash {index}")
        self.assertEqual(len(crash.paths()), crash.KEEP)

    def test_clearing_removes_every_report(self):
        crash.report("one")
        crash.report("two")
        self.assertEqual(crash.clear(), 2)
        self.assertEqual(crash.paths(), [])


class ReadingThemBack(WithAFolder):
    def test_history_is_newest_first(self):
        first = crash.report("older")
        second = crash.report("newer")
        rows = crash.history()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["path"], second)
        self.assertEqual(rows[1]["path"], first)

    def test_each_row_carries_the_header_and_the_path(self):
        crash.report(ValueError("nope"), where="somewhere")
        row = crash.history()[0]
        self.assertEqual(row["kind"], "ValueError")
        self.assertEqual(row["where"], "somewhere")
        self.assertTrue(row["path"].endswith(".txt"))

    def test_digest_with_nothing_to_report_says_so_in_words(self):
        self.assertIn("no record of crashing", crash.digest())

    def test_digest_names_the_newest_crash(self):
        crash.report(ValueError("nope"), where="somewhere")
        text = crash.digest()
        self.assertIn("1 crash report", text)
        self.assertIn("ValueError", text)
        self.assertIn("somewhere", text)

    def test_the_traceback_can_be_read_on_its_own(self):
        try:
            raise RuntimeError("the fault")
        except RuntimeError as error:
            crash.report(error, where="here")
        self.assertIn("RuntimeError", crash.last_trace())

    def test_the_startup_notice_is_empty_when_nothing_crashed(self):
        self.assertEqual(crash.startup_notice(), "")

    def test_the_startup_notice_names_the_last_crash_in_one_line(self):
        crash.report(ValueError("nope"), where="here")
        notice = crash.startup_notice()
        self.assertIn("I crashed on", notice)
        self.assertEqual(len(notice.splitlines()), 1)

    def test_the_summary_counts_what_kind_they_were(self):
        crash.report(ValueError("a"))
        crash.report(ValueError("b"))
        crash.report(KeyError("c"))
        summary = crash.summary()
        self.assertEqual(summary["reports"], 3)
        self.assertEqual(summary["kinds"]["ValueError"], 2)

    def test_the_folder_is_reported_so_it_can_be_told_to_a_person(self):
        self.assertTrue(crash.folder().endswith("logs"))


class TheHooksAreArmed(WithAFolder):
    def test_installing_sets_the_main_thread_hook(self):
        saved = (sys.excepthook, crash._state["installed"])
        crash._state["installed"] = False
        try:
            result = crash.install(root=self.root)
            self.assertTrue(result["installed"])
            self.assertFalse(result["again"])
            self.assertIs(sys.excepthook, crash._on_exception)
            self.assertTrue(crash.is_installed())
        finally:
            sys.excepthook = saved[0]
            crash._state["installed"] = saved[1]

    def test_installing_twice_changes_nothing(self):
        saved = (sys.excepthook, crash._state["installed"])
        crash._state["installed"] = False
        try:
            crash.install(root=self.root)
            again = crash.install(root=self.root)
            self.assertTrue(again["again"])
        finally:
            sys.excepthook = saved[0]
            crash._state["installed"] = saved[1]

    def test_a_worker_thread_crash_is_recorded(self):
        class Fake:                                # what threading.ExceptHookArgs gives
            exc_value = ValueError("in a thread")
            exc_type = ValueError
            thread = threading.current_thread()
        crash._on_thread(Fake())
        row = crash.history()[0]
        self.assertEqual(row["kind"], "ValueError")
        self.assertIn("worker thread", row["where"])

    def test_an_unraisable_failure_is_recorded(self):
        class Fake:
            exc_value = RuntimeError("in __del__")
            exc_type = RuntimeError
            object = "an object"
        crash._on_unraisable(Fake())
        self.assertEqual(crash.history()[0]["kind"], "RuntimeError")

    def test_disarming_puts_the_hooks_back(self):
        saved = (sys.excepthook, threading.excepthook, crash._state["installed"])
        crash._state["installed"] = False
        try:
            crash.install(root=self.root)
            result = crash.disarm()
            self.assertFalse(crash.is_installed())
            self.assertIs(sys.excepthook, sys.__excepthook__)
            self.assertIn("closed", result)
        finally:
            sys.excepthook = saved[0]
            threading.excepthook = saved[1]
            crash._state["installed"] = saved[2]

    def test_installing_into_a_second_folder_lets_go_of_the_first(self):
        crash._state["installed"] = False
        first = self.root / "one"
        second = self.root / "two"
        first.mkdir()
        second.mkdir()
        try:
            crash.install(root=first)
            crash.install(root=second)
            self.assertEqual(crash.folder(), str(second / "logs"))
        finally:
            crash.disarm()

    def test_an_exception_reaching_the_top_writes_a_file(self):
        try:
            raise ValueError("top level")
        except ValueError as error:
            path = crash._on_exception(type(error), error, error.__traceback__)
        self.assertTrue(Path(path).exists())


class SelfEvolutionStartsFromTheFault(WithAFolder):
    def test_the_evidence_reads_the_reports(self):
        crash.report(ValueError("nope"), where="core/x.py")
        evidence = self_change.evidence()
        self.assertEqual(evidence["total"], 1)
        self.assertEqual(evidence["crashes"][0]["kind"], "ValueError")
        self.assertIn("folder", evidence)

    def test_a_proposal_carries_the_crash_it_is_probably_about(self):
        base = self.root / "proj"
        (base / "core").mkdir(parents=True)
        (base / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
        saved = (self_change.root(), self_change.store())
        self_change.set_root(base)
        self_change.set_store(self.root / "store")
        crash.report(ValueError("nope"), where="app.py")
        try:
            proposal = self_change.propose("app.py", "fix the crash",
                                           find="VALUE = 1", replace="VALUE = 2")
        finally:
            self_change.set_root(saved[0])
            self_change.set_store(saved[1])
        self.assertEqual(proposal["evidence"][0]["kind"], "ValueError")

    def test_the_tool_answers_why_did_you_crash(self):
        crash.report(ValueError("nope"), where="here")
        answer = tool.self_modify({"action": "crashes"})
        self.assertIn("crash report", answer)
        self.assertIn("ValueError", answer)

    def test_the_tool_can_be_asked_for_the_traceback(self):
        try:
            raise RuntimeError("the fault")
        except RuntimeError as error:
            crash.report(error, where="here")
        answer = tool.self_modify({"action": "crashes", "trace": True})
        self.assertIn("RuntimeError", answer)

    def test_the_tool_with_no_reports_says_where_a_native_one_would_be(self):
        answer = tool.self_modify({"action": "crashes"})
        self.assertIn("no crash report", answer)
        self.assertIn("faulthandler.log", answer)

    def test_the_unknown_action_message_lists_the_new_one(self):
        self.assertIn("crashes", tool.self_modify({"action": "nonsense"}))

    def test_the_tool_schema_declares_the_action(self):
        self.assertIn("crashes", tool.TOOL["parameters"]["properties"]["action"]["enum"])
        self.assertIn("trace", tool.TOOL["parameters"]["properties"])


class TheAppUsesIt(WithAFolder):
    def test_main_installs_the_handlers_before_anything_heavy(self):
        text = (ROOT / "main.py").read_text(encoding="utf-8", errors="replace")
        self.assertIn("_crash.install()", text)

    def test_main_says_what_the_last_run_died_of(self):
        text = (ROOT / "main.py").read_text(encoding="utf-8", errors="replace")
        self.assertIn("_crash.startup_notice()", text)

    def test_the_instruction_tells_it_to_answer_from_the_report(self):
        text = (ROOT / "core" / "prompt.txt").read_text(encoding="utf-8", errors="replace")
        self.assertIn("action=crashes", text)
        self.assertIn("not from memory", text)

    def test_the_reports_are_not_published(self):
        text = (ROOT / ".gitignore").read_text(encoding="utf-8", errors="replace")
        self.assertIn("\nlogs/", text)


if __name__ == "__main__":
    unittest.main()
