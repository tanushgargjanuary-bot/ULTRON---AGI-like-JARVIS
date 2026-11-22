"""Smoke tests for the two seams every tool call and every module passes through.

WHY THIS FILE EXISTS, AND WHY IT RUNS IN THE FAST GATE
    At c57d0e4 `PluginRegistry.run` began reading `rec.declaration`, an attribute
    `PluginRecord` has never had. Every one of the fifteen plugins then answered
    "the plugin failed" while each plugin was fine. The fast gate stayed green and
    the full suite (which was red for other reasons) hid it; the first person to
    notice would have been the owner, by voice.

    Separately, `core/heartbeat.py` imported two names `core/ipc_client.py` does not
    define, so the module could not even be imported, and the only test near it
    skips unless a Rust binary has been built.

    Both are the same shape — a seam nobody exercised — so both are exercised here,
    offline, in a few seconds, with nothing to install.
"""

from __future__ import annotations

import builtins
import json
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent

# The packages whose modules are meant to import on their own. `ui.py` and
# `main.py` are left out on purpose: they start a window and a session.
IMPORT_PACKAGES = ("core", "actions", "plugins", "custom_jarvis", "providers", "memory")


class PluginDispatch(unittest.TestCase):
    """`PluginRegistry.run` must hand a plugin its arguments, typed as declared."""

    def setUp(self):
        from core.plugin_loader import discover_plugins

        self._discover = discover_plugins
        self.temp = tempfile.TemporaryDirectory()
        self.plugins = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def _registry(self, source: str):
        (self.plugins / "probe.py").write_text(source, encoding="utf-8")
        return self._discover(self.plugins, set(), logger=lambda _line: None,
                              force_reload=True)

    def test_run_reaches_the_plugin(self):
        registry = self._registry(
            "PLUGIN = {'name': 'probe_plugin', 'description': 'Use it when testing.', "
            "'parameters': {'type': 'OBJECT', 'properties': {}}}\n"
            "def run(parameters=None): return 'reached'\n")
        self.assertEqual(registry.run("probe_plugin", {}, player=None), "reached")

    def test_arguments_are_coerced_to_the_declared_types(self):
        # A model that sends "3" for an INTEGER and "yes" for a BOOLEAN must not
        # crash the plugin; the declaration is the promise being kept here.
        registry = self._registry(
            "PLUGIN = {'name': 'probe_plugin', 'description': 'Use it when testing.', "
            "'parameters': {'type': 'OBJECT', 'properties': {"
            "'count': {'type': 'INTEGER'}, 'flag': {'type': 'BOOLEAN'}, "
            "'label': {'type': 'STRING'}}}}\n"
            "def run(parameters=None):\n"
            "    p = parameters or {}\n"
            "    return repr((p.get('count'), p.get('flag'), p.get('label')))\n")
        result = registry.run(
            "probe_plugin", {"count": "3", "flag": "yes", "label": 7, "gone": None},
            player=None)
        self.assertEqual(result, repr((3, True, "7")))

    def test_a_plugin_that_raises_is_reported_not_propagated(self):
        registry = self._registry(
            "PLUGIN = {'name': 'probe_plugin', 'description': 'Use it when testing.', "
            "'parameters': {'type': 'OBJECT', 'properties': {}}}\n"
            "def run(parameters=None): raise RuntimeError('boom')\n")
        result = registry.run("probe_plugin", {}, player=None)
        self.assertIn("boom", result)

    def test_every_bundled_plugin_dispatches_without_a_wrapper_error(self):
        """Run all of `plugins/` with no arguments, offline.

        A plugin may refuse an empty request in words. What it may not do is fail
        inside the registry's own wrapper — those failures read "has no attribute"
        or "is not defined" and name the loader, not the plugin.
        """
        def no_network(*_args, **_kwargs):
            raise OSError("network disabled for this test")

        registry = self._discover(ROOT / "plugins", set(), logger=lambda _line: None,
                                  force_reload=True)
        self.assertGreaterEqual(len(registry.names()), 12)
        with mock.patch.object(socket, "create_connection", no_network), \
                mock.patch.object(socket.socket, "connect", no_network), \
                mock.patch.object(socket, "getaddrinfo", no_network), \
                mock.patch.object(builtins, "print"):
            for name in sorted(registry.names()):
                with self.subTest(plugin=name):
                    result = registry.run(name, {}, player=None)
                    self.assertIsInstance(result, str)
                    for marker in ("has no attribute", "is not defined",
                                   "unexpected keyword", "positional argument"):
                        self.assertNotIn(marker, result, f"{name}: {result}")


class ModulesImport(unittest.TestCase):
    """Every module in the runtime packages must at least import."""

    SCRIPT = r'''
import importlib, json, sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
repo_tops = {p.name for p in root.iterdir() if p.is_dir() and (p / "__init__.py").exists()}
repo_tops |= {p.stem for p in root.glob("*.py")}
found = []
for package in sys.argv[2:]:
    for path in sorted((root / package).glob("*.py")):
        # `_name.py` is internal: `core/_smoke_harness.py` is a subprocess entry
        # point that reads sys.argv when imported, which is correct for it.
        if path.name == "__init__.py" or path.name.startswith("_"):
            continue
        name = f"{package}.{path.stem}"
        try:
            importlib.import_module(name)
        except ModuleNotFoundError as error:
            top = (error.name or "").split(".")[0]
            kind = "defect" if top in repo_tops else "skip"
            found.append([name, kind, f"{type(error).__name__}: {error}"])
        except ImportError as error:
            top = (error.name or "").split(".")[0]
            own = "cannot import name" in str(error) and top in repo_tops
            found.append([name, "defect" if own else "skip",
                          f"{type(error).__name__}: {error}"])
        except OSError as error:
            found.append([name, "skip", f"{type(error).__name__}: {error}"])
        except BaseException as error:
            found.append([name, "defect", f"{type(error).__name__}: {error}"])
print("RESULT:" + json.dumps(found))
'''

    def test_every_runtime_module_imports(self):
        proc = subprocess.run(
            [sys.executable, "-c", self.SCRIPT, str(ROOT), *IMPORT_PACKAGES],
            cwd=ROOT, capture_output=True, text=True, timeout=180, check=False,
            env={**__import__("os").environ, "QT_QPA_PLATFORM": "offscreen",
                 "PYTHONDONTWRITEBYTECODE": "1"},
        )
        line = next((row for row in proc.stdout.splitlines()
                     if row.startswith("RESULT:")), None)
        self.assertIsNotNone(line, f"the import probe did not finish: {proc.stderr[-800:]}")
        found = json.loads(line[len("RESULT:"):])
        defects = [f"{name}: {why}" for name, kind, why in found if kind == "defect"]
        self.assertEqual(defects, [], "modules that cannot be imported (a name another "
                                      "repo module expects is missing, or a bug runs at "
                                      "import time)")


if __name__ == "__main__":
    unittest.main()
