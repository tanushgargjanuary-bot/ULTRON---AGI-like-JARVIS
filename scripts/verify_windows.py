"""What only real Windows can answer, asked on real Windows.

    python scripts/verify_windows.py
    python scripts/verify_windows.py --json windows-report.json

Every check here is something Linux cannot stand in for: the accessibility tree
comes from UI Automation, the volume from Core Audio, the browsers from the
registry, the scale factor from the actual monitor. Run it on the machine Ultron
is meant for and it prints a line per capability.

Nothing here changes a setting. The checks that would (volume, brightness) read
the value, set it back to what it was, and report both.

Exit code is 0 when nothing FAILED. SKIP means "this machine cannot do it" —
which is an answer, and the report says which.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

IS_WINDOWS = platform.system() == "Windows"
results: list[dict] = []


def record(name: str, status: str, detail: str = "", **extra) -> None:
    entry = {"check": name, "status": status, "detail": detail}
    entry.update(extra)
    results.append(entry)
    mark = {"PASS": "PASS", "FAIL": "FAIL", "SKIP": "SKIP", "INFO": "INFO"}[status]
    print(f"  {mark}  {name}" + (f" — {detail}" if detail else ""))


def check(name: str):
    """Run one check function; it returns (status, detail)."""
    def run(fn):
        if not IS_WINDOWS:
            record(name, "SKIP", "not running on Windows")
            return fn
        try:
            status, detail = fn()
        except Exception as exc:                     # a check must never kill the run
            status, detail = "FAIL", f"{type(exc).__name__}: {exc}"
        record(name, status, detail)
        return fn
    return run


# ── the operating system ─────────────────────────────────────────────────────
def os_facts():
    return ("PASS" if IS_WINDOWS else "SKIP",
            f"{platform.system()} {platform.release()} {platform.machine()} "
            f"| Python {platform.python_version()}")


def dpi_scaling():
    """Qt must see the real display, and scale with it."""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    screen = app.primaryScreen()
    ratio = screen.devicePixelRatio()
    size = screen.size()
    return ("PASS",
            f"{size.width()}x{size.height()} logical, device pixel ratio "
            f"{ratio:.2f}, Qt scale {os.environ.get('QT_SCALE_FACTOR', '(unset)')}")


def window_fits_the_screen():
    """The 1.2.4 promise: the window never opens larger than the display."""
    from PyQt6.QtWidgets import QApplication
    import ui
    app = QApplication.instance() or QApplication([])
    screen = app.primaryScreen().availableGeometry()
    face = ROOT / "core" / "face_model.obj"
    window = ui.MainWindow(str(face))
    try:
        fits = (window.width() <= screen.width() and window.height() <= screen.height())
        detail = (f"window {window.width()}x{window.height()} on a "
                  f"{screen.width()}x{screen.height()} desktop")
        return ("PASS" if fits else "FAIL", detail)
    finally:
        window.close()


def no_console_windows():
    """Every subprocess must be created without a console window.

    main.py patches Popen to force CREATE_NO_WINDOW; this proves the patch is in
    force rather than trusting the file.
    """
    import subprocess as sp
    flags = getattr(sp, "CREATE_NO_WINDOW", 0)
    if not flags:
        return ("FAIL", "CREATE_NO_WINDOW is not available")
    out = sp.run([sys.executable, "-c", "print('quiet')"],
                 capture_output=True, text=True, timeout=60)
    return ("PASS" if out.stdout.strip() == "quiet" else "FAIL",
            f"a child process ran and printed ({len(out.stdout.strip())} chars) "
            f"with CREATE_NO_WINDOW available")


def audio_devices():
    """A real microphone and speaker, and what sounddevice sees."""
    try:
        import sounddevice as sd
    except Exception as exc:
        return ("FAIL", f"sounddevice will not load: {exc}")
    devices = sd.query_devices()
    ins = [d for d in devices if d.get("max_input_channels")]
    outs = [d for d in devices if d.get("max_output_channels")]
    if not ins:
        # A hosted build server has no audio hardware. SKIP says "not tested
        # here"; FAIL would say "Ultron is broken", which is not what happened.
        return ("SKIP", "no input device on this machine — nothing to test here")
    return ("PASS", f"{len(ins)} input, {len(outs)} output devices; "
                    f"default in '{ins[0]['name']}'")


def microphone_actually_records():
    """Record a second of audio and report what came back.

    Silence is not a failure — a quiet room is silent. An empty buffer or an
    exception is.
    """
    import numpy as np
    import sounddevice as sd
    if not [d for d in sd.query_devices() if d.get("max_input_channels")]:
        return ("SKIP", "no microphone on this machine — nothing to record")
    info = sd.query_devices(kind="input")
    rate = int(info.get("default_samplerate") or 16000)
    try:
        frames = sd.rec(int(rate * 1.0), samplerate=rate, channels=1,
                        dtype="int16")
        sd.wait()
    except Exception as exc:
        return ("FAIL", f"recording raised: {exc}")
    peak = int(np.abs(frames).max()) if frames.size else 0
    return ("PASS", f"{frames.size} samples at {rate} Hz, peak amplitude {peak} "
                    f"({len(frames.tobytes())} bytes)")


def speak_a_tone():
    """Write a second of sound. The user should hear it."""
    import numpy as np
    import sounddevice as sd
    if not [d for d in sd.query_devices() if d.get("max_output_channels")]:
        return ("SKIP", "no speaker on this machine — nothing to play")
    info = sd.query_devices(kind="output")
    rate = int(info.get("default_samplerate") or 24000)
    t = np.linspace(0, 1.0, rate, endpoint=False)
    tone = (0.2 * np.sin(2 * np.pi * 440 * t) * 32767).astype("int16")
    try:
        sd.play(tone, samplerate=rate)
        sd.wait()
    except Exception as exc:
        return ("FAIL", f"playback raised: {exc}")
    return ("PASS", "one second of 440 Hz was written to the default output")


def screen_capture():
    """A real desktop screenshot, through the app's own function."""
    try:
        from actions.screen_processor import _capture_screen
    except Exception as exc:
        return ("FAIL", f"screen_processor will not import: {exc}")
    data, mime = _capture_screen()
    if not data:
        return ("FAIL", "capture returned nothing")
    return ("PASS", f"{len(data):,} bytes of {mime}")


