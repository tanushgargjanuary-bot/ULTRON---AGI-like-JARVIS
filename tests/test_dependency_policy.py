"""Dependencies and CI: the rules the requirements file states about itself, enforced.

`requirements.txt` says "the upper bound stops the next MAJOR release of a dependency from
breaking every fresh clone on the day it ships" — and then listed 23 packages with no bound
at all. The same pass fixed the neighbours of that fault:

* the PDF fallback reader was PyPDF2, unreleased since 2022 and unpatched against what pypdf
  has fixed since; `file_processor` now prefers pypdf, and stops reading pages once it has the
  characters it will use (it parsed a 4,000-page PDF whole to keep the first 50,000);
* the web app had no lock file and CI ran `npm install`, so one commit could build green on
  one day and red the next (the web app was removed on 2026-11-26, and its three tests with it);
* CI linted with `ruff>=0.14,<1` while the development pin is `ruff==0.17.3`;
* every action was referenced by a movable tag, and the reviewdog binary by `latest`.

Found 2026-11-25, on Dependabot's #34: CI installs a short list written into `verify.yml` and never reads
`requirements.txt`, so a change to that file was never installed by anything and every check stayed green. On
Python 3.11, which the readme supports, #34's file could not be installed at all (`numpy>=2.5.5` needs Python
3.12), and it moved the PyQt6 ceiling that is below Qt 6.12 on purpose. `install-check.yml` installs the real
file; Dependabot is told to edit a requirement only when its range is too narrow, and to leave Qt alone.
"""

from __future__ import annotations

import re
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

# No upper bound, each for a stated reason that is also written in requirements.txt.
UNBOUNDED_ON_PURPOSE = {
    "yt-dlp": "YouTube changes without notice and yt-dlp answers with a release",
    "pycaw": "versioned by date (20260927): there is no major release to bound",
    "pywin32": "versioned by build number (312): there is no major release to bound",
}


def requirement_lines(name: str):
    for number, text in enumerate((ROOT / name).read_text(encoding="utf-8").splitlines(), 1):
        line = text.split("#")[0].strip()
        if line:
            yield number, line


def package_name(line: str) -> str:
    return re.split(r"[\s<>=!~;\[]", line, maxsplit=1)[0].lower()


