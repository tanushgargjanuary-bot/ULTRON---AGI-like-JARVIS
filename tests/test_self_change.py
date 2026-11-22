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
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import confirm as hud  # noqa: E402
from core import self_change
from core.confirm import request as put_up_a_banner  # noqa: E402

try:
    from tempprompt import press_the_button
except ImportError:                       # imported as tests.test_self_change
    from tests.tempprompt import press_the_button

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


class WithABanner(WithAFakeProject):
    """The interface: a banner the test can press, standing where ui.py stands."""

    def setUp(self):
        super().setUp()
        self.banners: list[tuple[str, str]] = []
        self.hud_log: list[str] = []
        hud.bind(show=lambda title, detail: self.banners.append((title, detail)),
                 hide=lambda: None, log=self.hud_log.append)
        self.addCleanup(self._unbind)

    @staticmethod
    def _unbind():
        hud._show_cb = hud._hide_cb = hud._log_cb = None
        hud._pending = None

    def click(self, accepted: bool = True) -> str:
        """Press CONFIRM (or CANCEL) on the banner that is up, and wait for the work."""
        return press_the_button(self.hud_log, accepted)


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

    def test_the_github_folder_is_refused(self):
        with self.assertRaises(ValueError):
            self_change.propose(".github/workflows/verify.yml", "no", new_text="x\n")


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

    # `restart_command()` reads only `os.name`, so the tests pin it: the answer is different on
    # Windows, and a test that depended on the machine running it passed on Linux and failed on the
    # first Windows run (the fake project holds a `run.ps1` now that the launcher is protected).
    def test_the_restart_line_names_the_program(self):
        with patch.object(self_change, "os", types.SimpleNamespace(name="posix")):
            self.assertIn("main.py", self_change.restart_command())

    def test_on_windows_the_restart_line_names_the_launcher_when_there_is_one(self):
        self.assertTrue((self.project / "run.ps1").exists(), "the fake project has a launcher")
        with patch.object(self_change, "os", types.SimpleNamespace(name="nt")):
            line = self_change.restart_command()
        self.assertIn("run.ps1", line, "the launcher keeps the boot guard on; main.py would skip it")
        self.assertNotIn("main.py", line)

    def test_on_windows_without_a_launcher_the_restart_line_names_main_py(self):
        (self.project / "run.ps1").unlink()
        with patch.object(self_change, "os", types.SimpleNamespace(name="nt")):
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


class TheTool(WithABanner):
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
        self.call(action="confirm", change=change)         # the yes, and the button goes up
        self.click()                                         # the owner presses it
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


