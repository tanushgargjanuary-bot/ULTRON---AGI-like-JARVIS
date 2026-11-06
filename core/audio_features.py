"""core/audio_features.py — is that speech, and have they finished?

WHAT THIS REPLACES
    `providers/engine_pipeline.py::_watch_for_turn_end` decided with one number:
    the RMS of the frame against a single-pole adaptive floor. Loudness alone
    cannot separate a voice from a keyboard, a fan, a television or a passing
    truck, so two failures follow:

      - the turn never ends while anything in the room is loud (it waits),
      - or the floor rises and a quiet sentence is ignored (it interrupts).

    Both are the top complaints about every voice assistant, and both are
    fixable without a model, because speech and noise differ in ways that are
    visible in a 30 ms spectrum.

THE FEATURES (DAA Unit V: the FFT is not decoration here)
    `spectral_flatness`  geometric mean / arithmetic mean of the power spectrum.
                         White noise has a flat spectrum → ~1.0. Voiced speech is
                         harmonic — a handful of tall narrow peaks → 0.05–0.4.
                         That ratio is the single most useful number in this file.
    `zero_crossing_rate` how often the waveform flips sign. Low for voiced
                         speech (2–12 %), high for fricatives and for hiss.
    `rms`                loudness, still useful, now used for gating rather than
                         for deciding alone.

    Together: a frame is speech-like when it is loud enough for the room AND its
    spectrum is peaky rather than flat. That is three cheap measurements per
    frame, ~1 ms for a 30 ms frame at 16 kHz.

THE FLOOR
    A single-pole tracker (`floor += 0.002*(rms-floor)`) is an exponential moving
    average, which is exactly the wrong statistic for a noise floor: it tracks
    the MEAN of the room, so a long loud passage raises the bar for everything
    after it. This file keeps the 10th percentile of the last two seconds
    instead — the level below which the room is quiet 10 % of the time, which is
    what a noise floor means. It is robust to a single door slam in a way a mean
    is not.

WHY NUMPY IS IMPORTED AT THE TOP HERE
    `main.py` imports numpy for the microphone stream before any of this is
    touched, so there is no launch cost to defer, and the alternative —
    hand-rolled loops in Python — is ~200× slower on a per-frame path. The
    project's lazy-import rule exists for libraries that are *sometimes* needed;
    this one is always resident by the time it is reached.

WHAT IS NOT HERE
    No VAD neural network. A 2 MB model would be more accurate on hard cases
    (whispered speech, heavy background music), and it is a legitimate future
    option — but it needs an informed download decision, and these four
    measurements already beat a fixed threshold by a wide margin.
"""

from __future__ import annotations

import numpy as np

# Thresholds. Each is a parameter with a measured default rather than a constant
# buried in an expression, so a test can move it and a future caller can tune it.
FLATNESS_MAX = 0.72          # above this the spectrum is noise-like
ZCR_MIN = 0.005              # below this it is near-DC hum or silence
ZCR_MAX = 0.45               # above this it is broadband hiss
FLOOR_MARGIN = 2.2           # speech must beat the room by this factor
ABSOLUTE_MIN_RMS = 0.0045    # -47 dBFS, below which nothing is speech
FLOOR_WINDOW_S = 2.0
FLOOR_PERCENTILE = 10.0


def rms(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))


def zero_crossing_rate(samples: np.ndarray) -> float:
    """Fraction of adjacent sample pairs with opposite sign."""
    if samples.size < 2:
        return 0.0
    return float(np.count_nonzero(np.diff(np.signbit(samples))) / (samples.size - 1))


def spectral_flatness(samples: np.ndarray, eps: float = 1e-12) -> float:
    """Geometric-to-arithmetic mean ratio of the power spectrum, 0..1.

    Inclusive of a Hann window: without one, the spectral leakage from a loud
    tone smears across the whole band and makes a pure tone look flat, which
    would invert the meaning of the measurement.
    """
    if samples.size < 8:
        return 1.0
    window = np.hanning(samples.size)
    spectrum = np.abs(np.fft.rfft(samples * window)) ** 2
    spectrum = spectrum[1:]                       # drop DC: it is not spectral content
    if spectrum.size == 0:
        return 1.0
    power = spectrum + eps
    geometric = float(np.exp(np.mean(np.log(power))))
    arithmetic = float(np.mean(power))
    if arithmetic <= 0:
        return 1.0
    return max(0.0, min(1.0, geometric / arithmetic))


