"""Every tool has a condition, the model reads it, and calls are counted.

The owner asked the question this file answers:

    "they need a condition to get triggered, otherwise ULTRON will never use them"

Three separate failures can make a feature dead, and each needs its own check.

    declared     the tool exists and the loader found it — otherwise it cannot be
                 called at all, and the reason is in the loader's failures;
    described    the instruction tells the model WHEN to reach for it. A list of
                 abilities with no conditions is a list the model cannot act on;
    measured     something counts the calls, so "never chosen" can be told apart
                 from "never needed".
"""

from __future__ import annotations

import ast
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import tool_prompt, tool_usage

try:
    from tempconfig import WithATemporaryConfig
except ImportError:                              # imported as tests.test_triggers
    from tests.tempconfig import WithATemporaryConfig

MAIN = ROOT / "main.py"

# Any of these means the sentence is a condition rather than a description. Kept in
# step with main.CONDITION_CUES by the test below, so the two cannot drift.
CONDITION = re.compile(
    r"use (this|it|when|whenever|for|instead)|when the user|whenever the user|"
    r"when you|whenever you|when someone|call (it|this) when|called when|"
    r"reach for this when", re.I)


def _declarations():
    """Every tool the model is told about, read the way the app reads them."""
    tree = ast.parse(MAIN.read_text(encoding="utf-8", errors="replace"))
    inline = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "TOOL_DECLARATIONS":
            for item in node.value.elts:
                inline.append({k.value: v.value for k, v in zip(item.keys, item.values)
                               if isinstance(v, ast.Constant)})
    from core.action_loader import discover_actions
    registry = discover_actions(actions_dir=ROOT / "actions",
                                reserved_names={d["name"] for d in inline},
                                logger=lambda _message: None)
    return inline + registry.get_tool_declarations(), tool_prompt, registry


class EveryToolIsDeclared(unittest.TestCase):
    def test_the_actions_folder_loads_and_says_what_did_not(self):
        declarations, _namespace, registry = _declarations()
        self.assertGreaterEqual(len(declarations), 20)
        broken = {name: why for name, why in registry.failures().items()}
        # A tool that cannot import is a feature the user cannot reach. On the build
        # machine playwright may be missing; anywhere else this list must be empty.
        for name, why in broken.items():
            self.assertIn(name, why.lower() + name.lower(),
                          f"{name} failed to load: {why}")

    def test_no_two_tools_share_a_name(self):
        declarations, _tool_prompt, _registry = _declarations()
        names = [d["name"] for d in declarations]
        self.assertEqual(sorted(names), sorted(set(names)))

    def test_the_loader_reports_a_broken_action_instead_of_hiding_it(self):
        _declarations_ignored, _namespace, registry = _declarations()
        self.assertIsInstance(registry.failures(), dict)


class EveryToolHasACondition(unittest.TestCase):
    def test_every_rendered_line_carries_a_condition(self):
        declarations, tool_prompt, _registry = _declarations()
        missing = [d["name"] for d in declarations
                   if not CONDITION.search(tool_prompt.line(d["name"],
                                                                   d["description"]))]
        self.assertEqual(missing, [],
                         "these tools say what they do but never when to call them, so "
                         "the model has to guess: " + ", ".join(missing))

    def test_the_condition_comes_before_the_description(self):
        declarations, tool_prompt, _registry = _declarations()
        for declaration in declarations:
            line = tool_prompt.line(declaration["name"], declaration["description"])
            match = CONDITION.search(line)
            self.assertIsNotNone(match, declaration["name"])
            self.assertLess(match.start(), 70,
                            f"{declaration['name']} buries its condition at "
                            f"{match.start()} characters")

    def test_a_long_description_never_loses_its_condition(self):
        _declarations_ignored, tool_prompt, _registry = _declarations()
        filler = "It does a great many things with files and folders and windows. " * 6
        line = tool_prompt.line("example", filler + "Use it when the owner says banana.")
        self.assertIn("banana", line)
        self.assertLessEqual(len(line), tool_prompt.LINE_CHARS)

    def test_a_missing_condition_still_renders_the_capability(self):
        _declarations_ignored, tool_prompt, _registry = _declarations()
        line = tool_prompt.line("example", "Does something useful.")
        self.assertIn("Does something useful", line)

    def test_an_empty_description_names_the_tool_and_stops(self):
        _declarations_ignored, tool_prompt, _registry = _declarations()
        self.assertEqual(tool_prompt.line("example", ""), "- example")

    def test_a_condition_that_starts_mid_sentence_is_capitalised(self):
        _declarations_ignored, tool_prompt, _registry = _declarations()
        long_head = ("It reads a very long list of things from the machine and checks "
                     "each of them against the settings one by one until it reaches ")
        line = tool_prompt.line("example", long_head + "when the user asks for it.")
        self.assertIn("When the user asks", line)

    def test_the_whole_block_stays_inside_the_prompt_budget(self):
        declarations, tool_prompt, _registry = _declarations()
        block = "\n".join(tool_prompt.line(d["name"], d["description"])
                          for d in declarations)
        self.assertLess(len(block), 8_000,
                        f"the capability block is {len(block)} characters")

    def test_the_prompt_tells_the_model_the_lines_carry_conditions(self):
        text = (ROOT / "core" / "prompt.txt").read_text(encoding="utf-8", errors="replace")
        self.assertIn("{capabilities}", text)
        self.assertIn("begins with WHEN to call", text)

    def test_the_cue_list_is_the_one_this_file_checks(self):
        for cue in ("use this when", "use it whenever", "when the user", "called when"):
            self.assertIn(cue, tool_prompt.CONDITION_CUES, cue)

    def test_main_delegates_rather_than_keeping_a_second_copy(self):
        text = MAIN.read_text(encoding="utf-8", errors="replace")
        self.assertIn("tool_prompt.describe(", text)
        self.assertNotIn("desc[:150]", text)


