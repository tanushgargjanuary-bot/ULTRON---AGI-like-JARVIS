"""Computer-control failures are recorded without running real desktop actions."""

import unittest
from unittest.mock import patch

from actions import computer_control


class ComputerCapabilityTests(unittest.TestCase):
    def test_control_error_is_reported_to_health_instrumentation(self):
        with patch.object(computer_control, "_click", side_effect=RuntimeError("simulated driver failure")), \
             patch.object(computer_control.failures, "note") as note:
            result = computer_control.computer_control({"action": "click", "x": 1, "y": 2})
        self.assertIn("failed", result)
        note.assert_called_once()
        args, _kwargs = note.call_args
        self.assertEqual(args[0], "computer_control.click")
        self.assertIsInstance(args[1], RuntimeError)


if __name__ == "__main__":
    unittest.main()
