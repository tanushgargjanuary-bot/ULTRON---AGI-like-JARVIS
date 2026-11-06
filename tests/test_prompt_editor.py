"""The system prompt as a thing the owner can read, and instruct the assistant to edit.

Three properties matter, and each one is a class below.

    readable     what the model is given can be shown, in full, to the person who
                 instructs it;
    deliberate   no change happens on one instruction — a proposal is staged, and it
                 applies only after two confirmations made in two different places;
    reversible   every applied change keeps the text it replaced, and going back is
                 a change like any other.

Everything runs against a copy of the template in a temporary folder. A test that
edited the real `core/prompt.txt` would leave the repository changed by a test run,
which is the one thing this project has never allowed.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from actions import prompt_editor
from core import failures, policy, prompt_store


class WithATemporaryPrompt(unittest.TestCase):
    """Every test gets its own prompt file and its own history folder."""

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.prompt = self.folder / "prompt.txt"
        shutil.copyfile(ROOT / "core" / "prompt.txt", self.prompt)
        self._real_prompt = prompt_store.PROMPT_PATH
        prompt_store.PROMPT_PATH = self.prompt
        prompt_store.set_store(self.folder / "versions")
        failures.clear()

    def tearDown(self):
        prompt_store.PROMPT_PATH = self._real_prompt
        prompt_store.set_store(None)
        shutil.rmtree(self.folder, ignore_errors=True)

    def call(self, **parameters) -> str:
        return prompt_editor.system_prompt(parameters)

    # A passage that is in the shipped prompt, and the change the test wants to see
    # applied. The first version of this test used "Be concise.", which the prompt
    # does not contain — the stage was refused, correctly, and eleven tests failed
    # because of a fixture rather than a fault.
    FIND = "Brevity is the default."
    REPLACE = "Brevity is the default, and one line is usually enough."

    def stage_small_change(self, reason="be shorter"):
        return self.call(action="stage", reason=reason,
                         find=self.FIND, replace=self.REPLACE)


class TheOwnerCanSeeIt(WithATemporaryPrompt):
    def test_show_returns_the_whole_prompt_and_where_it_lives(self):
        shown = self.call(action="show")
        self.assertIn("--- the system prompt ---", shown)
        self.assertIn("--- end of the system prompt ---", shown)
        self.assertIn("prompt.txt", shown)
        self.assertIn(f"{prompt_store.size()} characters", shown)

    def test_the_prompt_it_shows_is_the_prompt_the_model_gets(self):
        template = prompt_store.read()
        shown = self.call(action="show")
        self.assertLess(len(shown), prompt_store.size() + 1_000,
                         "the whole prompt should fit in one answer")
        # Distinctive passages from across the file, with the placeholders filled.
        for passage in ("[SELF]", "[WHAT YOU CANNOT DO]", "[UNTRUSTED CONTENT]",
                        "Brevity is the default.", "You are Ultron"):
            self.assertIn(passage, shown)
        for token in ("{limits}", "{capabilities}", "{platform}"):
            self.assertNotIn(token, shown, "a placeholder should be filled in a preview")

    def test_the_raw_template_is_available_unchanged(self):
        self.assertEqual(self.call(action="template"), prompt_store.read())

    def test_it_never_pretends_a_staged_change_is_live(self):
        said = self.stage_small_change()
        self.assertIn("Staged, not applied", said)
        self.assertEqual(prompt_store.read(), self.prompt.read_text(encoding="utf-8"))
        self.assertNotIn(self.REPLACE, prompt_store.read())


class AChangeNeedsTwoPeople(WithATemporaryPrompt):
    def proposal_id(self) -> str:
        self.stage_small_change()
        return prompt_store.pending()[0].id

    def test_one_confirmation_changes_nothing(self):
        proposal = self.proposal_id()
        said = self.call(action="confirm", proposal=proposal, channel="voice")
        self.assertIn("Nothing has changed yet", said)
        self.assertEqual(prompt_store.read(), self.prompt.read_text(encoding="utf-8"))

    def test_the_same_place_twice_is_not_two_confirmations(self):
        proposal = self.proposal_id()
        self.call(action="confirm", proposal=proposal, channel="voice")
        said = self.call(action="confirm", proposal=proposal, channel="voice")
        self.assertIn("somewhere else", said)
        self.assertEqual(len(prompt_store.pending()), 1)

    def test_two_different_places_apply_it(self):
        proposal = self.proposal_id()
        self.call(action="confirm", proposal=proposal, channel="voice")
        said = self.call(action="confirm", proposal=proposal, channel="panel")
        self.assertIn("Applied", said)
        self.assertIn(self.REPLACE, prompt_store.read())
        self.assertEqual(prompt_store.pending(), [])

    def test_an_applied_change_keeps_what_it_replaced(self):
        before = prompt_store.read()
        proposal = self.proposal_id()
        self.call(action="confirm", proposal=proposal, channel="voice")
        self.call(action="confirm", proposal=proposal, channel="panel")
        kept = prompt_store.versions()
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].read_text(encoding="utf-8"), before)

    def test_the_changelog_names_who_confirmed_and_why(self):
        proposal = self.proposal_id()
        self.call(action="confirm", proposal=proposal, channel="voice")
        self.call(action="confirm", proposal=proposal, channel="panel")
        row = prompt_store.history()[0]
        self.assertEqual(row["reason"], "be shorter")
        self.assertEqual(sorted(row["confirmations"]), ["panel", "voice"])

    def test_a_rejected_proposal_leaves_nothing_behind(self):
        proposal = self.proposal_id()
        said = self.call(action="reject", proposal=proposal)
        self.assertIn("Nothing changed", said)
        self.assertEqual(prompt_store.pending(), [])

    def test_an_unknown_proposal_is_answered_not_raised(self):
        said = self.call(action="confirm", proposal="p000000000000", channel="voice")
        self.assertIn("no proposal", said.lower())

    def test_staging_without_a_reason_is_refused(self):
        said = self.call(action="stage", find=self.FIND, replace="Brevity.")
        self.assertIn("without a reason", said)
        self.assertEqual(prompt_store.pending(), [])


class ABrokenPromptIsRefused(WithATemporaryPrompt):
    def test_removing_a_placeholder_is_refused_by_the_store(self):
        broken = prompt_store.read().replace("{limits}", "nothing")
        ok, problems = prompt_store.validate(broken)
        self.assertFalse(ok)
        self.assertTrue(any("{limits}" in problem for problem in problems))

    def test_removing_a_placeholder_is_refused_by_the_tool_in_a_sentence(self):
        said = self.call(action="stage", reason="simplify",
                         find="{limits}", replace="")
        self.assertIn("{limits}", said)
        self.assertEqual(prompt_store.pending(), [])

    def test_an_empty_prompt_is_refused(self):
        ok, problems = prompt_store.validate("   ")
        self.assertFalse(ok)
        self.assertIn("empty", problems[0])

    def test_a_prompt_over_the_budget_is_refused(self):
        ok, problems = prompt_store.validate(prompt_store.read() + "x" * 20_000)
        self.assertFalse(ok)
        self.assertTrue(any("ceiling" in problem for problem in problems))

    def test_a_prompt_too_short_to_be_an_instruction_is_refused(self):
        ok, problems = prompt_store.validate("You are Ultron. {limits}{capabilities}"
                                             "{platform}{assistant_name}")
        self.assertFalse(ok)

    def test_the_shipped_prompt_passes_every_rule(self):
        ok, problems = prompt_store.validate(
            (ROOT / "core" / "prompt.txt").read_text(encoding="utf-8"))
        self.assertTrue(ok, problems)

    def test_an_ambiguous_find_is_refused_rather_than_guessed(self):
        said = self.call(action="stage", reason="tidy", find="the", replace="a")
        self.assertIn("more specific", said)


class GoingBack(WithATemporaryPrompt):
    def apply_one_change(self):
        self.stage_small_change()
        proposal = prompt_store.pending()[0].id
        self.call(action="confirm", proposal=proposal, channel="voice")
        self.call(action="confirm", proposal=proposal, channel="panel")
        return prompt_store.versions()[0].name

    def test_revert_is_staged_like_any_other_change(self):
        original = prompt_store.read()
        version = self.apply_one_change()
        self.assertNotEqual(prompt_store.read(), original)
        said = self.call(action="revert", version=version)
        self.assertIn("Nothing has changed yet", said)

    def test_revert_restores_the_earlier_text_after_two_confirmations(self):
        original = prompt_store.read()
        version = self.apply_one_change()
        self.call(action="revert", version=version)
        proposal = prompt_store.pending()[0].id
        self.call(action="confirm", proposal=proposal, channel="voice")
        self.call(action="confirm", proposal=proposal, channel="panel")
        self.assertEqual(prompt_store.read(), original)

    def test_asking_for_versions_lists_them(self):
        version = self.apply_one_change()
        self.assertIn(version, self.call(action="versions"))


class TheToolIsSafeByConstruction(WithATemporaryPrompt):
    def test_it_is_registered_with_the_gate_it_carries(self):
        tool = prompt_editor.TOOL
        self.assertEqual(tool["name"], "system_prompt")
        self.assertIn("stage", tool["description"])
        verdict = policy.classify("system_prompt", {"action": "show"})
        self.assertTrue(verdict.allow)
        self.assertIn("own per-step gate", verdict.reason)

    def test_an_unknown_action_lists_what_it_can_do(self):
        said = self.call(action="destroy-everything")
        self.assertIn("I do not know the action", said)
        self.assertIn("show", said)

    def test_it_cannot_be_pointed_at_another_file(self):
        # There is no path parameter, by design: the only file it can write is the
        # prompt, and the only folder it can grow is the version history.
        self.assertNotIn("path", prompt_editor.TOOL["parameters"]["properties"])
        self.assertNotIn("file", prompt_editor.TOOL["parameters"]["properties"])

    def test_a_failure_is_recorded_rather_than_swallowed(self):
        # An unknown version raises KeyError inside the tool; the tool answers with a
        # sentence and nothing is written.
        said = self.call(action="revert", version="v9999-nothing.txt")
        self.assertIn("no proposal or version", said)

    def test_the_file_is_replaced_in_one_step(self):
        self.stage_small_change()
        proposal = prompt_store.pending()[0].id
        self.call(action="confirm", proposal=proposal, channel="voice")
        self.call(action="confirm", proposal=proposal, channel="panel")
        self.assertFalse((self.prompt.parent / "prompt.txt.new").exists(),
                         "a half-written prompt would be a broken assistant")


if __name__ == "__main__":
    unittest.main()
