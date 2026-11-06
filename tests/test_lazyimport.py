"""tests/test_lazyimport.py — deferred imports on the launch path.

WHY THIS FILE EXISTS
    Launch time is not a feeling, it is an import graph. `core/lazyimport.py` had
    no tests, and the two things it must promise are exactly the two things a
    refactor breaks quietly:

      1. A `LazyModule` really defers. If it accidentally resolves at
         construction, everything still works — it is just slow again, and
         nothing fails.
      2. A deferred name still behaves like the module. If it does not, the app
         raises `NameError` at the moment the user asks for something.

    So the tests below check behaviour (a probe module that records whether it
    was executed) and the boot path itself (an AST scan asserting that no
    `actions/` or `plugins/` file imports a heavy library at module scope, which
    is what made a launch slow in the first place).

    The AST layer is deliberately not a timing test: timing measured on a build
    server tells you about that machine. "This module does not import pyautogui
    at module scope" is true everywhere.
"""

from __future__ import annotations

import ast
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.lazyimport import LazyModule, installed

# Libraries whose only job is to cost time at launch. If one of these is imported
# at module scope by a file the boot path executes, the launch pays for it whether
# or not the session ever needs it.
HEAVY = {
    "pyautogui",
    "playwright",
    "requests",
    "bs4",
    "cv2",
    "PIL",
    "pandas",
    "docx",
    "openpyxl",
    "youtube_transcript_api",
    "sounddevice",
    "pyperclip",
    "numpy",
}

# (file, module) pairs that stay eager, each for a reason worth writing down.
ALLOWED_EAGER = {
    # main.py imports numpy for audio and runs before any action is read, so this
    # file reuses what is already in memory rather than deferring it.
    ("actions/screen_processor.py", "numpy"),
    # The RAM meter is built during window construction; psutil has to be there.
    ("actions/system_monitor.py", "psutil"),
}