class TheSecondConfirmationIsAPress(WithABanner):
    """`confirm` records the first yes and puts a button up. Only the press records the second.

    The two confirmations used to be two `confirm` calls whose `channel` argument the model wrote
    (voice, then panel), so a model could stage, rehearse, confirm, confirm and apply with the only
    human step being the approval banner on each call, which shows call arguments and not the change.
    """

    @classmethod
    def setUpClass(cls):
        from actions import self_change as tool
        cls.tool = tool

    def call(self, **parameters) -> str:
        return self.tool.self_modify(parameters)

    def rehearsed(self, path="app.py", find="'hello'", replace="'hello, sir'", reason="politer",
                  **kwargs) -> str:
        proposal = self_change.propose(path, reason, find=find, replace=replace, **kwargs)
        self.assertIn("passed", self.call(action="rehearse", change=proposal["id"]))
        return proposal["id"]

    def confirmations(self, change: str) -> list[str]:
        return self_change.review(change)["confirmations"]

    def test_stage_rehearse_confirm_voice_confirm_panel_applies_nothing(self):
        change = self.rehearsed()
        self.call(action="confirm", change=change, channel="voice")
        self.call(action="confirm", change=change, channel="panel")
        said = self.call(action="apply", change=change)
        self.assertIn("1 of 2", said)
        self.assertEqual(self.read("app.py"), APP, "no person pressed anything")

    def test_a_channel_the_model_names_is_not_recorded(self):
        change = self.rehearsed()
        self.call(action="confirm", change=change, channel="panel")
        self.assertEqual(self.confirmations(change), ["voice"], "the model does not get to say 'panel'")

    def test_no_label_the_model_can_send_is_taken_for_the_press(self):
        change = self.rehearsed()
        for label in ("cli", "panel", "voice", "PANEL", "anything", ""):
            self.call(action="approve", change=change, channel=label)
        self.assertEqual(self.confirmations(change), ["voice"])
        self.assertEqual(self.read("app.py"), APP)

    def test_with_no_interface_nothing_is_recorded_as_a_press_and_it_says_so(self):
        hud._show_cb = None
        change = self.rehearsed()
        said = self.call(action="confirm", change=change)
        self.assertIn("not available", said)
        self.assertEqual(self.confirmations(change), ["voice"])

    def test_the_press_records_the_second_place_and_apply_then_writes(self):
        change = self.rehearsed()
        said = self.call(action="confirm", change=change)
        self.assertIn("CONFIRMATION_PENDING", said)
        self.assertIn("Your yes is recorded (1 of 2)", said)
        self.assertEqual(self.read("app.py"), APP, "putting a button up writes nothing")
        self.click()
        self.assertEqual(self.confirmations(change), ["voice", "panel"])
        self.assertEqual(self.read("app.py"), APP, "the press confirms; it does not apply")
        self.assertIn("Applied", self.call(action="apply", change=change))
        self.assertEqual(self.read("app.py"), NEW_APP)

    def test_cancel_records_nothing_and_the_owner_can_be_asked_again(self):
        change = self.rehearsed()
        self.call(action="confirm", change=change)
        self.click(False)
        self.assertEqual(self.confirmations(change), ["voice"])
        self.call(action="confirm", change=change)
        self.assertEqual(len(self.banners), 2)
        self.click()
        self.assertEqual(self.confirmations(change), ["voice", "panel"])

    def test_a_banner_for_something_else_is_not_overwritten(self):
        put_up_a_banner("shutdown", "Shut down?", "", lambda: "off")
        change = self.rehearsed()
        said = self.call(action="confirm", change=change)
        self.assertIn("Another confirmation is waiting", said)
        self.assertEqual(hud.pending_title(), "Shut down?")
        self.assertEqual(len(self.banners), 1, "only the first banner was ever shown")
        self.assertNotIn("panel", self.confirmations(change))

    def test_a_change_that_was_not_rehearsed_gets_no_button(self):
        proposal = self_change.propose("app.py", "politer", find="'hello'", replace="'hello, sir'")
        said = self.call(action="confirm", change=proposal["id"])
        self.assertIn("has not passed a rehearsal", said)
        self.assertEqual(self.banners, [])
        self.assertEqual(self.confirmations(proposal["id"]), [])

    def test_a_change_confirmed_twice_does_not_put_up_a_second_button(self):
        change = self.rehearsed()
        self.call(action="confirm", change=change)
        self.click()
        said = self.call(action="confirm", change=change)
        self.assertIn("already confirmed twice", said)
        self.assertEqual(len(self.banners), 1)

    def test_a_change_swapped_after_the_banner_is_not_recorded(self):
        change = self.rehearsed()
        self.call(action="confirm", change=change)
        data = self_change._load_proposals()                 # something rewrites the staged change
        data[change]["new"] = data[change]["new"].replace("hello, sir", "os.system('x')")
        self_change._save_proposals(data)
        said = self.click()
        self.assertIn("not the change that was shown", said)
        self.assertEqual(self.confirmations(change), ["voice"])

    def test_a_change_dropped_after_the_banner_is_not_recorded(self):
        change = self.rehearsed()
        self.call(action="confirm", change=change)
        data = self_change._load_proposals()
        data.pop(change)
        self_change._save_proposals(data)
        self.assertIn("is gone", self.click())

    def test_the_banner_lists_every_changed_line_and_says_how_many(self):
        old = "".join(f"value_{n} = {n}\n" for n in range(60))
        new = "".join(f"value_{n} = {n + 1}\n" for n in range(60))
        (self.project / "many.py").write_text(old, encoding="utf-8")
        change = self.rehearsed("many.py", find=None, replace=None, new_text=new)
        self.call(action="confirm", change=change)
        detail = self.banners[0][1]
        for n in range(60):
            self.assertIn(f"-value_{n} = {n}\n", detail + "\n")
            self.assertIn(f"+value_{n} = {n + 1}\n", detail + "\n")
        self.assertIn("Every changed line (120)", detail)
        self.assertIn(change, detail)
        self.assertIn("many.py", detail)

    def test_the_banner_says_what_was_run_in_the_copy(self):
        change = self.rehearsed()
        self.call(action="confirm", change=change)
        self.assertIn("the full test harness passed in a copy", self.banners[0][1])

    def test_a_changed_line_that_starts_with_dashes_is_on_the_banner(self):
        (self.project / "a.sql").write_text("-- a comment\nx = 1\n", encoding="utf-8")
        change = self.rehearsed("a.sql", find=None, replace=None, new_text="++ other\nx = 1\n")
        self.call(action="confirm", change=change)
        detail = self.banners[0][1]
        self.assertIn("--- a comment", detail, "a removed line that starts '--' is a '---' row")
        self.assertIn("+++ other", detail, "an added line that starts '++' is a '+++' row")

    def test_a_character_that_changes_how_text_looks_is_written_out(self):
        (self.project / "b.py").write_text("name = 'evil'\n", encoding="utf-8")
        change = self.rehearsed("b.py", find="'evil'", replace="'evil\u202egpj.exe'")
        self.call(action="confirm", change=change)
        detail = self.banners[0][1]
        self.assertNotIn("\u202e", detail)
        self.assertIn("\\u202e", detail)

    def test_the_reason_is_the_models_and_is_bounded(self):
        change = self.rehearsed(reason="reassuring " * 500)
        self.call(action="confirm", change=change)
        reason = next(line for line in self.banners[0][1].splitlines() if line.startswith("Reason"))
        self.assertLessEqual(len(reason), len("Reason, as the model wrote it: ") + self.tool.REASON_LIMIT + 1)

    def test_a_change_too_big_to_read_is_refused_before_any_yes_and_any_button(self):
        old = "".join(f"v{n} = 'an existing line of code, number {n}'\n" for n in range(700))
        new = "".join(f"v{n} = 'a replaced line of code, number {n}!'\n" for n in range(700))
        (self.project / "big.py").write_text(old, encoding="utf-8")
        proposal = self_change.propose("big.py", "a rewrite", new_text=new)
        self.assertIn("passed", self.call(action="rehearse", change=proposal["id"]))
        said = self.call(action="confirm", change=proposal["id"])
        self.assertIn("will not put up a button", said)
        self.assertEqual(self.banners, [])
        self.assertEqual(self.confirmations(proposal["id"]), [], "no yes was recorded either")

    def test_staging_a_change_too_big_to_read_says_so_at_once(self):
        old = "".join(f"v{n} = 'an existing line of code, number {n}'\n" for n in range(700))
        new = "".join(f"v{n} = 'a replaced line of code, number {n}!'\n" for n in range(700))
        (self.project / "big.py").write_text(old, encoding="utf-8")
        said = self.call(action="propose", path="big.py", text=new, reason="a rewrite")
        self.assertIn("will not put up a button", said)

    def test_the_tool_declares_no_channel_and_the_rules_do_not_promise_one(self):
        self.assertNotIn("channel", self.tool.TOOL["parameters"]["properties"])
        rules = self.call(action="rules")
        self.assertNotIn("voice, panel", rules)
        self.assertIn("CONFIRM button", rules)

    def test_the_old_two_call_api_still_counts_for_the_code_that_calls_it_directly(self):
        # scripts/proof_gate.py checks the counting rule this way, not through the tool.
        proposal = self.staged()
        self_change.rehearse(proposal["id"])
        self_change.confirm(proposal["id"], "voice")
        self.assertIn("Confirmed twice", self_change.confirm(proposal["id"], "panel"))


