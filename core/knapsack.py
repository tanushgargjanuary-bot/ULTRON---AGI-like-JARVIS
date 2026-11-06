"""core/knapsack.py — filling a context budget by value rather than by order.

THE PROBLEM
    Every model call carries a fixed character budget: memory entries, recent
    turns, tool results, the prompt itself. Today the memory block is chosen by
    recency and `_trimmed()` drops history from the front when the budget is
    exceeded. Both are FIFO policies, and FIFO is why a 12 KB tool result can
    evict six facts that a later question needed.

    "Choose a subset of items, each with a value and a size, maximising total
    value under a size limit" is 0/1 knapsack — DAA Unit IV's resource
    allocation problem, with tokens as the resource.

WHY NOT JUST RUN THE DP
    Exact 0/1 knapsack is O(n·W) where W is the capacity in integer units. With
    a 12,000-token budget measured in tokens, that is 12,000 × n cells: fine for
    40 candidates, wasteful for 400, and it allocates a table on a path that
    runs before every model call. So:

      - exact DP when `n * capacity_units` is small (default 200 000 cells),
      - otherwise the 2-approximation below, whose error is invisible in a
        prompt and whose cost is a sort.

THE 2-APPROXIMATION, AND WHY IT IS VALID
    Sort by value/weight and take items while they fit; when the next one does
    not, remember it as the BREAK ITEM. Return the better of:

        (a) the items taken so far, and
        (b) the break item alone.

    Argument: the fractional-relaxation optimum z* is at least the integer
    optimum, and greedy achieves exactly z* (plus a fraction of the break item).
    If the fraction contributes less than half of z*, then the whole items
    already contribute more than half; if it contributes more than half, the
    break item on its own does — and it fits, since a fraction of it does. So
    max(a, b) >= z*/2 >= OPT/2. This is the standard proof and the reason the
    code takes a `max` instead of just trusting the greedy prefix, which alone
    has no bound at all.

    (Taking only the greedy prefix and stopping is a common bug: one heavy item
    at the front can empty the knapsack.)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    """One candidate for a budget. `name` is for reporting, not for logic."""

    name: str
    value: float
    weight: int

    @property
    def ratio(self) -> float:
        return self.value / self.weight if self.weight > 0 else float("inf")


@dataclass
class Selection:
    chosen: list[Item]
    value: float
    weight: int
    exact: bool
    # How the answer was obtained: "exact", "greedy+break", "single"
    method: str = ""

    @property
    def overflow(self) -> int:
        return max(0, self.weight - 0)


def _clean(items) -> list[Item]:
    """Free items are taken unconditionally; negative values are dropped.

    An item with no weight is free value, so it never competes for budget. An
    item with negative value would let the optimiser "pay" for space it does not
    have; dropping it is simpler and matches the caller's intent.
    """
    return [item for item in items if item.weight >= 0 and item.value > 0]


def solve_exact(items: list[Item], capacity: int) -> Selection:
    """0/1 knapsack by dynamic programming over integer capacity.

    A FULL (n+1) x (capacity+1) table, not the usual one-row trick. The one-row
    version computes the optimal VALUE correctly but cannot reconstruct WHICH
    items produced it: the backpointers it leaves behind describe states from
    intermediate rows, not the final one, and reconstruction silently returns a
    different, cheaper set. That is a bug that passes every value-only test and
    fails only when you look at what was chosen — so the table is kept, and
    `exact_cells` in `solve()` is what bounds its size.

    Time O(n·W), space O(n·W).
    """
    free = [item for item in items if item.weight == 0]
    paid = [item for item in items if item.weight > 0]
    if capacity <= 0:
        return Selection(list(free), sum(item.value for item in free), 0, True, "exact")
    if not paid:
        return Selection(list(free), sum(item.value for item in free), 0, True, "exact")

    # Values are scaled to integers so the DP compares exact numbers instead of
    # accumulating float error across thousands of additions.
    scale = 1_000_000
    values = [max(0, round(item.value * scale)) for item in paid]

    rows = len(paid) + 1
    table = [[0] * (capacity + 1) for _ in range(rows)]
    for i in range(1, rows):
        weight, value = paid[i - 1].weight, values[i - 1]
        row, previous = table[i], table[i - 1]
        for c in range(capacity + 1):
            row[c] = previous[c]
            if weight <= c:
                candidate = previous[c - weight] + value
                row[c] = max(row[c], candidate)

    chosen: list[Item] = []
    c = capacity
    for i in range(rows - 1, 0, -1):
        if table[i][c] != table[i - 1][c]:
            chosen.append(paid[i - 1])
            c -= paid[i - 1].weight
    chosen.reverse()
    chosen = free + chosen
    return Selection(
        chosen=chosen,
        value=sum(item.value for item in chosen),
        weight=sum(item.weight for item in chosen),
        exact=True,
        method="exact",
    )


def solve_greedy(items: list[Item], capacity: int) -> Selection:
    """The 2-approximation: greedy by ratio, then `max(greedy, break item)`."""
    ordered = sorted(_clean(items), key=lambda item: (-item.ratio, item.name))
    taken: list[Item] = []
    used = 0
    break_item: Item | None = None

    for item in ordered:
        if used + item.weight <= capacity:
            taken.append(item)
            used += item.weight
        elif item.weight <= capacity:
            break_item = item          # fits alone, but not on top of the rest
            break

    greedy_value = sum(item.value for item in taken)
    if break_item is not None and break_item.value > greedy_value:
        return Selection([break_item], break_item.value, break_item.weight, False, "single")
    return Selection(taken, greedy_value, used, False, "greedy+break")


def solve(items, capacity: int, *, exact_cells: int = 200_000) -> Selection:
    """Best available answer for this size of problem.

    `exact_cells` is the point where the table stops being worth allocating on a
    per-turn path. It is a parameter rather than a constant so a test can force
    the exact path and compare the two.
    """
    items = _clean(list(items))
    if capacity <= 0:
        return Selection([], 0.0, 0, True, "exact")
    if not items:
        return Selection([], 0.0, 0, True, "exact")

    free = [item for item in items if item.weight == 0]
    paid = [item for item in items if item.weight > 0]
    free_value = sum(item.value for item in free)
    free_weight = sum(item.weight for item in free)

    if len(paid) * (capacity + 1) <= exact_cells:
        result = solve_exact(paid, capacity)
    else:
        result = solve_greedy(paid, capacity)

    result.chosen = free + result.chosen
    result.value += free_value
    result.weight += free_weight
    return result