def module_scope_imports(path: Path) -> set[str]:
    """Top-level third-party names imported when this file is executed.

    Imports inside a function do not run at import time, so they are invisible
    here — which is the entire point of the check. Imports inside a module-level
    `try:` or a class body DO run, so they count.
    """
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    found: set[str] = set()

    def type_checking_only(node: ast.If) -> bool:
        """True for `if TYPE_CHECKING:` / `if False:` guards.

        Those bodies are never executed at runtime — `TYPE_CHECKING` is False —
        so an import inside one costs nothing at launch. browser_control.py uses
        exactly this to keep its playwright type hints while importing nothing.
        """
        test = node.test
        names = {n.id for n in ast.walk(test) if isinstance(n, ast.Name)}
        names |= {n.attr for n in ast.walk(test) if isinstance(n, ast.Attribute)}
        if "TYPE_CHECKING" in names:
            return True
        return isinstance(test, ast.Constant) and not test.value

    def collect(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                for alias in child.names:
                    if isinstance(child, ast.Import):
                        found.add(alias.name.split(".")[0])
                    elif child.module:
                        found.add(child.module.split(".")[0])
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue          # a function body is not the import path
            elif isinstance(child, ast.If) and type_checking_only(child):
                continue          # never executed at runtime
            else:
                collect(child)

    collect(tree)
    return found


class ProbeModuleTests(unittest.TestCase):
    """A real module on disk, so 'was it executed?' can be answered exactly."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.dir = Path(self._temp.name)
        self.marker = self.dir / "was_executed"
        (self.dir / "probe_mod_ultron.py").write_text(
            textwrap.dedent(
                f"""
                from pathlib import Path

                Path(r"{self.marker}").write_text("yes", encoding="utf-8")

                VALUE = 41
                NAME = "probe"

                def double(x):
                    return x * 2

                class Thing:
                    pass
                """
            ),
            encoding="utf-8",
        )
        sys.path.insert(0, str(self.dir))
        sys.modules.pop("probe_mod_ultron", None)

    def tearDown(self):
        sys.modules.pop("probe_mod_ultron", None)
        if str(self.dir) in sys.path:
            sys.path.remove(str(self.dir))
        self._temp.cleanup()

    def test_construction_does_not_import(self):
        LazyModule("probe_mod_ultron")
        self.assertFalse(self.marker.exists(), "constructing the proxy executed the module")
        self.assertNotIn("probe_mod_ultron", sys.modules)

    def test_repr_distinguishes_loaded_from_not_loaded(self):
        proxy = LazyModule("probe_mod_ultron")
        self.assertIn("not yet imported", repr(proxy))
        _ = proxy.VALUE
        self.assertIn("loaded", repr(proxy))

    def test_first_attribute_access_imports_once(self):
        proxy = LazyModule("probe_mod_ultron")
        self.assertEqual(proxy.VALUE, 41)
        self.assertTrue(self.marker.exists())
        # Second access must not re-execute the module.
        self.marker.unlink()
        _ = proxy.VALUE
        self.assertEqual(proxy.VALUE, 41)
        self.assertFalse(self.marker.exists())

    def test_functions_and_classes_are_reachable(self):
        proxy = LazyModule("probe_mod_ultron")
        self.assertEqual(proxy.double(5), 10)
        self.assertIsInstance(proxy.Thing(), proxy.Thing)

    def test_attribute_assignment_lands_on_the_module(self):
        proxy = LazyModule("probe_mod_ultron")
        proxy.VALUE = 7
        self.assertEqual(sys.modules["probe_mod_ultron"].VALUE, 7)

    def test_dir_lists_the_real_module(self):
        self.assertIn("double", dir(LazyModule("probe_mod_ultron")))

    def test_configure_hook_runs_on_every_access(self):
        # pyautogui's PAUSE/FAILSAFE are module-global: whoever is about to use
        # the module has to set them immediately before the call, which is why
        # the hook cannot be a once-only callback.
        calls = []
        proxy = LazyModule("probe_mod_ultron", lambda module: calls.append(module.VALUE))
        for _ in range(3):
            _ = proxy.VALUE
        self.assertEqual(len(calls), 3)

    def test_a_missing_module_fails_on_use_not_on_construction(self):
        proxy = LazyModule("probe_mod_ultron_absent")
        with self.assertRaises(ModuleNotFoundError):
            _ = proxy.anything

    def test_installed_answers_without_importing(self):
        self.assertTrue(installed("probe_mod_ultron"))
        self.assertNotIn("probe_mod_ultron", sys.modules)
        self.assertFalse(installed("probe_mod_ultron_absent"))
        self.assertTrue(installed("json"))
        self.assertFalse(installed(""))
        # Dotted names whose parent does not exist must answer False, not raise.
        self.assertFalse(installed("probe_mod_ultron_absent.child"))


class BootPathTests(unittest.TestCase):
    """The launch path, checked structurally."""

    def test_actions_and_plugins_do_not_import_heavy_libraries_at_module_scope(self):
        offenders = []
        for folder in ("actions", "plugins"):
            for path in sorted((ROOT / folder).glob("*.py")):
                rel = f"{folder}/{path.name}"
                for name in module_scope_imports(path) & HEAVY:
                    if (rel, name) in ALLOWED_EAGER:
                        continue
                    offenders.append(f"{rel} imports {name} at module scope")
        self.assertEqual(offenders, [], "launch-path imports that are paid on every start")

    def test_main_defers_the_provider_sdk(self):
        # 590 ms of a 795 ms module import was this one package.
        names = module_scope_imports(ROOT / "main.py")
        self.assertNotIn("google", names)
        self.assertNotIn("genai", names)

    def test_main_binds_the_provider_sdk_through_the_proxy(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8-sig")
        self.assertIn('genai = LazyModule("google.genai")', source)
        self.assertIn('types = LazyModule("google.genai.types")', source)
        self.assertIn("_GENAI_INSTALLED", source)

    def test_no_return_annotation_eagerly_imports_a_deferred_module(self):
        # `def f() -> types.X:` evaluates the annotation when the function is
        # defined, i.e. during module import — which would quietly undo the
        # deferral. Quoted annotations do not.
        source = (ROOT / "main.py").read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
        eager = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.returns is not None and isinstance(node.returns, ast.Attribute):
                eager.append(f"line {node.lineno}: {ast.unparse(node.returns)}")
        self.assertEqual(eager, [], "unquoted annotation on a deferred module")

    def test_the_identity_fallback_is_not_a_literal_name(self):
        # A config that fails to parse must not rename the assistant back to a
        # name this build stopped using.
        source = (ROOT / "main.py").read_text(encoding="utf-8-sig")
        self.assertNotIn('self._asst_name = "JARVIS"', source)
        self.assertIn("self._asst_name = identity.NAME", source)

    def test_the_config_file_is_read_with_a_context_manager(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8-sig")
        self.assertNotIn('json.loads(open(API_CONFIG_PATH', source)


if __name__ == "__main__":
    unittest.main()
