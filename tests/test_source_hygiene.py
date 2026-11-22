"""Rules about how the program's own code is written, checked on the code.

`tempfile.mktemp` returns a name and creates nothing. Between getting the name and writing
to it, another process can create a file or a link with that name, and the write then goes
wherever it points. Three places used it (`actions/desktop.py` twice, `actions/file_processor.py`
once) — a wallpaper image, and the audio track pulled out of a video for transcription.
`tempfile.mkstemp` creates the file exclusively and is the replacement.
"""

from __future__ import annotations

import ast
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OWNED = ("actions", "core", "custom_jarvis", "dashboard", "memory", "plugins", "providers",
         "scripts")


def python_files():
    for folder in OWNED:
        for path in sorted((ROOT / folder).rglob("*.py")):
            yield path
    for name in ("main.py", "ui.py", "setup.py"):
        if (ROOT / name).is_file():
            yield ROOT / name


class NoPredictableTempNames(unittest.TestCase):
    def test_nothing_calls_mktemp(self):
        offenders = []
        for path in python_files():
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    function = node.func
                    name = function.attr if isinstance(function, ast.Attribute) else \
                        getattr(function, "id", "")
                    if name == "mktemp":
                        offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
        self.assertEqual(offenders, [], "use tempfile.mkstemp, which creates the file")


class VendoredFilesAreAccountedFor(unittest.TestCase):
    """A third-party file in the tree has its licence in the tree.

    `dashboard/static/crypto-js.min.js` (CryptoJS, MIT) was in the repository with no
    entry in `licenses/THIRD_PARTY_NOTICES.md`; MIT asks that the notice travel with
    copies. The entry says the file is not loaded — this is the check that keeps that true.
    """

    def test_every_vendored_script_is_named_in_the_notices(self):
        notices = (ROOT / "licenses" / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        vendored = sorted(path.name for path in (ROOT / "dashboard" / "static").glob("*.min.js"))
        self.assertTrue(vendored, "the folder this test guards is empty; update the test")
        for name in vendored:
            with self.subTest(file=name):
                self.assertIn(name, notices)

    def test_the_licence_text_is_in_the_licenses_folder(self):
        text = (ROOT / "licenses" / "CRYPTOJS-LICENSE.txt").read_text(encoding="utf-8")
        self.assertIn("MIT License", text)
        self.assertIn("Evan Vosberg", text)

    def test_the_notice_says_unused_only_while_no_page_loads_it(self):
        pages = [path.read_text(encoding="utf-8")
                 for path in (ROOT / "dashboard" / "static").glob("*.html")]
        self.assertTrue(pages)
        loaded = [name for name in ("crypto-js.min.js", "crypto-js.js") if any(name in p for p in pages)]
        notices = (ROOT / "licenses" / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        if "vendored, not loaded" in notices:
            self.assertEqual(loaded, [], "a page loads CryptoJS now: fix the notice, which says it does not")


class TheWallpaperTempFile(unittest.TestCase):
    def test_it_is_a_real_empty_file_that_nobody_else_can_have(self):
        from actions import desktop
        made = [desktop._new_temp_file(".bmp") for _ in range(3)]
        try:
            self.assertEqual(len({str(path) for path in made}), 3)
            for path in made:
                self.assertTrue(path.is_file())
                self.assertEqual(path.stat().st_size, 0)
                self.assertEqual(path.suffix, ".bmp")
        finally:
            for path in made:
                os.unlink(path)


if __name__ == "__main__":
    unittest.main()
