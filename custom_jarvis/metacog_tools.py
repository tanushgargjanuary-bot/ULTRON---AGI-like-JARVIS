"""custom_jarvis/metacog_tools.py — the metacognitive tools, as tools.

The ledger in `custom_jarvis/metacog.py` is the arithmetic. These are the handles
the assistant actually reaches for, so that "how sure are you, and why" has an
answer that comes from a record instead of from tone of voice.

Nine tools, three jobs:

    before a claim      record_prediction, open_predictions
    after the fact      resolve_prediction
    before a task       recall_lessons, choose_strategy, self_review
    after a task        record_lesson, record_attempt
    anytime             calibration_report

All read-only except the three that record, all local, all bounded by the ledger's
own limits. Nothing here executes project code or touches the workspace.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from custom_jarvis.metacog import Ledger
from custom_jarvis.tools import ToolRegistry, ToolResult


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)[:8000]


def register_metacog_tools(registry: ToolRegistry, ledger: Optional[Ledger] = None) -> None:
    """Attach the metacognitive tools. Idempotent: a second call does nothing."""
    if registry.get("calibration_report"):
        return
    ledger = ledger or Ledger("metacog.json")

    def register(name: str, description: str,
                 properties: Dict[str, Any], required: List[str]):
        return registry.register(
            name=name,
            description=description,
            category="metacognition",
            parameters={"type": "object", "properties": properties, "required": required},
        )

    @register(
        "record_prediction",
        "Record a claim with the confidence you are stating it at, so it can be "
        "scored later. Use it before answering anything that could be wrong.",
        {
            "claim": {"type": "string", "description": "The claim, in one sentence"},
            "confidence": {"type": "number", "description": "0.0 to 1.0"},
            "domain": {"type": "string", "description": "Topic, e.g. windows or python"},
        },
        ["claim", "confidence"],
    )
    def record_prediction(claim: str, confidence: float, domain: str = "general") -> ToolResult:
        try:
            row = ledger.record_prediction(claim, confidence, domain)
        except ValueError as exc:
            return ToolResult(False, error=str(exc))
        return ToolResult(True, output=_json(row), data=row)

    @register(
        "resolve_prediction",
        "Finish a recorded prediction with what actually happened: correct, "
        "partly, or wrong. This is the only way the record becomes evidence.",
        {
            "id": {"type": "string", "description": "The prediction id"},
            "outcome": {"type": "string", "description": "correct | partly | wrong"},
        },
        ["id", "outcome"],
    )
    def resolve_prediction(id: str, outcome: str) -> ToolResult:
        try:
            row = ledger.resolve_prediction(id, outcome)
        except ValueError as exc:
            return ToolResult(False, error=str(exc))
        return ToolResult(True, output=_json(row), data=row)

    @register(
        "open_predictions",
        "List predictions that have not been resolved yet — the questions this "
        "assistant still owes an answer to.",
        {
            "domain": {"type": "string"},
            "limit": {"type": "integer"},
        },
        [],
    )
    def open_predictions(domain: str = "", limit: int = 10) -> ToolResult:
        rows = ledger.open_predictions(domain, max(1, min(int(limit or 10), 50)))
        return ToolResult(True, output=_json(rows), data=rows)

    @register(
        "calibration_report",
        "How reliable this assistant has actually been: accuracy, an honest lower "
        "bound, Brier score, and the confidence buckets where it is overconfident.",
        {"domain": {"type": "string", "description": "Empty means every domain"}},
        [],
    )
    def calibration_report(domain: str = "") -> ToolResult:
        report = ledger.calibration(domain)
        return ToolResult(True, output=_json(report), data=report)

    @register(
        "record_lesson",
        "Store one mistake and the rule that prevents it. A lesson without a rule "
        "is a diary entry and is refused.",
        {
            "trigger": {"type": "string", "description": "The situation it applies to"},
            "mistake": {"type": "string", "description": "What went wrong"},
            "rule": {"type": "string", "description": "What to do instead, next time"},
            "domain": {"type": "string"},
        },
        ["trigger", "mistake", "rule"],
    )
    def record_lesson(trigger: str, mistake: str, rule: str, domain: str = "general") -> ToolResult:
        try:
            row = ledger.record_lesson(trigger, mistake, rule, domain)
        except ValueError as exc:
            return ToolResult(False, error=str(exc))
        return ToolResult(True, output=_json(row), data=row)

    @register(
        "recall_lessons",
        "Rank the stored rules against a task about to be attempted. Call this "
        "before repeating work that has failed before.",
        {
            "task": {"type": "string", "description": "What you are about to do"},
            "limit": {"type": "integer"},
        },
        ["task"],
    )
    def recall_lessons(task: str, limit: int = 5) -> ToolResult:
        rows = ledger.lessons_for(task, max(1, min(int(limit or 5), 20)))
        return ToolResult(True, output=_json(rows), data=rows)

    @register(
        "record_attempt",
        "Record which strategy was used for a task type and whether it worked, so "
        "the next attempt can be chosen on evidence.",
        {
            "task_type": {"type": "string", "description": "e.g. test_failure_triage"},
            "strategy": {"type": "string", "description": "e.g. read_stack_trace_first"},
            "success": {"type": "boolean"},
        },
        ["task_type", "strategy", "success"],
    )
    def record_attempt(task_type: str, strategy: str, success: bool) -> ToolResult:
        try:
            row = ledger.record_attempt(task_type, strategy, bool(success))
        except ValueError as exc:
            return ToolResult(False, error=str(exc))
        return ToolResult(True, output=_json(row), data=row)

    @register(
        "choose_strategy",
        "Pick the strategy with the best honest record for this task type. An "
        "untried strategy is preferred once, before trusting the rest.",
        {
            "task_type": {"type": "string"},
            "options": {"type": "array", "items": {"type": "string"}},
        },
        ["task_type"],
    )
    def choose_strategy(task_type: str, options: Optional[List[str]] = None) -> ToolResult:
        row = ledger.choose_strategy(task_type, options)
        return ToolResult(True, output=_json(row), data=row)

    @register(
        "self_review",
        "The pre-flight check on itself: calibration, the lessons that apply to "
        "this task, and the confidence buckets where it is overconfident.",
        {"task": {"type": "string", "description": "The task about to start"}},
        [],
    )
    def self_review(task: str = "") -> ToolResult:
        report = ledger.self_review(task)
        return ToolResult(True, output=_json(report), data=report)
