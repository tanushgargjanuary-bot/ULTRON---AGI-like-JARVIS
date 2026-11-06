"""The workspace has a size, and the size is a number somebody looks at.

The failure this guards is not a bug in the app. A session installed the whole
dependency set inside the project folder instead of in `/tmp`, briefly wrote 375 MB
across 6,711 files, and the save that followed kept 128 MB and silently dropped 6,352
files. Nothing was on fire; a limit was simply discovered by crossing it.

So the ceiling is a test. The numbers below are deliberately under the platform's own
128 MB / 10,000 files, and they are checked against the project rather than against
somebody's `.venv`, which belongs to them.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "workspace_budget.py"

# Measured on 2026-11-06 after the clean-up: 8.9 MB across 336 files.
MB_CEILING = 20.0
FILE_CEILING = 900
BIGGEST_FILE_KB = 512

# One file is allowed to be heavy, and it is named here rather than waved through.
# `watchd-windows.exe` is the Windows background helper. The owner's machine has no Go
# toolchain, so if the built binary is not in the tree it does not exist — and the
# installer has nothing to ship. It is the payload, not build litter.
ALLOWED_BINARIES = {"sidecar/bin/watchd-windows.exe"}


def load_budget():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts import workspace_budget
    return workspace_budget


class TheMeasurement(unittest.TestCase):
    def setUp(self):
        self.budget = load_budget()

    def build(self, files: dict[str, int]) -> Path:
        folder = Path(tempfile.mkdtemp())
        for name, size in files.items():
            path = folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x" * size)
        self.addCleanup(lambda: __import__("shutil").rmtree(folder, ignore_errors=True))
        return folder

    def test_it_counts_files_and_bytes(self):
        folder = self.build({"a.py": 1000, "sub/b.py": 2000})
        report = self.budget.measure(folder)
        self.assertEqual(report["files"], 2)
        self.assertAlmostEqual(report["mb"], round(3000 / 1048576, 1), places=1)

    def test_a_generated_folder_is_reported_but_not_counted(self):
        # A user's .venv is theirs. Counting it would make the number meaningless and
        # the check would be switched off inside a week.
        folder = self.build({"main.py": 10, ".venv/lib/big.so": 5000})
        report = self.budget.measure(folder)
        self.assertEqual(report["files"], 1)
        self.assertEqual(report["generated_files"], 1)

    def test_the_report_says_which_folders_account_for_it(self):
        folder = self.build({"a/x.py": 300, "b/y.py": 100})
        report = self.budget.measure(folder)
        names = [row["name"] for row in report["folders"]]
        self.assertEqual(names[0], "a")

    def test_over_budget_is_stated_plainly(self):
        report = {"mb": 200.0, "files": 10, "generated_mb": 0, "generated_files": 0,
                  "folders": []}
        text = self.budget.render(report, 100.0, 5000)
        self.assertIn("OVER BUDGET", text)
        self.assertIn("/tmp", text, "the report should say what to do about it")

    def test_inside_budget_says_so(self):
        report = {"mb": 8.9, "files": 336, "generated_mb": 0, "generated_files": 0,
                  "folders": []}
        self.assertIn("inside budget", self.budget.render(report, 100.0, 5000))

    def test_it_finds_the_caches_it_is_allowed_to_delete(self):
        folder = self.build({"a.py": 10, "__pycache__/m.pyc": 10})
        found = [path.name for path in self.budget.cache_folders(folder)]
        self.assertEqual(found, ["__pycache__"])


class ThisProject(unittest.TestCase):
    """The ratchet: the project itself, on the machine that runs the tests."""

    @classmethod
    def setUpClass(cls):
        cls.budget = load_budget()
        cls.report = cls.budget.measure(ROOT)

    def test_the_project_is_well_under_the_platform_limit(self):
        self.assertLess(self.report["mb"], MB_CEILING,
                        f"the project is {self.report['mb']} MB; the ceiling is "
                        f"{MB_CEILING}")
        self.assertLess(self.report["files"], FILE_CEILING,
                        f"the project holds {self.report['files']} files")

    def test_no_single_tracked_file_is_a_binary_in_disguise(self):
        # Build output belongs in a build, not in the tree. The one 359 KB file is
        # ui.py, which is a real source file and the size of a screen.
        heavy = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts:
                continue
            if any(part in {"__pycache__", ".venv", "build", "dist"} for part in path.parts):
                continue
            if path.stat().st_size <= BIGGEST_FILE_KB * 1024:
                continue
            name = path.relative_to(ROOT).as_posix()
            if name in ALLOWED_BINARIES:
                continue
            heavy.append(f"{name} {path.stat().st_size // 1024} KB")
        self.assertEqual(heavy, [], "a file this big belongs in a release, not the tree")

    def test_the_script_reports_the_same_number_it_is_tested_with(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--json"],
                                capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr[-400:])
        report = json.loads(result.stdout)
        self.assertEqual(report["files"], self.report["files"])
        self.assertLess(report["mb"], 100)


if __name__ == "__main__":
    unittest.main()
