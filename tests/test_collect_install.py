"""Offline tests for scripts/collect_install.py.

The script is meant to be pointed at somebody's real install folder, so the tests
care most about what it refuses to include and what it guarantees about secrets.
"""

import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "collect_install", ROOT / "scripts" / "collect_install.py"
)
collect = importlib.util.module_from_spec(_spec)
# Register before executing: dataclasses resolves annotations through
# sys.modules, and a module loaded from a path is not registered automatically.
sys.modules[_spec.name] = collect
_spec.loader.exec_module(collect)

SECRET = "AIza-SECRET-VALUE-SHOULD-NOT-APPEAR"
SECRET2 = "gsk-another-secret"
FACT = "My sister is called Priya"


def make_install(base: Path) -> Path:
    root = base / "mark-custom-jarvis"
    (root / "config").mkdir(parents=True)
    (root / "memory").mkdir(parents=True)
    (root / "actions").mkdir()
    (root / "__pycache__").mkdir()
    (root / "main.py").write_text("# code", encoding="utf-8")
    (root / "actions" / "open_app.py").write_text("# code", encoding="utf-8")
    (root / "actions" / "open_app.cpython-312.pyc").write_text("x", encoding="utf-8")
    (root / "__pycache__" / "junk.pyc").write_text("x", encoding="utf-8")
    (root / "LICENSE").write_text("CC BY-NC 4.0", encoding="utf-8")
    (root / "screenshot.png").write_bytes(b"\x89PNG")
    (root / "config" / "api_keys.json").write_text(json.dumps({
        "assistant_name": "JARVIS",
        "gemini_api_key": SECRET,
        "providers": {"groq": {"api_key": SECRET2, "model": "m"}},
    }), encoding="utf-8")
    (root / "memory" / "long_term.json").write_text(json.dumps({
        "identity": {"sister": FACT},
        "sessions": [],
    }), encoding="utf-8")
    return root


class ClassifyTests(unittest.TestCase):
    def test_known_paths(self):
        self.assertEqual(collect.classify("memory/long_term.json"), "data")
        self.assertEqual(collect.classify("config/api_keys.json"), "config")
        self.assertEqual(collect.classify("main.py"), "code")
        self.assertEqual(collect.classify("LICENSE"), "doc")
        self.assertEqual(collect.classify("screenshot.png"), "cache")
        self.assertEqual(collect.classify("mystery.bin"), "unknown")

    def test_a_json_at_the_root_is_data_not_config(self):
        self.assertEqual(collect.classify("something.json"), "data")

    def test_a_json_inside_a_package_folder_is_config(self):
        self.assertEqual(collect.classify("dashboard/settings.json"), "config")

    def test_the_state_file_is_not_user_data(self):
        self.assertEqual(collect.classify(collect.STATE_FILENAME), "cache")

    def test_database_and_log_extensions(self):
        self.assertEqual(collect.classify("state/knowledge.sqlite3"), "data")
        self.assertEqual(collect.classify("debug.log"), "cache")


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = make_install(Path(self.temp.name))

    def test_caches_and_virtualenvs_are_skipped(self):
        result = collect.scan(self.root)
        rels = {item.rel for item in result.files}
        self.assertNotIn("__pycache__/junk.pyc", rels)
        self.assertIn("main.py", rels)

    def test_a_stray_compiled_file_is_cache_not_data(self):
        # Scan lists everything it sees; what matters is that a .pyc is never
        # classified as data, because that is what decides what gets bundled.
        kinds = {item.rel: item.kind for item in collect.scan(self.root).files}
        self.assertEqual(kinds["actions/open_app.cpython-312.pyc"], "cache")
        self.assertEqual(kinds["screenshot.png"], "cache")

    def test_the_data_files_are_found(self):
        result = collect.scan(self.root)
        data = {item.rel for item in result.files if item.kind in ("data", "config")}
        self.assertEqual(data, {"memory/long_term.json", "config/api_keys.json"})

    def test_our_own_state_file_is_ignored(self):
        (self.root / collect.STATE_FILENAME).write_text("{}", encoding="utf-8")
        result = collect.scan(self.root)
        self.assertNotIn(collect.STATE_FILENAME, {item.rel for item in result.files})

    def test_fingerprints_change_when_content_changes(self):
        first = collect.snapshot_of(collect.scan(self.root))
        (self.root / "memory" / "long_term.json").write_text(
            json.dumps({"identity": {"a": "b"}}), encoding="utf-8")
        second = collect.snapshot_of(collect.scan(self.root))
        self.assertNotEqual(first["memory/long_term.json"], second["memory/long_term.json"])