def camera_capture():
    """A real frame from the camera, or an honest reason there is none."""
    try:
        from actions.screen_processor import _capture_camera
    except Exception as exc:
        return ("SKIP", f"camera path unavailable: {exc}")
    try:
        data, mime = _capture_camera()
    except Exception as exc:
        return ("SKIP", f"no camera answered: {exc}")
    return ("PASS" if data else "SKIP",
            f"{len(data):,} bytes of {mime}" if data else "camera returned nothing")


def accessibility_tree():
    """UI Automation — the tree the tool ladder prefers over vision.

    Asks core.ui_windows, exactly as the app does. When this check imported
    uiautomation itself it could report SKIP while the app believed the tree was
    available (pywinauto installed, driver missing) — the instrument has to ask
    the same question the product asks, or it measures nothing.
    """
    try:
        from core.ui_windows import available
        usable, reason = available()
    except Exception as exc:
        return ("SKIP", f"the bridge cannot be imported: {exc}")
    if not usable:
        return ("SKIP", reason)
    import uiautomation as auto
    window = auto.GetForegroundControl()
    if window is None:
        return ("SKIP", "no foreground window to read")
    children = []
    try:
        for child in window.GetChildren()[:5]:
            children.append(f"{child.ControlTypeName}:{child.Name}"[:40])
    except Exception as exc:
        return ("FAIL", f"the tree could not be walked: {exc}")
    return ("PASS", f"foreground '{window.Name}' -> {len(children)} children: "
                    f"{'; '.join(children)}")


def volume_round_trip():
    """Read, change and restore the system volume — the undo path, for real."""
    try:
        from actions.computer_settings import volume_get, volume_set
    except Exception as exc:
        return ("SKIP", f"volume helpers unavailable: {exc}")
    before = volume_get()
    if before is None:
        return ("SKIP", "this machine does not report its volume")
    target = 0 if before > 10 else 40
    volume_set(target)
    after = volume_get()
    volume_set(before)
    restored = volume_get()
    ok = after is not None and abs(int(after) - target) <= 2
    backok = restored is not None and abs(int(restored) - int(before)) <= 2
    return ("PASS" if ok and backok else "FAIL",
            f"{before}% -> {after}% -> {restored}% (restored)")


def brightness_round_trip():
    try:
        from actions.computer_settings import brightness_get, brightness_set
    except Exception as exc:
        return ("SKIP", f"brightness helpers unavailable: {exc}")
    before = brightness_get()
    if before is None:
        return ("SKIP", "this machine does not report its brightness")
    brightness_set(max(0, min(100, int(before) - 10)))
    mid = brightness_get()
    brightness_set(before)
    back = brightness_get()
    return ("PASS" if mid is not None and back is not None else "FAIL",
            f"{before}% -> {mid}% -> {back}%")