class TheDifferenceIsEveryChangedLine(WithAFakeProject):
    """`diff` showed what a person asks of it, or it did not: three ways it did not."""

    def stage_text(self, old: str, new: str) -> str:
        (self.project / "d.py").write_text(old, encoding="utf-8")
        return self_change.propose("d.py", "a test", new_text=new)["id"]

    def rows(self, change: str, limit: int = 40) -> list[str]:
        return [line.strip() for line in self_change.diff(change, limit).splitlines()[1:]]

    def test_a_line_added_a_second_time_is_shown(self):
        old = "def a():\n    remove(path)\n\ndef b():\n    pass\n"
        new = "def a():\n    remove(path)\n\ndef b():\n    remove(path)\n"
        rows = self.rows(self.stage_text(old, new))
        self.assertEqual(rows, ["-     pass", "+     remove(path)"],
                         "a line the file already had, now added in a second place")

    def test_a_line_removed_from_one_place_and_still_standing_in_another_is_shown(self):
        change = self.stage_text("remove(path)\nx = 1\nremove(path)\n", "remove(path)\nx = 1\n")
        text = self_change.diff(change)
        self.assertIn("- remove(path)", text)
        self.assertNotIn("only the order", text)

    def test_a_list_cut_at_the_limit_says_how_many_rows_it_did_not_show(self):
        change = self.stage_text("", "".join(f"line_{n} = {n}\n" for n in range(60)))
        text = self_change.diff(change, limit=40)
        self.assertEqual(text.count("\n  + line_"), 40)
        self.assertIn("20 more changed line(s) are not shown", text)

    def test_a_limit_of_zero_lists_every_row_and_adds_no_marker(self):
        change = self.stage_text("", "".join(f"line_{n} = {n}\n" for n in range(60)))
        text = self_change.diff(change, limit=0)
        self.assertEqual(text.count("\n  + line_"), 60)
        self.assertNotIn("not shown", text)

    def test_a_list_that_fits_has_no_marker(self):
        change = self.stage_text("a = 1\n", "a = 2\n")
        self.assertNotIn("not shown", self_change.diff(change))

    def test_a_changed_line_that_starts_with_dashes_or_pluses_is_shown(self):
        change = self.stage_text("-- old comment\nx = 1\n", "++ new line\nx = 1\n")
        rows = self.rows(change)
        self.assertEqual(rows, ["- -- old comment", "+ ++ new line"])

    def test_a_difference_in_line_endings_only_is_said_not_shown_as_nothing(self):
        change = self.stage_text("a = 1\n", "a = 1")
        self.assertIn("no line differs", self_change.diff(change))

    def test_an_unknown_change_is_a_sentence(self):
        self.assertIn("no change called", self_change.diff("cnosuchthing"))

    def test_the_tools_show_action_lists_more_than_twenty_rows(self):
        from actions import self_change as tool
        change = self.stage_text("", "".join(f"line_{n} = {n}\n" for n in range(60)))
        said = tool.self_modify({"action": "show", "change": change})
        self.assertEqual(said.count("\n  + line_"), 60)

    def test_the_review_holds_every_row_and_a_digest_that_follows_the_text(self):
        first = self.stage_text("a = 1\n", "a = 2\n")
        view = self_change.review(first)
        self.assertEqual(view["rows"], ["-a = 1", "+a = 2"])
        self.assertEqual(view["digest"], self_change.review(first)["digest"])
        second = self.stage_text("a = 1\n", "a = 3\n")
        self.assertNotEqual(view["digest"], self_change.review(second)["digest"])
        data = self_change._load_proposals()
        data[first]["new"] = "a = 99\n"
        self_change._save_proposals(data)
        self.assertNotEqual(view["digest"], self_change.review(first)["digest"])

    def test_the_review_of_nothing_is_none(self):
        self.assertIsNone(self_change.review("cnosuchthing"))


