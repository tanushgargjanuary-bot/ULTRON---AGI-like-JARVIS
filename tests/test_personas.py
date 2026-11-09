"""Tests for persona names, labels, and prompts."""

import unittest

from core.personas import PERSONAS, get_persona, persona_prompt


class PersonaTests(unittest.TestCase):
    def test_requested_display_names_and_labels_are_stable(self):
        self.assertEqual(
            {key: PERSONAS[key].name for key in PERSONAS},
            {
                "ultron": "Ultron",
                "teenager": "Nova",
                "hacker": "Cipher",
                "villain": "Vanta",
                "girly": "Luna",
            },
        )

    def test_every_persona_has_its_own_animation_pack(self):
        packs = [p.animation for p in PERSONAS.values()]
        self.assertEqual(len(packs), len(set(packs)))

    def test_unknown_persona_fails_safe_to_ultron(self):
        self.assertEqual(get_persona("not-a-persona").id, "ultron")

    def test_persona_prompt_keeps_capabilities_and_safety_unchanged(self):
        for persona_id in PERSONAS:
            prompt = persona_prompt(persona_id).lower()
            self.assertIn("same tools, capabilities", prompt)
            self.assertIn("safety limits", prompt)
            self.assertIn("approval requirements", prompt)

    def test_profiles_have_theme_and_supported_voice(self):
        allowed_voices = {"Charon", "Puck", "Kore", "Fenrir", "Aoede"}
        for persona in PERSONAS.values():
            self.assertTrue(persona.default_theme)
            self.assertIn(persona.voice, allowed_voices)


if __name__ == "__main__":
    unittest.main()
