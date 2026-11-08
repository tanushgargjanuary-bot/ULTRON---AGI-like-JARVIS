"""Malformed model arguments must fail closed rather than crash video playback."""

from __future__ import annotations

import unittest

from actions.video_player import video_player
from core import failures


class VideoPlayerArgumentTests(unittest.TestCase):
    def setUp(self):
        failures.clear()

    def tearDown(self):
        failures.clear()

    def test_non_text_action_is_reported_and_refused(self):
        result = video_player({"action": ["not", "a", "string"]}, player=object())
        self.assertIn("plain text", result)
        self.assertEqual(failures.recent()[-1]["where"], "video_player.arguments")

    def test_non_text_source_is_reported_and_refused(self):
        result = video_player({"source": {"url": "https://example.invalid"}}, player=object())
        self.assertIn("plain text", result)
        self.assertEqual(failures.recent()[-1]["where"], "video_player.arguments")

    def test_a_missing_action_and_source_still_uses_existing_prompt(self):
        self.assertEqual(video_player({}, player=object()), "What should I play?")


if __name__ == "__main__":
    unittest.main()
