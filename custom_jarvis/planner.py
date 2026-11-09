"""Open-Manus style Autonomous Planner & Orchestrator for Custom Jarvis.

Implements an autonomous goal execution loop:
1. Analyze goal and classify intent (Microsoft Jarvis / HuggingGPT style).
2. Decompose into action steps.
3. For each step, call appropriate tools from custom_jarvis.tools.
4. Reflect and observe: read execution output, check if errors occurred.
5. Self-Correction: if a tool failed, formulate an alternative command or fix, and retry.
6. Terminate when the goal is achieved or a maximum step count is reached.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from custom_jarvis import plan_state
from custom_jarvis import settings as config
from custom_jarvis.brain import (
    CorrectionDecision,
    IntentResult,
    IntentType,
    JarvisBrain,
)
from custom_jarvis.tools import ToolRegistry, ToolResult
from custom_jarvis.tools import registry as default_tool_registry

logger = logging.getLogger("JarvisPlanner")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO, format="[%(asctime)s] [%(name)s] %(levelname)s: %(message)s"
    )


class StepStatus(str, Enum):
    """Execution status of an individual action step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


@dataclass
class PlanStep:
    """An individual atomic action step in the autonomous plan."""

    step_id: int
    description: str
    tool_name: str
    tool_args: Dict[str, Any]
    expected_outcome: Optional[str] = None
    status: StepStatus = StepStatus.PENDING
    output: Optional[str] = None
    error: Optional[str] = None
    attempts: int = 0
    max_attempts: int = config.MAX_RETRIES_PER_STEP
    execution_time: float = 0.0
    reflection_notes: List[str] = field(default_factory=list)
    verification: str = "not_run"
    evidence: Optional[str] = None
    backup_id: Optional[str] = None
    data: Any = None
    artifact_sha256: Optional[str] = None
    resolved_args: Optional[Dict[str, Any]] = None
    approval_recorded: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "description": self.description,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "expected_outcome": self.expected_outcome,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "attempts": self.attempts,
            "execution_time": self.execution_time,
            "reflection_notes": self.reflection_notes,
            "verification": self.verification,
            "evidence": self.evidence,
            "backup_id": self.backup_id,
            "data": self.data,
            "artifact_sha256": self.artifact_sha256,
            "resolved_args": self.resolved_args,
            "approval_recorded": self.approval_recorded,
        }


@dataclass
class Plan:
    """Represents a structured multi-step execution plan."""

    goal: str
    intent: IntentResult
    steps: List[PlanStep] = field(default_factory=list)
    current_step_index: int = 0
    is_completed: bool = False
    success: bool = False

    def get_current_step(self) -> Optional[PlanStep]:
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    def add_step(self, step: PlanStep):
        self.steps.append(step)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "intent": self.intent.to_dict(),
            "steps": [s.to_dict() for s in self.steps],
            "current_step_index": self.current_step_index,
            "is_completed": self.is_completed,
            "success": self.success,
        }


@dataclass
class PlanExecutionResult:
    """Final outcome returned after executing the goal loop."""

    goal: str
    intent: IntentResult
    success: bool
    plan: Plan
    total_steps_executed: int
    final_message: str
    execution_duration: float
    execution_log: List[str] = field(default_factory=list)
    spoken_message: Optional[str] = None
    goal_verification: Dict[str, Any] = field(default_factory=dict)

    @property
    def summary(self) -> str:
        """Alias for final_message to maintain backward compatibility."""
        return self.final_message

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "intent": self.intent.to_dict(),
            "success": self.success,
            "plan": self.plan.to_dict(),
            "total_steps_executed": self.total_steps_executed,
            "final_message": self.final_message,
            "execution_duration": self.execution_duration,
            "execution_log": self.execution_log,
            "goal_verification": self.goal_verification,
            "verified_steps": sum(
                s.verification == "verified" for s in self.plan.steps
            ),
            "verification_scope": "Individual tool postconditions only; overall goal is not independently verified",
        }


