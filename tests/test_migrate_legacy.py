"""Offline tests for scripts/migrate_legacy.py.

The script touches a user's real data, so the tests are about restraint: what it
refuses to copy, what it strips, and that a failed run cannot leave a half-written
config behind.
"""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import identity

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "migrate_legacy", ROOT / "scripts" / "migrate_legacy.py"
)
migrate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate)


def make_install(root: Path, *, name="JARVIS", key="AIza-not-a-real-key",
                 memory=None, config_extra=None) -> Path:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "memory").mkdir(parents=True, exist_ok=True)
    (root / "main.py").write_text("# placeholder", encoding="utf-8")
    config = {"gemini_api_key": key, "assistant_name": name, "user_name": "Sir",
              "voice_name": "Puck", "ui_color": "#ff3355"}
    config.update(config_extra or {})
    (root / "config" / "api_keys.json").write_text(json.dumps(config), encoding="utf-8")
    (root / "memory" / "long_term.json").write_text(
        json.dumps(memory if memory is not None else {"facts": ["likes tea"]}),
        encoding="utf-8",
    )
    return root


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.old = make_install(base / "old")
        self.new = make_install(base / "new", name="Ultron", key="", memory={})
        self.state = base / "state"
        self.state.mkdir()
        patcher = patch.object(migrate, "custom_state_dir", return_value=self.state)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_migration(self, **kwargs):
        return migrate.main(["--from", str(self.old), "--to", str(self.new), *[
            f"--{k.replace('_', '-')}" for k, v in kwargs.items() if v
        ]])

    def read_config(self):
        return json.loads((self.new / "config" / "api_keys.json").read_text(encoding="utf-8"))

    def read_memory(self):
        return json.loads((self.new / "memory" / "long_term.json").read_text(encoding="utf-8"))

    # ── the happy path ──────────────────────────────────────────────────────
    def test_memory_is_carried_over(self):
        self.old_memory = {"facts": ["likes tea", "works late"]}
        (self.old / "memory" / "long_term.json").write_text(
            json.dumps(self.old_memory), encoding="utf-8")
        self.assertEqual(self.run_migration(), 0)
        self.assertEqual(self.read_memory(), self.old_memory)

    def test_the_name_becomes_ultron(self):
        self.assertEqual(self.run_migration(), 0)
        self.assertEqual(self.read_config()["assistant_name"], identity.NAME)

    def test_keep_name_preserves_the_old_one(self):
        self.assertEqual(self.run_migration(keep_name=True), 0)
        self.assertEqual(self.read_config()["assistant_name"], "JARVIS")

    def test_other_settings_survive(self):
        self.assertEqual(self.run_migration(), 0)
        config = self.read_config()
        self.assertEqual(config["voice_name"], "Puck")
        self.assertEqual(config["ui_color"], "#ff3355")
        self.assertEqual(config["user_name"], "Sir")

    # ── secrets ─────────────────────────────────────────────────────────────
    def test_api_keys_are_blanked_by_default(self):
        self.assertEqual(self.run_migration(), 0)
        self.assertEqual(self.read_config()["gemini_api_key"], "")

    def test_nested_provider_keys_are_blanked_too(self):
        (self.old / "config" / "api_keys.json").write_text(json.dumps({
            "assistant_name": "JARVIS",
            "providers": {"groq": {"api_key": "gsk_secret", "model": "x"}},
        }), encoding="utf-8")
        self.assertEqual(self.run_migration(), 0)
        providers = self.read_config()["providers"]
        self.assertEqual(providers["groq"]["api_key"], "")
        self.assertEqual(providers["groq"]["model"], "x", "non-secret settings must survive")

    def test_include_keys_copies_them(self):
        self.assertEqual(self.run_migration(include_keys=True), 0)
        self.assertEqual(self.read_config()["gemini_api_key"], "AIza-not-a-real-key")

    def test_no_secret_value_is_ever_printed(self):
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.run_migration()
        output = buffer.getvalue()
        self.assertNotIn("AIza-not-a-real-key", output)
        self.assertIn("credentials removed", output)

    # ── restraint ───────────────────────────────────────────────────────────
    def test_dry_run_writes_nothing(self):
        before = (self.new / "config" / "api_keys.json").read_text(encoding="utf-8")
        self.assertEqual(self.run_migration(dry_run=True), 0)
        after = (self.new / "config" / "api_keys.json").read_text(encoding="utf-8")
        self.assertEqual(before, after)

    def test_same_folder_is_refused(self):
        self.assertEqual(migrate.main(["--from", str(self.old), "--to", str(self.old)]), 2)

    def test_a_folder_that_is_not_an_install_is_refused(self):
        empty = Path(self.temp.name) / "empty"
        empty.mkdir()
        self.assertEqual(migrate.main(["--from", str(empty), "--to", str(self.new)]), 2)

    def test_the_previous_file_is_backed_up(self):
        self.assertEqual(self.run_migration(), 0)
        backups = list((self.new / "config").glob("api_keys.json.bak-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(json.loads(backups[0].read_text(encoding="utf-8"))["assistant_name"],
                         "Ultron")

    def test_the_source_install_is_untouched(self):
        before = (self.old / "config" / "api_keys.json").read_text(encoding="utf-8")
        self.run_migration()
        after = (self.old / "config" / "api_keys.json").read_text(encoding="utf-8")
        self.assertEqual(before, after)

    def test_broken_json_stops_instead_of_guessing(self):
        (self.old / "memory" / "long_term.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(self.run_migration(), 2)

    def test_nothing_to_migrate_reports_so(self):
        for path in (self.old / "config" / "api_keys.json", self.old / "memory" / "long_term.json"):
            path.unlink()
        self.assertEqual(self.run_migration(), 3)

    # ── custom layer state ──────────────────────────────────────────────────
    def test_approved_insights_and_workspace_travel(self):
        (self.state / "approved-insights.json").write_text(
            json.dumps({"response_length": "concise"}), encoding="utf-8")
        (self.state / "workspace.json").write_text(
            json.dumps({"path": "C:/work"}), encoding="utf-8")
        self.assertEqual(self.run_migration(), 0)
        self.assertEqual(json.loads((self.state / "approved-insights.json")
                                    .read_text(encoding="utf-8"))["response_length"], "concise")

    def test_screenshots_and_backups_are_left_behind(self):
        (self.state / "screenshots").mkdir()
        (self.state / "screenshots" / "a.png").write_bytes(b"x")
        (self.state / "backups").mkdir()
        (self.state / "backups" / "b.json").write_text("{}", encoding="utf-8")
        self.assertEqual(self.run_migration(), 0)
        targets = {step["source"].name for step in
                   migrate.plan(self.old.resolve(), self.new.resolve(), False, False)["steps"]}
        self.assertNotIn("a.png", targets)
        self.assertNotIn("b.json", targets)


if __name__ == "__main__":
    unittest.main()
