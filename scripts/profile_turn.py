"""scripts/profile_turn.py — where the Python actually goes in one exchange.

The owner asked why most of the code is still Python, and whether the code itself
could be faster. This is the instrument that answers the second half with numbers
instead of an opinion.

WHY IT EXISTS
    "Rewrite it in a faster language" is a claim about time, so it needs a
    measurement of time. This script times the pure-Python work of a turn —
    prompt assembly, tool description, policy classification, memory read, the
    transcript scrub — with no network, no microphone, no model and no window. If
    a stage here is small, no language will make the exchange faster. If a stage
    here is large, it is our bug and it can be fixed in Python first.

HOW IT MEASURES
    Each stage runs many times and reports a median. A single run of anything in
    Python is dominated by the caches of whatever ran before it.

    The final section is a cProfile top list over the whole set, so a cost that
    hides inside a stage — the JSON decoder, the regular expression engine, the
    filesystem — is named rather than guessed at.

WHAT IT DOES NOT MEASURE
    The model, the network, speech recognition, the window. Those are measured
    separately, and honestly, in docs/LANGUAGE_MATRIX.md. This file is only about
    the part we wrote.

USAGE
    python scripts/profile_turn.py
    python scripts/profile_turn.py --rounds 200 --top 15
"""

from __future__ import annotations

import argparse
import cProfile
import io
import json
import os
import platform
import pstats
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def timeit(fn, rounds: int) -> dict:
    """Median and p95 milliseconds for one callable."""
    samples = []
    error = ""
    for _ in range(rounds):
        try:
            started = time.perf_counter()
            fn()
            samples.append((time.perf_counter() - started) * 1000.0)
        except Exception as exc:                     # a stage that cannot run here
            error = f"{type(exc).__name__}: {exc}"
            break
    if not samples:
        return {"median_ms": None, "p95_ms": None, "error": error}
    samples.sort()
    return {
        "median_ms": statistics.median(samples),
        "p95_ms": samples[int(len(samples) * 0.95) - 1],
        "error": "",
    }


def _import_main():
    """Import `main` even on a machine with no audio device or display.

    The stages profiled here are pure functions: prompt assembly, policy,
    memory, the transcript scrub. None of them touches a speaker. On a build
    machine with no PortAudio or no window server the module-level imports of
    `main` would stop the measurement before it started, so a missing device is
    stubbed — and the stub is named in the output, because a benchmark that
    quietly runs against fakes is a benchmark about fakes.
    """
    import types
    stubbed = []
    # Only modules used inside functions can be stubbed: PyQt6 supplies base
    # classes (QWidget), so a fake one produces a TypeError instead of a window.
    # If PyQt6 is missing, install it — that is what the app's own venv does.
    for name in ("sounddevice", "mss"):
        try:
            __import__(name)
        except Exception:
            module = types.ModuleType(name)
            module.__getattr__ = lambda attribute: _Stub(attribute)
            sys.modules[name] = module
            stubbed.append(name)
    try:
        import PyQt6  # noqa: F401
    except Exception as exc:
        raise SystemExit(
            "PyQt6 is needed to import this program. Run the app's own setup "
            f"(run.bat / run.ps1) or pip install PyQt6. ({exc})")
    import main
    return main, stubbed


class _Stub:
    """Absorbs any attribute access on a stubbed module."""

    def __init__(self, name: str):
        self._name = name

    def __getattr__(self, attribute):
        return _Stub(f"{self._name}.{attribute}")

    def __call__(self, *args, **kwargs):
        return _Stub(self._name)

    def __iter__(self):
        return iter(())


