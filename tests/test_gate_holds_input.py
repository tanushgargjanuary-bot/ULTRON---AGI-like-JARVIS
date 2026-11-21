"""While the owner is being asked something, nothing but a read runs.

A confirmation banner is a button. A button is pressed by a click, by a key press, or by a typed
space once it has the focus, and `computer_control` sends all three and is a routine tool, which
runs with no banner of its own. So a model that wanted a banner answered could send the answer
itself, two calls long (`press tab`, `press space`), and every sentence that said "only a person can
press it" rested on the model not trying.

`core/custom_gate.dispatch` now refuses a call that would otherwise run, unless it is read-only,
for as long as a confirmation is waiting. These tests drive the real dispatcher with a real
(unanswered) confirmation and a handler that records whether it was ever awaited.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import confirm, custom_gate, policy  # noqa: E402
from core.confirm import request as put_up_a_banner  # noqa: E402


class WhileAConfirmationWaits(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        confirm.resolve(False)
        confirm.bind(MagicMock(), MagicMock())
        self.player = MagicMock()
        self.handler = AsyncMock(return_value=SimpleNamespace(response={"result": "ran"}))
        put_up_a_banner("question", "Change my own code", "every changed line", lambda: "done")
        self.addCleanup(self._tidy)

    @staticmethod
    def _tidy():
        confirm.resolve(False)
        confirm.bind(None, None)

    async def call(self, name: str, **args):
        fc = SimpleNamespace(name=name, id="one", args=args)
        return await custom_gate.dispatch(fc, self.handler, self.player, SimpleNamespace)

    def assertRoutine(self, name: str, **args):
        """The precondition: without a waiting confirmation this call would run with no banner."""
        decision = policy.decide(name, args)
        self.assertTrue(decision.allow, f"{name} {args} is not allowed to run unasked: {decision}")
        self.assertIsNot(decision.tier, policy.Tier.OBSERVE)

    async def test_the_two_calls_that_would_press_the_button_do_not_run(self):
        self.assertRoutine("computer_control", action="press", key="tab")
        self.assertRoutine("computer_control", action="press", key="space")
        for key in ("tab", "space", "enter"):
            result = await self.call("computer_control", action="press", key=key)
            self.assertIn("confirmation is waiting", result.response["result"])
        self.handler.assert_not_awaited()
        self.assertEqual(confirm.pending_title(), "Change my own code", "nothing answered it")

    async def test_a_click_and_a_typed_space_do_not_run_either(self):
        self.assertRoutine("computer_control", action="click", x=10, y=10)
        self.assertRoutine("computer_control", action="type", text=" ")
        await self.call("computer_control", action="click", x=10, y=10)
        await self.call("computer_control", action="type", text=" ")
        self.handler.assert_not_awaited()

    async def test_the_refusal_names_the_call_and_what_to_do(self):
        result = await self.call("computer_control", action="press", key="tab")
        said = result.response["result"]
        self.assertIn("computer_control", said)
        self.assertIn("Change my own code", said)
        self.assertIn("answer it first", said)

    async def test_a_read_still_runs(self):
        decision = policy.decide("system_status", {})
        self.assertIs(decision.tier, policy.Tier.OBSERVE)
        await self.call("system_status")
        self.handler.assert_awaited_once()

    async def test_the_tool_that_carries_its_own_gate_is_held_too(self):
        await self.call("system_prompt", action="confirm", proposal="p1")
        self.handler.assert_not_awaited()

    async def test_a_guarded_call_is_still_told_another_confirmation_is_pending(self):
        result = await self.call("some_unknown_plugin", content="x")
        self.assertIn("Another confirmation", result.response["result"])
        self.assertEqual(confirm.pending_title(), "Change my own code")
        self.handler.assert_not_awaited()

    async def test_after_the_answer_the_same_call_runs(self):
        confirm.resolve(False)
        await self.call("computer_control", action="press", key="tab")
        self.handler.assert_awaited_once()

    async def test_a_title_with_a_hidden_character_is_written_out_in_the_refusal(self):
        confirm.resolve(False)
        put_up_a_banner("q2", "Shut down\u202e?", "", lambda: "done")
        result = await self.call("computer_control", action="press", key="tab")
        self.assertNotIn("\u202e", result.response["result"])
        self.assertIn("\\u202e", result.response["result"])


class WithNothingWaiting(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        confirm.resolve(False)
        confirm.bind(MagicMock(), MagicMock())
        self.addCleanup(lambda: (confirm.resolve(False), confirm.bind(None, None)))

    async def test_a_routine_call_runs_as_it_always_did(self):
        handler = AsyncMock(return_value=SimpleNamespace(response={"result": "ran"}))
        fc = SimpleNamespace(name="computer_control", id="one", args={"action": "press", "key": "tab"})
        await custom_gate.dispatch(fc, handler, MagicMock(), SimpleNamespace)
        handler.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
