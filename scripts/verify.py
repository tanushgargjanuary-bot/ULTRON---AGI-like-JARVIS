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
    """
    stray = []
    if USER_CONFIG.exists() and not USER_CONFIG.read_bytes().strip() == b"":
        stray.append(str(USER_CONFIG.relative_to(ROOT)))
    for pattern in ("api_keys.json.tmp", "api_keys.json.broken-*", "setup-log.txt"):
        for path in (ROOT / "config").glob(pattern):
            stray.append(str(path.relative_to(ROOT)))
    return stray


def _count_lines(root):
    total = 0
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in
                   {".git", ".venv", "__pycache__", ".ruff_cache", ".hypothesis"}]
        for filename in files:
            if filename.endswith(".py"):
                total += len((Path(folder) / filename).read_text(
                    encoding="utf-8-sig", errors="replace").splitlines())
    return total


def refresh_readme_sizes(files):
    """Files and lines are facts about the tree, true before anything runs.

    They must be written before the suite, because the suite contains a test that
    compares them. The TEST count is different — it depends on which modules import
    cleanly — so it is written afterwards, and only if every check passed.
    """
    import re
    readme = Path(ROOT) / "readme.md"
    if not readme.exists():
        return
    text = readme.read_text(encoding="utf-8")
    found = re.search(r"\*\*(\d+) Python files\. ([\d,]+) lines\.", text)
    if found is None:
        return
    lines = f"{_count_lines(ROOT):,}"
    if found.group(1) == str(files) and found.group(2) == lines:
        return
    replaced = text.replace(found.group(0), f"**{files} Python files. {lines} lines.",
                            1)
    readme.write_text(replaced, encoding="utf-8")
    print(f"Readme sizes refreshed: {files} Python files, {lines} lines.", flush=True)


def refresh_readme_numbers(files):
    """Keep the page's numbers true, in the one place that knows them.

    The page states three numbers: Python files, lines, tests. Two of them are
    facts about this tree and one — the test count — depends on which optional
    packages are installed, because several tests exist only to check what happens
    when a package is MISSING. So the number is not stable across machines, and a
    hand-maintained copy is wrong the moment either one changes.

    verify.py therefore owns that line: it counts, compares, rewrites, and says
    what it changed. A red build then means the code is wrong, not that someone
    forgot to edit a number.
    """
    import re
    import unittest
    readme = Path(ROOT) / "readme.md"
    if not readme.exists():
        return
    loader = unittest.defaultTestLoader
    tests_dir = str(Path(ROOT) / "tests")
    # Same two paths the command line uses: the project as the import root, and the
    # test folder as its own start directory. Getting this wrong raises
    # "Start directory is not importable", which is what the first version did.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    suite = loader.discover(tests_dir, top_level_dir=tests_dir)
    tests = suite.countTestCases()
    lines = _count_lines(ROOT)
    text = readme.read_text(encoding="utf-8")
    current = re.search(r"\*\*\d+ Python files\..*?(\d[\d,]*) tests\.\*\*", text)
    previous = int(current.group(1).replace(",", "")) if current else 0
    # A guard, learned from a real failure: an environment missing one shared
    # library lost eighty-five tests to an import error, and the first version of
    # this function wrote that smaller number onto the page as if it were the truth.
    # A collapse is an environment problem, so the page is left exactly as it is.
    if previous and tests < previous * 0.9:
        print(f"Readme test count NOT refreshed: this run collected {tests:,} tests "
              f"against {previous:,} on the page — that gap means modules failed to "
              f"import, not that tests were removed.", flush=True)
        return
    new = f"**{files} Python files. {lines:,} lines. {tests:,} tests.**"
    found = re.search(r"\*\*\d+ Python files\..*?tests\.\*\*", text)
    if found is None:
        return
    if found.group(0) != new:
        readme.write_text(text.replace(found.group(0), new, 1), encoding="utf-8")
        print(f"Readme numbers refreshed: {new.strip('*')}", flush=True)


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
    refresh_readme_sizes(count)
    # Before the suite, because the suite contains the test that compares this
    # number to the page. The collapse guard inside makes that safe.
    refresh_readme_numbers(count)
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    stray_before = set(_stray_host_files())
    checks = [
        # First, because a workspace that is over budget loses files on the next save,
        # and a lost file makes every check below a test of a tree that no longer exists.
        ("Workspace size and file count", ["scripts/workspace_budget.py"]),
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
