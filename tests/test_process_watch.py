"""tests/test_process_watch.py — the supervisor must watch, not touch.

Two kinds of test here, and the first kind matters more:

* **The read-only proof.** A supervisor that can end another program's life is a
  supervisor that will one day end the wrong one. These tests read the module's
  own text and fail if it ever gains the ability to signal, kill, suspend, or
  re-prioritise a process.
* **The behaviour.** Real short-lived processes, watched until they stop, and a
  speech gate that must stay silent while the owner is talking — including the
  case where the owner pauses for breath, which is not the same as stopping.
"""

from __future__ import annotations

import subprocess
import sys
import time
import unittest
from pathlib import Path

from core.process_watch import (Completion, SpeechGate, Supervisor, Watcher,
                                format_duration, merge)

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# A stand of processes that behave exactly as badly as real ones.
# ---------------------------------------------------------------------------

class _FakeProc:
    def __init__(self, pid, name, create_time, cmdline=(), status="running"):
        self.info = {"pid": pid, "name": name, "create_time": create_time,
                     "cmdline": list(cmdline), "status": status}


class _FakeLib:
    """A process table a test can rewrite between two polls."""

    def __init__(self, *procs):
        self.procs = list(procs)

    def process_iter(self, attrs=None):
        return list(self.procs)

    def set(self, *procs):
        self.procs = list(procs)


class _FakeClock:
    def __init__(self, now=0.0):
        self.now = float(now)

    def __call__(self):
        return self.now

    def tick(self, seconds):
        self.now += seconds
        return self.now


class ReadOnlyProof(unittest.TestCase):
    """The words that must never appear in the module as a call."""

    FORBIDDEN = (".terminate(", ".kill(", ".suspend(", ".resume(", "os.kill",
                 "signal.pthread", ".nice(", ".send_signal(", ".wait(")

    def setUp(self):
        text = (ROOT / "core" / "process_watch.py").read_text(encoding="utf-8")
        self.text = text
        self.code = "\n".join(line for line in text.splitlines()
                              if not line.lstrip().startswith("#"))

    def test_it_cannot_end_or_pause_a_process(self):
        for word in self.FORBIDDEN:
            if word == ".wait(":
                continue          # never called here either; see the next test
            self.assertNotIn(word, self.code, f"process_watch gained {word!r}")

    def test_it_never_blocks_on_a_process(self):
        self.assertNotIn(".wait(", self.code)

    def test_it_does_not_write_to_the_process_table(self):
        for word in ("set_nice(", "cpu_affinity(", "rlimit("):
            self.assertNotIn(word, self.code)


class DurationWording(unittest.TestCase):
    def test_a_person_can_read_it(self):
        self.assertEqual(format_duration(0.8), "0.8 s")
        self.assertEqual(format_duration(12), "12 s")
        self.assertEqual(format_duration(95), "1 min 35 s")
        self.assertEqual(format_duration(600), "10 min")
        self.assertEqual(format_duration(3900), "1 hr 5 min")
        self.assertEqual(format_duration(-4), "0.0 s")


class WatchByPid(unittest.TestCase):
    """A real process, started, watched, and left alone to finish."""

    def test_it_reports_a_finish_once(self):
        child = subprocess.Popen([sys.executable, "-c",
                                  "import time; time.sleep(0.9)"])
        self.addCleanup(lambda: child.poll() is None and child.kill())
        watcher = Watcher()
        watcher.watch_pid(child.pid, "a short job")

        self.assertEqual(watcher.poll(), [], "it reported a finish while still running")
        self.assertTrue(any(p.pid == child.pid for p in watcher.live()))

        child.wait(timeout=30)
        time.sleep(0.1)
        done = watcher.poll()
        self.assertEqual(len(done), 1, done)
        event = done[0]
        self.assertEqual(event.label, "a short job")
        self.assertEqual(event.pid, child.pid)
        self.assertEqual(event.how, "ended")
        self.assertIsNone(event.exit_code, "an unowned process must not claim a code")
        self.assertGreater(event.seconds, 0.5)
        self.assertIn("finished", event.sentence())

        self.assertEqual(watcher.poll(), [], "the same finish was reported twice")

    def test_a_process_that_has_not_started_is_not_an_error(self):
        watcher = Watcher(library=_FakeLib())
        watcher.watch("antigravity")
        self.assertEqual(watcher.poll(), [])
        self.assertEqual(watcher.watched_labels(), ["antigravity"])


