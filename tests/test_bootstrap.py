"""tests/test_bootstrap.py — the double-click path.

A launcher is the only part of this project with no Python in it, so it gets no
coverage from anything else. run.bat is what a stranger touches first, and the
failure mode that matters is not "it printed the wrong thing" — it is "it exited
without saying anything", or "it edited the line endings and now cmd.exe reads a
stray carriage return". This file asserts the properties that would break the
launcher, and exercises the recovery logic behind it that can be tested here.

The one thing that cannot be tested on this machine is whether cmd.exe runs the
file. It is checked for the mistakes that make it not run: a bare LF, a non-ASCII
byte, a `goto` to a label that does not exist, a launcher pointed at a script
that was renamed.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import bootstrap


def bat_text() -> str:
    return (ROOT / "run.bat").read_bytes().decode("ascii")


class RunBatTests(unittest.TestCase):
    def test_it_exists_and_is_plain_ascii(self):
        data = (ROOT / "run.bat").read_bytes()
        bad = [(i, b) for i, b in enumerate(data) if b > 127]
        self.assertEqual(bad, [], f"run.bat has non-ASCII bytes at {bad[:5]}")

    def test_it_uses_windows_line_endings(self):
        data = (ROOT / "run.bat").read_bytes()
        self.assertIn(b"\r\n", data)
        self.assertEqual(data.count(b"\n"), data.count(b"\r\n"), "run.bat has a bare LF")

    def test_every_goto_and_call_lands_on_a_label(self):
        text = bat_text()
        labels = {line.strip()[1:].lower() for line in text.splitlines()
                  if line.strip().startswith(":") and not line.strip().startswith("::")}
        labels.add("eof")  # goto :eof is built into cmd's extensions, not a label
        targets = {
            match.group(1).lower()
            for match in re.finditer(r"(?:goto|call)\s+:?([A-Za-z_][\w]*)", text)
        }
        self.assertTrue(targets)
        self.assertEqual(sorted(targets - labels), [], "run.bat jumps to a missing label")

    def test_it_installs_nothing_by_itself_and_launches_through_bootstrap(self):
        text = bat_text()
        self.assertIn("scripts\\bootstrap.py", text)
        self.assertIn("main.py", text)
        # The launcher must not grow its own installer: pip belongs in bootstrap.
        self.assertNotIn("pip", text)

    def test_a_failure_never_closes_the_window_silently(self):
        text = bat_text()
        self.assertIn("pause", text)
        for label in (":setupfailed", ":appfailed", ":missing", ":nopython", ":envfailed"):
            self.assertIn(f"{label}", text, f"{label} is not reachable")

    def test_it_offers_python_before_giving_up(self):
        # The one manual step left in a fresh-machine install. If winget exists the
        # user is asked, once, instead of being sent to a web page.
        text = bat_text()
        self.assertIn("winget install", text)
        self.assertIn("www.python.org", text)
        self.assertIn("set /p", text)

    def test_a_broken_venv_is_moved_aside_not_deleted(self):
        text = bat_text()
        self.assertIn("move \".venv\" \".venv.old\"", text)
        self.assertNotIn("rmdir /s /q \".venv\"", text)


class GitignoreTests(unittest.TestCase):
    """The .gitignore is plumbing, and it is the plumbing run.bat touches.

    This class exists because the file looked right and ignored nothing: every
    pattern had a trailing `# comment`, which git reads as part of the pattern.
    `config/api_keys.json` was not ignored, on a project whose own header says
    committing it publishes the key.
    """

    GIT = shutil.which("git")

    def patterns(self) -> list[str]:
        lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        return [line for line in lines if line.strip() and not line.lstrip().startswith("#")]

    def test_no_pattern_carries_a_trailing_comment(self):
        offenders = [line for line in self.patterns() if "#" in line]
        self.assertEqual(offenders, [], "git has no trailing comments; these match nothing")

    def test_the_launcher_output_is_ignored(self):
        patterns = self.patterns()
        self.assertIn("setup-log.txt", patterns)
        self.assertIn(".ultron-collect-state.json", patterns)
        self.assertIn(".venv.old/", patterns)

    @unittest.skipUnless(GIT, "git is not installed here")
    def test_the_secrets_are_actually_ignored(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            subprocess.run([self.GIT, "init", "-q", str(repo)], check=True)
            (repo / ".gitignore").write_bytes((ROOT / ".gitignore").read_bytes())
            (repo / "config").mkdir()
            (repo / "config" / "api_keys.json").write_text("{}", encoding="utf-8")
            (repo / "config" / "certs").mkdir()
            (repo / "config" / "certs" / "tls.key").write_text("k", encoding="utf-8")
            (repo / "setup-log.txt").write_text("x", encoding="utf-8")

            for name in ("config/api_keys.json", "config/certs/tls.key", "setup-log.txt"):
                with self.subTest(name=name):
                    done = subprocess.run(
                        [self.GIT, "check-ignore", "-q", name], cwd=repo, check=False
                    )
                    self.assertEqual(done.returncode, 0, f"{name} is not ignored")

    @unittest.skipUnless(GIT, "git is not installed here")
    def test_the_project_files_are_not_ignored(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            subprocess.run([self.GIT, "init", "-q", str(repo)], check=True)
            (repo / ".gitignore").write_bytes((ROOT / ".gitignore").read_bytes())
            for name in ("run.bat", "main.py", "requirements.txt", "log.txt",
                         "ALGORITHMS.md", "verification-results.txt"):
                with self.subTest(name=name):
                    done = subprocess.run(
                        [self.GIT, "check-ignore", "-q", name], cwd=repo, check=False
                    )
                    self.assertEqual(done.returncode, 1, f"{name} must never be ignored")


class RequirementsParsingTests(unittest.TestCase):
    def test_comments_and_blank_lines_are_dropped(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "requirements.txt"
            path.write_text("# a comment\n\nnumpy>=1.24,<3   # trailing\n", encoding="utf-8")
            self.assertEqual(bootstrap.requirement_specs(path), ["numpy>=1.24,<3"])

    def test_environment_markers_survive(self):
        # They are the reason one file serves Windows, macOS and Linux.
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "requirements.txt"
            path.write_text('comtypes;   sys_platform == "win32"\n', encoding="utf-8")
            specs = bootstrap.requirement_specs(path)
            self.assertEqual(len(specs), 1)
            self.assertIn('sys_platform == "win32"', specs[0])

    def test_the_real_file_yields_installable_specs(self):
        specs = bootstrap.requirement_specs(ROOT / "requirements.txt")
        self.assertGreater(len(specs), 30)
        self.assertIn("PyQt6", " ".join(specs))
        for spec in specs:
            self.assertFalse(spec.startswith("-"), f"{spec} is an option, not a package")
            self.assertTrue(bootstrap.distribution_name(spec))

    def test_a_distribution_name_survives_a_version_bound(self):
        self.assertEqual(bootstrap.distribution_name("PyQt6>=6.6,<6.12"), "PyQt6")
        self.assertEqual(bootstrap.distribution_name('wmi; sys_platform == "win32"'), "wmi")
        self.assertEqual(bootstrap.distribution_name("uvicorn[standard]>=0.27"), "uvicorn")


class StartupCheckTests(unittest.TestCase):
    def test_the_critical_list_is_read_out_of_main_py(self):
        # Not a hardcoded list: if main.py grows a top-level import, the check
        # follows it. numpy and sounddevice are the two it has today.
        imports = bootstrap.critical_imports()
        self.assertIn("numpy", imports)
        self.assertIn("sounddevice", imports)
        self.assertIn("PyQt6.QtWidgets", imports)

    def test_this_projects_own_packages_are_not_demanded_from_pip(self):
        imports = bootstrap.critical_imports()
        for local in ("core", "actions", "memory", "ui"):
            self.assertNotIn(local, imports)

    def test_a_module_that_imports_is_not_reported(self):
        self.assertEqual(bootstrap.missing_imports(["json", "pathlib"]), [])

    def test_every_broken_module_is_named_not_just_the_first(self):
        broken = bootstrap.missing_imports(["json", "definitely_not_installed_one",
                                           "definitely_not_installed_two"])
        self.assertEqual(broken, ["definitely_not_installed_one",
                                 "definitely_not_installed_two"])

    def test_an_empty_list_costs_nothing(self):
        self.assertEqual(bootstrap.missing_imports([]), [])


class FingerprintTests(unittest.TestCase):
    def test_editing_requirements_invalidates_the_marker(self):
        # Otherwise a new dependency would never be installed on an existing install.
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "requirements.txt"
            path.write_text("numpy\n", encoding="utf-8")
            before = bootstrap.ready_marker(path)
            path.write_text("numpy\nscipy\n", encoding="utf-8")
            self.assertNotEqual(before, bootstrap.ready_marker(path))

    def test_the_same_inputs_produce_the_same_marker(self):
        path = ROOT / "requirements.txt"
        self.assertEqual(bootstrap.ready_marker(path), bootstrap.ready_marker(path))


class EntryPointTests(unittest.TestCase):
    def test_it_refuses_to_install_outside_a_virtual_environment(self):
        with mock.patch.object(sys, "prefix", sys.base_prefix):
            self.assertEqual(bootstrap.main([]), 1)

    def test_it_refuses_a_python_it_does_not_support(self):
        with mock.patch.object(sys, "prefix", "/tmp/fake-venv"), \
             mock.patch.object(sys, "version_info", (3, 14, 0)):
            self.assertEqual(bootstrap.main([]), 1)

    def test_the_console_is_reconfigured_rather_than_allowed_to_crash(self):
        # A cp1251 console must not turn a status line into a UnicodeEncodeError
        # in the middle of an install.
        bootstrap.configure_console()  # must not raise on any stream shape
        with mock.patch.object(sys, "stdout", object()):
            bootstrap.configure_console()


class SkipBrowsersTests(unittest.TestCase):
    def test_the_escape_hatch_is_honoured(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "setup-log.txt"
            with (
                mock.patch.dict(os.environ, {"ULTRON_SKIP_BROWSERS": "1"}),
                mock.patch.object(bootstrap, "run_logged") as runner,
            ):
                bootstrap.install_browsers(log)
            runner.assert_not_called()

    def test_it_installs_them_when_asked_for(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "setup-log.txt"
            with (
                mock.patch.dict(os.environ, {"ULTRON_SKIP_BROWSERS": ""}),
                mock.patch.object(bootstrap, "run_logged", return_value=0) as runner,
            ):
                bootstrap.install_browsers(log)
            self.assertTrue(runner.called)


if __name__ == "__main__":
    unittest.main()
