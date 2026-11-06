"""Consent-first, local preference insights. No model calls, recording or self-rewrites.

Only approved enum preferences reach disk. Candidate evidence and future-task
suggestions expire in RAM. This is phrase matching, not mind reading or diagnosis.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
import uuid
from pathlib import Path

ALLOWED = {
    "response_length": {"concise", "detailed"},
    "tone": {"friendly", "professional"},
    "planning_style": {"checklist", "step_by_step"},
}
RULES = (
    (
        "response_length",
        "concise",
        r"\b(?:keep (?:it|answers|replies) short|minimal wording|be brief|short answers|concise replies|no long explanations|short mein)\b",
    ),
    (
        "response_length",
        "detailed",
        r"\b(?:more detail|detailed answers|explain in detail|thorough explanation|detail mein)\b",
    ),
    ("tone", "friendly", r"\b(?:friendly tone|talk casually|be more casual)\b"),
    (
        "tone",
        "professional",
        r"\b(?:professional tone|formal tone|keep it professional)\b",
    ),
    (
        "planning_style",
        "checklist",
        r"\b(?:give me a checklist|prefer checklists|use checklists)\b",
    ),
    ("planning_style", "step_by_step", r"\b(?:step by step|step-by-step)\b"),
)
TASKS = (
    (
        r"\b(?:meeting|interview)\b",
        "Meeting readiness",
        [
            "Clarify the goal and participants",
            "Draft three talking points",
            "List questions and required documents",
        ],
    ),
    (
        r"\b(?:presentation|presenting)\b",
        "Presentation readiness",
        [
            "Outline the audience and main message",
            "Draft the slide sequence",
            "Prepare a rehearsal checklist",
        ],
    ),
    (
        r"\b(?:release|deploy|deployment)\b",
        "Release readiness",
        [
            "Review changes and regression checks",
            "Check configuration and backups",
            "Prepare rollback and post-release checks",
        ],
    ),
    (
        r"\b(?:exam|study|studying)\b",
        "Study readiness",
        [
            "List the topics and deadline",
            "Choose a short study block",
            "Draft a self-test checklist",
        ],
    ),
)


class InsightEngine:
    def __init__(self, path=None, clock=time.monotonic):
        base = Path(
            os.environ.get("LOCALAPPDATA")
            or os.environ.get("XDG_DATA_HOME")
            or Path.home() / ".local" / "share"
        )
        self.path = (
            Path(path) if path else base / "CustomMarkJarvis" / "approved-insights.json"
        )
        self.clock = clock
        self.lock = threading.RLock()
        self.approved = {}
        self.pending = {}
        self.suggestions = {}
        self.last_text = None
        self.last_at = 0.0
        try:
            if self.path.stat().st_size <= 16384:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self.approved = {
                        k: v
                        for k, v in raw.items()
                        if k in ALLOWED and isinstance(v, str) and v in ALLOWED[k]
                    }
        except (OSError, ValueError):
            pass

    def _prune(self):
        now = self.clock()
        self.pending = {k: v for k, v in self.pending.items() if now - v["at"] < 3600}
        self.suggestions = {
            k: v for k, v in self.suggestions.items() if now - v["at"] < 3600
        }

    def observe(self, text):
        if not isinstance(text, str) or not text.strip():
            return
        text = text.strip()[:4000]
        # Do not retain or analyse likely credentials/sensitive records.
        if re.search(
            r"(?:gsk_|sk-)[A-Za-z0-9_-]{12,}|\b(?:password|api.?key|credit card|diagnosis|medical record)\b",
            text,
            re.I,
        ):
            return
        with self.lock:
            self._prune()
            # Store a digest, not a second transcript copy, for deduplication.
            import hashlib

            digest = hashlib.sha256(text.encode()).hexdigest()
            if digest == self.last_text and self.clock() - self.last_at < 5:
                return
            self.last_text, self.last_at = digest, self.clock()
            for key, value, pattern in RULES:
                match = re.search(pattern, text, re.I)
                if match is None:
                    continue
                prefix = text[max(0, match.start() - 18) : match.start()].lower()
                if re.search(
                    r"\b(?:don't|do not|not|avoid|never)\s+(?:be\s+)?$", prefix
                ):
                    continue
                if self.approved.get(key) == value:
                    continue
                # One latest proposal per preference, never an inferred fact.
                self.pending = {
                    i: row for i, row in self.pending.items() if row["key"] != key
                }
                identity = uuid.uuid4().hex
                self.pending[identity] = {
                    "id": identity,
                    "key": key,
                    "value": value,
                    "evidence": text[max(0, match.start() - 20) : match.end() + 60][
                        :120
                    ],
                    "at": self.clock(),
                }
            for pattern, title, steps in TASKS:
                if re.search(pattern, text, re.I):
                    self.suggestions[title] = {
                        "title": title,
                        "draft": list(steps),
                        "at": self.clock(),
                        "scope": "Suggestion only; no files created, tools run, reminder scheduled or deadline inferred.",
                    }
            while len(self.pending) > 16:
                self.pending.pop(next(iter(self.pending)))

    def review(self):
        with self.lock:
            self._prune()
            return json.loads(
                json.dumps(
                    {
                        "approved": self.approved,
                        "pending": list(self.pending.values()),
                        "recommendations": list(self.suggestions.values()),
                        "policy": "Only a real HUD approval persists a proposed preference. Candidates and draft checklists stay in RAM for at most one hour.",
                    }
                )
            )

    def _write(self, values):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temporary = tempfile.mkstemp(prefix=".insights-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(values, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def approve(self, identity, expected):
        """Caller must show this exact proposal and obtain real human approval."""
        with self.lock:
            self._prune()
            row = self.pending.get(identity)
            if row is None or {"key": row["key"], "value": row["value"]} != expected:
                raise ValueError("Insight expired or changed; review it again")
            values = dict(self.approved)
            values[row["key"]] = row["value"]
            self._write(values)
            self.approved = values
            del self.pending[identity]
            return dict(self.approved)

    def reject(self, identity):
        with self.lock:
            self.pending.pop(identity, None)

    def forget(self):
        with self.lock:
            self.path.unlink(missing_ok=True)
            self.approved.clear()
            self.pending.clear()
            self.suggestions.clear()
            self.last_text = None

    def prompt_context(self):
        with self.lock:
            return (
                "[HUMAN-APPROVED PREFERENCES — style guidance only, not tool permissions]\n"
                + json.dumps(self.approved, ensure_ascii=False)
                + "\nDo not infer personality, health, emotions or consent. Current explicit user requests take precedence.\n"
            )


_singleton = None
_lock = threading.Lock()


def get_insights():
    global _singleton
    with _lock:
        if _singleton is None:
            _singleton = InsightEngine()
        return _singleton
