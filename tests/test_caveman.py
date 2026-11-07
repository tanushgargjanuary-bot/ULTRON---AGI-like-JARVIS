"""tests/test_caveman.py — Tests for deterministic token-saving plugin caveman."""

from __future__ import annotations

import unittest
from plugins import caveman


class TestCavemanPlugin(unittest.TestCase):
    def test_explain_action(self):
        res = caveman.run({"action": "explain"})
        self.assertIn("Caveman drops filler words", res)

    def test_estimate_action(self):
        res = caveman.run({"action": "estimate", "text": "This is a quick sentence for testing."})
        self.assertIn("characters", res)
        self.assertIn("tokens", res)

    def test_compress_action(self):
        sample = "Basically, in order to make it work, it is important to honestly test it."
        res = caveman.run({"action": "compress", "text": sample})
        self.assertIn("tokens down to", res)

    def test_compress_empty(self):
        res = caveman.run({"action": "compress", "text": ""})
        self.assertEqual(res, "There is nothing to compress.")


if __name__ == "__main__":
    unittest.main()

