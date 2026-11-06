"""tests/test_schedule_packs.py — the queue, the packs, and the GitHub reminders.

Three features that only make sense together:

    schedule.Queue     when to interrupt, and when silence is correct
    skillpacks         how Ultron adds a skill to itself, as data
    github_tool        the watch list whose cards the queue orders
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import webapi
from custom_jarvis import skillpacks
from custom_jarvis.schedule import Queue
from custom_jarvis.service import CustomService
from custom_jarvis.skills import SKILL_BY_ID, SKILLS


def noon(day: int = 1) -> float:
    """Noon on a fixed day: never inside quiet hours, always reproducible."""
    return time.mktime((2026, 11, day, 12, 0, 0, 0, 0, -1))


class Queueing(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "reminders.json"

    def tearDown(self):
        self.folder.cleanup()

    def test_a_failing_build_outranks_a_trending_repository(self):
        queue = Queue(self.path)
        queue.add("trending:acme/rocket", "A new repository is trending",
                  urgency=0.35, value=0.9)
        queue.add("ci:mine/app", "The build is broken", urgency=0.9, value=1.5)
        due = queue.due(now=noon())
        self.assertEqual(due[0]["id"], "ci:mine/app")
        self.assertGreater(due[0]["score"], due[1]["score"])

    def test_quiet_hours_are_respected_until_it_is_an_emergency(self):
        queue = Queue(self.path, quiet_start=22, quiet_end=7)
        queue.add("pr:mine/app", "A pull request is waiting", urgency=0.5)
        queue.add("ci:mine/app", "Production is down", urgency=0.99, value=2.0)
        three_am = time.mktime((2026, 11, 2, 3, 0, 0, 0, 0, -1))
        self.assertTrue(queue.quiet(three_am))
        self.assertEqual([card["id"] for card in queue.due(now=three_am)],
                         ["ci:mine/app"])

    def test_the_same_card_is_not_repeated_inside_its_cooldown(self):
        queue = Queue(self.path, cooldown=3600)
        queue.add("notifications:all", "Three unread notifications", urgency=0.8)
        first = queue.due(now=noon())
        self.assertEqual(len(first), 1)
        queue.mark_shown([card["id"] for card in first], now=noon())
        self.assertEqual(queue.due(now=noon() + 60), [])
        later = queue.due(now=noon() + 3601)
        self.assertEqual(len(later), 1)

    def test_a_card_that_costs_more_than_it_is_worth_is_not_shown(self):
        queue = Queue(self.path)
        queue.add("noise:chatter", "Somebody commented somewhere",
                  urgency=0.05, value=0.5, cost=0.6)
        self.assertEqual(queue.due(now=noon()), [])

    def test_the_queue_survives_a_restart(self):
        queue = Queue(self.path)
        queue.add("ci:mine/app", "The build is broken", urgency=0.9)
        queue.mark_shown(["ci:mine/app"], now=noon())
        again = Queue(self.path)
        self.assertEqual(again.due(now=noon() + 10), [])
        self.assertEqual(again.cards()[0]["id"], "ci:mine/app")

    def test_a_damaged_file_is_replaced_by_an_empty_queue(self):
        self.path.write_text("{not json")
        queue = Queue(self.path)
        self.assertEqual(queue.cards(), [])
        queue.add("ci:x/y", "fine", urgency=0.5)
        self.assertEqual(len(Queue(self.path).cards()), 1)

    def test_a_card_needs_an_id(self):
        with self.assertRaises(ValueError):
            Queue(self.path).add("  ", "no id")


class Packs(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.directory = Path(self.folder.name)
        self.pack = {
            "id": "pack_todo_report",
            "title": "Todo report",
            "purpose": "Count the TODO markers in the workspace and list the first few.",
            "steps": [{"tool": "search_text",
                       "args": {"path": "@workspace", "query": "TODO"}}],
        }

    def tearDown(self):
        for identity in ("pack_todo_report", "second_pack"):
            SKILL_BY_ID.pop(identity, None)
            SKILLS[:] = [skill for skill in SKILLS if skill.identity != identity]
        self.folder.cleanup()

    def test_a_good_pack_installs_and_becomes_a_skill(self):
        result = skillpacks.install(self.pack, self.directory,
                                    ["search_text", "measure_code"])
        self.assertTrue(result["ok"], result)
        self.assertIn("pack_todo_report", SKILL_BY_ID)
        self.assertTrue((self.directory / "skills" / "pack_todo_report.json").exists())

    def test_a_pack_may_not_use_a_tool_that_writes(self):
        pack = dict(self.pack, steps=[{"tool": "write_file",
                                       "args": {"path": "@workspace/x.txt"}}])
        problems = skillpacks.validate(pack, ["write_file"])
        self.assertTrue(any("not a read-only tool" in line for line in problems))

    def test_a_pack_may_not_shadow_a_built_in(self):
        pack = dict(self.pack, id="secret_scan")
        problems = skillpacks.validate(pack, ["search_text"])
        self.assertTrue(any("already a skill" in line for line in problems))

    def test_a_pack_may_not_escape_the_workspace(self):
        for path in ("/etc/passwd", "../../secrets", "@elsewhere"):
            pack = dict(self.pack, steps=[{"tool": "search_text",
                                           "args": {"path": path, "query": "x"}}])
            problems = skillpacks.validate(pack, ["search_text"])
            self.assertTrue(problems, path)

    def test_a_pack_may_not_use_a_tool_this_build_lacks(self):
        pack = dict(self.pack, steps=[{"tool": "search_text", "args": {}}])
        problems = skillpacks.validate(pack, ["measure_code"])
        self.assertTrue(any("does not have" in line for line in problems))

    def test_too_many_steps_is_refused(self):
        steps = [{"tool": "search_text", "args": {"path": "@workspace"}}] * 9
        problems = skillpacks.validate(dict(self.pack, steps=steps), ["search_text"])
        self.assertTrue(any("at most 8" in line for line in problems))

    def test_remove_deletes_the_file_and_the_skill(self):
        skillpacks.install(self.pack, self.directory, ["search_text"])
        result = skillpacks.remove("pack_todo_report", self.directory)
        self.assertTrue(result["ok"])
        self.assertNotIn("pack_todo_report", SKILL_BY_ID)
        self.assertFalse((self.directory / "skills" / "pack_todo_report.json").exists())

    def test_a_built_in_cannot_be_removed_as_a_pack(self):
        result = skillpacks.remove("secret_scan", self.directory)
        self.assertFalse(result["ok"])
        self.assertIn("secret_scan", SKILL_BY_ID)

    def test_loading_a_folder_restores_what_was_installed(self):
        skillpacks.install(self.pack, self.directory, ["search_text"])
        skillpacks.remove("pack_todo_report", self.directory)
        skillpacks.install(self.pack, self.directory, ["search_text"])
        SKILL_BY_ID.pop("pack_todo_report", None)
        SKILLS[:] = [skill for skill in SKILLS if skill.identity != "pack_todo_report"]
        result = skillpacks.load(self.directory, ["search_text"])
        self.assertEqual(result["loaded"], ["pack_todo_report"])
        self.assertEqual(result["errors"], {})

    def test_a_broken_file_is_reported_not_crashed(self):
        folder = skillpacks.folder(self.directory)
        (folder / "junk.json").write_text("{oops")
        result = skillpacks.load(self.directory, ["search_text"])
        self.assertIn("junk.json", result["errors"])

    def test_the_pack_tools_are_in_the_service_and_ask_permission(self):
        asked = []
        service = CustomService(self.directory / "state",
                                approval=lambda kind, *rest: asked.append(kind) or True)
        names = {row["name"] for row in service.perform("list_tools", {})}
        for tool in ("add_skill", "remove_skill", "list_packs"):
            self.assertIn(tool, names)
        result = service.perform("tool", {"name": "add_skill",
                                          "arguments": {"pack": self.pack}})
        self.assertTrue(result["success"], result)
        self.assertIn("pack_todo_report", SKILL_BY_ID)
        listed = {row["id"] for row in service.perform("list_skills", {})}
        self.assertIn("pack_todo_report", listed)
        self.assertTrue(asked, "adding a skill must ask first")


class PackTools(unittest.TestCase):
    """pack_tools is the thin layer over skillpacks; it must not be clever."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        from custom_jarvis.pack_tools import register_pack_tools
        from custom_jarvis.tools import ToolRegistry
        self.registry = ToolRegistry()
        register_pack_tools(self.registry, self.folder.name, ["search_text"])

    def tearDown(self):
        SKILL_BY_ID.pop("pack_named_directly", None)
        SKILLS[:] = [skill for skill in SKILLS if skill.identity != "pack_named_directly"]
        self.folder.cleanup()

    def test_three_tools_are_registered_under_the_metacognition_category(self):
        rows = {row["name"]: row for row in self.registry.list_tools()}
        for name in ("add_skill", "remove_skill", "list_packs"):
            self.assertIn(name, rows)
            self.assertEqual(rows[name]["category"], "metacognition")

    def test_a_pack_can_be_added_and_listed_and_removed(self):
        from custom_jarvis import skillpacks
        pack = {"id": "pack_named_directly", "title": "Named directly",
                "purpose": "Proves the tool layer reaches the pack layer.",
                "steps": [{"tool": "search_text", "args": {"path": "@workspace",
                                                           "query": "x"}}]}
        self.assertTrue(skillpacks.install(pack, self.folder.name,
                                           ["search_text"])["ok"])
        listed = self.registry.execute("list_packs")
        self.assertIn("pack_named_directly", listed.output)
        self.assertTrue(self.registry.execute("remove_skill", id="pack_named_directly").success)


