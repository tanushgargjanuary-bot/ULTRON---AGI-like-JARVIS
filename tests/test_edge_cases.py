"""tests/test_edge_cases.py — the inputs nobody types on purpose.

Written after driving every tool, every settable value and both engine paths with
empty, null, wrong-typed and hostile input, then fixing what fell over. Each class
below is one of those answers, and each test fails without its fix.

    NullParameterTests        a tool call with "action": null crashed six actions
    MemoryIntegrityTests      concurrent writes lost facts; a scalar ate a category
    ConfigWriteTests          a read-only config folder raised out of a Qt slot
    ProviderRobustnessTests   a hand-edited config crashed the provider build
    VisionProbeTests          "could not ask" was recorded as "cannot see"
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ── tools and null parameters ────────────────────────────────────────────────

class NullParameterTests(unittest.TestCase):
    """`{"action": null}` reached handlers as None and raised AttributeError.

    dict.get(key, default) returns the default only when the key is ABSENT. A
    model that sends an explicit null — which Gemini does for optional fields —
    got "Tool 'file_controller' failed: 'NoneType' object has no attribute
    'lower'" back. Six of seventeen actions fell over on it.
    """

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.dir = Path(self._temp.name)

    def tearDown(self):
        self._temp.cleanup()

    def test_the_loader_drops_nulls_before_a_handler_sees_them(self):
        from core.action_loader import _clean_parameters
        self.assertEqual(_clean_parameters({"a": None, "b": 1}), {"b": 1})
        self.assertEqual(_clean_parameters(None), {})
        self.assertEqual(_clean_parameters({"a": None}), {})
        self.assertEqual(_clean_parameters([1, 2]), [1, 2])

    def test_a_null_action_reaches_the_handler_as_missing(self):
        from core.action_loader import discover_actions
        (self.dir / "probe.py").write_text(
            "def _h(parameters=None, **_kw):\n"
            "    return 'keys=' + ','.join(sorted(parameters or {}))\n"
            "TOOL = {'name': 'probe', 'description': 'x',\n"
            "        'parameters': {'type': 'OBJECT', 'properties': {}},\n"
            "        'handler': _h}\n", encoding="utf-8")
        registry = discover_actions(self.dir, logger=lambda _m: None)
        self.assertEqual(registry.run("probe", {"action": None, "path": ""}),
                         "keys=path")

    def test_every_action_survives_a_null_action(self):
        """The six that used to raise, through the real dispatcher."""
        from core.action_loader import discover_actions
        registry = discover_actions(ROOT / "actions", logger=lambda _m: None)
        hostile = [{"action": None, "path": None, "text": None, "query": None},
                   {"action": 5}, {"action": ""}, {},
                   {"action": ["not", "a", "string"]},
                   {"action": "play", "volume": "loud", "seconds": "soon"}]
        for name in sorted(registry.names()):
            for params in hostile:
                with self.subTest(tool=name, params=params):
                    out = registry.run(name, dict(params))
                    self.assertIsInstance(out, str)
                    self.assertNotIn("NoneType", out)


# ── memory ───────────────────────────────────────────────────────────────────

class MemoryIntegrityTests(unittest.TestCase):
    def setUp(self):
        from memory import memory_manager as mm
        self.mm = mm
        self._temp = tempfile.TemporaryDirectory()
        self._saved = mm.MEMORY_PATH
        mm.MEMORY_PATH = Path(self._temp.name) / "long_term.json"

    def tearDown(self):
        self.mm.MEMORY_PATH = self._saved
        self._temp.cleanup()

    def store(self) -> dict:
        return json.loads(self.mm.MEMORY_PATH.read_text(encoding="utf-8"))

    def test_concurrent_writes_do_not_lose_facts(self):
        # Measured before the fix: six threads, thirty writes each, 53 of 180
        # remembered facts survived. No error, no message — just facts the user
        # asked to be remembered, gone.
        def work(i):
            for j in range(30):
                self.mm.update_memory({"notes": {f"t{i}_{j}": {"value": str(j)}}})

        threads = [threading.Thread(target=work, args=(i,)) for i in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(self.store()["notes"]), 180)

    def test_a_scalar_cannot_replace_a_whole_category(self):
        # {"notes": "not a dict"} turned the category into one value and every
        # entry in it was gone.
        self.mm.update_memory({"notes": {"dentist": {"value": "Tuesday"}}})
        self.mm.update_memory({"notes": "not a dict"})
        notes = self.store()["notes"]
        self.assertIsInstance(notes, dict)
        self.assertIn("dentist", notes)

    def test_a_corrupt_file_is_replaced_not_crashed_on(self):
        Path(self.mm.MEMORY_PATH).write_text('{"notes": {"a": {"val', encoding="utf-8")
        self.assertEqual(self.mm.load_memory()["notes"], {})
        self.mm.update_memory({"notes": {"k": {"value": "v"}}})
        self.assertEqual(self.store()["notes"]["k"]["value"], "v")

    def test_a_list_shaped_file_does_not_break_a_write(self):
        Path(self.mm.MEMORY_PATH).write_text("[1, 2, 3]", encoding="utf-8")
        self.mm.update_memory({"notes": {"k": {"value": "v"}}})
        self.assertEqual(self.store()["notes"]["k"]["value"], "v")


# ── config writes ────────────────────────────────────────────────────────────

class ConfigWriteTests(unittest.TestCase):
    """A setting that cannot be saved is a sentence, not a crash.

    PyQt6 turns an unhandled exception in a slot into an abort, so a read-only
    config folder meant changing a colour closed the application.
    """

    def setUp(self):
        from memory import config_manager as cm
        self.cm = cm
        self._temp = tempfile.TemporaryDirectory()
        self.dir = Path(self._temp.name)
        self._saved = (cm.CONFIG_DIR, cm.CONFIG_FILE)
        cm.CONFIG_DIR = self.dir
        cm.CONFIG_FILE = self.dir / "api_keys.json"

    def tearDown(self):
        self.cm.CONFIG_DIR, self.cm.CONFIG_FILE = self._saved
        try:
            os.chmod(self.dir, 0o700)
        except OSError:
            pass
        self._temp.cleanup()

    @unittest.skipIf(os.name == "nt",
                     "Windows ignores the read-only attribute on a folder, so a "
                     "read-only folder cannot be made here")
    def test_a_read_only_folder_does_not_raise(self):
        self.cm.save_ui_scale(1.3)                      # create it first
        os.chmod(self.dir, 0o500)
        self.cm.save_ui_scale(1.6)                      # must not raise
        os.chmod(self.dir, 0o700)
        self.assertEqual(self.cm.get_ui_scale(), 1.3, "the old value stands")

    def test_a_config_folder_that_is_a_file_does_not_raise(self):
        blocker = self.dir / "config-is-a-file"
        blocker.write_text("x", encoding="utf-8")
        self.cm.CONFIG_DIR = blocker
        self.cm.CONFIG_FILE = blocker / "api_keys.json"
        self.assertFalse(self.cm.ensure_config_dir())
        self.cm.save_ui_scale(1.4)                      # must not raise

    def test_a_successful_write_reports_success(self):
        self.assertTrue(self.cm.ensure_config_dir())
        self.cm.save_ui_scale(1.2)
        self.assertTrue(self.cm.CONFIG_FILE.exists())

    def test_scale_is_still_bounded_both_ways(self):
        self.cm.save_ui_scale(99)
        self.assertEqual(self.cm.get_ui_scale(), self.cm.UI_SCALE_MAX)
        self.cm.save_ui_scale(0.01)
        self.assertEqual(self.cm.get_ui_scale(), self.cm.UI_SCALE_MIN,
                         "below the floor is lifted to the floor, not stored")
        self.cm.save_ui_scale("not a number")
        self.assertEqual(self.cm.get_ui_scale(), 0.0)


# ── providers ────────────────────────────────────────────────────────────────

class ProviderRobustnessTests(unittest.TestCase):
    """Every value here comes from a file a person may have typed into."""

    def test_a_junk_config_still_builds(self):
        from providers import registry
        llm = registry.build("openai_compat@groq", {
            "base_url": 7, "model": 123, "api_key": 5,
            "timeout": "soon", "max_tools": "lots", "vision": "maybe"})
        self.assertEqual(llm.model, "123")
        self.assertEqual(llm.key, "5")
        self.assertGreater(llm.timeout, 0)

    def test_an_id_that_is_not_a_string_is_reported_not_raised_as_a_type_error(self):
        from providers import registry
        for bad in (None, 5, "", "no_such_provider", "a@b@c"):
            with self.subTest(id=bad):
                with self.assertRaises(LookupError):
                    registry.build(bad, {})
                self.assertFalse(registry.get_declaration(bad))

    def test_a_non_dict_config_is_treated_as_empty(self):
        from providers import registry
        llm = registry.build("openai_compat@groq", ["not", "a", "dict"])
        self.assertEqual(llm.model, "")
        self.assertEqual(llm.key, "")


class VisionProbeTests(unittest.TestCase):
    """A model server that is not running yet is not a model without eyes.

    Measured: unreachable Ollama made the app write `vision: ""` over a stored
    "yes", withdraw the screen and camera tools for that session, every launch.
    """

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.dir = Path(self._temp.name)
        from memory import config_manager as cm
        self.cm = cm
        self._saved = (cm.CONFIG_DIR, cm.CONFIG_FILE)
        cm.CONFIG_DIR = self.dir
        cm.CONFIG_FILE = self.dir / "api_keys.json"

    def tearDown(self):
        self.cm.CONFIG_DIR, self.cm.CONFIG_FILE = self._saved
        self._temp.cleanup()

    def _llm(self, vision=True):
        from providers import registry
        return registry.build("openai_compat@ollama", {
            "base_url": "http://127.0.0.1:9/v1",       # nothing listens here
            "model": "some-vl-model", "vision": vision})

    def test_an_unreachable_server_is_not_an_answer(self):
        llm = self._llm()
        self.assertIsNone(llm.can_see(timeout=0.4))

    def test_a_failed_probe_keeps_the_stored_decision(self):
        llm = self._llm(vision=True)
        saved = []
        self.assertTrue(llm.ensure_vision_known(save=saved.append))
        self.assertEqual(saved, [], "nothing was learned, so nothing is written")

    def test_a_failed_probe_does_not_remove_vision_from_the_session(self):
        llm = self._llm(vision=True)
        llm.ensure_vision_known()
        self.assertTrue(llm.caps["vision"], "the tools stay available")

    def test_only_a_refusal_of_the_image_counts_as_cannot_see(self):
        from providers import llm_openai as mod

        class Response:
            def __init__(self, code, text=""):
                self.status_code, self.text = code, text

        class HTTPError(Exception):
            def __init__(self, code, text=""):
                self.response = Response(code, text)

        self.assertTrue(mod._refused_the_image(HTTPError(400, "this model does not support image input")))
        self.assertTrue(mod._refused_the_image(HTTPError(422, "invalid content: multimodal")))
        self.assertFalse(mod._refused_the_image(HTTPError(400, "bad temperature")))
        self.assertFalse(mod._refused_the_image(HTTPError(404, "model not found")))
        self.assertFalse(mod._refused_the_image(HTTPError(503, "starting up")))
        self.assertFalse(mod._refused_the_image(ConnectionRefusedError()))


class AppResolutionTests(unittest.TestCase):
    """An error message is not an app.

    Measured: on a machine with no default browser, `xdg-mime query default`
    exits 0 and prints "No default applications for “x-scheme-handler/http”".
    That whole sentence became the target, so "open the browser" reported success
    and tried to launch an application called `http”`.
    """

    def test_an_error_sentence_is_not_a_handler(self):
        from core.app_resolver import _handler_from
        for line in ("No default applications for “x-scheme-handler/http”",
                     "No such schema",
                     "Error: nothing registered",
                     "unknown",
                     "",
                     " "):
            self.assertIsNone(_handler_from(line), line)

    def test_a_real_handler_is_read_from_either_tool(self):
        from core.app_resolver import _handler_from
        self.assertEqual(_handler_from("google-chrome.desktop"), "google-chrome.desktop")
        self.assertEqual(_handler_from("x-scheme-handler/http: firefox.desktop"),
                         "firefox.desktop")
        self.assertEqual(_handler_from('"brave-browser.desktop"'), "brave-browser.desktop")

    def test_a_resolution_never_targets_prose(self):
        from core.app_resolver import resolve, Backends
        backends = Backends(
            scheme_handler=lambda _scheme: "No default applications for “x-scheme-handler/http”",
            installed=lambda: [],
            running_labels=lambda: [],
            is_directory=lambda _target: False)
        result = resolve("browser", backends=backends)
        self.assertNotEqual(result.status, "resolved")
        self.assertNotIn("No default", result.target or "")


if __name__ == "__main__":
    unittest.main()
