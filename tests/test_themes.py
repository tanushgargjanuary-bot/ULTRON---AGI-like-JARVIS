"""Named HUD theme presets remain deterministic and separate from custom colours."""

import unittest

from core import themes


class ThemePresetTests(unittest.TestCase):
    def test_holographic_preset_is_named_and_distinct(self):
        holo = themes.theme("HOLOGRAPHIC")
        classic = themes.theme("classic_cyan")
        self.assertEqual(holo["label"], "Holographic")
        self.assertNotEqual(holo["accent"], classic["accent"])
        self.assertIn("hologram", holo["description"].lower())

    def test_unknown_preset_fails_closed(self):
        self.assertIsNone(themes.theme("not-a-theme"))

    def test_color_mapping_returns_preset_or_custom(self):
        self.assertEqual(themes.theme_id_for_color("#22f5d8"), "holographic")
        self.assertEqual(themes.theme_id_for_color("#123456"), "custom")


if __name__ == "__main__":
    unittest.main()
