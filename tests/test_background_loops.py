"""The daily digest and the process watcher must not depend on the dashboard starting.

`JarvisLive.run` started four long-lived loops inside ONE `try:` whose `except` says
"[Dashboard] Disabled". Two of the four (`_digest_loop`, `_process_watch_loop`) have nothing
to do with the dashboard, so a machine where `DashboardServer()` could not be built (a
missing package is enough; before this change a missing `python-multipart` was enough) lost
the digest and the "your background job finished" announcement, and was told only that the
dashboard was off.

`main.py` imports `sounddevice` at module level, so these checks read the source instead of
importing it; they run on a machine with no audio library.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "main.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def method(name: str) -> ast.AST:
    for node in ast.walk(TREE):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"main.py has no {name}")


def called_names(node: ast.AST):
    """The name of every coroutine function handed to `create_task` inside `node`."""
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            function = child.func
            started = getattr(function, "attr", getattr(function, "id", ""))
            if started == "create_task" and child.args:
                inner = child.args[0]
                if isinstance(inner, ast.Call):
                    target = inner.func
                    yield getattr(target, "attr", getattr(target, "id", ""))


def dashboard_try() -> ast.Try:
    for node in ast.walk(method("run")):
        if isinstance(node, ast.Try) and any(
                isinstance(n, ast.Name) and n.id == "DashboardServer" for n in ast.walk(node)):
            return node
    raise AssertionError("the try block that builds the dashboard was not found")


class LoopsAreIndependentOfTheDashboard(unittest.TestCase):
    def test_the_digest_and_the_watcher_are_started_outside_the_dashboards_try(self):
        inside = set(called_names(dashboard_try()))
        self.assertNotIn("_digest_loop", inside)
        self.assertNotIn("_process_watch_loop", inside)

    def test_they_are_started_at_all(self):
        started = set(called_names(method("run")))
        self.assertIn("_digest_loop", started)
        self.assertIn("_process_watch_loop", started)

    def test_the_dashboard_only_loops_stay_inside_it(self):
        inside = set(called_names(dashboard_try()))
        self.assertIn("serve", inside)
        self.assertIn("_process_dashboard_commands", inside)

    def test_each_long_lived_loop_is_created_inside_a_hold_call(self):
        # `asyncio.create_task(x)` as a bare statement drops the only strong reference to the
        # task. Each of the four must be the argument of `self._hold(...)`.
        held = set()
        for node in ast.walk(method("run")):
            if (isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "_hold"
                    and node.args):
                held.update(called_names(node.args[0]))
        for loop in ("serve", "_process_dashboard_commands", "_digest_loop", "_process_watch_loop"):
            with self.subTest(loop=loop):
                self.assertIn(loop, held, f"{loop} is started without being held")

    def test_the_text_the_proof_gate_and_the_watch_tests_look_for_is_still_there(self):
        # scripts/proof_gate.py (claim `procwatch`) and tests/test_process_watch.py read
        # main.py for this exact line; the helper was shaped so that it stays.
        self.assertIn("asyncio.create_task(self._process_watch_loop())", SOURCE)

    def test_main_delegates_to_the_shared_helper(self):
        body = ast.get_source_segment(SOURCE, method("_hold"))
        self.assertIn("core.background_tasks", body)
        self.assertIn("_background_tasks", body)

    def test_hold_keeps_the_task_and_notes_a_failure(self):
        import asyncio
        from unittest import mock

        from core import background_tasks, failures

        noted = []

        async def boom():
            raise RuntimeError("loop died")

        async def scenario():
            held = set()
            with mock.patch.object(failures, "note",
                                   lambda where, error, **kw: noted.append((where, error))):
                task = asyncio.create_task(boom())
                background_tasks.hold(held, task, "demo")
                self.assertIn(task, held, "the task is referenced from the moment it is held")
                self.assertEqual(task.get_name(), "demo")
                await asyncio.gather(task, return_exceptions=True)
                await asyncio.sleep(0)
            return held

        held = asyncio.run(scenario())
        self.assertEqual(held, set(), "a finished task is let go")
        self.assertEqual(len(noted), 1)
        self.assertIn("demo", noted[0][0])
        self.assertIsInstance(noted[0][1], RuntimeError)

    def test_a_cancelled_loop_is_not_reported_as_a_failure(self):
        import asyncio
        from unittest import mock

        from core import background_tasks, failures

        noted = []

        async def forever():
            await asyncio.sleep(3600)

        async def scenario():
            held = set()
            with mock.patch.object(failures, "note",
                                   lambda where, error, **kw: noted.append(where)):
                task = background_tasks.hold(held, asyncio.create_task(forever()), "demo")
                await asyncio.sleep(0)
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                await asyncio.sleep(0)
            return held

        self.assertEqual(asyncio.run(scenario()), set())
        self.assertEqual(noted, [])

    def test_the_default_assistant_name_is_not_corrupted(self):
        self.assertNotIn("JARVI    S", SOURCE)


if __name__ == "__main__":
    unittest.main()