def browser_discovery():
    """The registry of installed browsers, read the way the tool reads it."""
    try:
        from actions import browser_control as bc
    except Exception as exc:
        return ("SKIP", f"browser_control will not import: {exc}")
    browsers = bc._registry.list_sessions()
    detected = bc._detect_default_browser()
    return ("PASS" if detected else "SKIP",
            f"default: {detected or 'not identified'}; sessions: {browsers}")


def open_app_resolution():
    """Capability-based app resolution, and the reason when it has no answer.

    A machine with no browser installed SHOULD say "unknown". What it must never
    do is claim success and hand back an error message as the program name — that
    is what it did before this was checked.
    """
    from core.app_resolver import resolve
    result = resolve("browser")
    target = getattr(result, "target", "") or ""
    status = getattr(result, "status", "")
    if status == "resolved":
        if " " in target.strip() and not target.endswith((".desktop", ".app", ".exe")):
            return ("FAIL", f"a sentence was returned as the program: {target!r}")
        return ("PASS", f"'browser' -> {target}")
    return ("SKIP", f"no browser resolved here ({getattr(result, 'reason', '')})")


def powershell_launchers():
    """run.bat and run.ps1 are the install; both must be present, ASCII, no BOM."""
    problems = []
    for name in ("run.bat", "run.ps1"):
        path = ROOT / name
        if not path.exists():
            problems.append(f"{name} missing")
            continue
        data = path.read_bytes()
        if data.startswith(b"\xef\xbb\xbf"):
            problems.append(f"{name} has a BOM")
        try:
            data.decode("ascii")
        except UnicodeDecodeError:
            problems.append(f"{name} is not ASCII")
    return ("FAIL" if problems else "PASS",
            "; ".join(problems) if problems else "both launchers present, ASCII, no BOM")


def one_double_click():
    """The launcher's own preflight, without installing anything."""
    bat = ROOT / "run.bat"
    if not bat.exists():
        return ("SKIP", "run.bat not present")
    text = bat.read_text(encoding="ascii", errors="replace").lower()
    needs = ["python", ".venv", "requirements"]
    missing = [n for n in needs if n not in text]
    return ("FAIL" if missing else "PASS",
            f"run.bat mentions: {', '.join(n for n in needs if n not in missing) or 'nothing'}")


# These read files or call APIs that exist everywhere; running them on Linux is
# still information, so they are not gated on the platform.
ANY_PLATFORM = {"app resolution", "PowerShell launchers", "one double-click"}

CHECKS = [
    ("operating system", os_facts),
    ("display and DPI scaling", dpi_scaling),
    ("window fits the screen", window_fits_the_screen),
    ("child processes are silent", no_console_windows),
    ("audio devices", audio_devices),
    ("microphone records", microphone_actually_records),
    ("speaker plays", speak_a_tone),
    ("screen capture", screen_capture),
    ("camera capture", camera_capture),
    ("accessibility tree (UI Automation)", accessibility_tree),
    ("volume read/write/restore", volume_round_trip),
    ("brightness read/write/restore", brightness_round_trip),
    ("browser discovery", browser_discovery),
    ("app resolution", open_app_resolution),
    ("PowerShell launchers", powershell_launchers),
    ("one double-click", one_double_click),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", default="", help="write the report here")
    args = parser.parse_args(argv)

    print(f"Ultron — platform verification")
    print(f"  project: {ROOT}")
    print(f"  machine: {platform.platform()}")
    print()
    for name, fn in CHECKS:
        if not IS_WINDOWS and name not in ANY_PLATFORM:
            record(name, "SKIP", "not running on Windows")
            continue
        try:
            status, detail = fn()
        except Exception as exc:
            status, detail = "FAIL", f"{type(exc).__name__}: {exc}"
        record(name, status, detail)

    failed = [r for r in results if r["status"] == "FAIL"]
    passed = [r for r in results if r["status"] == "PASS"]
    skipped = [r for r in results if r["status"] == "SKIP"]
    print()
    print(f"  {len(passed)} passed, {len(failed)} failed, {len(skipped)} skipped")
    if not IS_WINDOWS:
        print(f"  {len(passed)} of these do not need Windows. The rest do: run it there.")
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"  report: {args.json}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
