"""`scripts/verify.py`: it catches what the suite leaves behind, and it does only its job.

Two faults:

* The config writer (`memory/config_manager.py`) now writes `api_keys.json.<random>.tmp`
  before replacing the file, and the leftover-file check only knew the old fixed name
  `api_keys.json.tmp` — a test that left a temp behind would pass the check.
* `refresh_readme_numbers` ran at the start of every verification, including every
  self-change rehearsal, and imported all ~270 test modules in that process to count
  the tests — then found no number on the page to update (the front page states no
  counts, and `tests/test_readme.py` forbids them) and threw the count away.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path, PureWindowsPath
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verify_script", ROOT / "scripts" / "verify.py")
verify = importlib.util.module_from_spec(SPEC)
sys.modules["verify_script"] = verify
SPEC.loader.exec_module(verify)


class WithAScratchProject(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        (self.root / "config").mkdir()
        for name, value in (("ROOT", self.root),
                            ("USER_CONFIG", self.root / "config" / "api_keys.json")):
            patcher = mock.patch.object(verify, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def touch(self, name: str, text: str = "x") -> None:
        (self.root / "config" / name).write_text(text, encoding="utf-8")


class TheLeftoverCheck(WithAScratchProject):
    def test_a_clean_project_has_nothing_stray(self):
        self.assertEqual(verify._stray_host_files(), [])

    def test_the_unique_temp_the_config_writer_makes_is_caught(self):
        self.touch("api_keys.json.k3j2x9ab.tmp")
        self.assertEqual(verify._stray_host_files(), ["config/api_keys.json.k3j2x9ab.tmp"])

    def test_the_old_fixed_temp_and_the_quarantine_are_still_caught(self):
        self.touch("api_keys.json.tmp")
        self.touch("api_keys.json.broken-1700000000")
        self.touch("setup-log.txt")
        found = set(verify._stray_host_files())
        self.assertEqual(found, {"config/api_keys.json.tmp",
                                 "config/api_keys.json.broken-1700000000",
                                 "config/setup-log.txt"})

    def test_a_set_aside_memory_store_and_its_temporary_file_are_caught(self):
        (self.root / "memory").mkdir()
        for name in ("long_term.json.broken-1700000000", ".long_term.json.ab12cd.tmp"):
            (self.root / "memory" / name).write_text("x", encoding="utf-8")
        self.assertEqual(set(verify._stray_host_files()),
                         {"memory/long_term.json.broken-1700000000",
                          "memory/.long_term.json.ab12cd.tmp"})

    def test_the_memory_store_itself_is_not_called_stray(self):
        (self.root / "memory").mkdir()
        (self.root / "memory" / "long_term.json").write_text("{}", encoding="utf-8")
        self.assertEqual(verify._stray_host_files(), [])

    def test_the_names_the_memory_store_makes_match_the_patterns(self):
        # Both ends of the contract, as for the settings file below.
        import fnmatch
        import os
        from memory import memory_manager
        with tempfile.TemporaryDirectory() as folder:
            descriptor, name = tempfile.mkstemp(dir=folder, suffix=".tmp",
                                                prefix=f".{memory_manager.MEMORY_PATH.name}.")
            os.close(descriptor)
            self.assertTrue(fnmatch.fnmatch(Path(name).name, ".long_term.json.*.tmp"), name)
        self.assertTrue(fnmatch.fnmatch(f"{memory_manager.MEMORY_PATH.name}.broken-1700000000",
                                        "long_term.json.broken-*"))

    def test_a_settings_file_with_content_is_caught_and_an_empty_one_is_not(self):
        self.touch("api_keys.json", "")
        self.assertEqual(verify._stray_host_files(), [])
        self.touch("api_keys.json", '{"window_width": 1600}')
        self.assertEqual(verify._stray_host_files(), ["config/api_keys.json"])

    def test_names_use_forward_slashes_even_where_the_system_writes_backslashes(self):
        # `str(path.relative_to(root))` is `config\api_keys.json` on Windows, and four tests
        # failed on the first Windows run for that alone. This path is a real one on this
        # machine whose `relative_to` answers the way Windows does, so the same mistake fails
        # here too, without a Windows machine.
        class LooksLikeWindows(type(Path())):
            def relative_to(self, *args, **kwargs):
                return PureWindowsPath(*super().relative_to(*args, **kwargs).parts)

        self.touch("api_keys.json", '{"window_width": 1600}')
        self.touch("api_keys.json.k3j2x9ab.tmp")
        (self.root / "memory").mkdir()
        (self.root / "memory" / "long_term.json.broken-1700000000").write_text("x", encoding="utf-8")
        with mock.patch.object(verify, "ROOT", LooksLikeWindows(self.root)), \
                mock.patch.object(verify, "USER_CONFIG",
                                  LooksLikeWindows(self.root / "config" / "api_keys.json")):
            found = verify._stray_host_files()
        self.assertEqual(len(found), 3, found)
        for name in found:
            self.assertNotIn("\\", name)
        self.assertEqual(set(found), {"config/api_keys.json", "config/api_keys.json.k3j2x9ab.tmp",
                                      "memory/long_term.json.broken-1700000000"})

    def test_the_temp_name_the_writer_makes_matches_the_pattern(self):
        # Both ends of the contract in one place: whatever the writer names its temp
        # file, this check has to see it.
        from memory import config_manager
        import fnmatch
        with tempfile.TemporaryDirectory() as folder:
            descriptor, name = tempfile.mkstemp(dir=folder, suffix=".tmp",
                                                prefix=f"{config_manager.CONFIG_FILE.name}.")
            import os
            os.close(descriptor)
            self.assertTrue(fnmatch.fnmatch(Path(name).name, "api_keys.json.*.tmp"), name)


class ItDoesOnlyItsJob(unittest.TestCase):
    def test_the_dead_readme_refreshers_are_gone(self):
        self.assertFalse(hasattr(verify, "refresh_readme_numbers"))
        self.assertFalse(hasattr(verify, "refresh_readme_sizes"))

    def test_it_does_not_import_the_whole_test_suite_to_count_it(self):
        source = (ROOT / "scripts" / "verify.py").read_text(encoding="utf-8")
        self.assertNotIn(".discover(", source)
        self.assertNotIn("defaultTestLoader", source)

    def test_it_never_rewrites_the_front_page(self):
        source = (ROOT / "scripts" / "verify.py").read_text(encoding="utf-8")
        self.assertNotIn("readme.md", source)


if __name__ == "__main__":
    unittest.main()
