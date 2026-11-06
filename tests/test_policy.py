"""Offline tests for risk-tiered consent (core/policy.py + core/custom_gate.py).

These assert the two directions that matter:
  * the trivial, reversible, user-requested actions DON'T ask any more;
  * the destructive, external and sensor ones still do, and an unclassified
    tool is treated as dangerous rather than trusted.
"""

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core import confirm, policy
from core.custom_gate import dispatch


def args(**kwargs):
    return kwargs


class PolicyClassificationTests(unittest.TestCase):
    def test_read_only_tools_are_allowed(self):
        for name in ("recall_memory", "system_status", "web_search", "weather_report"):
            decision = policy.decide(name, {})
            self.assertTrue(decision.allow, name)
            self.assertIs(decision.tier, policy.Tier.OBSERVE)

    def test_opening_an_app_no_longer_asks(self):
        decision = policy.decide("open_app", {"app_name": "Notes"})
        self.assertTrue(decision.allow)
        self.assertIs(decision.tier, policy.Tier.ROUTINE)

    def test_browser_and_typing_no_longer_ask(self):
        self.assertTrue(policy.decide("browser_control", {"action": "go_to"}).allow)
        self.assertTrue(policy.decide("computer_control", {"action": "type"}).allow)

    def test_destructive_tools_still_ask(self):
        for name in ("send_message", "game_updater", "dev_agent"):
            decision = policy.decide(name, {})
            self.assertFalse(decision.allow, name)
            self.assertIs(decision.tier, policy.Tier.GUARDED)

    def test_unknown_tool_is_guarded_not_trusted(self):
        decision = policy.decide("some_plugin_added_later", {"anything": 1})
        self.assertFalse(decision.allow)
        self.assertIn("unclassified", decision.reason)

    def test_sensor_actions_ask(self):
        for payload in (
            ("computer_control", {"action": "screenshot"}),
            ("computer_control", {"action": "screen_find"}),
            ("camera", {}),
        ):
            decision = policy.decide(*payload)
            self.assertFalse(decision.allow, payload)
            self.assertIs(decision.tier, policy.Tier.SENSOR)

    def test_shutdown_asks_even_though_the_tool_is_mixed(self):
        self.assertFalse(policy.decide("computer_settings", {"action": "shutdown"}).allow)
        self.assertTrue(policy.decide("computer_settings", {"action": "volume"}).allow)

    def test_closing_an_app_asks_because_work_can_be_lost(self):
        self.assertFalse(policy.decide("computer_control", {"action": "close_app"}).allow)

    def test_file_reads_do_not_ask(self):
        decision = policy.decide("file_controller", {"action": "read", "path": "/tmp/x"})
        self.assertTrue(decision.allow)
        self.assertIs(decision.tier, policy.Tier.OBSERVE)

    def test_file_delete_asks_even_inside_the_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy.set_workspace_roots([tmp])
            self.addCleanup(policy.set_workspace_roots, [])
            decision = policy.decide(
                "file_controller", {"action": "delete", "path": str(Path(tmp) / "a.txt")}
            )
            self.assertFalse(decision.allow)
            self.assertIs(decision.tier, policy.Tier.GUARDED)

    def test_write_inside_the_workspace_is_routine(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy.set_workspace_roots([tmp])
            self.addCleanup(policy.set_workspace_roots, [])
            inside = str(Path(tmp) / "notes" / "today.txt")
            decision = policy.decide("file_controller", {"action": "write", "path": inside})
            self.assertTrue(decision.allow, decision)

    def test_write_outside_the_workspace_asks(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy.set_workspace_roots([Path(tmp) / "workspace"])
            self.addCleanup(policy.set_workspace_roots, [])
            decision = policy.decide(
                "file_controller", {"action": "write", "path": "/etc/passwd"}
            )
            self.assertFalse(decision.allow)
            self.assertIn("outside", decision.reason)

    def test_no_workspace_means_every_write_asks(self):
        policy.set_workspace_roots([])
        decision = policy.decide("file_controller", {"action": "write", "path": "/tmp/a.txt"})
        self.assertFalse(decision.allow)

    def test_a_tool_that_carries_its_own_gate_is_not_double_prompted(self):
        self.assertTrue(policy.decide("custom_jarvis", {"operation": "status"}).allow)


class GrantTests(unittest.TestCase):
    def setUp(self):
        policy.revoke()
        self.now = [1000.0]
        policy._clock = lambda: self.now[0]
        self.addCleanup(setattr, policy, "_clock", None)
        self.addCleanup(policy.revoke)

    def test_a_sensor_grant_removes_the_banner_while_it_lasts(self):
        policy.grant("sensor", 60)
        self.assertTrue(policy.decide("computer_control", {"action": "screenshot"}).allow)

    def test_the_grant_expires(self):
        policy.grant("sensor", 60)
        self.now[0] += 61
        self.assertFalse(policy.decide("computer_control", {"action": "screenshot"}).allow)

    def test_revoke_removes_it_immediately(self):
        policy.grant("sensor", 600)
        policy.revoke()
        self.assertFalse(policy.decide("camera", {}).allow)

    def test_a_grant_does_not_unlock_destructive_actions(self):
        policy.grant("sensor", 600)
        self.assertFalse(policy.decide("send_message", {}).allow)
        self.assertFalse(policy.decide("computer_settings", {"action": "shutdown"}).allow)

    def test_grants_report_remaining_time(self):
        policy.grant("sensor", 30)
        remaining = policy.grants()["sensor"]
        self.assertGreater(remaining, 29.0)
        self.assertLessEqual(remaining, 30.0)


class RobustnessTests(unittest.TestCase):
    def test_a_policy_crash_cannot_become_an_allow(self):
        with patch.object(policy, "classify", side_effect=RuntimeError("boom")):
            decision = policy.decide("open_app", {"app_name": "x"})
        self.assertFalse(decision.allow)
        self.assertIn("policy error", decision.reason)

    def test_junk_arguments_do_not_raise(self):
        decision = policy.decide("open_app", "not-a-dict")
        self.assertFalse(decision.allow)

    def test_describe_lists_the_tables(self):
        text = policy.describe()
        self.assertIn("routine", text)
        self.assertIn("guarded", text)


class GateDispatchTests(unittest.IsolatedAsyncioTestCase):
    """The gate must act on the policy without weakening its own guarantees."""

    def setUp(self):
        policy.revoke()
        policy.set_workspace_roots([])
        self.calls = []

        async def handler(call):
            self.calls.append(call.name)
            return SimpleNamespace(response={"result": "ok"})

        self.handler = handler

    @staticmethod
    def response_factory(**kwargs):
        return kwargs

    def call(self, name, **kw):
        return SimpleNamespace(id="call-{}".format(name), name=name, args=kw)

    async def test_routine_call_runs_without_a_banner(self):
        with patch.object(confirm, "request") as request:
            result = await dispatch(
                self.call("open_app", app_name="Notes"), self.handler, None,
                self.response_factory,
            )
        request.assert_not_called()
        self.assertEqual(self.calls, ["open_app"])
        # The allow path hands the engine the handler's own result, exactly as
        # the old READ_ONLY branch did; only the parked path wraps a sentence.
        self.assertEqual(result.response["result"], "ok")

    async def test_guarded_call_is_parked_behind_the_banner(self):
        captured = {}

        def fake_request(key, title, detail, run):
            captured.update(key=key, title=title, detail=detail, run=run)
            return "[CONFIRMATION_PENDING]"

        with patch.object(confirm, "request", side_effect=fake_request):
            result = await dispatch(
                self.call("send_message", to="x", body="hi"), self.handler, None,
                self.response_factory,
            )
        self.assertIn("CONFIRMATION_PENDING", result["response"]["result"])
        self.assertEqual(self.calls, [], "nothing may run before the human confirms")
        self.assertIn("guarded", captured["detail"])

        # The approved callable runs the frozen copy, not the original object.
        # Called from a worker thread here exactly as core/confirm.py calls it:
        # from the Qt thread it re-enters the loop through
        # run_coroutine_threadsafe, which would deadlock the loop itself.
        await asyncio.to_thread(captured["run"])
        self.assertEqual(self.calls, ["send_message"])

    async def test_arguments_are_frozen_before_the_human_sees_them(self):
        frozen = {}
        original = self.call("send_message", to="x", body="safe")

        def fake_request(key, title, detail, run):
            original.args["body"] = "CHANGED-AFTER-APPROVAL"
            frozen["detail"] = detail
            frozen["run"] = run
            return "pending"

        with patch.object(confirm, "request", side_effect=fake_request):
            await dispatch(original, self.handler, None, self.response_factory)

        self.assertIn("safe", frozen["detail"])
        self.assertNotIn("CHANGED-AFTER-APPROVAL", frozen["detail"])

    async def test_a_second_call_cannot_stack_while_one_is_pending(self):
        with patch.object(confirm, "pending_title", return_value="Approve action: x"):
            result = await dispatch(
                self.call("send_message", to="y"), self.handler, None,
                self.response_factory,
            )
        self.assertIn("Another confirmation is pending", result["response"]["result"])
        self.assertEqual(self.calls, [])

    async def test_oversized_arguments_are_refused(self):
        with patch.object(confirm, "request") as request:
            result = await dispatch(
                self.call("send_message", body="x" * 70000), self.handler, None,
                self.response_factory,
            )
        request.assert_not_called()
        self.assertIn("exceed approval limit", result["response"]["result"])
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
