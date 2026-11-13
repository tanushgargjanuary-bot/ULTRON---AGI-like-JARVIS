"""tests/test_skill_docs.py - the written skills are reachable and bounded.

The claim these tests defend is boring and important: a skill document under
`skills/` is now read by something. Before this module the folder was decoration
- four good files nobody loaded.

Also pinned:

- only `skills/<simple-name>/SKILL.md` is reachable, so a name cannot carry a
  path out of the folder;
- a document larger than the budget is truncated, never pasted whole;
- a broken document is reported, not raised.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from actions import skill_guide  # noqa: E402
from core import skill_docs  # noqa: E402


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)

    def tearDown(self):
        self.folder.cleanup()

    def test_frontmatter_is_read(self):
        write(self.root / "alpha" / "SKILL.md",
              "---\nname: alpha\ndescription: Use for the alpha case.\n---\n\nBody.\n")
        docs = skill_docs.index(self.root)
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].name, "alpha")
        self.assertEqual(docs[0].description, "Use for the alpha case.")

    def test_a_folder_without_a_document_is_skipped(self):
        (self.root / "empty").mkdir()
        self.assertEqual(skill_docs.index(self.root), [])

    def test_a_document_without_frontmatter_still_loads(self):
        write(self.root / "plain" / "SKILL.md", "# Plain skill\n\nDo the thing.\n")
        docs = skill_docs.index(self.root)
        self.assertEqual(docs[0].name, "plain")
        self.assertIn("Plain skill", docs[0].description)

    def test_an_unusable_folder_name_is_not_a_skill(self):
        write(self.root / "bad name" / "SKILL.md", "---\nname: bad\n---\nx\n")
        self.assertEqual(skill_docs.index(self.root), [])

    def test_problems_explains_a_folder_that_looks_like_a_skill(self):
        (self.root / "empty").mkdir()
        self.assertTrue(any("no SKILL.md" in row for row in skill_docs.problems(self.root)))


class ReadTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)

    def tearDown(self):
        self.folder.cleanup()

    def test_read_returns_the_document(self):
        write(self.root / "alpha" / "SKILL.md", "---\nname: alpha\n---\n\nBody text.\n")
        self.assertIn("Body text", skill_docs.read("alpha", self.root))

    def test_an_unknown_name_is_a_clear_error(self):
        with self.assertRaises(ValueError):
            skill_docs.read("nothing-here", self.root)

    def test_a_path_is_not_a_name(self):
        write(self.root / "alpha" / "SKILL.md", "---\nname: alpha\n---\nx\n")
        for attempt in ("../alpha", "alpha/SKILL.md", "C:\\alpha"):
            with self.assertRaises(ValueError):
                skill_docs.read(attempt, self.root)

    def test_a_long_document_is_truncated(self):
        body = "x" * (skill_docs.MAX_CHARS + 500)
        write(self.root / "long" / "SKILL.md", f"---\nname: long\n---\n{body}\n")
        text = skill_docs.read("long", self.root)
        self.assertLessEqual(len(text), skill_docs.MAX_CHARS + 60)
        self.assertIn("truncated", text)

    def test_brief_is_one_line_per_skill(self):
        write(self.root / "alpha" / "SKILL.md", "---\nname: alpha\ndescription: A.\n---\nx\n")
        write(self.root / "beta" / "SKILL.md", "---\nname: beta\ndescription: B.\n---\nx\n")
        lines = skill_docs.brief(root=self.root).splitlines()
        self.assertEqual(lines, ["alpha: A.", "beta: B."])


class InstalledSkillsTests(unittest.TestCase):
    def test_the_repository_skills_are_loadable(self):
        docs = {doc.name for doc in skill_docs.index()}
        self.assertIn("computer-use", docs)
        self.assertIn("background-awareness", docs)
        self.assertIn("security-review", docs)

    def test_no_installed_document_breaks_the_index(self):
        self.assertEqual(skill_docs.problems(), [])


class GuideActionTests(unittest.TestCase):
    def test_list_names_every_installed_skill(self):
        answer = skill_guide.skill_guide({"action": "list"})
        self.assertIn("computer-use", answer)
        self.assertIn("security-review", answer)

    def test_read_returns_the_named_document(self):
        answer = skill_guide.skill_guide({"action": "read", "skill": "computer-use"})
        self.assertIn("Computer use", answer)

    def test_read_without_a_name_asks_for_one(self):
        self.assertIn("Which skill", skill_guide.skill_guide({"action": "read"}))

    def test_the_declaration_matches_the_handler(self):
        tool = skill_guide.TOOL
        self.assertEqual(tool["name"], "skill_guide")
        self.assertIs(tool["handler"], skill_guide.skill_guide)
        self.assertEqual(set(tool["parameters"]["properties"]), {"action", "skill"})


if __name__ == "__main__":
    unittest.main()