class WatchAnOwnedProcess(unittest.TestCase):
    """The one case where an exit code is knowable, and therefore reported."""

    def test_a_clean_exit_is_reported_with_its_code(self):
        child = subprocess.Popen([sys.executable, "-c", "pass"])
        watcher = Watcher()
        watcher.adopt(child, "my build")
        child.wait(timeout=30)
        done = watcher.poll()
        self.assertEqual(len(done), 1)
        self.assertEqual(done[0].exit_code, 0)
        self.assertEqual(done[0].how, "exited")
        self.assertIn("cleanly", done[0].sentence())

    def test_a_failing_exit_is_not_dressed_up(self):
        child = subprocess.Popen([sys.executable, "-c", "raise SystemExit(3)"])
        watcher = Watcher()
        watcher.adopt(child, "my failing build")
        child.wait(timeout=30)
        event = watcher.poll()[0]
        self.assertEqual(event.exit_code, 3)
        self.assertIn("code 3", event.sentence())


class WatchByName(unittest.TestCase):
    def test_a_name_pattern_matches_anywhere_in_the_name(self):
        lib = _FakeLib(_FakeProc(10, "Antigravity Helper", 1.0),
                       _FakeProc(11, "explorer.exe", 1.0))
        watcher = Watcher(library=lib)
        watcher.watch("antigravity", label="Antigravity")
        running = watcher.live()
        self.assertEqual([p.pid for p in running], [10])

    def test_a_pid_reuse_does_not_fake_a_finish(self):
        """The reason identity is pid *and* create time."""
        lib = _FakeLib(_FakeProc(10, "worker", 100.0))
        watcher = Watcher(library=lib)
        watcher.watch_pid(10, "worker")
        watcher.poll()

        # The original died and an unrelated program took pid 10.
        lib.set(_FakeProc(10, "worker", 500.0))
        done = watcher.poll()
        self.assertEqual(len(done), 1, "a reused pid must be reported as a finish")

    def test_an_unreadable_table_is_not_a_finish(self):
        class _Raises(_FakeLib):
            def process_iter(self, attrs=None):
                raise RuntimeError("the table went away")

        watcher = Watcher(library=_Raises(_FakeProc(10, "worker", time.time() - 3)))
        watcher.watch_pid(10, "worker")
        self.assertEqual(watcher.poll(), [], "it never saw the process it was given")
        # The table is now unreadable. "I cannot see it" is not "it finished", and
        # a supervisor that confuses the two announces a build that is still
        # running because one permission check failed.
        self.assertEqual(watcher.poll(), [], "an unreadable table faked a finish")
        self.assertEqual(watcher.watched_labels(), ["worker"], "the watch was dropped")


class SpeechGateRules(unittest.TestCase):
    """Do not speak over a person. Including when the person breathes."""

    def setUp(self):
        self.clock = _FakeClock()
        self.gate = SpeechGate(quiet_for=1.5, clock=self.clock)

    def test_nothing_is_said_over_speech(self):
        self.gate.hold("the agent replied")
        self.assertEqual(self.gate.ready(busy=True), [])
        self.clock.tick(10)
        self.assertEqual(self.gate.ready(busy=True), [])
        self.assertEqual(self.gate.pending, 1)

    def test_a_pause_is_not_a_stop(self):
        self.gate.hold("the agent replied")
        self.assertEqual(self.gate.ready(False), [])
        self.clock.tick(0.6)
        self.assertEqual(self.gate.ready(False)[:0], [])
        self.assertEqual(self.gate.pending, 1, "it spoke during a breath")

    def test_it_speaks_once_the_room_is_quiet(self):
        self.gate.hold("the agent replied")
        self.gate.ready(False)
        self.clock.tick(1.6)
        self.assertEqual(self.gate.ready(False), ["the agent replied"])
        self.assertEqual(self.gate.pending, 0)
        self.assertEqual(self.gate.ready(False), [], "it repeated itself")

    def test_talking_again_resets_the_quiet_clock(self):
        self.gate.hold("the agent replied")
        self.gate.ready(False)
        self.clock.tick(1.0)
        self.gate.ready(True)          # the owner talks again
        self.clock.tick(1.0)
        self.assertEqual(self.gate.ready(False), [], "the clock was not reset")
        self.clock.tick(1.6)
        self.assertEqual(len(self.gate.ready(False)), 1)

    def test_five_finishes_are_one_sentence(self):
        for name in ("alpha", "beta", "gamma"):
            self.gate.hold(f"{name} finished.")
        self.gate.ready(False)
        self.clock.tick(2)
        said = self.gate.ready(False)
        self.assertEqual(len(said), 1)
        self.assertIn("alpha finished", said[0])
        self.assertIn("2 more", said[0])

    def test_merge_leaves_one_line_alone(self):
        self.assertEqual(merge(["only one"]), ["only one"])
        self.assertEqual(merge([]), [])
        self.assertEqual(merge(["", "  "]), [])