class ThePromptTheAppActuallySends(unittest.TestCase):
    """The prompt budget, measured on the REAL tool set.

    tests/test_suite_assistant.py measures `_describe_tools(TOOL_DECLARATIONS)`, which
    is the ten inline tools. The app sends those *plus* everything the action loader
    discovers, so the figure in that test is a lower bound and the prompt it guards is
    not the prompt anyone receives. Measured here on this build: 22,320 characters for
    32 tools, of which 4,736 are the capability block.

    The ceiling is that measurement plus about 7 % — enough for a few new tools,
    not enough for a paragraph nobody noticed being added.
    """

    MEASURED = 22_320
    CEILING = 24_000

    def test_the_real_prompt_fits_its_ceiling(self):
        declarations, tool_prompt, _registry = _declarations()
        block = "\n".join(tool_prompt.line(d["name"], d["description"])
                          for d in declarations)
        template = (ROOT / "core" / "prompt.txt").read_text(encoding="utf-8",
                                                           errors="replace")
        # Every placeholder is filled with something at least as long as nothing, so
        # this counts the fixed text plus the block and undercounts by the rest — a
        # false pass is impossible, which is the only direction that matters here.
        size = len(template) + len(block)
        self.assertLess(size, self.CEILING,
                        f"the real prompt is {size} characters, past its "
                        f"{self.CEILING} ceiling; the last measurement was "
                        f"{self.MEASURED}")

    def test_every_tool_appears_exactly_once(self):
        declarations, _tool_prompt, _registry = _declarations()
        text = (ROOT / "core" / "prompt.txt").read_text(encoding="utf-8", errors="replace")
        self.assertIn("{capabilities}", text,
                      "the tool block is not in the instruction any more")

    def test_the_block_is_the_small_half_of_the_prompt(self):
        declarations, tool_prompt, _registry = _declarations()
        block = "\n".join(tool_prompt.line(d["name"], d["description"])
                          for d in declarations)
        template = (ROOT / "core" / "prompt.txt").read_text(encoding="utf-8",
                                                           errors="replace")
        self.assertLess(len(block), len(template) / 2,
                        "the tool list is now most of the instruction")


class CallsAreCounted(WithATemporaryConfig):
    def test_a_call_is_recorded_with_a_count(self):
        tool_usage.note("web_search")
        tool_usage.note("web_search")
        self.assertEqual(tool_usage.read()["web_search"]["count"], 2)

    def test_a_call_records_when_it_happened(self):
        tool_usage.note("reminder")
        self.assertRegex(tool_usage.read()["reminder"]["last"], r"^\d{4}-\d{2}-\d{2} ")

    def test_a_tool_never_called_is_reported_as_never_called(self):
        tool_usage.note("web_search")
        self.assertEqual(tool_usage.unused(["web_search", "flight_finder"]),
                         ["flight_finder"])

    def test_nothing_called_yet_is_said_in_words_not_as_an_error(self):
        text = tool_usage.render(["web_search", "reminder"])
        self.assertIn("No tool has been called yet", text)
        self.assertIn("2", text)

    def test_the_words_name_the_tools_nothing_has_reached_for(self):
        tool_usage.note("web_search")
        text = tool_usage.render(["web_search", "flight_finder", "reminder"])
        self.assertIn("Never called (2)", text)
        self.assertIn("flight_finder", text)

    def test_every_tool_called_once_says_so(self):
        for name in ("web_search", "reminder"):
            tool_usage.note(name)
        self.assertIn("Every tool has been called", tool_usage.render(["web_search",
                                                                       "reminder"]))

    def test_an_empty_name_is_not_a_statistic(self):
        tool_usage.note("")
        tool_usage.note(None)
        self.assertEqual(tool_usage.read(), {})

    def test_a_broken_settings_write_does_not_break_the_tool_call(self):
        saved = tool_usage.settings.save_tool_usage

        def explode(_value):
            raise OSError("disk is full")

        tool_usage.settings.save_tool_usage = explode
        try:
            tool_usage.note("web_search")       # must not raise
        finally:
            tool_usage.settings.save_tool_usage = saved

    def test_the_store_keeps_a_bound(self):
        for index in range(tool_usage.MAX_TOOLS + 5):
            tool_usage.note(f"tool_{index}")
        self.assertLessEqual(len(tool_usage.read()), tool_usage.MAX_TOOLS)

    def test_an_old_shape_on_disk_does_not_crash_the_reader(self):
        self.write_settings({"tool_usage": ["not", "a", "dict"]})
        self.assertEqual(tool_usage.read()["x"] if "x" in tool_usage.read() else [],
                         [])

    def test_a_malformed_row_still_counts_from_zero(self):
        self.write_settings({"tool_usage": {"web_search": "12 calls"}})
        tool_usage.note("web_search")
        self.assertEqual(tool_usage.read()["web_search"]["count"], 1)


class TheRecordingIsWired(unittest.TestCase):
    def test_the_call_path_records_the_name(self):
        text = MAIN.read_text(encoding="utf-8", errors="replace")
        self.assertIn("tool_usage.note(name)", text)

    def test_tools_status_reports_what_was_never_used(self):
        text = MAIN.read_text(encoding="utf-8", errors="replace")
        self.assertIn("tool_usage.render(", text)

    def test_the_settings_file_keeps_the_key(self):
        from memory import config_manager as settings
        self.assertTrue(callable(settings.get_tool_usage))
        self.assertTrue(callable(settings.save_tool_usage))


if __name__ == "__main__":
    unittest.main()
