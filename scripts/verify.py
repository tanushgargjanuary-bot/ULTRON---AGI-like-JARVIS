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
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    stray_before = set(_stray_host_files())
    checks = [
        (
            "Custom and ported regression suite",
            ["-m", "unittest", "discover", "-s", "tests"],
        ),
        ("MARK upstream provider/UI self-tests", ["-m", "providers._tests"]),
        ("1,000 offline stress scenarios", ["scripts/stress_custom.py"]),
        ("15 targeted seeded mutations", ["scripts/check_mutations.py"]),
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
