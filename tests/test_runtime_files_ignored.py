"""Every file the app can leave in the project folder is ignored by git, or this fails.

The repository is public and the app's own `ship` tool stages with `git add -A`. A file the app writes
that `.gitignore` does not name is therefore a file that can be published by the next ship. The first
version of the memory store's crash safety made exactly that mistake: a store that would not parse was
set aside as `memory/long_term.json.broken-<epoch>` — a copy of everything the user had asked to be
remembered — and no rule named it. `git add -A --dry-run` listed it.

The names here are produced by the real functions, in a scratch folder laid out like the project, and
each is then put to `git check-ignore` with this repository's own `.gitignore`. A name typed into a test
would only prove the test; a name the code made proves the rule.
"""

import contextlib
import io
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GIT = shutil.which("git")


@unittest.skipUnless(GIT, "git is not installed")
class EveryFileTheAppLeavesIsIgnored(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = Path(tempfile.mkdtemp())
        subprocess.run([GIT, "init", "-q"], cwd=cls.repo, check=True)
        shutil.copyfile(ROOT / ".gitignore", cls.repo / ".gitignore")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.repo, ignore_errors=True)

    def ignored(self, relative: str) -> bool:
        done = subprocess.run([GIT, "check-ignore", "-q", relative], cwd=self.repo)
        return done.returncode == 0

    def assertIgnored(self, relative: str):
        self.assertTrue(self.ignored(relative), f"git would publish {relative}")

    # -- what the memory store makes ------------------------------------------------------------

    def test_a_memory_store_that_would_not_parse_is_set_aside_under_an_ignored_name(self):
        from memory import memory_manager as store
        folder = Path(tempfile.mkdtemp())
        path = folder / "memory" / "long_term.json"
        path.parent.mkdir()
        path.write_text('{"identity": {"name": ', encoding="utf-8")          # cut off mid-write
        with mock.patch.object(store, "MEMORY_PATH", path):
            store.load_memory()
        moved = [item.name for item in path.parent.iterdir() if item.name != path.name]
        self.assertEqual(len(moved), 1, f"expected one set-aside copy, found {moved}")
        self.assertIn(".broken-", moved[0])
        self.assertIgnored(f"memory/{moved[0]}")
        shutil.rmtree(folder, ignore_errors=True)

    def test_two_set_aside_in_one_second_are_both_ignored(self):
        from memory import memory_manager as store
        folder = Path(tempfile.mkdtemp())
        path = folder / "memory" / "long_term.json"
        path.parent.mkdir()
        with mock.patch.object(store, "MEMORY_PATH", path), mock.patch.object(time, "time", return_value=1763700000):
            for _ in range(2):
                path.write_text("{", encoding="utf-8")
                store.load_memory()
        names = sorted(item.name for item in path.parent.iterdir())
        self.assertEqual(len(names), 2, names)
        for name in names:
            self.assertIgnored(f"memory/{name}")
        shutil.rmtree(folder, ignore_errors=True)

    def test_the_temporary_file_of_a_write_that_was_cut_short_is_ignored(self):
        from memory import memory_manager as store
        folder = Path(tempfile.mkdtemp())
        path = folder / "memory" / "long_term.json"
        path.parent.mkdir()
        # A kill between writing the temporary file and moving it leaves it behind. Stand in for
        # the kill: the move fails and the clean-up that would remove the file is skipped.
        with mock.patch.object(store, "MEMORY_PATH", path), \
                mock.patch.object(store, "replace_with_retry", side_effect=OSError("cut short")), \
                mock.patch.object(Path, "unlink", lambda *args, **kwargs: None):
            with self.assertRaises(OSError):
                store._write_store({"identity": {}})
        left = [item.name for item in path.parent.iterdir()]
        self.assertEqual(len(left), 1, left)
        self.assertTrue(left[0].startswith(".long_term.json."), left)
        self.assertIgnored(f"memory/{left[0]}")
        shutil.rmtree(folder, ignore_errors=True)

    # -- what the self-change pipeline and its boot guard make ----------------------------------

    def test_everything_a_self_change_leaves_in_its_folder_is_ignored(self):
        # Proposals hold the whole old and new text of the file, the backups are the files it replaced,
        # and the app's own `ship` runs `git add -A`. None of it was ignored.
        from core import self_change
        folder = Path(tempfile.mkdtemp())
        project = folder / "project"
        project.mkdir()
        (project / "app.py").write_text("x = 1\n", encoding="utf-8")
        store = project / "config" / "self_change"
        self_change.set_root(project)
        self_change.set_store(store)
        try:
            proposal = self_change.propose("app.py", "a test", find="x = 1", replace="x = 2")
            self_change.rehearse(proposal["id"], command=[sys.executable, "-c", "pass"])
            self_change.confirm(proposal["id"], "voice")
            self_change.confirm(proposal["id"], "panel")
            self_change.apply(proposal["id"])
        finally:
            self_change.set_root(None)
            self_change.set_store(None)
        names = sorted(path.relative_to(project).as_posix() for path in project.rglob("*")
                       if path.is_file() and path.name != "app.py")
        for needed in ("proposals.json", "ledger.jsonl", "boot-watch.json"):
            self.assertIn(f"config/self_change/{needed}", names)
        self.assertTrue(any(name.endswith(".bak") for name in names), names)
        self.assertIn("restart-required.json", names)
        for name in names:
            self.assertIgnored(name)
        shutil.rmtree(folder, ignore_errors=True)

    # -- what the settings writer makes ------------------------------------------------------

    def test_a_damaged_settings_file_and_a_half_written_one_are_ignored(self):
        from memory import config_manager as settings
        folder = Path(tempfile.mkdtemp())
        config = folder / "config"
        config.mkdir()
        target = config / "api_keys.json"
        target.write_text('{"gemini_api_key": "FIXTURE', encoding="utf-8")
        with mock.patch.object(settings, "CONFIG_DIR", config), mock.patch.object(settings, "CONFIG_FILE", target), \
                mock.patch.object(settings, "_replace_with_retry", side_effect=OSError("cut short")), \
                mock.patch.object(Path, "unlink", lambda *args, **kwargs: None):
            with contextlib.redirect_stdout(io.StringIO()):      # the module prints that it failed
                settings._load_for_write()           # sets the damaged file aside
                settings._write_config({"a": 1})     # leaves its temporary file behind
        names = sorted(item.name for item in config.iterdir() if item.name != target.name)
        self.assertTrue(any(".broken-" in name for name in names), names)
        self.assertTrue(any(name.endswith(".tmp") for name in names), names)
        for name in names:
            self.assertIgnored(f"config/{name}")
        shutil.rmtree(folder, ignore_errors=True)

    def test_the_local_model_script_backup_and_its_leftover_temporary_file_are_ignored(self):
        # scripts/local_model.py writes `api_keys.json.bak` (a copy of every key) and, through
        # mkstemp, a temporary file named `api_keys.json.<random>.tmp`; a kill between the two
        # leaves the second behind.
        try:
            from scripts import local_model
        except ImportError as error:                    # `requests` is not installed here
            self.skipTest(f"scripts/local_model.py cannot be imported here: {error}")
        folder = Path(tempfile.mkdtemp())
        config = folder / "config"
        config.mkdir()
        target = config / "api_keys.json"
        target.write_text('{"gemini_api_key": "FIXTURE"}', encoding="utf-8")
        with mock.patch.object(local_model.os, "replace", side_effect=OSError("cut short")), \
                mock.patch.object(Path, "unlink", lambda *args, **kwargs: None):
            with self.assertRaises(OSError):
                local_model.write_config(target, "http://localhost:11434", "llama3.2:3b")
        names = sorted(item.name for item in config.iterdir() if item.name != target.name)
        self.assertTrue(any(name.endswith(".bak") for name in names), names)
        self.assertTrue(any(name.endswith(".tmp") for name in names), names)
        for name in names:
            self.assertIgnored(f"config/{name}")
        shutil.rmtree(folder, ignore_errors=True)

    # -- what the background programs write --------------------------------------------------

    def test_the_log_of_a_background_program_is_ignored(self):
        from core import crash
        folder = Path(tempfile.mkdtemp())
        path = crash.child_log_path("ollama", root=folder)
        self.assertIgnored(path.relative_to(folder).as_posix())
        shutil.rmtree(folder, ignore_errors=True)

    # -- machine state the app keeps in the project folder ---------------------------------

    def test_the_names_the_app_keeps_about_this_machine_are_ignored(self):
        # Where each is made: main.py (the watcher's event file), scripts/evolve.py (LOG_PATH),
        # actions/dev_agent.py (_BRIEF_DIR, one file per project).
        for relative in ("memory/watch-events.jsonl", "memory/evolution-log.json",
                         "config/project_briefs/0123456789abcdef.json"):
            self.assertIgnored(relative)

    def test_the_names_that_were_already_ignored_still_are(self):
        for relative in ("config/api_keys.json", "memory/long_term.json", "memory/long_term.json.bak-1",
                         "config/certs/jarvis.key", "state/memory_changes.json"):
            self.assertIgnored(relative)

    # -- and the rules do not swallow the project's own files --------------------------------

    def test_source_files_in_those_folders_are_not_ignored(self):
        tracked = subprocess.run([GIT, "ls-files", "memory", "config"], cwd=ROOT, capture_output=True,
                                 text=True).stdout.split()
        if not tracked:
            self.skipTest("this copy of the project has no git history to ask")
        for relative in tracked:
            self.assertFalse(self.ignored(relative), f"{relative} is tracked and must not be ignored")


if __name__ == "__main__":
    unittest.main()
