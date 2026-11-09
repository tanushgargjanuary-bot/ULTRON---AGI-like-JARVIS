"""Ultron changing its own source: the five stages, and the four refusals.

    a proposal is not a change      nothing in the tree is written until `apply`;
    a rehearsal is a copy           the change is tried in a temporary tree, so a
                                    broken draft costs nothing that matters;
    two confirmations, two places   the same rule as the prompt editor, for the same
                                    reason: one yes can be a reflex;
    the referee is off limits       the files that decide permission, or record that
                                    a change happened, cannot be edited at all.

Every test runs against a small fake project in a temporary folder. The real tree is
never written by a test — that rule has held since the first commit and this module is
exactly the kind of thing that could break it.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import self_change

APP = "def greeting():\n    return 'hello'\n"
NEW_APP = "def greeting():\n    return 'hello, sir'\n"


class WithAFakeProject(unittest.TestCase):
    """A four-file project that looks enough like this one to be worth changing."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.project = Path(self._temp.name) / "project"
        self.project.mkdir()
        (self.project / "app.py").write_text(APP, encoding="utf-8")
        (self.project / "notes.md").write_text("# notes\n", encoding="utf-8")
        verify = self.project / "scripts" / "verify.py"
        verify.parent.mkdir(parents=True, exist_ok=True)
        verify.write_text(
            "import compileall, sys\n"
            "if not compileall.compile_dir('.', quiet=1):\n"
            "    sys.exit(1)\n"
            "print('full verification passed')\n",
            encoding="utf-8",
        )
        for protected in self_change.PROTECTED:
            path = self.project / protected
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("PROTECTED = True\n", encoding="utf-8")
        self_change.set_root(self.project)
        self_change.set_store(Path(self._temp.name) / "store")

    def tearDown(self):
        self_change.set_root(None)
        self_change.set_store(None)
        self._temp.cleanup()

    def read(self, name: str) -> str:
        return (self.project / name).read_text(encoding="utf-8")

    def staged(self, path="app.py", find="'hello'", replace="'hello, sir'",
               **kwargs) -> dict:
        # A whole-file replacement wins over find/replace inside `propose`, so
        # passing both is harmless and keeps this helper one line.
        return self_change.propose(path, kwargs.pop("reason", "a clearer greeting"),
                                   find=find, replace=replace, **kwargs)

    def ready(self, path="app.py", find="'hello'", replace="'hello, sir'") -> dict:
        """A proposal that has been rehearsed and confirmed twice."""
        proposal = self.staged(path=path, find=find, replace=replace)
        self_change.rehearse(proposal["id"])
        self_change.confirm(proposal["id"], "voice")
        self_change.confirm(proposal["id"], "panel")
        return proposal


class Staging(WithAFakeProject):
    def test_proposals_write_does_not_follow_the_old_fixed_temp_hardlink(self):
        store = self_change.store()
        external = self.project.parent / "external-proposals.txt"
        external.write_text("preserve this file", encoding="utf-8")
        legacy_temp = store / "proposals.tmp"
        try:
            os.link(external, legacy_temp)
        except OSError as error:
            self.skipTest(f"hard links are unavailable: {error}")

        self.staged()

        self.assertEqual(external.read_text(encoding="utf-8"), "preserve this file")
        self.assertEqual(legacy_temp.read_text(encoding="utf-8"), "preserve this file")
        self.assertTrue((store / "proposals.json").is_file())

    def test_a_proposal_writes_nothing_to_the_project(self):

        proposal = self.staged()
        self.assertEqual(self.read("app.py"), APP)
        self.assertEqual(proposal["stage"], "proposed")
        self.assertTrue(proposal["id"].startswith("c"))

    def test_a_change_needs_a_reason(self):
        with self.assertRaises(ValueError) as caught:
            self_change.propose("app.py", "")
        self.assertIn("reason", str(caught.exception))

    def test_a_passage_that_appears_twice_is_refused(self):
        (self.project / "twice.py").write_text("x = 1\nx = 1\n", encoding="utf-8")
        with self.assertRaises(ValueError) as caught:
            self.staged(path="twice.py", find="x = 1", replace="x = 2")
        self.assertIn("2 time(s)", str(caught.exception))

    def test_a_passage_that_is_not_there_is_refused(self):
        with self.assertRaises(ValueError):
            self.staged(find="not in the file", replace="anything")

    def test_a_change_that_changes_nothing_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            self.staged(find="'hello'", replace="'hello'")
        self.assertIn("exactly as it is", str(caught.exception))

    def test_the_whole_file_can_be_replaced(self):
        proposal = self.staged(path="notes.md", new_text="# better notes\n")
        self.assertEqual(proposal["after"], len("# better notes\n"))


