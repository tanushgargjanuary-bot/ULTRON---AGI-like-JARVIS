"""Local, transactional operational memory. Never executes learned content."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class KnowledgeStore:
    """Each operation opens its own connection: safe across UI/worker threads.

    Automatic observations store tool names and counters, not arguments or output.
    Reviewed procedures and optional checkpoints can contain sensitive task data.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS stats (
                    tool TEXT PRIMARY KEY, attempts INTEGER NOT NULL DEFAULT 0,
                    succeeded INTEGER NOT NULL DEFAULT 0, verified INTEGER NOT NULL DEFAULT 0,
                    seconds REAL NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS procedures (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, instructions TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('proposed','approved','rejected')),
                    created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS checkpoints (
                    id TEXT PRIMARY KEY, state TEXT NOT NULL, payload TEXT NOT NULL,
                    updated REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS procedures_status_created
                    ON procedures(status, created DESC);
                CREATE INDEX IF NOT EXISTS checkpoints_updated
                    ON checkpoints(updated DESC);
                CREATE TABLE IF NOT EXISTS failure_fingerprints (
                    fingerprint TEXT PRIMARY KEY, tool TEXT NOT NULL, context_key TEXT NOT NULL,
                    error_code TEXT NOT NULL, normalized_error TEXT NOT NULL, adapter_source TEXT,
                    contracts_json TEXT, occurrences INTEGER NOT NULL DEFAULT 1,
                    resolved_count INTEGER NOT NULL DEFAULT 0, last_seen REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_fingerprints_tool_ctx ON failure_fingerprints(tool, context_key, last_seen DESC);
                CREATE TABLE IF NOT EXISTS model_competence (
                    model TEXT NOT NULL, task_class TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                    verified_successes INTEGER NOT NULL DEFAULT 0, ambiguous_failures INTEGER NOT NULL DEFAULT 0,
                    total_latency_ms REAL NOT NULL DEFAULT 0, updated REAL NOT NULL, PRIMARY KEY(model,task_class));
                CREATE INDEX IF NOT EXISTS idx_competence_task ON model_competence(task_class,verified_successes DESC);
                CREATE TABLE IF NOT EXISTS budget_ledger (
                    session_id TEXT PRIMARY KEY, completion_calls INTEGER NOT NULL DEFAULT 0,
                    repair_calls INTEGER NOT NULL DEFAULT 0, wall_seconds REAL NOT NULL DEFAULT 0, updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS incident_graph (
                    incident_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, step_id INTEGER NOT NULL,
                    tool TEXT NOT NULL, error_code TEXT NOT NULL, root_cause_step_id INTEGER,
                    classification TEXT NOT NULL, created REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_incident_task ON incident_graph(task_id,step_id ASC);
            """)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def observe(self, tool: str, success: bool, verified: bool, seconds: float) -> None:
        with self._connect() as db:
            db.execute(
                """INSERT INTO stats VALUES (?,1,?,?,?) ON CONFLICT(tool) DO UPDATE SET
                attempts=attempts+1, succeeded=succeeded+excluded.succeeded,
                verified=verified+excluded.verified, seconds=seconds+excluded.seconds""",
                (tool[:100], int(success), int(verified), max(0, seconds)),
            )

    def statistics(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            return [
                dict(row) for row in db.execute("SELECT * FROM stats ORDER BY tool")
            ]

    def propose(self, title: str, instructions: str) -> str:
        if not title.strip() or not instructions.strip():
            raise ValueError("A procedure needs a title and instructions")
        if len(title) > 200 or len(instructions) > 12000:
            raise ValueError("Procedure exceeds size limit")
        identity = uuid.uuid4().hex
        with self._connect() as db:
            db.execute(
                "INSERT INTO procedures VALUES (?,?,?,?,?)",
                (identity, title, instructions, "proposed", time.time()),
            )
        return identity

    def review(self, identity: str, approve: bool) -> None:
        with self._connect() as db:
            changed = db.execute(
                "UPDATE procedures SET status=? WHERE id=? AND status='proposed'",
                ("approved" if approve else "rejected", identity),
            )
            if not changed.rowcount:
                raise ValueError("Only an existing proposed procedure can be reviewed")

    def procedures(self, status: str = "approved") -> list[dict[str, Any]]:
        with self._connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM procedures WHERE status=? ORDER BY created DESC LIMIT 200",
                    (status,),
                )
            ]

    def checkpoint(self, identity: str, state: str, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, default=str)
        if len(encoded.encode("utf-8")) > 2 * 1024 * 1024:
            raise ValueError("Checkpoint exceeds 2 MB limit")
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO checkpoints VALUES (?,?,?,?)",
                (identity, state, encoded, time.time()),
            )
            # Bound disk growth; checkpoints are recovery aids, not permanent archives.
            db.execute(
                "DELETE FROM checkpoints WHERE id NOT IN "
                "(SELECT id FROM checkpoints ORDER BY updated DESC LIMIT 50)"
            )

    def checkpoints(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM checkpoints ORDER BY updated DESC LIMIT 50"
                )
            ]

    def forget(self) -> None:
        with self._connect() as db:
            for table in (
                "stats",
                "procedures",
                "checkpoints",
                "failure_fingerprints",
                "model_competence",
                "budget_ledger",
                "incident_graph",
            ):
                db.execute(f"DELETE FROM {table}")
            # Ordinary deletion is not a guarantee of forensic secure erasure.

    def record_fingerprint(
        self, fingerprint, tool, context_key, error_code, normalized_error
    ):
        with self._connect() as db:
            db.execute(
                "INSERT INTO failure_fingerprints(fingerprint,tool,context_key,error_code,normalized_error,last_seen) VALUES (?,?,?,?,?,?) ON CONFLICT(fingerprint) DO UPDATE SET occurrences=occurrences+1,last_seen=excluded.last_seen",
                (
                    fingerprint,
                    tool,
                    context_key,
                    error_code,
                    normalized_error[:1000],
                    time.time(),
                ),
            )
            row = dict(
                db.execute(
                    "SELECT * FROM failure_fingerprints WHERE fingerprint=?",
                    (fingerprint,),
                ).fetchone()
            )
            if not row["resolved_count"]:
                row["adapter_source"] = row["contracts_json"] = None
            return row

    def get_fingerprint(self, fingerprint):
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM failure_fingerprints WHERE fingerprint=?", (fingerprint,)
            ).fetchone()
            return dict(row) if row else None

    def bind_fingerprint_solution(self, fingerprint, adapter_source, contracts_json):
        if len(adapter_source.encode()) > 8192 or len(contracts_json.encode()) > 131072:
            raise ValueError("Fingerprint solution exceeds limits")
        with self._connect() as db:
            changed = db.execute(
                "UPDATE failure_fingerprints SET adapter_source=?,contracts_json=?,resolved_count=resolved_count+1 WHERE fingerprint=?",
                (adapter_source, contracts_json, fingerprint),
            )
            if not changed.rowcount:
                raise ValueError(
                    "Fingerprint must be recorded before binding a solution"
                )

    def record_model_outcome(
        self, model, task_class, verified, latency_ms, ambiguous=False
    ):
        with self._connect() as db:
            db.execute(
                "INSERT INTO model_competence VALUES (?,?,1,?,?,?,?) ON CONFLICT(model,task_class) DO UPDATE SET attempts=attempts+1,verified_successes=verified_successes+excluded.verified_successes,ambiguous_failures=ambiguous_failures+excluded.ambiguous_failures,total_latency_ms=total_latency_ms+excluded.total_latency_ms,updated=excluded.updated",
                (
                    model,
                    task_class,
                    int(verified),
                    int(ambiguous),
                    max(0, latency_ms),
                    time.time(),
                ),
            )

    def competence(self):
        with self._connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM model_competence ORDER BY task_class,model"
                )
            ]

    def rank_models_for_task(self, candidates, task_class):
        with self._connect() as db:
            rows = {
                row["model"]: dict(row)
                for row in db.execute(
                    "SELECT * FROM model_competence WHERE task_class=?", (task_class,)
                )
            }

        def score(model):
            r = rows.get(model, {})
            n = r.get("attempts", 0)
            return (r.get("verified_successes", 0) + 1) / (n + 2) - 0.15 * r.get(
                "ambiguous_failures", 0
            ) / max(1, n)

        # Sparse candidates remain in their user-ordered slots. Sort only slots
        # with adequate evidence; this avoids a non-transitive pair comparator.
        ranked = list(candidates)
        slots = [
            i for i, m in enumerate(ranked) if rows.get(m, {}).get("attempts", 0) >= 3
        ]
        values = sorted((ranked[i] for i in slots), key=score, reverse=True)
        for i, m in zip(slots, values):
            ranked[i] = m
        return ranked

    def record_budget_usage(
        self, session_id, completion_calls=0, repair_calls=0, wall_seconds=0.0
    ):
        if min(completion_calls, repair_calls, wall_seconds) < 0:
            raise ValueError("Budget usage cannot be negative")
        with self._connect() as db:
            db.execute(
                "INSERT INTO budget_ledger VALUES (?,?,?,?,?) ON CONFLICT(session_id) DO UPDATE SET completion_calls=completion_calls+excluded.completion_calls,repair_calls=repair_calls+excluded.repair_calls,wall_seconds=wall_seconds+excluded.wall_seconds,updated=excluded.updated",
                (session_id, completion_calls, repair_calls, wall_seconds, time.time()),
            )
            return dict(
                db.execute(
                    "SELECT * FROM budget_ledger WHERE session_id=?", (session_id,)
                ).fetchone()
            )

    def record_causal_incident(
        self,
        incident_id,
        task_id,
        step_id,
        tool,
        error_code,
        root_cause_step_id,
        classification,
    ):
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO incident_graph VALUES (?,?,?,?,?,?,?,?)",
                (
                    incident_id,
                    task_id,
                    step_id,
                    tool,
                    error_code,
                    root_cause_step_id,
                    classification,
                    time.time(),
                ),
            )
            db.execute(
                "DELETE FROM incident_graph WHERE incident_id NOT IN (SELECT incident_id FROM incident_graph ORDER BY created DESC LIMIT 500)"
            )
