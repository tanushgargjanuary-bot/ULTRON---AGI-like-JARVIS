"""A memory hierarchy for what Ultron is allowed to remember in one answer.

The prompt has a character budget, and the syllabus has a name for what happens when a
small fast store sits in front of a big slow one: COA unit 4, the memory hierarchy.
The rules that make it work are the same rules, and they are worth stating because the
project already broke one of them:

    hot     what the current turn is about. Kept, always.
    warm    what was useful recently. Kept while it fits, evicted least-recently-used.
    cold    what was useful once. Kept only if there is room after the other two.

That is a cache with an eviction policy, and a log so a decision can be explained
afterwards — which is DBMS unit 4's log-based recovery, applied to a context block
instead of a database.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.mental.registry import implements

HOT, WARM, COLD = 0, 1, 2
TIER_NAMES = {HOT: "hot", WARM: "warm", COLD: "cold"}


@dataclass
class Piece:
    """One thing that would like to be in the prompt."""

    key: str
    text: str
    tier: int = WARM
    value: float = 1.0
    used_at: int = 0

    @property
    def size(self) -> int:
        return len(self.text)


@dataclass
class Context:
    """A bounded store with three tiers, an LRU rule and a log."""

    budget: int
    pieces: dict = field(default_factory=dict)
    clock: int = 0
    log: list = field(default_factory=list)

    def remember(self, key: str, text: str, tier: int = WARM, value: float = 1.0) -> "Context":
        self.clock += 1
        self.pieces[str(key)] = Piece(str(key), str(text), int(tier), float(value),
                                      self.clock)
        return self

    def touch(self, key: str) -> "Context":
        """Mark a piece as used now, which is what protects it from eviction."""
        if str(key) in self.pieces:
            self.clock += 1
            self.pieces[str(key)].used_at = self.clock
        return self

    @implements("COA", 4, "Cache replacement and write policies")
    def assemble(self) -> dict:
        """Fill the budget tier by tier, and say what was left out and why.

        Within a tier the rule is least-recently-used first, and the tie is broken by
        value. Both are stated rather than implied: a context block that silently
        drops the fact somebody just gave you is the failure this exists to prevent.
        """
        kept, dropped = [], []
        room = max(0, int(self.budget))
        for tier in (HOT, WARM, COLD):
            candidates = sorted((piece for piece in self.pieces.values()
                                 if piece.tier == tier),
                                key=lambda piece: (piece.used_at, piece.value),
                                reverse=True)
            for piece in candidates:
                if piece.size <= room:
                    kept.append(piece)
                    room -= piece.size
                else:
                    dropped.append(piece)
        reply = {"text": "\n".join(piece.text for piece in kept), "kept": kept,
                 "dropped": dropped, "used": int(self.budget) - room}
        self.log.append({"at": self.clock, "used": reply["used"],
                         "kept": [piece.key for piece in kept],
                         "dropped": [piece.key for piece in dropped]})
        return reply

    def evicted(self) -> list[str]:
        """The keys the last assembly could not fit, for an honest sentence."""
        return list(self.log[-1]["dropped"]) if self.log else []


@implements("DBMS", 4, "Log-based recovery")
def replay(entries) -> dict:
    """Rebuild a store from its log, skipping what was never committed.

    The same shape as the config writer's read-modify-write and the self-change
    ledger: an operation that is not recorded did not happen, and an operation that is
    recorded but not committed is not replayed.
    """
    state = {}
    applied, skipped = [], []
    for entry in entries:
        key = entry.get("key")
        if key is None:
            continue
        if not entry.get("committed", True):
            skipped.append(key)
            continue
        state[key] = entry.get("value")
        applied.append(key)
    return {"state": state, "applied": applied, "skipped": skipped}
