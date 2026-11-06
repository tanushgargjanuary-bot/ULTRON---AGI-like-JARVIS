"""How much work is worth doing — DAA unit 5, applied to every answer.

An assistant has the same problem a course has: the exact answer to a big instance
takes longer than the question is worth. The syllabus states the shape of that trade:

    unit 1   growth of functions         n log n is fine, 2^n is not, at n = 40
    unit 4   dynamic programming         exact when the table is small enough
    unit 5   NP-completeness             no exact algorithm is coming; approximate
    unit 5   approximation algorithms    a stated ratio now beats a proof later

`plan_work()` turns that into a decision with a sentence attached, so a caller can say
*why* it chose the cheap route instead of leaving the user to wonder.
"""

from __future__ import annotations

import heapq

from core.mental.registry import implements

# What each growth rate costs per input unit, in the same unit as the deadline.
# These are orderings, not measurements: the point is the shape of the curve.
GROWTH = {
    "n": lambda n: n,
    "n_log_n": lambda n: max(1.0, n * max(1.0, n.bit_length())),
    "n_squared": lambda n: n * n,
    "two_to_the_n": lambda n: 2.0 ** min(n, 60),
}


@implements("DAA", 1, "Growth of functions")
def cost_of(growth: str, n: int) -> float:
    """The work a shape of algorithm costs at size n, in arbitrary but comparable units."""
    if growth not in GROWTH:
        raise ValueError(f"unknown growth '{growth}'; I know {', '.join(GROWTH)}")
    return GROWTH[growth](max(1, int(n)))


@implements("DAA", 5, "Approximation algorithms")
def plan_work(n: int, deadline_units: float, shapes=("n_log_n", "n_squared"),
              exact_shape: str = "n_squared") -> dict:
    """Pick the most exact shape that still fits, or say that none does.

    The order is deliberate: try the shapes from the most exact to the least, and take
    the first that fits the budget. If none fits, the answer is not a guess — it is a
    refusal with the number that made it unavoidable.
    """
    n = max(1, int(n))
    for shape in sorted(shapes, key=lambda name: -cost_of(name, n)):
        if cost_of(shape, n) <= deadline_units:
            return {"shape": shape, "exact": shape == exact_shape,
                    "cost": round(cost_of(shape, n), 1),
                    "why": (f"n = {n}: {shape} costs {cost_of(shape, n):,.0f} against "
                            f"a budget of {deadline_units:,.0f}"
                            + ("" if shape == exact_shape else
                               ", so an approximate route is chosen and said out loud"))}
    cheapest = min(shapes, key=lambda name: cost_of(name, n))
    return {"shape": cheapest, "exact": False, "cost": round(cost_of(cheapest, n), 1),
            "why": (f"n = {n} is past what any of these shapes can do inside "
                    f"{deadline_units:,.0f}: the cheapest is {cheapest} at "
                    f"{cost_of(cheapest, n):,.0f}. Answering partially and saying so "
                    f"is the honest option")}


@implements("DS", 4, "Heaps and heap operations")
def top_k(items, key, k: int = 3) -> list:
    """The k best items, in O(n log k) rather than sorting everything.

    A heap, used where it earns its place: the caller has more candidates than it can
    afford to sort, or a stream it cannot sort at all.
    """
    k = max(0, int(k))
    if k == 0:
        return []
    best = heapq.nlargest(k, items, key=key)
    return best


@implements("DAA", 1, "Growth of functions")
def budget_for(n: int, per_item: float = 200.0, ceiling: float = 2_000_000.0) -> float:
    """A work budget that grows with the job but is never unbounded.

    It is expressed in the same units `plan_work` costs in — elementary steps — so the
    two can be compared without a conversion nobody can check. The ceiling is not a
    performance tweak, it is a promise: a job that would take longer than this is a job
    the user has already stopped waiting for, and the honest answer to it is a partial
    one that says so.
    """
    return min(ceiling, max(float(per_item), max(1, int(n)) * float(per_item)))