class EveryRequirementIsBounded(unittest.TestCase):
    FILES = ("requirements.txt", "requirements-dev.txt", "requirements-ocr.txt",
             "requirements-demo.txt")

    def test_each_requirement_has_an_upper_bound_or_a_stated_reason(self):
        unbounded = []
        for name in self.FILES:
            for number, line in requirement_lines(name):
                spec = line.split(";")[0]
                if re.search(r"<|==|~=", spec):
                    continue
                if package_name(line) in UNBOUNDED_ON_PURPOSE:
                    continue
                unbounded.append(f"{name}:{number}: {line}")
        self.assertEqual(unbounded, [], "a major release will install itself on a fresh clone")

    def test_the_exceptions_are_still_in_the_file_and_still_explained_there(self):
        text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        listed = {package_name(line) for _n, line in requirement_lines("requirements.txt")}
        for package in UNBOUNDED_ON_PURPOSE:
            with self.subTest(package=package):
                self.assertIn(package, listed, "no longer listed: remove it from the exceptions")
        self.assertIn("Deliberately UNBOUNDED", text)
        self.assertIn("date-versioned", text)
        self.assertIn("build-numbered", text)

    # The newest release of each of these on PyPI on 2026-11-20, when the bounds were set.
    # The test below is deterministic on purpose: comparing against whatever happens to be
    # installed made it fail on a machine whose packages had simply moved on.
    LATEST_SEEN = {
        "pyautogui": "0.9.54", "pyperclip": "1.11.0", "send2trash": "2.2.0",
        "python-pptx": "1.0.2", "google-api-python-client": "2.202.0",
        "google-auth-oauthlib": "1.5.0", "tinytuya": "1.21.1", "paho-mqtt": "2.2.0",
        "openpyxl": "3.1.5", "youtube-transcript-api": "1.2.5", "pygetwindow": "0.0.9",
        "comtypes": "1.5.0", "win10toast": "0.9", "wmi": "1.5.1", "uiautomation": "2.0.29",
        "pywinauto": "0.6.9", "pdfplumber": "0.11.10", "pypdf": "7.1.1",
        "python-docx": "1.2.0", "pynvml": "13.0.1",
    }

    @staticmethod
    def as_tuple(version: str):
        return tuple(int(part) for part in version.split("."))

    def test_the_bounds_admit_the_release_that_was_current_when_they_were_set(self):
        # A bound written wrongly (<1 for a package already at 2.x) makes the file
        # uninstallable: pip would resolve to a release from years ago, or fail.
        problems = []
        seen = set()
        for _n, line in requirement_lines("requirements.txt"):
            name = package_name(line)
            if name not in self.LATEST_SEEN:
                continue
            seen.add(name)
            latest = self.as_tuple(self.LATEST_SEEN[name])
            spec = line.split(";")[0]
            upper = re.search(r"<\s*([\d.]+)", spec)
            lower = re.search(r">=\s*([\d.]+)", spec)
            if upper and not latest < self.as_tuple(upper.group(1)):
                problems.append(f"{name}: {self.LATEST_SEEN[name]} is not below {upper.group(1)}")
            if lower and not latest >= self.as_tuple(lower.group(1)):
                problems.append(f"{name}: {self.LATEST_SEEN[name]} is below the floor {lower.group(1)}")
        self.assertEqual(problems, [])
        self.assertEqual(sorted(set(self.LATEST_SEEN) - seen), [],
                         "listed here but no longer in requirements.txt: drop it from this table")

    def test_pypdf_replaces_pypdf2_and_the_floor_is_the_patched_release(self):
        names = {package_name(line) for _n, line in requirement_lines("requirements.txt")}
        self.assertIn("pypdf", names)
        self.assertNotIn("pypdf2", names)
        line = next(line for _n, line in requirement_lines("requirements.txt")
                    if package_name(line) == "pypdf")
        floor = re.search(r">=\s*([\d.]+)", line)
        self.assertIsNotNone(floor)
        self.assertGreaterEqual(tuple(int(x) for x in floor.group(1).split(".")), (6, 21, 4))


class PdfFallbackReader(unittest.TestCase):
    """`actions.file_processor._extract_pdf_text`, with fake readers."""

    def setUp(self):
        from actions import file_processor
        self.module = file_processor
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.pdf = Path(folder.name) / "doc.pdf"
        self.pdf.write_bytes(b"%PDF-1.4 not a real file; the readers here are fakes")

    @staticmethod
    def reader_module(name, pages_read, text="x" * 1000, count=10_000):
        class Page:
            def __init__(self, index):
                self.index = index

            def extract_text(self):
                pages_read.append(self.index)
                return text

        class PdfReader:
            def __init__(self, handle):
                self.pages = (Page(i) for i in range(count))

        module = types.ModuleType(name)
        module.PdfReader = PdfReader
        return module

    def extract(self, **modules):
        """Run the extractor with `pdfplumber` absent and the given readers present."""
        absent = {name: None for name in ("pdfplumber", "pypdf", "PyPDF2") if name not in modules}
        with mock.patch.dict(sys.modules, {**absent, **modules}):
            text = self.module._extract_pdf_text(self.pdf)
        return text, text

    def test_pypdf_is_preferred_over_pypdf2(self):
        from_new, from_old = [], []
        result, text = self.extract(
            pypdf=self.reader_module("pypdf", from_new, text="new reader"),
            PyPDF2=self.reader_module("PyPDF2", from_old, text="old reader"))
        self.assertIn("new reader", text)
        self.assertEqual(from_old, [], "PyPDF2 is only a fallback")

    def test_pypdf2_is_used_when_it_is_all_there_is(self):
        pages = []
        _result, text = self.extract(PyPDF2=self.reader_module("PyPDF2", pages, text="old reader"))
        self.assertIn("old reader", text)

    def test_no_reader_at_all_says_so_instead_of_raising(self):
        _result, text = self.extract()
        self.assertEqual(text, "")

    def test_it_stops_reading_pages_once_it_has_enough_characters(self):
        pages = []
        _result, text = self.extract(pypdf=self.reader_module("pypdf", pages))
        self.assertLessEqual(len(text), 50_000)
        # 1,001 characters a page -> 50 pages is enough; the rest are never parsed.
        self.assertLess(len(pages), 60, f"{len(pages)} of 10000 pages were parsed")
        self.assertGreaterEqual(len(pages), 49)

    def test_a_page_with_no_text_is_not_a_crash(self):
        pages = []
        _result, text = self.extract(
            pypdf=self.reader_module("pypdf", pages, text=None, count=3))
        self.assertEqual(text.strip(), "")
        self.assertEqual(len(pages), 3)


