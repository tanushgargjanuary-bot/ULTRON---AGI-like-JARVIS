"""One shared, lock-protected session budget; never authorizes a tool."""

from __future__ import annotations

import math
import threading
import uuid
from dataclasses import dataclass


@dataclass
class BudgetLimits:
    max_completion_calls: int = 50
    max_repair_calls: int = 12
    max_wall_seconds: float = 600.0
    max_consecutive_aborts: int = 4


class AutonomyGovernor:
    def __init__(self, knowledge=None, limits=None, session_id=None):
        self.knowledge = knowledge
        self.limits = limits or BudgetLimits()
        self.session_id = session_id or uuid.uuid4().hex
        self.lock = threading.RLock()
        self.usage = {"completion_calls": 0, "repair_calls": 0, "wall_seconds": 0.0}
        self.aborts = 0
        self.storage_failed = False
        if knowledge:
            self.usage.update(
                {
                    k: v
                    for k, v in knowledge.record_budget_usage(self.session_id).items()
                    if k in self.usage
                }
            )

    def _persist(self, **increments):
        if self.knowledge:
            try:
                self.knowledge.record_budget_usage(self.session_id, **increments)
            except Exception:
                self.storage_failed = True
                raise

    def request_call(self, kind="completion"):
        if kind not in {"completion", "repair"}:
            raise ValueError("Unknown budget kind")
        with self.lock:
            if self.storage_failed:
                return False, "BUDGET_STORAGE_UNAVAILABLE"
            if self.usage["wall_seconds"] >= self.limits.max_wall_seconds:
                return False, "SESSION_WALL_BUDGET_EXCEEDED"
            if self.aborts >= self.limits.max_consecutive_aborts:
                return False, "SESSION_ABORT_LIMIT_EXCEEDED"
            if (
                kind == "repair"
                and self.usage["repair_calls"] >= self.limits.max_repair_calls
            ):
                return False, "SESSION_REPAIR_BUDGET_EXCEEDED"
            if self.usage["completion_calls"] >= self.limits.max_completion_calls:
                return False, "SESSION_COMPLETION_BUDGET_EXCEEDED"
            increments = {"completion_calls": 1, "repair_calls": int(kind == "repair")}
            self._persist(**increments)
            for key, value in increments.items():
                self.usage[key] += value
            return True, "ALLOWED"

    def record_task_duration(self, seconds, aborted=False):
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError("Duration must be finite and nonnegative")
        with self.lock:
            self._persist(wall_seconds=seconds)
            self.usage["wall_seconds"] += seconds
            self.aborts = self.aborts + 1 if aborted else 0

    def status(self):
        with self.lock:
            return {
                "session_id": self.session_id,
                **self.usage,
                "remaining_completion_calls": max(
                    0, self.limits.max_completion_calls - self.usage["completion_calls"]
                ),
                "remaining_repair_calls": max(
                    0, self.limits.max_repair_calls - self.usage["repair_calls"]
                ),
                "paused": self.storage_failed
                or self.aborts >= self.limits.max_consecutive_aborts
                or self.usage["wall_seconds"] >= self.limits.max_wall_seconds
                or self.usage["completion_calls"] >= self.limits.max_completion_calls
                or self.usage["repair_calls"] >= self.limits.max_repair_calls,
            }
