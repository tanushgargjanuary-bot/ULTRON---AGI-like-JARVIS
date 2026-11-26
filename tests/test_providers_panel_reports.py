"""tests/test_providers_panel_reports.py — what a worker thread of the provider panel reports must reach the panel, and must not touch Qt.

Found on 2026-11-26, looking for the next place with the shape of the Linux crash (a thread handed something that belongs to
a window). Three workers of `ProvidersOverlay` report back, and two of them could not:

* `_install` (the one-click install of a provider's package) and `_prepare` (Piper's voice download) reported back with
  `QTimer.singleShot(0, ...)`, called from a plain Python thread. That thread has no Qt event loop, so the callback is dropped.
  Measured in this repository's own environment (PyQt 6.11.0): scheduled from a thread, it never ran in 1.5 seconds of event
  processing. So the panel said "installing some-package — this can take a minute…" for ever, however the install ended, and the
  voice download said nothing at all.
* `_fetch_models` (the list of models on an endpoint) emitted a signal of the PANEL from its thread. While the panel is open that
  works. A read that finishes after the panel was destroyed emits on a deleted object: the shape of the crash that PR #37 and PR #40
  fixed for the voice list.

Now each panel owns an inbox, a plain deque. A worker is handed the inbox and never the panel, and puts what it has to say into it.
The panel's own timer, the one that already looks for the voice list, shows it. The timer is destroyed with the panel, so a late
report lands in a deque nobody looks at, and nothing in it is Qt.

What is asserted (the scenarios run in a child interpreter: a crash there is a failed assertion that shows the exit code and the
last lines it printed, and in this process it would end the whole run with no report):

    * a finished install changes the panel's line from "installing" to the result, and so does one that failed;
    * a voice download's progress reaches the panel, in the order it was reported;
    * a list of models reaches an open panel, and a second read of the same endpoint is not refused;
    * a line that cannot be shown (its label was rebuilt away) is noted, and the lines behind it are still shown;
    * a list of models that arrives after the panel was destroyed raises nothing and does not take the process down;
    * the scenarios really did destroy the panel first and really did run the read on a thread;
    * no function nested in a method that starts a thread calls `QTimer.singleShot`: from a thread it is dropped.
"""

from __future__ import annotations

import ast
import importlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:
    importlib.import_module("PyQt6.QtWidgets")      # only to learn whether Qt can load on this machine
    QT_LOADS, WHY_NOT = True, ""
except ImportError as exc:      # pragma: no cover - environment without Qt
    QT_LOADS, WHY_NOT = False, str(exc)