def features(samples: np.ndarray) -> dict:
    """Everything this module knows about one frame."""
    level = rms(samples)
    flatness = spectral_flatness(samples)
    zcr = zero_crossing_rate(samples)
    peaky = flatness <= FLATNESS_MAX
    voiced = ZCR_MIN <= zcr <= ZCR_MAX
    return {
        "rms": level,
        "flatness": flatness,
        "zcr": zcr,
        "tonal": peaky,
        "speech_like": bool(level > ABSOLUTE_MIN_RMS and peaky and voiced),
    }


class NoiseFloor:
    """Rolling 10th percentile of frame levels over a window.

    Implemented with a fixed-size ring buffer and `np.percentile` on the live
    slice: O(n log n) on ~66 frames is a few microseconds, and the alternative
    (a histogram or a P² estimator) is more code for less clarity at this size.
    """

    def __init__(self, window_frames: int = 66, percentile: float = FLOOR_PERCENTILE) -> None:
        self._window = max(4, int(window_frames))
        self._percentile = float(percentile)
        self._buffer = np.zeros(self._window, dtype=np.float64)
        self._count = 0
        self._index = 0

    def push(self, level: float) -> None:
        self._buffer[self._index] = float(level)
        self._index = (self._index + 1) % self._window
        self._count = min(self._count + 1, self._window)

    @property
    def value(self) -> float:
        if self._count == 0:
            return 0.0
        return float(np.percentile(self._buffer[: self._count], self._percentile))

    def threshold(self, margin: float = FLOOR_MARGIN) -> float:
        return max(self.value * margin, ABSOLUTE_MIN_RMS)


class TurnEndDetector:
    """Speech-gated turn segmentation with hysteresis.

    `push(samples)` returns one of:

        "idle"    nothing speech-like yet (pre-roll, so a leading consonant is
                  not clipped when the turn does start),
        "speech"  the user is talking,
        "end"     speech happened and then stopped for `silence_ms`.

    Hysteresis is the point: `min_speech_ms` stops a cough from opening a turn,
    and `silence_ms` (longer than any mid-sentence pause) stops a comma from
    closing one.
    """

    def __init__(
        self,
        sample_rate: int,
        *,
        min_speech_ms: float = 220.0,
        silence_ms: float = 700.0,
        max_turn_s: float = 30.0,
        floor_window_s: float = FLOOR_WINDOW_S,
    ) -> None:
        self.sample_rate = int(sample_rate)
        self.min_speech_ms = float(min_speech_ms)
        self.silence_ms = float(silence_ms)
        self.max_turn_s = float(max_turn_s)
        frame_ms = 1000.0 * 0.03
        self._floor = NoiseFloor(window_frames=int(max(4, floor_window_s * 1000.0 / frame_ms)))
        self._speech_ms = 0.0
        self._quiet_ms = 0.0
        self._total_ms = 0.0
        self._started = False

    def reset(self) -> None:
        self._speech_ms = 0.0
        self._quiet_ms = 0.0
        self._total_ms = 0.0
        self._started = False

    @property
    def started(self) -> bool:
        return self._started

    def push(self, samples: np.ndarray) -> str:
        if samples.size == 0:
            return "idle"
        frame_ms = 1000.0 * samples.size / self.sample_rate
        info = features(samples)
        self._total_ms += frame_ms

        if self._started and self._total_ms >= self.max_turn_s * 1000.0:
            # A microphone left open on a noisy room must not hold a turn open
            # forever. Checked before classification, because the failure it
            # prevents happens precisely when every frame looks like speech.
            self.reset()
            return "end"

        # The floor learns ONLY from frames that are not speech-like.
        #
        # Learning from every frame was the first version, and it fails on the
        # simplest possible input: twelve frames of continuous speech in a silent
        # room put the 10th percentile AT the speech level, so the threshold rose
        # above the voice and the user was never heard at all. A noise floor is an
        # estimate of the ROOM, and the room is what is left when nobody is
        # talking.
        if not info["speech_like"]:
            self._floor.push(info["rms"])
        threshold = self._floor.threshold()
        loud = info["rms"] >= threshold

        if loud and info["speech_like"]:
            self._speech_ms += frame_ms
            self._quiet_ms = 0.0
            if self._speech_ms >= self.min_speech_ms:
                self._started = True
            return "speech" if self._started else "idle"

        if not self._started:
            # Loud but not speech (typing, a door): do not accumulate, and do
            # not open a turn on it.
            self._speech_ms = 0.0 if not loud else self._speech_ms
            return "idle"

        self._quiet_ms += frame_ms
        if self._quiet_ms >= self.silence_ms:
            self.reset()
            return "end"
        return "speech"
