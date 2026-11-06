"""Local setup for the Ultron launcher — everything lands inside .venv.

run.bat and run.ps1 call this before the app starts, so that "double-click and it
works" is true on a machine that has never seen this project. Three jobs:

  1. Install requirements.txt. One optional package must never be able to stop
     the app: if the whole-file install fails, every requirement is retried on
     its own and whatever is still missing is reported by name, with the feature
     it belongs to, instead of as a pip exit code in a closed window.
  2. Prove the app can start. The third-party modules main.py imports at module
     level are imported here, in a subprocess, so a broken install fails in this
     window with one readable sentence rather than a traceback inside the HUD.
  3. Fetch the Playwright browsers. Skiddable on purpose: set ULTRON_SKIP_BROWSERS=1
     to start the app now and download the browser engines later.

The outcome is cached in .venv/.ultron-ready, keyed by a hash of requirements.txt,
the Python version and this file's own version, so every later launch skips
straight to the app. Nothing is installed outside .venv.

setup.py still exists and still does the same install for someone who wants to run
it by hand; this file is the version that also logs, recovers per package and
checks the result. Keep the two policies in step: a package added to
requirements.txt is added once, not twice.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Bumped when this file's own logic changes, so an existing install re-runs it.
_VERSION = b"ultron-bootstrap-v2"

LOG_PATH = ROOT / "setup-log.txt"
MARKER_NAME = ".ultron-ready"

MIN_PY = (3, 11)
MAX_PY = (3, 13)

# The GUI toolkit is not a top-level import of main.py (ui.py owns it) and the
# HUD cannot start without it, so it is named here rather than derived.
_EXTRA_CRITICAL = ("PyQt6.QtWidgets",)

_SKIP_BROWSERS = "ULTRON_SKIP_BROWSERS"


def configure_console() -> None:
    """Never die on a console that cannot encode the message.

    A legacy Windows code page turns the wrong character into UnicodeEncodeError
    in the middle of an install, which reads as "setup is broken" when nothing is.
    """
    for stream in ("stdout", "stderr"):
        handle = getattr(sys, stream, None)
        try:
            if handle is not None and hasattr(handle, "reconfigure"):
                handle.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001, S110 - pythonw, pipes, anything exotic
            pass  # never fatal: a console that cannot be fixed is still a console


# ── requirements.txt ─────────────────────────────────────────────────────────


def requirement_specs(path: Path) -> list[str]:
    """One installable spec per line, comments and blank lines stripped.

    Environment markers are kept: `comtypes; sys_platform == "win32"` is pip's,
    and it is what makes one requirements file serve every OS.
    """
    specs = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            specs.append(line)
    return specs


def distribution_name(spec: str) -> str:
    """`PyQt6>=6.6,<6.12` -> `PyQt6`. Used only when naming a failure."""
    return re.split(r"[<>=!~\[;\s]", spec, maxsplit=1)[0].strip()


# ── running things ───────────────────────────────────────────────────────────


def run_logged(args: list[str], log_path: Path, *, echo: bool = True) -> int:
    """Run a command, stream its output, and keep it in setup-log.txt.

    Streamed rather than captured so a ten-minute download looks like a
    ten-minute download and not like a hang.
    """
    with log_path.open("a", encoding="utf-8", errors="replace") as log:
        log.write("\n$ " + " ".join(args) + "\n")
        log.flush()
        try:
            process = subprocess.Popen(
                args,
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except OSError as exc:
            message = f"could not run {args[0]}: {exc}"
            print(message)
            log.write(message + "\n")
            return 1
        assert process.stdout is not None
        for line in process.stdout:
            log.write(line)
            if echo:
                print(line, end="", flush=True)
        return process.wait()


def _pip(*args: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        *args,
    ]


def install_requirements(log_path: Path) -> list[str]:
    """Install every requirement. Returns the specs that would not install.

    The one-shot attempt comes first because the resolver is faster and better
    at shared dependencies. The per-spec pass only exists for the case where one
    package fails and takes the other forty with it.
    """
    requirements = ROOT / "requirements.txt"
    if not requirements.is_file():
        print("requirements.txt is missing — the folder was not extracted completely.")
        return ["requirements.txt"]

    print("\n== Installing Python packages (this is the slow part, once only) ==", flush=True)
    if run_logged(_pip("-r", str(requirements)), log_path) == 0:
        return []

    print("\nThe whole-file install failed. Retrying one package at a time so a"
          "\nsingle failure does not take the other packages down with it.\n", flush=True)
    failed = []
    for spec in requirement_specs(requirements):
        if run_logged(_pip(spec), log_path, echo=False) != 0:
            failed.append(spec)
            print(f"  skipped: {spec}", flush=True)
    if failed:
        print(f"\n{len(failed)} package(s) did not install:", flush=True)
        for spec in failed:
            print(f"  - {spec}", flush=True)
        print("The parts of the app that need them stay switched off; the rest runs."
              "\nFull pip output is in setup-log.txt.", flush=True)
    return failed


def critical_imports() -> list[str]:
    """Third-party modules main.py imports at module level, plus the GUI toolkit.

    Read out of main.py instead of listed here, so adding a top-level import to
    the entry point cannot quietly leave this check behind. Local packages
    (core, actions, memory, ui) are excluded by looking for them on disk.
    """
    import ast

    source = (ROOT / "main.py").read_text(encoding="utf-8", errors="replace")
    found: set[str] = set()
    for node in ast.parse(source).body:
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)

    third_party = []
    for name in sorted(found):
        top = name.split(".")[0]
        if not top or top in sys.stdlib_module_names:
            continue
        if (ROOT / f"{top}.py").exists() or (ROOT / top).exists():
            continue  # this project's own package
        third_party.append(name)
    return sorted(set(third_party) | set(_EXTRA_CRITICAL))


def missing_imports(imports: list[str]) -> list[str]:
    """Import them in a subprocess — the answer must come from a clean start."""
    if not imports:
        return []
    code = "import " + ", ".join(imports)
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode == 0:
        return []

    # One process for all of them would report only the first failure, and a
    # machine with two broken packages should be told about both.
    broken = []
    for name in imports:
        probe = subprocess.run(
            [sys.executable, "-c", f"import {name}"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if probe.returncode != 0:
            broken.append(name)
    return broken or [code]


def ensure_app_can_start(log_path: Path) -> bool:
    """The last gate before the app is launched."""
    imports = critical_imports()
    broken = missing_imports(imports)
    if not broken:
        print(f"Startup check: {len(imports)} required modules import cleanly.", flush=True)
        return True

    print("\nThese modules the app needs did not import:", flush=True)
    for name in broken:
        print(f"  - {name}", flush=True)

    # Second chance: a package can be present but incomplete (an interrupted
    # wheel, a Python upgrade underneath an old .venv).
    for name in broken:
        package = name.split(".")[0]
        print(f"Reinstalling {package} …", flush=True)
        run_logged(_pip("--force-reinstall", "--no-cache-dir", package), log_path, echo=False)

    still_broken = missing_imports(imports)
    if not still_broken:
        print("Reinstall fixed it; all required modules import now.", flush=True)
        return True

    print("\nStill missing:", flush=True)
    for name in still_broken:
        print(f"  - {name}", flush=True)
    print(
        "\nUltron will not start without these. Most likely causes, in order:\n"
        "  1. The download was interrupted — run run.bat again, it resumes.\n"
        "  2. No internet, or a proxy is blocking pypi.org.\n"
        "  3. A 32-bit Python is installed. Install 64-bit Python 3.12, delete the\n"
        "     .venv folder, and run run.bat again.\n"
        "The full output is in setup-log.txt next to run.bat.",
        flush=True,
    )
    return False


def install_browsers(log_path: Path) -> None:
    """Chromium and Firefox for web automation. Never fatal, always skippable."""
    if os.environ.get(_SKIP_BROWSERS, "").strip() not in ("", "0"):
        print(f"\nSkipping the browser engines ({_SKIP_BROWSERS} is set).", flush=True)
        print("Browser automation stays off until: "
              f'{sys.executable} -m playwright install chromium firefox', flush=True)
        return
    print("\n== Installing the browser engines (chromium + firefox) ==", flush=True)
    code = run_logged(_pip("playwright"), log_path, echo=False)
    code = code or run_logged(
        [sys.executable, "-m", "playwright", "install", "chromium", "firefox"],
        log_path,
    )
    if code:
        print("\nThe browser engines did not install. Everything except browser"
              "\nautomation works. Retry later with:", flush=True)
        print(f"  {sys.executable} -m playwright install chromium firefox", flush=True)


def ready_marker(requirements: Path) -> str:
    """Fingerprint of everything a successful install depended on."""
    digest = hashlib.sha256()
    digest.update(requirements.read_bytes())
    digest.update(str(sys.version_info[:2]).encode("ascii"))
    digest.update(_VERSION)
    return digest.hexdigest()


# ── entry point ──────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    configure_console()
    argv = sys.argv[1:] if argv is None else argv

    if sys.prefix == sys.base_prefix:
        print("Launch with run.bat (or run.ps1) so packages are installed only"
              " inside this folder's .venv.")
        return 1
    if not MIN_PY <= sys.version_info[:2] <= MAX_PY:
        print(f"This launcher supports Python {MIN_PY[0]}.{MIN_PY[1]} to "
              f"{MAX_PY[0]}.{MAX_PY[1]}; this environment is "
              f"{sys.version_info[0]}.{sys.version_info[1]}.")
        print("Delete the .venv folder, install 64-bit Python 3.12, run run.bat again.")
        return 1

    requirements = ROOT / "requirements.txt"
    marker = Path(sys.prefix) / MARKER_NAME
    force = "--force" in argv

    # A matching marker means this exact requirements.txt and Python version
    # already installed here, and the app-start check passed at the time. A
    # stale one means something changed, so the whole install runs again — pip
    # itself skips what is already satisfied, which is why that is cheap.
    if not force and marker.is_file():
        try:
            if marker.read_text(encoding="ascii").strip() == ready_marker(requirements):
                return 0
        except OSError:
            pass

    LOG_PATH.write_text("", encoding="utf-8")
    with LOG_PATH.open("a", encoding="utf-8") as log:
        log.write(f"Ultron setup log — Python {sys.version.split()[0]} on "
                  f"{sys.platform}\n")

    print("\n" + "=" * 70)
    print("  Ultron — first launch on this machine.")
    print("  It installs its own Python packages into this folder's .venv.")
    print("  Ten to twenty minutes on a normal connection. Leave this window")
    print("  open; you only do this once.")
    print("=" * 70, flush=True)

    install_requirements(LOG_PATH)
    if not ensure_app_can_start(LOG_PATH):
        return 1
    install_browsers(LOG_PATH)

    marker.write_text(ready_marker(requirements), encoding="ascii")
    print("\nSetup complete. Starting Ultron.\n", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OSError as exc:
        print("Setup failed:", exc)
        raise SystemExit(1)
