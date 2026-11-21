"""The fast gate runs the checks the docs say it runs.

`scripts/fast_verify.py` is the gate every branch push passes through. It ran policy,
README, runner and stress groups and nothing that called a tool, so a fault on the one
path every tool takes (`core/plugin_loader.py`, a wrong attribute name) failed 29 tests in
the full suite and not one check in the fast gate, which stayed green for it.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import fast_verify  # noqa: E402


class TheGroups(unittest.TestCase):
    def groups(self):
        recorded = []

        def record(name, command, *, root=None, env=None, timeout=None):
            recorded.append((name, command, timeout))
            return True

        with mock.patch.object(fast_verify, "run_check", record):
            results = fast_verify.run_fast_checks({})
        self.assertTrue(all(results))
        return recorded

    def test_the_dispatch_smoke_group_is_part_of_the_gate(self):
        recorded = self.groups()
        smoke = [entry for entry in recorded if "test_dispatch_smoke.py" in entry[1]]
        self.assertEqual(len(smoke), 1, [name for name, _c, _t in recorded])

    def test_every_test_module_a_group_names_exists(self):
        for name, command, _timeout in self.groups():
            for part in command:
                if part.startswith("test_") and part.endswith(".py"):
                    with self.subTest(group=name, module=part):
                        self.assertTrue((ROOT / "tests" / part).is_file())

    def test_a_hung_group_is_stopped_well_inside_the_job_limit(self):
        # fast-checks.yml gives the whole job eight minutes, installs included. Each
        # group's own timeout is what turns a hang into a named failure instead of the
        # job being killed with no name; the new group is cheap, so its limit is small.
        for name, _command, timeout in self.groups():
            with self.subTest(group=name):
                self.assertLess(timeout, 8 * 60)
        smoke = next(t for n, c, t in self.groups() if "test_dispatch_smoke.py" in c)
        self.assertLessEqual(smoke, 60)

    def test_the_smoke_test_needs_only_what_the_gate_installs(self):
        # fast-checks.yml installs requests and jsonschema and nothing else; a heavier
        # import in the smoke test would turn the gate red on every push for the wrong
        # reason. The test module must not import anything outside the repo and stdlib
        # (plus those two) at module level.
        import ast
        source = (ROOT / "tests" / "test_dispatch_smoke.py").read_text(encoding="utf-8")
        allowed = {"requests", "jsonschema"}
        local = {"core", "actions", "plugins", "custom_jarvis", "memory", "providers"}
        for node in ast.parse(source).body:
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module.split(".")[0]]
            for name in names:
                if name in sys.stdlib_module_names or name in local or name in allowed:
                    continue
                self.fail(f"test_dispatch_smoke.py imports {name!r} at module level")


if __name__ == "__main__":
    unittest.main()