def build_stages() -> list[tuple[str, object]]:
    """The stages of a turn that are ours, in the order a turn meets them."""
    main, stubbed = _import_main()
    if stubbed:
        print(f"note: stubbed for this run: {', '.join(stubbed)}")
    from core import policy
    from memory import memory_manager

    template = (ROOT / "core" / "prompt.txt").read_text(encoding="utf-8", errors="replace")
    declarations = list(main.TOOL_DECLARATIONS)
    names = [d.get("name", "") for d in declarations if isinstance(d, dict)]

    values = {
        "assistant_name": "Ultron",
        "user_name": "Owner",
        "tools": main._describe_tools(declarations),
        "limits": main._describe_limits(True, True),
        "platform": "Windows",
        "memory": json.dumps({"identity": {"name": "Owner"}}, ensure_ascii=False),
        "date": "2026-11-06",
        "time": "10:30",
    }

    def describe_tools():
        main._describe_tools(declarations)

    def render_prompt():
        main._render_prompt(template, values)

    def load_prompt():
        main._load_system_prompt()

    def classify_all():
        for name in names:
            policy.decide(name, {"path": "notes.txt"})

    def read_memory():
        memory_manager.load_memory()

    def write_memory():
        memory_manager.save_memory(memory_manager.load_memory())

    def scrub():
        main._clean_transcript("  Ultron, open the \x07browser \x1b[0m please  ")

    return [
        ("policy.decide × every tool", classify_all),
        ("_describe_tools (all tools)", describe_tools),
        ("_render_prompt (system prompt)", render_prompt),
        ("_load_system_prompt (disk read)", load_prompt),
        ("memory load (JSON parse)", read_memory),
        ("memory load+save (atomic write)", write_memory),
        ("_clean_transcript", scrub),
    ]


def main_profiled(rounds: int, top: int) -> int:
    stages = build_stages()

    print(f"machine: {platform.platform()}  python {sys.version.split()[0]}")
    print(f"rounds: {rounds} per stage, median\n")
    print(f"{'stage':<34}{'median':>10}{'p95':>10}")
    total = 0.0
    rows = []
    for label, fn in stages:
        result = timeit(fn, rounds)
        if result["median_ms"] is None:
            print(f"{label:<34}{'skipped':>10}{'':>10}   {result['error'][:60]}")
            continue
        total += result["median_ms"]
        rows.append((label, result))
        print(f"{label:<34}{result['median_ms']:>8.3f} ms{result['p95_ms']:>8.3f} ms")
    print(f"\n{'sum of the stages above':<34}{total:>8.3f} ms")

    # The other lever the performance document lists: prompt length. It is not a
    # Python cost, it is a token cost paid by the provider on every request, so it
    # is reported in characters and an estimated token count rather than in ms.
    try:
        import main as _main
        base = _main._load_system_prompt()
        decls = list(_main.TOOL_DECLARATIONS)
        tools = _main._describe_tools(decls)
        limits = _main._describe_limits(True, True)
        rendered = _main._render_prompt(base, {
            "assistant_name": "Ultron", "user_name": "Owner", "tools": tools,
            "limits": limits, "platform": "Windows", "memory": "{}",
            "date": "2026-11-06", "time": "10:30"})
        print(f"\n{'prompt: base template':<34}{len(base):>8d} chars")
        print(f"{'prompt: tool descriptions':<34}{len(tools):>8d} chars"
              f"  ({len(decls)} tools)")
        print(f"{'prompt: limits block':<34}{len(limits):>8d} chars")
        print(f"{'prompt: assembled':<34}{len(rendered):>8d} chars"
              f"  (~{len(rendered) // 4} tokens)")
        print("Prompt length is a provider cost per request, not a Python cost.")
    except Exception as exc:
        print(f"\nprompt composition not measurable here: {type(exc).__name__}: {exc}")
    print("One model round trip is 600-4000 ms. Everything above is what Python")
    print("adds to it.")

    profile = cProfile.Profile()
    profile.enable()
    for _label, fn in stages:
        for _ in range(max(1, rounds // 4)):
            try:
                fn()
            except Exception:
                pass
    profile.disable()
    stream = io.StringIO()
    pstats.Stats(profile, stream=stream).sort_stats("cumulative").print_stats(top)
    print("\n--- cProfile, top "
          f"{top} by cumulative time (rounds/4 each) ---")
    print("\n".join(stream.getvalue().splitlines()[4:]))
    return 0


def cli() -> int:
    parser = argparse.ArgumentParser(description="profile the Python half of a turn")
    parser.add_argument("--rounds", type=int, default=200)
    parser.add_argument("--top", type=int, default=12)
    args = parser.parse_args()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return main_profiled(args.rounds, args.top)


if __name__ == "__main__":
    raise SystemExit(cli())
