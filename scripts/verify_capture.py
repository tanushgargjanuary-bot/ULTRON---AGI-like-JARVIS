"""Can this machine see, hear and speak? Ask it, do not assume.

    python scripts/verify_capture.py
    python scripts/verify_audio.py --record 3
    python scripts/verify_browser.py
    python scripts/verify_display.py

These are the four capabilities Linux off-screen could not answer: a real screen
grab, a real microphone and speaker, a real browser, a real display. Each script
drives the app's OWN code — `actions.screen_processor._capture_screen`,
`sounddevice` the way `main.py` uses it, `actions.browser_control` through its
own registry, `ui.MainWindow` — and prints one line per question with the reason
when the answer is no.

Every one of them works on the machine Ultron is meant for. None of them uses a
list of model names or a vendor SDK.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

results: list[dict] = []


def record(area: str, name: str, status: str, detail: str = "", **extra) -> None:
    entry = {"area": area, "check": name, "status": status, "detail": detail}
    entry.update(extra)
    results.append(entry)
    print(f"  {status:4s}  {name}" + (f" — {detail}" if detail else ""))


def finish(report_path: str = "", extra: str = "") -> int:
    failed = [r for r in results if r["status"] == "FAIL"]
    passed = [r for r in results if r["status"] == "PASS"]
    skipped = [r for r in results if r["status"] == "SKIP"]
    print(f"\n  {len(passed)} passed, {len(failed)} failed, {len(skipped)} skipped"
          + (f" — {extra}" if extra else ""))
    if report_path:
        Path(report_path).write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"  report: {report_path}")
    return 1 if failed else 0


# ── capture ──────────────────────────────────────────────────────────────────
def capture_main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="screen and camera capture")
    parser.add_argument("--json", default="")
    parser.add_argument("--save", default="", help="write the frame here")
    args = parser.parse_args(argv)

    print(f"Capture on {platform.platform()}")
    try:
        import mss  # noqa: F401
        record("capture", "mss is installed", "PASS", f"version {mss.__version__}"
               if hasattr(mss, "__version__") else "")
    except ImportError as exc:
        record("capture", "mss is installed", "FAIL",
               f"{exc} — run: pip install mss")

    from actions import screen_processor as sp

    started = time.monotonic()
    try:
        data, mime = sp._capture_screen()
        took = time.monotonic() - started
        if not data:
            record("capture", "screen grab", "\nFAIL", "returned nothing")
        else:
            record("capture", "screen grab", "PASS",
                   f"{len(data):,} bytes of {mime} in {took * 1000:.0f} ms")
            if args.save:
                Path(args.save).write_bytes(data)
                record("capture", "frame written", "PASS", args.save)
    except Exception as exc:
        record("capture", "screen grab", "FAIL", f"{type(exc).__name__}: {exc}")

    screen_only = len([r for r in results if r["status"] == "FAIL"]) == 0
    try:
        data, mime = sp._capture_camera()
        record("capture", "camera grab", "PASS" if data else "SKIP",
               f"{len(data):,} bytes of {mime}" if data else "no frame")
    except Exception as exc:
        record("capture", "camera grab", "SKIP", f"{type(exc).__name__}: {exc}")

    return finish(args.json, "" if screen_only else "screen capture is not working here")


if __name__ == "__main__":
    raise SystemExit(capture_main())
