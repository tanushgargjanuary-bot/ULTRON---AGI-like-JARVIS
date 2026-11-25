"""tests/test_providers_panel_threads.py — a settings panel that is gone must not be called by a thread that outlives it.

CI's Linux job died twice with exit code 245 (a segmentation fault), once on main and once on a pull request, and
passed when it was run again. The log said nothing else. This reproduces it.

Opening the engine panel starts reads in the background. Piper's list of published voices is an HTTPS call that can
take as long as its twenty-second timeout. Each read was handed `self._live_ready.emit`, a signal of the PANEL, to
call when it finished. A read that finishes after the panel has been destroyed emitted on freed memory and killed the
whole process, at providers/tts_piper.py line 170.

That is not only a test problem. The window destroys its panels when it closes, so closing the program while a voice
list was still downloading did the same thing. Reproduced with the panel parented to a window, as ui.py builds it:
5 runs out of 5 crashed.

What is asserted:
    * a read that finishes after its panel was destroyed does not take the process down;
    * the scenario really did destroy the panel first and really did run the read on a thread, so a refactor cannot
      leave the first check passing for the wrong reason;
    * a panel that is still open is still told when its read finishes, so the redraw it exists for still happens.

The scenarios run in a child interpreter. A crash there is a failed assertion that shows the exit code and the last
lines the child printed. In this process it would end the whole run with no report.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:
    importlib.import_module("PyQt6.QtWidgets")      # only to learn whether Qt can load on this machine
except ImportError as exc:      # pragma: no cover - environment without Qt
    raise unittest.SkipTest(str(exc)) from exc


# Printed, one fact per line, by the child. The parent reads them back.
CHILD = r'''
import faulthandler, os, sys, tempfile, threading
from pathlib import Path
faulthandler.enable()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, sys.argv[1])
from PyQt6 import sip
from PyQt6.QtWidgets import QApplication, QWidget

app = QApplication([])
import ui
from memory import config_manager as cm
from providers import tts_piper, tts_system

settings = tempfile.TemporaryDirectory()                  # the owner's real settings file is never opened
cm.CONFIG_DIR, cm.CONFIG_FILE = Path(settings.name), Path(settings.name) / "api_keys.json"

gate, started, workers, told = threading.Event(), threading.Event(), [], []

def held_catalog(refresh=False):
    started.set()
    gate.wait(60)                                          # the network read, held until the scenario lets it end
    return {}

real_prefetch = tts_piper.prefetch
def recording_prefetch(on_ready=None):
    before = set(threading.enumerate())
    real_prefetch(on_ready)
    workers.extend(t for t in threading.enumerate() if t not in before)

tts_piper.catalog = held_catalog
tts_piper.prefetch = recording_prefetch
tts_system.prefetch = lambda on_ready=None: None           # its list is a PowerShell call on Windows: not under test
ui.ProvidersOverlay._on_live_ready = lambda self: told.append(self)

def open_a_panel():
    gate.clear(); started.clear(); tts_piper._catalog = None; del workers[:]
    window = QWidget()
    panel = ui.ProvidersOverlay(parent=window)             # what ui.py builds: a panel inside the window
    started.wait(20)
    return window, panel

def let_the_read_finish():
    gate.set()
    for thread in workers:
        thread.join(60)
    app.processEvents()                                    # a call queued for the interface thread arrives here

window, panel = open_a_panel()
let_the_read_finish()
print("open_panel_told=%d" % len(told), flush=True)

window, panel = open_a_panel()
sip.delete(window)                                         # the window closes and takes its panel with it
print("panel_destroyed=%s" % sip.isdeleted(panel), flush=True)
print("read_ran_on_a_thread=%s" % bool(workers), flush=True)
let_the_read_finish()
print("late_read_finished=%s" % (not any(t.is_alive() for t in workers)), flush=True)
settings.cleanup()
print("survived", flush=True)
'''


def run_the_scenarios() -> tuple:
    """(exit code or None if it never finished, everything the child printed)."""
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    try:
        done = subprocess.run([sys.executable, "-c", CHILD, str(ROOT)], cwd=str(ROOT), env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              encoding="utf-8", errors="replace", timeout=240, check=False)
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        return None, partial
    return done.returncode, done.stdout


def tail(text: str, lines: int = 30) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


class AReadThatOutlivesThePanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # One child for every check below: it costs a few seconds to import the interface.
        cls.code, cls.output = run_the_scenarios()

    def facts(self) -> dict:
        found = {}
        for line in self.output.splitlines():
            key, sep, value = line.partition("=")
            if sep and key.isidentifier():
                found[key] = value.strip()
        return found

    def test_the_process_survives_a_read_that_finishes_after_the_panel_is_gone(self):
        self.assertIsNotNone(self.code, "the child never finished:\n" + tail(self.output))
        self.assertEqual(self.code, 0, "the process died when a read finished after its panel was destroyed "
                         f"(exit code {self.code}; 139 or -11 is a segmentation fault):\n" + tail(self.output))
        self.assertEqual(self.facts().get("late_read_finished"), "True", "the read never finished:\n" + tail(self.output))
        self.assertIn("survived", self.output)

    def test_the_scenario_destroyed_the_panel_and_ran_the_read_on_a_thread(self):
        # Both facts are printed before the late read is let go, so they hold even if that read kills the process:
        # the first test then reports the crash and this one says the scenario itself was sound.
        facts = self.facts()
        self.assertEqual(facts.get("panel_destroyed"), "True", "the panel was not destroyed first:\n" + tail(self.output))
        self.assertEqual(facts.get("read_ran_on_a_thread"), "True", "no read ran on a thread:\n" + tail(self.output))

    def test_a_panel_that_is_still_open_is_told_when_its_read_finishes(self):
        told = int(self.facts().get("open_panel_told", "0"))
        self.assertGreaterEqual(told, 1, "an open panel was never told its voice list had arrived:\n" + tail(self.output))


if __name__ == "__main__":
    unittest.main()
