"""Tests that prior conversation is carried into a new session."""

import unittest

from core.conversation_context import carryover_block


class CarryoverTests(unittest.TestCase):
    def test_empty_history_is_empty(self):
        self.assertEqual(carryover_block([]), "")

    def test_keeps_recent_lines_in_order(self):
        block = carryover_block(["User: first", "Nova: second", "User: third"])
        self.assertLess(block.index("User: first"), block.index("Nova: second"))
        self.assertLess(block.index("Nova: second"), block.index("User: third"))

    def test_truncates_only_the_prompt_copy_and_marks_it(self):
        turns = [f"turn {index} " + "x" * 100 for index in range(20)]
        block = carryover_block(turns, limit=500)
        self.assertIn("Earlier transcript lines are still retained", block)
        self.assertIn("turn 19", block)
        self.assertNotIn("turn 0 ", block)
        self.assertEqual(len(turns), 20)

    def test_oversized_single_line_is_clipped_to_budget(self):
        block = carryover_block(["x" * 1000], limit=300)
        self.assertLessEqual(len(block), 600)
        self.assertTrue(block.endswith("x" * 100))


if __name__ == "__main__":
    unittest.main()
