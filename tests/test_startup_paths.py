"""tests/test_startup_paths.py — the things that stop the app starting at all.

main.py cannot be imported in this environment: it pulls sounddevice and a live
audio stack on the first line. So the functions that decide whether a session can
be opened are extracted from the source with `ast` and executed here against
temporary config files. That is a real behavioural test of the real source, not a
search for a string — the only thing missing is the module around them.

Each test here comes from a defect found by tracing the start-up path of an
install configured for a provider and no Gemini key, which is now a first-class
way to run and was the least-exercised path in the tree.
"""

from __future__ import annotations

import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SOURCE = (ROOT / "main.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def extract(*names: str, extra_globals: dict | None = None) -> dict:
    """Build a namespace containing only the named top-level functions."""
    wanted = [node for node in TREE.body
              if isinstance(node, ast.FunctionDef) and node.name in names]
    missing = set(names) - {node.name for node in wanted}
    assert not missing, f"not found in main.py: {sorted(missing)}"
    module = ast.Module(body=wanted, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {"json": json}
    namespace.update(extra_globals or {})
    exec(compile(module, "main.py (extracted)", "exec"), namespace)
    return namespace


class ApiKeyTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.path = Path(self._temp.name) / "api_keys.json"
        self.ns = extract("_get_api_key", "_has_gemini_key",
                          extra_globals={"API_CONFIG_PATH": self.path})

    def tearDown(self):
        self._temp.cleanup()

    def test_a_present_key_is_returned_without_whitespace(self):
        self.path.write_text(json.dumps({"gemini_api_key": "  AIza-key  "}), "utf-8")
        self.assertEqual(self.ns["_get_api_key"](), "AIza-key")
        self.assertTrue(self.ns["_has_gemini_key"]())

    def test_no_key_is_an_empty_string_and_not_a_key_error(self):
        # The old body was `return json.load(f)["gemini_api_key"]`, so an install
        # configured for a provider and no Gemini key raised KeyError from inside
        # the reconnect loop — where every exception becomes a retry.
        self.path.write_text(json.dumps({"os_system": "windows"}), "utf-8")
        self.assertEqual(self.ns["_get_api_key"](), "")
        self.assertFalse(self.ns["_has_gemini_key"]())

    def test_a_missing_file_is_an_empty_string(self):
        self.assertEqual(self.ns["_get_api_key"](), "")
        self.assertFalse(self.ns["_has_gemini_key"]())

    def test_a_damaged_file_is_an_empty_string(self):
        self.path.write_text("{not json", "utf-8")
        self.assertEqual(self.ns["_get_api_key"](), "")

    def test_a_json_list_is_an_empty_string(self):
        self.path.write_text("[1, 2, 3]", "utf-8")
        self.assertEqual(self.ns["_get_api_key"](), "")


class PromptFallbackTests(unittest.TestCase):
    def test_the_fallback_prompt_is_named_after_this_assistant(self):
        # It said "You are JARVIS, Tony Stark's AI assistant" — the upstream
        # project's name, in the one place that speaks the persona when the
        # prompt file is missing.
        from core import identity
        with tempfile.TemporaryDirectory() as temp:
            ns = extract("_load_system_prompt",
                         extra_globals={"PROMPT_PATH": Path(temp) / "missing.txt",
                                        "identity": identity})
            text = ns["_load_system_prompt"]()
        self.assertIn(identity.NAME, text)
        self.assertNotIn("JARVIS", text)

    def test_the_real_prompt_file_still_wins(self):
        from core import identity
        ns = extract("_load_system_prompt",
                     extra_globals={"PROMPT_PATH": ROOT / "core" / "prompt.txt",
                                    "identity": identity})
        self.assertEqual(ns["_load_system_prompt"](), (ROOT / "core" / "prompt.txt")
                         .read_text(encoding="utf-8"))


class PipelineFallbackIsHonestTests(unittest.TestCase):
    """A fallback that does not exist is worse than no fallback.

    With provider mode configured, a broken engine, and no Gemini key, the loop
    used to ask Gemini Live with an empty key, take an auth error, and answer it
    with the setup screen — repeatedly — while the real fault was a provider that
    would not build.
    """

    def test_the_loop_refuses_to_open_a_session_it_cannot_authenticate(self):
        self.assertIn('self._engine_mode() == "pipeline"', SOURCE)
        self.assertIn("not _has_gemini_key()", SOURCE)
        # and it waits rather than spinning
        start = SOURCE.index("not _has_gemini_key()")
        window = SOURCE[start:start + 600]
        self.assertIn("await asyncio.sleep", window)

    def test_the_reason_comes_back_from_the_engine_resolution(self):
        self.assertIn("self._pipeline_error = reason", SOURCE)
        self.assertIn('self._pipeline_error = ""', SOURCE)

    def test_the_message_depends_on_whether_a_key_exists(self):
        start = SOURCE.index("def _resolve_engine_caps")
        body = SOURCE[start:start + 4000]
        self.assertIn("if _has_gemini_key():", body)
        self.assertIn("ENGINE & PROVIDERS", body)

    def test_a_failure_is_reported_once_not_once_per_attempt(self):
        start = SOURCE.index("def _resolve_engine_caps")
        body = SOURCE[start:start + 4000]
        self.assertIn("_pipeline_reported", body)


if __name__ == "__main__":
    unittest.main()
