"""tests/test_check_install.py — the check that says whether requirements.txt really installed.

`scripts/bootstrap.py` installs requirements.txt and then checks only that the few modules `main.py` imports at start-up
load. On purpose it lets an optional package fail to install and still exits 0 ("one optional package must never be able to
stop the app"). That is right for a person starting the app and wrong for a check of the file itself: a package that did not
install on Windows with Python 3.13 would leave the check green.

`scripts/check_install.py` asks pip what it would still install (`pip install --dry-run --report`): nothing means every line
that applies here is satisfied. Then it asks `pip check` whether what is installed agrees with itself. These tests drive it
with a stand-in for pip, so they need no network and install nothing.
"""

from __future__ import annotations

import importlib
import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

check_install = importlib.import_module("scripts.check_install")


def entry(name: str, version: str = "1.0") -> dict:
    return {"metadata": {"name": name, "version": version}}


class APip:
    """A stand-in for `python -m pip`: what it would install, what `pip check` says, and what it was asked."""

    def __init__(self, would_install=(), dry_run_code=0, dry_run_text="", check_code=0, check_text="No broken requirements found.",
                 write_report=True):
        self.would_install = list(would_install)
        self.dry_run_code, self.dry_run_text = dry_run_code, dry_run_text
        self.check_code, self.check_text = check_code, check_text
        self.write_report = write_report
        self.calls: list[list[str]] = []

    def __call__(self, args):
        self.calls.append(list(args))
        if args[0] == "check":
            return self.check_code, self.check_text
        if self.write_report and "--report" in args:
            report = {"version": "1", "install": [entry(*item) for item in self.would_install]}
            Path(args[args.index("--report") + 1]).write_text(json.dumps(report), encoding="utf-8")
        return self.dry_run_code, self.dry_run_text


def run_main(pip: APip) -> tuple[int, str]:
    out = io.StringIO()
    with mock.patch.object(check_install, "run_pip", pip), redirect_stdout(out):
        code = check_install.main()
    return code, out.getvalue()


class StillToInstall(unittest.TestCase):
    def test_an_empty_report_means_nothing_is_left(self):
        self.assertEqual(check_install.still_to_install({"version": "1", "install": []}), [])

    def test_a_report_with_no_install_list_means_nothing_is_left(self):
        self.assertEqual(check_install.still_to_install({"version": "1"}), [])

    def test_each_package_is_named_with_its_version(self):
        report = {"install": [entry("numpy", "2.4.6"), entry("pyautogui", "0.9.54")]}
        self.assertEqual(check_install.still_to_install(report), ["numpy 2.4.6", "pyautogui 0.9.54"])

    def test_an_entry_without_metadata_is_still_reported(self):
        self.assertEqual(check_install.still_to_install({"install": [{}]}), ["?"])


class Main(unittest.TestCase):
    def test_everything_installed_and_consistent_passes(self):
        code, said = run_main(APip())
        self.assertEqual(code, 0, said)
        self.assertIn("Every line of requirements.txt that applies here is installed", said)

    def test_one_package_left_to_install_fails_and_names_it(self):
        code, said = run_main(APip(would_install=[("win10toast", "0.9")]))
        self.assertEqual(code, 1)
        self.assertIn("win10toast 0.9", said)
        self.assertIn("NOT fully installed", said)

    def test_a_file_pip_cannot_resolve_fails_and_shows_pips_own_words(self):
        said_by_pip = "ERROR: No matching distribution found for numpy<3,>=2.5.5"
        code, said = run_main(APip(dry_run_code=1, dry_run_text=said_by_pip, write_report=False))
        self.assertEqual(code, 1)
        self.assertIn(said_by_pip, said)

    def test_a_report_that_was_not_written_fails(self):
        code, said = run_main(APip(write_report=False))
        self.assertEqual(code, 1)
        self.assertIn("no readable report", said)

    def test_packages_that_disagree_with_each_other_fail(self):
        broken = "google-genai 3.6.1 has requirement websockets<15, but you have websockets 15.1."
        code, said = run_main(APip(check_code=1, check_text=broken))
        self.assertEqual(code, 1)
        self.assertIn(broken, said)
        self.assertIn("do not agree", said)

    def test_it_asks_about_requirements_txt_and_nothing_else_and_asks_before_it_checks(self):
        pip = APip()
        run_main(pip)
        first, second = pip.calls
        self.assertEqual(first[:2], ["install", "--dry-run"], "nothing may actually be installed by a check")
        self.assertEqual(first[first.index("-r") + 1], str(ROOT / "requirements.txt"))
        self.assertEqual(second[0], "check")

    def test_a_package_left_to_install_is_not_hidden_by_a_clean_pip_check(self):
        code, _ = run_main(APip(would_install=[("pyperclip", "1.11.0")], check_code=0))
        self.assertEqual(code, 1)


class RunningPip(unittest.TestCase):
    def test_pip_is_run_by_this_interpreter_with_a_time_limit_and_its_output_kept(self):
        done = subprocess.CompletedProcess([], 0, stdout="out\n", stderr="err\n")
        with mock.patch.object(check_install.subprocess, "run", return_value=done) as run:
            code, text = check_install.run_pip(["check"])
        command = run.call_args.args[0]
        self.assertEqual(command[:3], [sys.executable, "-m", "pip"])
        self.assertGreater(run.call_args.kwargs["timeout"], 0)
        self.assertNotEqual(run.call_args.kwargs.get("stdout"), subprocess.DEVNULL)
        self.assertEqual((code, text), (0, "out\nerr\n"))

    def test_a_pip_that_never_finishes_is_a_failure_that_says_so(self):
        stuck = subprocess.TimeoutExpired(cmd="pip", timeout=1)
        with mock.patch.object(check_install.subprocess, "run", side_effect=stuck):
            code, text = check_install.run_pip(["install"])
        self.assertNotEqual(code, 0)
        self.assertIn("did not finish", text)


if __name__ == "__main__":
    unittest.main()
