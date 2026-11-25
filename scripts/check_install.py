"""Is everything in requirements.txt really installed in this environment?

`scripts/bootstrap.py` installs requirements.txt and then checks only that the few modules `main.py` imports at start-up
load. On purpose it lets an optional package fail to install and still exits 0 ("one optional package must never be able to
stop the app"). That is right for a person starting the app and wrong for a check of the file itself: a package that did not
install on Windows with Python 3.13 would leave the check green.

This asks pip what it would still install (`pip install --dry-run --report`). Nothing means every line that applies on this
platform and this Python is satisfied. Then it asks `pip check` whether what is installed agrees with itself.

    python scripts/check_install.py       # exit 0: everything installed and consistent; 1: say what is not

It installs nothing. `.github/workflows/install-check.yml` runs it after the launcher's own setup, on Windows for each Python
the launcher accepts. tests/test_check_install.py drives it with a stand-in for pip.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIME_LIMIT = 900        # seconds, for either pip call: a stuck download must not hold a runner for hours


def run_pip(args: list[str]) -> tuple[int, str]:
    """pip, run by this interpreter, with its whole output kept: (exit code, what it printed)."""
    try:
        done = subprocess.run(
            [sys.executable, "-m", "pip", *args],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIME_LIMIT,
        )
    except subprocess.TimeoutExpired:
        return 124, f"pip did not finish in {TIME_LIMIT} seconds."
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def still_to_install(report: dict) -> list[str]:
    """The packages (name and version) that `pip install --report` says it would still install."""
    todo = []
    for item in report.get("install", []):
        meta = item.get("metadata", {})
        todo.append(f"{meta.get('name', '?')} {meta.get('version', '')}".strip())
    return todo


def main() -> int:
    requirements = ROOT / "requirements.txt"
    with tempfile.TemporaryDirectory() as folder:
        report_path = Path(folder) / "report.json"
        code, said = run_pip(["install", "--dry-run", "--quiet", "--disable-pip-version-check", "--no-input",
                              "--report", str(report_path), "-r", str(requirements)])
        if code != 0:
            print(said.strip()[-4000:])
            print("\npip could not work out what to install from requirements.txt here.")
            return 1
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            print(f"pip wrote no readable report ({error}).")
            return 1

    todo = still_to_install(report)
    if todo:
        print("requirements.txt is NOT fully installed here. pip would still install:")
        for name in todo:
            print(f"  - {name}")
        return 1
    print("Every line of requirements.txt that applies here is installed.")

    code, said = run_pip(["check", "--disable-pip-version-check"])
    print(said.strip())
    if code != 0:
        print("\nThe installed packages do not agree with each other (pip check, above).")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
