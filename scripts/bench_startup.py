"""scripts/bench_startup.py — what the launch actually costs, measured.

WHY THIS EXISTS
    "Optimise the code" needs a number before and a number after, or it is an
    opinion. The numbers that matter for this application are not loop
    microbenchmarks: the per-turn Python work (prompt building, history
    trimming, risk classification, the spoken-register pass) totals well under a
    millisecond against a network round trip measured in hundreds. What a user
    feels is the two seconds before the window is useful.

    So this measures the launch: how long each stage takes, and — more
    importantly — which libraries get pulled in on the way. A module imported at
    launch is paid on every launch, whether or not the session ever needs it.

HOW IT MEASURES
    Each stage runs in its OWN subprocess. Timing imports inside one process is
    easy to get wrong: the second import is free because the first one already
    put the module in `sys.modules`, so a single process reports the first stage
    hot and every later one cold. Separate processes, each with a clean
    `sys.modules`, is the only version that means anything.

    Each stage runs `--runs` times and reports the median, because the first run
    of anything on Windows is dominated by antivirus and the file cache.

USAGE
    python scripts\\bench_startup.py
    python scripts\\bench_startup.py --runs 5
    python scripts\\bench_startup.py --json
    python scripts\\bench_startup.py --stage import      (one stage only)

EXIT CODES
    0 measured · 2 bad arguments · 3 a stage could not run at all (missing
    dependency, no display) — the report still prints what it did measure.

NOT MEASURED, ON PURPOSE
    Window construction, TTS and STT warm-up, provider handshake. All four need
    a display, audio hardware or a network, and a benchmark that needs any of
    them cannot run on a build machine.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Each probe prints ONE json object as its last line: {"ms": float, "extra": {...}}
# so the parent never has to parse prose.
PROBES: dict[str, str] = {
    "import": textwrap.dedent(
        """
        import sys, time, json
        t0 = time.perf_counter()
        import main
        ms = (time.perf_counter() - t0) * 1000
        watched = ["google.genai", "google.genai.types", "pyautogui", "playwright",
                   "requests", "PIL", "PIL.Image", "cv2", "pandas"]
        print(json.dumps({"ms": ms, "extra": {
            "loaded": [m for m in watched if m in sys.modules],
        }}))
        """
    ),
    "actions": textwrap.dedent(
        """
        import sys, time, json
        from pathlib import Path
        from core.action_loader import discover_actions
        t0 = time.perf_counter()
        registry = discover_actions(Path("actions"))
        ms = (time.perf_counter() - t0) * 1000
        watched = ["pyautogui", "playwright", "requests", "PIL", "cv2", "pandas"]
        print(json.dumps({"ms": ms, "extra": {
            "tools": len(registry.names()),
            "loaded": [m for m in watched if m in sys.modules],
        }}))
        """
    ),
    "turn": textwrap.dedent(
        """
        import json, time
        import memory.memory_manager as mm
        from core import policy, voice_style
        from providers import engine_pipeline as ep

        memory = {"identity": {"name": {"value": "sir", "updated": "2026-01-01"}},
                  "preferences": {}, "projects": {}, "relationships": {},
                  "wishes": {}, "notes": {}}
        for i in range(60):
            for cat in ("preferences", "projects", "relationships", "wishes", "notes"):
                memory[cat][f"k_{cat}_{i}"] = {
                    "value": "a remembered value, roughly a sentence long " * 2,
                    "updated": f"2026-0{1 + i % 9}-1{i % 9}",
                }

        history = []
        for i in range(250):
            if i % 5 == 4:
                history.append({"role": "tool", "name": "web_search",
                                "content": json.dumps({"results": ["x" * 400] * 12})})
            else:
                history.append({"role": "user" if i % 2 == 0 else "assistant",
                                "content": "a fairly long message about something " * 20})

        engine = ep.PipelineEngine.__new__(ep.PipelineEngine)
        engine._history_chars = ep._DEFAULT_HISTORY_CHARS
        engine._system = "system prompt " * 100
        engine._history = history

        spoken = ("Certainly! Here is a summary:\\n1. it is 24 degrees\\n"
                  "2. rain later\\n\\nLet me know if you need anything else. ") * 8

        def work():
            mm.format_memory_for_prompt(memory)
            policy.classify("open_app", {"app": "notepad"})
            engine._trimmed()
            voice_style.spoken(spoken)

        runs = 50
        t0 = time.perf_counter()
        for _ in range(runs):
            work()
        per = (time.perf_counter() - t0) * 1000 / runs
        print(json.dumps({"ms": per, "extra": {"what": "one turn of local work"}}))
        """
    ),
}


def run_probe(name: str, code: str, runs: int) -> dict:
    """Vehicle the probe `runs` times in fresh processes; median of the batch."""
    samples, extra, failure = [], {}, None
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8")
    for _ in range(runs):
        done = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
            env=env,
        )
        line = next(
            (ln for ln in reversed(done.stdout.splitlines()) if ln.startswith("{")), None
        )
        if done.returncode != 0 or line is None:
            tail = (done.stderr.strip().splitlines() or ["no output"])[-1]
            failure = tail[:160]
            break
        payload = json.loads(line)
        samples.append(payload["ms"])
        extra = payload.get("extra", extra)
    return {
        "stage": name,
        "ms": statistics.median(samples) if samples else None,
        "samples": samples,
        "extra": extra,
        "error": failure,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bench_startup.py",
        description="Measure the launch path. Nothing is started, nothing is sent.",
    )
    parser.add_argument("--stage", choices=sorted(PROBES), action="append",
                        help="measure only this stage (repeatable)")
    parser.add_argument("--runs", type=int, default=3, help="runs per stage, median reported")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    if args.runs < 1 or args.runs > 20:
        print("--runs must be between 1 and 20", file=sys.stderr)
        return 2

    stages = args.stage or ["import", "actions", "turn"]
    results = [run_probe(name, PROBES[name], args.runs) for name in stages]

    if args.json:
        print(json.dumps({"stages": results, "runs": args.runs}, indent=2))
    else:
        print(f"startup benchmark — medians of {args.runs} run(s), offscreen, no network\n")
        for result in results:
            if result["error"]:
                print(f"  {result['stage']:<10} not measurable here: {result['error']}")
                continue
            line = f"  {result['stage']:<10} {result['ms']:8.1f} ms"
            loaded = result["extra"].get("loaded")
            if loaded:
                line += f"   pulled in: {', '.join(loaded)}"
            elif loaded == []:
                line += "   nothing heavy pulled in"
            print(line)
        failed = [r for r in results if r["error"]]
        if failed:
            print(
                "\nA stage that could not run is reported, not guessed. On Windows the"
                "\nimport stage needs the .venv this app installs; the turn stage needs"
                "\nonly the standard library and this repo."
            )
            return 3
        print("\nLower is better. The import and actions stages are paid once per")
        print("launch; the turn stage is paid per exchange but is far below the")
        print("network round trip it sits next to.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
