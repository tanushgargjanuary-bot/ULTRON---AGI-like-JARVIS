"""tests/test_readme.py — the front page must not claim anything the tree lacks.

The owner asked, twice, for proof that nothing in `readme.md` was invented. A
promise that it was checked is worth less than a test that checks it, so this is
the test. It reads the page a stranger reads first and asks the only question
this project keeps asking: what does this sentence make the program say, and what
proves it?

What is asserted:
    * every path the page names exists in the repository;
    * every relative link points at a real file;
    * the animated picture exists, is a real GIF, and is small enough to load;
    * the counts the page quotes are the counts in the tree;
    * the licence credit is present, because the licence requires it.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "readme.md"


def readme_text() -> str:
    return README.read_text(encoding="utf-8")


class PathsOnTheFrontPage(unittest.TestCase):
    def setUp(self):
        self.text = readme_text()

    def test_every_backticked_file_path_exists(self):
        pattern = re.compile(r"`([\w./-]+\.(?:py|md|json|txt|yml|bat|ps1|gif|so|c))`")
        missing = sorted({hit for hit in pattern.findall(self.text)
                          if "/" in hit and not (ROOT / hit).exists()})
        self.assertEqual(missing, [], f"the readme names files that do not exist: {missing}")

    def test_every_relative_link_points_at_something(self):
        links = re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", self.text)
        missing = []
        for link in links:
            if link.startswith(("http://", "https://", "mailto:")):
                continue
            if not (ROOT / link).exists():
                missing.append(link)
        self.assertEqual(missing, [], f"broken links: {missing}")

    def test_the_picture_is_a_small_gif(self):
        picture = ROOT / "docs" / "img" / "hud-states.gif"
        self.assertTrue(picture.exists(), "the readme shows a picture that does not exist")
        data = picture.read_bytes()[:6]
        self.assertIn(data, (b"GIF87a", b"GIF89a"), "the picture is not a GIF")
        self.assertLess(picture.stat().st_size, 400_000,
                        "the picture is too big to load quickly on a phone")

    def test_the_picture_is_captioned_as_an_illustration(self):
        """It is drawn, not photographed. Saying so is the honest part."""
        self.assertIn("illustration", self.text.lower())


class NumbersOnTheFrontPage(unittest.TestCase):
    """A number in a document must come from the tree, or it does not go in."""

    def setUp(self):
        self.text = readme_text()

    def test_the_python_file_count_is_the_real_one(self):
        actual = len([path for path in ROOT.rglob("*.py")
                      if ".git" not in path.parts and "__pycache__" not in path.parts])
        self.assertIn(f"{actual} Python files", self.text,
                      f"the readme does not say {actual} Python files")

    def test_the_test_count_is_the_one_the_suite_reports(self):
        # Counted live, from the test loader, not read from a file that a previous
        # run wrote. The old version read verification-results.txt, which made the
        # page a statement about the LAST run on SOME machine — and the count moves
        # by a few between machines, because some tests only exist when an optional
        # package is missing. That is a broken claim, not a broken page: this shows
        # up as a red test on the owner's Windows box while the Linux box is green.
        #
        # Discovery imports the modules and counts, without running anything, so it
        # is quick and it is exactly the number the suite will print as "Ran N".
        import sys as _sys
        import unittest as _unittest
        tests_dir = str(ROOT / "tests")
        if str(ROOT) not in _sys.path:
            _sys.path.insert(0, str(ROOT))
        suite = _unittest.defaultTestLoader.discover(tests_dir, top_level_dir=tests_dir)
        number = suite.countTestCases()
        # The page writes counts with thousands separators; the suite does not.
        for spelling in (f"{number} tests", f"{number:,} tests"):
            if spelling in self.text:
                return
        self.fail(f"the readme does not say {number:,} tests")


class Licence(unittest.TestCase):
    def test_the_credit_the_licence_requires_is_present(self):
        text = readme_text()
        for piece in ("FatihMakes", "BY-NC", "Creative Commons", "0101e5"):
            self.assertIn(piece, text)


class NoInventedScreenRecordings(unittest.TestCase):
    def test_the_page_does_not_promise_recordings_it_does_not_ship(self):
        text = readme_text().lower()
        self.assertNotIn("screen recording", text)
        self.assertFalse((ROOT / "renders").exists(),
                         "the readme used to point at renders/; if that folder is "
                         "added, say so on the page and delete this test")


if __name__ == "__main__":
    unittest.main()
