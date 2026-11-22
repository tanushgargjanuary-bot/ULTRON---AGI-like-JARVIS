"""`tool_usage.note` no longer stops the event loop for the length of a disk write.

`main.py` calls `tool_usage.note(name)` from `_execute_tool_approved`, on the event loop that
also carries the voice. `note` was a read, a count and a locked, flushed settings write that
waits and retries (up to 0.3 s) when something else has the file; on Windows an antivirus
scanner does. Measured on Linux with nothing contending: 0.81 ms per call at the first commit and
1.1-1.6 ms after the settings file became safer to write, all of it on the loop. The worst case
is the retry wait.

The fix keeps the one thing other code depends on: called anywhere but on an event loop, `note`
still writes before it returns (the proof gate calls it that way and reads the result at once).
Called on a loop, it queues the name and one background thread writes. These tests hold both
halves, and the cost of the change (a call can wait in the queue), and they all run without
touching the real settings file: each stubs the save, or points the settings at a scratch folder.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from pathlib import Path

from core import tool_usage

ROOT = Path(__file__).resolve().parents[1]

try:
    from tempconfig import WithATemporaryConfig
except ImportError:                              # imported as tests.test_tool_usage_loop
    from tests.tempconfig import WithATemporaryConfig

SLOW = 0.25          # how long the stubbed save takes: far longer than any honest call


class _SlowDisk:
    """Replace the save and the read with an in-memory store that is slow to write.

    Records which thread each save ran on, so a test can say where the work happened.
    """

    def __init__(self, delay: float = SLOW):
        self.delay = delay
        self.saved: dict = {}
        self.threads: list[str] = []

    def __enter__(self):
        self._read, self._save = tool_usage.read, tool_usage.settings.save_tool_usage

        def save(value):
            time.sleep(self.delay)
            self.threads.append(threading.current_thread().name)
            self.saved = json.loads(json.dumps(value))

        tool_usage.read = lambda: json.loads(json.dumps(self.saved))
        tool_usage.settings.save_tool_usage = save
        return self

    def __exit__(self, *exc):
        try:
            tool_usage.settle(10)                # nothing may still be writing into a restored store
        finally:
            tool_usage.read, tool_usage.settings.save_tool_usage = self._read, self._save
        return False


class OnTheEventLoopTheCallDoesNotWait(unittest.TestCase):
    def test_a_note_on_the_loop_returns_before_the_disk_has_answered(self):
        with _SlowDisk() as disk:
            async def calls():
                started = time.perf_counter()
                for _ in range(3):
                    tool_usage.note("web_search")
                return time.perf_counter() - started

            elapsed = asyncio.run(calls())
            self.assertLess(elapsed, SLOW / 2, f"three notes stopped the loop for {elapsed:.3f}s; "
                                               f"one save takes {SLOW}s")
            self.assertTrue(tool_usage.settle(10))
            self.assertEqual(disk.saved["web_search"]["count"], 3)

    def test_the_work_runs_on_the_writer_thread_not_the_loops(self):
        with _SlowDisk(0.01) as disk:
            async def one():
                tool_usage.note("reminder")
                return threading.current_thread().name

            loop_thread = asyncio.run(one())
            tool_usage.settle(10)
            self.assertEqual(disk.threads, ["tool-usage-writer"])
            self.assertNotEqual(loop_thread, "tool-usage-writer")

    def test_every_call_is_counted_and_in_order(self):
        with _SlowDisk(0.005) as disk:
            async def many():
                for index in range(40):
                    tool_usage.note(f"tool_{index % 4}")

            asyncio.run(many())
            tool_usage.settle(10)
            self.assertEqual({name: row["count"] for name, row in disk.saved.items()},
                             {"tool_0": 10, "tool_1": 10, "tool_2": 10, "tool_3": 10})

    def test_the_time_recorded_is_when_it_was_called_not_when_it_was_saved(self):
        with _SlowDisk(0.1) as disk:
            stamps = []
            real = tool_usage._iso
            tool_usage._iso = lambda moment: (stamps.append(moment), real(moment))[1]
            try:
                async def one():
                    before = time.time()
                    tool_usage.note("web_search")
                    return before, time.time()

                before, after = asyncio.run(one())
                tool_usage.settle(10)
            finally:
                tool_usage._iso = real
            self.assertEqual(len(stamps), 1)
            self.assertTrue(before <= stamps[0] <= after,
                            "the stamp was taken after the call returned, when the write ran")
            self.assertEqual(disk.saved["web_search"]["count"], 1)

    def test_an_empty_name_is_still_not_a_statistic_on_the_loop(self):
        with _SlowDisk(0.0) as disk:
            async def blanks():
                tool_usage.note("")
                tool_usage.note(None)
                tool_usage.note("   ")

            asyncio.run(blanks())
            tool_usage.settle(10)
            self.assertEqual(disk.saved, {})

    def test_a_save_that_fails_neither_raises_on_the_loop_nor_stops_the_writer(self):
        saved = tool_usage.settings.save_tool_usage
        attempts = []

        def broken(_value):
            attempts.append(1)
            raise OSError("disk is full")

        tool_usage.settings.save_tool_usage = broken
        try:
            async def calls():
                tool_usage.note("web_search")
                tool_usage.note("web_search")

            asyncio.run(calls())                     # must not raise
            tool_usage.settle(10)
            self.assertEqual(len(attempts), 2, "the writer stopped after the first failure")
        finally:
            tool_usage.settings.save_tool_usage = saved

        with _SlowDisk(0.0) as disk:                 # and it still works afterwards
            async def again():
                tool_usage.note("reminder")

            asyncio.run(again())
            tool_usage.settle(10)
            self.assertEqual(disk.saved["reminder"]["count"], 1)


class WhenNoWriterCanBeStarted(unittest.TestCase):
    def test_the_call_is_written_in_place_and_nothing_waits_for_a_thread_that_never_ran(self):
        class NoThreads:
            def __init__(self, *args, **kwargs):
                pass

            def start(self):
                raise RuntimeError("can't start new thread")

            def is_alive(self):
                return False

        with _SlowDisk(0.01) as disk:
            fresh = tool_usage._Writer()
            real_writer, real_thread = tool_usage._WRITER, tool_usage.threading.Thread
            tool_usage._WRITER = fresh
            tool_usage.threading.Thread = NoThreads
            try:
                async def one():
                    tool_usage.note("web_search")

                asyncio.run(one())
                self.assertEqual(disk.saved["web_search"]["count"], 1, "the call was lost")
                started = time.perf_counter()
                self.assertTrue(tool_usage.settle(5))
                self.assertLess(time.perf_counter() - started, 1.0, "settle waited for a thread that never ran")
            finally:
                tool_usage._WRITER, tool_usage.threading.Thread = real_writer, real_thread


class AnywhereElseTheWriteIsStillDoneBeforeNoteReturns(unittest.TestCase):
    """The proof gate's contract, and every existing caller's."""

    def test_a_plain_call_has_written_by_the_time_it_returns(self):
        with _SlowDisk(0.02) as disk:
            tool_usage.note("web_search")
            self.assertEqual(disk.saved["web_search"]["count"], 1, "a plain call must not defer")
            self.assertEqual(disk.threads, [threading.current_thread().name])

    def test_the_proof_gates_own_probe_still_passes(self):
        # scripts/proof_gate.py claim_triggers: replace read and save, note twice, expect 2.
        written: dict = {}
        saved_read, saved_save = tool_usage.read, tool_usage.settings.save_tool_usage
        tool_usage.read = lambda: dict(written)
        tool_usage.settings.save_tool_usage = lambda value: written.update(value)
        try:
            tool_usage.note("gate_probe")
            tool_usage.note("gate_probe")
        finally:
            tool_usage.read, tool_usage.settings.save_tool_usage = saved_read, saved_save
        self.assertEqual(written.get("gate_probe", {}).get("count"), 2)

    def test_a_worker_thread_writes_on_its_own_thread(self):
        with _SlowDisk(0.01) as disk:
            runner = threading.Thread(target=tool_usage.note, args=("web_search",), name="a-tool-thread")
            runner.start()
            runner.join(10)
            self.assertEqual(disk.threads, ["a-tool-thread"])

    def test_a_thread_that_runs_its_own_loop_is_on_a_loop(self):
        with _SlowDisk(0.01) as disk:
            def runs_a_loop():
                async def go():
                    tool_usage.note("web_search")

                asyncio.run(go())

            runner = threading.Thread(target=runs_a_loop)
            runner.start()
            runner.join(10)
            tool_usage.settle(10)
            self.assertEqual(disk.threads, ["tool-usage-writer"])


class ReadersSeeTheCallThatIsBeingMade(WithATemporaryConfig):
    """`render` and `unused` wait for the queue, so the answer is not a few milliseconds stale."""

    def test_render_right_after_a_note_on_the_loop_includes_it(self):
        async def ask():
            tool_usage.note("tools_status")
            return tool_usage.render(["tools_status", "web_search"])

        text = asyncio.run(ask())
        self.assertIn("1 of 2 tools have been called", text)
        self.assertNotIn("No tool has been called yet", text)

    def test_unused_right_after_a_note_on_the_loop_includes_it(self):
        async def ask():
            tool_usage.note("web_search")
            return tool_usage.unused(["web_search", "flight_finder"])

        self.assertEqual(asyncio.run(ask()), ["flight_finder"])

    def test_with_a_slow_disk_render_waits_for_it_rather_than_report_stale_counts(self):
        with _SlowDisk(0.15):
            async def ask():
                tool_usage.note("web_search")
                return tool_usage.render(["web_search", "reminder"])

            self.assertIn("1 of 2 tools have been called", asyncio.run(ask()))

    def test_render_waits_once_for_a_stuck_disk_not_twice(self):
        # render() settles, and used to call unused(), which settles again: two waits on the loop.
        release = threading.Event()
        saved = tool_usage.settings.save_tool_usage
        tool_usage.settings.save_tool_usage = lambda _value: release.wait(10)
        try:
            async def ask():
                tool_usage.note("web_search")
                started = time.perf_counter()
                text = tool_usage.render(["web_search", "reminder"])
                return time.perf_counter() - started, text

            elapsed, text = asyncio.run(ask())
            self.assertLess(elapsed, 1.6, f"render waited {elapsed:.2f}s; one settle is 1 s at most")
            self.assertIn("No tool has been called yet", text, "the write never finished, so nothing is counted")
        finally:
            release.set()
            tool_usage.settle(10)
            tool_usage.settings.save_tool_usage = saved

    def test_settling_with_nothing_queued_is_instant_and_true(self):
        started = time.perf_counter()
        self.assertTrue(tool_usage.settle(5))
        self.assertLess(time.perf_counter() - started, 1.0)

    def test_settling_gives_up_at_its_timeout_when_the_disk_is_stuck(self):
        release = threading.Event()
        saved = tool_usage.settings.save_tool_usage
        tool_usage.settings.save_tool_usage = lambda _value: release.wait(10)
        try:
            async def one():
                tool_usage.note("web_search")

            asyncio.run(one())
            started = time.perf_counter()
            self.assertFalse(tool_usage.settle(0.2), "a stuck write was reported as finished")
            self.assertLess(time.perf_counter() - started, 2.0)
        finally:
            release.set()
            tool_usage.settle(10)
            tool_usage.settings.save_tool_usage = saved

    def test_a_negative_timeout_is_a_zero_timeout(self):
        self.assertTrue(tool_usage.settle(-5), "nothing is queued, so there is nothing to wait for")

    def test_a_zero_timeout_with_work_pending_says_false_and_does_not_raise(self):
        release = threading.Event()
        saved = tool_usage.settings.save_tool_usage
        tool_usage.settings.save_tool_usage = lambda _value: release.wait(10)
        try:
            async def one():
                tool_usage.note("web_search")

            asyncio.run(one())
            self.assertFalse(tool_usage.settle(0))
        finally:
            release.set()
            tool_usage.settle(10)
            tool_usage.settings.save_tool_usage = saved
        self.assertTrue(tool_usage.settle(0), "it was saved, so nothing is pending now")


class TheRealFileEndToEnd(WithATemporaryConfig):
    def test_calls_on_the_loop_reach_the_settings_file(self):
        async def calls():
            for name in ("web_search", "web_search", "reminder"):
                tool_usage.note(name)

        asyncio.run(calls())
        tool_usage.settle(10)
        stored = self.read_settings()["tool_usage"]
        self.assertEqual(stored["web_search"]["count"], 2)
        self.assertEqual(stored["reminder"]["count"], 1)

    def test_the_keys_the_owner_pasted_survive_it(self):
        self.write_settings({"gemini_api_key": "FIXTURE-KEY-keep-me"})

        async def calls():
            tool_usage.note("web_search")

        asyncio.run(calls())
        tool_usage.settle(10)
        stored = self.read_settings()
        self.assertEqual(stored["gemini_api_key"], "FIXTURE-KEY-keep-me")
        self.assertEqual(stored["tool_usage"]["web_search"]["count"], 1)

    def test_loop_calls_and_thread_calls_together_lose_nothing(self):
        done = threading.Event()

        def from_threads():
            for _ in range(15):
                tool_usage.note("web_search")
            done.set()

        runner = threading.Thread(target=from_threads)
        runner.start()

        async def on_loop():
            for _ in range(15):
                tool_usage.note("web_search")
                await asyncio.sleep(0)

        asyncio.run(on_loop())
        runner.join(30)
        tool_usage.settle(30)
        self.assertEqual(self.read_settings()["tool_usage"]["web_search"]["count"], 30)


class TheExit(unittest.TestCase):
    def test_a_normal_exit_saves_what_is_still_queued(self):
        # The writer is a daemon thread, so without the exit hook a write in flight when the
        # interpreter closes would be thrown away. The child exits with a 0.3 s write pending.
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "saved.json"
            script = textwrap.dedent(f"""
                import asyncio, json, sys, time
                sys.path.insert(0, {str(ROOT)!r})
                from core import tool_usage
                def save(value):
                    time.sleep(0.3)
                    open({str(target)!r}, "w").write(json.dumps(value))
                tool_usage.read = lambda: {{}}
                tool_usage.settings.save_tool_usage = save
                async def main():
                    tool_usage.note("exit_probe")
                asyncio.run(main())
                # the interpreter closes here, with the save still running
            """)
            done = subprocess.run([sys.executable, "-B", "-c", script], capture_output=True,
                                  text=True, timeout=60, cwd=folder)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertTrue(target.exists(), "the pending write was thrown away at exit")
            self.assertEqual(json.loads(target.read_text())["exit_probe"]["count"], 1)

    def test_a_stuck_disk_does_not_keep_the_program_open(self):
        script = textwrap.dedent(f"""
            import asyncio, sys, threading
            sys.path.insert(0, {str(ROOT)!r})
            from core import tool_usage
            tool_usage.read = lambda: {{}}
            tool_usage.settings.save_tool_usage = lambda value: threading.Event().wait()   # never returns
            async def main():
                tool_usage.note("stuck_probe")
            asyncio.run(main())
        """)
        started = time.perf_counter()
        done = subprocess.run([sys.executable, "-B", "-c", script], capture_output=True, text=True,
                              timeout=60, cwd=str(ROOT))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertLess(time.perf_counter() - started, 20, "the exit waited for a write that never ends")


class TheCallSiteIsUnchanged(unittest.TestCase):
    def test_main_still_calls_note_the_way_the_gate_looks_for(self):
        text = (ROOT / "main.py").read_text(encoding="utf-8", errors="replace")
        self.assertIn("tool_usage.note(name)", text)
        self.assertNotIn("await asyncio.to_thread(tool_usage.note", text,
                         "the proof gate greps for the plain call; moving it needs the gate changed too")


if __name__ == "__main__":
    unittest.main()
