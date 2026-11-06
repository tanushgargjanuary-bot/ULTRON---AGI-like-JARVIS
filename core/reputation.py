"""core/reputation.py — how much to trust a tool, as a number with an error bar.

THE PROBLEM WITH "IT WORKED LAST TIME"
    `custom_jarvis/failure_memory.py` already records that a tool failed. What
    nothing does is turn that record into a DECISION. So a tool that failed twice
    yesterday and worked once today is offered with the same confidence as one
    that has worked forty times in a row, and the assistant keeps walking into
    the same wall.

THE MODEL
    Each tool has a Beta(α, β) posterior over its success probability:

        α = prior_successes + successes   (weighted)
        β = prior_failures  + failures

    Beta is the conjugate prior for a coin, which is exactly what "did this tool
    work?" is. Three consequences worth stating:

      - The MEAN is α/(α+β) and it is not what you should rank on. A tool with
        2/2 successes has mean 0.67 and says almost nothing.
      - The LOWER bound (a Beta quantile) is what you should rank on. 2/2 has a
        5 % lower bound around 0.16; 40/42 around 0.83. That is the difference
        between "unproven" and "reliable", expressed numerically.
      - The bound tightens with evidence, automatically. No hand-tuned cutoffs.

    Ranking on a lower bound is also why this cannot be gamed by a lucky streak,
    and why the same 0.70 discipline as the action predictor applies here — one
    rule, two places.

EVIDENCE DECAYS
    A tool whose provider changed behaviour last month should not be judged by
    scores from last year. Evidence is halved on a configurable half-life
    (default: 30 days of wall clock), which keeps `alpha - prior` and
    `beta - prior` shrinking toward the prior without ever losing the prior
    itself. This is exponential forgetting on the SUFFICIENT STATISTICS, not on
    the ratios, so it stays a valid Beta.

PERSISTENCE
    In memory only, with `snapshot()` / `restore()` for whoever wires it up. The
    engine does not decide where state lives; the service above it does.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass

from core.numerics import beta_mean, beta_quantile

DEFAULT_PRIOR_ALPHA = 1.0
DEFAULT_PRIOR_BETA = 1.0
DEFAULT_HALF_LIFE = 30 * 24 * 60 * 60.0        # 30 days in seconds


@dataclass
class Record:
    """Evidence about one subject (a tool name, a provider, a skill)."""

    name: str
    alpha: float = DEFAULT_PRIOR_ALPHA
    beta: float = DEFAULT_PRIOR_BETA
    samples: int = 0
    last_at: float = 0.0

    @property
    def mean(self) -> float:
        return beta_mean(self.alpha, self.beta)

    @property
    def evidence(self) -> float:
        """How much has actually been observed: (α-1)+(β-1)."""
        return max(0.0, (self.alpha - DEFAULT_PRIOR_ALPHA) + (self.beta - DEFAULT_PRIOR_BETA))

    def lower(self, confidence: float = 0.05) -> float:
        """Lower bound of the success probability at `confidence` tail mass.

        `confidence=0.05` means a 95 % one-sided lower bound: the value the
        success rate exceeds with 95 % confidence given what has been seen.
        """
        return beta_quantile(max(1e-9, min(1 - 1e-9, confidence)), self.alpha, self.beta)

    def as_dict(self) -> dict:
        return {"alpha": round(self.alpha, 6), "beta": round(self.beta, 6),
                "samples": self.samples, "last_at": self.last_at}


class Reputation:
    """Thread-safe Beta reputation for named subjects."""

    def __init__(
        self,
        *,
        prior_alpha: float = DEFAULT_PRIOR_ALPHA,
        prior_beta: float = DEFAULT_PRIOR_BETA,
        half_life: float = DEFAULT_HALF_LIFE,
        clock=time.time,
    ) -> None:
        self._prior_alpha = float(prior_alpha)
        self._prior_beta = float(prior_beta)
        self._half_life = float(half_life)
        self._clock = clock
        self._lock = threading.RLock()
        self._records: dict[str, Record] = {}

    # ── evidence ────────────────────────────────────────────────────────────
    def record(self, name: str, ok: bool, weight: float = 1.0) -> Record:
        """Record one outcome. `weight` allows counting a cheap success as less
        than a costly failure, or (weight<1) a soft signal such as a timeout."""
        name = str(name)
        weight = max(0.0, float(weight))
        now = float(self._clock())
        with self._lock:
            entry = self._records.get(name)
            if entry is None:
                entry = Record(name=name, alpha=self._prior_alpha, beta=self._prior_beta)
                self._records[name] = entry
            self._decay(entry, now)
            if ok:
                entry.alpha += weight
            else:
                entry.beta += weight
            entry.samples += 1
            entry.last_at = now
            return entry

    def _decay(self, entry: Record, now: float) -> None:
        """Move the evidence part halfway back to the prior per half-life."""
        if self._half_life <= 0 or entry.last_at <= 0:
            return
        elapsed = now - entry.last_at
        if elapsed <= 0:
            return
        factor = math.pow(0.5, elapsed / self._half_life)
        entry.alpha = self._prior_alpha + (entry.alpha - self._prior_alpha) * factor
        entry.beta = self._prior_beta + (entry.beta - self._prior_beta) * factor

    # ── questions ───────────────────────────────────────────────────────────
    def get(self, name: str) -> Record:
        name = str(name)
        with self._lock:
            entry = self._records.get(name)
            if entry is None:
                return Record(name=name, alpha=self._prior_alpha, beta=self._prior_beta)
            self._decay(entry, float(self._clock()))
            return entry

    def lower(self, name: str, confidence: float = 0.05) -> float:
        return self.get(name).lower(confidence)

    def rank(self, names, confidence: float = 0.05) -> list[tuple[str, float]]:
        """[(name, lower bound)] best first. The list to choose a tool from."""
        scored = [(str(name), self.lower(str(name), confidence)) for name in names]
        scored.sort(key=lambda pair: (-pair[1], pair[0]))
        return scored

    def best(self, names, confidence: float = 0.05, minimum: float = 0.0):
        """Highest lower bound, or None when nothing reaches `minimum`.

        `minimum` is the honest way to say "if I have no evidence worth acting
        on, do not prefer anything" — returning a name regardless would make an
        unproven tool look chosen for a reason.
        """
        ranking = self.rank(names, confidence)
        if not ranking:
            return None
        name, score = ranking[0]
        return name if score >= minimum else None

    def ranked_tools(self, names, confidence: float = 0.05) -> list[str]:
        return [name for name, _ in self.rank(names, confidence)]

    # ── state ───────────────────────────────────────────────────────────────
    def snapshot(self) -> dict:
        with self._lock:
            return {
                "prior_alpha": self._prior_alpha,
                "prior_beta": self._prior_beta,
                "half_life": self._half_life,
                "records": {name: entry.as_dict() for name, entry in self._records.items()},
            }

    def restore(self, data: dict) -> None:
        if not isinstance(data, dict):
            return
        with self._lock:
            self._records.clear()
            for name, payload in (data.get("records") or {}).items():
                if not isinstance(payload, dict):
                    continue
                self._records[str(name)] = Record(
                    name=str(name),
                    alpha=float(payload.get("alpha", self._prior_alpha)),
                    beta=float(payload.get("beta", self._prior_beta)),
                    samples=int(payload.get("samples", 0)),
                    last_at=float(payload.get("last_at", 0.0)),
                )

    def reset(self) -> None:
        with self._lock:
            self._records.clear()
