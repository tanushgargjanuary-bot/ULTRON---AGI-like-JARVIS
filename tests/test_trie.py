"""tests/test_trie.py — prefix completion, including the awkward cases."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.trie import Trie


class BasicsTests(unittest.TestCase):
    def test_insert_and_contains(self):
        trie = Trie(["chrome", "chromium", "chromecast"])
        self.assertEqual(len(trie), 3)
        self.assertIn("chrome", trie)
        self.assertNotIn("chrom", trie)
        self.assertNotIn("chromium browser", trie)

    def test_reinsert_keeps_the_highest_weight(self):
        trie = Trie()
        trie.insert("whatsapp", 1.0)
        trie.insert("whatsapp", 9.0)
        trie.insert("whatsapp", 2.0)
        self.assertEqual(len(trie), 1)
        self.assertEqual(dict(trie.complete("what"))["whatsapp"], 9.0)

    def test_empty_key_is_ignored(self):
        trie = Trie(["", "x"])
        self.assertEqual(len(trie), 1)

    def test_duplicate_keys_count_once(self):
        trie = Trie(["a", "a", "a"])
        self.assertEqual(len(trie), 1)


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.trie = Trie([("chrome", 3.0), ("chromium", 1.0), ("chromecast", 2.0), ("firefox", 5.0)])

    def test_prefix_returns_the_subtree(self):
        self.assertEqual(
            [key for key, _ in self.trie.complete("chrom")],
            ["chrome", "chromecast", "chromium"],
        )

    def test_ordering_is_weight_then_alphabet(self):
        results = self.trie.complete("chrom")
        self.assertEqual(results[0][0], "chrome")          # 3.0
        self.assertEqual(results[1][0], "chromecast")      # 2.0
        self.assertEqual(results[2][0], "chromium")        # 1.0

    def test_limit_bounds_the_work_not_just_the_output(self):
        self.assertEqual(len(self.trie.complete("chrom", limit=2)), 2)
        self.assertEqual(self.trie.complete("chrom", limit=0), [])

    def test_unknown_prefix_is_empty(self):
        self.assertEqual(self.trie.complete("zzz"), [])
        self.assertEqual(self.trie.complete(""), sorted(
            ((key, weight) for key, weight in self.trie.complete("")),
            key=lambda pair: (-pair[1], pair[0]),
        ))

    def test_longest_prefix(self):
        trie = Trie(["chro", "chrome", "chromium"])
        self.assertEqual(trie.longest_prefix("chromex"), "chrome")
        self.assertEqual(trie.longest_prefix("chromi"), "chro")   # chromium is not a prefix
        self.assertEqual(trie.longest_prefix("zzz"), "")

    def test_keys_enumerates_everything_once(self):
        self.assertEqual(sorted(self.trie.keys()), ["chrome", "chromecast", "chromium", "firefox"])


class RobustnessTests(unittest.TestCase):
    def test_deep_keys_do_not_recurse(self):
        """A recursive traversal takes the app down on one long path."""
        deep = "p/" * 4000 + "file.txt"
        trie = Trie([deep])
        self.assertIn(deep, trie)
        self.assertEqual(trie.complete("p/" * 3999, limit=1)[0][0], deep)

    def test_unicode_keys(self):
        trie = Trie(["café", "cafe"])
        self.assertEqual({key for key, _ in trie.complete("caf")}, {"café", "cafe"})

    def test_scale(self):
        keys = [f"tool_{i:05d}" for i in range(5000)]
        trie = Trie(keys)
        self.assertEqual(len(trie), 5000)
        self.assertEqual(len(trie.complete("tool_0499", limit=10)), 10)


if __name__ == "__main__":
    unittest.main()
