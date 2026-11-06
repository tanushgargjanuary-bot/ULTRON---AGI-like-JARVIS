"""Explicit execution boundaries for the native command center.

Approval is not an OS sandbox: approved shell commands retain the user's permissions.
Cancellation is cooperative and cannot interrupt an already running tool/API call.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, TypedDict

from custom_jarvis.tools import ToolResult


class Registry(Protocol):
    """Small engine contract; policy does not depend on a concrete registry."""

    def list_tools(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]: ...

    def execute(self, name: str, **kwargs: Any) -> ToolResult: ...


ApprovalCallback = Callable[[str, dict[str, Any]], bool]


class ControlledRegistry:
    READ_ONLY = frozenset(
        {
            "read_file",
            "list_dir",
            "find_files",
            "get_active_window",
            "take_screenshot",
            "web_search",
            "fetch_web_page",
        }
    )

    def __init__(
        self, registry: Registry, approve: ApprovalCallback | None = None
    ) -> None:
        self.registry = registry
        self.approve = approve
        self.cancelled = threading.Event()
        self.preview = False

    def list_tools(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return self.registry.list_tools(*args, **kwargs)

    @staticmethod
    def blocked(message: str, code: str) -> ToolResult:
        return ToolResult(
            False,
            error=message,
            metadata={"requires_user_action": True, "error_code": code},
        )

    def execute(self, name: str, **kwargs: Any) -> ToolResult:
        if self.cancelled.is_set():
            return self.blocked(
                "Cancelled by user. No further tools were executed.", "CANCELLED"
            )
        if self.preview:
            return self.blocked(
                "Preview only: no tools were executed. Disable Preview to run this plan.",
                "PREVIEW",
            )
        if name not in self.READ_ONLY:
            # Unknown tools and aliases are deliberately not implicitly trusted.
            if self.approve is None or not self.approve(name, kwargs):
                return self.blocked("Action not approved. Execution stopped.", "DENIED")
        if self.cancelled.is_set():
            return self.blocked("Cancelled before tool execution.", "CANCELLED")
        return self.registry.execute(name, **kwargs)


class HistoryRecord(TypedDict):
    time: str
    goal: str
    success: bool
    duration: float


class History:
    """Bounded local task metadata, with atomic replacement and per-instance locking.

    Multiple writers cannot share a temporary filename. Separate History instances
    do not provide transaction isolation: concurrent appends can still lose updates.
    Tool arguments, outputs, and API keys are never persisted here.
    """

    def __init__(self, path: str | Path, limit: int = 100) -> None:
        if limit < 1:
            raise ValueError("History limit must be positive")
        self.path = Path(path)
        self.limit = limit
        self.lock = threading.Lock()

    def read(self) -> list[dict[str, Any]]:
        with self.lock:
            return self._read()

    def _read(self) -> list[dict[str, Any]]:
        """Caller holds the lock; tolerate malformed or partially edited files."""
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        return [row for row in data[-self.limit :] if isinstance(row, dict)]

    def append(self, goal: str, success: bool, duration: float) -> None:
        with self.lock:
            rows = self._read()
            record: HistoryRecord = {
                "time": datetime.now(timezone.utc).isoformat(),
                "goal": goal[:500],
                "success": bool(success),
                "duration": round(duration, 2),
            }
            rows.append(record)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path: Path | None = None
            try:
                # Same directory ensures replace stays on the same filesystem.
                # Close before replacing: Windows will not replace an open file.
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self.path.parent,
                    prefix=f".{self.path.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as stream:
                    temporary_path = Path(stream.name)
                    json.dump(rows[-self.limit :], stream, indent=2)
                os.replace(temporary_path, self.path)
            finally:
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)

    def clear(self) -> None:
        with self.lock:
            self.path.unlink(missing_ok=True)
