"""tests/test_file_safety.py — what file_controller will and will not touch.

The safety test used to be "is this path inside the home directory", and the home
directory is where every credential on a machine lives. Measured before this was
fixed: `read_file("~/.ssh/id_rsa")` was allowed, and so — from a project inside
home — was reading this program's own `config/api_keys.json`. An assistant that
will read those on request is one web page away from reading them out loud.

Both halves are asserted here: the refusal, and the fact that ordinary work in
ordinary folders is untouched by it.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from actions import file_controller as fc          # noqa: E402


class CredentialStoreTests(unittest.TestCase):
    def assert_refused(self, raw: str):
        target = fc._resolve_path(raw)
        self.assertFalse(fc._is_safe_path(target), f"{raw} should be refused")

    def test_ssh_keys_are_refused(self):
        for raw in ("~/.ssh/id_rsa", "~/.ssh/id_ed25519", "~/.ssh/config"):
            self.assert_refused(raw)

    def test_cloud_and_gpg_stores_are_refused(self):
        for raw in ("~/.aws/credentials", "~/.gnupg/secring.gpg", "~/.kube/config",
                    "~/.docker/config.json", "~/.password-store/x.gpg"):
            self.assert_refused(raw)

    def test_dotenv_files_are_refused(self):
        for raw in ("~/.env", "~/proj/.env", "~/proj/.env.local"):
            self.assert_refused(raw)

    def test_key_material_by_extension_is_refused(self):
        for raw in ("~/keys/server.pem", "~/keys/id.key", "~/certs/x.p12",
                    "~/vault.kdbx"):
            self.assert_refused(raw)

    def test_this_programs_own_key_file_is_refused(self):
        # Even when the project sits inside the home directory, which it does by
        # default when someone extracts the ZIP where Windows puts downloads.
        self.assert_refused("~/app/config/api_keys.json")
        self.assert_refused("~/Desktop/ultron/config/api_keys.json")

    def test_a_browser_profile_is_refused(self):
        for raw in ("~/AppData/Local/Google/Chrome/User Data/Default/Login Data",
                    "~/.mozilla/firefox/abc.default/logins.json",
                    "~/.config/google-chrome/Default/Cookies"):
            self.assert_refused(raw)

    def test_ordinary_home_files_are_still_allowed(self):
        for raw in ("~/notes.txt", "~/Documents/report.docx", "~/Downloads/x.pdf",
                    "~/Pictures/holiday.jpg", "~/Desktop/todo.md"):
            target = fc._resolve_path(raw)
            self.assertTrue(fc._is_safe_path(target), f"{raw} should be allowed")

    def test_the_refusal_says_which_kind_of_refusal_it_is(self):
        message = fc._denial_message(Path("~/.ssh/id_rsa").expanduser())
        self.assertIn("credentials", message)
        self.assertNotIn("Access denied", message)

    def test_an_outside_path_still_says_access_denied(self):
        self.assertIn("Access denied", fc._denial_message(Path("/etc/passwd")))


class RealOperationsTests(unittest.TestCase):
    """The deny-list must not get in the way of the work it is protecting."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.home = Path(self._temp.name)
        self._saved = fc._SAFE_ROOTS
        fc._SAFE_ROOTS = [self.home]

    def tearDown(self):
        fc._SAFE_ROOTS = self._saved
        self._temp.cleanup()

    def test_write_read_and_append_round_trip(self):
        target = self.home / "notes.md"
        self.assertIn("Written", fc.write_file(str(target), content="one\n"))
        self.assertIn("Appended", fc.write_file(str(target), content="two\n", append=True))
        self.assertEqual(target.read_text(encoding="utf-8"), "one\ntwo\n")
        self.assertIn("one\ntwo", fc.read_file(str(target)))

    def test_a_write_is_undoable(self):
        from core import undo
        undo.clear()
        target = self.home / "keep.txt"
        target.write_text("original", encoding="utf-8")
        fc.write_file(str(target), content="replaced")
        self.assertEqual(target.read_text(encoding="utf-8"), "replaced")
        undo.undo_last()
        self.assertEqual(target.read_text(encoding="utf-8"), "original")
        undo.clear()

    def test_listing_a_folder_still_works(self):
        (self.home / "a.txt").write_text("x", encoding="utf-8")
        listing = fc.file_controller({"action": "list", "path": str(self.home)})
        self.assertIn("a.txt", listing)


if __name__ == "__main__":
    unittest.main()
