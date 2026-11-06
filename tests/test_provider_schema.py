"""tests/test_provider_schema.py — the exact list the provider is handed.

The previous contract test compared a handler with its own schema. It never asked
whether the provider would *accept* the schema, and that is a different question with a
much worse answer.

Five bridge plugins declared `"required": ["action"]` and declared no `action` property,
because the handler reads it out of the call rather than out of the schema. Google answers
that with

    APIError: 1007 ... function_declarations[40].parameters.required[0]:
    property is not defined

and closes the session. The fault is in one field of one tool, but the cost is the whole
assistant: it cannot connect at all. The activity log then said "API key invalid" because
1007 was read as a key error, so the owner spent an evening pasting a key that was fine.

Two things are tested here, and they are deliberately separate:

  1. What this build sends is valid. Every declaration the model is given, from every
     source, may only require what it declares, and every property must carry a type the
     provider knows.
  2. If a future plugin sends something invalid anyway, `sanitize_declarations` repairs it
     and says so, and a rejected tool list is never reported as a bad key.

The second exists because the first is a promise about code that has not been written yet.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TYPE_NAMES = {"STRING", "NUMBER", "INTEGER", "BOOLEAN", "ARRAY", "OBJECT"}


def declared_sources() -> dict[str, list[dict]]:
    """Every declaration, grouped by where it comes from.

    Labelled by source so a failure says which loader to open. A source that cannot be
    read is a failure, not a skip: a test that quietly checks nothing is worse than none.
    """
    from core.action_loader import discover_actions
    from core.plugin_loader import discover_plugins

    actions = discover_actions(ROOT / "actions", logger=lambda _m: None)
    plugins = discover_plugins(ROOT / "plugins", core_tool_names=set(),
                              logger=lambda _m: None)
    return {
        "actions/": actions.get_tool_declarations(),
        "plugins/": plugins.get_tool_declarations(),
        "main.py": inline_declarations(),
    }


def inline_declarations() -> list[dict]:
    """TOOL_DECLARATIONS from main.py, read as data.

    main.py is never imported by a test — it starts a GUI and installs crash hooks. The
    literal is read from the source instead, which is also why a value that is not a
    constant fails here rather than silently disappearing from the check.
    """
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    for node in ast.parse(source).body:
        targets = [getattr(t, "id", "") for t in getattr(node, "targets", [])]
        if "TOOL_DECLARATIONS" in targets:
            return list(ast.literal_eval(node.value))
    raise AssertionError("TOOL_DECLARATIONS is not in main.py any more — fix this test")


class TheListTheProviderReceivesTests(unittest.TestCase):
    def test_every_source_declares_something(self):
        # An empty group would make every test below pass without checking anything.
        for source, decls in declared_sources().items():
            self.assertTrue(decls, f"{source} produced no declarations")

    def test_nothing_is_required_that_is_not_declared(self):
        # This is the 1007. It is one line of the provider's rules and it cost a session.
        offenders = []
        for source, decls in declared_sources().items():
            for decl in decls:
                params = decl.get("parameters") or {}
                props = params.get("properties") or {}
                for key in params.get("required") or []:
                    if key not in props:
                        offenders.append(f"{source}{decl.get('name')}: requires "
                                         f"'{key}', declares {sorted(props)}")
        self.assertEqual(offenders, [],
                         "the provider rejects the whole tool list for one of these:\n"
                         + "\n".join(offenders))

    def test_every_property_has_a_type_the_provider_knows(self):
        offenders = []
        for source, decls in declared_sources().items():
            for decl in decls:
                props = (decl.get("parameters") or {}).get("properties") or {}
                for key, spec in props.items():
                    kind = str((spec or {}).get("type") or "").upper()
                    if kind not in TYPE_NAMES:
                        offenders.append(f"{source}{decl.get('name')}.{key}: "
                                         f"type {spec.get('type')!r}")
        self.assertEqual(offenders, [], "unknown parameter types:\n" + "\n".join(offenders))

    def test_every_declaration_has_a_name_and_a_description(self):
        for source, decls in declared_sources().items():
            for decl in decls:
                self.assertTrue(str(decl.get("name") or "").strip(), f"{source}: no name")
                self.assertTrue(str(decl.get("description") or "").strip(),
                                f"{decl.get('name')}: no description — the model cannot "
                                f"know when to use it")

    def test_the_bridge_tools_can_say_which_action_they_want(self):
        # These five are the ones that broke. They are named explicitly so the
        # declaration is checked even if the loader stops returning them for some other
        # reason, which would otherwise turn this into a silent pass.
        from core.plugin_loader import discover_plugins
        plugins = discover_plugins(ROOT / "plugins", core_tool_names=set(),
                                   logger=lambda _m: None)
        found = {decl["name"]: decl for decl in plugins.get_tool_declarations()}
        for name in ("rea_bridge", "hyperframes_bridge", "hypit_bridge",
                     "hindsight_bridge", "voicestudio_bridge"):
            self.assertIn(name, found, f"{name} is no longer loaded — check why")
            props = found[name]["parameters"]["properties"]
            self.assertIn("action", props, f"{name} requires 'action' — declare it")
            self.assertEqual(props["action"]["type"], "STRING")

    def test_a_repaired_list_is_the_same_list(self):
        # The sanitiser runs on every start. On a correct build it must change nothing,
        # or it is hiding a fault it should be reporting.
        from core.action_loader import sanitize_declarations
        for source, decls in declared_sources().items():
            clean, repairs = sanitize_declarations(decls)
            self.assertEqual(repairs, [], f"{source}: {repairs}")
            self.assertEqual(clean, decls, f"{source} was changed by the repair pass")


class TheRepairPassTests(unittest.TestCase):
    """A malformed declaration must cost one tool's argument list, not the session."""

    def test_a_required_key_with_no_property_is_dropped_and_reported(self):
        from core.action_loader import sanitize_declarations
        decls = [{"name": "broken", "parameters": {
            "type": "OBJECT", "properties": {"command": {"type": "STRING"}},
            "required": ["action"]}}]
        clean, repairs = sanitize_declarations(decls)
        self.assertEqual(clean[0]["parameters"]["required"], [])
        self.assertEqual(clean[0]["parameters"]["properties"],
                         {"command": {"type": "STRING"}})
        self.assertTrue(any("action" in line and "broken" in line for line in repairs),
                        repairs)

    def test_a_property_with_no_type_is_given_one_and_reported(self):
        from core.action_loader import sanitize_declarations
        decls = [{"name": "untyped", "parameters": {
            "type": "OBJECT", "properties": {"text": {}}, "required": ["text"]}}]
        clean, repairs = sanitize_declarations(decls)
        self.assertEqual(clean[0]["parameters"]["properties"]["text"]["type"], "STRING")
        self.assertEqual(clean[0]["parameters"]["required"], ["text"])
        self.assertTrue(any("untyped.text" in line for line in repairs), repairs)

    def test_a_type_the_provider_does_not_know_is_replaced_and_reported(self):
        from core.action_loader import sanitize_declarations
        decls = [{"name": "odd", "parameters": {
            "type": "OBJECT", "properties": {"n": {"type": "FLOAT"}}}}]
        clean, repairs = sanitize_declarations(decls)
        self.assertEqual(clean[0]["parameters"]["properties"]["n"]["type"], "STRING")
        self.assertTrue(any("FLOAT" in line for line in repairs), repairs)

    def test_a_tool_with_no_parameters_is_left_alone(self):
        from core.action_loader import sanitize_declarations
        decls = [{"name": "bare", "description": "no arguments"}]
        clean, repairs = sanitize_declarations(decls)
        self.assertEqual(clean, decls)
        self.assertEqual(repairs, [])

    def test_the_original_is_not_modified(self):
        # The declaration list is shared with the prompt builder. Repairing it in place
        # would make the model read one thing and the provider receive another.
        from core.action_loader import sanitize_declarations
        decls = [{"name": "broken", "parameters": {
            "type": "OBJECT", "properties": {}, "required": ["action"]}}]
        sanitize_declarations(decls)
        self.assertEqual(decls[0]["parameters"]["required"], ["action"])


