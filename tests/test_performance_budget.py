"""tests/test_performance_budget.py — the Python half of a turn stays small.

Written after profiling it: the whole Python contribution to one exchange measures
0.165 ms on the build machine (scripts/profile_turn.py). The model round trip is
600-4000 ms, so this file guards the ratio that matters — Python must stay a
rounding error, not become a cost.

WHY A CEILING AND NOT A BENCHMARK
    A wall-clock assertion that says "under 0.5 ms" fails on a slow build server
    for reasons that have nothing to do with the code. So each ceiling here is at
    least twenty times the measured value. It cannot catch a 20 % regression, and
    it is not meant to: it catches the class of mistake that actually happens —
    a config file read on every turn, a regex compiled inside a loop, a JSON parse
    per tool. Those are factors, not percentages.
"""

from __future__ import annotations

import statistics
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Ceilings in milliseconds, twenty times or more the measured value.
CEILING = {
    "policy over every tool": 5.0,
    "describe every tool": 5.0,
    "render the system prompt": 5.0,
    "memory read": 5.0,
}


def load_main():
    """Import the program, or skip, on a machine with no audio device or kit.

    The stages measured here never touch a speaker, so a missing PortAudio is
    stubbed. A missing PyQt6 is not stubbable — it supplies base classes — so that
    machine skips, which is the same rule the audio claims follow.
    """
    try:
        import PyQt6  # noqa: F401
    except Exception as exc:                           # pragma: no cover
        raise unittest.SkipTest(f"PyQt6 not installed: {exc}")
    for name in ("sounddevice", "mss"):
        try:
            __import__(name)
        except Exception:
            sys.modules[name] = mock.MagicMock()
    try:
        import main
    except Exception as exc:                           # pragma: no cover
        raise unittest.SkipTest(f"main.py will not import here: {exc}")
    return main


def median_ms(fn, rounds: int = 30) -> float:
    samples = []
    for _ in range(rounds):
        started = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - started) * 1000.0)
    return statistics.median(samples)


class TurnBudget(unittest.TestCase):
    """Four measured stages of a turn, each with a generous ceiling."""

    @classmethod
    def setUpClass(cls):
        cls.main = load_main()

    def test_policy_classification_of_every_tool_is_cheap(self):
        from core import policy
        names = [d.get("name", "") for d in self.main.TOOL_DECLARATIONS
                 if isinstance(d, dict)]

        def run():
            for name in names:
                policy.decide(name, {"path": "notes.txt"})

        elapsed = median_ms(run)
        self.assertLess(elapsed, CEILING["policy over every tool"],
                        f"{len(names)} policy decisions took {elapsed:.2f} ms")

    def test_describing_every_tool_is_cheap(self):
        declarations = list(self.main.TOOL_DECLARATIONS)
        elapsed = median_ms(lambda: self.main._describe_tools(declarations))
        self.assertLess(elapsed, CEILING["describe every tool"],
                        f"describing {len(declarations)} tools took {elapsed:.2f} ms")

    def test_rendering_the_prompt_is_cheap(self):
        template = (ROOT / "core" / "prompt.txt").read_text(encoding="utf-8")
        values = {"assistant_name": "Ultron", "tools": "- one: does a thing" * 50,
                  "limits": "nothing", "date": "2026-11-06", "time": "10:30"}
        elapsed = median_ms(lambda: self.main._render_prompt(template, values))
        self.assertLess(elapsed, CEILING["render the system prompt"],
                        f"prompt rendering took {elapsed:.2f} ms")

    def test_reading_memory_is_cheap(self):
        from memory import memory_manager
        elapsed = median_ms(lambda: memory_manager.load_memory())
        self.assertLess(elapsed, CEILING["memory read"],
                        f"memory read took {elapsed:.2f} ms")


class PromptBudget(unittest.TestCase):
    """The system prompt is paid for by the provider on every request.

    Measured on the build machine: 15,534 characters of hand-written template,
    1,669 of tool descriptions and 1,107 of limits — 16,620 characters assembled,
    about 4,155 tokens. Nine tenths of it is persona and rules, and there is no
    duplicated line in it, so there is nothing to cut safely without a live
    evaluation of whether the assistant still behaves.

    What this test does instead of trimming blind: it stops the prompt from
    *growing* unnoticed, and it checks the two things that make it correct — every
    tool appears once, and no placeholder is left unfilled.
    """

    CEILING_CHARS = 20_000          # measured 16,620; about 20 % of headroom

    @classmethod
    def setUpClass(cls):
        cls.main = load_main()

    def assemble(self) -> tuple[str, str, str]:
        base = self.main._load_system_prompt()
        declarations = list(self.main.TOOL_DECLARATIONS)
        tools = self.main._describe_tools(declarations)
        limits = self.main._describe_limits(True, True)
        rendered = self.main._render_prompt(base, {
            "assistant_name": "Ultron", "user_name": "Owner", "tools": tools,
            "limits": limits, "platform": "Windows", "memory": '{"identity": {}}',
            "date": "2026-11-06", "time": "10:30"})
        return rendered, tools, base

    def test_the_assembled_prompt_stays_inside_its_budget(self):
        rendered, tools, base = self.assemble()
        self.assertLess(len(rendered), self.CEILING_CHARS,
                        f"the prompt is {len(rendered)} chars, over its "
                        f"{self.CEILING_CHARS} budget")
        # The template is the part a person edits, so it gets its own line here:
        # a jump in this figure is someone writing a new paragraph, not a bug.
        self.assertLess(len(base), 18_000, "the hand-written template has grown")

    def test_every_tool_appears_exactly_once(self):
        _rendered, tools, _base = self.assemble()
        names = [d.get("name") for d in self.main.TOOL_DECLARATIONS
                 if isinstance(d, dict) and d.get("name")]
        lines = [line for line in tools.splitlines() if line.startswith("- ")]
        self.assertEqual(len(lines), len(names), "a tool is missing from the prompt")
        for name in names:
            self.assertEqual(sum(1 for line in lines if line.startswith(f"- {name}:")
                                 or line == f"- {name}"), 1,
                             f"{name} appears more than once")

    def test_no_placeholder_is_left_unfilled(self):
        rendered, _tools, _base = self.assemble()
        for token in ("{tools}", "{limits}", "{memory}", "{assistant_name}",
                      "{user_name}", "{date}", "{time}", "{platform}"):
            self.assertNotIn(token, rendered, f"{token} was never filled in")


class NoWorkPerCall(unittest.TestCase):
    """The mistake a language change cannot fix: doing the same work twice."""

    def test_policy_tables_are_module_constants_not_built_per_call(self):
        from core import policy
        for name in ("OBSERVE_TOOLS", "ROUTINE_TOOLS", "GUARDED_TOOLS"):
            self.assertIsInstance(getattr(policy, name), (set, frozenset, dict),
                                  f"{name} is rebuilt on every decision")

    def test_the_transcript_regex_is_compiled_once(self):
        main = load_main()
        pattern = getattr(main, "_CTRL_RE", None)
        self.assertIsNotNone(pattern, "_CTRL_RE disappeared from main.py")
        self.assertTrue(hasattr(pattern, "sub"),
                        "the transcript scrub compiles its pattern per call")


if __name__ == "__main__":
    unittest.main()