class WorkflowsAreNotMovable(unittest.TestCase):
    def workflow_texts(self):
        return {path.name: path.read_text(encoding="utf-8") for path in sorted(WORKFLOWS.glob("*.yml"))}

    def test_every_action_is_pinned_to_a_commit(self):
        loose = []
        for name, text in self.workflow_texts().items():
            for number, line in enumerate(text.splitlines(), 1):
                found = re.match(r"\s*(?:-\s*)?uses:\s*(\S+)", line)
                if not found or found.group(1).startswith("./"):
                    continue
                reference = found.group(1)
                if not re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", reference):
                    loose.append(f"{name}:{number}: {reference}")
        self.assertEqual(loose, [], "a tag can be moved to different code; a commit cannot")

    def test_a_pinned_action_says_which_release_it_is(self):
        for name, text in self.workflow_texts().items():
            for number, line in enumerate(text.splitlines(), 1):
                if re.search(r"uses:\s*\S+@[0-9a-f]{40}", line):
                    with self.subTest(where=f"{name}:{number}"):
                        self.assertRegex(line, r"#\s*v\d")

    def test_the_review_tool_is_not_pinned_to_latest(self):
        for name, text in self.workflow_texts().items():
            with self.subTest(workflow=name):
                self.assertNotRegex(text, r"_version:\s*latest")

    def test_ruff_comes_from_the_development_pin_everywhere(self):
        pin = next(line for _n, line in requirement_lines("requirements-dev.txt")
                   if package_name(line) == "ruff")
        self.assertRegex(pin, r"^ruff==\d")
        for name in ("fast-checks.yml", "reviewdog.yml", "verify.yml"):
            text = (WORKFLOWS / name).read_text(encoding="utf-8")
            with self.subTest(workflow=name):
                self.assertNotRegex(text, r"ruff\s*>=")
                self.assertIn("grep -E '^ruff==' requirements-dev.txt", text)

    def test_dependabot_keeps_the_pins_moving(self):
        text = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
        for ecosystem in ("github-actions", "pip"):
            with self.subTest(ecosystem=ecosystem):
                self.assertIn(f'package-ecosystem: "{ecosystem}"', text)
        self.assertEqual(len(re.findall(r"open-pull-requests-limit:\s*\d", text)), 2,
                         "an unbounded stream of update PRs is its own problem")

    def test_dependabot_only_watches_places_that_exist(self):
        # The web client went with its npm entry. An entry left behind makes Dependabot report an error on every
        # run, and nothing else in this suite would notice.
        text = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
        found = re.findall(r'(?m)^    directory:\s*"([^"]+)"', text)
        self.assertTrue(found, "no directory was read: the pattern no longer matches the file")
        for directory in found:
            with self.subTest(directory=directory):
                self.assertTrue((ROOT / directory.lstrip("/")).is_dir())

    def test_dependabot_opens_one_grouped_pull_request_per_ecosystem(self):
        """Its first run opened ten pull requests at once, a branch each, and none was read.

        The file said "one pull request per ecosystem at a time" while allowing 2, 3 and 3,
        and Dependabot opened 4, 4 and 2: the limit alone did not hold. A group is one pull
        request, so every ecosystem gets one group that takes every package, and the limit
        stays at 1 as a second guard.
        """
        text = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
        entries = re.split(r"(?m)^  - package-ecosystem:", text)[1:]
        ecosystems = sorted(entry.splitlines()[0].strip().strip('"') for entry in entries)
        self.assertEqual(ecosystems, ["github-actions", "pip"],
                         "an ecosystem is added or dropped on purpose, and this list says so")
        for entry in entries:
            ecosystem = entry.splitlines()[0].strip()
            with self.subTest(ecosystem=ecosystem):
                self.assertRegex(entry, r"(?m)^    open-pull-requests-limit:\s*1\s*$")
                self.assertRegex(
                    entry,
                    r'(?m)^    groups:\s*\n      [\w-]+:\s*\n        patterns:\s*\["\*"\]\s*$',
                    f"{ecosystem}: one group that takes every package",
                )


