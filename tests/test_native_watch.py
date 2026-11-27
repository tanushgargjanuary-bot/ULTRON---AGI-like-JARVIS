"""The freeze watch: Ultron starts the Rust helper, which notes when Ultron stops answering.

2026-11-27, the owner, asked what the Rust helper should do first: "(a)", which was: watch Ultron and note when it freezes,
with no restarts, switched off until he switches it on.

What is held here, in seconds, on any machine:
* the switch: off on a new install, and only a saved `true` turns it on (`memory/config_manager.py`);
* `core/native_core.py`: where the program is looked for, how it is started (with the three options the Rust program
  accepts, its output in `logs/child-ultron-core.log` and never thrown away), how it is stopped, what it noted last
  time, and that every failure is noted and said and never raised;
* the window: a button that shows the switch and says when it takes effect, and a pulse the beats wait for;
* `main.py`: the helper is started in one place, in the background, outside any `try`;
* the two ends: the options, the limit and the words Python reads are in the Rust source;
* `docs/FREEZE_WATCH.md`: what it tells the owner is the same as the code.

The end-to-end tests, which start the real program, are in `tests/test_hybrid_ipc.py` and run in
`.github/workflows/native-build.yml`. The clock itself is tested in `native/ultron-core/src/watchdog/stall.rs`.
"""

from __future__ import annotations

import ast
import asyncio
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import failures, heartbeat, native_core

try:
    from tempconfig import WithATemporaryConfig, cm
except ImportError:
    from tests.tempconfig import WithATemporaryConfig, cm

ROOT = Path(__file__).resolve().parents[1]
CRATE = ROOT / "native" / "ultron-core"
MAIN = (ROOT / "main.py").read_text(encoding="utf-8")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TheSwitchIsOffUntilTheOwnerTurnsItOn(WithATemporaryConfig):
    def test_a_new_install_has_it_off(self):
        self.assertIs(cm.get_native_watch_enabled(), False)

    def test_only_a_saved_true_turns_it_on(self):
        for value in ("true", "yes", 1, "1", None, [], {}, 0, "false"):
            with self.subTest(saved=value):
                self.write_settings({"native_watch_enabled": value})
                self.assertIs(cm.get_native_watch_enabled(), False)
        self.write_settings({"native_watch_enabled": True})
        self.assertIs(cm.get_native_watch_enabled(), True)

    def test_saving_it_changes_that_one_key_and_keeps_the_others(self):
        self.write_settings({"morning_brief_enabled": True, "ui_scale": 1.25})
        cm.save_native_watch_enabled(True)
        self.assertEqual(self.read_settings(),
                         {"morning_brief_enabled": True, "ui_scale": 1.25, "native_watch_enabled": True})
        cm.save_native_watch_enabled(False)
        self.assertIs(cm.get_native_watch_enabled(), False)


class TheProgramIsLookedForWhereTheBuildPutsIt(unittest.TestCase):
    def test_the_place_is_where_the_build_check_leaves_it(self):
        self.assertEqual(native_core.RELATIVE_PATH.as_posix(), "native/ultron-core/target/release/ultron-core.exe")
        self.assertIn(native_core.RELATIVE_PATH.as_posix(), read(ROOT / ".github" / "workflows" / "native-build.yml"))

    def test_an_environment_variable_points_somewhere_else(self):
        with tempfile.TemporaryDirectory() as folder:
            program = Path(folder) / "mine.exe"
            program.write_bytes(b"MZ")
            with mock.patch.object(native_core, "IS_WINDOWS", True), \
                    mock.patch.dict(os.environ, {"ULTRON_NATIVE_CORE": str(program)}):
                self.assertEqual(native_core.binary_path(), program)

    def test_a_named_path_that_is_wrong_is_none_and_the_reason_names_it(self):
        # The owner said where it is. If that is wrong, the reason says so; another copy is not quietly used.
        with tempfile.TemporaryDirectory() as folder:
            wrong = Path(folder) / "not-there.exe"
            with mock.patch.object(native_core, "IS_WINDOWS", True), \
                    mock.patch.dict(os.environ, {"ULTRON_NATIVE_CORE": str(wrong)}):
                self.assertIsNone(native_core.binary_path())
                self.assertIn(str(wrong), native_core.why_missing())

    def test_a_missing_program_is_none_and_the_reason_names_the_place_and_the_download(self):
        with mock.patch.object(native_core, "IS_WINDOWS", True), \
                mock.patch.dict(os.environ, {"ULTRON_NATIVE_CORE": ""}), \
                mock.patch.object(native_core, "ROOT", Path(tempfile.gettempdir()) / "no-such-ultron"):
            self.assertIsNone(native_core.binary_path())
            reason = native_core.why_missing()
        self.assertIn("ultron-core.exe", reason)
        self.assertIn("ultron-core-windows-x64", reason)
        self.assertIn("nothing will watch until it is there", reason)

    def test_it_is_windows_only_like_the_crate(self):
        with mock.patch.object(native_core, "IS_WINDOWS", False):
            self.assertIsNone(native_core.binary_path())
            self.assertIn("Windows", native_core.why_missing())


