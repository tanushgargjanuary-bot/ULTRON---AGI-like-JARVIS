"""Choose between candidate actions with arithmetic, not with a feeling.

A decision system is three numbers and one rule:

    score = p(success) x value - cost - risk penalty

`p` is supplied by the caller — in practice by the calibration record in
`metacog.py`, which is why that ledger exists. `value` and `cost` are in the same
unit (anything consistent), and `risk` is the project's own tier name.

The rule that makes this worth having is the refusal: when every option scores
below zero, the honest answer is "do none of these", not "pick the least bad".
An assistant that always has a recommendation is not deciding, it is performing.
"""

from __future__ import annotations

from typing import Any, Iterable

from core.numerics import wilson_lower

# Subtracted from the score. The names match the risk tiers the rest of the
# project already uses, and a blocked option is not scored at all: it loses.
RISK_PENALTY = {"routine": 0.0, "guarded": 0.15, "confirm": 0.4, "blocked": 1.0}


def _number(value: Any, name: str, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number, not {value!r}") from None
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"{name} must be finite")
    if not low <= number <= high:
        raise ValueError(f"{name} must be between {low} and {high}, not {number}")
    return number


def score(p: Any, value: Any = 1.0, cost: Any = 0.0, risk: Any = "routine") -> float:
    """One candidate's expected worth. Higher is better; below zero means "no"."""
    probability = _number(p, "p", 0.0, 1.0)
    worth = max(0.0, float(value))
    price = max(0.0, float(cost))
    tier = str(risk or "routine").strip().lower()
    if tier not in RISK_PENALTY:
        raise ValueError(f"unknown risk {risk!r}; expected one of {sorted(RISK_PENALTY)}")
    if tier == "blocked":
        return float("-inf")
    return round(probability * worth - price - RISK_PENALTY[tier], 4)


def from_record(wins: int, tries: int) -> float:
    """The chance to use when the evidence is a record: its Wilson lower bound.

    A raw ratio says 1 of 1 is a 100% chance. It is not. The lower bound says
    what the record still supports after the small sample is accounted for, which
    is the only version of the number a decision can safely be built on.
    """
    attempts, hits = int(tries), int(wins)
    if attempts <= 0:
        raise ValueError("a record needs at least one attempt")
    if not 0 <= hits <= attempts:
        raise ValueError("wins must be between 0 and tries")
    return round(wilson_lower(hits, attempts), 4)


def _probability(candidate: dict) -> Any:
    """`p` if it is given, otherwise the honest bound from wins/tries."""
    if candidate.get("p") is not None:
        return candidate.get("p")
    if candidate.get("wins") is not None and candidate.get("tries") is not None:
        return from_record(candidate["wins"], candidate["tries"])
    return None


def choose(candidates: Iterable[dict], limit: int = 3) -> dict:
    """Rank candidate actions and name the one to take, or refuse to name one.

    A candidate is a dict: `{"name", "p", "value", "cost", "risk"}`. Only `p` is
    required; value defaults to 1.0, cost to 0.0, risk to "routine".
    """
    rows = []
    for index, candidate in enumerate(candidates or ()):
        if not isinstance(candidate, dict):
            raise ValueError("each candidate must be an object")
        name = str(candidate.get("name") or candidate.get("action") or
                   f"option {index + 1}").strip()[:80]
        chance = _probability(candidate)
        rows.append({
            "name": name,
            "score": score(chance, candidate.get("value", 1.0),
                           candidate.get("cost", 0.0), candidate.get("risk", "routine")),
            "risk": str(candidate.get("risk") or "routine").strip().lower(),
            "p": chance,
        })

    if not rows:
        return {"choice": "", "score": None, "refused": True, "ranked": [],
                "why": "no candidate was given, so there is nothing to decide"}

    rows.sort(key=lambda row: (-row["score"], row["name"]))
    ranked = [{"name": row["name"], "score": None if row["score"] == float("-inf")
               else row["score"], "risk": row["risk"]} for row in rows[: max(1, int(limit))]]
    best = rows[0]

    if best["score"] == float("-inf"):
        return {"choice": "", "score": None, "refused": True, "ranked": ranked,
                "why": "every option is blocked by a rule I am not allowed to break"}
    if best["score"] < 0:
        return {"choice": "", "score": best["score"], "refused": True, "ranked": ranked,
                "why": ("every option is worth less than it costs, so none of them "
                        f"should be done — the best was {best['name']!r} at "
                        f"{best['score']:+.2f}")}
    return {"choice": best["name"], "score": best["score"], "refused": False,
            "ranked": ranked,
            "why": (f"highest expected value: {best['name']!r} at {best['score']:+.2f} "
                    f"(stated chance {best['p']}, risk {best['risk']})")}
