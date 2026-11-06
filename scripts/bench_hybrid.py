"""scripts/bench_hybrid.py — what a faster language buys, measured, not argued.

    python scripts/bench_hybrid.py

Three ways to compute the same thing — the level of one audio frame (peak, RMS,
zero crossings) — and one number each:

    pure Python   a loop over the samples
    numpy         the same arithmetic, vectorised
    C             native/frame.c, compiled with gcc and called through ctypes

The point is not that C wins. It is that the answer is known before anyone spends
a year rewriting a program in it. A rewrite is worth it when a hot leaf dominates
a turn. Today the dominant term is the network round trip to a model, so this
benchmark is the instrument that says so, and the argument for a hybrid: keep the
shell where it is, move the leaf if the leaf ever gets heavy.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FRAME_RATE = 16000
FRAME_MS = 30.0
FRAME = int(FRAME_RATE * FRAME_MS / 1000.0)      # 480 samples, the app's own size
ROUNDS = 4000


def signal(seed: int = 7) -> list[int]:
    """A frame that looks like speech: a tone, a wobble and a little noise."""
    import math
    import random

    rng = random.Random(seed)
    out = []
    for index in range(FRAME):
        t = index / FRAME_RATE
        value = (9000 * math.sin(2 * math.pi * 220 * t)
                 + 2500 * math.sin(2 * math.pi * 640 * t)
                 + rng.randint(-700, 700))
        out.append(int(max(-32768, min(32767, value))))
    return out


def level_python(samples) -> tuple[int, int, int]:
    peak = 0
    total = 0
    crossings = 0
    previous = 0
    for index, value in enumerate(samples):
        magnitude = -value if value < 0 else value
        if magnitude > peak:
            peak = magnitude
        total += value * value
        if index and ((value >= 0) != (previous >= 0)):
            crossings += 1
        previous = value
    return peak, int((total / len(samples)) ** 0.5), crossings


def level_numpy(samples):
    import numpy as np

    data = np.asarray(samples, dtype=np.int32)
    peak = int(np.abs(data).max())
    rms = int(np.sqrt((data * data).mean()))
    crossings = int(np.count_nonzero(np.diff(data >= 0)))
    return peak, rms, crossings


def load_c():
    for name in ("libframe.so", "libframe.dylib", "frame.dll"):
        path = ROOT / "native" / name
        if path.exists():
            library = ctypes.CDLL(str(path))
            break
    else:
        return None

    class Level(ctypes.Structure):
        _fields_ = [("peak", ctypes.c_int), ("rms", ctypes.c_int),
                    ("crossings", ctypes.c_int)]

    library.frame_level.restype = Level
    library.frame_level.argtypes = [ctypes.POINTER(ctypes.c_int16), ctypes.c_int]

    def run(samples):
        buffer = (ctypes.c_int16 * len(samples))(*samples)
        out = library.frame_level(buffer, len(samples))
        return out.peak, out.rms, out.crossings

    run.pointer = library          # exposed for the zero-copy row below
    return run


def time_it(function, samples, rounds: int) -> float:
    """Microseconds per frame, by the median of `rounds` single calls."""
    marks = []
    for _ in range(rounds):
        started = time.perf_counter()
        function(samples)
        marks.append((time.perf_counter() - started) * 1_000_000)
    return statistics.median(marks)


def main() -> int:
    samples = signal()
    reference = level_python(samples)

    print(f"One audio frame: {FRAME} samples at {FRAME_RATE} Hz "
          f"({FRAME_MS:.0f} ms), {ROUNDS} rounds each.")
    print(f"peak {reference[0]}, rms {reference[1]}, "
          f"zero crossings {reference[2]}\n")

    rows = [("pure Python", lambda s: level_python(s), True)]

    try:
        import numpy  # noqa: F401
        rows.append(("numpy", level_numpy, True))
    except Exception as exc:                                  # noqa: BLE001
        print(f"numpy is not installed ({exc}) — that row is skipped, not guessed.")

    native = load_c()
    if native:
        rows.append(("C through ctypes", native, True))
        # The real pipeline receives its samples from sounddevice as one
        # contiguous int16 array, so the C call can take a pointer straight into
        # it. Timing that separately is the difference between "C is fast" and
        # "getting the data to C is slow" — and it is the honest hybrid number.
        try:
            import numpy as np

            at_once = np.asarray(samples, dtype=np.int16)
            pointer = at_once.ctypes.data_as(ctypes.POINTER(ctypes.c_int16))
            library = native.pointer

            def native_no_copy(_samples):
                out = library.frame_level(pointer, len(at_once))
                return out.peak, out.rms, out.crossings

            rows.append(("C, buffer already there", native_no_copy, True))
        except Exception as exc:                              # noqa: BLE001
            print(f"zero-copy row skipped: {exc}")
    else:
        print("native/libframe.so is not built — run: "
              "gcc -O2 -shared -fPIC native/frame.c -o native/libframe.so")

    print(f"{'way':22s} {'microseconds':>13s} {'of a 30 ms frame':>18s} "
          f"{'speed-up':>9s}  agrees")
    baseline = None
    for name, function, _ in rows:
        result = function(samples)
        agrees = "yes" if tuple(result) == tuple(reference) else f"NO {result}"
        micro = time_it(function, samples, ROUNDS)
        baseline = baseline or micro
        share = micro / (FRAME_MS * 1000.0) * 100.0
        print(f"{name:22s} {micro:13.3f} {share:17.3f}% "
              f"{baseline / micro:8.1f}x  {agrees}")

    print("\nWhat this means for Ultron:")
    print("  The whole audio path costs a fraction of one percent of the audio it")
    print("  processes in every column. The turn is spent waiting for a model and")
    print("  for speech recognition — both already outside Python. A rewrite of the")
    print("  shell would move none of that. A hybrid keeps the shell and moves a")
    print("  leaf, and this is the measurement that says whether a leaf is heavy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
