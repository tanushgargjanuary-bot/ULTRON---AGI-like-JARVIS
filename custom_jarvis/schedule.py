"""custom_jarvis/schedule.py — when to interrupt you, and when not to.

A reminder system fails in two ways, and both are annoying rather than dangerous:
it says nothing because it has no queue, or it says everything because it has no
order. This module is the queue and the order.

Four rules, and each one answers a complaint the owner actually made:

1. **One score, shared with the decision layer.** A card is ranked by
   `decision.score(chance=urgency, value, cost)` — the same arithmetic that
   chooses an action. So a failing build outranks a new trending repository
   because it scores higher, not because someone hardcoded a list.
2. **Quiet hours are respected** — unless the card is close to an emergency
   (`urgency >= 0.95`), which is the one case where a 3 a.m. sentence is right.
3. **A repeated card has a cooldown.** The same repository cannot be mentioned
   twice in one afternoon.
4. **A card that scores below zero is dropped, not shown.** If being told about
   it is worth less than the interruption costs, the honest action is silence.

State is one small JSON file, so a reminder that was shown at 09:00 is remembered
after a restart.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from custom_jarvis.decision import score as grade

DEFAULT_COOLDOWN = 6 * 3600      # six hours between mentions of one card
EMERGENCY = 0.95                 # high enough to cut through quiet hours


class Queue:
    """A small ordered set of things worth telling you, with a memory."""

    def __init__(self, path: Path | str | None = None, *, quiet_start: int = 23,
                 quiet_end: int = 7, cooldown: int = DEFAULT_COOLDOWN) -> None:
        self.path = Path(path) if path else None
        self.quiet_start = int(quiet_start) % 24
        self.quiet_end = int(quiet_end) % 24
        self.cooldown = max(0, int(cooldown))
        self._cards: dict[str, dict] = {}
        self._shown: dict[str, float] = {}
        self._load()

    # ------------------------------------------------------------- persistence
    def _load(self) -> None:
        if not self.path or not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for key in ("cards", "shown"):
                value = raw.get(key) if isinstance(raw, dict) else None
                if isinstance(value, dict):
                    if key == "cards":
                        self._cards = {str(k): v for k, v in value.items()
                                       if isinstance(v, dict)}
                    else:
                        self._shown = {str(k): float(v) for k, v in value.items()
                                       if isinstance(v, (int, float))}
        except (OSError, ValueError, TypeError):
            self._cards, self._shown = {}, {}

    def _save(self) -> None:
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps({"cards": self._cards, "shown": self._shown},
                                            indent=1, ensure_ascii=False),
                                 encoding="utf-8")
            os.replace(temporary, self.path)
        except OSError:
            pass

    # ------------------------------------------------------------------ cards
    def add(self, identity: str, title: str, *, urgency: float = 0.5,
            value: float = 1.0, cost: float = 0.2,
            cooldown: int | None = None) -> dict:
        """Add or replace one card. `urgency` is the chance it matters today."""
        key = str(identity or "").strip()[:80]
        if not key:
            raise ValueError("a card needs an id")
        card = {"id": key, "title": str(title or "").strip()[:200],
                "urgency": min(1.0, max(0.0, float(urgency))),
                "value": max(0.0, float(value)), "cost": max(0.0, float(cost)),
                "cooldown": self.cooldown if cooldown is None else max(0, int(cooldown))}
        self._cards[key] = card
        self._save()
        return card

    def clear(self) -> None:
        self._cards, self._shown = {}, {}
        self._save()

    def cards(self) -> list[dict]:
        return sorted(self._cards.values(), key=lambda card: card["id"])

    # ------------------------------------------------------------------- time
    def quiet(self, now: float | None = None) -> bool:
        """True inside the quiet window, including a window that crosses midnight."""
        hour = time.localtime(now if now is not None else time.time()).tm_hour
        if self.quiet_start == self.quiet_end:
            return False
        if self.quiet_start < self.quiet_end:
            return self.quiet_start <= hour < self.quiet_end
        return hour >= self.quiet_start or hour < self.quiet_end

    def due(self, now: float | None = None, limit: int = 3) -> list[dict]:
        """The cards worth showing now, best first. Empty means "say nothing"."""
        moment = time.time() if now is None else float(now)
        quiet = self.quiet(moment)
        ranked = []
        for card in self._cards.values():
            if quiet and card["urgency"] < EMERGENCY:
                continue
            last = self._shown.get(card["id"])
            if last is not None and moment - last < card["cooldown"]:
                continue
            worth = grade(card["urgency"], card["value"], card["cost"])
            if worth <= 0:
                continue
            ranked.append({**card, "score": worth,
                           "why": (f"{card['urgency']:.0%} likely to matter, "
                                   f"worth {card['value']:.1f} for a cost of "
                                   f"{card['cost']:.1f}")})
        ranked.sort(key=lambda row: (-row["score"], row["id"]))
        return ranked[: max(1, int(limit))]

    def mark_shown(self, identities: list[str], now: float | None = None) -> None:
        moment = time.time() if now is None else float(now)
        for identity in identities:
            if str(identity) in self._cards:
                self._shown[str(identity)] = moment
        self._save()

    def forget(self, identity: str) -> bool:
        key = str(identity or "")
        self._cards.pop(key, None)
        self._shown.pop(key, None)
        self._save()
        return True
