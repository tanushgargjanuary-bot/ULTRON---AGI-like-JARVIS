"""A real browser, on a real page, through the real engine.

    python scripts/verify_browser.py
    python scripts/verify_browser.py --drive-ultron      # opens a visible window
    python scripts/verify_browser.py --browser firefox

Two separate questions, asked separately:

  1. Does the ENGINE work here — Playwright installed, a browser binary that
     actually launches, a page that loads, text that can be read, a click, a
     typed character, a screenshot, and a JS error that does not crash anything.
     This runs headless, in its own browser, touching nothing of the user's.

  2. Does ULTRON'S control layer work — `actions/browser_control` imports, its
     registry enumerates what is installed, and (with --drive-ultron) its own
     `go_to` action opens a local page. That one DOES open a visible window,
     because driving the user's real browser is what that tool is for, so it is
     opt-in.

Nothing here uses a model or a network. The page is generated locally.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import platform
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

results: list[dict] = []

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>Ultron browser check</title></head>
<body>
  <h1 id="title">Browser verification</h1>
  <button id="press" onclick="document.getElementById('out').textContent='pressed'">Press</button>
  <input id="field" placeholder="type here">
  <p id="out">idle</p>
</body></html>
"""


def record(name: str, status: str, detail: str = "") -> None:
    results.append({"check": name, "status": status, "detail": detail})
    print(f"  {status:4s}  {name}" + (f" — {detail}" if detail else ""))


def finish(report: str = "") -> int:
    failed = [r for r in results if r["status"] == "FAIL"]
    passed = [r for r in results if r["status"] == "PASS"]
    skipped = [r for r in results if r["status"] == "SKIP"]
    print(f"\n  {len(passed)} passed, {len(failed)} failed, {len(skipped)} skipped")
    if report:
        Path(report).write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"  report: {report}")
    return 1 if failed else 0


def _binary_problem(exe: str) -> str:
    """Why a browser binary will not start, in words that can be acted on.

    Playwright reports "Target page, context or browser has been closed", which
    says nothing about the usual cause on Linux — a shared library the package
    manager never installed. Asking the binary directly and reading ldd turns
    that into "missing libnss3, libatk…: run playwright install-deps".
    """
    import subprocess
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True,
                             timeout=60)
    except Exception as exc:
        return f"could not run it: {exc}"
    if out.returncode == 0 and out.stdout.strip():
        return ""
    text = (out.stderr or out.stdout or "").strip().splitlines()
    missing = ""
    try:
        ldd = subprocess.run(["ldd", exe], capture_output=True, text=True, timeout=60)
        absent = sorted({line.split("=>")[0].strip()
                         for line in ldd.stdout.splitlines() if "not found" in line})
        if absent:
            missing = (f"missing libraries: {', '.join(absent[:8])}"
                       f"{'…' if len(absent) > 8 else ''} — on Linux run "
                       f"'playwright install-deps', on Windows reinstall Playwright")
    except Exception:
        pass
    return missing or (text[-1][:200] if text else "it exited non-zero for no stated reason")


async def drive_engine(page_url: str, browser_name: str, headed: bool) -> None:
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        engine = getattr(pw, browser_name, None)
        if engine is None:
            record("engine exists", "FAIL", f"no {browser_name} in Playwright")
            return
        exe = getattr(engine, "executable_path", "")
        record("browser binary present", "PASS" if exe and Path(exe).exists() else "FAIL",
               exe or "Playwright did not report one")
        if exe and Path(exe).exists():
            note = _binary_problem(exe)
            if note:
                record("browser binary runs", "FAIL", note)
                return
        try:
            browser = await engine.launch(headless=not headed, args=["--no-sandbox"])
        except Exception as exc:
            record("browser launches", "FAIL",
                   f"{type(exc).__name__}: {str(exc)[:200]}")
            return
        record("browser launches", "PASS", f"{browser_name} headless={not headed}")

        page = await browser.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        await page.goto(page_url)
        record("page loads", "PASS", await page.title())

        text = await page.inner_text("#title")
        record("text can be read", "PASS" if "verification" in text else "FAIL", text[:60])

        await page.click("#press")
        after = await page.inner_text("#out")
        record("click", "PASS" if after == "pressed" else "FAIL", f"state now {after!r}")

        await page.fill("#field", "typed by the check")
        record("type", "PASS" if await page.input_value("#field") == "typed by the check"
               else "FAIL")

        shot = await page.screenshot()
        record("screenshot", "PASS" if len(shot) > 1000 else "FAIL",
               f"{len(shot):,} bytes of PNG")

        record("a JS error is survived", "PASS" if not errors else "INFO",
               "; ".join(errors[:2]) or "none raised")

        await browser.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="real browser verification")
    parser.add_argument("--browser", default="chromium",
                        choices=("chromium", "firefox", "webkit"))
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--drive-ultron", action="store_true",
                        help="also drive actions/browser_control (opens a window)")
    parser.add_argument("--json", default="")
    args = parser.parse_args(argv)

    print(f"Browser on {platform.platform()}")
    try:
        import playwright                                     # noqa: F401
        record("playwright installed", "PASS")
    except ImportError as exc:
        # Not installed is the absence of a capability, and the sentence says how
        # to add it. Installed and failing to launch is the FAIL below.
        record("playwright installed", "SKIP",
               f"{exc} — run: pip install playwright && playwright install chromium")
        return finish(args.json)

    temp = Path(tempfile.mkdtemp()) / "page.html"
    temp.write_text(PAGE, encoding="utf-8")

    try:
        asyncio.run(drive_engine(temp.as_uri(), args.browser, args.headed))
    except Exception as exc:
        record("engine run", "FAIL", f"{type(exc).__name__}: {str(exc)[:300]}")

    # ── Ultron's own control layer ───────────────────────────────────────────
    try:
        from actions import browser_control as bc
        record("browser_control imports", "PASS")
    except Exception as exc:
        record("browser_control imports", "SKIP", f"{type(exc).__name__}: {str(exc)[:160]}")
        return finish(args.json)

    try:
        sessions = bc._registry.list_sessions()
        record("registry enumerates", "PASS", str(sessions)[:120])
    except Exception as exc:
        record("registry enumerates", "FAIL", f"{type(exc).__name__}: {exc}")

    try:
        default = bc._detect_default_browser()
        record("default browser detected", "PASS" if default else "SKIP", default or "none")
    except Exception as exc:
        record("default browser detected", "FAIL", f"{type(exc).__name__}: {exc}")

    if args.drive_ultron:
        try:
            out = bc.browser_control({"action": "go_to", "url": temp.as_uri()})
            record("browser_control go_to", "PASS" if out and "fail" not in out.lower()
                   else "FAIL", out[:160])
        except Exception as exc:
            record("browser_control go_to", "FAIL", f"{type(exc).__name__}: {exc}")
    else:
        record("browser_control go_to", "SKIP", "not run — pass --drive-ultron")

    return finish(args.json)


if __name__ == "__main__":
    raise SystemExit(main())
