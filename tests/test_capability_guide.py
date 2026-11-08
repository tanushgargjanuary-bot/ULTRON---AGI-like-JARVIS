"""Routing checks for the capability guide.

These arrived from the ``chatgpt`` branch as pytest-style functions — bare ``assert`` plus a
``monkeypatch`` fixture. This repository runs ``unittest discover``, so that file collected
*zero* tests and its five passing checks never ran in CI. Same checks, same wording, now in a
shape the suite can actually execute.
"""

import unittest
from types import SimpleNamespace

from actions import capability_guide as guide


def _entry(name, category, summary, available=True, reason=""):
    return SimpleNamespace(
        name=name, category=category, summary=summary,
        available=available, reason=reason,
    )


def _skill(identity, title, purpose):
    return SimpleNamespace(identity=identity, title=title, purpose=purpose)


class CapabilityGuideRouting(unittest.TestCase):
    """A phrase must find the tool, refuse to guess, and name a gap out loud."""

    def setUp(self):
        self._real_build = guide.tool_catalog.build
        self._real_skills = guide.SKILLS

    def tearDown(self):
        guide.tool_catalog.build = self._real_build
        guide.SKILLS = self._real_skills

    def _run(self, request, entries, skills=()):
        guide.tool_catalog.build = lambda: entries
        guide.SKILLS = list(skills)
        return guide.run({"request": request})

    def test_indirect_compression_request_finds_file_processor(self):
        result = self._run(
            "This file is too large to send; can you make it smaller?",
            [_entry("file_processor", "files", "Processes uploaded files.", True)],
        )
        self.assertIn("file_processor (ready)", result)

    def test_review_wording_matches_skill_identifier(self):
        result = self._run(
            "Review my workspace changes",
            [],
            [_skill("review_changes", "Review change footprint", "Inspect status and diff.")],
        )
        self.assertIn("Review change footprint [review_changes]", result)

    def test_generic_file_request_does_not_guess_a_tool(self):
        result = self._run(
            "Help with this file",
            [_entry("file_processor", "files", "Processes uploaded files.", True)],
        )
        self.assertIn("No strong tool match", result)

    def test_unavailable_tool_is_reported_and_gap_is_explicit(self):
        result = self._run(
            "Compress this file",
            [_entry("file_processor", "files", "Processes uploaded files.", False, "missing codec")],
        )
        self.assertIn("unavailable: missing codec", result)
        self.assertIn("research candidate GitHub projects", result)

    def test_desktop_click_request_routes_to_computer_controls(self):
        result = self._run(
            "Click the button in the desktop window",
            [_entry("computer_control", "system", "Direct computer control for keyboard, mouse, and screen actions."),
             _entry("browser_control", "system", "Control a browser page.")],
        )
        self.assertIn("computer_control (ready)", result)

    def test_read_public_webpage_routes_to_bounded_web_reader(self):
        result = self._run(
            "Scrape the public webpage and extract the article",
            [_entry("web_read", "knowledge", "Read and extract text from a public web page.", True)],
        )
        self.assertIn("web_read (ready)", result)

    def test_unknown_task_offers_research_without_claiming_a_tool(self):
        result = self._run(
            "Teleport a person to Mars",
            [_entry("file_processor", "files", "Processes uploaded files.", True)],
        )
        self.assertIn("No strong tool match", result)
        self.assertIn("research candidate GitHub projects", result)


if __name__ == "__main__":
    unittest.main()
