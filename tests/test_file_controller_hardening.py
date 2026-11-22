"""`actions/file_controller.py`: the credential deny-list, and copy/move over existing files.

Faults reproduced before they were fixed:

1. `_SENSITIVE_DIR_PARTS` held `".config/BraveSoftware"` in mixed case, but the path it is
   compared with is lower-cased first, so the entry could never match: a Brave profile
   (saved logins, `Local State`) was readable while the owner's own rule says browser
   profiles are not. Brave and Edge on Windows had no entry at all, and neither did
   `.npmrc`, `.pypirc`, `gh/hosts.yml`, `.git/config`, shell histories or `rclone.conf` —
   places where tokens are kept in plain text.
2. `copy_file` replaced an existing destination, and its undo then DELETED the destination:
   undoing the copy destroyed the file that had been there first. `move_file` replaced too,
   and its undo moved the NEW file back, so the overwritten one was lost for good.
3. Handlers in `_get_laptop_roots` discarded every error, and a malformed `allowed_roots`
   (a string, `null`) was iterated character by character.
4. `laptop_wide_access` (every drive, on Windows) was on unless the settings said otherwise. The first
   hosted Windows run of the proof gate then found that a write outside the owner's folders was not
   refused (`\\tmp\\proof-gate-nope.txt`, at the top of the runner's D: drive). Only a saved `true` turns it on.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from actions import file_controller as fc
from core import failures, undo


def refused(raw: str) -> bool:
    return not fc._is_safe_path(fc._resolve_path(raw))


class TheDenyList(unittest.TestCase):
    def test_every_entry_can_match_the_lowered_path(self):
        # The mixed-case entry could never match; this is the class of mistake.
        for part in fc._SENSITIVE_DIR_PARTS + fc._CRITICAL_SYSTEM_DIR_PARTS:
            with self.subTest(part=part):
                self.assertEqual(part, part.lower())
                self.assertNotIn("\\", part)

    def test_names_and_suffixes_are_lower_case_too(self):
        for name in fc._SENSITIVE_FILE_NAMES:
            self.assertEqual(name, name.lower(), name)
        for suffix in fc._SENSITIVE_SUFFIXES:
            self.assertEqual(suffix, suffix.lower(), suffix)

    def test_a_brave_profile_is_refused_on_every_system(self):
        for raw in ("~/.config/BraveSoftware/Brave-Browser/Local State",
                    "~/.config/BraveSoftware/Brave-Browser/Default/Preferences",
                    "~/AppData/Local/BraveSoftware/Brave-Browser/User Data/Local State",
                    "~/Library/Application Support/BraveSoftware/Brave-Browser/Local State"):
            with self.subTest(raw=raw):
                self.assertTrue(refused(raw), raw)

    def test_the_other_browsers_are_refused_too(self):
        for raw in ("~/AppData/Local/Microsoft/Edge/User Data/Local State",
                    "~/.config/microsoft-edge/Default/Preferences",
                    "~/AppData/Local/Vivaldi/User Data/Local State",
                    "~/AppData/Roaming/Opera Software/Opera Stable/Local State",
                    "~/.config/vivaldi/Default/Preferences",
                    "~/Library/Application Support/Google/Chrome/Local State",
                    "~/Library/Application Support/Firefox/Profiles/x.default/prefs.js"):
            with self.subTest(raw=raw):
                self.assertTrue(refused(raw), raw)

    def test_token_files_in_the_home_folder_are_refused(self):
        for raw in ("~/.npmrc", "~/.pypirc", "~/.yarnrc.yml", "~/.config/gh/hosts.yml",
                    "~/AppData/Roaming/GitHub CLI/hosts.yml", "~/.git-credentials",
                    "~/proj/.git/config", "~/.config/rclone/rclone.conf",
                    "~/.s3cfg", "~/.my.cnf", "~/.vault-token", "~/.htpasswd",
                    "~/.dockercfg", "~/.boto"):
            with self.subTest(raw=raw):
                self.assertTrue(refused(raw), raw)

    def test_shell_histories_are_refused(self):
        for raw in ("~/.bash_history", "~/.zsh_history", "~/.python_history",
                    "~/.mysql_history", "~/.psql_history",
                    "~/AppData/Roaming/Microsoft/Windows/PowerShell/PSReadLine/"
                    "ConsoleHost_history.txt"):
            with self.subTest(raw=raw):
                self.assertTrue(refused(raw), raw)

    def test_more_key_material_is_refused(self):
        for raw in ("~/vpn/work.ovpn", "~/keys/putty.ppk", "~/keys/AuthKey_ABC.p8",
                    "~/old.kdb", "~/.ssh_backup/id_rsa", "~/backup/id_rsa.bak",
                    "~/backup/id_ed25519_work", "~/Desktop/id_ecdsa-copy"):
            with self.subTest(raw=raw):
                self.assertTrue(refused(raw), raw)

    def test_a_backup_of_a_credential_folder_is_still_refused(self):
        # A name that continues with a separator, not a letter, is a copy of the folder.
        for raw in ("~/.ssh-old/id_x", "~/.ssh.bak/config", "~/.aws_backup/credentials"):
            with self.subTest(raw=raw):
                self.assertTrue(refused(raw), raw)

    def test_the_keychains_on_a_mac_are_refused(self):
        self.assertTrue(refused("~/Library/Keychains/login.keychain-db"))

    def test_the_original_entries_still_hold(self):
        for raw in ("~/.ssh/id_rsa", "~/.aws/credentials", "~/.gnupg/secring.gpg",
                    "~/.kube/config", "~/.docker/config.json", "~/.env", "~/proj/.env.local",
                    "~/app/config/api_keys.json", "~/keys/x.pem", "~/vault.kdbx",
                    "~/AppData/Local/Google/Chrome/User Data/Default/Login Data",
                    "~/.mozilla/firefox/abc.default/logins.json",
                    "~/.config/google-chrome/Default/Cookies"):
            with self.subTest(raw=raw):
                self.assertTrue(refused(raw), raw)

    def test_ordinary_files_that_resemble_a_credential_are_not_refused(self):
        for raw in ("~/proj/.dockerignore",             # starts like `.docker`
                    "~/proj/.gitignore", "~/proj/.git/HEAD", "~/proj/.github/workflows/ci.yml",
                    "~/.config/ghostty/config",         # starts like `.config/gh`
                    "~/Documents/awsome-notes.txt",
                    "~/Documents/keys-notes.txt", "~/Desktop/identity.pdf",
                    "~/Documents/idea.txt",
                    "~/Documents/id_rsa.pub",           # the public half is meant to be shared
                    "~/Documents/report.docx", "~/Pictures/holiday.jpg"):
            with self.subTest(raw=raw):
                self.assertFalse(refused(raw), f"{raw} is an ordinary file")

    def test_the_refusal_says_credentials_for_the_new_entries(self):
        message = fc._denial_message(Path("~/.npmrc").expanduser())
        self.assertIn("credentials", message)
        self.assertNotIn("Access denied", message)

    def test_a_windows_system_folder_is_still_a_system_folder(self):
        with mock.patch.object(fc, "_OS", "Windows"):
            target = Path("C:/Windows/System32/cmd.exe")
            self.assertIn("critical operating system", fc._denial_message(target))


class CopyAndMoveNeverOverwrite(unittest.TestCase):
    def setUp(self):
        undo.clear()
        self.addCleanup(undo.clear)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name).resolve()
        for patcher in (mock.patch.object(fc, "_SAFE_ROOTS", [self.home]),
                        mock.patch.object(fc, "_get_laptop_roots", return_value=[self.home])):
            patcher.start()
            self.addCleanup(patcher.stop)

    def make(self, name, text):
        path = self.home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_copy_onto_an_existing_file_is_refused_and_changes_nothing(self):
        source = self.make("a.txt", "source")
        target = self.make("b.txt", "precious original")
        reply = fc.copy_file(str(source), destination=str(target))
        self.assertIn("already exists", reply)
        self.assertEqual(target.read_text(encoding="utf-8"), "precious original")
        self.assertEqual(source.read_text(encoding="utf-8"), "source")
        self.assertFalse(undo.can_undo(), "nothing happened, so there is nothing to undo")

    def test_copy_into_a_folder_that_already_has_that_name_is_refused(self):
        source = self.make("a.txt", "source")
        self.make("dest/a.txt", "precious original")
        reply = fc.copy_file(str(source), destination=str(self.home / "dest"))
        self.assertIn("already exists", reply)
        self.assertEqual((self.home / "dest" / "a.txt").read_text(encoding="utf-8"),
                         "precious original")

    def test_copy_to_a_free_name_works_and_undo_removes_only_the_copy(self):
        source = self.make("a.txt", "source")
        reply = fc.copy_file(str(source), destination=str(self.home / "copy.txt"))
        self.assertIn("Copied", reply)
        self.assertEqual((self.home / "copy.txt").read_text(encoding="utf-8"), "source")
        undo.undo_last()
        self.assertFalse((self.home / "copy.txt").exists())
        self.assertTrue(source.exists(), "the original is never touched")

    def test_copying_a_folder_onto_an_existing_folder_is_refused(self):
        self.make("src/x.txt", "x")
        self.make("dst/y.txt", "y")
        reply = fc.copy_file(str(self.home / "src"), destination=str(self.home / "dst"))
        # "dst" is a directory, so the copy would land in dst/src — which is free.
        self.assertIn("Copied", reply)
        reply = fc.copy_file(str(self.home / "src"), destination=str(self.home / "dst"))
        self.assertIn("already exists", reply)
        self.assertEqual((self.home / "dst" / "y.txt").read_text(encoding="utf-8"), "y")

    def test_copy_onto_itself_is_a_clear_refusal_not_an_exception_message(self):
        source = self.make("a.txt", "source")
        reply = fc.copy_file(str(source), destination=str(source))
        self.assertIn("already exists", reply)
        self.assertNotIn("Could not", reply)

    def test_move_onto_an_existing_file_is_refused_and_changes_nothing(self):
        source = self.make("a.txt", "source")
        target = self.make("b.txt", "precious original")
        reply = fc.move_file(str(source), destination=str(target))
        self.assertIn("already exists", reply)
        self.assertEqual(target.read_text(encoding="utf-8"), "precious original")
        self.assertEqual(source.read_text(encoding="utf-8"), "source")
        self.assertFalse(undo.can_undo())

    def test_move_into_a_folder_that_has_that_name_is_refused(self):
        source = self.make("a.txt", "source")
        self.make("dest/a.txt", "precious original")
        reply = fc.move_file(str(source), destination=str(self.home / "dest"))
        self.assertIn("already exists", reply)
        self.assertTrue(source.exists())
        self.assertEqual((self.home / "dest" / "a.txt").read_text(encoding="utf-8"),
                         "precious original")

    def test_move_to_a_free_name_works_and_undo_puts_it_back(self):
        source = self.make("a.txt", "source")
        reply = fc.move_file(str(source), destination=str(self.home / "moved.txt"))
        self.assertIn("Moved", reply)
        self.assertFalse(source.exists())
        undo.undo_last()
        self.assertEqual(source.read_text(encoding="utf-8"), "source")
        self.assertFalse((self.home / "moved.txt").exists())


class TheRoots(unittest.TestCase):
    def setUp(self):
        failures.clear()
        self.addCleanup(failures.clear)

    def notes(self):
        return [n for n in failures.recent() if n["where"].startswith("file_controller.")]

    def test_a_string_for_allowed_roots_is_not_read_character_by_character(self):
        self.assertEqual(fc._configured_roots({"allowed_roots": "/home/user"}), [])
        self.assertEqual(len(self.notes()), 1)
        self.assertIn("must be a list", self.notes()[0]["error"])

    def test_null_and_other_junk_entries_are_skipped_and_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            roots = fc._configured_roots({"allowed_roots": [None, 5, folder, folder]})
        self.assertEqual([r.name for r in roots], [Path(folder).resolve().name])
        self.assertEqual(len(self.notes()), 2)

    def test_a_folder_that_does_not_exist_is_not_a_root(self):
        self.assertEqual(fc._configured_roots({"allowed_roots": ["/no/such/folder/here"]}), [])

    def test_a_config_that_cannot_be_read_leaves_the_built_in_roots(self):
        from memory import config_manager
        with mock.patch.object(config_manager, "load_api_keys",
                               side_effect=OSError("disk went away")):
            roots = fc._get_laptop_roots()
        self.assertEqual(roots, list(fc._SAFE_ROOTS))
        self.assertTrue(any("disk went away" in n["error"] for n in self.notes()))

    def test_a_configured_root_extends_the_safe_roots(self):
        from memory import config_manager
        with tempfile.TemporaryDirectory() as folder:
            with mock.patch.object(config_manager, "load_api_keys",
                                   return_value={"allowed_roots": [folder],
                                                 "laptop_wide_access": False}):
                roots = fc._get_laptop_roots()
            self.assertIn(Path(folder).resolve(), roots)

    # `laptop_wide_access` reaches every drive: on Windows only, and only if the owner saved `true`.
    # It used to be on unless the settings said otherwise, and the first hosted Windows run of the
    # proof gate found a write outside the owner's folders that was not refused. `Path("C:/")` is
    # only a name on Linux, so these tests make two drives, C: and D:, exist by name on every system.
    def roots_with(self, config, system="Windows"):
        from memory import config_manager
        real_exists = Path.exists

        def exists(path, *args, **kwargs):
            name = str(path).rstrip("/\\")
            if len(name) == 2 and name[1] == ":":
                return name in {"C:", "D:"}
            return real_exists(path, *args, **kwargs)

        with mock.patch.object(fc, "_OS", system), \
                mock.patch.object(config_manager, "load_api_keys", return_value=config), \
                mock.patch.object(Path, "exists", exists):
            return fc._get_laptop_roots()

    def test_with_no_saved_choice_no_drive_is_added(self):
        self.assertEqual(self.roots_with({}), list(fc._SAFE_ROOTS))

    def test_a_choice_that_is_not_the_boolean_true_adds_no_drive(self):
        for value in (False, "true", "yes", 1, [], None):
            with self.subTest(value=value):
                self.assertEqual(self.roots_with({"laptop_wide_access": value}),
                                 list(fc._SAFE_ROOTS))

    def test_a_saved_true_adds_every_drive_that_exists_and_no_other(self):
        roots = self.roots_with({"laptop_wide_access": True})
        self.assertIn(Path("C:/"), roots)
        self.assertIn(Path("D:/"), roots)
        self.assertNotIn(Path("E:/"), roots)

    def test_the_setting_does_nothing_off_windows(self):
        for system in ("Linux", "Darwin"):
            with self.subTest(system=system):
                self.assertEqual(self.roots_with({"laptop_wide_access": True}, system),
                                 list(fc._SAFE_ROOTS))


if __name__ == "__main__":
    unittest.main()
