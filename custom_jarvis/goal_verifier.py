"""Deterministic, workspace-confined assertions; never executes project code."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from custom_jarvis.evidence import bounded_text, file_digest


@dataclass(frozen=True)
class GoalAssertion:
    kind: str
    target: str
    expected: Any = None


def infer_goal_assertions(goal, steps, workspace):
    assertions = []
    # Last write wins when a plan deliberately updates the same artifact twice.
    writes = {}
    for step in steps:
        args = getattr(step, "resolved_args", None) or step.tool_args
        path = args.get("path")
        if not isinstance(path, str) or "$" in path or "{" in path:
            continue
        if step.tool_name == "write_file" and isinstance(args.get("content"), str):
            content = args["content"].replace("\r\n", "\n").replace("\r", "\n")
            append = args.get("append") or args.get("mode") == "a"
            writes[path] = [
                GoalAssertion("file_exists", path),
                GoalAssertion(
                    "file_suffix" if append else "file_sha256",
                    path,
                    content
                    if append
                    else hashlib.sha256(
                        content.replace("\n", os.linesep).encode()
                    ).hexdigest(),
                ),
            ]
        elif step.tool_name in {"inspect_python", "inspect_json"}:
            assertions.append(
                GoalAssertion(
                    "python_valid"
                    if step.tool_name == "inspect_python"
                    else "json_valid",
                    path,
                )
            )
    for group in writes.values():
        assertions.extend(group)
    return assertions


def verify_goal(assertions, workspace, step_results):
    details = []
    root = Path(workspace).resolve() if workspace is not None else None
    for item in assertions:
        passed, error = False, None
        try:
            if root is None:
                raise ValueError("Independent file assertions require a workspace")
            path = (root / Path(item.target)).resolve()
            if not path.is_relative_to(root):
                raise ValueError("Assertion target outside workspace")
            if item.kind == "file_exists":
                passed = path.is_file()
            elif item.kind == "file_sha256":
                passed = file_digest(path) == item.expected
            elif item.kind == "file_digest":
                passed = file_digest(path) == item.expected
            elif item.kind == "file_contains":
                passed = item.expected in bounded_text(path)
            elif item.kind == "file_suffix":
                passed = bounded_text(path).endswith(item.expected)
            elif item.kind == "python_valid":
                ast.parse(bounded_text(path))
                passed = True
            elif item.kind == "json_valid":
                json.loads(bounded_text(path))
                passed = True
            elif item.kind == "json_key_equals":
                value = json.loads(bounded_text(path))
                passed = value[item.expected["key"]] == item.expected["value"]
            elif item.kind == "git_clean":
                result = subprocess.run(
                    [
                        "git",
                        "--no-optional-locks",
                        "-c",
                        "core.fsmonitor=false",
                        "status",
                        "--porcelain",
                    ],
                    cwd=path,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                passed = result.returncode == 0 and not result.stdout.strip()
            else:
                raise ValueError("Unknown goal assertion")
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            SyntaxError,
            subprocess.TimeoutExpired,
            RecursionError,
        ) as exc:
            error = str(exc)
        details.append(
            {"kind": item.kind, "target": item.target, "passed": passed, "error": error}
        )
    return {
        "goal_verified": bool(assertions) and all(row["passed"] for row in details),
        "assertions_checked": len(details),
        "assertions_passed": sum(row["passed"] for row in details),
        "details": details,
        "scope": "Deterministic postcondition assertions verified"
        if assertions
        else "No independent semantic goal assertions registered; tool postconditions only",
    }
