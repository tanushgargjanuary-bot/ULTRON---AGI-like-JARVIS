"""tests/test_audio_features.py — speech vs noise, with signals we can control.

    Real microphones cannot be tested in CI, so the tests use synthetic signals
    whose spectral character is known exactly:

      voiced speech   a 140 Hz fundamental plus harmonics (peaky spectrum)
      white noise     uniform random samples (flat spectrum)
      silence         zeros
      clatter         broadband bursts with silence between them

    If the classifier cannot separate those, it will not separate a real room
    either, and no amount of microphone data would make a broken test pass.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.audio_features import (
    NoiseFloor,
    TurnEndDetector,
    features,
    rms,
    spectral_flatness,
    zero_crossing_rate,
)

RATE = 16000
FRAME = 480            # 30 ms


def voiced(n=FRAME, f0=140.0, amplitude=0.25):
    """A harmonic-rich burst: what a vowel looks like to an FFT."""
    t = np.arange(n) / RATE
    signal = sum(np.sin(2 * np.pi * f0 * k * t) / k for k in range(1, 8))
    return (amplitude * signal / 2.0).astype(np.float64)


def noise(n=FRAME, amplitude=0.25, seed=0):
    rng = np.random.default_rng(seed)
    return (rng.uniform(-amplitude, amplitude, n)).astype(np.float64)


def silence(n=FRAME):
    return np.zeros(n, dtype=np.float64)


class FeatureTests(unittest.TestCase):
    def test_rms_of_silence_and_signal(self):
        self.assertEqual(rms(silence()), 0.0)
        self.assertGreater(rms(voiced()), 0.01)
        self.assertEqual(rms(np.array([])), 0.0)

    def test_flatness_separates_tone_from_noise(self):
        tonal = spectral_flatness(voiced())
        flat = spectral_flatness(noise())
        self.assertLess(tonal, 0.35, "a harmonic burst should look peaky")
        self.assertGreater(flat, 0.5, "white noise should look flat")
        self.assertGreater(flat, tonal * 2)

    def test_flatness_of_silence_is_defined(self):
        for samples in (silence(), np.zeros(4), np.array([])):
            value = spectral_flatness(samples)
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)

    def test_zero_crossing_rate(self):
        self.assertEqual(zero_crossing_rate(silence()), 0.0)
        self.assertGreater(zero_crossing_rate(noise()), 0.4)     # broadband
        self.assertLess(zero_crossing_rate(voiced()), 0.2)       # low frequency

    def test_features_reports_the_shape_a_caller_needs(self):
        info = features(voiced())
        for key in ("rms", "flatness", "zcr", "tonal", "speech_like"):
            self.assertIn(key, info)
        self.assertTrue(info["speech_like"])

    def test_noise_is_not_speech(self):
        self.assertFalse(features(noise())["speech_like"])
        self.assertFalse(features(silence())["speech_like"])

    def test_a_quiet_room_whisper_is_not_mistaken_for_silence(self):
        """Very quiet but harmonic should still classify as speech-like when it
        is above the absolute floor — the floor, not the classifier, decides
        what is too quiet to hear."""
        info = features(voiced(amplitude=0.02))
        self.assertTrue(info["speech_like"])
        self.assertTrue(features(voiced(amplitude=0.0001))["rms"] < 0.0045)


class FloorTests(unittest.TestCase):
    def test_floor_is_the_percentile_not_the_mean(self):
        floor = NoiseFloor(window_frames=100)
        for _ in range(90):
            floor.push(0.005)
        for _ in range(10):
            floor.push(0.5)              # one loud passage
        self.assertLess(floor.value, 0.05, "a mean would have been dragged to 0.05+")

    def test_floor_has_a_ceiling_independent_of_the_room(self):
        floor = NoiseFloor(window_frames=10)
        for _ in range(10):
            floor.push(0.0)
        self.assertGreater(floor.threshold(), 0.0)          # absolute minimum applies

    def test_empty_floor(self):
        self.assertEqual(NoiseFloor().value, 0.0)


class TurnEndTests(unittest.TestCase):
    def test_speech_then_silence_ends_the_turn(self):
        detector = TurnEndDetector(RATE)
        states = [detector.push(voiced()) for _ in range(12)]     # 360 ms of speech
        self.assertIn("speech", states)
        self.assertTrue(detector.started)
        endeds = [detector.push(silence()) for _ in range(30)]    # 900 ms of quiet
        self.assertIn("end", endeds)
        self.assertFalse(detector.started)

    def test_a_short_cough_does_not_open_a_turn(self):
        detector = TurnEndDetector(RATE)
        for _ in range(3):                                        # 90 ms
            detector.push(voiced())
        self.assertFalse(detector.started)
        for _ in range(5):
            self.assertEqual(detector.push(silence()), "idle")

    def test_typing_does_not_open_a_turn(self):
        detector = TurnEndDetector(RATE)
        for i in range(60):                                       # 1.8 s of clatter
            frame = noise(amplitude=0.3, seed=i)
            detector.push(frame)
        self.assertFalse(detector.started)

    def test_a_mid_sentence_pause_does_not_end_the_turn(self):
        detector = TurnEndDetector(RATE, silence_ms=700)
        for _ in range(10):
            detector.push(voiced())
        for _ in range(8):                                        # 240 ms pause
            detector.push(silence())
        self.assertTrue(detector.started)
        for _ in range(6):
            detector.push(voiced())
        self.assertTrue(detector.started)

    def test_maximum_turn_length_force_ends(self):
        detector = TurnEndDetector(RATE, silence_ms=10_000, max_turn_s=0.5)
        states = [detector.push(voiced()) for _ in range(30)]     # 900 ms, no pause
        self.assertIn("end", states)

    def test_reset_clears_state(self):
        detector = TurnEndDetector(RATE)
        for _ in range(12):
            detector.push(voiced())
        detector.reset()
        self.assertFalse(detector.started)

    def test_empty_frame_is_idle(self):
        self.assertEqual(TurnEndDetector(RATE).push(np.array([])), "idle")

    def test_detection_costs_less_than_a_frame(self):
        """A 30 ms frame must not take 30 ms to classify."""
        import time

        detector = TurnEndDetector(RATE)
        frame = voiced()
        start = time.perf_counter()
        for _ in range(100):
            detector.push(frame)
        per_frame_ms = (time.perf_counter() - start) * 1000 / 100
        self.assertLess(per_frame_ms, 5.0, f"{per_frame_ms:.2f} ms per frame")


if __name__ == "__main__":
    unittest.main()


class EngineWiringTests(unittest.TestCase):
    """The detector as the engine actually calls it.

    `_watch_for_turn_end` takes PCM bytes and is allowed to trigger a flush. The
    test drives it with real 16-bit frames and replaces only the flush, so what
    is exercised is the wiring — attribute names, unit conversion, state
    resets — and not a copy of the logic.
    """

    def _engine(self):
        import providers.engine_pipeline as ep
        from core.audio_features import TurnEndDetector

        engine = ep.PipelineEngine.__new__(ep.PipelineEngine)
        engine._mic = []
        engine._mic_bytes = 0
        engine._detector = None
        engine._vad_floor = ep._VAD_ABSOLUTE_MIN
        engine._vad_speech_ms = 0.0
        engine._vad_quiet_ms = 0.0
        engine._vad_started = False
        engine._log = lambda message: None
        engine.flushes = []

        async def fake_flush(sample_rate: int = 16000) -> str:
            engine.flushes.append(sample_rate)
            return ""

        engine.flush_microphone = fake_flush
        return engine, ep, TurnEndDetector

    @staticmethod
    def _pcm(samples):
        import numpy as np

        return (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()

    def test_speech_then_silence_triggers_one_flush(self):
        import asyncio

        engine, _ep, _det = self._engine()

        async def drive():
            for _ in range(12):                                   # 360 ms speech
                engine._mic.append(self._pcm(voiced()))
                await engine._watch_for_turn_end(self._pcm(voiced()))
            for _ in range(30):                                   # 900 ms quiet
                await engine._watch_for_turn_end(self._pcm(silence()))

        asyncio.run(drive())
        self.assertEqual(len(engine.flushes), 1)

    def test_typing_alone_never_flushes(self):
        import asyncio

        engine, _ep, _det = self._engine()

        async def drive():
            for i in range(80):
                await engine._watch_for_turn_end(self._pcm(noise(amplitude=0.3, seed=i)))

        asyncio.run(drive())
        self.assertEqual(engine.flushes, [])

    def test_the_detector_is_built_lazily_and_reused(self):
        engine, _ep, _det = self._engine()
        self.assertIsNone(engine._detector)
        first = engine._turn_detector()
        self.assertIs(first, engine._turn_detector())

    def test_a_broken_detector_falls_back_instead_of_crashing(self):
        engine, _ep, _det = self._engine()
        engine._detector = False                       # simulate an unavailable path
        self.assertIsNone(engine._turn_detector())
        # ...and the level path still runs and can still end a turn.
        import asyncio

        async def drive():
            for _ in range(20):
                await engine._watch_for_turn_end(self._pcm(voiced()))
            for _ in range(60):
                await engine._watch_for_turn_end(self._pcm(silence()))

        asyncio.run(drive())
        self.assertEqual(len(engine.flushes), 1)

    def test_empty_frames_are_ignored(self):
        import asyncio

        engine, _ep, _det = self._engine()
        asyncio.run(engine._watch_for_turn_end(b""))
        self.assertEqual(engine.flushes, [])
