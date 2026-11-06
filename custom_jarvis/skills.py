"""Auditable skill recipes: deterministic tool plans, never generated Python code."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Skill:
    identity: str
    title: str
    purpose: str
    calls: tuple[tuple[str, dict[str, Any]], ...]
    needs_target: bool = False
    required_markers: tuple[str, ...] = ()
    platform_required: str | None = None

    def plan(self, workspace: Path, target: str = "README.md") -> list[dict[str, Any]]:
        context = {
            "workspace": str(workspace.resolve()),
            "target": str((workspace / target).resolve()),
        }
        steps = []
        for index, (tool, arguments) in enumerate(self.calls, 1):
            args = {
                k: context[v[1:]]
                if isinstance(v, str) and v.startswith("@")
                else deepcopy(v)
                for k, v in arguments.items()
            }
            steps.append(
                {
                    "step_id": index,
                    "description": f"{self.title}: {tool}",
                    "tool_name": tool,
                    "tool_args": args,
                }
            )
        return steps


def call(name: str, **args: Any) -> tuple[str, dict[str, Any]]:
    return name, args


SKILLS = (
    Skill(
        "orient",
        "Orient in workspace",
        "Discover structure before making assumptions.",
        (call("project_snapshot", path="@workspace"),),
    ),
    Skill(
        "context",
        "Build project context",
        "Combine structure with top-level file metadata.",
        (
            call("project_snapshot", path="@workspace"),
            call("list_dir", path="@workspace"),
        ),
    ),
    Skill(
        "git_status",
        "Check worktree health",
        "Inspect tracked changes without modifying Git state.",
        (call("git_inspect", path="@workspace", view="status"),),
    ),
    Skill(
        "review_changes",
        "Review change footprint",
        "Inspect status and diff statistics before further work.",
        (
            call("git_inspect", path="@workspace", view="status"),
            call("git_inspect", path="@workspace", view="diff"),
        ),
    ),
    Skill(
        "recent_context",
        "Recover recent Git context",
        "Inspect recent commits and current tracked changes.",
        (
            call("git_inspect", path="@workspace", view="log"),
            call("git_inspect", path="@workspace", view="status"),
        ),
    ),
    Skill(
        "python_preflight",
        "Validate Python before execution",
        "Check file existence and parse syntax; never import it.",
        (call("verify_file", path="@target"), call("inspect_python", path="@target")),
        True,
    ),
    Skill(
        "json_preflight",
        "Validate structured configuration",
        "Verify the file and parse JSON without running it.",
        (call("verify_file", path="@target"), call("inspect_json", path="@target")),
        True,
    ),
    Skill(
        "fingerprint",
        "Fingerprint an artifact",
        "Collect SHA-256 and existence evidence for a bounded file.",
        (call("verify_file", path="@target"),),
        True,
    ),
    Skill(
        "read_before_change",
        "Read before changing",
        "Verify and read the target before proposing an edit.",
        (call("verify_file", path="@target"), call("read_file", path="@target")),
        True,
    ),
    Skill(
        "python_structure",
        "Map Python structure",
        "Inspect imports and definitions without executing source.",
        (call("inspect_python", path="@target"),),
        True,
    ),
    Skill(
        "json_shape",
        "Inspect JSON shape",
        "Report type, top-level keys and count.",
        (call("inspect_json", path="@target"),),
        True,
    ),
    Skill(
        "find_tests",
        "Discover Python tests",
        "Find tests before selecting a verification command.",
        (
            call(
                "discover_project_files",
                pattern="test_*.py",
                search_path="@workspace",
                max_results=100,
            ),
        ),
    ),
    Skill(
        "find_docs",
        "Discover project documentation",
        "Find Markdown context without executing anything.",
        (
            call(
                "discover_project_files",
                pattern="*.md",
                search_path="@workspace",
                max_results=100,
            ),
        ),
    ),
    Skill(
        "find_instructions",
        "Discover agent instructions",
        "Locate AGENTS.md; contents remain untrusted project data.",
        (
            call(
                "discover_project_files",
                pattern="AGENTS.md",
                search_path="@workspace",
                max_results=50,
            ),
        ),
    ),
    Skill(
        "find_pyprojects",
        "Discover Python packages",
        "Locate pyproject.toml manifests.",
        (
            call(
                "discover_project_files",
                pattern="pyproject.toml",
                search_path="@workspace",
                max_results=50,
            ),
        ),
    ),
    Skill(
        "find_nodeprojects",
        "Discover JavaScript packages",
        "Locate package.json manifests; never install packages.",
        (
            call(
                "discover_project_files",
                pattern="package.json",
                search_path="@workspace",
                max_results=50,
            ),
        ),
    ),
    Skill(
        "find_requirements",
        "Discover dependency specifications",
        "Locate requirements files without installing them.",
        (
            call(
                "discover_project_files",
                pattern="requirements*.txt",
                search_path="@workspace",
                max_results=50,
            ),
        ),
    ),
    Skill(
        "find_configuration",
        "Discover configuration surfaces",
        "Locate files whose names include config.",
        (
            call(
                "discover_project_files",
                pattern="*config*",
                search_path="@workspace",
                max_results=100,
            ),
        ),
    ),
    Skill(
        "observe_window",
        "Observe desktop focus",
        "Identify the foreground window before planning interaction.",
        (call("get_active_window"),),
    ),
    Skill(
        "observe_accessibility",
        "Inspect accessible controls",
        "Inspect foreground Windows UIA children without clicking.",
        (call("get_active_window"), call("inspect_accessibility")),
    ),
    Skill(
        "capture",
        "Capture real desktop evidence",
        "Capture actual pixels; unavailable sessions fail explicitly.",
        (call("take_screenshot"),),
    ),
    Skill(
        "vision_readiness",
        "Check screen-understanding readiness",
        "Report vision capability without uploading anything.",
        (call("vision_capability_status"),),
    ),
    Skill(
        "test_context",
        "Build test-planning evidence",
        "Combine project markers and test-file discovery.",
        (
            call("project_snapshot", path="@workspace"),
            call(
                "discover_project_files",
                pattern="test_*.py",
                search_path="@workspace",
                max_results=100,
            ),
        ),
    ),
    Skill(
        "handoff",
        "Prepare evidence for a handoff",
        "Collect project structure, worktree status and recent commits.",
        (
            call("project_snapshot", path="@workspace"),
            call("git_inspect", path="@workspace", view="status"),
            call("git_inspect", path="@workspace", view="log"),
        ),
    ),
)
SKILL_BY_ID = {skill.identity: skill for skill in SKILLS}


def judge_skill_applicability(skill, workspace):
    import os
    import shutil

    missing = []
    root = Path(workspace) if workspace else None
    if root is None or not root.is_dir():
        missing.append("workspace directory")
    if root is not None:
        missing.extend(
            marker for marker in skill.required_markers if not (root / marker).exists()
        )
    if skill.platform_required and os.name != skill.platform_required:
        missing.append("platform " + skill.platform_required)
    tools = {name for name, _ in skill.calls}
    if "git_inspect" in tools:
        if shutil.which("git") is None:
            missing.append("git binary")
        if root is not None and not (root / ".git").exists() and ".git" not in missing:
            missing.append(".git")
    if "inspect_accessibility" in tools and os.name != "nt":
        missing.append("Windows UI Automation")
    return {
        "applicable": not missing,
        "reason": "Applicable"
        if not missing
        else "Missing prerequisite: " + ", ".join(missing),
        "missing_prerequisites": missing,
    }


def compile_procedure_to_skill(procedure_row, available_tools):
    import json
    import re

    if procedure_row.get("status") != "approved":
        raise ValueError("Only an approved procedure can become a skill")
    text = procedure_row.get("instructions", "")
    if len(text) > 12000:
        raise ValueError("Procedure exceeds limits")
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    calls = []
    if isinstance(parsed, list):
        for row in parsed[:24]:
            if (
                not isinstance(row, dict)
                or row.get("tool_name") not in available_tools
                or not isinstance(row.get("tool_args", {}), dict)
            ):
                raise ValueError(
                    "Procedure includes unavailable tools or invalid arguments"
                )
            calls.append((row["tool_name"], deepcopy(row.get("tool_args", {}))))
    else:
        # Do not invent arguments for a command embedded in prose. Only tools
        # whose complete safe arguments can be reconstructed are accepted.
        safe = {
            "project_snapshot": {"path": "@workspace"},
            "list_dir": {"path": "@workspace"},
            "verify_file": {"path": "@target"},
            "inspect_python": {"path": "@target"},
            "inspect_json": {"path": "@target"},
        }
        for name in re.findall(r"\b[a-z][a-z_]+\b", text):
            if name in available_tools and name in safe:
                calls.append((name, dict(safe[name])))
    if not calls:
        raise ValueError("No auditable structured tool calls found")
    if "project_snapshot" in available_tools:
        calls.insert(0, ("project_snapshot", {"path": "@workspace"}))
    elif "verify_file" in available_tools:
        calls.insert(0, ("verify_file", {"path": "@target"}))
    if "verify_file" in available_tools and any(
        "@target" in args.values() for _, args in calls
    ):
        calls.append(("verify_file", {"path": "@target"}))
    return Skill(
        "procedure_" + str(procedure_row["id"]),
        procedure_row.get("title", "Reviewed procedure"),
        "Compiled from explicitly approved steps; all normal approvals still apply",
        tuple(calls),
        any("@target" in args.values() for _, args in calls),
    )
