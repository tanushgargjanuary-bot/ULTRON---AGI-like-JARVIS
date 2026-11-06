"""The installer, checked from a machine that cannot run it.

An installer is the one piece of software that is almost never run before it ships,
on the one platform the author is not using, and its failures are the expensive
kind: a file left out of the payload, a version number that says 0.0.0, an
uninstaller that deletes somebody's API keys.

So these tests check what can be checked anywhere — that the list of files is real,
that the three files agree with each other, that nothing sensitive is included, and
that the uninstall rules keep the owner's data. What they cannot check is that Inno
Setup compiles the script or that Windows runs the result; that needs a Windows
machine, and `docs/INSTALL.md` says so instead of pretending otherwise.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGING = ROOT / "packaging"


def read(name: str) -> str:
    return (PACKAGING / name).read_text(encoding="utf-8")


class ThePayloadList(unittest.TestCase):
    """What ships is a list somebody can read, not a wildcard nobody checks."""

    def payload(self) -> list[str]:
        entries = []
        for line in read("payload.txt").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            entries.append(line.rstrip("/"))
        return entries

    def test_every_named_path_exists(self):
        missing = [entry for entry in self.payload()
                   if not (ROOT / entry).exists()]
        self.assertEqual(missing, [],
                         "the installer would ship a path that is not in the tree")

    def test_it_ships_the_things_a_start_needs(self):
        entries = set(self.payload())
        for needed in ("main.py", "run.ps1", "requirements.txt", "core",
                       "providers", "config"):
            self.assertIn(needed, entries, f"{needed} is not in the payload")

    def test_no_development_folder_slips_in(self):
        entries = self.payload()
        for unwanted in (".git", ".venv", "build", "dist", "__pycache__"):
            self.assertNotIn(unwanted, entries)

    def test_the_owners_own_configuration_is_not_shipped(self):
        # A fresh install must reach the setup screen, not somebody's keys.
        text = read("payload.txt")
        self.assertNotIn("api_keys.json", text)

    def test_the_build_script_stages_from_this_one_list(self):
        script = read("build_installer.ps1")
        self.assertIn("payload.txt", script,
                      "the build script must stage from the payload list, not a "
                      "wildcard")


class TheVersion(unittest.TestCase):
    def test_it_is_three_numbers(self):
        version = read("version.txt").strip()
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")

    def test_it_matches_the_release_record(self):
        # log.txt is where every build writes its number down. Two places that
        # disagree about the version is how a bug report arrives for a build that
        # was never published.
        version = read("version.txt").strip()
        log = (ROOT / "log.txt").read_text(encoding="utf-8", errors="replace")
        found = re.findall(r"build (\d+\.\d+\.\d+)", log)
        self.assertTrue(found, "log.txt records no build number")
        newest = max(found, key=lambda item: tuple(int(part) for part in item.split(".")))
        self.assertEqual(version, newest,
                         "packaging/version.txt and the newest logged build disagree")


class TheInnoScript(unittest.TestCase):
    def setUp(self):
        self.text = read("ultron.iss")

    def test_it_installs_without_an_administrator(self):
        self.assertIn("PrivilegesRequired=lowest", self.text,
                      "an assistant that needs an administrator password is one most "
                      "people cannot install")

    def test_it_offers_shortcuts(self):
        self.assertIn("[Icons]", self.text)
        self.assertIn("desktopicon", self.text)

    def test_the_start_menu_entry_runs_the_launcher_that_exists(self):
        self.assertIn("run.ps1", self.text)

    def uninstall_rules(self) -> str:
        """The lines that actually delete something, without their comments.

        The comment above [UninstallDelete] explains that the memory store is NOT
        deleted, and a search for the word "memory" finds that explanation and calls
        it a deletion. Only `Type:` lines delete.
        """
        block = self.text.split("[UninstallDelete]", 1)[1].split("[Code]", 1)[0]
        return "\n".join(line for line in block.splitlines()
                         if line.strip().startswith("Type:"))

    def test_the_uninstall_keeps_the_owners_data(self):
        block = self.uninstall_rules()
        self.assertNotIn("api_keys.json", block,
                         "uninstalling must not delete the key file")
        self.assertNotIn("memory", block,
                         "uninstalling must not delete the memory store")

    def test_it_removes_the_environment_it_built(self):
        self.assertIn(".venv", self.uninstall_rules())

    def test_it_says_where_the_kept_files_are(self):
        self.assertIn("api_keys.json", self.text,
                      "the uninstaller must tell the owner what it kept and where")
        self.assertIn("memory", self.text)

    def test_it_checks_for_python_before_copying_anything(self):
        self.assertIn("PythonPresent", self.text)
        self.assertIn("python.org", self.text)

    def test_the_icon_it_names_exists(self):
        for match in re.finditer(r"jarvis\.ico", self.text):
            self.assertTrue((ROOT / "config" / "jarvis.ico").exists())
        self.assertIn("jarvis.ico", self.text, "the installer should look like the app")

    def test_the_output_name_carries_the_version(self):
        self.assertIn("OutputBaseFilename=UltronSetup-{#AppVersion}", self.text)

    def test_no_secret_is_written_into_the_installer(self):
        for pattern in (r"sk-[A-Za-z0-9]{20,}", r"github_pat_[0-9A-Za-z_]{40,}",
                        r"AIza[0-9A-Za-z_-]{30,}"):
            self.assertIsNone(re.search(pattern, self.text))


class TheBuildScript(unittest.TestCase):
    def setUp(self):
        self.text = read("build_installer.ps1")

    def test_it_reads_the_same_three_files_as_everything_else(self):
        for name in ("version.txt", "payload.txt", "ultron.iss"):
            self.assertIn(name, self.text)

    def test_it_stops_with_a_sentence_rather_than_a_stack_trace(self):
        self.assertIn("Stop-With", self.text)
        self.assertIn("Inno Setup was not found", self.text)

    def test_it_refuses_a_staged_folder_with_development_files(self):
        for unwanted in (".git", ".venv", "__pycache__"):
            self.assertIn(unwanted, self.text)

    def test_it_passes_the_version_to_the_compiler(self):
        self.assertIn("/DAppVersion=", self.text)


class TheSelfContainedSpec(unittest.TestCase):
    """The PyInstaller route: checked for structure, not for working."""

    def setUp(self):
        self.path = PACKAGING / "ultron.spec"
        self.text = self.path.read_text(encoding="utf-8")
        self.tree = ast.parse(self.text, filename=str(self.path))

    def test_it_is_a_python_file_that_parses(self):
        self.assertTrue(self.tree.body)

    def test_every_data_folder_it_names_exists(self):
        block = self.text.split("DATA = [", 1)[1].split("]", 1)[0]
        named = re.findall(r'"([^"]+)"', block)
        self.assertTrue(named)
        for path in named:
            self.assertTrue((ROOT / path).exists(), f"{path} is not in the tree")

    def test_it_starts_main_py(self):
        self.assertIn('"main.py"', self.text)

    def test_it_says_plainly_that_it_has_not_been_built(self):
        # An unbuilt route described as working is a claim nobody can check.
        self.assertIn("not yet built on Windows", self.text)


class TheInstructions(unittest.TestCase):
    def test_the_paths_the_page_tells_people_to_use_exist(self):
        text = (ROOT / "docs" / "INSTALL.md").read_text(encoding="utf-8")
        for named in ("packaging\\build_installer.ps1", "packaging\\ultron.spec",
                      "packaging\\payload.txt", "packaging\\version.txt",
                      "run.ps1", "requirements.txt"):
            self.assertIn(named, text, f"the page does not mention {named}")
            self.assertTrue((ROOT / named.replace("\\", "/")).exists(),
                            f"{named} is named but not in the tree")

    def test_it_tells_the_reader_what_it_keeps_on_uninstall(self):
        text = (ROOT / "docs" / "INSTALL.md").read_text(encoding="utf-8")
        self.assertIn("api_keys.json", text)
        self.assertIn("kept", text)


if __name__ == "__main__":
    unittest.main()
