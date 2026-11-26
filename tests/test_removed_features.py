"""What the owner took out stays out.

2026-11-26, the owner: "I did meant the webapp. Remove the dashboard for phone and web remote."

A removal that is only a deleted folder comes back by accident: a merge from upstream, an old branch, a
document that still says to run it, a workflow that still builds it. Each removal gets one class here, red while
the folder or anything that points at it is still in the tree. Bringing a feature back is a decision: revert the
merge that removed it (DECISIONS.md names the merge), and that revert takes the class below out with it.
"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def text_of(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


class TheWebClientIsGone(unittest.TestCase):
    """`webapp/`: a Next.js sign-in page with a chat box that was switched off, never connected to Ultron."""

    def test_the_folder_is_gone(self):
        self.assertFalse((ROOT / "webapp").exists(),
                         "webapp/ was removed at the owner's request; revert the removal to get it back")

    def test_no_workflow_is_left_that_builds_it(self):
        self.assertFalse((WORKFLOWS / "webapp.yml").exists())
        for path in sorted(WORKFLOWS.glob("*.yml")):
            with self.subTest(workflow=path.name):
                self.assertNotIn("webapp", text_of(path))

    def test_dependabot_is_not_told_to_watch_it(self):
        text = text_of(ROOT / ".github" / "dependabot.yml")
        self.assertNotIn('package-ecosystem: "npm"', text)
        self.assertNotIn("webapp", text)

    def test_the_attributes_file_does_not_name_it(self):
        self.assertNotIn("webapp", text_of(ROOT / ".gitattributes"))


if __name__ == "__main__":
    unittest.main()
