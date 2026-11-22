"""`scripts/map.py` must not say "every module" under a list of modules that are not.

The script ended with "Every module has a docstring and a test that names it." whenever
no NEW gap was found, printed straight under the list of 25 inherited modules that have
neither. The last line is read by whoever ran the check, as the answer.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("map_script", ROOT / "scripts" / "map.py")
map_script = importlib.util.module_from_spec(SPEC)
sys.modules["map_script"] = map_script
SPEC.loader.exec_module(map_script)

WITH_GAPS = ("# Module map\n\n## Inherited, and reported not fixed\n\n"
             "Upstream modules.\n\n- core/a.py: no docstring\n- actions/b.py: no test\n")
CLEAN = "# Module map\n\n## `core/` — 3 modules, 100 lines\n"


class TheClosingLine(unittest.TestCase):
    def test_inherited_gaps_are_counted_and_not_denied(self):
        line = map_script.closing(WITH_GAPS, [])
        self.assertNotIn("Every module", line)
        self.assertIn("2 inherited", line)
        self.assertIn("No new gap", line)

    def test_a_clean_map_may_say_every_module(self):
        self.assertEqual(map_script.closing(CLEAN, []),
                         "Every module has a docstring and a test that names it.")

    def test_a_problem_says_nothing_comforting(self):
        self.assertEqual(map_script.closing(WITH_GAPS, ["core/c.py: no docstring"]), "")


if __name__ == "__main__":
    unittest.main()