# Printed, one fact per line, by the child. The parent reads them back.
CHILD = r'''
import faulthandler, os, subprocess, sys, tempfile, threading, time, types
from pathlib import Path
faulthandler.enable()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, sys.argv[1])
from PyQt6 import sip
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

app = QApplication([])
import ui
from memory import config_manager as cm
from providers import tts_piper, tts_system

settings = tempfile.TemporaryDirectory()                   # the owner's real settings file is never opened
cm.CONFIG_DIR, cm.CONFIG_FILE = Path(settings.name), Path(settings.name) / "api_keys.json"
tts_piper.prefetch = lambda on_ready=None: None            # the panel's own reads at start-up: not under test
tts_system.prefetch = lambda on_ready=None: None

models_seen = []                                           # set on the class, before any panel is built
ui.ProvidersOverlay._on_models_ready = lambda self, pid, items: models_seen.append((pid, list(items)))


def pump(until, seconds=5.0):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        if until():
            return True
        time.sleep(0.02)
    return bool(until())


def new_panel(registry):
    window = QWidget()
    panel = ui.ProvidersOverlay(parent=window)             # what ui.py builds: a panel inside the window
    panel._registry = registry                             # the panel asks it for a declaration, or to build a provider
    panel._values = lambda pid: {"base_url": "http://127.0.0.1:9"}
    for pid in ("engine", "voice"):
        panel._status[pid] = QLabel(window)
    return window, panel


# 1. an install finishes
class InstallRegistry:
    def get_declaration(self, pid):
        return {"install": "some-package"}

class Finished:
    returncode = 0
    stdout = b"Successfully installed some-package"

real_run = subprocess.run
subprocess.run = lambda *args, **kwargs: Finished()        # pip is not run
window, panel = new_panel(InstallRegistry())
panel._install("engine")
label = panel._status["engine"]
print("install_said_installing_first=%s" % ("installing" in label.text()), flush=True)
print("install_result_arrived=%s" % pump(lambda: "installed" in label.text()), flush=True)
print("install_line=%s" % label.text(), flush=True)

def pip_is_missing(*args, **kwargs):
    raise OSError("no pip here")

subprocess.run = pip_is_missing                            # an install that cannot even start
window, panel = new_panel(InstallRegistry())
panel._install("engine")
label = panel._status["engine"]
print("failed_install_result_arrived=%s" % pump(lambda: "no pip here" in label.text()), flush=True)
subprocess.run = real_run

# 2. a voice is downloaded, and says how it is getting on
fake = types.ModuleType("providers.fakeprep")
def prepare(values, report):
    report(None, "fetching the voice")             # back to back: both are waiting when the panel's timer next looks
    report(True, "the voice is ready")
fake.prepare = prepare
sys.modules["providers.fakeprep"] = fake

class PrepareRegistry:
    def get_declaration(self, pid):
        return {"_module": "fakeprep"}

window, panel = new_panel(PrepareRegistry())
shown, real_say = [], panel._say
panel._say = lambda pid, text, colour: (shown.append(text), real_say(pid, text, colour))[1]
panel._prepare("voice")
print("prepare_reports_arrived=%s" % pump(lambda: any("ready" in text for text in shown)), flush=True)
print("prepare_reports_in_order=%s" % (shown == ["fetching the voice", "\u2713  the voice is ready"]), flush=True)
print("prepare_shown=%r" % (shown,), flush=True)

# 3. a list of models arrives while the panel is open
class ModelsInstance:
    def models(self, timeout=6.0):
        return ["model-a", "model-b"]

class ModelsRegistry:
    def build(self, pid, values):
        return ModelsInstance()

window, panel = new_panel(ModelsRegistry())
panel._fetch_models("engine")
print("models_arrived=%s" % pump(lambda: bool(models_seen)), flush=True)
print("models_items=%r" % (models_seen[-1] if models_seen else None,), flush=True)
panel._fetch_models("engine")                              # the first read is over: asking again must be allowed
print("a_second_read_is_not_refused=%s" % pump(lambda: len(models_seen) >= 2), flush=True)

# 4. one line cannot be shown (its label was rebuilt away), and the next one still is
from core import failures
failures.clear()
window, panel = new_panel(ModelsRegistry())
inbox = getattr(panel, "_inbox", None)
if inbox is None:                                          # the panel from before the inbox: say so, and go on to the rest
    print("a_lost_line_did_not_stop_the_rest=the panel has no inbox", flush=True)
    print("a_lost_line_was_noted=the panel has no inbox", flush=True)
else:
    doomed = QLabel(window)
    panel._status["doomed"] = doomed
    sip.delete(doomed)
    inbox.append(("say", "doomed", "this label is gone", ""))
    inbox.append(("say", "engine", "this one is fine", ""))
    print("a_lost_line_did_not_stop_the_rest=%s" % pump(lambda: panel._status["engine"].text() == "this one is fine"), flush=True)
    print("a_lost_line_was_noted=%s" % any(n["where"] == "ui.providers_inbox" for n in failures.recent(200)), flush=True)

# 5. a list of models arrives after the panel was destroyed
gate, started, errors = threading.Event(), threading.Event(), []
threading.excepthook = lambda args: errors.append(args.exc_type.__name__)

class SlowInstance:
    def models(self, timeout=6.0):
        started.set()
        gate.wait(60)                                      # the network read, held until the scenario lets it end
        return ["model-a"]

class SlowRegistry:
    def build(self, pid, values):
        return SlowInstance()

before = set(threading.enumerate())
window, panel = new_panel(SlowRegistry())
panel._fetch_models("late")
workers = [t for t in threading.enumerate() if t not in before]
started.wait(20)
sip.delete(window)                                         # the window closes and takes its panel with it
print("late_panel_destroyed=%s" % sip.isdeleted(panel), flush=True)
print("late_read_ran_on_a_thread=%s" % bool(workers and started.is_set()), flush=True)
gate.set()
for worker in workers:
    worker.join(30)
app.processEvents()
print("late_read_finished=%s" % (not any(t.is_alive() for t in workers)), flush=True)
print("late_errors=%s" % (",".join(sorted(set(errors))) or "none"), flush=True)
settings.cleanup()
print("survived", flush=True)
'''


def facts_in(output: str) -> dict:
    found = {}
    for line in output.splitlines():
        key, sep, value = line.partition("=")
        if sep and key.isidentifier():
            found[key] = value.strip()
    return found