class AutonomousPlanner:
    """Autonomous Goal Execution Loop Agent (Open-Manus + Microsoft Jarvis)."""

    def __init__(
        self,
        brain: Optional[JarvisBrain] = None,
        tool_registry: Optional[ToolRegistry] = None,
        max_steps: Optional[int] = None,
        verbose: bool = True,
    ):
        self.brain = brain or JarvisBrain()
        self.tool_registry = tool_registry or default_tool_registry
        self.max_steps = max_steps or config.MAX_PLAN_STEPS
        self.verbose = verbose
        self.governor = None
        self.preflight_doctor = None
        self._resume_verified = None

        # Observability Callbacks
        self.on_intent_classified: Optional[Callable[[IntentResult], None]] = None
        self.on_plan_created: Optional[Callable[[Plan], None]] = None
        self.on_step_start: Optional[Callable[[PlanStep], None]] = None
        self.on_step_completed: Optional[Callable[[PlanStep, ToolResult], None]] = None
        self.on_reflection: Optional[Callable[[PlanStep, CorrectionDecision], None]] = (
            None
        )
        self.on_checkpoint: Optional[Callable[[Dict[str, Any]], None]] = None

    def _checkpoint(self, plan: Plan, *, persist: bool = True) -> bool:
        # The active-plan file is a minimal, non-output checkpoint. `on_checkpoint`
        # is a separate opt-in store and may hold more detail behind its own approval.
        """Persist minimal resume state and any explicitly approved checkpoint."""
        saved = True
        if persist:
            try:
                if plan.is_completed:
                    saved = plan_state.clear()
                else:
                    payload = plan.to_dict()
                    engine = getattr(self.tool_registry, "engine", None)
                    workspace = getattr(engine, "workspace", None)
                    payload["workspace"] = (
                        str(Path(workspace).resolve()) if workspace is not None else None
                    )
                    saved = plan_state.save(payload)
            except Exception:
                saved = False
                logger.exception("Could not record the running plan")
            if self.on_checkpoint:
                try:
                    self.on_checkpoint(plan.to_dict())
                except Exception:
                    logger.exception(
                        "Checkpoint storage failed; task remains inspectable in memory"
                    )
        return bool(saved)

    def _log(self, message: str, prefix: str = "[J.A.R.V.I.S.]"):
        """Print stylized output for user/console observability."""
        formatted = f"{prefix} {message}"
        if self.verbose:
            print(formatted)
        logger.info(message)

    def _resolve_step_args(self, args: Any, context: Dict[str, Any]) -> Any:
        """Resolve placeholders in tool arguments using previous step outputs/data.

        Supports:
        - Exact matches: "$PREV_OUTPUT", "{{prev_output}}", "$OUTPUT", "{{output}}"
        - In-string interpolation: "... {{prev_output}} ...", "... $PREV_OUTPUT ..."
        - Specific step references: "$STEP_1_OUTPUT", "{{step_1.output}}", "{{step_1_output}}"
        - Structured data references: "$STEP_1_DATA", "{{step_1.data}}", "$PREV_DATA", "{{prev_data}}"
        """
        if isinstance(args, dict):
            return {k: self._resolve_step_args(v, context) for k, v in args.items()}
        elif isinstance(args, list):
            return [self._resolve_step_args(item, context) for item in args]
        elif isinstance(args, str):
            # Most arguments are literal paths/text. Avoid regex work entirely
            # when neither placeholder introducer is present. Preserve whitespace.
            if "$" not in args and "{" not in args:
                return args
            val = args.strip()
            # 1. Exact match replacements (preserves structured types if data is dict/list/int)
            if val in (
                "$PREV_OUTPUT",
                "{{prev_output}}",
                "{prev_output}",
                "$OUTPUT",
                "{{output}}",
                "{output}",
            ):
                return context.get("prev_output", "")
            if val in ("$PREV_DATA", "{{prev_data}}", "{prev_data}"):
                return context.get("prev_data", None)

            m_exact_step = re.match(
                r"^(\$STEP_(\d+)_OUTPUT|\{\{step_(\d+)\.output\}\}|\{step_(\d+)_output\})$",
                val,
                re.IGNORECASE,
            )
            if m_exact_step:
                s_id = int(
                    m_exact_step.group(2)
                    or m_exact_step.group(3)
                    or m_exact_step.group(4)
                )
                return context.get("step_outputs", {}).get(s_id, "")

            m_exact_data = re.match(
                r"^(\$STEP_(\d+)_DATA|\{\{step_(\d+)\.data\}\})$",
                val,
                re.IGNORECASE,
            )
            if m_exact_data:
                s_id = int(m_exact_data.group(2) or m_exact_data.group(3))
                return context.get("step_data", {}).get(s_id, None)

            # 2. In-string placeholder substitution
            res_str = args
            for placeholder in (
                "{{prev_output}}",
                "{prev_output}",
                "$PREV_OUTPUT",
                "{{output}}",
                "{output}",
                "$OUTPUT",
            ):
                if placeholder in res_str:
                    res_str = res_str.replace(
                        placeholder, str(context.get("prev_output", ""))
                    )

            for s_id, s_out in context.get("step_outputs", {}).items():
                p1 = r"\{\{step_" + str(s_id) + r"\.output\}\}"
                p2 = r"\{step_" + str(s_id) + r"_output\}"
                p3 = r"\$STEP_" + str(s_id) + r"_OUTPUT\b"
                res_str = re.sub(
                    p1, lambda match: str(s_out), res_str, flags=re.IGNORECASE
                )
                res_str = re.sub(
                    p2, lambda match: str(s_out), res_str, flags=re.IGNORECASE
                )
                res_str = re.sub(
                    p3, lambda match: str(s_out), res_str, flags=re.IGNORECASE
                )

            return res_str
        return args

    def execute(
        self,
        goal,
        intent_override=None,
        force_plan=False,
        plan_only=False,
        prepared_steps=None,
    ):
        started = time.monotonic()
        result = None
        try:
            result = self._execute(
                goal, intent_override, force_plan, plan_only, prepared_steps
            )
            return result
        finally:
            if self.governor:
                self.governor.record_task_duration(
                    time.monotonic() - started,
                    aborted=result is None or (not result.success and not plan_only),
                )

    def _execute(
        self,
        goal: str,
        intent_override: Optional[IntentType] = None,
        force_plan: bool = False,
        plan_only: bool = False,
        prepared_steps: Optional[List[Dict[str, Any]]] = None,
    ) -> PlanExecutionResult:
        """Run the complete autonomous goal execution loop.

        Args:
            goal: The high-level user goal or prompt.
            intent_override: Optional override for intent classification.
            force_plan: If True, forces execution through the planning loop even if classified as conversation.

        Returns:
            PlanExecutionResult containing steps, logs, and final status.
        """
        if prepared_steps is not None:
            intent_override = IntentType.MULTI_STEP_PLAN
            force_plan = True
        from custom_jarvis.goal_verifier import infer_goal_assertions, verify_goal
        from custom_jarvis.preflight import CausalGraphTracker

        start_time = time.time()
        logs: List[str] = []

        def record(msg: str):
            logs.append(f"[{time.strftime('%X')}] {msg}")
            self._log(msg)

        record(f'Goal received: "{goal}"')

        # -------------------------------------------------------------
        # 1. Analyze Goal & Classify Intent (Microsoft Jarvis Routing)
        # -------------------------------------------------------------
        if intent_override:
            intent_result = IntentResult(
                intent=intent_override,
                confidence=1.0,
                reasoning="Explicit intent override provided.",
                suggested_skills=[intent_override.value],
                requires_multi_step=(intent_override == IntentType.MULTI_STEP_PLAN),
            )
        else:
            intent_result = self.brain.classify_intent(goal)

        if force_plan and intent_result.intent == IntentType.GENERAL_CONVERSATION:
            intent_result = IntentResult(
                intent=IntentType.SYSTEM_COMMAND,
                confidence=0.8,
                reasoning="Forced planning mode enabled.",
                suggested_skills=["system_command"],
                requires_multi_step=False,
            )
        if self.on_intent_classified:
            self.on_intent_classified(intent_result)

        record(
            f"Intent identified: {intent_result.intent.value.upper()} "
            f"(Confidence: {intent_result.confidence * 100:.1f}%)"
        )
        record(f"Reasoning: {intent_result.reasoning}")

        # If pure conversational and does not require multi-step action
        if (
            intent_result.intent == IntentType.GENERAL_CONVERSATION
            and not intent_result.requires_multi_step
        ):
            record("Direct conversational inquiry detected. Generating response...")
            response = self.brain.respond_conversation(goal)
            duration = round(time.time() - start_time, 2)
            empty_plan = Plan(
                goal=goal, intent=intent_result, is_completed=True, success=True
            )
            return PlanExecutionResult(
                goal=goal,
                intent=intent_result,
                success=True,
                plan=empty_plan,
                total_steps_executed=0,
                final_message=response,
                execution_duration=duration,
                execution_log=logs,
                spoken_message=response,
            )

        # -------------------------------------------------------------
        # 2. Decompose into Action Steps (Open-Manus Decomposition)
        # -------------------------------------------------------------
        available_tools = self.tool_registry.list_tools()
        raw_steps = (
            prepared_steps
            if prepared_steps is not None
            else self.brain.decompose_goal(goal, intent_result, available_tools)
        )
        if not isinstance(raw_steps, list) or any(
            not isinstance(st, dict) or not isinstance(st.get("tool_args", {}), dict)
            for st in raw_steps
        ):
            raise ValueError(
                "Plan must contain step objects with dictionary tool arguments"
            )

        plan_steps: List[PlanStep] = []
        for i, raw_step in enumerate(raw_steps, start=1):
            plan_steps.append(
                PlanStep(
                    step_id=raw_step.get("step_id", i),
                    description=raw_step.get("description", f"Action step {i}"),
                    tool_name=raw_step.get("tool_name", "run_shell"),
                    tool_args=raw_step.get("tool_args", {}),
                    expected_outcome=raw_step.get("expected_outcome"),
                    approval_recorded=bool(raw_step.get("approval_recorded", False)),
                )
            )

        plan = Plan(goal=goal, intent=intent_result, steps=plan_steps)
        engine = getattr(self.tool_registry, "engine", None)
        workspace = engine.workspace if engine is not None else None
        if self.preflight_doctor is not None and not plan_only:
            report = self.preflight_doctor.check_plan(
                plan.steps, workspace, bool(getattr(self.brain, "is_live", False))
            )
            if not report.ready:
                return PlanExecutionResult(
                    goal,
                    intent_result,
                    False,
                    plan,
                    0,
                    "Preflight blocked: " + str(report.blockers),
                    round(time.time() - start_time, 2),
                    logs,
                )
        if self.preflight_doctor is not None and prepared_steps is None:
            from custom_jarvis.brain import detect_intent_ambiguity
            from custom_jarvis.runtime import ControlledRegistry

            if any(
                step.tool_name not in ControlledRegistry.READ_ONLY
                for step in plan.steps
            ):
                ambiguity = detect_intent_ambiguity(goal, workspace)
                if ambiguity["ambiguous"]:
                    return PlanExecutionResult(
                        goal,
                        intent_result,
                        False,
                        plan,
                        0,
                        ambiguity["clarification_question"],
                        round(time.time() - start_time, 2),
                        logs,
                    )
        tracker = CausalGraphTracker(getattr(engine, "store", None))
        if hasattr(self.tool_registry, "begin_plan") and not plan_only:
            self.tool_registry.begin_plan()
            for old in self._resume_verified or []:
                args = old.resolved_args or old.tool_args
                if old.artifact_sha256 and args.get("path"):
                    engine.drift_guard.observe_file(
                        Path(args["path"]), old.artifact_sha256
                    )
        if self._resume_verified is not None:
            for index, old in enumerate(self._resume_verified):
                plan.steps[index] = old
            plan.current_step_index = len(self._resume_verified)
        if self.on_plan_created:
            self.on_plan_created(plan)
        self._checkpoint(plan, persist=not plan_only)

        if plan_only:
            return PlanExecutionResult(
                goal=goal,
                intent=intent_result,
                success=bool(plan.steps),
                plan=plan,
                total_steps_executed=0,
                final_message=(
                    f"Preview ready: {len(plan.steps)} proposed step(s). No tools were executed. "
                    "Turn off Preview and submit again to run with per-action approvals."
                ),
                execution_duration=round(time.time() - start_time, 2),
                execution_log=logs,
                spoken_message="Plan preview ready. No tools were executed.",
            )

        record(f"Formulated execution plan with {len(plan.steps)} action step(s):")
        for st in plan.steps:
            record(f"  [{st.step_id}] {st.description} (Tool: {st.tool_name})")

        # -------------------------------------------------------------
        # 3. Autonomous Execution & Self-Correction Loop
        # -------------------------------------------------------------
        total_steps_executed = 0
        overall_success = bool(plan.steps)
        execution_context: Dict[str, Any] = {
            "prev_output": "",
            "prev_data": None,
            "step_outputs": {},
            "step_data": {},
        }

        if self._resume_verified is not None:
            verified = self._resume_verified
            self._resume_verified = None
            for index, old in enumerate(verified):
                plan.steps[index] = old
                execution_context["prev_output"] = old.output or ""
                execution_context["prev_data"] = old.data
                execution_context["step_outputs"][old.step_id] = old.output or ""
                execution_context["step_data"][old.step_id] = old.data
            plan.current_step_index = len(verified)
        while plan.current_step_index < len(plan.steps):
            if total_steps_executed >= self.max_steps:
                record(
                    f"[!] Warning: Maximum execution step limit ({self.max_steps}) reached. Halting loop."
                )
                overall_success = False
                break

            step = plan.get_current_step()
            if not step:
                break

            total_steps_executed += 1
            step.attempts += 1
            step.status = StepStatus.RUNNING

            # Resolve step arguments using execution context (prior step outputs / data)
            resolved_args = self._resolve_step_args(step.tool_args, execution_context)
            step.resolved_args = dict(resolved_args)

            record(
                f"\n--- [Step {step.step_id}/{len(plan.steps)}] (Attempt {step.attempts}): {step.description} ---"
            )
            record(f"Invoking tool: '{step.tool_name}' with args: {resolved_args}")

            if self.on_step_start:
                self.on_step_start(step)

            self._checkpoint(plan)

            # Persist the per-step approval record before a gated tool can run. The
            # record is for audit/resume state, not a reusable authorization token.
            previous_approval_observer = getattr(self.tool_registry, "on_approval", None)
            if hasattr(self.tool_registry, "on_approval"):
                def record_approval(_name, _arguments, _step=step):
                    _step.approval_recorded = True
                    return self._checkpoint(plan)

                self.tool_registry.on_approval = record_approval
            try:
                tool_res: ToolResult = self.tool_registry.execute(
                    step.tool_name, **resolved_args
                )
            finally:
                if hasattr(self.tool_registry, "on_approval"):
                    self.tool_registry.on_approval = previous_approval_observer
            step.execution_time = tool_res.execution_time
            step.verification = tool_res.metadata.get(
                "verification", "executed_unverified" if tool_res.success else "failed"
            )
            step.evidence = tool_res.metadata.get("evidence")
            step.backup_id = tool_res.metadata.get("backup_id")
            step.data = tool_res.data
            step.artifact_sha256 = tool_res.metadata.get("artifact_sha256")

            # ---------------------------------------------------------
            # 4. Reflect and Observe Execution Output
            # ---------------------------------------------------------
            if tool_res.success:
                step.status = StepStatus.COMPLETED
                step.output = tool_res.output
                step.error = None

                # Update execution context so subsequent steps can reference this step's output
                execution_context["prev_output"] = tool_res.output or ""
                execution_context["prev_data"] = tool_res.data
                execution_context["step_outputs"][step.step_id] = tool_res.output or ""
                execution_context["step_data"][step.step_id] = tool_res.data

                record(
                    f"[+] Step {step.step_id} succeeded in {tool_res.execution_time}s."
                )
                if tool_res.output:
                    snippet = tool_res.output[:200] + (
                        "..." if len(tool_res.output) > 200 else ""
                    )
                    record(f"    Output: {snippet}")

                if self.on_step_completed:
                    self.on_step_completed(step, tool_res)

                # Advance to next step in the plan
                plan.current_step_index += 1
                self._checkpoint(plan)

            else:
                # -----------------------------------------------------
                # 5. Self-Correction & Reflection on Failure
                # -----------------------------------------------------
                tracker.record(step, tool_res.error or "", tool_res.metadata)
                step.status = StepStatus.RETRYING
                step.output = tool_res.output
                step.error = tool_res.error
                record(f"[-] Step {step.step_id} failed: {tool_res.error}")
                self._checkpoint(plan)

                # A locked/non-interactive desktop requires user intervention, not
                # speculative clicks, shell workarounds, or repeated model calls.
                if tool_res.metadata.get("requires_user_action"):
                    step.status = StepStatus.FAILED
                    overall_success = False
                    if self.on_step_completed:
                        self.on_step_completed(step, tool_res)
                    record(f"[!] User action required: {tool_res.error}")
                    break

                max_allowed = max(1, step.max_attempts or config.MAX_RETRIES_PER_STEP)
                if step.attempts >= max_allowed:
                    step.status = StepStatus.FAILED
                    record(
                        f"[!] Step {step.step_id} exceeded max attempts ({max_allowed}). Aborting step."
                    )
                    overall_success = False
                    break

                record("Reflecting on failure and formulating corrective action...")
                decision = self.brain.reflect_and_correct(
                    goal=goal,
                    step=step.to_dict(),
                    execution_output=tool_res.output,
                    error=tool_res.error,
                    available_tools=available_tools,
                    attempt_num=step.attempts,
                )

                note = f"Attempt {step.attempts} failed. Action: {decision.action} ({decision.explanation})"
                step.reflection_notes.append(note)
                record(
                    f"[?] Reflection verdict: {decision.action} -> {decision.explanation}"
                )

                if self.on_reflection:
                    self.on_reflection(step, decision)

                action = (decision.action or "").strip().upper()

                if action in ("RETRY_WITH_NEW_ARGS", "RETRY", "RETRY_NEW_ARGS"):
                    if decision.new_tool_args is not None:
                        step.tool_args = decision.new_tool_args
                    if decision.new_tool_name:
                        step.tool_name = decision.new_tool_name
                    record(f"Adjusted parameters for step {step.step_id}. Retrying...")

                elif action in (
                    "TRY_ALTERNATIVE_TOOL",
                    "ALTERNATIVE_TOOL",
                    "SWAP_TOOL",
                ):
                    if decision.new_tool_name:
                        step.tool_name = decision.new_tool_name
                    if decision.new_tool_args is not None:
                        step.tool_args = decision.new_tool_args
                    record(
                        f"Swapped to alternative tool '{step.tool_name}'. Retrying..."
                    )

                elif action in ("SKIP_STEP", "SKIP", "CONTINUE"):
                    step.status = StepStatus.SKIPPED
                    record(
                        f"Step {step.step_id} marked as SKIPPED ({decision.explanation}). Continuing plan."
                    )
                    plan.current_step_index += 1

                elif action in ("ABORT", "CANCEL", "STOP", "FAIL"):
                    step.status = StepStatus.FAILED
                    record(
                        f"Mission aborted by reflection agent: {decision.explanation}"
                    )
                    overall_success = False
                    break

                else:
                    logger.warning(
                        f"Unrecognized reflection action '{decision.action}'. Defensively retrying or aborting."
                    )
                    if step.attempts >= max_allowed:
                        step.status = StepStatus.FAILED
                        overall_success = False
                        break
                    if decision.new_tool_args is not None:
                        step.tool_args = decision.new_tool_args
                    if decision.new_tool_name:
                        step.tool_name = decision.new_tool_name

        # -------------------------------------------------------------
        # 6. Terminate & Final Status Report
        # -------------------------------------------------------------
        plan.is_completed = plan.current_step_index >= len(plan.steps)
        plan.success = overall_success and plan.is_completed
        self._checkpoint(plan)
        duration = round(time.time() - start_time, 2)
        if plan.success:
            final_message = (
                f"Tool plan reached its end after {total_steps_executed} attempt(s) ({duration}s), Sir. "
                f"Verified tool postconditions: {sum(st.verification == 'verified' for st in plan.steps)}/{len(plan.steps)}. "
                "Overall goal completion has not been independently verified."
            )
            record(f"[+] {final_message}")
        else:
            final_message = (
                f"Goal could not be completed satisfactorily. Execution stopped after "
                f"{total_steps_executed} step(s) ({duration}s)."
            )
            failed_step = next(
                (s for s in plan.steps if s.status == StepStatus.FAILED), None
            )
            if failed_step and failed_step.error:
                final_message += f" {failed_step.error}"
                companion_spoken = final_message
            record(f"[-] {final_message}")

        # Use the evidence-grounded status for speech as well; a generated summary
        # must not accidentally turn "tool executed" into "goal verified".
        companion_spoken = final_message
        goal_verification = verify_goal(
            infer_goal_assertions(goal, plan.steps, workspace), workspace, plan.steps
        )
        return PlanExecutionResult(
            goal=goal,
            intent=intent_result,
            success=plan.success,
            plan=plan,
            total_steps_executed=total_steps_executed,
            final_message=final_message,
            execution_duration=duration,
            execution_log=logs,
            spoken_message=companion_spoken,
            goal_verification=goal_verification,
        )

    def resume_from_checkpoint(self, checkpoint_payload, approve_resume=True):
        """Validate a saved plan, verify completed artifacts, and resume safely."""
        if not approve_resume:
            raise ValueError("Explicit resume approval is required")
        engine = getattr(self.tool_registry, "engine", None)
        if engine is None or engine.workspace is None:
            raise ValueError("Resume requires a workspace-confined registry")
        payload, rows = _validated_checkpoint(checkpoint_payload, engine)
        completed = _restore_completed_steps(rows, engine)
        self._resume_verified = completed
        try:
            return self.execute(
                payload.get("goal", "Resume reviewed plan"), prepared_steps=rows
            )
        finally:
            self._resume_verified = None


