"""core/selfimprove.py — self-improvement that has to prove itself first.

WHAT "RECURSIVE SELF-IMPROVEMENT" CAN HONESTLY MEAN HERE
    The phrase describes a loop where a system proposes changes, measures them,
    and keeps what is measurably better — repeatedly, with each round starting
    from the last one. That loop is real and it is buildable. What is not
    buildable at this scale is the other half of the phrase: a model rewriting
    its own weights. That needs a training pipeline, a GPU, a dataset and a
    licence to ship a different model — none of which this install has, and none
    of which would pay for itself on a 1.5-3 B local model.

    So this module improves the things that are actually Ultron's own: thresholds,
    ranking weights, prompt wording, tool-preference order, retry budgets. Those
    are where its behaviour lives. Each change is proposed, run against a held-out
    set of cases, compared case by case with the current version, and kept only if
    the improvement survives a significance test and breaks nothing.

WHY A SIGNIFICANCE TEST AND NOT "IT SCORED HIGHER"
    A candidate that wins 5 of 8 cases has not been shown to be better; it has
    been shown to be plausible. Running twenty candidates and keeping the best
    guarantees an improvement *on those cases* whether or not one exists — the
    multiple-comparisons problem, and the reason "our benchmark went up" is
    usually noise. So: an exact paired sign test (which needs no distributional
    assumption and is exact at these sample sizes), a minimum effect size, a
    minimum number of cases, and a record of every rejected candidate.

WHY SAFETY CASES ARE SEPARATE
    A change that makes ninety tasks 5% better and one task destroy a file is not
    an improvement, and a mean over all cases would happily accept it. Cases can
    be marked `safety=True`; any regression on one of those rejects the candidate
    outright, whatever the average says.

WHAT THIS MODULE WILL NOT DO
    Apply anything protected. Anything touching code, permissions, the
    confirmation gate or the workspace boundary needs a human — two confirmations,
    as the user required — no matter how good the numbers look. The acceptance
    call is returned as `needs_human`, with the evidence attached, so the human is
    confirming a measured proposal rather than a hunch.
"""

from __future__ import annotations

import json
import math
import random
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from core.numerics import betai

# Cases needed before a comparison is allowed to mean anything. Below this the
# sign test cannot reach p < 0.05 even with a perfect record (6 of 6 gives 0.031;
# 5 of 5 gives 0.0625), so accepting on fewer cases would be accepting on noise.
MIN_CASES = 6


class Case:
    """One thing to be good at, and whether breaking it is disqualifying."""

    __slots__ = ("id", "payload", "safety", "weight")

    def __init__(self, id: str, payload: Any = None, *, safety: bool = False,
                 weight: float = 1.0) -> None:
        self.id = str(id)
        self.payload = payload
        self.safety = bool(safety)
        self.weight = float(weight)

    def __repr__(self) -> str:
        return f"Case({self.id!r}, safety={self.safety})"


class Evaluator(Protocol):
    """Anything that can score a configuration on a case."""

    def cases(self) -> Sequence[Case]:
        ...

    def score(self, value: Any, case: Case) -> float:
        ...


@dataclass
class Artefact:
    """Something that can be tuned, and the rules for tuning it."""

    name: str
    current: Any
    space: Sequence[Any] = ()
    kind: str = "parameter"
    protected: bool = False        # code, permissions, gates: a human decides
    reversible: bool = True
    note: str = ""


@dataclass
class Comparison:
    """Candidate against current, case by case."""

    current_mean: float
    candidate_mean: float
    delta: float
    wins: int
    losses: int
    ties: int
    cases: int
    p_value: float
    safety_regressions: tuple[str, ...] = ()
    per_case: dict[str, tuple[float, float]] = field(default_factory=dict)

    @property
    def significant(self) -> bool:
        return self.p_value < 0.05

    def as_dict(self) -> dict:
        payload = asdict(self)
        payload["safety_regressions"] = list(self.safety_regressions)
        return payload


