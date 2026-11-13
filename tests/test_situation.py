"""tests/test_situation.py - what the assistant knows about the machine.

Two claims are pinned here:

1. **The read is honest.** A version comes from the program's own record, or it
   is empty. A missing process library does not become "nothing is running".
2. **The read is private and passive.** No window titles, no command lines
   outside the Minecraft case, and no call that could start, stop or focus
   anything.

The process table is injected, so these tests say what the code does on this
machine without depending on what happens to be open on it.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from actions import situation_report as report_action  # noqa: E402
from core import situation  # noqa: E402


class NameTests(unittest.TestCase):
    """One process name in, one label out."""

    def test_browser_is_named_the_way_a_person_says_it(self):
        self.assertEqual(situation._kind("chrome.exe")[0], "Chrome")
        self.assertEqual(situation._kind("msedge.exe")[0], "Edge")

    def test_minecraft_needs_evidence_not_a_java_process(self):
        self.assertEqual(situation._kind("javaw.exe")[0], "Java")
        cmdline = ["javaw.exe", "-cp", "client.jar",
                   "net.minecraft.client.main.Main", "--version", "1.21.4"]
        self.assertEqual(situation._kind("javaw.exe", cmdline), ("Minecraft", "game"))

    def test_an_unknown_program_is_not_dressed_up(self):
        label, kind = situation._kind("somehelper.exe")
        self.assertEqual(kind, "other")
        self.assertEqual(label, "somehelper")

    def test_a_name_that_contains_a_known_name_is_not_that_app(self):
        # `opencode.exe` once read as VS Code because "code" was a substring.
        self.assertEqual(situation._kind("opencode.exe")[0], "OpenCode")
        self.assertEqual(situation._kind("code.exe")[0], "VS Code")
        self.assertEqual(situation._kind("bravecrashhandler.exe")[1], "other")

    def test_version_comes_from_the_launch_line(self):
        cmdline = ["java", "net.minecraft.client.main.Main", "--version", "1.21.4"]
        self.assertEqual(situation._minecraft_from_cmdline(cmdline), "1.21.4")

    def test_a_plain_java_line_has_no_minecraft_version(self):
        self.assertEqual(situation._minecraft_from_cmdline(["java", "-jar", "tool.jar"]), "")


class LauncherProfileTests(unittest.TestCase):
    """The launcher's own record, not a guess from a folder name."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)

    def tearDown(self):
        self.folder.cleanup()

    def test_most_recently_used_profile_wins(self):
        data = {
            "profiles": {
                "a": {"lastVersionId": "1.20.1", "lastUsed": "2026-01-01T10:00:00"},
                "b": {"lastVersionId": "1.21.4", "lastUsed": "2026-11-10T10:00:00"},
            }
        }
        (self.root / "launcher_profiles.json").write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(situation._profile_version(self.root), "1.21.4")

    def test_a_broken_profile_is_empty_not_an_exception(self):
        (self.root / "launcher_profiles.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(situation._profile_version(self.root), "")

    def test_installed_versions_are_the_fallback(self):
        versions = self.root / "versions"
        versions.mkdir()
        old = versions / "1.19.2"
        new = versions / "1.21.4"
        old.mkdir()
        new.mkdir()
        os.utime(old, (1_600_000_000, 1_600_000_000))
        os.utime(new, (1_700_000_000, 1_700_000_000))
        self.assertEqual(situation._newest_installed_version(self.root), "1.21.4")


class SnapshotTests(unittest.TestCase):
    """The summary the prompt and the tool both use."""

    def setUp(self):
        self.rows = [
            (10, "chrome.exe", "", ()),
            (11, "javaw.exe", "", ("javaw", "net.minecraft.client.main.Main",
                                  "--version", "1.21.4")),
            (12, "python.exe", "", ()),
        ]
        self._real = situation._iter_processes
        situation._iter_processes = lambda: list(self.rows)
        self._real_front = situation.foreground
        situation.foreground = lambda: situation.App("VS Code", 20, "editor", "1.95.0")

    def tearDown(self):
        situation._iter_processes = self._real
        situation.foreground = self._real_front

    def test_known_apps_and_versions_are_reported(self):
        apps = situation.running_apps()
        names = [app.name for app in apps]
        self.assertIn("Chrome", names)
        minecraft = [app for app in apps if app.name == "Minecraft"]
        self.assertEqual(minecraft[0].version, "1.21.4")

    def test_unknown_and_plain_java_processes_are_left_out(self):
        names = [app.name for app in situation.running_apps()]
        self.assertNotIn("python", names)
        self.assertNotIn("Java", names)

    def test_two_installs_of_one_app_are_one_line(self):
        self.rows.append((13, "msedge.exe", "", ()))
        self.rows.append((14, "msedge.exe", "", ()))
        names = [app.name for app in situation.running_apps()]
        self.assertEqual(names.count("Edge"), 1)

    def test_no_window_title_reaches_the_data(self):
        data = situation.snapshot().as_dict()
        for key in ("title", "titles", "window_title"):
            self.assertNotIn(key, data)
        for app in data["apps"]:
            self.assertEqual(set(app), {"name", "pid", "kind", "version"})

    def test_the_front_app_is_not_listed_twice(self):
        self.rows.append((20, "code.exe", "", ()))
        current = situation.snapshot()
        self.assertEqual(current.foreground.name, "VS Code")
        self.assertNotIn(20, [app.pid for app in current.apps])

    def test_the_sentence_names_the_front_app_and_a_game(self):
        sentence = situation.describe(situation.snapshot())
        self.assertIn("VS Code", sentence)
        self.assertIn("Minecraft 1.21.4", sentence)

    def test_a_missing_process_library_is_said_out_loud(self):
        situation._iter_processes = lambda: []
        real = situation.psutil
        situation.psutil = None
        try:
            current = situation.snapshot()
        finally:
            situation.psutil = real
        self.assertIn("psutil", current.note)


class ReportActionTests(unittest.TestCase):
    """The spoken half: same read, shaped as an answer."""

    def setUp(self):
        self.current = situation.Situation(
            foreground=situation.App("Chrome", 1, "browser", "141.0.7390.55"),
            apps=[situation.App("Minecraft", 2, "game", "1.21.4")],
        )
        self._snapshot = situation.snapshot
        self._running = situation.running_apps
        situation.snapshot = lambda **kwargs: self.current
        situation.running_apps = lambda only="", **kwargs: (
            [situation.App("Minecraft", 2, "game", "1.21.4")]
            if only.lower() == "minecraft" else []
        )

    def tearDown(self):
        situation.snapshot = self._snapshot
        situation.running_apps = self._running

    def test_a_short_answer_is_one_sentence(self):
        answer = report_action.situation_report({})
        self.assertIn("Chrome", answer)
        self.assertIn("Minecraft", answer)

    def test_a_named_app_that_is_absent_is_said_plainly(self):
        answer = report_action.situation_report({"app": "Spotify"})
        self.assertIn("not running", answer)

    def test_a_named_app_that_is_present_includes_its_version(self):
        answer = report_action.situation_report({"app": "Minecraft"})
        self.assertIn("1.21.4", answer)

    def test_full_detail_lists_each_app(self):
        answer = report_action.situation_report({"detail": "full"})
        self.assertIn("Minecraft", answer)

    def test_the_declaration_matches_the_handler(self):
        tool = report_action.TOOL
        self.assertEqual(tool["name"], "situation_report")
        self.assertIs(tool["handler"], report_action.situation_report)
        self.assertEqual(set(tool["parameters"]["properties"]), {"app", "detail"})


if __name__ == "__main__":
    unittest.main()
