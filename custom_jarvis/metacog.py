"""custom_jarvis/metacog.py — knowing what it knows, and learning how it learns.

Two capabilities, one small store.

META-COGNITION is knowledge about its own knowledge. Not a mood: a number with a
provenance. Every claim the assistant makes can be recorded with the confidence it
claimed, and later resolved against what actually happened. From those pairs this
module answers three useful questions:

    how reliable am I at this kind of question, with an honest lower bound?
    where am I overconfident — the buckets where I say 90% and I am right 60%?
    given that, should I answer, verify first, or ask?

The lower bound is Wilson's, from `core.numerics`, and deliberately not the raw
ratio: 3-for-3 is not "100% reliable", it is "at least 44%, probably better". An
assistant that reports 100% after three successes is the failure this exists to
prevent.

META-LEARNING is changing behaviour after a mistake. `record_lesson` writes one
sentence — the trigger, the mistake, the rule — and `lessons_for` ranks the stored
rules against a new task by token overlap. `record_attempt` / `choose_strategy`
keep a per-task-type record of which strategy worked, and pick with the same
lower-bound rule, exploring an untried strategy first.

DELIBERATE LIMITS
    No model call, no embeddings, no network. Ranking is token overlap, which is
    boring, inspectable and instant — and it is enough for a store of a few hundred
    lessons.
    Nothing here acts. It records, ranks and advises; the decision stays with the
    caller and the risk tables.
    Bounded: at most MAX_PREDICTIONS resolved rows and MAX_LESSONS rules are kept,
    oldest first out, so this file cannot grow without limit on a machine that
    runs for months.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from pathlib import Path

from core.bandit import UCB1
from core.numerics import wilson_lower
from custom_jarvis.shortlist import rank

MAX_PREDICTIONS = 500
MAX_LESSONS = 300
RECENT_ATTEMPTS = 20
HALF_LIFE_DAYS = 30.0
MAX_ATTEMPTS_PER_STRATEGY = 200

OUTCOMES = {"correct": 1.0, "partly": 0.5, "wrong": 0.0}

_WORD = re.compile(r"[a-z0-9_]+")
_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "it", "this",
    "that", "is", "was", "be", "with", "as", "at", "by", "from", "i", "we", "it's",
    "when", "then", "than", "so", "if", "not", "no", "do", "did", "does",
}

# A confidence below this, once resolved, is not worth prompting about; above the
# high mark the assistant should say it plainly and show the number.
HIGH = 0.90
FAIR = 0.75


def _tokens(text: str) -> set[str]:
    return {word for word in _WORD.findall(str(text or "").lower())
            if word not in _STOP and len(word) > 1}


def _clamp(value, low=0.0, high=1.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return low
    return max(low, min(high, number))


class Ledger:
    """The metacognitive record. One JSON file, written atomically."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._data = self._load()

    # ------------------------------------------------------------------ storage
    def _empty(self) -> dict:
        return {"version": 1, "predictions": [], "lessons": [], "strategies": {}}

    def _load(self) -> dict:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return self._empty()
        if not isinstance(raw, dict):
            return self._empty()
        data = self._empty()
        for key in ("predictions", "lessons"):
            rows = raw.get(key)
            data[key] = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
        strategies = raw.get("strategies")
        data["strategies"] = strategies if isinstance(strategies, dict) else {}
        return data

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._data, ensure_ascii=False, indent=1),
                             encoding="utf-8")
        temporary.replace(self.path)

    # -------------------------------------------------------------- predictions
    def record_prediction(self, claim: str, confidence: float, domain: str = "general") -> dict:
        """Store one claim with the confidence it was stated at."""
        text = str(claim or "").strip()
        if not text:
            raise ValueError("a prediction needs the claim it is about")
        row = {
            "id": uuid.uuid4().hex[:12],
            "claim": text[:400],
            "confidence": round(_clamp(confidence), 3),
            "domain": (str(domain or "general").strip().lower()[:40] or "general"),
            "created": time.time(),
            "outcome": "",
        }
        with self._lock:
            self._data["predictions"].append(row)
            self._prune_predictions()
            self._save()
        return row

    def resolve_prediction(self, record_id: str, outcome: str) -> dict:
        """Say what actually happened: correct, partly, or wrong."""
        key = str(outcome or "").strip().lower()
        if key not in OUTCOMES:
            raise ValueError("outcome must be one of: correct, partly, wrong")
        wanted = str(record_id or "").strip()
        with self._lock:
            for row in self._data["predictions"]:
                if row.get("id") == wanted:
                    row["outcome"] = key
                    row["resolved"] = time.time()
                    self._save()
                    return row
        raise ValueError(f"no prediction with id {wanted!r}")

    def open_predictions(self, domain: str = "", limit: int = 10) -> list[dict]:
        wanted = str(domain or "").strip().lower()
        rows = [row for row in self._data["predictions"]
                if not row.get("outcome")
                and (not wanted or row.get("domain") == wanted)]
        return rows[-limit:]

    def _prune_predictions(self) -> None:
        rows = self._data["predictions"]
        if len(rows) <= MAX_PREDICTIONS:
            return
        # Resolved rows are the ones that can be forgotten; an open prediction is
        # still a question about the world and is never dropped.
        resolved = [row for row in rows if row.get("outcome")]
        keep_open = [row for row in rows if not row.get("outcome")]
        overflow = len(rows) - MAX_PREDICTIONS
        drop = {id(row) for row in resolved[:overflow]}
        self._data["predictions"] = [row for row in rows if id(row) not in drop]

    # ------------------------------------------------------------- calibration
    def calibration(self, domain: str = "") -> dict:
        """Brier score, buckets, and an honest lower bound on accuracy."""
        wanted = str(domain or "").strip().lower()
        rows = [row for row in self._data["predictions"]
                if row.get("outcome")
                and (not wanted or row.get("domain") == wanted)]
        if not rows:
            return {
                "domain": wanted or "all", "n": 0,
                "reliability": None, "lower_bound": None, "brier": None,
                "verdict": "no resolved predictions yet — nothing to be confident about",
                "buckets": [],
            }

        hits = sum(1 for row in rows if OUTCOMES[row["outcome"]] == 1.0)
        brier = sum((_clamp(row["confidence"]) - OUTCOMES[row["outcome"]]) ** 2
                    for row in rows) / len(rows)

        buckets = []
        for low in (0.5, 0.6, 0.7, 0.8, 0.9):
            upper = round(low + 0.1, 1)
            members = [
                row for row in rows
                if low <= _clamp(row["confidence"]) < upper
                or (upper == 1.0 and _clamp(row["confidence"]) == 1.0)
            ]
            if not members:
                continue
            buckets.append({
                "range": f"{int(low * 100)}-{int((low + 0.1) * 100)}%",
                "n": len(members),
                "said": round(sum(_clamp(r["confidence"]) for r in members) / len(members), 3),
                "was_right": round(
                    sum(OUTCOMES[r["outcome"]] for r in members) / len(members), 3),
            })

        bound = wilson_lower(hits, len(rows))
        if bound >= HIGH:
            verdict = "reliable — state it plainly, cite the record"
        elif bound >= FAIR:
            verdict = "usually right — say the number, offer to check"
        elif bound >= 0.5:
            verdict = "unreliable — verify before asserting"
        else:
            verdict = "not yet evidence — ask, or go and check"
        return {
            "domain": wanted or "all",
            "n": len(rows),
            "hits": hits,
            "accuracy": round(hits / len(rows), 3),
            "lower_bound": round(bound, 3),
            "brier": round(brier, 4),
            "verdict": verdict,
            "buckets": buckets,
        }

    def summary(self) -> dict:
        """One compact dict: what to trust, what to watch."""
        return {
            "all": self.calibration(),
            "open": len(self.open_predictions(limit=999)),
            "lessons": len(self._data["lessons"]),
            "domains": sorted({row.get("domain", "general")
                               for row in self._data["predictions"]})[:12],
        }

    # ------------------------------------------------------------------ lessons
    def record_lesson(self, trigger: str, mistake: str, rule: str,
                      domain: str = "general") -> dict:
        """One mistake, one rule. A lesson without a rule is a diary entry."""
        rule_text = str(rule or "").strip()
        if not rule_text:
            raise ValueError("a lesson needs a rule that changes the next attempt")
        row = {
            "id": uuid.uuid4().hex[:12],
            "trigger": str(trigger or "").strip()[:300],
            "mistake": str(mistake or "").strip()[:400],
            "rule": rule_text[:400],
            "domain": (str(domain or "general").strip().lower()[:40] or "general"),
            "created": time.time(),
            "hits": 0,
        }
        with self._lock:
            self._data["lessons"].append(row)
            if len(self._data["lessons"]) > MAX_LESSONS:
                del self._data["lessons"][: len(self._data["lessons"]) - MAX_LESSONS]
            self._save()
        return row

    def lessons_for(self, task: str, limit: int = 5) -> list[dict]:
        """Rank stored rules against a new task: BM25 relevance, then use, then age.

        BM25 rather than a count of shared words, because a word that appears in
        every lesson ("tests") ranks nothing, and a rare word that appears three
        times in one lesson ranks more. `shortlist.py` holds the arithmetic.
        """
        wanted = _tokens(task)
        rows = self._data["lessons"]
        if not rows:
            return []
        if not wanted:
            # No task was given, so relevance cannot decide; use and age can.
            ordered = sorted(rows, key=lambda row: (int(row.get("hits", 0)),
                                                   row.get("created", 0.0)), reverse=True)
            chosen = ordered[: max(1, int(limit))]
        else:
            documents = [{"id": index, "trigger": row.get("trigger", ""),
                          "rule": row.get("rule", ""), "domain": row.get("domain", ""),
                          "row": row} for index, row in enumerate(rows)]
            # The trigger says when the rule applies, so it counts double. The
            # domain is context, so it counts half.
            chosen = [item["document"]["row"]
                      for item in rank(task, documents, limit=max(1, int(limit)),
                                       fields={"trigger": 2.0, "rule": 1.0,
                                               "domain": 0.5})]
        if chosen:
            with self._lock:
                for row in chosen:
                    row["hits"] = int(row.get("hits", 0)) + 1
                self._save()
        return chosen

    # --------------------------------------------------------------- strategies
    def record_attempt(self, task_type: str, strategy: str, success: bool) -> dict:
        kind = str(task_type or "general").strip().lower()[:40] or "general"
        name = str(strategy or "").strip().lower()[:40]
        if not name:
            raise ValueError("an attempt needs the strategy that was used")
        with self._lock:
            table = self._data["strategies"].setdefault(kind, {})
            row = table.setdefault(name, {"tries": 0, "wins": 0})
            row["tries"] = min(int(row.get("tries", 0)) + 1, MAX_ATTEMPTS_PER_STRATEGY)
            if success:
                row["wins"] = min(int(row.get("wins", 0)) + 1, MAX_ATTEMPTS_PER_STRATEGY)
            # A strategy is not a fixed thing: code changes, a dependency moves,
            # and the method that worked in March may fail in November. The last
            # twenty attempts are kept with their times so the choice can weigh
            # what is recent more heavily than what is old.
            recent = row.get("recent")
            if not isinstance(recent, list):
                recent = []
            recent.append({"ok": bool(success), "at": round(time.time(), 1)})
            row["recent"] = recent[-RECENT_ATTEMPTS:]
            self._save()
            return {"task_type": kind, "strategy": name, **row,
                    "lower_bound": round(wilson_lower(row["wins"], row["tries"]), 3)}

    def choose_strategy(self, task_type: str, options: list[str] | None = None) -> dict:
        """Best known strategy by lower bound; try an untried one first."""
        kind = str(task_type or "general").strip().lower()[:40] or "general"
        table = self._data["strategies"].get(kind, {})
        names = [str(option).strip().lower()[:40] for option in (options or []) if str(option).strip()]
        names = [name for name in names if name] or list(table)
        if not names:
            return {"task_type": kind, "strategy": "", "why": "no strategy recorded for this task type",
                    "lower_bound": None}
        untried = [name for name in names if not table.get(name, {}).get("tries")]
        if untried:
            return {"task_type": kind, "strategy": untried[0], "lower_bound": None,
                    "why": "untried — worth one attempt before trusting the rest"}

        # UCB1: mean + an optimism bonus for the option tried least. It is the
        # same decision rule the rest of the project uses for provider choice,
        # and it is the reason a 6-of-6 and a 1-of-6 are not treated as equally
        # trustworthy. Aggregate counts are replayed as individual rewards,
        # because the bandit scores per attempt and not per summary.
        bandit = UCB1(names)
        for name in names:
            row = table[name]
            history = row.get("recent")
            if isinstance(history, list) and history:
                # Decayed replay: a reward halves every HALF_LIFE days, so a
                # method that stopped working loses its lead instead of keeping
                # it for ever.
                for attempt in history[-RECENT_ATTEMPTS:]:
                    age_days = max(0.0, (time.time() - float(attempt.get("at", 0.0)))
                                   / 86400.0)
                    weight = 0.5 ** (age_days / HALF_LIFE_DAYS)
                    bandit.update(name, (1.0 if attempt.get("ok") else 0.0) * weight)
            else:
                for _ in range(int(row["wins"])):
                    bandit.update(name, 1.0)
                for _ in range(int(row["tries"]) - int(row["wins"])):
                    bandit.update(name, 0.0)
        best = bandit.choose() or names[0]
        upper = dict(bandit.scores()).get(best, 0.0)
        row = table[best]
        return {"task_type": kind, "strategy": best, "tries": row["tries"], "wins": row["wins"],
                "lower_bound": round(wilson_lower(row["wins"], row["tries"]), 3),
                "ucb": None if upper == float("inf") else round(upper, 3),
                "recent": len(row.get("recent") or []),
                "why": (f"{row['wins']}/{row['tries']} on record, lower bound "
                        f"{wilson_lower(row['wins'], row['tries']):.2f}; chosen by UCB1, "
                        "which pays a bonus to the option tried least")}

    # ------------------------------------------------------------------- report
    def self_review(self, task: str = "") -> dict:
        """What to do differently, right now, before starting."""
        calibration = self.calibration()
        lessons = self.lessons_for(task, limit=5) if task else []
        watch = []
        for bucket in calibration.get("buckets", []):
            if bucket["n"] >= 3 and bucket["said"] - bucket["was_right"] >= 0.15:
                watch.append(
                    f"overconfident in the {bucket['range']} bucket "
                    f"(said {bucket['said']:.0%}, right {bucket['was_right']:.0%})")
        return {
            "calibration": calibration,
            "lessons": [{"rule": row.get("rule", ""), "trigger": row.get("trigger", "")}
                        for row in lessons],
            "watch": watch,
            "advice": calibration.get("verdict", ""),
        }
