"""plugins/agent_monitor_bridge.py — Live agent execution monitor and observability bridge.

Inspired by Charonyuu/whatsmyagentdoing on GitHub.
Provides real-time visibility into Ultron's background worker threads, active agent tasks,
and external agent execution loops.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from core import failures

PLUGIN = {
    "name": "agent_monitor_bridge",
    "description": (
        "Monitors active Ultron agents, background worker threads, and live tool executions. "
        "Use it when the user asks what Ultron or background agents are currently doing, "
        "checks task progress, inspects running threads, or diagnoses stuck operations."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "'status' for overall activity summary, 'threads' to list running background workers, 'tasks' to inspect current task states, or 'dashboard' for visual monitor status.",
                "enum": ["status", "threads", "tasks", "dashboard"],
            },
            "filter": {
                "type": "STRING",
                "description": "Optional substring filter to match specific thread or task names.",
            },
            "verbose": {
                "type": "BOOLEAN",
                "description": "Whether to include detailed daemon flags and thread identifiers.",
            },
        },
        "required": ["action"],
    },
    "tier": "OBSERVE",
}

DEFAULT_DASHBOARD_URL = "http://127.0.0.1:8765"


def _probe_dashboard() -> tuple[bool, str]:
    """Check if the external whatsmyagentdoing visual dashboard is running."""
    try:
        req = urllib.request.Request(
            f"{DEFAULT_DASHBOARD_URL}/",
            headers={"User-Agent": "Ultron-AgentMonitorBridge"},
        )
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            if resp.status in (200, 204, 302):
                return True, f"Dashboard live at {DEFAULT_DASHBOARD_URL}"
    except Exception as exc:
        failures.note("agent_monitor.probe", exc)
    return False, f"Dashboard offline ({DEFAULT_DASHBOARD_URL})"


def _inspect_threads(filter_query: str = "", verbose: bool = False) -> list[dict[str, Any]]:
    """Enumerate alive threads and categorize agent workers."""
    threads = threading.enumerate()
    results = []
    filter_lower = filter_query.lower()

    for t in threads:
        name = t.name
        if filter_lower and filter_lower not in name.lower():
            continue

        is_agent_worker = any(
            w in name.lower()
            for w in ("agent", "dev-agent", "send-message", "video-player", "code-", "worker", "crawler", "ocr")
        )
        is_runtime = any(
            r in name.lower()
            for r in ("mainthread", "asyncio", "threadpool", "qthread", "signal", "pyqt", "dummy")
        )

        cat = "Agent Worker" if is_agent_worker else ("Runtime" if is_runtime else "Background")
        results.append({
            "name": name,
            "ident": t.ident,
            "daemon": t.daemon,
            "alive": t.is_alive(),
            "category": cat,
        })

    results.sort(key=lambda x: (0 if x["category"] == "Agent Worker" else 1, x["name"]))
    return results


def _inspect_dev_agent_task() -> dict[str, Any] | None:
    """Introspect actions.dev_agent state if running."""
    mod = sys.modules.get("actions.dev_agent")
    if mod is None:
        return None
    task = getattr(mod, "_CURRENT_TASK", None) or getattr(mod, "_current_task", None)
    running = getattr(mod, "_IS_RUNNING", False) or getattr(mod, "_is_running", False)
    if running or task:
        return {
            "active": bool(running),
            "task": str(task) if task else "In progress",
        }
    return None


def _safe_show(player, title: str, content: str) -> None:
    """Thread-safe UI content display helper."""
    if player is not None:
        try:
            player.show_content(title, content)
        except Exception as exc:
            failures.note("agent_monitor.show_content", exc)


def _handle_status(dash_detail: str, threads: list[dict[str, Any]], workers: list[dict[str, Any]],
                   dev_task: dict[str, Any] | None, verbose: bool, player: Any) -> str:
    lines = [
        "### Ultron Agent Execution Monitor",
        f"- **Active Agent Workers**: {len(workers)} running",
        f"- **Total Living Threads**: {len(threads)}",
        f"- **External Telemetry Dashboard**: {dash_detail}",
    ]
    if dev_task and dev_task["active"]:
        lines.append(f"- **Coding Subagent**: ACTIVE — `{dev_task['task']}`")

    if workers:
        lines.append("\n**Active Worker Threads:**")
        for w in workers:
            daemon_flag = " (daemon)" if verbose and w["daemon"] else ""
            lines.append(f"  - `{w['name']}` [{w['category']}]{daemon_flag}")
    else:
        lines.append("\n*No long-running agent tasks currently in progress.*")

    summary = "\n".join(lines)
    _safe_show(player, "AGENT MONITOR", summary)
    voice = f"Sir, {len(workers)} agent worker thread{' is' if len(workers) == 1 else 's are'} running, with {len(threads)} total threads."
    if dev_task and dev_task["active"]:
        voice += f" The coding subagent is active on: {dev_task['task']}."
    return f"{voice}\n\n{summary}"


def _handle_threads(threads: list[dict[str, Any]], verbose: bool, player: Any) -> str:
    lines = [f"### Active Threads ({len(threads)} found)"]
    for t in threads:
        ident_str = f" [ID: {t['ident']}]" if verbose else ""
        daemon_str = " (daemon)" if t["daemon"] else ""
        lines.append(f"- **{t['name']}** — `{t['category']}`{daemon_str}{ident_str}")
    listing = "\n".join(lines)
    _safe_show(player, "ACTIVE THREADS", listing)
    return listing


def _handle_tasks(workers: list[dict[str, Any]], dev_task: dict[str, Any] | None, player: Any) -> str:
    tasks = []
    if dev_task and dev_task["active"]:
        tasks.append(f"- **Dev Agent**: `{dev_task['task']}`")
    for w in workers:
        tasks.append(f"- **Worker**: `{w['name']}` is active")
    if not tasks:
        return "Sir, there are no active background tasks currently running."
    task_report = "### Active Agent Tasks\n" + "\n".join(tasks)
    _safe_show(player, "ACTIVE TASKS", task_report)
    return task_report


def _handle_dashboard(dash_live: bool, player: Any) -> str:
    if dash_live:
        msg = f"The visual agent monitor dashboard is running at {DEFAULT_DASHBOARD_URL}."
    else:
        msg = (
            f"The whatsmyagentdoing visual dashboard is currently offline at {DEFAULT_DASHBOARD_URL}.\n"
            "To launch it: run `npx whatsmyagentdoing` or `docker run -p 8765:8765 charonyuu/whatsmyagentdoing`."
        )
    _safe_show(player, "AGENT DASHBOARD", msg)
    return msg


def run(parameters: dict, player=None, session_memory=None) -> str:
    """Execute live agent monitor action safely."""
    try:
        action = str(parameters.get("action") or "status").strip().lower()
        filter_str = str(parameters.get("filter") or "").strip()
        verbose = bool(parameters.get("verbose", False))

        dash_live, dash_detail = _probe_dashboard()
        threads = _inspect_threads(filter_query=filter_str, verbose=verbose)
        workers = [t for t in threads if t["category"] == "Agent Worker"]
        dev_task = _inspect_dev_agent_task()

        handlers = {
            "status": lambda: _handle_status(dash_detail, threads, workers, dev_task, verbose, player),
            "threads": lambda: _handle_threads(threads, verbose, player),
            "tasks": lambda: _handle_tasks(workers, dev_task, player),
            "dashboard": lambda: _handle_dashboard(dash_live, player),
        }
        if action in handlers:
            return handlers[action]()
        return f"Sir, unknown action '{action}'. Supported actions are 'status', 'threads', 'tasks', and 'dashboard'."
    except Exception as exc:
        failures.note("agent_monitor.run", exc)
        return f"Sir, agent monitor encountered an error: {type(exc).__name__}: {exc}"
