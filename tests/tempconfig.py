"""A throwaway settings file, shared by the tests that need one.

Four test modules need the same three lines: point `memory/config_manager` at a
temporary folder, so a test that saves a setting never writes the owner's real
`config/api_keys.json`. Written once here, because the fourth copy of a fixture is
how a test suite starts to drift.

Importable both ways on purpose. `scripts/verify.py` discovers tests with the tests
folder on the path, so the module is `tempconfig`; `python -m unittest tests.x`
imports it as a namespace package, so it is `tests.tempconfig`.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory import config_manager as cm


class WithATemporaryConfig(unittest.TestCase):
    """Every test gets its own api_keys.json, and the real one is never opened."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        folder = Path(self._temp.name)
        self._saved = (cm.CONFIG_DIR, cm.CONFIG_FILE)
        cm.CONFIG_DIR = folder
        cm.CONFIG_FILE = folder / "api_keys.json"

    def tearDown(self):
        cm.CONFIG_DIR, cm.CONFIG_FILE = self._saved
        self._temp.cleanup()

    def write_settings(self, payload: dict) -> None:
        cm.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        cm.CONFIG_FILE.write_text(json.dumps(payload), encoding="utf-8")

    def read_settings(self) -> dict:
        if not cm.CONFIG_FILE.exists():
            return {}
        return json.loads(cm.CONFIG_FILE.read_text(encoding="utf-8"))
