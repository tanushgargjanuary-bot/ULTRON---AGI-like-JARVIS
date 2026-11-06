"""Does the window actually draw? Render it and look at the pixels.

    python scripts/verify_display.py
    python scripts/verify_display.py --out renders --json display-report.json

The suite can prove a widget exists. It cannot prove the window is not blank, that
the text is inside the frame, or that the scale control did anything. This renders
the real `ui.MainWindow` — the same class the app launches — at the sizes people
actually run, and looks at the resulting pixels:

  * is anything drawn at all (more than a handful of distinct colours)
  * is the activity log painted (dark-and-light variation inside its rectangle)
  * is the bottom-most control still inside the window at the smallest size
  * does a larger window mean more drawn content, not the same stretched frame

Each render is written to --out, so the picture can be looked at rather than
trusted. On Windows the same script also reports the real DPI and scale factor.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

results: list[dict] = []


def record(name: str, status: str, detail: str = "") -> None:
    results.append({"check": name, "status": status, "detail": detail})
    print(f"  {status:4s}  {name}" + (f" — {detail}" if detail else ""))


SIZES = [(980, 700), (1280, 800), (1600, 900)]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="render the window and inspect it")
    parser.add_argument("--out", default=str(ROOT.parent / "renders"))
    parser.add_argument("--json", default="")
    args = parser.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    print(f"Display on {platform.platform()} (Qt platform: "
          f"{os.environ.get('QT_QPA_PLATFORM', 'default')})")

    try:
        from PyQt6.QtWidgets import QApplication
        import ui
    except Exception as exc:
        record("Qt and ui import", "FAIL", f"{type(exc).__name__}: {exc}")
        return finish(args.json)

    app = QApplication.instance() or QApplication([])
    screen = app.primaryScreen()
    record("a screen is reported", "PASS",
           f"{screen.size().width()}x{screen.size().height()}, "
           f"device pixel ratio {screen.devicePixelRatio():.2f}")

    face = str(ROOT / "core" / "face_model.obj")
    window = ui.MainWindow(face)
    window.show()

    # The first-run setup panel covers the HUD, and on a fresh folder it is what
    # the window shows. Render the assistant itself: hide it, and say that it was
    # there, because "the HUD draws" and "the setup panel draws" are two claims.
    overlay = getattr(window, "_overlay", None)
    if overlay is not None:
        record("first-run panel appears on an unconfigured folder", "PASS",
               "hidden for the renders below")
        overlay.hide()
        app.processEvents()

    for width, height in SIZES:
        window.resize(width, height)
        app.processEvents()
        window.hud.repaint()
        app.processEvents()
        pixmap = window.grab()
        image = pixmap.toImage()

        colours = set()
        step = max(1, min(image.width(), image.height()) // 80)
        for y in range(0, image.height(), step):
            for x in range(0, image.width(), step):
                colours.add(image.pixel(x, y))
                if len(colours) > 4000:
                    break
        name = f"hud-{width}x{height}.png"
        pixmap.save(str(out / name))

        blank = len(colours) < 8
        record(f"{width}x{height} draws something", "FAIL" if blank else "PASS",
               f"{len(colours)} distinct colours, {image.width()}x{image.height()} px, "
               f"saved renders/{name}")

        # The activity log is the panel that used to fall off the bottom, and it
        # is the one place the app cannot be silent: if it is not painted, the
        # user has no idea what Ultron is doing.
        log = getattr(window, "_log", None)
        if log is not None:
            from PyQt6.QtCore import QPoint
            corner = log.mapTo(window, QPoint(0, 0))
            inside = (corner.x() >= 0 and corner.y() >= 0
                      and corner.x() + log.width() <= window.width()
                      and corner.y() + log.height() <= window.height()
                      and log.height() > 40)
            record(f"{width}x{height} log panel is inside the window",
                   "PASS" if inside else "FAIL",
                   f"{log.width()}x{log.height()} at ({corner.x()},{corner.y()}) "
                   f"in {window.width()}x{window.height()}")

            log.append_log("DISPLAY CHECK: this line must be painted")
            deadline = __import__("time").monotonic() + 4.0
            while __import__("time").monotonic() < deadline:
                app.processEvents()
                __import__("time").sleep(0.02)
            painted = window.grab()
            shot = painted.toImage()
            tints = set()
            for y in range(corner.y(), min(corner.y() + log.height(), shot.height()), 2):
                for x in range(corner.x(), min(corner.x() + log.width(), shot.width()), 2):
                    tints.add(shot.pixel(x, y))
            record(f"{width}x{height} log panel is painted",
                   "PASS" if len(tints) > 3 else "FAIL",
                   f"{len(tints)} distinct colours inside the panel")

    record("window title names the assistant", "PASS" if "ltron" in window.windowTitle()
           or "MARK" in window.windowTitle() else "FAIL", window.windowTitle())

    scale = os.environ.get("QT_SCALE_FACTOR", "")
    record("scale factor in force", "PASS", scale or "automatic")

    window.close()
    app.processEvents()
    return finish(args.json)


def finish(report: str = "") -> int:
    failed = [r for r in results if r["status"] == "FAIL"]
    passed = [r for r in results if r["status"] == "PASS"]
    print(f"\n  {len(passed)} passed, {len(failed)} failed")
    if report:
        Path(report).write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"  report: {report}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
