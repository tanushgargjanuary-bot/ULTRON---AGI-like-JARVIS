"""Offline tests for scripts/inventory_data.py.

The point of the script is restraint as much as reporting: it may say that a
credential field exists; it may never say what is in it, and it may never print
a stored memory.
"""

import contextlib
import importlib.util
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "inventory_data", ROOT / "scripts" / "inventory_data.py"
)
inventory_data = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(inventory_data)

SECRET = "AIza-THIS-IS-THE-SECRET"
FACT = "My sister is called Priya"


def build_install(base: Path, *, sessions=None, facts=None, key=SECRET) -> Path:
    install = base / "install"
    (install / "config").mkdir(parents=True)
    (install / "memory").mkdir(parents=True)
    (install / "config" / "api_keys.json").write_text(json.dumps({
        "gemini_api_key": key,
        "assistant_name": "JARVIS",
        "providers": {"groq": {"api_key": "gsk_another_secret", "model": "x"}},
    }), encoding="utf-8")
    memory = {
        "identity": {"name": FACT} if facts else {},
        "preferences": {},
        "sessions": sessions or [],
    }
    (install / "memory" / "long_term.json").write_text(
        json.dumps(memory), encoding="utf-8")
    return install


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.state = self.base / "state"
        self.state.mkdir()

    def report(self, install):
        return inventory_data.inventory(install, self.state)

    def test_empty_install_reports_nothing(self):
        report = self.report(self.base / "nothing")
        self.assertEqual(report["files"], [])
        self.assertEqual(report["summary"]["conversation_summaries"], 0)

    def test_files_and_counts_are_reported(self):
        install = build_install(self.base, sessions=[{"date": "2026-11-05", "summary": "x"}],
                                facts=True)
        report = self.report(install)
        self.assertEqual(report["summary"]["conversation_summaries"], 1)
        self.assertEqual(report["summary"]["saved_facts"], 1)

    def test_no_sessions_means_the_honest_verdict(self):
        install = build_install(self.base)
        report = self.report(install)
        self.assertEqual(report["summary"]["conversation_summaries"], 0)
        self.assertIn("no conversation history", report["summary"]["verdict"])

    def test_credential_fields_are_named_but_not_valued(self):
        install = build_install(self.base)
        report = self.report(install)
        config = next(f for f in report["files"] if f["file"].endswith("api_keys.json"))
        self.assertIn("gemini_api_key", config["credential_fields"])
        self.assertEqual(config["credential_fields_present"], 1)
        self.assertNotIn(SECRET, json.dumps(report))

    def test_printed_output_contains_no_memory_and_no_secret(self):
        install = build_install(self.base, facts=True)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            inventory_data.print_human(self.report(install))
        output = buffer.getvalue()
        self.assertNotIn(SECRET, output)
        self.assertNotIn("Priya", output, "a stored memory must never be printed")
        self.assertIn("gemini_api_key", output)

    def test_sqlite_tables_and_rows_are_counted(self):
        database = self.state / "knowledge.sqlite3"
        connection = sqlite3.connect(database)
        connection.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY, name TEXT)")
        connection.executemany("INSERT INTO tasks (name) VALUES (?)", [("a",), ("b",)])
        connection.commit()
        connection.close()
        report = self.report(build_install(self.base))
        sqlite_report = next(f for f in report["files"] if f["kind"] == "sqlite")
        self.assertEqual(sqlite_report["tables"]["tasks"], 2)

    def test_state_json_is_included(self):
        (self.state / "approved-insights.json").write_text(
            json.dumps({"response_length": "concise"}), encoding="utf-8")
        report = self.report(build_install(self.base))
        names = [Path(f["file"]).name for f in report["files"]]
        self.assertIn("approved-insights.json", names)

    def test_broken_json_is_reported_not_raised(self):
        install = build_install(self.base)
        (install / "memory" / "long_term.json").write_text("{broken", encoding="utf-8")
        report = self.report(install)
        entry = next(f for f in report["files"] if f["file"].endswith("long_term.json"))
        self.assertIn("error", entry)

    def test_cli_json_output_parses(self):
        install = build_install(self.base)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = inventory_data.main(["--install", str(install),
                                        "--state", str(self.state), "--json"])
        self.assertEqual(code, 0)
        self.assertIn("summary", json.loads(buffer.getvalue()))

    def test_cli_rejects_a_missing_folder(self):
        self.assertEqual(inventory_data.main(["--install", str(self.base / "nope")]), 2)


if __name__ == "__main__":
    unittest.main()