class TheReferee(WithAFakeProject):
    def test_a_protected_file_is_refused_at_the_door(self):
        for relative in self_change.PROTECTED:
            with self.subTest(path=relative):
                with self.assertRaises(ValueError) as caught:
                    self_change.propose(relative, "let me in", new_text="open\n")
                self.assertIn("referee", str(caught.exception))

    def test_a_path_outside_the_project_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            self_change.propose("../../etc/passwd", "no", new_text="x\n")
        self.assertIn("outside", str(caught.exception))

    def test_an_absolute_path_is_refused(self):
        with self.assertRaises(ValueError):
            self_change.propose("/etc/passwd", "no", new_text="x\n")

    def test_the_history_folder_is_refused(self):
        with self.assertRaises(ValueError):
            self_change.propose(".git/config", "no", new_text="x\n")


    def test_a_symlink_alias_to_a_protected_file_is_refused(self):
        protected = self.project / "core" / "policy.py"
        alias = self.project / "policy-alias.py"
        try:
            alias.symlink_to(protected)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"symlink creation is unavailable: {error}")

        with self.assertRaises(ValueError):
            self_change.propose("policy-alias.py", "change through alias",
                                new_text="ALLOW EVERYTHING = True\n")
        self.assertEqual(protected.read_text(encoding="utf-8"), "PROTECTED = True\n")
        self.assertIsNone(self_change._inside("policy-alias.py"))

    def test_a_symlinked_directory_cannot_alias_the_protected_referee(self):
        core_alias = self.project / "core-alias"
        try:
            core_alias.symlink_to(self.project / "core", target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"directory symlink creation is unavailable: {error}")

        with self.assertRaises(ValueError):
            self_change.propose("core-alias/policy.py", "change through directory alias",
                                new_text="ALLOW EVERYTHING = True\n")
        self.assertEqual(self.read("core/policy.py"), "PROTECTED = True\n")


    def test_a_symlink_to_an_allowed_file_is_refused(self):
        alias = self.project / "change-alias.py"
        try:
            alias.symlink_to(self.project / "app.py")
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"symlink creation is unavailable: {error}")

        with self.assertRaisesRegex(ValueError, "outside"):
            self_change.propose("change-alias.py", "change through a link",
                                new_text=NEW_APP)
        self.assertEqual(self.read("app.py"), APP)

    def test_a_target_replaced_by_a_symlink_after_approval_is_not_written(self):
        proposal = self.ready(path="app.py")
        app = self.project / "app.py"
        try:
            app.unlink()
            app.symlink_to(self.project / "notes.md")
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"symlink creation is unavailable: {error}")

        with self.assertRaisesRegex(ValueError, "no longer a file"):
            self_change.apply(proposal["id"])
        self.assertEqual(self.read("notes.md"), "# notes\n")