@dataclass
class Verdict:
    """What the loop decided, and everything it decided it from."""

    accepted: bool
    value: Any
    reason: str
    comparison: Comparison | None = None
    needs_human: bool = False
    tried: int = 0
    seconds: float = 0.0

    def as_dict(self) -> dict:
        return {
            "accepted": self.accepted,
            "value": self.value,
            "reason": self.reason,
            "needs_human": self.needs_human,
            "tried": self.tried,
            "seconds": round(self.seconds, 3),
            "comparison": self.comparison.as_dict() if self.comparison else None,
        }

    def spoken(self) -> str:
        if self.needs_human:
            return "It measured better, but this one needs your approval."
        if self.accepted:
            return f"Kept it: {self.reason}"
        return f"Left it alone: {self.reason}"


def sign_test_p(wins: int, losses: int) -> float:
    """Two-sided exact binomial p-value for a paired comparison.

    Ties are excluded before this is called: a case where nothing changed carries
    no evidence either way.
    """
    trials = int(wins) + int(losses)
    if trials <= 0:
        return 1.0
    k = min(int(wins), int(losses))
    # P(X <= k) for X ~ Binomial(trials, 1/2) is the regularised incomplete beta
    # I_{1/2}(trials - k, k + 1); doubled for two-sided. Checked against the
    # closed forms: 8 wins of 8 gives 0.0078, 6 of 6 gives 0.0313, 5 of 5 gives
    # 0.0625 — which is why MIN_CASES is 6 and not 5.
    tail = betai(trials - k, k + 1, 0.5)
    return min(1.0, 2.0 * tail)


def compare(current: Any, candidate: Any, evaluator: Evaluator,
            cases: Iterable[Case] | None = None) -> Comparison:
    """Score both configurations on the same cases and compare per case."""
    case_list = list(cases if cases is not None else evaluator.cases())
    per_case: dict[str, tuple[float, float]] = {}
    wins = losses = ties = 0
    total_current = total_candidate = 0.0
    regressions: list[str] = []
    for case in case_list:
        before = float(evaluator.score(current, case))
        after = float(evaluator.score(candidate, case))
        per_case[case.id] = (before, after)
        total_current += before
        total_candidate += after
        if after > before:
            wins += 1
        elif after < before:
            losses += 1
            if case.safety:
                regressions.append(case.id)
        else:
            ties += 1
    count = max(1, len(case_list))
    return Comparison(
        current_mean=total_current / count,
        candidate_mean=total_candidate / count,
        delta=(total_candidate - total_current) / count,
        wins=wins,
        losses=losses,
        ties=ties,
        cases=len(case_list),
        p_value=sign_test_p(wins, losses),
        safety_regressions=tuple(regressions),
        per_case=per_case,
    )


