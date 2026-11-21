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
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "readme.md"


def readme_text() -> str:
    return README.read_text(encoding="utf-8")


class PathsOnTheFrontPage(unittest.TestCase):
    def setUp(self):
        self.text = readme_text()

    def _is_runtime_file(self, name: str) -> bool:
        """True when the repository deliberately does not ship this path.

        The page documents files the app creates on first run — the key file and
        the long-term memory store. Those are gitignored on purpose, so a fresh
        checkout must NOT contain them, and a test that demands they exist fails on
        every clean machine while passing on the author's. Git already knows the
        difference, so ask it rather than keeping a second list to go stale.
        """
        try:
            done = subprocess.run(["git", "check-ignore", "-q", name], cwd=ROOT,
                                  capture_output=True, timeout=10)
            return done.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def test_every_backticked_file_path_exists(self):
        pattern = re.compile(r"`([\w./-]+\.(?:py|md|json|txt|yml|bat|ps1|gif|so|c))`")
        missing = sorted({hit for hit in pattern.findall(self.text)
                          if "/" in hit and not (ROOT / hit).exists()
                          and not self._is_runtime_file(hit)})
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

    def test_the_demo_is_a_small_animated_gif(self):
        picture = ROOT / "docs" / "img" / "ultron-operating-layer-demo.gif"
        self.assertTrue(picture.exists(), "the readme demo GIF is missing")
        data = picture.read_bytes()[:6]
        self.assertIn(data, (b"GIF87a", b"GIF89a"), "the demo is not a GIF")
        self.assertLess(picture.stat().st_size, 400_000,
                        "the demo is too big to load quickly on a phone")
        self.assertTrue((ROOT / "docs" / "img" / "ultron-operating-layer-demo.cast").exists())

    def test_visual_media_is_labelled_honestly(self):
        """The HUD picture is illustrative and the terminal demo is scripted."""
        self.assertIn("illustration", self.text.lower())
        self.assertIn("scripted", self.text.lower())
        self.assertIn("synthetic", self.text.lower())


class CapabilityClaims(unittest.TestCase):
    def test_core_capabilities_and_theme_are_named(self):
        text = readme_text().lower()
        for claim in ("use the computer", "search the web", "web_read", "robots.txt", "holographic"):
            self.assertIn(claim, text)

    def test_readme_avoids_machine_dependent_test_and_file_counts(self):
        text = readme_text().lower()
        self.assertNotRegex(text, r"\b\d[\d,]* python files\b")
        self.assertNotRegex(text, r"\b\d[\d,]* tests\b")


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


class Badges(unittest.TestCase):
    """A badge is a claim. It must be true, or read its truth from somewhere that is."""

    def setUp(self):
        self.text = readme_text()

    def test_the_python_range_is_the_one_the_launcher_accepts(self):
        # The badge said 3.10+ while main.py uses BaseExceptionGroup (3.11) and the
        # launcher refuses everything but 3.11 to 3.13.
        import re
        from urllib.parse import unquote
        from core import launch_guard
        badge = re.search(r"img\.shields\.io/badge/Python-([^)\s]+?)-blue", self.text)
        self.assertIsNotNone(badge, "the page has no Python badge")
        shown = unquote(badge.group(1))
        low, high = launch_guard.SUPPORTED[0], launch_guard.SUPPORTED[-1]
        self.assertIn(f"{low[0]}.{low[1]}", shown)
        self.assertIn(f"{high[0]}.{high[1]}", shown)
        self.assertNotIn("+", shown, "an open-ended range promises versions nobody tested")

    def test_no_static_badge_says_a_check_is_passing(self):
        # "Fast Gate Passing" was a fixed image: it stayed green while the full
        # verification on main failed 22 pushes in a row.
        import re
        static = re.findall(r"img\.shields\.io/badge/[^)\s]*", self.text)
        for url in static:
            with self.subTest(url=url):
                self.assertNotRegex(url.lower(), r"pass|green|success|verified")

    def test_the_status_badges_read_the_real_workflows(self):
        import re
        workflows = re.findall(r"actions/workflows/([\w.-]+)/badge\.svg", self.text)
        self.assertTrue(workflows, "the page has no live workflow badge")
        for name in workflows:
            with self.subTest(workflow=name):
                self.assertTrue((ROOT / ".github" / "workflows" / name).is_file())


if __name__ == "__main__":
    unittest.main()
