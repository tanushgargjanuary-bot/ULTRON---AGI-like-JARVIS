"""Persistent notices for detected failures, with safe background repair proposals.

This is an issue inbox, not an omniscient monitor: it reports availability states
that the app can inspect and runtime failures recorded through ``core.failures``.
Fix requests may stage and rehearse a candidate in a scratch copy, but can never
apply it or supply either human confirmation.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from pathlib import Path

from core import failures

MAX_ISSUES = 500
MAX_JOBS = 100
DETAIL_LIMIT = 500


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _safe(value, limit: int = DETAIL_LIMIT) -> str:
    """Bound persisted diagnostics and redact credential-shaped values."""
    try:
        from core.crash import redact
        text = redact(str(value or ""))
    except Exception:
        text = str(value or "")
    text = " ".join(text.split())
    return text[:limit]


def _fingerprint(source: str, component: str, kind: str, detail: str) -> str:
    material = "\0".join((source, component, kind, detail.casefold()))
    return "i" + hashlib.sha256(material.encode("utf-8", "replace")).hexdigest()[:10]


class HealthCenter:
    """Thread-safe, bounded local issue ledger and background repair queue."""

    def __init__(self, path: Path | str | None = None, notifier=None):
        if path is None:
            from core.paths import state_dir
            path = state_dir() / "health_center.json"
        self.path = Path(path)
        self._lock = threading.RLock()
        self._notifier = notifier
        self._issues: dict[str, dict] = {}
        self._jobs: dict[str, dict] = {}
        self._repair_busy = False
        self._storage_error = ""
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("version") != 1:
                raise ValueError("unsupported health ledger format")
            issues = data.get("issues", {})
            jobs = data.get("jobs", {})
            if isinstance(issues, dict):
                self._issues = {
                    str(key): value for key, value in issues.items()
                    if isinstance(value, dict) and value.get("id") == key
                }
            if isinstance(jobs, dict):
                self._jobs = {
                    str(key): value for key, value in jobs.items()
                    if isinstance(value, dict) and value.get("id") == key
                }
        except FileNotFoundError:
            return
        except (OSError, ValueError, TypeError):
            self._storage_error = "The saved health ledger could not be read; new notices remain in memory only."
            self._issues = {}
            self._jobs = {}
            return

        # Threads do not survive restart. Make their interrupted state explicit.
        changed = False
        for job in self._jobs.values():
            if job.get("status") in {"queued", "running"}:
                job["status"] = "interrupted"
                job["updated"] = _now()
                job["result"] = "The app restarted before this background repair proposal finished."
                changed = True
        if changed:
            self._persist_locked()

    def _persist_locked(self) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_name(self.path.name + ".tmp")
            payload = {"version": 1, "issues": self._issues, "jobs": self._jobs}
            temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(self.path)
            self._storage_error = ""
            return True
        except OSError as error:
            self._storage_error = f"Health notices could not be saved: {type(error).__name__}."
            return False

    def set_notifier(self, notifier) -> None:
        with self._lock:
            self._notifier = notifier if callable(notifier) else None

    def _notify(self, text: str) -> None:
        with self._lock:
            callback = self._notifier
        if callback:
            try:
                callback(text)
            except Exception:
                pass

    def record(self, source: str, component: str, summary: str,
               detail: str = "", kind: str = "Unavailable") -> dict:
        """Record or update one issue; emit one proactive notice per new recurrence."""
        source = _safe(source, 48) or "unknown"
        component = _safe(component, 120) or "unknown"
        kind = _safe(kind, 80) or "Issue"
        summary = _safe(summary, 220) or f"Issue detected in {component}"
        detail = _safe(detail)
        issue_id = _fingerprint(source, component, kind, detail)
        new_active = False
        with self._lock:
            row = self._issues.get(issue_id)
            now = _now()
            if row is None:
                row = {
                    "id": issue_id, "source": source, "component": component,
                    "kind": kind, "summary": summary, "detail": detail,
                    "status": "active", "first_seen": now, "last_seen": now,
                    "occurrences": 1,
                }
                self._issues[issue_id] = row
                new_active = True
            else:
                if row.get("status") in {"dismissed", "resolved"}:
                    row["status"] = "active"
                    new_active = True
                row["last_seen"] = now
                row["occurrences"] = int(row.get("occurrences", 0)) + 1
                # Keep the current wording if it became more useful on a later report.
                row["summary"] = summary
                row["detail"] = detail
            self._prune_issues_locked()
            self._persist_locked()
            result = dict(row)
        if new_active and result["status"] == "active":
            self._notify(
                f"Health notice {issue_id}: {summary}. Say 'health status', "
                f"'ignore {issue_id}', 'dismiss {issue_id}', or 'fix {issue_id}' "
                "to stage and test a repair proposal."
            )
        return result

    def _prune_issues_locked(self) -> None:
        if len(self._issues) <= MAX_ISSUES:
            return
        ordered = sorted(self._issues.values(), key=lambda row: row.get("last_seen", ""))
        for row in ordered[:len(self._issues) - MAX_ISSUES]:
            self._issues.pop(row.get("id"), None)

    def capture_failure(self, entry: dict) -> None:
        """Listener for the bounded runtime failure journal; never raises."""
        try:
            where = _safe(entry.get("where") or "runtime", 120)
            kind = _safe(entry.get("kind") or "Failure", 80)
            error = _safe(entry.get("error") or entry.get("detail") or kind)
            self.record("runtime", where, f"Detected failure in {where} ({kind})", error, kind)
        except Exception:
            return

    def record_unavailable(self, component: str, detail: str, source: str = "local_catalog") -> dict:
        return self.record(source, component, f"{component} is unavailable", detail, "Unavailable")

    def reconcile_availability(self, unavailable: list[tuple[str, str]]) -> int:
        """Record current local tool gaps and resolve old gaps no longer observed."""
        current = set()
        for component, detail in unavailable:
            row = self.record_unavailable(component, detail)
            current.add(row["id"])
        with self._lock:
            changed = False
            for issue_id, row in self._issues.items():
                if (row.get("source") == "local_catalog" and row.get("status") == "active"
                        and issue_id not in current):
                    row["status"] = "resolved"
                    row["resolved_at"] = _now()
                    changed = True
            if changed:
                self._persist_locked()
        return len(current)

    def scan_local_catalog(self) -> int:
        """Inspect action/plugin availability without probing external bridges."""
        from core import tool_catalog
        entries = tool_catalog.build(include_bridges=False)
        return self.reconcile_availability([
            (entry.name, entry.reason or entry.summary)
            for entry in entries if not entry.available
        ])

    def scan_bridges(self) -> int:
        """Explicitly probe configured integrations; never runs their tools."""
        from core.bridges import probe_all
        rows = probe_all()
        unavailable = [row for row in rows if not row.get("ready")]
        current = set()
        for row in unavailable:
            issue = self.record(
                "bridge_catalog", f"bridge:{row.get('key', 'unknown')}",
                f"{row.get('title', row.get('key', 'Bridge'))} is unavailable",
                str(row.get("detail") or "bridge did not answer"), "Unavailable",
            )
            current.add(issue["id"])
        with self._lock:
            changed = False
            for issue_id, row in self._issues.items():
                if (row.get("source") == "bridge_catalog" and row.get("status") == "active"
                        and issue_id not in current):
                    row["status"] = "resolved"
                    row["resolved_at"] = _now()
                    changed = True
            if changed:
                self._persist_locked()
        return len(current)

    def ignore(self, issue_id: str) -> bool:
        return self._set_issue_status(issue_id, "ignored")

    def dismiss(self, issue_id: str) -> bool:
        return self._set_issue_status(issue_id, "dismissed")

    def restore(self, issue_id: str) -> bool:
        return self._set_issue_status(issue_id, "active")

    def _set_issue_status(self, issue_id: str, status: str) -> bool:
        with self._lock:
            row = self._issues.get(str(issue_id or "").strip())
            if row is None:
                return False
            row["status"] = status
            row["updated"] = _now()
            self._persist_locked()
            return True

    def issues(self, include_inactive: bool = False) -> list[dict]:
        with self._lock:
            rows = [dict(row) for row in self._issues.values()]
        if not include_inactive:
            rows = [row for row in rows if row.get("status") == "active"]
        return sorted(rows, key=lambda row: (row.get("status") == "active", row.get("last_seen", "")), reverse=True)

    def start_fix(self, issue_id: str, path: str, reason: str,
                  *, text: str | None = None, find: str | None = None,
                  replace: str | None = None, player=None) -> dict:
        """Stage and fully rehearse a candidate off-thread; never apply it."""
        with self._lock:
            issue = self._issues.get(str(issue_id or "").strip())
            if issue is None:
                raise ValueError("I cannot find that issue ID. Ask for health status to see current IDs.")
            if self._repair_busy:
                running = next((job for job in self._jobs.values()
                                if job.get("status") in {"queued", "running"}), None)
                raise ValueError("A background repair proposal is already running" +
                                 (f" ({running['id']})" if running else "."))
            if not str(path or "").strip() or not str(reason or "").strip():
                raise ValueError("A repair proposal needs a project-relative path and a reason.")
            if text is None and not str(find or ""):
                raise ValueError("Provide either the proposed whole-file text, or one exact passage to replace.")
            job_id = "r" + uuid.uuid4().hex[:10]
            job = {
                "id": job_id, "issue_id": issue["id"], "component": issue["component"],
                "path": _safe(path, 180), "reason": _safe(reason, 240),
                "status": "queued", "created": _now(), "updated": _now(),
                "proposal_id": "", "result": "Queued; project files are unchanged.",
            }
            self._jobs[job_id] = job
            self._repair_busy = True
            self._prune_jobs_locked()
            self._persist_locked()
        thread = threading.Thread(
            target=self._run_fix,
            args=(job_id, str(path), str(reason), text, find, replace, player),
            name=f"ultron-health-repair-{job_id}", daemon=True,
        )
        thread.start()
        return dict(job)

    def _prune_jobs_locked(self) -> None:
        if len(self._jobs) <= MAX_JOBS:
            return
        ordered = sorted(self._jobs.values(), key=lambda row: row.get("created", ""))
        for row in ordered[:len(self._jobs) - MAX_JOBS]:
            if row.get("status") not in {"queued", "running"}:
                self._jobs.pop(row.get("id"), None)

    def _update_job(self, job_id: str, **updates) -> dict:
        with self._lock:
            row = self._jobs.get(job_id)
            if row is None:
                return {}
            row.update(updates)
            row["updated"] = _now()
            self._persist_locked()
            return dict(row)

    def _run_fix(self, job_id, path, reason, text, find, replace, player) -> None:
        from core import self_change
        try:
            self._update_job(job_id, status="running", result="Staging candidate; running the full verification harness in a scratch copy.")
            with self_change.change_lock():
                proposal = self_change.propose(
                    path, reason, new_text=text, find=find, replace=replace
                )
                result = self_change.rehearse(proposal["id"], full=True)
            if result.get("ok"):
                message = (f"Background repair {job_id} passed the full harness. "
                           f"Proposal {proposal['id']} is ready for review; nothing was applied. "
                           f"Use self_modify show for {proposal['id']}, then confirm in two "
                           "different channels before applying.")
                job = self._update_job(
                    job_id, status="ready_for_review", proposal_id=proposal["id"],
                    result=message,
                )
            else:
                tail = _safe(result.get("tail") or "No test output was captured.", 1200)
                message = (f"Background repair {job_id} did not pass verification. "
                           "No project files were changed and the candidate cannot be applied. "
                           f"Proposal: {proposal['id']}. {tail}")
                job = self._update_job(
                    job_id, status="verification_failed", proposal_id=proposal["id"],
                    result=message,
                )
        except Exception as error:
            message = _safe(f"Background repair {job_id} stopped: {type(error).__name__}: {error}", 1200)
            job = self._update_job(job_id, status="failed", result=message)
        finally:
            with self._lock:
                self._repair_busy = False
        if player is not None:
            try:
                player.write_log("SYS: " + message)
            except Exception:
                pass

    def job(self, job_id: str) -> dict | None:
        with self._lock:
            row = self._jobs.get(str(job_id or "").strip())
            return dict(row) if row else None

    def jobs(self) -> list[dict]:
        with self._lock:
            rows = [dict(row) for row in self._jobs.values()]
        return sorted(rows, key=lambda row: row.get("created", ""), reverse=True)

    def storage_error(self) -> str:
        with self._lock:
            return self._storage_error


_center_lock = threading.Lock()
_center: HealthCenter | None = None


def get_health_center() -> HealthCenter:
    """Shared process-local center; state itself remains in the user's data folder."""
    global _center
    with _center_lock:
        if _center is None:
            _center = HealthCenter()
        return _center


def reset_health_center_for_tests() -> None:
    global _center
    with _center_lock:
        _center = None