def improve(
    artefact: Artefact,
    evaluator: Evaluator,
    *,
    candidates: Sequence[Any] | None = None,
    min_effect: float = 0.02,
    alpha: float = 0.05,
    min_cases: int = MIN_CASES,
    budget: int = 12,
    seed: int | None = 0,
    apply: Callable[[Any], None] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> Verdict:
    """Try candidate values for one artefact; keep the best that earns it.

    Every candidate is compared against the SAME current value on the SAME cases,
    so a candidate is never judged on an easier set than the one it must replace.
    """
    started = clock()
    space = list(candidates if candidates is not None else artefact.space)
    if not space:
        return Verdict(False, artefact.current, "there is nothing to try", seconds=clock() - started)

    cases = list(evaluator.cases())
    if len(cases) < min_cases:
        return Verdict(
            False, artefact.current,
            f"only {len(cases)} cases — {min_cases} are needed before a change can be "
            "called an improvement",
            tried=0, seconds=clock() - started,
        )

    order = list(space)
    random.Random(seed).shuffle(order)
    order = order[: max(0, int(budget))]

    best: tuple[Any, Comparison] | None = None
    tried = 0
    for value in order:
        tried += 1
        comparison = compare(artefact.current, value, evaluator, cases)
        if comparison.safety_regressions:
            continue
        if comparison.delta < min_effect:
            continue
        if comparison.p_value >= alpha:
            continue
        if best is None or comparison.delta > best[1].delta:
            best = (value, comparison)

    if best is None:
        return Verdict(
            False, artefact.current,
            "nothing tried was better by enough to be believed",
            tried=tried, seconds=clock() - started,
        )

    value, comparison = best
    reason = (
        f"{comparison.wins}/{comparison.cases} cases better, "
        f"{comparison.losses} worse, mean +{comparison.delta:.3f} (p={comparison.p_value:.4f})"
    )

    if artefact.protected or not artefact.reversible:
        why = "protected" if artefact.protected else "not reversible"
        return Verdict(
            False, value,
            f"{reason} — but this artefact is {why}, so a human decides",
            comparison=comparison, needs_human=True, tried=tried,
            seconds=clock() - started,
        )

    if apply is not None:
        try:
            apply(value)
        except Exception as exc:              # noqa: BLE001 - a failed apply is not an accept
            return Verdict(
                False, artefact.current, f"applying it failed: {type(exc).__name__}: {exc}",
                comparison=comparison, tried=tried, seconds=clock() - started,
            )
    return Verdict(
        True, value, reason, comparison=comparison, tried=tried,
        seconds=clock() - started,
    )


@dataclass
class Entry:
    """One accepted change, with enough context to undo it."""

    artefact: str
    before: Any
    after: Any
    delta: float
    p_value: float
    at: float = 0.0

    def as_dict(self) -> dict:
        return asdict(self)


class Lineage:
    """Every change ever accepted, in order, with the ability to go back one."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self.entries: list[Entry] = []

    def record(self, artefact: str, before: Any, after: Any, comparison: Comparison) -> Entry:
        entry = Entry(artefact, before, after, comparison.delta, comparison.p_value,
                      at=self._clock())
        self.entries.append(entry)
        return entry

    def history(self, artefact: str) -> list[Entry]:
        return [entry for entry in self.entries if entry.artefact == artefact]

    def previous(self, artefact: str) -> Any:
        """The value before the last accepted change, or None."""
        changes = self.history(artefact)
        return changes[-1].before if changes else None

    def snapshot(self) -> dict:
        return {"entries": [entry.as_dict() for entry in self.entries]}

    def restore(self, payload: dict | None) -> None:
        self.entries = []
        for raw in (payload or {}).get("entries") or []:
            try:
                self.entries.append(Entry(**raw))
            except (TypeError, ValueError):
                continue

    def to_json(self) -> str:
        return json.dumps(self.snapshot(), ensure_ascii=False)


class Budget:
    """How much self-improvement a session is allowed to attempt.

    Not a rate limit for its own sake: the loop runs models locally and produces
    changes nobody asked for, so it stops. An assistant that tunes itself forever
    in the background is not improving, it is drifting.
    """

    def __init__(self, max_experiments: int = 20, max_seconds: float = 900.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.max_experiments = max(0, int(max_experiments))
        self.max_seconds = max(0.0, float(max_seconds))
        self._clock = clock
        self._started = clock()
        self.used = 0

    def remaining(self) -> int:
        return max(0, self.max_experiments - self.used)

    def spend(self, count: int = 1) -> bool:
        if self.stopped():
            return False
        self.used += max(0, int(count))
        return True

    def stopped(self) -> bool:
        return self.remaining() == 0 or (self._clock() - self._started) >= self.max_seconds

    def reason(self) -> str:
        if self.remaining() == 0:
            return "experiment budget spent"
        if (self._clock() - self._started) >= self.max_seconds:
            return "time budget spent"
        return ""


def wilson_interval(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    """A confidence interval for a success rate, for reporting rather than gating."""
    from core.numerics import wilson_lower

    if trials <= 0:
        return (0.0, 1.0)
    low = wilson_lower(successes, trials, z)
    high = 1.0 - wilson_lower(trials - successes, trials, z)
    if not math.isfinite(high):
        high = 1.0
    return (max(0.0, low), min(1.0, high))