class TheRehearsalCopy(WithAFakeProject):
    """A full rehearsal of this repository failed nine tests and errored on six more, because the copy
    left out `.github` and the tests read the workflow files there."""

    def lay_out_a_project_like_the_real_one(self):
        (self.project / ".github" / "workflows").mkdir(parents=True)
        (self.project / ".github" / "workflows" / "verify.yml").write_text("name: verify\n", encoding="utf-8")
        (self.project / ".git").mkdir()
        (self.project / ".git" / "THE_REAL_HISTORY").write_text("commits\n", encoding="utf-8")
        (self.project / ".gitignore").write_text("config/api_keys.json\n", encoding="utf-8")
        for name in (".venv", "node_modules", "uploads", "__pycache__"):
            (self.project / name).mkdir()
            (self.project / name / "x").write_text("x", encoding="utf-8")

    PROBE = (
        "import os, sys\n"
        "need = ['.github/workflows/verify.yml', 'app.py']\n"
        "gone = ['.git/THE_REAL_HISTORY', '.venv', 'node_modules', 'uploads', '__pycache__']\n"
        "bad = [p for p in need if not os.path.exists(p)] + [p for p in gone if os.path.exists(p)]\n"
        "print('wrong in the copy:', bad)\n"
        "sys.exit(1 if bad else 0)\n"
    )

    def test_the_copy_has_the_workflows_and_leaves_out_the_history_and_the_packages(self):
        self.lay_out_a_project_like_the_real_one()
        proposal = self.staged()
        result = self_change.rehearse(proposal["id"], command=[sys.executable, "-c", self.PROBE])
        self.assertTrue(result["ok"], result["tail"])

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_the_copy_is_a_repository_of_one_commit_that_knows_what_is_ignored_and_what_is_tracked(self):
        self.lay_out_a_project_like_the_real_one()
        proposal = self.staged()
        git = shutil.which("git")
        probe = (
            f"import subprocess, sys\n"
            f"def ask(*args):\n"
            f"    return subprocess.run([{git!r}, *args], capture_output=True, text=True)\n"
            f"ignored = ask('check-ignore', '-q', 'config/api_keys.json').returncode\n"
            f"commits = ask('rev-list', '--count', 'HEAD').stdout.strip()\n"
            f"tracked = ask('ls-files').stdout.split()\n"
            f"waiting = ask('status', '--porcelain', '--untracked-files=all').stdout.split()\n"
            f"print('ignored:', ignored, 'commits:', commits, 'tracked:', tracked, 'waiting:', waiting)\n"
            f"ok = (ignored == 0 and commits == '1' and 'app.py' in tracked\n"
            f"      and 'THE_REAL_HISTORY' not in ' '.join(tracked))\n"
            f"sys.exit(0 if ok else 1)\n")
        result = self_change.rehearse(proposal["id"], command=[sys.executable, "-c", probe])
        self.assertTrue(result["ok"], result["tail"])

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_the_change_is_written_after_the_commit_so_it_reads_as_an_edit(self):
        self.lay_out_a_project_like_the_real_one()
        proposal = self.staged()
        git = shutil.which("git")
        probe = (f"import subprocess, sys\n"
                 f"out = subprocess.run([{git!r}, 'status', '--porcelain'], capture_output=True, text=True).stdout\n"
                 f"print(out)\n"
                 f"sys.exit(0 if out.split() == ['M', 'app.py'] else 1)\n")
        result = self_change.rehearse(proposal["id"], command=[sys.executable, "-c", probe])
        self.assertTrue(result["ok"], result["tail"])

    def test_a_machine_without_git_still_gets_a_copy(self):
        self.lay_out_a_project_like_the_real_one()
        proposal = self.staged()
        with patch.object(self_change.shutil, "which", return_value=None):
            result = self_change.rehearse(proposal["id"], command=[sys.executable, "-c", "print('ok')"])
        self.assertTrue(result["ok"], result["tail"])

    def test_a_git_that_will_not_start_is_noted_and_the_copy_still_runs(self):
        from core import failures
        failures.clear()
        self.lay_out_a_project_like_the_real_one()
        proposal = self.staged()
        with patch.object(self_change.shutil, "which", return_value="/no/such/folder/git"):
            result = self_change.rehearse(proposal["id"], command=[sys.executable, "-c", "print('ok')"])
        self.assertTrue(result["ok"], result["tail"])
        self.assertIn("self_change.copy_git", failures.summary())

    def test_having_the_workflows_in_the_copy_does_not_make_them_writable(self):
        self.lay_out_a_project_like_the_real_one()
        self.assertIn(".github", self_change.SKIP_DIRS)
        self.assertNotIn(".github", self_change.COPY_SKIP)
        self.assertIn(".git", self_change.COPY_SKIP)
        with self.assertRaises(ValueError):
            self_change.propose(".github/workflows/verify.yml", "edit the CI", new_text="name: x\n")

    def test_the_real_tree_is_untouched_by_a_rehearsal(self):
        self.lay_out_a_project_like_the_real_one()
        proposal = self.staged()
        self_change.rehearse(proposal["id"], command=[sys.executable, "-c", "print('ok')"])
        self.assertEqual(self.read("app.py"), APP)
        self.assertEqual(sorted(path.name for path in (self.project / ".github").iterdir()), ["workflows"])