@unittest.skipUnless(QT_LOADS, WHY_NOT)
class WhatAWorkerReportsReachesThePanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # One child for every check below: it costs a few seconds to import the interface.
        from tests.test_providers_panel_threads import run_the_scenarios

        cls.code, cls.output = run_the_scenarios(CHILD)
        cls.facts = facts_in(cls.output)

    def shown(self) -> str:
        from tests.test_providers_panel_threads import tail

        return "\n" + tail(self.output)

    def test_the_child_finished(self):
        self.assertIsNotNone(self.code, "the child never finished:" + self.shown())
        self.assertEqual(self.code, 0, f"the child died (exit code {self.code}; 139 or -11 is a segmentation fault):" + self.shown())
        self.assertIn("survived", self.output)

    def test_a_finished_install_is_shown(self):
        self.assertEqual(self.facts.get("install_said_installing_first"), "True",
                         "the panel did not say it was installing: the scenario is wrong" + self.shown())
        self.assertEqual(self.facts.get("install_result_arrived"), "True",
                         "the install finished and the panel still says what it said at the start" + self.shown())

    def test_an_install_that_fails_says_so(self):
        self.assertEqual(self.facts.get("failed_install_result_arrived"), "True",
                         "an install that failed left the panel saying it was installing" + self.shown())

    def test_a_voice_download_reports_its_progress_in_order(self):
        self.assertEqual(self.facts.get("prepare_reports_arrived"), "True",
                         "a voice download reported and the panel never showed it" + self.shown())
        self.assertEqual(self.facts.get("prepare_reports_in_order"), "True",
                         "the reports reached the panel out of order, or not all of them" + self.shown())

    def test_a_list_of_models_reaches_an_open_panel(self):
        self.assertEqual(self.facts.get("models_arrived"), "True", "an open panel never got its list of models" + self.shown())
        self.assertIn("model-a", self.facts.get("models_items", ""), "the list that arrived is not the one that was read" + self.shown())

    def test_a_line_that_cannot_be_shown_is_noted_and_the_next_one_still_is(self):
        self.assertEqual(self.facts.get("a_lost_line_did_not_stop_the_rest"), "True",
                         "one line that could not be shown stopped the ones behind it" + self.shown())
        self.assertEqual(self.facts.get("a_lost_line_was_noted"), "True",
                         "a line that could not be shown was dropped without a note" + self.shown())

    def test_a_second_read_of_the_same_endpoint_is_not_refused(self):
        self.assertEqual(self.facts.get("a_second_read_is_not_refused"), "True",
                         "the panel kept the first read as still running, so it never asked again" + self.shown())

    def test_the_scenario_destroyed_the_panel_and_ran_the_read_on_a_thread(self):
        # Printed before the late read is let go, so they hold even if that read kills the process.
        self.assertEqual(self.facts.get("late_panel_destroyed"), "True", "the panel was not destroyed first" + self.shown())
        self.assertEqual(self.facts.get("late_read_ran_on_a_thread"), "True", "no read ran on a thread" + self.shown())

    def test_a_list_of_models_that_arrives_after_the_panel_is_gone_raises_nothing(self):
        self.assertEqual(self.facts.get("late_read_finished"), "True", "the late read never finished" + self.shown())
        self.assertEqual(self.facts.get("late_errors"), "none",
                         "the late read raised in its thread (it touched the destroyed panel)" + self.shown())


class NoWorkerSchedulesATimerFromItsThread(unittest.TestCase):
    """`QTimer.singleShot` from a thread without an event loop is dropped. This looks for the shape in ui.py: a function nested in
    a method that starts a thread, calling it. A heuristic: it does not follow calls into other methods. The scenarios above are
    the proof for the two places that had it."""

    def threaded_methods(self):
        tree = ast.parse((ROOT / "ui.py").read_text(encoding="utf-8"))
        for method in ast.walk(tree):
            if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            starts_a_thread = any(
                isinstance(node, ast.Call) and (
                    (isinstance(node.func, ast.Attribute) and node.func.attr == "Thread")
                    or (isinstance(node.func, ast.Name) and node.func.id == "Thread"))
                for node in ast.walk(method))
            if starts_a_thread:
                yield method

    @staticmethod
    def is_single_shot(node) -> bool:
        return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "singleShot"
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "QTimer")

    def test_no_function_nested_in_a_threaded_method_calls_single_shot(self):
        offenders = []
        for method in self.threaded_methods():
            for inner in ast.walk(method):
                if inner is method or not isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                    continue
                for node in ast.walk(inner):
                    if self.is_single_shot(node):
                        offenders.append(f"ui.py:{node.lineno} in {method.name}")
        self.assertEqual(sorted(set(offenders)), [],
                         "a worker thread has no event loop: QTimer.singleShot from it is dropped. Put the report in the "
                         "panel's `_inbox` instead (see ProvidersOverlay._drain_inbox)")

    def test_the_scan_can_see(self):
        # A scan that finds nothing passes on nothing. ui.py starts a dozen threads and schedules timers in a dozen places.
        methods = list(self.threaded_methods())
        tree = ast.parse((ROOT / "ui.py").read_text(encoding="utf-8"))
        timers = [node for node in ast.walk(tree) if self.is_single_shot(node)]
        self.assertGreaterEqual(len(methods), 8, "the scan found too few methods that start a thread; fix the scan, not the number")
        self.assertGreaterEqual(len(timers), 8, "the scan found too few QTimer.singleShot calls; fix the scan, not the number")


if __name__ == "__main__":
    unittest.main()
