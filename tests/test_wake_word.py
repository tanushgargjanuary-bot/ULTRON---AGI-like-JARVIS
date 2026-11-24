"""`core/wake_word.py`: one "Hey Jarvis" is one wake, and going to sleep forgets what was heard before.

openWakeWord's model keeps its recent audio features and scores. Left alone they outlive an utterance (the
phrase can fire again on the frames that follow it) and they outlive a wake (audio from before the assistant
woke is still in there when it goes back to sleep, so words said minutes earlier can wake it again).
`Model.reset()` empties both (openwakeword 0.6.0, `model.py`). Mark LVII reports twelve detections for one
phrase without it; that number was not reproduced here, because the real model is not run by these tests.
A stand-in whose score stays above the threshold until it is reset behaves the way those buffers do.

`main.py` imports `sounddevice` at module level, so `JarvisLive.sleep` is checked where it stands in the source
and not run, as `tests/test_background_loops.py` does for the loops it checks. (Running it would take a second
`exec`, and the debt ceiling for those is one.)
"""

from __future__ import annotations

import ast
import queue
import unittest
from pathlib import Path
from unittest import mock

from core import wake_word

try:
    import numpy  # noqa: F401  (the detector's loop imports it)
except ImportError as missing:                           # pragma: no cover
    raise unittest.SkipTest(f"numpy is not installed: {missing}") from missing

ROOT = Path(__file__).resolve().parents[1]
FRAME = [0] * 1280                                       # 80 ms of silence; the stand-in model ignores the sound


class StaleModel:
    """Scores above the threshold for `hot` frames after an utterance, until it is reset."""

    def __init__(self, hot: int = 12, resets_with: Exception | None = None):
        self.hot_left = hot
        self.events: list[str] = []
        self._resets_with = resets_with

    def predict(self, frame):
        self.events.append("predict")
        if self.hot_left > 0:
            self.hot_left -= 1
            return {"hey_jarvis_v0.1": 0.9}
        return {"hey_jarvis_v0.1": 0.0}

    def reset(self):
        self.events.append("reset")
        if self._resets_with is not None:
            raise self._resets_with
        self.hot_left = 0


class OneAtATime:
    """Frames arrive one by one with none backlogged, then None, which ends the loop."""

    def __init__(self, count: int):
        self._items = [FRAME] * count + [None]

    def get(self):
        return self._items.pop(0)

    def get_nowait(self):
        raise queue.Empty


def listening(model: StaleModel, frames: int, before=None):
    """Run the detector's loop over `frames` frames. Returns (how many times it woke, the detector)."""
    woke: list[int] = []
    detector = wake_word.WakeWordDetector(on_detect=lambda: woke.append(1), threshold=0.5, logger=lambda _m: None)
    detector._queue = OneAtATime(frames)
    detector._model = model
    detector._running = True
    if before:
        before(detector)
    detector._loop()
    return len(woke), detector


class OneUtteranceIsOneWake(unittest.TestCase):
    def test_a_model_that_stays_hot_after_a_phrase_wakes_it_once(self):
        woke, _detector = listening(StaleModel(hot=12), frames=13)
        self.assertEqual(woke, 1, "the same phrase fired again on the frames that followed it")

    def test_the_model_is_cleared_after_a_detection_and_before_the_callback_can_be_repeated(self):
        model = StaleModel(hot=12)
        listening(model, frames=2)
        self.assertEqual(model.events[:2], ["predict", "reset"])

    def test_a_second_phrase_after_silence_wakes_it_again(self):
        model = StaleModel(hot=1)
        woke, _detector = listening(model, frames=3)
        self.assertEqual(woke, 1)
        model.hot_left = 1                               # the next phrase
        woke_again, _detector = listening(model, frames=2)
        self.assertEqual(woke_again, 1)

    def test_a_model_that_cannot_be_reset_still_wakes_and_the_failure_is_recorded(self):
        model = StaleModel(hot=1, resets_with=RuntimeError("no reset"))
        with mock.patch.object(wake_word.failures, "note") as note:
            woke, _detector = listening(model, frames=2)
        self.assertEqual(woke, 1, "a reset that fails must not swallow the wake")
        # (`_drain` also notes the `queue.Empty` that ends every drain; that is older than this change.)
        failed = [call for call in note.call_args_list if call.args[0] == "wake_word.reset"]
        self.assertEqual(len(failed), 1, "the failed reset was not recorded, or was recorded twice")
        self.assertIsInstance(failed[0].args[1], RuntimeError)