class ChangeTests(unittest.TestCase):
    def test_added_changed_and_removed(self):
        changes = collect.compare(
            {"a": "1", "b": "2", "c": "3"},
            {"a": "1", "b": "CHANGED", "d": "4"},
        )
        self.assertEqual(changes["new"], ["d"])
        self.assertEqual(changes["changed"], ["b"])
        self.assertEqual(changes["gone"], ["c"])

    def test_nothing_changed(self):
        same = {"a": "1"}
        self.assertEqual(collect.compare(same, same),
                         {"new": [], "changed": [], "gone": []})


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = make_install(Path(self.temp.name))
        self.out = Path(self.temp.name) / "out.zip"

    def test_the_bundle_holds_data_and_not_code(self):
        manifest = collect.build_bundle(collect.scan(self.root), self.out)
        names = zipfile.ZipFile(self.out).namelist()
        self.assertIn("data/memory/long_term.json", names)
        self.assertIn("data/config/api_keys.json", names)
        self.assertIn("MANIFEST.json", names)
        self.assertIn("REPORT.txt", names)
        self.assertFalse([n for n in names if n.endswith(".py")])
        self.assertEqual(len(manifest["files"]), 2)

    def test_secrets_are_blanked_by_default(self):
        collect.build_bundle(collect.scan(self.root), self.out)
        with zipfile.ZipFile(self.out) as archive:
            config = json.loads(archive.read("data/config/api_keys.json"))
            report = archive.read("REPORT.txt").decode("utf-8")
        self.assertEqual(config["gemini_api_key"], "")
        self.assertEqual(config["providers"]["groq"]["api_key"], "")
        self.assertEqual(config["providers"]["groq"]["model"], "m")
        self.assertEqual(config["assistant_name"], "JARVIS")
        self.assertNotIn(SECRET, report)
        self.assertIn("gemini_api_key", report)

    def test_include_secrets_keeps_them(self):
        collect.build_bundle(collect.scan(self.root), self.out, include_secrets=True)
        with zipfile.ZipFile(self.out) as archive:
            config = json.loads(archive.read("data/config/api_keys.json"))
        self.assertEqual(config["gemini_api_key"], SECRET)

    def test_the_report_states_that_no_transcript_is_stored(self):
        collect.build_bundle(collect.scan(self.root), self.out)
        with zipfile.ZipFile(self.out) as archive:
            report = archive.read("REPORT.txt").decode("utf-8")
        self.assertIn("no conversation transcript", report)
        self.assertIn("Nothing was uploaded", report)

    def test_oversized_files_are_skipped_not_truncated(self):
        original = collect.MAX_BUNDLE_FILE
        collect.MAX_BUNDLE_FILE = 10
        self.addCleanup(setattr, collect, "MAX_BUNDLE_FILE", original)
        manifest = collect.build_bundle(collect.scan(self.root), self.out)
        self.assertEqual(manifest["files"], [])
        self.assertTrue(manifest["skipped"])


class CliTests(unittest.TestCase):
    def test_a_missing_folder_is_refused(self):
        self.assertEqual(collect.main(["--path", "/definitely/not/here"]), 2)

    def test_a_scan_succeeds_and_writes_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = make_install(Path(temp))
            self.assertEqual(collect.main(["--path", str(root)]), 0)
            self.assertTrue((root / collect.STATE_FILENAME).exists())

    def test_json_output_parses(self):
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as temp:
            root = make_install(Path(temp))
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                collect.main(["--path", str(root), "--json"])
            payload = json.loads(buffer.getvalue())
        self.assertIn("scan", payload)
        self.assertGreater(payload["scan"]["counts"]["code"], 0)


if __name__ == "__main__":
    unittest.main()
