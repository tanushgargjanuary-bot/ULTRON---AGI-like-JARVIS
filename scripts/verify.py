"""Offline migration verification; never starts a voice session or contacts a provider.

Install requirements.txt and requirements-dev.txt first.
Run: python scripts/verify.py > verification-results.txt 2>&1
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# The real config file: the one the user's providers and window size live in.
USER_CONFIG = ROOT / "config" / "api_keys.json"


def _stray_host_files():
    """Files the suite must never leave in the project.

    A test that builds a real MainWindow saves the window size, and saving it goes
    to config/api_keys.json — the user's own file. Measured before this check
    existed: the suite created one here, containing the test's 1600x900. Run on a
    real installation, that is somebody's remembered window size and, on the
    read-modify-write path, a file written beside the one holding their keys.

    Names are returned with forward slashes on every system. On Windows `str(relative_to)` gives
    `config\\api_keys.json`, and the tests (and the person reading the report) compare with
    `config/api_keys.json`; the first Windows run of this check failed four tests on exactly that.
    """
    stray = []
    if USER_CONFIG.exists() and not USER_CONFIG.read_bytes().strip() == b"":
        stray.append(USER_CONFIG.relative_to(ROOT).as_posix())
    # `api_keys.json.<random>.tmp` is what `memory/config_manager.py` writes before it
    # replaces the file (a name of its own per write, so two writers never share one);
    # the old fixed `api_keys.json.tmp` is kept in the list for trees from before that.
    for pattern in ("api_keys.json.tmp", "api_keys.json.*.tmp", "api_keys.json.broken-*",
                    "setup-log.txt"):
        for path in (ROOT / "config").glob(pattern):
            stray.append(path.relative_to(ROOT).as_posix())
    # The memory store's own: the copy it sets aside when the store will not parse, and the
    # temporary file of a write that was cut short. Each is a copy of everything the user asked
    # to be remembered, so a suite that leaves one in a real folder has leaked it.
    for pattern in ("long_term.json.broken-*", ".long_term.json.*.tmp"):
        for path in (ROOT / "memory").glob(pattern):
            stray.append(path.relative_to(ROOT).as_posix())
    return stray


def step_environment() -> dict:
    """What every step of the chain runs with.

    A step that dies of a native crash (a segmentation fault in Qt, an access violation on Windows) used to
    leave one line, `exit -11`, and the end of whatever its output had been flushed: standard output to a
    pipe is block-buffered, so that end was an arbitrary eight kilobytes before the crash. The hosted run of
    the merge of pull request #22 on `main` ended that way in the UI self-tests, on a tree that had passed
    the same step three times. `PYTHONFAULTHANDLER` makes Python print where the crash happened, and
    `PYTHONUNBUFFERED` makes the output stop where the crash did.
    """
    return dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONFAULTHANDLER="1", PYTHONUNBUFFERED="1")


def main():
    count = 0
    for folder, dirs, files in os.walk(ROOT):
        dirs[:] = [
            d
            for d in dirs
            if d not in {".git", ".venv", "__pycache__", ".ruff_cache", ".hypothesis"}
        ]
        for filename in files:
            if filename.endswith(".py"):
                path = Path(folder) / filename
                ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
                count += 1
    print(f"Syntax parsed {count} Python files.", flush=True)
    # The front page no longer states file, line or test counts (`tests/test_readme.py`
    # forbids them: they differ by machine). Two functions here used to keep those
    # numbers true; their pattern matched nothing on the page, yet the second one
    # still imported every test module in this process, once, to count them — on
    # every run, including each self-change rehearsal that runs this script.
    environment = step_environment()
    stray_before = set(_stray_host_files())
    checks = [
        (
            "Custom and ported regression suite",
            ["-m", "unittest", "discover", "-s", "tests"],
        ),
        ("MARK upstream provider/UI self-tests", ["-m", "providers._tests"]),
        ("1,000 offline stress scenarios", ["scripts/stress_custom.py"]),
        ("15 targeted seeded mutations", ["scripts/check_mutations.py"]),
        # Organisation is a check, not a hope: every module in the folders this
        # project owns must have a docstring and a test that names it.
        ("module map and organisation", ["scripts/map.py"]),
    ]
    for title, args in checks:
        print("\n=== " + title + " ===", flush=True)
        result = subprocess.run(
            [sys.executable, *args], cwd=ROOT, env=environment, check=False
        )
        if result.returncode:
            print(f"FAILED: {title} (exit {result.returncode})", flush=True)
            return result.returncode
    stray_after = set(_stray_host_files()) - stray_before
    if stray_after:
        print("\nFAILED: the suite left files in the project it must not touch:", flush=True)
        for name in sorted(stray_after):
            print(f"  {name}", flush=True)
        print("  A test is writing the user's real config. Point config_manager at a "
              "temporary directory in that test module's setUpModule().", flush=True)
        return 3
    print(
        "\nAll migration checks passed. This suite exercises the app in-process on "
        "this machine: provider transport against a local fake server, memory, "
        "actions, gates and the UI tree. It does NOT prove native Windows "
        "behaviour, a real microphone or speaker, screen capture, or a real "
        "browser. Run scripts/verify_all.py on the target machine for those — it "
        "reports SKIP where a question does not apply instead of guessing.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
