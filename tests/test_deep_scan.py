"""The deep scan's own tests, and the ceilings that stop the debt growing.

A scan that only prints is a report nobody acts on, and a debt nobody measures
grows. So the numbers in `docs/DEEP-SCAN.md` are held here as ceilings: the tree
may improve a figure or leave it alone, and it may not make it worse without a red
build and a decision written down.

When a fix genuinely lowers a number, lower the ceiling in the same commit. That is
the whole ritual: one line down, and the improvement can never silently return.
"""

from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Measured on 2026-11-06. The first number of each pair is the tree's figure at the
# time this test was written; the ceiling is that figure. Nothing here is a target:
# a target nobody reaches is worse than no target.
CEILINGS = {
    "high": 0,
    "swallowed-exception": 157,      # was 282: 43 handlers in core/ and providers/
    "print-in-library": 254,         # now leave a note instead of vanishing
    "complex-function": 108,
    "long-function": 97,
    "typed-exception-discarded": 82,
    "no-timeout": 45,
    "hardcoded-address": 37,
    "deep-nesting": 26,
    "address-in-constant": 19,
    "no-module-docstring": 18,
    "duplicate-body": 11,
    "dangerous-call": 1,
}


def load_scanner():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts import deep_scan
    return deep_scan


class TheScanItself(unittest.TestCase):
    """The rules must fire on the real thing and stay quiet on a deliberate one."""

    def setUp(self):
        self.scanner = load_scanner()
        self.report = self.scanner.Report()

    def scan(self, source: str) -> list:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sample.py"
            path.write_text(textwrap.dedent(source), encoding="utf-8")
            self.scanner.scan_python(path, self.report, {})
        return [f for f in self.report.findings]

    def kinds(self) -> set[str]:
        return {f.kind for f in self.report.findings}

    def test_a_real_key_shape_is_caught(self):
        self.scan('KEY = "sk-' + "a1b2c3d4e5" * 3 + '"')
        self.assertIn("secret-in-source", self.kinds())

    def test_a_marked_fixture_is_not_reported(self):
        # The repository marks fixtures the way the secret scanners do. Without
        # this, the scan cries wolf at its own tests and stops being read.
        self.scan('FIXTURE = "github_pat_11BZQ7XK2MvT9LpR4WnC8JdY6HsA3GfE5UoI1Kq7YmZ"'
                  '  # gitleaks:allow')
        self.assertNotIn("secret-in-source", self.kinds())

    def test_a_dict_get_is_not_a_network_call(self):
        self.scan("def f(d):\n    return d.get('key')")
        self.assertNotIn("no-timeout", self.kinds())

    def test_a_client_get_with_no_timeout_is_reported(self):
        self.scan("def f(session):\n    return session.get('/health')")
        self.assertIn("no-timeout", self.kinds())

    def test_qts_event_loop_is_not_pythons_exec(self):
        self.scan("def f(app):\n    return app.exec()")
        self.assertNotIn("dangerous-call", self.kinds())

    def test_a_named_tuple_of_types_is_not_catching_everything(self):
        # `except (OSError, ValueError):` names what it expects; `except Exception:`
        # does not. The first version of this scan read any tuple as the second and
        # called four honest handlers holes.
        self.scan("""
            def f():
                try:
                    work()
                except (OSError, ValueError):
                    pass
        """)
        self.assertNotIn("swallowed-exception", self.kinds())
        self.assertIn("typed-exception-discarded", self.kinds())

    def test_bare_exec_is_reported(self):
        self.scan("def f(source):\n    exec(source)")
        self.assertIn("dangerous-call", self.kinds())

    def test_a_caught_and_discarded_exception_is_reported(self):
        self.scan("""
            def f():
                try:
                    work()
                except Exception:
                    pass
        """)
        self.assertIn("swallowed-exception", self.kinds())

    def test_a_bare_except_is_high(self):
        self.scan("""
            def f():
                try:
                    work()
                except:
                    pass
        """)
        self.assertEqual([f.severity for f in self.report.findings
                          if f.kind == "bare-except"], ["high"])


class TheCeilings(unittest.TestCase):
    """The tree as it is, measured the way the report measures it."""

    @classmethod
    def setUpClass(cls):
        cls.scanner = load_scanner()
        cls.report = cls.scanner.run(ROOT)
        cls.counts = cls.report.counts()

    def test_no_finding_is_high(self):
        high = self.report.worst(self.scanner.HIGH)
        self.assertEqual([f"{Path(f.path).name}:{f.line} {f.detail}" for f in high],
                         [], "a high finding is a bug that ships")

    def test_no_measure_has_grown_past_its_ceiling(self):
        grown = {}
        for kind, ceiling in CEILINGS.items():
            measured = len(self.report.worst(self.scanner.HIGH)) if kind == "high" \
                else self.counts.get(kind, 0)
            if measured > ceiling:
                grown[kind] = (ceiling, measured)
        self.assertEqual(grown, {}, "the debt grew; fix it or lower it, do not raise "
                                    "the ceiling")

    def test_the_report_lists_where_it_counts_from(self):
        # A number with no file behind it is a claim, not evidence.
        swallowed = [f for f in self.report.findings
                     if f.kind == "swallowed-exception"]
        self.assertTrue(swallowed)
        self.assertTrue(all(f.path.endswith(".py") and f.line > 0
                            for f in swallowed))

    def test_the_owned_core_discards_nothing(self):
        # The rule this project actually promised: the modules it owns — the ones
        # the gates and the evidence path run through — never swallow a failure.
        owned = [f for f in self.report.findings
                 if f.kind == "swallowed-exception"
                 and Path(f.path).relative_to(ROOT).parts[0] in {"core", "providers"}]
        self.assertEqual([f"{Path(f.path).name}:{f.line}" for f in owned], [])


if __name__ == "__main__":
    unittest.main()
