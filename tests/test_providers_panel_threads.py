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

The first fix (a shared `_LiveRelay`, made once "and not deleted while the program runs") was not enough. On 2026-11-25
the Linux job died the same way again, in the provider self-test, at the same line, about three and a half hours after
that fix had been merged (run 45679604007, on 855f6c6; Windows passed on the same commit). The relay was NOT immortal: it is destroyed with the QApplication. The self-test
holds its application in a local variable, so the application, and the relay with it, go when that test returns. A read that
reports in afterwards called `relay.ready.emit`, a bound signal that keeps a raw pointer to freed memory. The same happens
when the program closes while a read is still running. Reproduced on purpose: 20 runs out of 20 crashed. A panel built
after the application was made again could not even be constructed ("wrapped C/C++ object of type _LiveRelay has been
deleted").

So no worker thread touches Qt now. A read that finishes calls `announce()` on a plain Python counter, which has no Qt in it
and cannot be gone. Each panel looks at that counter on a timer of its own, and the timer dies with the panel.

What is asserted:
    * a read that finishes after its panel was destroyed does not take the process down;
    * a read that finishes after the QApplication is gone does not take it down either, and raises nothing;
    * the scenarios really did destroy the panel, and the application, first, and really did run the read on a thread, so a
      refactor cannot leave the checks passing for the wrong reason;
    * a panel that is still open is still told when its read finishes, so the redraw it exists for still happens;
    * a panel built after the application was made again is built, and is told.

The scenarios run in child interpreters. A crash there is a failed assertion that shows the exit code and the last
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
import faulthandler, os, sys, tempfile, threading, time
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

def let_the_read_finish(expect_told=False):
    gate.set()
    for thread in workers:
        thread.join(60)
    deadline = time.time() + (5 if expect_told else 0.3)
    while time.time() < deadline:                          # the panel looks for news on a timer of its own
        app.processEvents()
        if expect_told and told:
            break
        time.sleep(0.02)

window, panel = open_a_panel()
let_the_read_finish(expect_told=True)
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


LATE_CHILD = r'''
import faulthandler, gc, os, sys, tempfile, threading, time
from pathlib import Path
faulthandler.enable()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, sys.argv[1])
from PyQt6 import sip
from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QApplication, QWidget

app = QApplication([])
import ui
from memory import config_manager as cm
from providers import tts_piper, tts_system

settings = tempfile.TemporaryDirectory()                  # the owner's real settings file is never opened
cm.CONFIG_DIR, cm.CONFIG_FILE = Path(settings.name), Path(settings.name) / "api_keys.json"

handed, told = [], []
tts_piper.prefetch = lambda on_ready=None: handed.append(on_ready)     # the read is held back; the scenario ends it
tts_system.prefetch = lambda on_ready=None: None
ui.ProvidersOverlay._on_live_ready = lambda self: told.append(self)

window = QWidget()
panel = ui.ProvidersOverlay(parent=window)
callback = handed[0]                                       # what the panel gave to its background read
print("read_was_handed_a_callback=%s" % callable(callback), flush=True)
sip.delete(window)                                         # the window closes and takes its panel with it
del window, panel
app.processEvents()
del app                                                    # the program is closing: the application goes too
gc.collect()
print("application_destroyed=%s" % (QApplication.instance() is None), flush=True)

errors, calls = [], [0]
def late_read():                                           # the read finishes now, and reports in
    for _ in range(300):
        try:
            callback()
            calls[0] += 1
        except Exception as error:
            errors.append(type(error).__name__)
        time.sleep(0.0002)

reader = threading.Thread(target=late_read)
reader.start()
junk = []
while reader.is_alive():                                   # meanwhile the interface thread keeps making objects
    junk.append([QObject() for _ in range(40)])
    if len(junk) > 30:
        junk.clear()
reader.join()
print("late_calls=%d" % calls[0], flush=True)
print("late_errors=%s" % (",".join(sorted(set(errors))) or "none"), flush=True)
print("survived_the_late_read", flush=True)

app2 = QApplication([])                                    # a restart, or the next test: a new application
before = len(told)
panel2 = ui.ProvidersOverlay()
print("panel_built_after_the_application_was_recreated=True", flush=True)
handed[-1]()                                               # its own read reports in
deadline = time.time() + 5
while time.time() < deadline and len(told) == before:
    app2.processEvents()
    time.sleep(0.02)
print("new_panel_told=%s" % (len(told) > before), flush=True)
settings.cleanup()
print("finished", flush=True)
'''


def run_the_scenarios(source: str | None = None) -> tuple:
    """(exit code or None if it never finished, everything the child printed)."""
    source = source or CHILD
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    try:
        done = subprocess.run([sys.executable, "-c", source, str(ROOT)], cwd=str(ROOT), env=env,
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


class AReadThatFinishesAfterTheApplicationIsGone(unittest.TestCase):
    """The crash that the first fix missed: the application, and everything Qt made, is gone when the read reports in."""

    @classmethod
    def setUpClass(cls):
        cls.code, cls.output = run_the_scenarios(LATE_CHILD)

    def facts(self) -> dict:
        found = {}
        for line in self.output.splitlines():
            key, sep, value = line.partition("=")
            if sep and key.isidentifier():
                found[key] = value.strip()
        return found

    def test_the_process_survives_a_read_that_finishes_after_the_application_is_gone(self):
        self.assertIsNotNone(self.code, "the child never finished:\n" + tail(self.output))
        self.assertEqual(self.code, 0, "the process died when a read reported in after the application was destroyed "
                         f"(exit code {self.code}; 139 or -11 is a segmentation fault):\n" + tail(self.output))
        self.assertIn("survived_the_late_read", self.output)

    def test_the_scenario_destroyed_the_application_and_gave_the_read_a_callback(self):
        # Printed before the late read starts, so these hold even if that read kills the process.
        facts = self.facts()
        self.assertEqual(facts.get("read_was_handed_a_callback"), "True", "no read was handed a callback:\n" + tail(self.output))
        self.assertEqual(facts.get("application_destroyed"), "True", "the application was still alive:\n" + tail(self.output))

    def test_a_late_read_can_always_report_in_without_an_error(self):
        facts = self.facts()
        self.assertEqual(facts.get("late_errors"), "none", "reporting in raised an error:\n" + tail(self.output))
        self.assertGreaterEqual(int(facts.get("late_calls", "0")), 1, "the late read never reported in:\n" + tail(self.output))

    def test_a_panel_built_after_the_application_was_recreated_is_built_and_told(self):
        facts = self.facts()
        self.assertEqual(facts.get("panel_built_after_the_application_was_recreated"), "True",
                         "a panel could not be built after the application was made again:\n" + tail(self.output))
        self.assertEqual(facts.get("new_panel_told"), "True", "the new panel was never told:\n" + tail(self.output))


if __name__ == "__main__":
    unittest.main()