class Rehearsal(WithAFakeProject):
    def test_the_copy_passes_and_the_body_is_untouched(self):
        proposal = self.staged()
        result = self_change.rehearse(proposal["id"])
        self.assertTrue(result["ok"], result["tail"])
        self.assertEqual(self.read("app.py"), APP, "the rehearsal wrote the real file")
        self.assertTrue(result["command"])
        self.assertEqual(self_change.pending()[0]["stage"], "rehearsed")

    def test_a_change_that_does_not_compile_fails_the_copy(self):
        proposal = self.staged(path="app.py", new_text="def broken(:\n")
        result = self_change.rehearse(proposal["id"])
        self.assertFalse(result["ok"])
        self.assertEqual(self.read("app.py"), APP)
        self.assertFalse(self_change.pending()[0]["rehearsed"])

    def test_a_failing_command_is_a_failed_rehearsal(self):
        proposal = self.staged()
        result = self_change.rehearse(proposal["id"],
                                      command=[sys.executable, "-c", "raise SystemExit(3)"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], 3)

    def test_the_full_harness_can_be_asked_for(self):
        proposal = self.staged()
        result = self_change.rehearse(
            proposal["id"], full=True,
            command=[sys.executable, "-c", "print('suite')"])
        self.assertTrue(result["ok"])
        self.assertTrue(result["full"])

    def test_rehearsing_a_change_that_does_not_exist_is_a_sentence(self):
        with self.assertRaises(ValueError):
            self_change.rehearse("cnosuchthing")


class Confirming(WithAFakeProject):
    def test_one_confirmation_is_not_enough(self):
        proposal = self.staged()
        self_change.rehearse(proposal["id"])
        self_change.confirm(proposal["id"], "voice")
        with self.assertRaises(ValueError) as caught:
            self_change.apply(proposal["id"])
        self.assertIn("1 of 2", str(caught.exception))

    def test_the_same_place_twice_does_not_count(self):
        proposal = self.staged()
        self_change.confirm(proposal["id"], "voice")
        said = self_change.confirm(proposal["id"], "voice")
        self.assertIn("already", said)
        self.assertEqual(len(self_change.pending()[0]["confirmations"]), 1)

    def test_a_place_that_is_not_a_channel_is_refused(self):
        proposal = self.staged()
        said = self_change.confirm(proposal["id"], "telepathy")
        self.assertIn("not one of them", said)

    def test_two_places_are_enough(self):
        proposal = self.staged()
        self_change.confirm(proposal["id"], "voice")
        said = self_change.confirm(proposal["id"], "cli")
        self.assertIn("Confirmed twice", said)


