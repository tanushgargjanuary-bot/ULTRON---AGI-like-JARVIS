"""Bounded local incident signatures and cooldowns, not an authorization policy."""

from __future__ import annotations

import re
import threading
import time
from collections import deque

from custom_jarvis.repair_judgment import fingerprint


def normalize_error_signature(error: str) -> str:
    text = error[:1000].lower()
    text = re.sub(r"0x[0-9a-f]+", "<addr>", text)
    text = re.sub(r"\b(line|column)\s+\d+", r"\1 <n>", text)
    text = re.sub(r"""["'](?:[a-z]:[\\/]|/|\.\.?[\\/])[^"']*["']""", "<path>", text)
    return " ".join(text.split())


def compute_incident_fingerprint(tool, error_code, error, context_key):
    return fingerprint(
        {
            "tool": tool,
            "code": error_code,
            "sig": normalize_error_signature(error),
            "ctx": context_key,
        }
    )


class RepairCircuitBreaker:
    def __init__(
        self,
        max_consecutive_failures=3,
        max_rollbacks_in_window=2,
        window_seconds=900.0,
        cooldown_seconds=300.0,
    ):
        if (
            min(
                max_consecutive_failures,
                max_rollbacks_in_window,
                window_seconds,
                cooldown_seconds,
            )
            <= 0
        ):
            raise ValueError("Circuit limits must be positive")
        self.max_failures = max_consecutive_failures
        self.max_rollbacks = max_rollbacks_in_window
        self.window = window_seconds
        self.cooldown = cooldown_seconds
        self.states = {}
        self.lock = threading.RLock()

    def _state(self, tool, context):
        key = (tool, context)
        if key not in self.states:
            if len(self.states) >= 512:
                self.states.pop(next(iter(self.states)))
            self.states[key] = {
                "attempt_outcomes": deque(maxlen=128),
                "rollback_events": deque(maxlen=128),
                "version_history": deque(maxlen=3),
                "tripped_until": 0.0,
                "reason": "CLOSED",
            }
        return self.states[key]

    def check(self, tool, context_key, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            s = self._state(tool, context_key)
            if s["tripped_until"] and now >= s["tripped_until"]:
                s["attempt_outcomes"].clear()
                s["rollback_events"].clear()
                s["version_history"].clear()
                s["tripped_until"] = 0
                s["reason"] = "CLOSED"
            for key in ("attempt_outcomes", "rollback_events"):
                q = s[key]
                while (
                    q
                    and (q[0][0] if key == "attempt_outcomes" else q[0])
                    < now - self.window
                ):
                    q.popleft()
            if now < s["tripped_until"]:
                return (
                    False,
                    s["reason"],
                    {"retry_after_seconds": s["tripped_until"] - now},
                )
            failures = 0
            for _, passed in reversed(s["attempt_outcomes"]):
                if passed:
                    break
                failures += 1
            history = list(s["version_history"])
            reason = (
                "CIRCUIT_OPEN_VERSION_OSCILLATION"
                if len(history) == 3
                and history[0] == history[2]
                and history[0] != history[1]
                else "CIRCUIT_OPEN_ROLLBACK_STORM"
                if len(s["rollback_events"]) >= self.max_rollbacks
                else "CIRCUIT_OPEN_REPEATED_REPAIR_FAILURES"
                if failures >= self.max_failures
                else "CLOSED"
            )
            if reason != "CLOSED":
                s["tripped_until"] = now + self.cooldown
                s["reason"] = reason
            return (
                reason == "CLOSED",
                reason,
                {
                    "consecutive_failures": failures,
                    "rollbacks": len(s["rollback_events"]),
                    "tripped_until": s["tripped_until"],
                },
            )

    def record_repair_attempt(self, tool, context_key, passed, now=None):
        with self.lock:
            self._state(tool, context_key)["attempt_outcomes"].append(
                (time.monotonic() if now is None else now, bool(passed))
            )

    def record_rollback(self, tool, context_key, from_version, to_version, now=None):
        with self.lock:
            s = self._state(tool, context_key)
            s["rollback_events"].append(time.monotonic() if now is None else now)
            if not s["version_history"] or s["version_history"][-1] != from_version:
                s["version_history"].append(from_version)
            if to_version:
                s["version_history"].append(to_version)

    def reset(self, tool=None, context_key=None):
        with self.lock:
            for key in list(self.states):
                if (tool is None or key[0] == tool) and (
                    context_key is None or key[1] == context_key
                ):
                    del self.states[key]
