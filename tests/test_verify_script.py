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
import inspect
import os
import subprocess
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


class ANativeCrashLeavesAnAccount(unittest.TestCase):
    """A step that dies of a native crash must say where, and keep what it had printed.

    The hosted run of the merge of pull request #22 on `main` ended in the UI self-tests with one line,
    `exit -11`, on a tree that had passed the same step three times: no report of where it died, and the
    end of the output was whatever the pipe had last been flushed to. A Qt crash looks the same on every
    system, so the child below crashes the same way everywhere: it says one thing without flushing it,
    then makes a real invalid read of address 0 with `faulthandler._read_null()`, the call CPython's own
    tests use for that. It also turns off the crash dialog nobody is there to click.

    The first version read address 0 through `ctypes.string_at(0)`. The hosted Windows run showed that
    this does not crash there: ctypes catches the fault and raises an ordinary OSError, so the child
    exited normally and flushed its line, and the control below failed. A native crash is not something
    to imitate with a library that is built to survive one.
    """

    CRASH = (
        "import faulthandler\n"
        "print('the last thing it said', end='')\n"
        "faulthandler._read_null()\n"
    )

    def crash(self, environment: dict) -> tuple[int, str, str]:
        # S603: the interpreter running this test and a program written above, nothing from outside
        done = subprocess.run([sys.executable, "-c", self.CRASH], env=environment, capture_output=True,  # noqa: S603
                              timeout=120, check=False)
        return done.returncode, done.stdout.decode("utf-8", "replace"), done.stderr.decode("utf-8", "replace")

    def test_the_old_environment_loses_both_which_is_why_it_changed(self):
        # The control: without the two variables the crash is silent and the line is gone. If this
        # ever fails, the test below proves nothing, because the crash no longer shows what it fixes.
        environment = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        for name in ("PYTHONFAULTHANDLER", "PYTHONUNBUFFERED"):
            environment.pop(name, None)
        code, out, err = self.crash(environment)
        self.assertNotEqual(code, 0)
        self.assertEqual(out, "")
        self.assertNotIn("most recent call first", err)

    def test_the_step_environment_keeps_the_report_and_the_last_line(self):
        code, out, err = self.crash(verify.step_environment())
        self.assertNotEqual(code, 0)
        self.assertEqual(out, "the last thing it said")
        self.assertIn("most recent call first", err)
        self.assertEqual(verify.step_environment()["QT_QPA_PLATFORM"], "offscreen")

    def test_every_step_of_the_chain_runs_with_it(self):
        source = inspect.getsource(verify.main)
        self.assertIn("step_environment()", source)
        self.assertNotIn("dict(os.environ", source)


if __name__ == "__main__":
    unittest.main()