def bootstrap_pythons() -> list[str]:
    """The Python versions the launcher accepts, read from scripts/bootstrap.py's own MIN_PY and MAX_PY."""
    text = (ROOT / "scripts" / "bootstrap.py").read_text(encoding="utf-8")
    low = re.search(r"(?m)^MIN_PY\s*=\s*\((\d+),\s*(\d+)\)", text)
    high = re.search(r"(?m)^MAX_PY\s*=\s*\((\d+),\s*(\d+)\)", text)
    if not (low and high):
        raise AssertionError("scripts/bootstrap.py no longer states MIN_PY and MAX_PY")
    return [f"{low.group(1)}.{minor}" for minor in range(int(low.group(2)), int(high.group(2)) + 1)]


def job_text(workflow: str, job: str) -> str:
    """The text of one job: from its `  name:` line to the next job or the end of the file."""
    found = re.search(rf"(?ms)^  {job}:\n(.*?)(?=^  [\w-]+:\n|\Z)", workflow)
    return found.group(1) if found else ""


class TheFreshInstallCheck(unittest.TestCase):
    """The workflow that installs requirements.txt, which nothing in CI did before.

    Two jobs. `install`: a clean Windows machine and each Python the launcher accepts, running the launcher's own
    scripts/bootstrap.py as run.bat does, then scripts/check_install.py, because the launcher lets an optional
    package fail and still exits 0. `suite`: Linux with every package installed, running the whole suite; the short
    list in verify.yml leaves out fastapi, so the phone dashboard's tests skip everywhere else.
    """

    WATCHED = ("requirements.txt", "requirements-dev.txt", "setup.py", "scripts/bootstrap.py",
               "scripts/check_install.py", "run.bat", "run.ps1", ".github/workflows/install-check.yml")
    REQUIRED_CHECKS = ("fast offline gate", "linux \u2014 suite and instruments",
                       "windows \u2014 the machine the claims are about")

    @classmethod
    def setUpClass(cls):
        path = WORKFLOWS / "install-check.yml"
        cls.text = path.read_text(encoding="utf-8") if path.is_file() else ""
        cls.install = job_text(cls.text, "install")
        cls.suite = job_text(cls.text, "suite")
        cls.triggers = cls.text.split("\npermissions:")[0]

    def event_block(self, event: str) -> str:
        found = re.search(rf"(?ms)^  {event}:\n(.*?)(?=^  \S|\Z)", self.triggers)
        return found.group(1) if found else ""

    def test_the_workflow_exists_with_both_jobs(self):
        self.assertTrue(self.text, ".github/workflows/install-check.yml is missing")
        self.assertTrue(self.install, "no `install` job")
        self.assertTrue(self.suite, "no `suite` job")

    def test_it_installs_the_real_file_the_way_run_bat_does(self):
        self.assertIn("python -m venv .venv", self.install)
        self.assertIn("scripts/bootstrap.py", self.install)
        self.assertNotRegex(self.install, r'pip install[^\n]*"[A-Za-z]',
                            "a hand-written package list is what verify.yml has, and what this must not")

    def test_it_runs_on_windows_for_every_python_the_launcher_accepts(self):
        self.assertIn("runs-on: windows-latest", self.install)
        listed = re.search(r"(?m)^\s+python:\s*\[(.*?)\]\s*$", self.install)
        self.assertTrue(listed, "no `python: [...]` matrix in the install job")
        self.assertEqual(re.findall(r'"([\d.]+)"', listed.group(1)), bootstrap_pythons(),
                         "the launcher accepts a different range now, or the matrix lost a version")

    def test_it_checks_that_everything_installed_and_not_only_that_the_app_starts(self):
        launcher = re.search(r"(?m)^\s+run:.*scripts/bootstrap\.py", self.install)
        checker = re.search(r"(?m)^\s+run:.*scripts/check_install\.py", self.install)
        self.assertTrue(launcher, "no step runs the launcher's setup")
        self.assertTrue(checker, "no step runs scripts/check_install.py")
        self.assertGreater(checker.start(), launcher.start(), "the check must come after the launcher's own setup")

    def test_it_runs_when_a_requirements_or_launcher_file_changes(self):
        for event in ("pull_request", "push"):
            block = self.event_block(event)
            for path in self.WATCHED:
                with self.subTest(event=event, path=path):
                    self.assertRegex(block, rf'(?m)^\s+-\s+"?{re.escape(path)}"?\s*$')

    def test_it_also_runs_every_month_and_by_hand(self):
        self.assertRegex(self.triggers, r'(?m)^\s+-\s+cron:\s+"\d+ \d+ \d+ \* \*"')
        self.assertRegex(self.triggers, r"(?m)^  workflow_dispatch:")

    def test_a_failed_install_keeps_its_log(self):
        self.assertRegex(self.install, r"(?s)if:\s*failure\(\).*?upload-artifact@[0-9a-f]{40}.*?setup-log\.txt")

    def test_every_job_has_a_time_limit(self):
        for name, job in (("install", self.install), ("suite", self.suite)):
            with self.subTest(job=name):
                self.assertRegex(job, r"(?m)^    timeout-minutes:\s*\d+\s*$")

    def test_it_only_reads_the_repository(self):
        self.assertRegex(self.text, r"(?m)^permissions:\n  contents: read\s*$")

    def test_a_commit_on_main_is_never_cancelled_by_the_next(self):
        self.assertIn("cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}", self.text)
        self.assertIn("github.ref == 'refs/heads/main' && github.sha || github.ref", self.text)

    def test_no_job_takes_the_name_of_a_required_check(self):
        for required in self.REQUIRED_CHECKS:
            with self.subTest(required=required):
                self.assertNotIn(required, self.text,
                                 "a job named like a required check could stand in for it, or block a merge")

    def test_the_suite_runs_with_every_package_installed(self):
        self.assertIn("runs-on: ubuntu-latest", self.suite)
        for needle in ("-r requirements.txt", "-r requirements-dev.txt", "unittest discover -s tests",
                       "libportaudio2", "libegl1"):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.suite)