class SleepingForgets(unittest.TestCase):
    def test_a_requested_reset_happens_before_the_next_frame_is_scored(self):
        model = StaleModel(hot=0)
        listening(model, frames=2, before=lambda detector: detector.reset())
        self.assertEqual(model.events, ["reset", "predict", "predict"])

    def test_a_request_is_served_once(self):
        model = StaleModel(hot=0)
        listening(model, frames=4, before=lambda detector: detector.reset())
        self.assertEqual(model.events.count("reset"), 1)

    def test_asking_a_detector_that_is_not_running_is_harmless(self):
        detector = wake_word.WakeWordDetector(on_detect=lambda: None, logger=lambda _m: None)
        with mock.patch.object(wake_word.failures, "note") as note:
            detector.reset()                             # never started: there is no model yet
            detector._reset_model()                      # and a stopped one has none either
        self.assertIsNone(detector._model)
        note.assert_not_called()                         # nothing went wrong, so nothing is recorded


def sleep_method() -> ast.FunctionDef:
    """`JarvisLive.sleep`, as the parser sees it in main.py."""
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "JarvisLive")
    return next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "sleep")


def resets_in(method: ast.FunctionDef) -> list:
    return [node for node in ast.walk(method) if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute) and node.func.attr == "reset"]


class TheAssistantGoingToSleep(unittest.TestCase):
    def the_reset_call(self, method: ast.FunctionDef) -> ast.Call:
        """The one `.reset()` call in sleep(), or a failure that says there is not exactly one."""
        calls = resets_in(method)
        self.assertEqual(len(calls), 1, "sleep() must ask the wake-word detector to reset, once")
        return calls[0]

    def test_it_asks_the_detector_to_forget_what_it_heard_and_it_is_the_assistants_own_detector(self):
        method = sleep_method()
        self.the_reset_call(method)
        reads = [node for node in ast.walk(method) if isinstance(node, ast.Attribute) and node.attr == "_wake_detector"]
        self.assertTrue(reads, "sleep() does not read self._wake_detector")

    def test_the_request_is_made_only_when_it_really_goes_to_sleep(self):
        method = sleep_method()
        guard = method.body[0]                           # `if not self._awake: return`
        self.assertIsInstance(guard, ast.If)
        self.assertTrue(any(isinstance(node, ast.Return) for node in guard.body), "the already-asleep guard is gone")
        asleep = next(node for node in method.body if isinstance(node, ast.Assign)
                      and isinstance(node.targets[0], ast.Attribute) and node.targets[0].attr == "_awake")
        request = self.the_reset_call(method)
        self.assertGreater(request.lineno, guard.end_lineno, "the request comes before the already-asleep guard")
        self.assertGreater(request.lineno, asleep.lineno, "the request comes before the assistant is marked asleep")

    def test_with_no_detector_it_still_sleeps(self):
        method = sleep_method()
        request = self.the_reset_call(method)
        guards = [node for node in ast.walk(method) if isinstance(node, ast.If) and request in list(ast.walk(node))
                  and isinstance(node.test, ast.Compare) and isinstance(node.test.ops[0], ast.IsNot)
                  and isinstance(node.test.comparators[0], ast.Constant) and node.test.comparators[0].value is None]
        self.assertTrue(guards, "wake word off means no detector: the request must be skipped, not crash sleep()")


if __name__ == "__main__":
    unittest.main()
