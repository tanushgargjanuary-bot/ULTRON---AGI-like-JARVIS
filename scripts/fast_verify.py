"""Fast, offline verification for every branch update.

Run: python scripts/fast_verify.py

This preflight complements, but does not replace, scripts/verify.py. It checks every
tracked or untracked, non-ignored Python source file for syntax errors, runs focused
regressions, and repeats deterministic repair stress cases. It makes no live model
or provider requests.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
CHECK_TIMEOUT_SECONDS = 180


def decode_git_paths(data: bytes) -> list[str]:
    """Decode Git's NUL-delimited paths without splitting unusual filenames."""
    if not data:
        return []
    if not data.endswith(b"\0"):
        raise ValueError("Git path output is not NUL-terminated")

    raw_paths = data[:-1].split(b"\0")
    if any(not raw for raw in raw_paths):
        raise ValueError("Git returned an empty path entry")

    try:
        return [raw.decode("utf-8", errors="strict") for raw in raw_paths]
    except UnicodeDecodeError as error:
        raise ValueError("Git returned a path that is not valid UTF-8") from error


def _parse_python_path(name: str) -> PurePosixPath:
    """Reject non-canonical or platform-specific paths before filesystem access."""
    parts = name.split("/")
    invalid = (
        not name
        or "\\" in name
        or name.startswith("/")
        or any(part in ("", ".", "..") for part in parts)
        or (len(parts[0]) >= 2 and parts[0][1] == ":")
    )
    if invalid:
        raise ValueError(f"Unsafe tracked Python path: {name!r}")

    relative = PurePosixPath(name)
    if relative.is_absolute():
        raise ValueError(f"Unsafe tracked Python path: {name!r}")
    return relative


def _resolve_python_path(
    root: Path,
    relative: PurePosixPath,
    display_name: str,
) -> Path:
    """Resolve one source file and reject symlinks or escapes from the repository."""
    candidate = root.joinpath(*relative.parts)
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError(f"Python source path traverses a symlink: {display_name}")

    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ValueError(
            f"Tracked Python file is missing or unsafe: {display_name}"
        ) from error

    if not resolved.is_relative_to(root):
        raise ValueError(f"Python source escapes the repository: {display_name}")
    if not resolved.is_file():
        raise ValueError(f"Tracked Python path is not a file: {display_name}")
    return resolved


def resolve_python_files(root: Path, names: list[str]) -> list[Path]:
    """Resolve Python paths safely and reject traversal, duplicates, or symlinks."""
    base = root.resolve(strict=True)
    files: list[Path] = []
    seen: set[str] = set()

    for name in names:
        if not name.endswith(".py"):
            continue
        relative = _parse_python_path(name)
        if name in seen:
            raise ValueError(f"Duplicate tracked Python path: {name!r}")
        seen.add(name)
        files.append(_resolve_python_path(base, relative, name))

    if not files:
        raise ValueError("Git reported no Python source files to verify")
    return files


def syntax_errors(root: Path, files: list[Path]) -> list[str]:
    """Parse selected Python files without importing or executing them."""
    errors: list[str] = []
    base = root.resolve()
    for path in files:
        try:
            source = path.read_text(encoding="utf-8-sig")
            ast.parse(source, filename=str(path.relative_to(base)))
        except SyntaxError as error:
            errors.append(
                f"{path.relative_to(base)}:{error.lineno}:{error.offset}: "
                f"{error.msg}"
            )
        except (OSError, UnicodeError) as error:
            errors.append(f"{path.relative_to(base)}: cannot read source: {error}")
    return errors


def run_check(
    name: str,
    command: list[str],
    *,
    root: Path = ROOT,
    env: dict[str, str] | None = None,
    timeout: int = CHECK_TIMEOUT_SECONDS,
) -> bool:
    """Run one command without a shell and fail on error, launch failure, or timeout."""
    started = time.monotonic()
    print(f"\n=== RUN: {name} ===", flush=True)
    print("$ " + " ".join(command), flush=True)
    try:
        result = subprocess.run(
            command,
            cwd=root,
            env=env,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - started
        print(f"FAIL: {name} timed out after {timeout}s ({elapsed:.2f}s)", flush=True)
        return False
    except OSError as error:
        elapsed = time.monotonic() - started
        print(f"FAIL: {name} could not start: {error} ({elapsed:.2f}s)", flush=True)
        return False

    elapsed = time.monotonic() - started
    if result.returncode != 0:
        print(f"FAIL: {name} exited with {result.returncode} ({elapsed:.2f}s)", flush=True)
        return False
    print(f"PASS: {name} ({elapsed:.2f}s)", flush=True)
    return True


def discover_python_files() -> list[Path]:
    """Read the repository inventory from Git and resolve all Python source paths."""
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("Git could not list repository files")
    names = decode_git_paths(result.stdout)
    return resolve_python_files(ROOT, names)


def run_fast_checks(environment: dict[str, str]) -> list[bool]:
    """Run the focused test groups and deterministic stress suite in order."""
    checks = [
        (
            "fast-runner edge tests",
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests",
                "-p",
                "test_fast_verify.py",
                "-q",
            ],
            60,
        ),
        (
            "policy and confirmation regressions",
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests",
                "-p",
                "test_policy.py",
                "-q",
            ],
            120,
        ),
        (
            "README contract regressions",
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests",
                "-p",
                "test_readme.py",
                "-q",
            ],
            60,
        ),
        (
            "seeded repair and boundary stress",
            [sys.executable, "scripts/stress_custom.py"],
            180,
        ),
    ]
    return [
        run_check(name, command, root=ROOT, env=environment, timeout=timeout)
        for name, command, timeout in checks
    ]


def report_summary(
    results: list[bool],
    parse_errors: list[str],
    file_count: int,
    elapsed: float,
) -> bool:
    """Print a stable summary and return the gate verdict."""
    passed = sum(results) + (not bool(parse_errors))
    total = len(results) + 1
    ok = all(results) and not parse_errors
    print("\n=== FAST GATE SUMMARY ===", flush=True)
    print(f"Verdict: {'PASS' if ok else 'FAIL'}", flush=True)
    print(f"Checks: {passed}/{total} passed", flush=True)
    print(f"Python files parsed: {file_count}", flush=True)
    print(f"Elapsed: {elapsed:.2f}s", flush=True)
    print("External provider/model requests: 0", flush=True)
    return ok


def main() -> int:
    """Run source validation and every fast regression group."""
    started = time.monotonic()
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["QT_QPA_PLATFORM"] = "offscreen"

    print("ULTRON fast branch gate", flush=True)
    print("Scope: offline syntax, focused regression, and deterministic stress.", flush=True)
    try:
        files = discover_python_files()
    except (OSError, RuntimeError, ValueError) as error:
        print(f"FAIL: Python source inventory is unsafe or incomplete: {error}", flush=True)
        return 1

    parse_errors = syntax_errors(ROOT, files)
    if parse_errors:
        print(f"FAIL: syntax check found {len(parse_errors)} issue(s):", flush=True)
        for error in parse_errors:
            print(f"  {error}", flush=True)
    else:
        print(f"PASS: syntax parsed {len(files)} Python file(s).", flush=True)

    results = run_fast_checks(environment)
    elapsed = time.monotonic() - started
    return 0 if report_summary(results, parse_errors, len(files), elapsed) else 1


if __name__ == "__main__":
    raise SystemExit(main())
