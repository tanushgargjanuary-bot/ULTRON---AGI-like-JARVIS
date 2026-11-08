"""The HUD line reports a policy tier and a tool's own outcome, without guessing."""

import unittest

from core.action_audit import after_action


class ActionAuditTests(unittest.TestCase):
    def test_read_only_tools_do_not_add_activity_noise(self):
        self.assertEqual(after_action("web_search", {}, "results"), "")

    def test_routine_action_reports_the_tool_status(self):
        line = after_action("open_app", {}, "status=done action=open_app verified=true")
        self.assertIn("risk=routine", line)
        self.assertIn("outcome=done", line)

    def test_sensor_action_reports_its_risk_tier(self):
        line = after_action("screen_process", {}, "status=unverified action=screen_process")
        self.assertIn("risk=sensor", line)
        self.assertIn("outcome=unverified", line)

    def test_unknown_action_fails_closed_in_the_audit_line(self):
        line = after_action("new_unclassified_tool", {}, "plain result")
        self.assertIn("risk=guarded", line)
        self.assertIn("outcome=unlabelled", line)

    def test_result_contents_and_arguments_are_not_logged(self):
        line = after_action("send_message", {"body": "private"},
                            "status=done action=send_message body=private")
        self.assertNotIn("private", line)
        self.assertIn("risk=guarded", line)


if __name__ == "__main__":
    unittest.main()