def _validated_checkpoint(checkpoint_payload, engine):
    """Validate resume payload, workspace binding, and omitted-output references."""
    if not isinstance(checkpoint_payload, dict):
        raise ValueError("Checkpoint must be an object")
    payload = checkpoint_payload.get("plan", checkpoint_payload)
    if not isinstance(payload, dict):
        raise ValueError("Checkpoint plan must be an object")
    rows = payload.get("steps", [])
    if not isinstance(rows, list) or not rows or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Checkpoint has no valid steps")
    saved_workspace = payload.get("workspace")
    if (not isinstance(saved_workspace, str)
            or Path(saved_workspace).resolve() != Path(engine.workspace).resolve()):
        raise ValueError("Checkpoint workspace does not match the selected workspace")
    for row in rows:
        if (plan_state.has_step_output_references(row.get("tool_args", {}))
                or plan_state.has_step_output_references(row.get("resolved_args", {}))):
            raise ValueError(
                "This checkpoint depends on step outputs that are not persisted; "
                "review and restart the plan manually."
            )
    return payload, rows


def _restore_completed_step(row, engine):
    """Recreate a completed artifact step only when its current bytes are verified."""
    from custom_jarvis.evidence import file_digest

    args = engine.prepare_args(row["tool_name"], row.get("tool_args", {}))
    path = args.get("path")
    if not isinstance(path, str):
        raise ValueError(
            "Completed non-artifact action cannot be independently verified; manual review required"
        )
    expected = row.get("artifact_sha256")
    if row.get("backup_id"):
        import json

        folder = engine.backups._folder(row["backup_id"])
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        if Path(manifest["path"]).resolve() != Path(path).resolve():
            raise ValueError("Checkpoint backup target mismatch")
        expected = manifest.get("after_sha256")
    if not expected or file_digest(Path(path)) != expected:
        raise ValueError("Completed artifact changed or lacks a verified fingerprint")
    return PlanStep(
        row["step_id"],
        row.get("description", "Restored step"),
        row["tool_name"],
        row.get("tool_args", {}),
        status=StepStatus.COMPLETED,
        output=row.get("output"),
        data=row.get("data"),
        artifact_sha256=expected,
        backup_id=row.get("backup_id"),
        resolved_args=args,
        verification=row.get("verification", "executed_unverified"),
        approval_recorded=bool(row.get("approval_recorded", False)),
    )


def _restore_completed_steps(rows, engine):
    """Restore only a contiguous prefix of independently verified file steps."""
    completed = []
    pending_seen = False
    for row in rows:
        if row.get("status") != "completed":
            pending_seen = True
            continue
        if pending_seen:
            raise ValueError("Non-contiguous checkpoint completion cannot be safely resumed")
        completed.append(_restore_completed_step(row, engine))
    return completed