class Applying(WithAFakeProject):
    def test_apply_does_not_write_through_the_old_fixed_temp_hardlink(self):
        proposal = self.ready()
        external = self.project.parent / "external-apply.txt"
        external.write_text("preserve this file", encoding="utf-8")
        legacy_temp = (self.project / "app.py").with_suffix(".py.ultron-tmp")
        try:
            os.link(external, legacy_temp)
        except OSError as error:
            self.skipTest(f"hard links are unavailable: {error}")

        self_change.apply(proposal["id"])

        self.assertEqual(self.read("app.py"), NEW_APP)
        self.assertEqual(external.read_text(encoding="utf-8"), "preserve this file")
        self.assertEqual(legacy_temp.read_text(encoding="utf-8"), "preserve this file")

    def test_apply_replaces_a_linked_backup_without_writing_through_it(self):
        proposal = self.ready()
        backup_dir = self.project.parent / "store" / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f"{proposal['id']}.bak"
        external = self.project.parent / "external-backup.txt"
        external.write_text("preserve this file", encoding="utf-8")
        try:
            os.link(external, backup)
        except OSError as error:
            self.skipTest(f"hard links are unavailable: {error}")

        self_change.apply(proposal["id"])

        self.assertEqual(external.read_text(encoding="utf-8"), "preserve this file")
        self.assertEqual(backup.read_text(encoding="utf-8"), APP)

    def test_a_change_that_was_never_rehearsed_is_not_written(self):

        proposal = self.staged()
        self_change.confirm(proposal["id"], "voice")
        self_change.confirm(proposal["id"], "panel")
        with self.assertRaises(ValueError) as caught:
            self_change.apply(proposal["id"])
        self.assertIn("rehearsal", str(caught.exception))
        self.assertEqual(self.read("app.py"), APP)

    def test_a_rehearsed_and_confirmed_change_is_written(self):
        proposal = self.ready()
        result = self_change.apply(proposal["id"])
        self.assertTrue(result["ok"])
        self.assertEqual(self.read("app.py"), NEW_APP)

    def test_apply_refuses_to_overwrite_a_file_changed_after_proposal(self):
        proposal = self.ready()
        newer = "def greeting():\n    return 'newer edit'\n"
        (self.project / "app.py").write_text(newer, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed after this proposal"):
            self_change.apply(proposal["id"])
        self.assertEqual(self.read("app.py"), newer)

    def test_a_code_change_asks_for_a_restart(self):
        proposal = self.ready()
        result = self_change.apply(proposal["id"])
        self.assertTrue(result["restart_required"])
        marker = self_change.restart_required()
        self.assertEqual(marker["change"], proposal["id"])

    def test_a_data_change_does_not(self):
        proposal = self.staged(path="notes.md", new_text="# better notes\n")
        self_change.rehearse(proposal["id"])
        self_change.confirm(proposal["id"], "voice")
        self_change.confirm(proposal["id"], "panel")
        result = self_change.apply(proposal["id"])
        self.assertFalse(result["restart_required"])

    def test_the_old_bytes_are_kept(self):
        proposal = self.ready()
        self_change.apply(proposal["id"])
        kept = self.project.parent / "store" / "backups" / f"{proposal['id']}.bak"
        self.assertEqual(kept.read_text(encoding="utf-8"), APP)

    def test_every_applied_change_is_in_the_ledger(self):
        proposal = self.ready()
        self_change.apply(proposal["id"])
        rows = self_change.ledger()
        self.assertEqual(rows[0]["event"], "applied")
        self.assertEqual(rows[0]["path"], "app.py")
        self.assertIn("a clearer greeting", rows[0]["reason"])

    def test_the_restart_line_names_the_program(self):
        self.assertIn("main.py", self_change.restart_command())


class Reverting(WithAFakeProject):
    def test_revert_does_not_write_through_the_old_fixed_temp_hardlink(self):
        proposal = self.ready()
        self_change.apply(proposal["id"])
        external = self.project.parent / "external-revert.txt"
        external.write_text("preserve this file", encoding="utf-8")
        legacy_temp = (self.project / "app.py").with_suffix(".py.ultron-tmp")
        try:
            os.link(external, legacy_temp)
        except OSError as error:
            self.skipTest(f"hard links are unavailable: {error}")

        self_change.revert(proposal["id"])

        self.assertEqual(self.read("app.py"), APP)
        self.assertEqual(external.read_text(encoding="utf-8"), "preserve this file")
        self.assertEqual(legacy_temp.read_text(encoding="utf-8"), "preserve this file")

    def test_revert_puts_back_exactly_what_was_there(self):

        proposal = self.ready()
        self_change.apply(proposal["id"])
        said = self_change.revert(proposal["id"])
        self.assertIn("Put back", said)
        self.assertEqual(self.read("app.py"), APP)

    def test_revert_refuses_to_overwrite_a_file_changed_after_apply(self):
        proposal = self.ready()
        self_change.apply(proposal["id"])
        newer = "def greeting():\n    return 'newer edit'\n"
        (self.project / "app.py").write_text(newer, encoding="utf-8")
        said = self_change.revert(proposal["id"])
        self.assertIn("changed after", said)
        self.assertEqual(self.read("app.py"), newer)

    def test_revert_of_something_never_applied_is_refused(self):
        proposal = self.staged()
        self.assertIn("never applied", self_change.revert(proposal["id"]))

    def test_revert_of_something_that_does_not_exist_is_a_sentence(self):
        self.assertIn("no change called", self_change.revert("cnosuchthing"))


class TheTool(WithAFakeProject):
    @classmethod
    def setUpClass(cls):
        from actions import self_change as tool
        cls.tool = tool

    def call(self, **parameters) -> str:
        return self.tool.self_modify(parameters)

    def test_every_action_reaches_a_callable(self):
        for name in self.tool.ACTIONS:
            with self.subTest(action=name):
                self.assertTrue(callable(self.tool.ACTIONS[name]))

    def test_the_declaration_is_what_the_loader_expects(self):
        declaration = self.tool.TOOL
        self.assertEqual(declaration["name"], "self_modify")
        self.assertTrue(callable(declaration["handler"]))
        offered = set(declaration["parameters"]["properties"]["action"]["enum"])
        self.assertTrue(offered <= set(self.tool.ACTIONS))

    def test_rehearsal_cannot_disable_the_full_test_harness(self):
        with patch.object(self.tool.self_change, "rehearse", return_value={
            "ok": True,
            "command": f"{sys.executable} scripts/verify.py",
            "full": True,
        }) as rehearse:
            said = self.call(action="rehearse", change="c123", full=False)
        rehearse.assert_called_once_with("c123", full=True)
        self.assertIn("full test harness", said.lower())

    def test_staging_says_plainly_that_nothing_happened(self):
        said = self.call(action="propose", path="app.py", find="'hello'",
                         replace="'hi'", reason="shorter greeting")
        self.assertIn("Staged, not applied", said)
        self.assertEqual(self.read("app.py"), APP)

    def test_the_whole_walk_through_the_tool(self):
        said = self.call(action="propose", path="app.py", find="'hello'",
                         replace="'hello, sir'", reason="politer")
        change = self_change.pending()[0]["id"]
        self.assertIn("staged", said.lower())
        self.assertIn("full test harness passed", self.call(action="rehearse", change=change))
        self.call(action="confirm", change=change, channel="voice")
        self.call(action="confirm", change=change, channel="panel")
        applied = self.call(action="apply", change=change)
        self.assertIn("Applied", applied)
        self.assertIn("restart", applied.lower())
        self.assertEqual(self.read("app.py"), NEW_APP)
        self.assertIn("Put back", self.call(action="revert", change=change))
        self.assertEqual(self.read("app.py"), APP)

        with patch.object(self.tool.self_change, "apply", return_value={
                "path": "actions/open_app.py", "note": "legacy restart note"}), \
                patch.object(self.tool.self_change, "restart_required",
                             return_value={"change": "leaf-change"}), \
                patch.object(self.tool.self_change, "restart_command",
                             return_value="run.ps1"):
            leaf_note = self.tool.ACTIONS["apply"]({"change": "leaf-change"})
        self.assertIn("next provider reconnect", leaf_note)
        self.assertIn("restart immediately", leaf_note)

    def test_a_protected_file_is_refused_in_words(self):
        said = self.call(action="propose", path="core/policy.py", text="x",
                         reason="because")
        self.assertIn("referee", said)

    def test_a_failed_rehearsal_is_reported_as_a_failure(self):
        self.call(action="propose", path="app.py", text="def broken(:\n", reason="try")
        change = self_change.pending()[0]["id"]
        said = self.call(action="rehearse", change=change)
        self.assertIn("failed", said)

    def test_the_rules_name_the_five_stages_and_the_referee(self):
        said = self.call(action="rules")
        for stage in ("propose", "rehearse", "confirm", "apply", "revert"):
            self.assertIn(stage, said)
        self.assertIn("core/policy.py", said)

    def test_an_unknown_action_lists_what_it_can_do(self):
        self.assertIn("rehearse", self.call(action="levitate"))


if __name__ == "__main__":
    unittest.main()
