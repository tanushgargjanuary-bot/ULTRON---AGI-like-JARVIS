"""Notice when Ultron itself gets slower, without a threshold that goes stale.

A fixed alarm ("a turn over 6 s is slow") is wrong twice: it fires on a slow
machine for ever, and it stays silent on a fast machine that just got five times
slower. This module compares each new measurement with the recent past instead.

Two numbers do the work:

- an **exponentially weighted mean** (EWMA), so the baseline follows the machine
  without storing history;
- a **spread** from the same weighting, so the comparison is in standard
  deviations — a "z-score" — rather than in seconds.

The alarm is a z-score above `sigmas`, and it stays quiet until `minimum`
measurements exist, because a spread over three samples is not a spread.
"""

from __future__ import annotations

import math
import threading
from typing import Any


class Monitor:
    """Moving baseline plus z-score for one measurement, e.g. seconds per turn."""

    def __init__(self, *, alpha: float = 0.2, minimum: int = 8, sigmas: float = 3.0,
                 label: str = "turn") -> None:
        self.alpha = min(0.99, max(0.01, float(alpha)))
        self.minimum = max(2, int(minimum))
        self.sigmas = max(1.0, float(sigmas))
        self.label = str(label or "turn")
        self._lock = threading.RLock()
        self._count = 0
        self._mean = 0.0
        self._spread = 0.0
        self._last = 0.0
        self._last_z = 0.0
        self._prior = 0.0
        self._alerts = 0

    def observe(self, value: Any) -> dict:
        """Add one measurement and return the comparison, including `alert`."""
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("a measurement must be a finite number")
        with self._lock:
            deviation = math.sqrt(max(0.0, self._spread))
            # Compare against the baseline that was established BEFORE this
            # measurement. Comparing after would let an outlier widen the spread
            # that judges it, and a real slowdown would hide itself.
            floor = max(1e-6, 0.02 * abs(self._mean))
            z_score = 0.0 if deviation <= floor and number == self._mean \
                else (number - self._mean) / max(deviation, floor)
            if self._count == 0:
                z_score = 0.0
            self._prior = self._mean
            difference = number - self._mean
            if self._count == 0:
                self._mean = number
                self._spread = 0.0
            else:
                self._mean += self.alpha * difference
                self._spread = (1.0 - self.alpha) * (
                    self._spread + self.alpha * difference * difference)
            self._count += 1
            self._last, self._last_z = number, z_score
            alert = self._count > self.minimum and z_score >= self.sigmas
            if alert:
                self._alerts += 1
            return {"value": round(number, 3), "mean": round(self._mean, 3),
                    "spread": round(deviation, 3), "z": round(z_score, 2),
                    "samples": self._count, "alert": alert,
                    "note": self._note(number, alert)}

    def _note(self, number: float, alert: bool) -> str:
        if self._count <= self.minimum:
            return (f"still learning what normal is for a {self.label} "
                    f"({self._count} of {self.minimum + 1} measurements)")
        if alert:
            # Past ten, the exact figure stops informing anyone: the machine was
            # steady and this was not. The number stays in the data; the sentence
            # stays readable.
            size = ("more than ten standard deviations" if self._last_z >= 10
                    else f"{self._last_z:.1f} standard deviations")
            return (f"a {self.label} took {number:.1f} s — {size} above the "
                    f"usual {self._prior:.1f} s")
        return f"usual {self.label} is about {self._mean:.1f} s"

    def status(self) -> dict:
        with self._lock:
            return {"label": self.label, "samples": self._count,
                    "mean": round(self._mean, 3), "spread": round(self._spread ** 0.5, 3),
                    "last": round(self._last, 3), "last_z": round(self._last_z, 2),
                    "alerts": self._alerts,
                    "note": self._note(self._last, self._count > self.minimum
                                       and self._last_z >= self.sigmas)}