class FakeResponse:
    def __init__(self, body, status=200, headers=None):
        self._body = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.status = status
        self.headers = headers or {}

    def read(self, size=-1):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Reminders(unittest.TestCase):
    """The watch list, ordered by the queue, with no network in the room."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.home = Path(self.folder.name)
        self.env = mock.patch.dict(os.environ, {"XDG_DATA_HOME": str(self.home),
                                                "LOCALAPPDATA": str(self.home)})
        self.env.start()
        self.routes = {
            "*": FakeResponse({"workflow_runs": [], "items": [], "open": 0})}
        webapi.set_opener(self._open)
        # The queue's own clock behaviour is tested above with fixed times; here
        # the subject is the cards and their order, so quiet hours are silenced.
        self.calm = mock.patch.object(Queue, "quiet", return_value=False)
        self.calm.start()

    def _open(self, request, timeout=None):
        answer = self.routes.get(request.full_url, self.routes["*"])
        if isinstance(answer, Exception):
            raise answer
        return answer

    def tearDown(self):
        self.calm.stop()
        webapi.set_opener(None)
        self.env.stop()
        self.folder.cleanup()
        from plugins import github_tool
        watch = self.home / "CustomMarkJarvis" / "github_watch.json"
        if watch.exists():
            watch.unlink()

    def plugin(self):
        from plugins import github_tool
        return github_tool

    def test_an_empty_watch_list_says_how_to_start(self):
        self.assertIn("not watching anything", self.plugin().run({"action": "reminders"}))

    def test_a_failing_build_is_the_first_reminder(self):
        plugin = self.plugin()
        plugin.run({"action": "watch", "repository": "acme/rocket"})
        self.routes[f"{'https://api.github.com'}/repos/acme/rocket/actions/runs?per_page=3"] = \
            FakeResponse({"workflow_runs": [{"name": "verify", "head_branch": "main",
                                             "status": "completed",
                                             "conclusion": "failure"}]})
        text = plugin.run({"action": "reminders"})
        self.assertIn("acme/rocket", text)
        self.assertIn("failed", text)

    def test_the_same_reminder_is_not_repeated_immediately(self):
        plugin = self.plugin()
        plugin.run({"action": "watch", "repository": "acme/rocket"})
        self.routes["https://api.github.com/repos/acme/rocket/actions/runs?per_page=3"] = \
            FakeResponse({"workflow_runs": [{"name": "verify", "head_branch": "main",
                                             "status": "completed",
                                             "conclusion": "failure"}]})
        self.assertIn("failed", plugin.run({"action": "reminders"}))
        self.assertIn("Nothing needs you", plugin.run({"action": "reminders"}))

    def test_unwatch_removes_it(self):
        plugin = self.plugin()
        plugin.run({"action": "watch", "repository": "acme/rocket"})
        self.assertIn("acme/rocket", plugin.run({"action": "watchlist"}))
        self.assertIn("No longer watching", plugin.run(
            {"action": "unwatch", "repository": "acme/rocket"}))
        self.assertIn("empty", plugin.run({"action": "watchlist"}))

    def test_a_trending_language_becomes_a_reminder(self):
        plugin = self.plugin()
        plugin.run({"action": "watch", "language": "rust"})
        self.routes["*"] = FakeResponse({"items": [
            {"full_name": "acme/rocket", "description": "fast", "stargazers_count": 900,
             "language": "Rust", "html_url": "u"}]})
        text = plugin.run({"action": "reminders"})
        self.assertIn("Trending in rust", text)
        self.assertIn("acme/rocket", text)


if __name__ == "__main__":
    unittest.main()
