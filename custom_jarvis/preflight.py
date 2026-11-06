"""Read-only preconditions, dependency-aware incidents and optimistic drift guards."""

from __future__ import annotations

import os
import re
import shutil
import threading
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PreflightReport:
    ready: bool
    blockers: list[dict[str, str]]
    warnings: list[dict[str, str]]
    checked_tools: list[str]

    def to_dict(self):
        return asdict(self)


class PreflightDoctor:
    @staticmethod
    def check_plan(steps, workspace, has_api_key):
        from custom_jarvis.addon_runtime import INSPECTION_TOOLS
        from custom_jarvis.vision import VisionConfig

        blockers, warnings, checked = [], [], []
        for step in steps:
            tool = step.tool_name if hasattr(step, "tool_name") else step["tool_name"]
            checked.append(tool)

            def block(code, remediation):
                blockers.append(
                    {"code": code, "tool": tool, "remediation": remediation}
                )

            if (
                tool in INSPECTION_TOOLS or tool == "analyze_screenshot"
            ) and workspace is None:
                block(
                    "WORKSPACE_REQUIRED",
                    "Select a workspace folder before running project inspection tools.",
                )
            if workspace is not None and not Path(workspace).is_dir():
                block(
                    "WORKSPACE_MISSING",
                    "Selected workspace directory no longer exists.",
                )
            if tool == "git_inspect" and shutil.which("git") is None:
                block("GIT_BINARY_MISSING", "Install Git and ensure it is on PATH.")
            if tool == "analyze_screenshot":
                config = VisionConfig.from_env()
                if not config.configured or not config.allow_uploads:
                    block(
                        "VISION_NOT_CONFIGURED",
                        "Configure JARVIS_VISION_BASE_URL, JARVIS_VISION_MODEL, and JARVIS_VISION_ALLOW_UPLOADS=1.",
                    )
            if tool == "inspect_accessibility" and os.name != "nt":
                block(
                    "WINDOWS_UIA_REQUIRED",
                    "Windows UI Automation requires a Windows host.",
                )
        if not has_api_key:
            warnings.append(
                {
                    "code": "OFFLINE_REASONING",
                    "tool": "planner",
                    "remediation": "Offline deterministic plans remain available; configure a key for live reasoning.",
                }
            )
        return PreflightReport(not blockers, blockers, warnings, checked)


_TOKEN = re.compile(
    r"\$STEP_(\d+)_(?:OUTPUT|DATA)\b|\{\{step_(\d+)\.(?:output|data)\}\}|\{step_(\d+)_output\}",
    re.I,
)
_PREVIOUS = (
    "$PREV_OUTPUT",
    "{{prev_output}}",
    "{prev_output}",
    "$OUTPUT",
    "{{output}}",
    "{output}",
    "$PREV_DATA",
    "{{prev_data}}",
    "{prev_data}",
)


def extract_step_dependencies(tool_args: Any, current_step_id: int) -> set[int]:
    found = set()
    pending = [tool_args]
    count = 0
    while pending:
        count += 1
        if count > 10000:
            raise ValueError("Dependency structure exceeds limits")
        item = pending.pop()
        if isinstance(item, dict):
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, str):
            if current_step_id > 1 and any(
                token.lower() in item.lower() for token in _PREVIOUS
            ):
                found.add(current_step_id - 1)
            found.update(
                int(next(x for x in match.groups() if x))
                for match in _TOKEN.finditer(item)
            )
    return {n for n in found if 0 < n < current_step_id}


def classify_step_failure(
    step_id, tool_name, error, metadata, prior_failures, dependencies
):
    code = metadata.get("error_code", "TOOL_FAILED")
    upstream = sorted(d for d in dependencies if d in prior_failures)
    absolute = code in {
        "DESKTOP_UNAVAILABLE",
        "DENIED",
        "WORKSPACE_BOUNDARY",
        "PERMISSION_DENIED",
        "STATE_DRIFT_DETECTED",
    }
    root = (
        prior_failures[upstream[0]].get("root_cause_step_id", upstream[0])
        if upstream and not absolute
        else step_id
    )
    return {
        "step_id": step_id,
        "classification": "cascaded_symptom"
        if upstream and not absolute
        else "root_cause",
        "root_cause_step_id": root,
        "error_code": code,
    }


class CausalGraphTracker:
    def __init__(self, knowledge=None, task_id=None):
        self.knowledge = knowledge
        self.task_id = task_id or uuid.uuid4().hex
        self.failures = {}

    def record(self, step, error, metadata):
        node = classify_step_failure(
            step.step_id,
            step.tool_name,
            error,
            metadata,
            self.failures,
            extract_step_dependencies(step.tool_args, step.step_id),
        )
        self.failures[step.step_id] = node
        if self.knowledge:
            self.knowledge.record_causal_incident(
                uuid.uuid4().hex,
                self.task_id,
                step.step_id,
                step.tool_name,
                node["error_code"],
                node["root_cause_step_id"],
                node["classification"],
            )
        return node


class StateDriftGuard:
    def __init__(self):
        self.enforce_drift_check = True
        self.last_observed_window_title = None
        self.observed_file_digests = {}
        self.lock = threading.RLock()

    def reset(self):
        with self.lock:
            self.observed_file_digests.clear()
            self.last_observed_window_title = None

    def observe_file(self, target, digest=None):
        from custom_jarvis.evidence import file_digest

        target = Path(target).resolve()
        with self.lock:
            self.observed_file_digests[target] = digest or file_digest(target)

    def unchanged(self, target):
        from custom_jarvis.evidence import file_digest

        target = Path(target).resolve()
        with self.lock:
            original = self.observed_file_digests.get(target)
            if not self.enforce_drift_check or original is None:
                return True
            try:
                return target.is_file() and file_digest(target) == original
            except OSError:
                return False