class StartingAndStoppingTheHelper(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.program = Path(self._folder.name) / "ultron-core.exe"
        self.program.write_bytes(b"MZ")
        for patch in (mock.patch.object(native_core, "IS_WINDOWS", True),
                      mock.patch.dict(os.environ, {"ULTRON_NATIVE_CORE": str(self.program)})):
            patch.start()
            self.addCleanup(patch.stop)
        failures.clear()

    def test_it_starts_with_the_three_options_and_its_output_goes_to_its_log(self):
        log = tempfile.TemporaryFile()
        self.addCleanup(log.close)
        with mock.patch.object(native_core.crash, "child_log", return_value=log), \
                mock.patch.object(native_core.subprocess, "Popen") as popen:
            helper = native_core.start(stall_seconds=30, wait_seconds=120)
        self.assertIsNotNone(helper)
        self.assertEqual(popen.call_args.args[0],
                         [str(self.program), "--once", "--wait-seconds=120", "--stall-seconds=30"])
        keywords = popen.call_args.kwargs
        self.assertIs(keywords["stdout"], log, "the helper's words go to logs/child-ultron-core.log")
        self.assertEqual(keywords["stderr"], native_core.subprocess.STDOUT)
        self.assertTrue(log.closed, "the child keeps its own copy of the handle, so this one is closed")

    def test_a_log_that_cannot_be_opened_is_on_record_and_the_helper_still_starts(self):
        # `crash.child_log` is the real one here: a FILE where its folder should be makes the open fail.
        blocker = Path(self._folder.name) / "a-file-where-a-folder-should-be"
        blocker.write_bytes(b"")
        with mock.patch.dict(native_core.crash._state, {"root": blocker}), \
                mock.patch.object(native_core.subprocess, "Popen") as popen:
            helper = native_core.start()
        self.assertIsNotNone(helper)
        self.assertEqual(popen.call_args.kwargs["stdout"], native_core.subprocess.DEVNULL)
        self.assertIn("crash.child_log", [note["where"] for note in failures.recent()],
                      "the output is dropped knowingly: the reason is on record")

    def test_a_start_that_fails_is_noted_and_returns_none(self):
        with mock.patch.object(native_core.crash, "child_log", return_value=None), \
                mock.patch.object(native_core.subprocess, "Popen", side_effect=OSError("blocked")):
            self.assertIsNone(native_core.start())
        started = [note for note in failures.recent() if note["where"] == "native_core.start"]
        self.assertEqual(len(started), 1)
        self.assertIn("blocked", started[0]["error"])

    def test_without_the_program_nothing_is_started(self):
        self.program.unlink()
        with mock.patch.object(native_core.subprocess, "Popen") as popen:
            self.assertIsNone(native_core.start())
        popen.assert_not_called()

    def test_stopping_asks_the_helper_to_end_and_waits_for_it(self):
        process = mock.Mock()
        process.poll.return_value = None
        native_core.NativeCore(process=process).stop()
        process.terminate.assert_called_once()
        process.wait.assert_called_once()
        process.kill.assert_not_called()

    def test_a_helper_that_ignores_the_request_is_ended_by_force(self):
        process = mock.Mock()
        process.poll.return_value = None
        process.wait.side_effect = [native_core.subprocess.TimeoutExpired("ultron-core", 5), None]
        native_core.NativeCore(process=process).stop()
        process.kill.assert_called_once()

    def test_stopping_a_helper_that_has_already_ended_does_nothing(self):
        process = mock.Mock()
        process.poll.return_value = 0
        native_core.NativeCore(process=process).stop()
        process.terminate.assert_not_called()

    def test_a_stop_that_fails_is_noted_and_not_raised(self):
        # It runs at exit, where an exception has nowhere to go.
        process = mock.Mock()
        process.poll.return_value = None
        process.terminate.side_effect = PermissionError("access denied")
        native_core.NativeCore(process=process).stop()
        self.assertIn("native_core.stop", [note["where"] for note in failures.recent()])


class WhatTheHelperNotedLastTime(unittest.TestCase):
    HEADER = "--- 2026-11-27 20:00:00 ultron-core started ---"

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.path = Path(self._folder.name) / "child-ultron-core.log"

    def log(self, text: str) -> None:
        self.path.write_text(text, encoding="utf-8")

    def test_no_log_is_no_news(self):
        self.assertEqual(native_core.previous_run(self.path), {})
        self.assertIsNone(native_core.report_for({}))

    def test_a_run_with_no_freeze_is_no_news(self):
        self.log(f"\n{self.HEADER}\n  INFO ultron_core::ipc::server: [IPC] Connection established.\n")
        self.assertEqual(native_core.previous_run(self.path), {})

    def test_only_the_last_run_counts(self):
        self.log(f"\n{self.HEADER}\n[Watch] STALL: a\n[Watch] STALL: b\n[Watch] STALL: c\n"
                 f"\n{self.HEADER}\n[Watch] STALL: d\n[Watch] RECOVERED: heartbeats from Ultron are back after 47 s of silence.\n")
        self.assertEqual(native_core.previous_run(self.path), {"stalls": 1, "longest": 47, "unfinished": False})

    def test_a_freeze_that_was_still_going_when_the_log_stopped_is_said_so(self):
        self.log(f"\n{self.HEADER}\n[Watch] STALL: a\n[Watch] RECOVERED: back after 12 s of silence.\n[Watch] STALL: b\n")
        self.assertEqual(native_core.previous_run(self.path), {"stalls": 2, "longest": 12, "unfinished": True})

    def test_the_longest_silence_that_ended_is_the_one_reported(self):
        self.log(f"\n{self.HEADER}\n[Watch] STALL: a\n[Watch] RECOVERED: back after 31 s of silence.\n"
                 "[Watch] STALL: b\n[Watch] RECOVERED: back after 140 s of silence.\n")
        self.assertEqual(native_core.previous_run(self.path)["longest"], 140)

    def test_a_log_that_cannot_be_read_is_noted_and_is_no_news(self):
        failures.clear()
        self.path.mkdir()          # a folder where the file should be: reading it is an OSError
        self.assertEqual(native_core.previous_run(self.path), {})
        self.assertIn("native_core.previous_run", [note["where"] for note in failures.recent()])

    def test_the_sentence_counts_correctly_in_the_singular_and_the_plural(self):
        one = native_core.report_for({"stalls": 1, "longest": 0, "unfinished": False})
        self.assertIn("answering 1 time.", one)
        self.assertIn("in the last run it watched", one, "a run with the watch off writes nothing, so \"last time\" would be untrue")
        self.assertNotIn("1 times", one)
        two = native_core.report_for({"stalls": 2, "longest": 47, "unfinished": True})
        self.assertIn("2 times", two)
        self.assertIn("lasted 47 s", two)
        self.assertIn("had not ended when Ultron closed", two)
        self.assertIn("logs/child-ultron-core.log", two)
        self.assertNotIn("had not ended", one)

    def test_the_parser_reads_the_lines_the_rust_source_writes(self):
        # The two ends meet in text. Take the format strings out of the Rust source, fill in the numbers as the
        # program would, wrap them as `tracing` does, and read them back with the Python parser.
        server = read(CRATE / "src" / "ipc" / "server.rs")
        stall = re.search(r'"(\[Watch\] STALL[^"]*)"', server).group(1).replace("{:.0}", "31").replace("{}", "41")
        recovered = re.search(r'"(\[Watch\] RECOVERED[^"]*)"', server).group(1).replace("{:.0}", "47")
        prefix = "2026-11-27T20:01:00.123456Z  WARN ultron_core::ipc::server: "
        self.log(f"\n{self.HEADER}\n{prefix}{stall}\n{prefix}{recovered}\n{prefix}{stall}\n")
        self.assertEqual(native_core.previous_run(self.path), {"stalls": 2, "longest": 47, "unfinished": True})


class TheTwoEndsAgree(unittest.TestCase):
    """The options, the limit and the words that Python and the end-to-end tests rely on are in the Rust source."""

    @classmethod
    def setUpClass(cls):
        cls.server = read(CRATE / "src" / "ipc" / "server.rs")
        cls.guard = read(CRATE / "src" / "watchdog" / "boot_guard.rs")
        cls.end_to_end = read(ROOT / "tests" / "test_hybrid_ipc.py")

    def test_every_option_python_passes_is_one_rust_accepts(self):
        passed = [argument.split("=")[0] for argument in native_core.arguments()]
        self.assertEqual(passed, ["--once", "--wait-seconds", "--stall-seconds"])
        # The exact forms in `Options::from_arguments`: the unit tests further down the same file spell the options
        # too, so a looser look would still find them after the real code stopped reading them.
        for name in passed:
            with self.subTest(option=name):
                reads = 'argument == "--once"' if name == "--once" else f'argument.strip_prefix("{name}=")'
                self.assertIn(reads, self.server)

    def test_the_limit_and_the_wait_are_the_defaults_the_rust_program_has(self):
        limit = re.search(r"HEARTBEAT_TIMEOUT: Duration = Duration::from_secs\((\d+)\)", self.guard)
        every = re.search(r"HEARTBEAT_INTERVAL: Duration = Duration::from_secs\((\d+)\)", self.guard)
        wait = re.search(r"wait_for_first: Duration::from_secs\((\d+)\)", self.server)
        self.assertTrue(limit and every and wait, "the Rust source changed shape: update this test with it")
        self.assertEqual(native_core.STALL_SECONDS, int(limit.group(1)))
        self.assertEqual(heartbeat.DEFAULT_INTERVAL_S, float(every.group(1)))
        self.assertEqual(native_core.WAIT_SECONDS, int(wait.group(1)))

    def test_a_stall_is_several_missed_beats_and_the_window_grace_is_shorter_than_it(self):
        self.assertGreaterEqual(native_core.STALL_SECONDS, 3 * heartbeat.DEFAULT_INTERVAL_S)
        self.assertLess(native_core.WINDOW_GRACE_SECONDS, native_core.STALL_SECONDS)
        self.assertGreater(native_core.WINDOW_GRACE_SECONDS, heartbeat.DEFAULT_INTERVAL_S,
                           "a window busy for one beat's time is a hiccup, not a freeze")

    def test_the_words_python_and_the_end_to_end_tests_look_for_are_in_the_rust_source(self):
        for words in ("[Watch] STALL", "[Watch] RECOVERED", "Nothing is restarted", "Nobody connected",
                      "unknown argument", "the last one was number", "back after {:.0} s of silence"):
            with self.subTest(words=words):
                self.assertIn(words, self.server)
        for words in ("STALL", "RECOVERED", "Nothing is restarted", "Nobody connected", "unknown argument",
                      "the last one was number"):
            with self.subTest(end_to_end=words):
                self.assertIn(words, self.end_to_end)


class TheWindowGate(unittest.TestCase):
    def test_a_window_that_answered_a_moment_ago_lets_the_beat_go(self):
        gate = native_core.window_gate(lambda: 0.4)
        self.assertIsNone(gate())

    def test_the_limit_itself_still_lets_it_go_and_one_more_second_does_not(self):
        limit = native_core.WINDOW_GRACE_SECONDS
        self.assertIsNone(native_core.window_gate(lambda: limit)())
        held = native_core.window_gate(lambda: limit + 1)()
        self.assertIn(f"the window has not answered for {limit + 1:.0f} s", held)

    def test_a_real_emitter_with_the_gate_sends_nothing_while_the_window_is_silent_and_resumes_after(self):
        from tests.test_hybrid_ipc import StubClient, wait_until
        silence = [30.0]

        async def scenario():
            client = StubClient()
            emitter = heartbeat.HeartbeatEmitter(client, interval=0.005, gate=native_core.window_gate(lambda: silence[0]))
            self.assertTrue(await emitter.start())
            await asyncio.sleep(0.1)
            while_silent = list(client.beats)
            silence[0] = 0.5                       # the window ran its timer again
            await wait_until(lambda: len(client.beats) >= 2)
            await emitter.stop()
            return while_silent, client.beats

        failures.clear()
        while_silent, afterwards = asyncio.run(scenario())
        self.assertEqual(while_silent, [])
        self.assertGreaterEqual(len(afterwards), 2)
        lost = [note for note in failures.recent() if note["where"] == "heartbeat.lost"]
        self.assertEqual(len(lost), 1)
        self.assertIn("the window has not answered for 30 s", lost[0]["error"])


class FakeEmitter:
    """Stands in for `HeartbeatEmitter`: what `begin` hands it, and whether it starts."""

    made: list = []
    will_start = True

    def __init__(self, client=None, interval=5.0, gate=None):
        self.gate = gate
        FakeEmitter.made.append(self)

    async def start(self):
        return FakeEmitter.will_start


class BeginStartsItBehindTheSwitch(WithATemporaryConfig):
    def setUp(self):
        super().setUp()
        failures.clear()
        FakeEmitter.made, FakeEmitter.will_start = [], True
        self.events: list = []
        self.said: list[str] = []
        self.helper = mock.Mock()
        self.registered = mock.Mock()
        for patch in (
            mock.patch.object(native_core, "HeartbeatEmitter", FakeEmitter),
            mock.patch.object(native_core, "binary_path", return_value=Path("ultron-core.exe")),
            mock.patch.object(native_core, "previous_run", return_value={}),
            mock.patch.object(native_core, "start", side_effect=self._start),
            mock.patch.object(native_core.atexit, "register", self.registered),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def _start(self, *_):
        self.events.append("start")
        return self.helper

    def say(self, line: str) -> None:
        self.events.append("say")
        self.said.append(line)

    def begin(self, window_silence=lambda: 0.0):
        return asyncio.run(native_core.begin(self.say, window_silence))

    def test_off_starts_nothing_and_says_nothing(self):
        self.assertIsNone(self.begin())
        self.assertEqual((self.events, FakeEmitter.made), ([], []))

    def test_on_without_the_program_says_why_and_starts_nothing(self):
        cm.save_native_watch_enabled(True)
        with mock.patch.object(native_core, "binary_path", return_value=None):
            self.assertIsNone(self.begin())
        self.assertEqual(self.events, ["say"])
        self.assertIn("Freeze watch is on, but", self.said[0])
        self.assertIn(native_core.why_missing(), self.said[0])

    def test_on_with_the_program_starts_the_helper_and_the_beats_and_says_so(self):
        cm.save_native_watch_enabled(True)
        watch = self.begin()
        self.assertIsInstance(watch, native_core.FreezeWatch)
        self.assertIs(watch.helper, self.helper)
        self.assertIs(watch.emitter, FakeEmitter.made[0])
        self.assertEqual(self.events, ["start", "say"])
        self.assertIn("Freeze watch is on", self.said[0])
        self.assertIn("restarts nothing", self.said[0])
        self.registered.assert_called_once_with(self.helper.stop)

    def test_what_the_last_run_noted_is_said_before_the_next_start_writes_its_header(self):
        cm.save_native_watch_enabled(True)
        last = {"stalls": 2, "longest": 47, "unfinished": True}
        with mock.patch.object(native_core, "previous_run", return_value=last):
            self.begin()
        self.assertEqual(self.events, ["say", "start", "say"], "the log is read before `start` adds a header to it")
        self.assertIn("stopped answering 2 times", self.said[0])

    def test_the_emitter_is_given_a_gate_that_reads_the_window(self):
        cm.save_native_watch_enabled(True)
        silence = [2.0]
        self.begin(lambda: silence[0])
        gate = FakeEmitter.made[0].gate
        self.assertIsNone(gate())
        silence[0] = 45.0
        self.assertIn("45 s", gate())

    def test_when_ultron_cannot_connect_the_helper_is_ended_and_the_owner_is_told(self):
        cm.save_native_watch_enabled(True)
        FakeEmitter.will_start = False
        self.assertIsNone(self.begin())
        self.helper.stop.assert_called_once()
        self.registered.assert_not_called()
        self.assertTrue(self.said[-1].startswith("ERR: Freeze watch: Ultron could not connect"))

    def test_when_the_helper_will_not_start_the_owner_is_told_and_no_beats_are_started(self):
        cm.save_native_watch_enabled(True)
        with mock.patch.object(native_core, "start", return_value=None):
            self.assertIsNone(self.begin())
        self.assertEqual(FakeEmitter.made, [])
        self.assertTrue(self.said[-1].startswith("ERR: Freeze watch: the helper program would not start"))
        self.assertIn("child-ultron-core.log", self.said[-1])

    def test_anything_that_goes_wrong_is_noted_and_said_and_never_raised(self):
        cm.save_native_watch_enabled(True)
        with mock.patch.object(native_core, "start", side_effect=RuntimeError("boom")):
            self.assertIsNone(self.begin())
        self.assertIn("native_core.begin", [note["where"] for note in failures.recent()])
        self.assertEqual(self.said, ["ERR: Freeze watch could not start: boom"])



class TheStartInMain(unittest.TestCase):
    """`main.py` imports the audio library at module level, so these read its source."""

    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse(MAIN)
        cls.method = next(node for node in ast.walk(cls.tree)
                          if isinstance(node, ast.AsyncFunctionDef) and node.name == "_start_freeze_watch")
        cls.source = ast.get_source_segment(MAIN, cls.method)

    def test_the_method_only_hands_over_to_begin_and_keeps_what_it_returns(self):
        self.assertIn("self._freeze_watch = await native_core.begin(self.ui.write_log, self.ui.window_silence)", self.source)

    def test_main_never_starts_the_program_itself(self):
        self.assertEqual(MAIN.count("native_core.begin("), 1)
        self.assertNotIn("native_core.start(", MAIN)
        self.assertNotIn("ultron-core.exe", MAIN)

    def test_it_is_started_in_the_background_so_the_session_does_not_wait_for_it(self):
        self.assertRegex(MAIN, r'self\._hold\(asyncio\.create_task\(self\._start_freeze_watch\(\)\), "freeze-watch"\)')

    def test_the_handle_exists_before_anything_can_read_it(self):
        init = next(node for node in ast.walk(self.tree) if isinstance(node, ast.FunctionDef)
                    and node.name == "__init__" and "_background_tasks" in ast.dump(node))
        self.assertIn("self._freeze_watch", ast.get_source_segment(MAIN, init))

    def test_the_window_gives_it_a_number_to_read(self):
        # `self.ui.window_silence` has to exist on the bridge `main.py` is given.
        ui_source = read(ROOT / "ui.py")
        self.assertIn("def window_silence(self) -> float:", ui_source)
        self.assertIn("self._pulse_at = time.monotonic()", ui_source)


try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    import ui
    APP = QApplication.instance() or QApplication([])
    HAVE_QT = True
except ImportError:          # pragma: no cover - a machine with no Qt
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "needs PyQt6")
class TheButtonAndThePulseInTheWindow(WithATemporaryConfig):
    def setUp(self):
        super().setUp()
        self.window = ui.MainWindow("face.png")

    def said(self) -> str:
        from tests.test_hud_fixes import type_all
        return type_all(self.window._log)

    def click(self, *, program_there: bool = True) -> None:
        # Windows is the only place the program can exist, so the sentences are the Windows ones on every machine.
        with mock.patch.object(native_core, "IS_WINDOWS", True), \
                mock.patch.object(native_core, "binary_path",
                                  return_value=Path("ultron-core.exe") if program_there else None):
            self.window._watch_btn.click()

    def test_it_says_off_on_a_new_install(self):
        self.assertIn("FREEZE WATCH: OFF", self.window._watch_btn.text())

    def test_a_click_switches_it_on_saves_it_and_says_when_it_takes_effect(self):
        self.click()
        self.assertIs(cm.get_native_watch_enabled(), True)
        self.assertIn("FREEZE WATCH: ON", self.window._watch_btn.text())
        said = self.said()
        self.assertIn("next time Ultron starts", said)
        self.assertIn("logs/child-ultron-core.log", said)

    def test_a_second_click_switches_it_off_and_says_so(self):
        self.click()
        self.click()
        self.assertIs(cm.get_native_watch_enabled(), False)
        self.assertIn("FREEZE WATCH: OFF", self.window._watch_btn.text())
        self.assertIn("Freeze watch is off", self.said())

    def test_a_save_that_fails_leaves_it_off_and_says_so(self):
        with mock.patch.object(cm, "save_native_watch_enabled", side_effect=OSError("disk full")):
            self.window._watch_btn.click()
        self.assertIn("FREEZE WATCH: OFF", self.window._watch_btn.text())
        said = self.said()
        self.assertIn("Could not save", said)
        self.assertIn("disk full", said)

    def test_it_says_so_when_the_program_is_not_there_yet(self):
        self.click(program_there=False)
        self.assertIn("nothing will watch until it is there", self.said())

    def test_a_window_built_with_it_already_on_shows_on(self):
        cm.save_native_watch_enabled(True)
        other = ui.MainWindow("face.png")
        self.assertIn("FREEZE WATCH: ON", other._watch_btn.text())

    def test_the_one_second_timer_stamps_the_pulse_and_the_bridge_reports_its_age(self):
        bridge = ui.JarvisUI.__new__(ui.JarvisUI)
        bridge._win = self.window
        self.window._pulse_at -= 100.0                      # as if the Qt thread had been stuck for 100 s
        self.assertGreaterEqual(bridge.window_silence(), 100.0)
        self.window._tick_clock()                           # what the timer does each second
        self.assertLess(bridge.window_silence(), 5.0)

    def test_the_pulse_is_driven_by_the_timer_that_runs_every_second(self):
        self.assertEqual(self.window._clock_tmr.interval(), 1000)
        self.assertTrue(self.window._clock_tmr.isActive())

    def test_a_window_that_has_not_pulsed_for_a_long_time_holds_the_beat_back(self):
        bridge = ui.JarvisUI.__new__(ui.JarvisUI)
        bridge._win = self.window
        gate = native_core.window_gate(bridge.window_silence)
        self.assertIsNone(gate())
        self.window._pulse_at -= 60.0
        self.assertIn("the window has not answered for", gate())


class TheGuideTellsTheTruth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / "docs" / "FREEZE_WATCH.md"
        cls.text = path.read_text(encoding="utf-8") if path.is_file() else ""

    def test_the_guide_exists_and_is_listed_in_the_index(self):
        self.assertTrue(self.text, "docs/FREEZE_WATCH.md is missing")
        self.assertIn("FREEZE_WATCH.md", read(ROOT / "docs" / "INDEX.md"))

    def test_it_names_the_setting_the_log_the_download_and_the_path_the_code_uses(self):
        workflow = read(ROOT / ".github" / "workflows" / "native-build.yml")
        artifact = re.search(r"name:\s*(ultron-core-windows-x64)\s*$", workflow, re.M).group(1)
        for needed in ("native_watch_enabled", native_core.log_path().relative_to(ROOT).as_posix(), artifact,
                       str(native_core.RELATIVE_PATH).replace("/", "\\"), "ULTRON_NATIVE_CORE",
                       f"{native_core.STALL_SECONDS} seconds", f"{native_core.WINDOW_GRACE_SECONDS:g} seconds"):
            with self.subTest(needed=needed):
                self.assertIn(needed, self.text)

    def test_it_says_what_the_helper_does_not_do(self):
        flat = " ".join(self.text.split())
        for sentence in ("restarts nothing", "ends nothing", "off until you switch it on"):
            with self.subTest(sentence=sentence):
                self.assertIn(sentence, flat)

    def test_it_says_what_a_line_in_the_log_can_and_cannot_tell_you(self):
        flat = " ".join(self.text.split())
        self.assertIn("cannot say which", flat)
        self.assertIn("Not verified", self.text, "the sleep false alarm is a guess and the guide must say so")


if __name__ == "__main__":
    unittest.main()
