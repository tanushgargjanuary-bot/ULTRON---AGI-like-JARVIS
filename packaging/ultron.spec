# -*- mode: python ; coding: utf-8 -*-
"""A self-contained Ultron: one folder, no Python needed on the target machine.

This is the second way to ship the app. The installer (`ultron.iss`) is the first
and the one with a tested path behind it: it copies the source and lets run.ps1
build a private environment, exactly as the repository does today.

This spec produces the other thing — a folder with an interpreter inside it, which
runs on a PC that has never had Python. It is bigger (a few hundred megabytes,
mostly Qt) and it must be built ON Windows for Windows.

    python -m pip install pyinstaller
    python -m PyInstaller packaging\\ultron.spec --noconfirm

Then wrap dist\\Ultron with the same .iss file by pointing build_installer.ps1's
staging folder at it.

STATUS: written and reviewed, not yet built on Windows. The file list below is
checked against the tree by tests/test_installer.py, so it cannot drift; but a
"works" claim needs a build on a Windows machine, and that has not happened.
"""

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent

# Data the app reads at runtime. Every path here is checked by a test: a spec that
# names a folder which has been renamed produces an app that starts and then cannot
# find its own instruction file.
DATA = [
    "core/prompt.txt",
    "config",
    "plugins",
    "native",
    "docs",
    "memory",
    "sidecar",
    "requirements.txt",
    "readme.md",
    "LICENSE",
]

# Imported inside functions, so PyInstaller's static analysis misses them.
HIDDEN = [
    "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.QtWidgets", "PyQt6.QtNetwork",
    "google.genai", "google.genai.types",
    "httpx", "httpcore", "anyio", "psutil", "mss", "sounddevice",
    "sqlite3", "json", "asyncio", "ctypes",
]

datas = [(str(ROOT / path), path) for path in DATA if (ROOT / path).exists()]

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=HIDDEN,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Ultron",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ROOT / "config" / "jarvis.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Ultron",
)