class SupervisorWiring(unittest.TestCase):
    """The log is instant; the voice waits. Both are recorded."""

    def setUp(self):
        self.clock = _FakeClock()
        self.lib = _FakeLib(_FakeProc(10, "worker", time.time() - 5))
        self.logged: list[str] = []
        self.said: list[str] = []
        self.watcher = Watcher(library=self.lib)
        self.watcher.watch_pid(10, "worker")
        self.sup = Supervisor(self.watcher,
                              gate=SpeechGate(quiet_for=1.0, clock=self.clock),
                              say=self.said.append, log=self.logged.append)
        self.sup.tick(False)                      # note it running

    def test_the_log_is_written_at_once_and_the_voice_waits(self):
        self.lib.procs = []
        self.assertEqual(self.sup.tick(busy=True), [])
        self.assertEqual(len(self.logged), 1, "the record waited for silence")
        self.assertEqual(self.said, [], "it spoke over the owner")

        # Silence starts now. The gate must wait for a quiet stretch, not speak
        # on the first poll after the conversation ends.
        self.clock.tick(1.1)
        self.assertEqual(self.sup.tick(busy=False), [], "it spoke the instant she stopped")
        self.clock.tick(1.1)
        self.assertEqual(self.sup.tick(busy=False), self.logged)
        self.assertEqual(self.said, self.logged)
        self.assertEqual(len(self.sup.completions), 1)

    def test_status_line_names_what_is_running(self):
        self.assertIn("worker", self.sup.status_line())
        self.lib.procs = []
        self.assertIn("Nothing", self.sup.status_line())


class ApplicationWiring(unittest.TestCase):
    """The watcher must be started, and it must read the owner's own state.

    A module nobody calls is a paragraph, not a capability, so this checks the
    two lines in main.py that matter: the loop is created, and the quiet test
    includes both Ultron speaking and the microphone hearing the owner.
    """

    def setUp(self):
        self.text = (ROOT / "main.py").read_text(encoding="utf-8", errors="replace")

    def test_the_loop_is_started(self):
        self.assertIn("async def _process_watch_loop", self.text)
        self.assertIn("asyncio.create_task(self._process_watch_loop())", self.text)

    def test_busy_means_speaking_or_hearing_the_owner(self):
        self.assertIn("def _owner_is_talking", self.text)
        block = self.text.split("def _owner_is_talking", 1)[1].split("def ", 1)[0]
        self.assertIn("speaking", block)
        self.assertIn("_mic_level", block)

    def test_the_watched_names_are_configurable(self):
        self.assertIn("ULTRON_WATCH", self.text)


class DefaultWatchList(unittest.TestCase):
    def test_the_defaults_are_names_a_person_recognises(self):
        from core.process_watch import WATCHED_BY_DEFAULT
        self.assertIn("antigravity", WATCHED_BY_DEFAULT)
        for pattern in WATCHED_BY_DEFAULT:
            self.assertEqual(pattern, pattern.lower())


if __name__ == "__main__":
    unittest.main()


class CompiledFeed(unittest.TestCase):
    """The Go sidecar feeds the same gate; its death falls back to Python.

    Two sources, one announcement path. These tests use a fake feed so they run on
    a machine with no Go toolchain — which is most machines, and is exactly the
    situation the fallback exists for.
    """

    class _Feed:
        def __init__(self, events, alive=True):
            self.events = list(events)
            self.alive = alive

        def poll(self):
            out, self.events = self.events, []
            return out

    def _supervisor(self, feed):
        logged, said = [], []
        sup = Supervisor(None, gate=SpeechGate(quiet_for=0.0), feed=feed,
                         say=said.append, log=logged.append)
        return sup, logged, said

    def test_a_sidecar_event_is_announced_like_any_other(self):
        event = Completion(label="antigravity", pid=1, name="antigravity",
                           seconds=90, exit_code=None, how="ended")
        sup, logged, said = self._supervisor(self._Feed([event]))
        sup.tick(busy=False)
        self.assertEqual(len(logged), 1)
        self.assertIn("finished", logged[0])
        self.assertEqual(said, logged)

    def test_a_dead_sidecar_says_so_once_and_stops_reading(self):
        event = Completion(label="x", pid=2, name="x", seconds=1)
        feed = self._Feed([event], alive=False)
        sup, logged, _said = self._supervisor(feed)
        sup.tick(busy=False)
        self.assertTrue(any("stopped" in line for line in logged),
                        "a dead sidecar passed for a quiet machine")
        self.assertIsNone(sup.feed, "the dead feed was kept")

    def test_no_watcher_and_no_feed_is_legal_and_quiet(self):
        sup = Supervisor(None)
        self.assertEqual(sup.tick(busy=False), [])
        self.assertIn("not the one running", sup.status_line())
