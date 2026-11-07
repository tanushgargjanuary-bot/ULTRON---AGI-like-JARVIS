"""Stop a startup with a sentence, not a traceback.

``python main.py`` is the second way to start Ultron, and it fails in two ways that look like
a bug in the app rather than a mistake in the terminal:

  * the system Python is 3.14, and this project supports 3.11 to 3.13;
  * the system Python exists but the packages live in the folder's own ``.venv``.

Both used to produce a stack trace, which reads as "Ultron is broken". Each now produces a
short message naming the two commands that work. Nothing here decides anything about the
application; it only chooses the words for a refusal.
"""

from __future__ import annotations

SUPPORTED = ((3, 11), (3, 12), (3, 13))
SUPPORTED_TEXT = "3.11, 3.12 or 3.13"
PACKAGE = "PyQt6"


def supported(version: tuple) -> bool:
    """True for a Python this project runs on."""
    return tuple(version[:2]) in SUPPORTED


def version_message(version: tuple) -> str:
    """What to say when the interpreter is the wrong one."""
    shown = ".".join(str(part) for part in tuple(version[:2]))
    return (
        f"Ultron needs Python {SUPPORTED_TEXT}. This interpreter is {shown}.\n"
        "\n"
        "Two ways that work:\n"
        "  1. double-click run.bat                 (builds .venv, installs, starts)\n"
        "  2. .venv\\Scripts\\python.exe main.py     (the same Python run.bat uses)\n"
        "\n"
        "run.bat installs the right Python itself if none is present. Nothing outside\n"
        "this folder is changed."
    )


def missing_package_message(package: str = PACKAGE) -> str:
    """What to say when the packages are missing from this interpreter."""
    return (
        f"Ultron could not load {package}. This Python does not have the app's packages.\n"
        "\n"
        "They live in the folder's own .venv, so start it one of these ways:\n"
        "  1. double-click run.bat                 (creates .venv and installs what is missing)\n"
        "  2. .venv\\Scripts\\python.exe main.py\n"
        "\n"
        "'python main.py' with the system Python skips that folder. That is the whole\n"
        "difference - the app is fine."
    )


def refuse(message: str) -> None:
    """Stop, with the message as the reason.

    ``SystemExit`` given a string prints that string and exits without a traceback, which is
    exactly what a person needs. Nothing is printed from this module: it is a library, and a
    library that prints is a library that is heard in places it was never meant to speak.
    """
    raise SystemExit(message)


def stop_early(version: tuple | None = None, has_package: bool | None = None) -> None:
    """Check the interpreter before the heavy imports, and stop if it cannot work.

    Both arguments exist so the behaviour can be tested without changing the interpreter
    the test suite runs on.
    """
    import sys

    version = sys.version_info if version is None else version
    if not supported(version):
        refuse(version_message(version))
    if has_package is None:
        try:
            __import__(PACKAGE)
            has_package = True
        except Exception:
            has_package = False
    if not has_package:
        refuse(missing_package_message())
