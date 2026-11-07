"""A folder search must not walk into a key store.

The Antigravity audit (7 Nov 2026) reported that ``find_files`` leaked credential files. It
did: ``_is_safe_path`` refused a *starting* path inside a key store, and then the recursive
walk below a safe folder listed everything it reached. The refusal is now repeated for every
entry the walk touches.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from actions import file_controller


class AFindNeverNamesAKeyStore(unittest.TestCase):
    """One safe folder, three files, one of them a private key."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        root = Path(self.folder.name)
        self.root = root
        (root / "notes.txt").write_text("ordinary", encoding="utf-8")
        (root / "report.pdf").write_bytes(b"%PDF-1.4")
        keys = root / ".ssh"
        keys.mkdir()
        (keys / "id_rsa").write_text("PRIVATE", encoding="utf-8")
        (root / ".env").write_text("SECRET=1", encoding="utf-8")
        (root / "server.pem").write_text("CERT", encoding="utf-8")

    def tearDown(self):
        self.folder.cleanup()

    def search(self, **kwargs):
        with patch.object(file_controller, "_SAFE_ROOTS", [self.root]):
            return file_controller.find_files(path=str(self.root), **kwargs)

    def test_an_ordinary_file_is_still_found(self):
        result = self.search()
        self.assertIn("notes.txt", result)

    def test_the_private_key_inside_a_hidden_folder_is_not_listed(self):
        result = self.search()
        self.assertNotIn("id_rsa", result)

    def test_a_dotenv_and_a_certificate_are_not_listed(self):
        result = self.search()
        self.assertNotIn(".env", result)
        self.assertNotIn("server.pem", result)

    def test_a_search_that_only_matches_keys_reports_nothing_found(self):
        result = self.search(name="id_rsa")
        self.assertIn("No id_rsa found", result)

    def test_a_search_by_extension_skips_the_certificate(self):
        result = self.search(extension=".pem")
        self.assertIn("No .pem found", result)


if __name__ == "__main__":
    unittest.main()