class ALineEndingIsNotAChange(WithAFakeProject):
    """`revert` says the file is "exactly what it was before". For a file with Windows line ends it was
    not: the text of a change is held with Unix line ends, `apply` wrote them out for every line of the
    file, and the kept copy had lost the Windows ones, so the put-back was a different file."""

    WINDOWS = b"Write-Host 'one'\r\nWrite-Host 'two'\r\n"

    def stage_in(self, name: str, original: bytes, find="'two'", replace="'three'") -> str:
        (self.project / name).write_bytes(original)
        proposal = self_change.propose(name, "a test", find=find, replace=replace)
        self_change.rehearse(proposal["id"], command=[sys.executable, "-c", "pass"])
        self_change.confirm(proposal["id"], "voice")
        self_change.confirm(proposal["id"], "panel")
        return proposal["id"]

    def raw(self, name: str) -> bytes:
        return (self.project / name).read_bytes()

    def test_a_windows_file_stays_windows_after_a_change_and_comes_back_byte_for_byte(self):
        change = self.stage_in("tool.ps1", self.WINDOWS)
        self_change.apply(change)
        self.assertEqual(self.raw("tool.ps1"), b"Write-Host 'one'\r\nWrite-Host 'three'\r\n",
                         "every line keeps its Windows line end, not only the changed one")
        self.assertIn("exactly what it was", self_change.revert(change))
        self.assertEqual(self.raw("tool.ps1"), self.WINDOWS)

    def test_the_kept_copy_is_the_exact_bytes(self):
        change = self.stage_in("tool.ps1", self.WINDOWS)
        self_change.apply(change)
        self.assertEqual((self_change.store() / "backups" / f"{change}.bak").read_bytes(), self.WINDOWS)

    def test_a_file_with_mixed_line_ends_is_written_with_unix_ends_and_still_comes_back_exactly(self):
        mixed = b"a = 1\r\nb = 2\nc = 3\r\n"
        change = self.stage_in("mixed.txt", mixed, find="b = 2", replace="b = 9")
        self_change.apply(change)
        self.assertEqual(self.raw("mixed.txt"), b"a = 1\nb = 9\nc = 3\n", "there is no one style to keep")
        self_change.revert(change)
        self.assertEqual(self.raw("mixed.txt"), mixed)

    def test_a_unix_file_stays_unix(self):
        change = self.stage_in("unix.txt", b"a = 1\nb = 2\n", find="b = 2", replace="b = 3")
        self_change.apply(change)
        self.assertEqual(self.raw("unix.txt"), b"a = 1\nb = 3\n")

    def test_a_change_whose_text_has_windows_line_ends_does_not_double_them(self):
        (self.project / "tool.ps1").write_bytes(self.WINDOWS)
        proposal = self_change.propose("tool.ps1", "a test",
                                       new_text="Write-Host 'one'\r\nWrite-Host 'three'\r\n")
        self_change.rehearse(proposal["id"], command=[sys.executable, "-c", "pass"])
        self_change.confirm(proposal["id"], "voice")
        self_change.confirm(proposal["id"], "panel")
        self_change.apply(proposal["id"])
        self.assertEqual(self.raw("tool.ps1"), b"Write-Host 'one'\r\nWrite-Host 'three'\r\n")

    def test_the_rehearsal_copy_holds_the_bytes_apply_would_write(self):
        (self.project / "tool.ps1").write_bytes(self.WINDOWS)
        proposal = self_change.propose("tool.ps1", "a test", find="'two'", replace="'three'")
        probe = ("import sys\n"
                 "data = open('tool.ps1', 'rb').read()\n"
                 "print(data)\n"
                 "sys.exit(0 if data == b\"Write-Host 'one'\\r\\nWrite-Host 'three'\\r\\n\" else 1)\n")
        result = self_change.rehearse(proposal["id"], command=[sys.executable, "-c", probe])
        self.assertTrue(result["ok"], result["tail"])

    def test_a_file_that_is_not_utf8_is_refused_at_the_door(self):
        (self.project / "legacy.txt").write_bytes(b"caf\xe9 = 1\n")
        with self.assertRaises(ValueError) as caught:
            self_change.propose("legacy.txt", "a test", find="= 1", replace="= 2")
        self.assertIn("not valid UTF-8", str(caught.exception))
        self.assertEqual(self.raw("legacy.txt"), b"caf\xe9 = 1\n")

    def test_a_new_file_is_still_a_proposal(self):
        proposal = self_change.propose("brand_new.py", "a test", new_text="x = 1\n")
        self.assertEqual(proposal["before"], 0)


if __name__ == "__main__":
    unittest.main()
