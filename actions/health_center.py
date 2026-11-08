"""Detected issue inbox with persistent ignore controls and background repair proposals."""

from __future__ import annotations

from custom_jarvis.health_center import get_health_center


def _render(center, include_inactive=False) -> str:
    rows = center.issues(include_inactive=include_inactive)
    active = [row for row in rows if row.get("status") == "active"]
    if not rows:
        storage = center.storage_error()
        suffix = f"\n{storage}" if storage else ""
        return "No detected health issues are waiting." + suffix
    lines = [f"Health center: {len(active)} active issue(s)."]
    for row in rows[:30]:
        status = row.get("status", "active")
        lines.append(
            f"{row['id']} [{status}] {row.get('summary', row.get('component', 'issue'))} "
            f"(seen {row.get('occurrences', 1)} time(s); last {row.get('last_seen', '?')})"
        )
        if row.get("detail"):
            lines.append(f"  Detail: {row['detail']}")
        lines.append(f"  Options: ignore {row['id']}, dismiss {row['id']}, or fix {row['id']}.")
    if len(rows) > 30:
        lines.append(f"Showing 30 of {len(rows)} records.")
    storage = center.storage_error()
    if storage:
        lines.append(storage)
    return "\n".join(lines)


def run(parameters: dict, player=None, session_memory=None) -> str:
    """List, mute, restore or start a background repair proposal for a detected issue."""
    parameters = dict(parameters or {})
    center = get_health_center()
    action = str(parameters.get("action") or "status").strip().lower()
    issue_id = str(parameters.get("issue_id") or parameters.get("issue") or "").strip()

    if action in {"status", "list", "show"}:
        return _render(center, bool(parameters.get("include_inactive")))
    if action == "scan":
        count = center.scan_local_catalog()
        return f"Local action/plugin scan finished. {count} unavailable item(s) detected.\n{_render(center)}"
    if action == "scan_bridges":
        count = center.scan_bridges()
        return (f"Configured bridge probe finished. {count} unavailable bridge(s) detected. "
                "This checked readiness only; it did not invoke bridge operations.\n"
                f"{_render(center)}")
    if action in {"ignore", "dismiss", "restore"}:
        if not issue_id:
            return "Give me the issue ID shown by health status."
        changed = getattr(center, action)(issue_id)
        if not changed:
            return f"I cannot find health issue {issue_id}. Ask for health status to see current IDs."
        label = "muted until restored" if action == "ignore" else (
            "dismissed; a later occurrence can reopen it" if action == "dismiss" else "restored"
        )
        return f"Health issue {issue_id} {label}. No code was changed."
    if action == "jobs":
        rows = center.jobs()
        if not rows:
            return "There are no background health-repair jobs."
        return "Background health-repair jobs:\n" + "\n".join(
            f"{row['id']} [{row['status']}] issue {row['issue_id']} — {row.get('result', '')}"
            for row in rows[:20]
        )
    if action == "job":
        job_id = str(parameters.get("job_id") or "").strip()
        row = center.job(job_id)
        return (f"I have no health-repair job {job_id}." if row is None else
                f"{row['id']} [{row['status']}] for issue {row['issue_id']}: {row.get('result', '')}")
    if action == "fix":
        if not issue_id:
            return "Give me a detected issue ID from health status."
        try:
            job = center.start_fix(
                issue_id,
                str(parameters.get("path") or ""),
                str(parameters.get("reason") or ""),
                text=parameters.get("text"),
                find=parameters.get("find"),
                replace=parameters.get("replace"),
                player=player,
            )
        except ValueError as error:
            return str(error)
        return (
            f"Started background repair proposal {job['id']} for issue {issue_id}. "
            "The conversation can continue. It will stage the candidate and run the full "
            "verification harness in a scratch copy; it cannot apply code or confirm for you. "
            f"Query health_center action=job with job_id={job['id']} for its status."
        )
    return "I can: status, scan, scan_bridges, ignore, dismiss, restore, fix, jobs, or job."


TOOL = {
    "name": "health_center",
    "description": (
        "Use when the user asks what is unavailable, what failed, whether a feature is broken, "
        "or wants to ignore, dismiss, restore, or fix a detected issue. Reports only instrumented "
        "or scanned issues. Use scan_bridges only for an explicit configured-service readiness probe; "
        "it never invokes bridge operations. A fix request must include issue_id, path, reason, and either whole-file "
        "text or one exact find/replace passage. It stages and rehearses a source proposal in a "
        "background thread using the full test harness; it never applies code or supplies human "
        "confirmations. The conversation continues while the job runs."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": [
                "status", "scan", "scan_bridges", "ignore", "dismiss", "restore", "fix", "jobs", "job"
            ]},
            "issue_id": {"type": "STRING", "description": "The issue ID from the health notice."},
            "job_id": {"type": "STRING", "description": "A background repair job ID."},
            "include_inactive": {"type": "BOOLEAN", "description": "Also show ignored and dismissed issues."},
            "path": {"type": "STRING", "description": "Project-relative source path for a proposed fix."},
            "reason": {"type": "STRING", "description": "Why the candidate change addresses the detected issue."},
            "text": {"type": "STRING", "description": "Whole proposed file contents; use instead of find/replace."},
            "find": {"type": "STRING", "description": "One exact existing passage to replace."},
            "replace": {"type": "STRING", "description": "Replacement passage paired with find."},
        },
        "required": ["action"],
    },
    "handler": run,
    "behavior": "NON_BLOCKING",
    "scheduling": "SILENT",
}
