"""core/branchbound.py — deciding whether to act, or to ask, by search.

THE RULE THIS IMPLEMENTS
    "A calibrated predictor at 70 % or better may act on reversible, unprotected
    actions; below that, ask." Stated as a rule it sounds like one comparison.
    Implemented as one comparison it produces the behaviour people complain
    about: act on the first candidate that squeaks past 0.70, and ignore that a
    second candidate scored 0.69.

    The honest version is a search:

      - each candidate interpretation is a NODE,
      - a node can be refined into more specific interpretations
        ("chrome" → Chrome / Chrome Remote Desktop / Chromium),
      - each node carries an optimistic UPPER bound on how good it could get,
      - nodes whose upper bound cannot reach the threshold are PRUNED,
      - if nothing survives, asking is not a failure mode, it is the answer.

    That is branch-and-bound with the confidence threshold as the pruning bound
    (DAA Unit IV), and it happens to be exactly what a calibrated 0.70 rule
    means when there is more than one candidate.

WHY THE MARGIN MATTERS AS MUCH AS THE THRESHOLD
    0.71 against 0.70 is a coin flip wearing a percentage. `ambiguity_margin`
    says how far clear of the runner-up the winner must be before acting is
    justified; below it, the pair is a genuine ambiguity and a one-line
    question ("Chrome, or Chrome Remote Desktop?") is cheaper than an undo.

WHAT THIS IS NOT
    Not a router and not a permission check. It never grants anything: the
    caller still runs the normal policy and confirmation path afterwards. This
    decides WHICH interpretation to offer, not whether the action is allowed.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any
from core.mental.registry import implements


@dataclass
class Candidate:
    """One interpretation of what the user meant."""

    label: str
    score: float                       # calibrated point estimate, 0..1
    payload: Any = None
    children: Iterable[Candidate] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        self.score = max(0.0, min(1.0, float(self.score)))
        # Normalised here so the search can iterate children repeatedly, in
        # reverse, without re-materialising a generator it has already consumed.
        self.children = tuple(self.children or ())


@dataclass
class Decision:
    chosen: Candidate | None
    ask: bool
    reason: str
    explored: int = 0
    pruned: int = 0
    runner_up: Candidate | None = None
    margin: float = 0.0

    def question(self, lead_in: str = "Did you mean") -> str:
        """The one line to say when asking. Empty when not asking."""
        if not self.ask or self.chosen is None:
            return ""
        if self.runner_up is not None and self.runner_up.label != self.chosen.label:
            return f"{lead_in} {self.chosen.label}, or {self.runner_up.label}?"
        return f"{lead_in} {self.chosen.label}?"


@implements("DAA", 4, "Branch and bound")
def decide(
    candidates: Iterable[Candidate],
    *,
    threshold: float = 0.70,
    ambiguity_margin: float = 0.08,
    optimism: Callable[[Candidate], float] | None = None,
    max_nodes: int = 500,
) -> Decision:
    """Search for an interpretation worth acting on.

    `optimism(candidate)` returns the upper bound for a node. The default is
    "a node cannot be better than the best of itself and its children", which is
    the only bound that is true without knowing anything about the domain. A
    caller that knows more (an edit-distance lower bound, say) should pass a
    tighter one — that is what makes pruning pay.

    `max_nodes` bounds the search: an unbounded expansion on a pathological
    candidate set would be a hang on the keystroke path, and a bounded search
    that gives up and asks is the correct failure.
    """
    roots = list(candidates)
    if not roots:
        return Decision(None, True, "no candidates at all", 0, 0)

    def default_bound(node: Candidate) -> float:
        best = node.score
        for child in node.children:
            best = max(best, default_bound(child))
        return min(1.0, best)

    bound = optimism or default_bound

    explored = 0
    pruned = 0
    survivors: list[Candidate] = []
    # Explicit stack, not recursion: candidate trees are shallow today, but a
    # recursive climb over user-supplied structure is a crash waiting for one
    # deep expander.
    stack = list(reversed(roots))
    while stack and explored < max_nodes:
        node = stack.pop()
        explored += 1
        if bound(node) < threshold:
            # Cannot reach the bar even if every child is perfect.
            pruned += 1
            continue
        survivors.append(node)
        stack.extend(reversed(node.children))

    if not survivors:
        return Decision(None, True, "nothing clears the threshold", explored, pruned)

    # Only LEAVES are answers. A parent that was refined into children is a
    # summary of them, not an alternative to them: without this, "chrome" and
    # the "Chrome" it expands into score the same and the margin rule declares a
    # tie between a thing and itself. If refinement pruned every child, the
    # coarse interpretation is the honest fallback.
    leaves = [node for node in survivors if not node.children]
    if leaves:
        survivors = leaves

    survivors.sort(key=lambda node: -node.score)
    best = survivors[0]
    runner_up = survivors[1] if len(survivors) > 1 else None
    margin = best.score - (runner_up.score if runner_up else 0.0)

    if best.score < threshold:
        return Decision(None, True, "best candidate is below the threshold",
                        explored, pruned, runner_up, margin)
    if runner_up is not None and margin < ambiguity_margin:
        return Decision(best, True, "too close to call",
                        explored, pruned, runner_up, margin)
    return Decision(best, False, "clear winner", explored, pruned, runner_up, margin)
