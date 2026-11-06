"""tests/test_tool_contract.py — what the model is told against what the code does.

Every tool is two halves that live in different places: a declaration the model
reads, and a handler that runs. Nothing checks that they agree, and when they stop
agreeing the tool does not fail loudly — it runs with defaults the model could not
override. That is how `drag` came to exist but never work, and how asking to
append to a file replaced it instead.

The invariant this file guards: every key a handler reads out of `parameters` is
declared in that tool's schema, so the model can actually say it.

Two reads are allowed to be undeclared and are listed below with the reason. Both
are fallbacks for a key that *is* declared, or for a message — not the only way to
reach a behaviour.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CTX_KEYS = {"player", "speak", "response", "session_memory"}

# (tool, key) pairs a handler may read without declaring, with why.
ALLOWED_UNDECLARED = {
    ("code_helper", "instruction"): "alias for the declared 'description'",
    ("desktop_control", "task"): "only used to name the action in an error message",
}

# Action modules whose import needs an optional third-party package. They are
# checked the same way as soon as that package is present; the skip is explicit
# rather than silent.
OPTIONAL_IMPORTS = {"browser_control": "playwright"}


def action_modules():
    out = []
    for path in sorted((ROOT / "actions").glob("*.py")):
        if path.stem.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"actions.{path.stem}")
        except ImportError as exc:
            if path.stem in OPTIONAL_IMPORTS:
                continue
            raise
        if isinstance(getattr(mod, "TOOL", None), dict):
            out.append(mod)
    return out


def keys_read_from_parameters(fn) -> set[str]:
    """String keys a handler pulls out of its `parameters` argument."""
    try:
        src = inspect.getsource(fn)
    except (OSError, TypeError):
        return set()
    tree = ast.parse(ast.unparse(ast.parse(src)))
    aliases = {"parameters"}
    for node in ast.walk(tree):
        # `params = parameters or {}` is the house style, one level deep.
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and "parameters" in ast.unparse(node.value)):
            aliases.add(node.targets[0].id)
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            recv = ast.unparse(node.func.value)
            if (node.func.attr in ("get", "pop") and node.args
                    and (recv.split(".")[0] in aliases or "parameters" in recv)
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                found.add(node.args[0].value)
        if isinstance(node, ast.Subscript) and any(
                isinstance(s, ast.Constant) and isinstance(s.value, str)
                for s in [node.slice]):
            recv = ast.unparse(node.value)
            if recv.split(".")[0] in aliases or "parameters" in recv:
                found.add(node.slice.value)
    return found


class ToolSchemaAgreementTests(unittest.TestCase):
    def test_every_helper_can_be_called_the_way_the_loader_calls_it(self):
        # core.action_loader._call_handler calls fn(parameters=..., **ctx). A
        # handler that does not take `parameters` under that exact name raises
        # TypeError on every call — a tool that is advertised and unusable.
        for mod in action_modules():
            tool = mod.TOOL
            sig = inspect.signature(tool["handler"])
            has_var_kw = any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values())
            self.assertTrue(has_var_kw or "parameters" in sig.parameters,
                            f"{tool['name']}: handler cannot accept parameters=")

    def test_no_handler_needs_an_argument_the_loader_never_passes(self):
        for mod in action_modules():
            tool = mod.TOOL
            sig = inspect.signature(tool["handler"])
            for p in sig.parameters.values():
                if p.name == "parameters" or p.kind in (p.VAR_KEYWORD, p.VAR_POSITIONAL):
                    continue
                if p.default is p.empty:
                    self.assertIn(p.name, CTX_KEYS,
                                  f"{tool['name']}: '{p.name}' has no default and "
                                  f"is not one of {sorted(CTX_KEYS)}")

    def test_the_schema_declares_everything_the_handler_reads(self):
        offenders = []
        for mod in action_modules():
            tool = mod.TOOL
            props = set((tool.get("parameters") or {}).get("properties") or {})
            for key in sorted(keys_read_from_parameters(tool["handler"])):
                if key in props or (tool["name"], key) in ALLOWED_UNDECLARED:
                    continue
                offenders.append(f"{tool['name']}: reads '{key}', schema declares "
                                 f"{sorted(props)}")
        self.assertEqual(offenders, [],
                         "the model cannot pass a parameter it is not told about:\n"
                         + "\n".join(offenders))

    def test_the_schema_does_not_require_a_parameter_it_never_declares(self):
        for mod in action_modules():
            tool = mod.TOOL
            params = tool.get("parameters") or {}
            props = set(params.get("properties") or {})
            for name in params.get("required") or []:
                self.assertIn(name, props, f"{tool['name']}: required '{name}' undeclared")

    def test_every_callable_action_is_discoverable(self):
        # A TOOL dict the loader rejects is a tool the assistant cannot use, and
        # the loader only logs it. This fails the build instead.
        from core.action_loader import discover_actions
        registry = discover_actions(ROOT / "actions", logger=lambda _m: None)
        names = registry.names()
        for mod in action_modules():
            self.assertIn(mod.TOOL["name"], names,
                          f"{mod.TOOL['name']} is not discoverable")


class PolicyKnowsTheRealToolNamesTests(unittest.TestCase):
    """A name in the policy tables is a claim about the app.

    The tables had drifted: `screen_processor` was guarded (the screen tool is
    `screen_process`), so the main capture tool fell through to "unclassified"
    and the sensor tier's grant never applied to it; `system_monitor` was listed
    as a read-only tool and belongs to no tool at all.
    """

    # Not tool names: two aliases kept for plugins, and the custom_jars tool that
    # lives outside actions/.
    ALLOWED_ALIASES = {"camera", "screen_capture", "custom_jarvis"}

    def real_tool_names(self) -> set[str]:
        import ast
        from core.action_loader import discover_actions
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        names = set()
        for node in ast.parse(source).body:
            if isinstance(node, ast.Assign) and any(
                    getattr(t, "id", "") == "TOOL_DECLARATIONS" for t in node.targets):
                for elt in getattr(node.value, "elts", []):
                    for k, v in zip(elt.keys, elt.values):
                        if getattr(k, "value", "") == "name" and isinstance(v, ast.Constant):
                            names.add(v.value)
        names |= discover_actions(ROOT / "actions", logger=lambda _m: None).names()
        # Plugins are tools too: they reach the model through
        # `plugin_registry.get_tool_declarations()`, so a plugin named in the risk
        # tables is a real name, not a ghost. Leaving them out made twelve correct
        # rows look like drift.
        from core.plugin_loader import discover_plugins
        plugins = discover_plugins(ROOT / "plugins", core_tool_names=set(),
                                   logger=lambda _m: None)
        names |= {row["name"] for row in plugins.list_for_ui() if row["valid"]}
        # Modules that need an optional package cannot be imported here, so their
        # declared name is read from the source instead of being skipped.
        for stem in OPTIONAL_IMPORTS:
            path = ROOT / "actions" / f"{stem}.py"
            if not path.exists():
                continue
            for node in ast.parse(path.read_text(encoding="utf-8")).body:
                if isinstance(node, ast.Assign) and any(
                        getattr(t, "id", "") == "TOOL" for t in node.targets):
                    if isinstance(node.value, ast.Dict):
                        for k, v in zip(node.value.keys, node.value.values):
                            if getattr(k, "value", "") == "name" and isinstance(v, ast.Constant):
                                names.add(v.value)
        return names

    def test_every_classified_name_is_a_tool_that_exists(self):
        from core import policy
        listed = (policy.OBSERVE_TOOLS | policy.ROUTINE_TOOLS
                  | policy.GUARDED_TOOLS | policy.SENSOR_TOOLS | policy.BYPASS_TOOLS)
        ghosts = sorted(listed - self.real_tool_names() - self.ALLOWED_ALIASES)
        self.assertEqual(ghosts, [], "these are classified and do not exist")

    def test_the_screen_tool_is_a_sensor(self):
        from core import policy
        self.assertIs(policy.decide("screen_process", {}).tier, policy.Tier.SENSOR)

    def test_stopping_a_capture_never_needs_approval(self):
        from core import policy
        self.assertTrue(policy.decide("close_camera", {}).allow)

    def test_undo_never_needs_approval(self):
        from core import policy
        self.assertTrue(policy.decide("undo", {}).allow)

    def test_memory_writes_are_gated_and_say_why(self):
        from core import policy
        decision = policy.decide("save_memory", {"key": "k", "value": "v"})
        self.assertFalse(decision.allow)
        self.assertIn("permanent", decision.reason)


class DragAndAppendTests(unittest.TestCase):
    """The three concrete holes this pass found, checked at the call site."""

    def test_drag_has_a_box_to_drag(self):
        mod = importlib.import_module("actions.computer_control")
        props = mod.TOOL["parameters"]["properties"]
        for key in ("x1", "y1", "x2", "y2"):
            self.assertIn(key, props, "action='drag' reads this and the model needs it")
        self.assertIn("drag", props["action"]["description"])

    def test_write_can_append(self):
        mod = importlib.import_module("actions.file_controller")
        props = mod.TOOL["parameters"]["properties"]
        self.assertIn("append", props)
        self.assertEqual(props["append"]["type"], "BOOLEAN")

    def test_weather_can_be_asked_about_another_day(self):
        mod = importlib.import_module("actions.weather_report")
        self.assertIn("time", mod.TOOL["parameters"]["properties"])

    def test_typing_can_press_enter(self):
        mod = importlib.import_module("actions.computer_settings")
        self.assertIn("press_enter", mod.TOOL["parameters"]["properties"])



class ActionDiscoverySurvivesTests(unittest.TestCase):
    """Loading must not be able to take the app down, and must not go quiet.

    Two failure modes met in the same function. `traceback.print_exc()` writes to
    sys.stderr, and under pythonw — the launcher that shows no console — that is
    None, so the error handler raised and discovery died with it. And the error
    itself only ever reached a console, so a capability could disappear from the
    session without the user being told.
    """

    def setUp(self):
        import tempfile
        self._temp = tempfile.TemporaryDirectory()
        self.dir = Path(self._temp.name)
        (self.dir / "broken.py").write_text(
            "raise ImportError('needs a package that is not installed')\n", encoding="utf-8")
        (self.dir / "crasher.py").write_text(
            "def _handler(parameters=None, **_kw):\n"
            "    raise RuntimeError('handler exploded')\n"
            "TOOL = {'name': 'crasher', 'description': 'crash on purpose',\n"
            "        'parameters': {'type': 'OBJECT', 'properties': {}},\n"
            "        'handler': _handler}\n", encoding="utf-8")
        (self.dir / "fine.py").write_text(
            "def _handler(parameters=None, **_kw):\n"
            "    return 'ok'\n"
            "TOOL = {'name': 'fine', 'description': 'works',\n"
            "        'parameters': {'type': 'OBJECT', 'properties': {}},\n"
            "        'handler': _handler}\n", encoding="utf-8")

    def tearDown(self):
        self._temp.cleanup()

    def _discover(self, logger):
        from core.action_loader import discover_actions
        return discover_actions(self.dir, logger=logger)

    def test_a_broken_file_does_not_take_discovery_down(self):
        lines = []
        registry = self._discover(lines.append)
        self.assertIn("fine", registry.names())
        self.assertNotIn("broken", registry.names())
        self.assertTrue(any("unavailable" in line and "broken" in line for line in lines),
                        lines)

    def test_discovery_works_with_no_console_at_all(self):
        # pythonw: sys.stderr is None. This used to raise AttributeError here.
        import sys
        saved = sys.stderr
        sys.stderr = None
        try:
            registry = self._discover(lambda _m: None)
        finally:
            sys.stderr = saved
        self.assertIn("fine", registry.names())

    def test_missing_capabilities_can_be_named(self):
        registry = self._discover(lambda _m: None)
        missing = registry.failures()
        self.assertIn("broken", missing)
        self.assertIn("not installed", missing["broken"])
        self.assertNotIn("fine", missing)

    def test_a_crashing_handler_is_reported_as_a_result_not_an_exception(self):
        registry = self._discover(lambda _m: None)
        result = registry.run("crasher", {})
        self.assertIn("failed", result.lower())
        self.assertIn("handler exploded", result)

    def test_an_unknown_action_is_refused_in_words(self):
        registry = self._discover(lambda _m: None)
        self.assertIn("not available", registry.run("no_such_tool", {}))


if __name__ == "__main__":
    unittest.main()
