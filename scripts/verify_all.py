"""Every capability check, one table, one verdict.

    python scripts/verify_all.py
    python scripts/verify_all.py --only display,audio
    python scripts/verify_all.py --report verification/capabilities.json

Runs each verifier as its own process, so a hard crash in one (a missing Qt, a
broken driver, a browser that dies) cannot take the rest down. Each one writes
JSON; this reads the JSON and prints the only thing that matters: what works on
THIS machine, what does not, and what could not be tested here.

Exit code is 1 if any check FAILED. A SKIP is not a failure — it means the
question does not apply on this platform, and the reason is printed.
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

VERIFIERS = [
    ("platform", "verify_windows.py", "Windows-native behaviour, apps, launchers"),
    ("display", "verify_display.py", "the window draws, at three sizes"),
    ("capture", "verify_capture.py", "screen and camera frames"),
    ("audio", "verify_audio.py", "microphone and speaker"),
    ("browser", "verify_browser.py", "Playwright engine and browser_control"),
]


def verdict_for(row: dict) -> str:
    """One word per area, and none of them a euphemism.

    "PARTLY TESTED" exists because a Linux run of the Windows checks reports
    passes for the parts that do apply and skips for the rest; calling that
    WORKS would be the exact dishonesty these scripts exist to prevent.
    """
    if row.get("failed"):
        return "BROKEN"
    if not row.get("passed"):
        return "NOT TESTED HERE"
    if row.get("skipped"):
        return "PARTLY TESTED"
    return "WORKS"


def run(area: str, script: str, description: str, workdir: Path) -> dict:
    report = workdir / f"{area}.json"
    command = [sys.executable, str(SCRIPTS / script), "--json", str(report)]
    print(f"\n── {area}: {description}")
    try:
        done = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True,
                              timeout=1800)
    except subprocess.TimeoutExpired:
        print(f"  FAIL  {script} did not finish within 30 minutes")
        return {"area": area, "passed": 0, "failed": 1, "skipped": 0,
                "checks": [{"check": "completes", "status": "FAIL",
                            "detail": "timed out"}]}
    for line in done.stdout.splitlines():
        if line.strip().startswith(("PASS", "FAIL", "SKIP")):
            print("  " + line.strip())
    if done.returncode != 0 and not report.exists():
        tail = (done.stderr or done.stdout).strip().splitlines()[-3:]
        print("  FAIL  " + script + " — " + (" | ".join(tail) or "no output"))
        return {"area": area, "passed": 0, "failed": 1, "skipped": 0,
                "checks": [{"check": "runs", "status": "FAIL",
                            "detail": " | ".join(tail)[:300]}]}
    checks = json.loads(report.read_text(encoding="utf-8")) if report.exists() else []
    return {
        "area": area,
        "passed": len([c for c in checks if c["status"] == "PASS"]),
        "failed": len([c for c in checks if c["status"] == "FAIL"]),
        "skipped": len([c for c in checks if c["status"] == "SKIP"]),
        "checks": checks,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="run every capability verifier")
    parser.add_argument("--only", default="", help="comma-separated areas")
    parser.add_argument("--report", default=str(ROOT / "verification" / "capabilities.json"))
    args = parser.parse_args(argv)

    wanted = {name.strip() for name in args.only.split(",") if name.strip()}
    chosen = [v for v in VERIFIERS if not wanted or v[0] in wanted]

    print(f"Capability verification on {platform.platform()}")
    print(f"{platform.python_version()}, {len(chosen)} verifier(s)")

    workdir = Path(tempfile.mkdtemp(prefix="ultron-verify-"))
    results = [run(*entry, workdir) for entry in chosen]

    print("\n══ verdict")
    print(f"  {'area':10s} {'pass':>5s} {'fail':>5s} {'skip':>5s}   verdict")
    for row in results:
        verdict = verdict_for(row)
        print(f"  {row['area']:10s} {row['passed']:5d} {row['failed']:5d} "
              f"{row['skipped']:5d}   {verdict}")

    totals = {key: sum(row[key] for row in results)
              for key in ("passed", "failed", "skipped")}
    print(f"\n  {totals['passed']} passed, {totals['failed']} failed, "
          f"{totals['skipped']} skipped")
    if totals["failed"]:
        print("  This machine cannot do everything Ultron asks of it. The failing "
              "lines above say why; a SKIP is a question that does not apply here.")

    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({
        "platform": platform.platform(),
        "python": platform.python_version(),
        "totals": totals,
        "areas": results,
    }, indent=2), encoding="utf-8")
    print(f"  report: {report}")

    return 1 if totals["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
