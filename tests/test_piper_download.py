"""`providers/tts_piper.py` `download`: a voice is listed as installed only when both of its files are whole.

Piper's own downloader (piper-tts 1.8.0, `download_voices.py`) writes the model straight to its final name and
fetches a file again only when it is missing or EMPTY. A download cut short therefore left a truncated,
non-empty `.onnx` that `installed()`, `prepare()` and Piper itself took for a finished voice, and that no later
download repaired. `download()` now has Piper write into a scratch folder and moves the files in only once both
are complete, the model last, because `installed()` looks for the model. The scratch folder belongs to one voice
(its name is the voice's, escaped, so no voice name can point it elsewhere), and the same voice is fetched by one
caller at a time, while different voices are fetched in parallel as they always were. Files truncated by a
download that failed before this change are not repaired (they pass the exists check): deleting such a voice's
`.onnx` lets the next download replace it.

The network is not touched: a stand-in for `piper.download_voices` writes what a real download writes, or is cut
short. Not verified: a real download over a real connection.
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

from providers import tts_piper

VOICE = "en_US-test-low"
SLOW, QUICK = "en_US-slow-low", "en_GB-quick-low"
MODEL = b"M" * 1000
CONFIG = b'{"audio": {"sample_rate": 22050}}'


def whole(voice, directory, force_redownload=False):
    """What piper-tts does: the model first, then its config."""
    (directory / f"{voice}.onnx").write_bytes(MODEL)
    (directory / f"{voice}.onnx.json").write_bytes(CONFIG)


def cut_in_the_model(voice, directory, force_redownload=False):
    (directory / f"{voice}.onnx").write_bytes(MODEL[:300])
    raise OSError("connection reset")


def cut_before_the_config(voice, directory, force_redownload=False):
    (directory / f"{voice}.onnx").write_bytes(MODEL)
    raise OSError("connection reset")


def not_a_voice(voice, directory, force_redownload=False):
    """What piper-tts does with a name that is not <language>-<name>-<quality>."""
    raise ValueError(f"Voice '{voice}' did not match pattern")


def downloader(behaviour) -> dict:
    """A stand-in `piper.download_voices` module, as `sys.modules` entries."""
    package = types.ModuleType("piper")
    module = types.ModuleType("piper.download_voices")
    module.download_voice = behaviour
    package.download_voices = module
    return {"piper": package, "piper.download_voices": module}


class Download(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.voices = self.root / "voices"
        self.voices.mkdir()
        patch = mock.patch.object(tts_piper, "_VOICE_DIR", self.voices)
        patch.start()
        self.addCleanup(patch.stop)

    def names(self) -> list:
        return sorted(item.name for item in self.voices.iterdir())

    def fetch(self, behaviour):
        with mock.patch.dict(sys.modules, downloader(behaviour)):
            return tts_piper.download(VOICE)

    def test_a_whole_download_lands_both_files_and_nothing_else(self):
        target = self.fetch(whole)
        self.assertEqual(target, self.voices / f"{VOICE}.onnx")
        self.assertEqual(self.names(), [f"{VOICE}.onnx", f"{VOICE}.onnx.json"])
        self.assertEqual(target.read_bytes(), MODEL)
        self.assertEqual(tts_piper.installed(), [VOICE])

    def test_a_download_cut_in_the_model_leaves_no_voice_behind(self):
        with self.assertRaises(OSError):
            self.fetch(cut_in_the_model)
        self.assertEqual(self.names(), [], "a truncated model must not sit under the name of a finished one")
        self.assertEqual(tts_piper.installed(), [])

    def test_a_download_cut_before_the_config_leaves_no_voice_behind(self):
        with self.assertRaises(OSError):
            self.fetch(cut_before_the_config)
        self.assertEqual(self.names(), [], "a model with no config is not a voice")
        self.assertEqual(tts_piper.installed(), [])

    def test_the_model_goes_in_last(self):
        moved: list[str] = []
        real = os.replace

        def recording(source, destination):
            moved.append(Path(destination).name)
            return real(source, destination)

        with mock.patch.object(tts_piper.os, "replace", side_effect=recording):
            self.fetch(whole)
        self.assertEqual(moved, [f"{VOICE}.onnx.json", f"{VOICE}.onnx"])

    def test_a_scratch_folder_left_by_a_crash_is_cleared_and_never_moved_into_place(self):
        leftover = self.voices / f".partial-{VOICE}"
        leftover.mkdir()
        (leftover / "other.onnx").write_bytes(b"left by a crash")
        self.fetch(whole)
        self.assertEqual(self.names(), [f"{VOICE}.onnx", f"{VOICE}.onnx.json"])

    def test_a_voice_already_on_disk_is_not_fetched_again(self):
        (self.voices / f"{VOICE}.onnx").write_bytes(MODEL)

        def must_not_run(*_args, **_kwargs):
            raise AssertionError("the voice was already there")

        self.assertEqual(self.fetch(must_not_run), self.voices / f"{VOICE}.onnx")

    def test_two_callers_for_one_voice_fetch_it_once(self):
        started, release = threading.Event(), threading.Event()
        calls: list[str] = []
        results: list[Path] = []

        def slow(voice, directory, force_redownload=False):
            calls.append(voice)
            started.set()
            release.wait(10)
            whole(voice, directory)

        def caller():
            results.append(tts_piper.download(VOICE))

        with mock.patch.dict(sys.modules, downloader(slow)):
            first, second = threading.Thread(target=caller), threading.Thread(target=caller)
            first.start()
            self.assertTrue(started.wait(10), "the first download never started")
            second.start()
            time.sleep(0.2)                             # long enough for the second caller to reach the lock
            release.set()
            first.join(10)
            second.join(10)
        self.assertEqual(calls, [VOICE], "the second caller fetched the same voice again")
        self.assertEqual(results, [self.voices / f"{VOICE}.onnx"] * 2)
        self.assertEqual(self.names(), [f"{VOICE}.onnx", f"{VOICE}.onnx.json"])

    def test_a_voice_stuck_on_a_slow_network_does_not_hold_up_another(self):
        release, slow_started = threading.Event(), threading.Event()
        results: dict[str, Path] = {}

        def behaviour(voice, directory, force_redownload=False):
            if voice == SLOW:
                slow_started.set()
                release.wait(10)
            whole(voice, directory)

        def fetch(voice):
            results[voice] = tts_piper.download(voice)

        with mock.patch.dict(sys.modules, downloader(behaviour)):
            slow, quick = threading.Thread(target=fetch, args=(SLOW,)), threading.Thread(target=fetch, args=(QUICK,))
            slow.start()
            self.assertTrue(slow_started.wait(10), "the slow download never started")
            quick.start()
            quick.join(5)
            quick_finished_first = not quick.is_alive()
            release.set()
            slow.join(10)
            quick.join(10)
        self.assertTrue(quick_finished_first, "the second voice waited behind the first")
        self.assertEqual(set(results), {SLOW, QUICK})
        self.assertEqual(tts_piper.installed(), sorted([SLOW, QUICK]))
        self.assertEqual(len(self.names()), 4, "both voices, both files, and no scratch folder")

    def test_a_voice_name_cannot_point_the_scratch_folder_outside_the_voices_folder(self):
        victim = self.root / "victim"
        victim.mkdir()
        (victim / "keep.txt").write_text("keep", encoding="utf-8")
        with mock.patch.dict(sys.modules, downloader(not_a_voice)), self.assertRaises(ValueError):
            tts_piper.download("x/../../victim")
        self.assertEqual((victim / "keep.txt").read_text(encoding="utf-8"), "keep", "a folder outside was deleted")
        self.assertEqual(self.names(), [], "and nothing is left behind in the voices folder")


if __name__ == "__main__":
    unittest.main()
