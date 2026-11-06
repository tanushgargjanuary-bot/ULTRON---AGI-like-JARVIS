"""tests/test_launchers.py — the PowerShell entry points.

A launcher is the first thing anyone touches and the only part of this project with
no Python in it, so it gets no test coverage from the rest of the suite. Two layers
here:

  1. Static checks that always run: the files exist, they are CRLF with plain ASCII
     (Windows PowerShell 5.1 mis-reads UTF-8 without a BOM), they name the scripts
     they claim to launch, and they never claim to do more than that.
  2. Live checks that run only where PowerShell is installed: the file parses with
     PowerShell's own parser, and collect-data.ps1 actually runs the collector and
     returns its exit code. On a machine with no PowerShell these are skipped rather
     than failed, because a missing tool is not a defect in the file.

The static layer is deliberately not a regex snapshot of the whole file. It asserts
the properties that would break the launcher: wrong line endings, a non-ASCII byte,
a launcher pointed at a script that does not exist.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")

LAUNCHERS = {
    "collect-data.ps1": "collect_install.py",
    "run.ps1": "bootstrap.py",
}


def read_bytes(name: str) -> bytes:
    return (ROOT / name).read_bytes()


class StaticLauncherTests(unittest.TestCase):
    def test_the_launchers_exist(self):
        for name in LAUNCHERS:
            with self.subTest(name=name):
                self.assertTrue((ROOT / name).is_file(), f"{name} is missing")

    def test_the_launchers_use_windows_line_endings(self):
        for name in LAUNCHERS:
            with self.subTest(name=name):
                data = read_bytes(name)
                self.assertIn(b"\r\n", data)
                # A bare LF is legal in PowerShell but shows up as a stray carriage
                # return in older editors and can break naive concatenation.
                self.assertEqual(data.count(b"\n"), data.count(b"\r\n"), f"{name} has a bare LF")

    def test_the_launchers_are_plain_ascii(self):
        # PowerShell 5.1 reads a BOM-less file as the system codepage. A typographic
        # dash in a comment can therefore be a parse error on a non-UTF-8 box.
        for name in LAUNCHERS:
            with self.subTest(name=name):
                data = read_bytes(name)
                bad = [(i, b) for i, b in enumerate(data) if b > 127]
                self.assertEqual(bad, [], f"{name} has non-ASCII bytes at {bad[:5]}")

    def test_the_launchers_point_at_scripts_that_exist(self):
        for name, script in LAUNCHERS.items():
            with self.subTest(name=name):
                self.assertTrue(any((ROOT / "scripts").glob(f"**/{script}")))
                self.assertIn(script, read_bytes(name).decode("ascii"))

    def test_the_collector_launcher_needs_no_third_party_package(self):
        # It may be run on a bare machine before .venv exists, so it must not
        # install or import anything the standard library does not provide.
        # (Comment text may mention a package; only real commands matter.)
        code = [
            line.lower()
            for line in read_bytes("collect-data.ps1").decode("ascii").splitlines()
            if not line.strip().startswith("#") and not line.strip().startswith(".")
        ]
        for forbidden in ("pip install", "import-module", "install-module", "install-package"):
            with self.subTest(forbidden=forbidden):
                self.assertFalse(
                    any(forbidden in line for line in code), f"{forbidden} in the collector launcher"
                )

    def test_the_launchers_document_the_execution_policy_trap(self):
        # The single most common reason a .ps1 "does not work" on Windows.
        for name in LAUNCHERS:
            with self.subTest(name=name):
                text = read_bytes(name).decode("ascii")
                self.assertIn("ExecutionPolicy", text)
                self.assertIn("Unblock-File", text)


@unittest.skipUnless(POWERSHELL, "PowerShell is not installed here")
class LiveLauncherTests(unittest.TestCase):
    def run_pwsh(
        self, *arguments: str, cwd: Path = ROOT, env: dict | None = None
    ) -> subprocess.CompletedProcess:
        return subprocess.run(
            [POWERSHELL, "-NoLogo", "-NoProfile", "-NonInteractive", *arguments],
            check=False,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=120,
            # stdin closed on purpose: the launchers pause on a non-zero exit when
            # the console is interactive, and on Windows a test runner's console
            # *is* interactive, so without this the failure path would block on
            # Read-Host forever instead of returning its exit code.
            stdin=subprocess.DEVNULL,
            env=dict(os.environ, **(env or {})),
        )

    def test_both_launchers_parse(self):
        # The path travels in an environment variable: `pwsh -Command` concatenates
        # anything after the command text into the command itself, so a positional
        # argument would be pasted onto the end of the expression.
        script = (
            "$tokens = $null; $errors = $null; "
            "[void][System.Management.Automation.Language.Parser]::ParseFile("
            "$env:ULTRON_TEST_TARGET, [ref]$tokens, [ref]$errors); "
            "if ($errors.Count -gt 0) { $errors[0].Message; exit 1 }; exit 0"
        )
        for name in LAUNCHERS:
            with self.subTest(name=name):
                done = self.run_pwsh(
                    "-Command", script, env={"ULTRON_TEST_TARGET": str(ROOT / name)}
                )
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_the_collector_launcher_runs_the_collector(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "memory").mkdir()
            (root / "memory" / "long_term.json").write_text('{"identity": ["sir"]}', encoding="utf-8")
            (root / "main.py").write_text("x = 1\n", encoding="utf-8")

            done = self.run_pwsh(
                "-File", str(ROOT / "collect-data.ps1"), "--path", str(root)
            )
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn("files:", done.stdout)
            self.assertIn("long_term.json", done.stdout)

    def test_the_collector_launcher_passes_the_exit_code_through(self):
        # A refusal must stay a refusal after the wrapper: exit 2 from the collector
        # has to reach the caller, or a script that checks $LASTEXITCODE is misled.
        done = self.run_pwsh(
            "-File", str(ROOT / "collect-data.ps1"), "--path", "/definitely/not/here"
        )
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)

    def test_a_missing_collector_is_reported_not_ignored(self):
        with tempfile.TemporaryDirectory() as temp:
            stray = Path(temp) / "collect-data.ps1"
            stray.write_bytes(read_bytes("collect-data.ps1"))
            done = self.run_pwsh("-File", str(stray))
            self.assertEqual(done.returncode, 3, done.stdout + done.stderr)
            self.assertIn("collect_install.py is missing", done.stdout)

    def test_the_app_launcher_refuses_an_incomplete_folder(self):
        # Extracting a ZIP into the wrong place, or half-extracting it, is common.
        # It must say so plainly instead of starting a broken environment.
        with tempfile.TemporaryDirectory() as temp:
            stray = Path(temp) / "run.ps1"
            stray.write_bytes(read_bytes("run.ps1"))
            done = self.run_pwsh("-File", str(stray))
            self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
            self.assertIn("Extract the complete ZIP", done.stdout)


if __name__ == "__main__":
    unittest.main()