class DependabotKeepsToThePins(unittest.TestCase):
    """Dependabot's default for an app raises every minimum to the newest release.

    That made #34: `numpy>=2.5.5` (numpy 2.5 needs Python 3.12, so Python 3.11 could not install the file), a PyQt6
    ceiling moved past the Qt release that crashes at launch, and nothing in CI installed any of it.
    `increase-if-necessary` leaves a requirement alone when its range already allows the new release.

    The first version of this file used `widen`, which suits ranges better and appears in GitHub's documentation.
    GitHub's own check of `dependabot.yml` refused it on the pull request ("did not match one of the following values:
    lockfile-only, auto, increase, increase-if-necessary"), and the test that asserted `widen` had passed, because a
    test that repeats its author's belief is not evidence. So the value is also held to the list GitHub gave.

    The same mistake a second time, found on Dependabot's first pull request under the file (#39, 2026-11-25). The Qt
    rule named `update-types` (minor and major) and a test asserted those words, so it was green. Dependabot raised the
    ceiling to `<6.13` anyway. Why is not known (its own log could not be read), but every requirement here is a range,
    and a rule on update types did not hold for one. The test that fails a pull request which moves the ceiling did
    hold, and #39 went red on that single test (none of the 2,966 others failed); it was the rule that did nothing.
    So the rule now names the versions to ignore, `>=6.12`, which is the ceiling. It does not need a current version.
    A bare rule ("ignore all updates") would ignore every version, security fixes included, and GitHub's documentation
    says `versions` applies to both kinds of update where `update-types` applies only to version updates: this one
    stops only what the ceiling forbids. The number is held to the ceiling, so lifting one means lifting the other,
    and no rule may rest on `update-types` for a requirement that is not an exact pin.
    """

    # What GitHub's validator accepts for a pip entry, as it printed them on 2026-11-25.
    ACCEPTED_FOR_PIP = ("lockfile-only", "auto", "increase", "increase-if-necessary")

    @classmethod
    def setUpClass(cls):
        text = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
        entries = re.split(r"(?m)^  - package-ecosystem:", text)[1:]
        cls.pip = next((e for e in entries if e.splitlines()[0].strip() == '"pip"'), "")

    @classmethod
    def ignore_rules(cls) -> dict[str, str]:
        """The pip entry's `ignore:` list as {dependency name: the lines written under its `dependency-name`}."""
        block = re.search(r"(?ms)^    ignore:[ \t]*\n(.*?)(?=^    \S|\Z)", cls.pip)
        rules: dict[str, str] = {}
        for item in re.split(r"(?m)^      - ", block.group(1) if block else "")[1:]:
            head, _, written = item.partition("\n")
            named = re.match(r'dependency-name:\s*"?([^"\s]+)"?\s*$', head)
            if named:
                rules[named.group(1)] = written
        return rules

    def test_a_requirement_is_edited_only_when_its_range_is_too_narrow(self):
        self.assertRegex(self.pip, r"(?m)^    versioning-strategy:\s*increase-if-necessary\s*$")

    def test_the_strategy_is_one_github_accepts_for_pip(self):
        found = re.search(r"(?m)^    versioning-strategy:\s*(\S+)\s*$", self.pip)
        self.assertTrue(found, "the pip entry has no versioning-strategy")
        self.assertIn(found.group(1), self.ACCEPTED_FOR_PIP,
                      "GitHub's own check of dependabot.yml refuses any other value for pip")

    def test_the_qt_ceiling_stays_below_the_release_that_crashes_and_dependabot_is_told(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        ceiling = re.search(r"(?m)^PyQt6[^\n#]*<\s*([\d.]+)", requirements)
        self.assertTrue(ceiling and ceiling.group(1) == "6.12", "the PyQt6 ceiling moved")
        self.assertIn("6.12.0", requirements, "requirements.txt no longer says why the ceiling is there")
        rule = self.ignore_rules().get("PyQt6")
        self.assertIsNotNone(rule, "no ignore rule names PyQt6")
        self.assertNotIn("update-types", rule,
                         "Dependabot raised this ceiling to <6.13 although minor and major were ignored (#39)")
        held = re.search(r'(?m)^\s*versions:\s*\[\s*"?>=\s*([\d.]+)"?\s*\]\s*$', rule)
        self.assertTrue(held, 'the rule must say `versions: [">=<the ceiling>"]`: a bare rule ignores every version, '
                              "and with it the security updates below the ceiling")
        self.assertEqual(held.group(1), ceiling.group(1), "the ignored versions and the ceiling must move together")
        self.assertIn("QAudioOutput", self.pip, "the ignore rule must carry its reason")

    def test_no_ignore_rule_rests_on_update_types_for_a_requirement_written_as_a_range(self):
        exact = {package_name(line) for name in ("requirements.txt", "requirements-dev.txt")
                 for _, line in requirement_lines(name) if "==" in line}
        rules = self.ignore_rules()
        self.assertTrue(rules, "the pip entry has no ignore rules to check")
        for name, written in rules.items():
            with self.subTest(dependency=name):
                if "update-types" in written:
                    self.assertIn(name.lower(), exact,
                                  "this requirement is a range, and Dependabot did not apply a rule on update types "
                                  "to one (#39): ignore the dependency, or its `versions`, instead")


if __name__ == "__main__":
    unittest.main()