class ARejectedToolListIsNotABadKeyTests(unittest.TestCase):
    """The owner's own log line, kept as the test fixture."""

    LOG_LINE = ("APIError: 1007 None.  *[BidiGenerateContentRequest.setup.tools][0]"
                ".function_declarations[40].parameters.required[0]: property is not "
                "defined*  Bid.")

    def test_the_real_failure_is_read_as_a_schema_fault(self):
        from core import close_codes
        self.assertEqual(close_codes.kind(self.LOG_LINE, 1007), "schema")

    def test_the_broken_declaration_can_be_named(self):
        from core import close_codes
        self.assertEqual(close_codes.rejected_declaration(self.LOG_LINE), 40)

    def test_the_explanation_does_not_tell_the_owner_to_re_enter_his_key(self):
        from core import close_codes
        said = close_codes.explain(self.LOG_LINE, 1007)
        self.assertIn("schema", said)
        self.assertIn("not your API key", said)
        self.assertNotIn("re-enter", said)

    def test_a_wrong_key_is_still_read_as_a_wrong_key(self):
        from core import close_codes
        for text in ("API key not valid. Please pass a valid API key.",
                     "400 API_KEY_INVALID",
                     "Incorrect API key provided"):
            self.assertEqual(close_codes.kind(text, 1007), "key", text)

    def test_the_code_alone_never_decides(self):
        # 1007 with nothing else said is not evidence of a key problem. This is the
        # exact test that would have caught the bug that prompted this file.
        from core import close_codes
        self.assertNotEqual(close_codes.kind("1007 None.", 1007), "key")

    def test_quota_and_network_are_told_apart(self):
        from core import close_codes
        self.assertEqual(close_codes.kind("429 RESOURCE_EXHAUSTED: quota", 1007), "quota")
        self.assertEqual(close_codes.kind("connection timed out", 1007), "network")

    def test_an_unknown_reason_is_quoted_not_guessed(self):
        from core import close_codes
        said = close_codes.explain("something new happened", 1007)
        self.assertIn("something new happened", said)
        self.assertNotIn("API key", said)


if __name__ == "__main__":
    unittest.main()
