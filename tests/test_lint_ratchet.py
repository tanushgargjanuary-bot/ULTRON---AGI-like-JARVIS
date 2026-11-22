"""`scripts/lint_ratchet.py`: the fast gate's lint step, compared with the base instead of with zero.

The gate ran `ruff check --select E4,E7,E9,F` on every file a change touched and failed on every
finding in it. `ui.py` has 97 findings and `actions/file_processor.py` 25 (cf02c0e plus this
branch), so a one-line change to either could not pass without cleaning the whole file.
The ratchet fails a change only for findings it ADDS, and it must never pass because it could not
run. Both halves are tested here: the comparison, and the exit status when ruff or git is missing.

The tests that call the real ruff skip on a machine without it (the lean CI install has none; the
fast-checks job, which installs it, runs the script itself on every push).
"""

from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import lint_ratchet  # noqa: E402


def have_ruff() -> bool:
    try:
        return subprocess.run([sys.executable, "-m", "ruff", "--version"],
                              capture_output=True, check=False).returncode == 0
    except OSError:
        return False


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.email=t@example.test", "-c", "user.name=t", *args],
                   cwd=root, check=True, capture_output=True)


def ratchet(root: Path, *argv: str):
    """Run main() against `root`; -> (exit status, printed text)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        status = lint_ratchet.main(list(argv), root=root)
    return status, out.getvalue()


class WithARepo(unittest.TestCase):
    """A throwaway git repository with one commit holding `FILES`."""

    FILES: dict[str, str] = {}

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        git(self.root, "init", "-q")
        self.write(self.FILES)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "base")

    def write(self, files: dict[str, str]) -> None:
        for name, text in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")


class ParsingGitsOutput(unittest.TestCase):
    def test_modified_added_and_renamed(self):
        raw = b"M\0a.py\0A\0b c.py\0R095\0old.py\0new.py\0"
        self.assertEqual(lint_ratchet.parse_name_status(raw), [
            ("M", "a.py", "a.py"), ("A", "b c.py", "b c.py"), ("R", "old.py", "new.py")])

    def test_unicode_names_survive(self):
        raw = "M\0dossier/résumé.py\0".encode("utf-8")
        self.assertEqual(lint_ratchet.parse_name_status(raw), [
            ("M", "dossier/résumé.py", "dossier/résumé.py")])

    def test_an_empty_change_list_is_empty(self):
        self.assertEqual(lint_ratchet.parse_name_status(b""), [])

    def test_a_truncated_list_is_an_error_not_a_pass(self):
        with self.assertRaises(lint_ratchet.CannotRun):
            lint_ratchet.parse_name_status(b"R100\0only-one-name.py\0")


class TheComparison(unittest.TestCase):
    @staticmethod
    def found(**rules):
        return {code: [(row, f"{code} message") for row in rows] for code, rows in rules.items()}

    def test_the_same_findings_are_not_a_regression(self):
        counts = {"ui.py": self.found(E702=[1, 2, 3])}
        self.assertEqual(lint_ratchet.regressions(counts, counts), [])

    def test_fewer_findings_are_welcome(self):
        before = {"ui.py": self.found(E702=[1, 2, 3])}
        now = {"ui.py": self.found(E702=[1])}
        self.assertEqual(lint_ratchet.regressions(before, now), [])

    def test_one_more_of_a_rule_is_reported_with_the_numbers(self):
        before = {"ui.py": self.found(E702=[1, 2])}
        now = {"ui.py": self.found(E702=[1, 2, 40])}
        lines = lint_ratchet.regressions(before, now)
        self.assertEqual(len(lines), 1)
        self.assertIn("ui.py: E702 3 now, 2 at the base", lines[0])
        self.assertIn("40", lines[0])

    def test_one_finding_swapped_for_another_of_the_same_rule_is_not_seen(self):
        # The limit the module docstring names: a count per file and rule is not a match of
        # individual findings. The old E402 at line 3 is gone; a new one stands at line 9.
        before = {"ui.py": self.found(E402=[3])}
        now = {"ui.py": self.found(E402=[9])}
        self.assertEqual(lint_ratchet.regressions(before, now), [])

    def test_a_swap_across_two_different_rules_is_seen(self):
        before = {"ui.py": self.found(E402=[3])}
        now = {"ui.py": self.found(F401=[9])}
        self.assertEqual(len(lint_ratchet.regressions(before, now)), 1)

    def test_a_rule_the_file_never_had_is_a_regression_even_if_others_dropped(self):
        before = {"ui.py": self.found(E702=[1, 2, 3, 4])}
        now = {"ui.py": self.found(E702=[1], F401=[9])}
        lines = lint_ratchet.regressions(before, now)
        self.assertEqual(len(lines), 1)
        self.assertIn("F401", lines[0])

    def test_a_new_file_starts_at_zero(self):
        lines = lint_ratchet.regressions({}, {"new.py": self.found(F401=[1])})
        self.assertEqual(len(lines), 1)
        self.assertIn("new.py: F401 1 now, 0 at the base", lines[0])

    def test_a_clean_new_file_is_fine(self):
        self.assertEqual(lint_ratchet.regressions({}, {}), [])

    def test_a_long_list_of_lines_is_cut_short(self):
        lines = lint_ratchet.regressions({}, {"a.py": self.found(E701=list(range(1, 20)))})
        self.assertIn("...", lines[0])


class WhatItRefusesToDo(WithARepo):
    FILES = {"a.py": "x = 1\n"}

    def test_it_never_passes_when_ruff_is_not_installed(self):
        # `python -m ruff` with no ruff exits 1 with an empty stdout, which looks like
        # "no findings" to anyone who only reads the status.
        missing = subprocess.CompletedProcess([], 1, b"", b"No module named ruff")
        with mock.patch.object(lint_ratchet, "_run", return_value=missing):
            status, said = ratchet(self.root, "--base", "HEAD")
        self.assertEqual(status, 2)
        self.assertIn("NOT passed", said)
        self.assertIn("ruff is not installed", said)

    def test_silence_from_ruff_is_an_error_not_zero_findings(self):
        self.write({"a.py": "import os\n"})
        silent = subprocess.CompletedProcess([], 1, b"", b"boom")
        with mock.patch.object(lint_ratchet, "ensure_ruff"), \
                mock.patch.object(lint_ratchet, "_run", side_effect=[
                    subprocess.CompletedProcess([], 0, b"M\0a.py\0", b""),     # git diff
                    subprocess.CompletedProcess([], 0, b"", b""),              # git ls-files
                    silent]):                                                   # ruff
            status, said = ratchet(self.root, "--base", "HEAD")
        self.assertEqual(status, 2)
        self.assertIn("printed nothing", said)

    def test_output_that_is_not_json_is_an_error(self):
        garbage = subprocess.CompletedProcess([], 1, b"not json at all", b"")
        with mock.patch.object(lint_ratchet, "_run", return_value=garbage):
            with self.assertRaises(lint_ratchet.CannotRun):
                lint_ratchet.ruff_findings(["a.py"], "F", self.root)

    def test_a_ruff_crash_is_an_error(self):
        crashed = subprocess.CompletedProcess([], 2, b"", b"error: unknown option")
        with mock.patch.object(lint_ratchet, "_run", return_value=crashed):
            with self.assertRaises(lint_ratchet.CannotRun):
                lint_ratchet.ruff_findings(["a.py"], "F", self.root)

    def test_json_that_is_not_a_list_is_an_error(self):
        wrong = subprocess.CompletedProcess([], 0, b'{"a": 1}', b"")
        with mock.patch.object(lint_ratchet, "_run", return_value=wrong):
            with self.assertRaises(lint_ratchet.CannotRun):
                lint_ratchet.ruff_findings(["a.py"], "F", self.root)

    def test_a_base_that_does_not_exist_is_an_error(self):
        with mock.patch.object(lint_ratchet, "ensure_ruff"):
            status, said = ratchet(self.root, "--base", "no-such-commit")
        self.assertEqual(status, 2)
        self.assertIn("NOT passed", said)

    def test_no_changed_python_files_is_a_pass_and_says_so(self):
        with mock.patch.object(lint_ratchet, "ensure_ruff"):
            status, said = ratchet(self.root, "--base", "HEAD")
        self.assertEqual(status, 0)
        self.assertIn("no changed Python files", said)


class TheBaseIsLintedUnderTheSameConfiguration(WithARepo):
    FILES = {"a.py": "x = 1\n", "ruff.toml": '[lint.per-file-ignores]\n"a.py" = ["F401"]\n'}

    def test_the_scratch_copy_carries_the_current_ruff_toml(self):
        self.write({"a.py": "x = 2\n"})
        seen = {}

        def fake(files, select, cwd):
            seen["config"] = (Path(cwd) / "ruff.toml").is_file()
            seen["files"] = [str(f) for f in files]
            return []

        rows = [("M", "a.py", "a.py")]
        with mock.patch.object(lint_ratchet, "ruff_findings", fake):
            lint_ratchet._base_counts("HEAD", rows, "F", self.root)
        self.assertTrue(seen["config"], "a per-file ignore must apply to the base as it does to the head")
        self.assertEqual(seen["files"], ["a.py"])

    def test_an_added_file_is_not_looked_up_at_the_base(self):
        seen = {}

        def fake(files, select, cwd):
            seen["files"] = list(files)
            return []

        with mock.patch.object(lint_ratchet, "ruff_findings", fake):
            lint_ratchet._base_counts("HEAD", [("A", "new.py", "new.py")], "F", self.root)
        self.assertEqual(seen["files"], [])


@unittest.skipUnless(have_ruff(), "ruff is not installed here; the fast-checks job runs the script itself")
class WithTheRealRuff(WithARepo):
    FILES = {
        "legacy.py": "x = 1\nif x: print(x)\n",             # one E701 that was already there
        "clean.py": "VALUE = 1\n",
        "ui.py": "".join(f"a{n} = {n}; b{n} = {n}\n" for n in range(5)),     # five E702
    }

    def test_touching_a_file_with_old_findings_is_fine(self):
        self.write({"legacy.py": "x = 2\nif x: print(x)\n"})
        status, said = ratchet(self.root, "--base", "HEAD")
        self.assertEqual(status, 0, said)
        self.assertIn("already there", said)

    def test_adding_a_finding_to_a_file_that_has_old_ones_fails_and_names_it(self):
        self.write({"legacy.py": "x = 1\nif x: print(x)\nif x: print(x + 1)\n"})
        status, said = ratchet(self.root, "--base", "HEAD")
        self.assertEqual(status, 1, said)
        self.assertIn("legacy.py: E701 2 now, 1 at the base", said)
        self.assertIn("lines 2, 3", said)

    def test_fixing_some_old_findings_while_touching_a_file_passes(self):
        self.write({"ui.py": "".join(f"a{n} = {n}\nb{n} = {n}\n" for n in range(3))
                    + "".join(f"c{n} = {n}; d{n} = {n}\n" for n in range(2))})
        status, said = ratchet(self.root, "--base", "HEAD")
        self.assertEqual(status, 0, said)

    def test_fixing_one_finding_and_adding_another_of_the_same_rule_passes(self):
        # legacy.py has one E701 (line 2). The change fixes it and adds a different one at line 5.
        # The count per file and rule is 1 before and 1 after, so the ratchet cannot tell, and
        # its docstring says so. If this ever fails, the docstring has to change with it.
        self.write({"legacy.py": "x = 1\nif x:\n    print(x)\ny = 2\nif y: print(y)\n"})
        status, said = ratchet(self.root, "--base", "HEAD")
        self.assertEqual(status, 0, said)

    def test_adding_one_without_fixing_one_still_fails(self):
        self.write({"legacy.py": "x = 1\nif x: print(x)\ny = 2\nif y: print(y)\n"})
        status, said = ratchet(self.root, "--base", "HEAD")
        self.assertEqual(status, 1, said)

    def test_a_new_clean_file_passes(self):
        self.write({"fresh.py": "VALUE = 2\n"})
        status, said = ratchet(self.root, "--base", "HEAD")
        self.assertEqual(status, 0, said)

    def test_a_new_file_with_a_finding_fails_even_though_nothing_is_committed(self):
        self.write({"fresh.py": "import os\n"})         # untracked
        status, said = ratchet(self.root, "--base", "HEAD")
        self.assertEqual(status, 1, said)
        self.assertIn("fresh.py: F401 1 now, 0 at the base", said)

    def test_a_rename_carries_its_old_findings_with_it(self):
        git(self.root, "mv", "legacy.py", "renamed.py")
        self.write({"renamed.py": "x = 2\nif x: print(x)\n"})
        git(self.root, "add", "-A")
        status, said = ratchet(self.root, "--base", "HEAD")
        self.assertEqual(status, 0, said)

    def test_a_new_kind_of_finding_fails_even_if_the_total_went_down(self):
        self.write({"ui.py": "import os\n"})
        status, said = ratchet(self.root, "--base", "HEAD")
        self.assertEqual(status, 1, said)
        self.assertIn("F401", said)

    def test_a_syntax_error_is_a_regression(self):
        self.write({"clean.py": "def broken(:\n"})
        status, said = ratchet(self.root, "--base", "HEAD")
        self.assertEqual(status, 1, said)

    def test_comparing_with_an_earlier_commit_sees_all_the_commits_since(self):
        self.write({"clean.py": "VALUE = 2\n"})
        git(self.root, "commit", "-q", "-am", "harmless")
        self.write({"clean.py": "import os\n"})
        git(self.root, "commit", "-q", "-am", "adds a finding")
        status, said = ratchet(self.root, "--base", "HEAD~2")
        self.assertEqual(status, 1, said)
        status, said = ratchet(self.root, "--base", "HEAD")
        self.assertEqual(status, 0, "against its own parent the tree is unchanged: " + said)


class TheDocstringTellsTheTruth(unittest.TestCase):
    """It once promised that a new finding always fails. The swap tests above show otherwise."""

    def words(self) -> str:
        return " ".join(lint_ratchet.__doc__.split())

    def test_it_does_not_promise_that_every_new_finding_fails(self):
        for promise in ("fails exactly as it did before", "Nothing is excused",
                        "a change may not ADD findings"):
            self.assertNotIn(promise, self.words())

    def test_it_says_it_counts_and_what_that_lets_through(self):
        for phrase in ("per file and per rule", "fixes one E402", "adds another E402", "passes"):
            self.assertIn(phrase, self.words())

    def test_the_decision_and_the_review_guide_carry_the_same_caveat(self):
        for name in ("DECISIONS.md", "docs/CODE_REVIEW.md", "docs/TEST_AUTOMATION.md"):
            with self.subTest(file=name):
                text = " ".join((ROOT / name).read_text(encoding="utf-8").split())
                self.assertIn("fixes one finding and adds another of the same rule", text)


class TheGateUsesIt(unittest.TestCase):
    def test_the_workflow_runs_the_ratchet_not_ruff_on_whole_files(self):
        workflow = (ROOT / ".github" / "workflows" / "fast-checks.yml").read_text(encoding="utf-8")
        self.assertIn('python scripts/lint_ratchet.py --base "$BASE_SHA"', workflow)
        self.assertNotIn('ruff check --select E4,E7,E9,F -- "${PY_FILES[@]}"', workflow)

    def test_the_rule_set_is_the_one_the_documents_name(self):
        self.assertEqual(lint_ratchet.DEFAULT_SELECT, "E4,E7,E9,F")
        for name in ("ruff.toml", "docs/TEST_AUTOMATION.md"):
            with self.subTest(file=name):
                self.assertIn("E4,E7,E9,F", (ROOT / name).read_text(encoding="utf-8"))

    def test_the_documents_describe_the_ratchet_not_the_old_rule(self):
        guide = (ROOT / "docs" / "TEST_AUTOMATION.md").read_text(encoding="utf-8")
        self.assertIn("lint_ratchet", guide)
        self.assertNotIn("Runs Ruff on changed Python files. It fails on selected", guide)
        config = (ROOT / "ruff.toml").read_text(encoding="utf-8")
        self.assertIn("lint_ratchet", config)


if __name__ == "__main__":
    unittest.main()
