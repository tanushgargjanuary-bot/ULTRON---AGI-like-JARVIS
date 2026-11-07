"""MARK-hosted service: deterministic skills and evidence-scoped repair.

No widgets or provider imports at module import. Slow operations run in one
worker; each state-changing tool independently waits for the real HUD gate.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path

from core import policy
from custom_jarvis.addon_runtime import AddonRegistry
from custom_jarvis.addon_tools import register_addon_tools
from custom_jarvis.metacog import Ledger
from custom_jarvis.metacog_tools import register_metacog_tools
from custom_jarvis import skillpacks
from custom_jarvis.pack_tools import register_pack_tools
from custom_jarvis.ship_tools import register_ship_tools
from custom_jarvis.autonomy_governor import AutonomyGovernor
from custom_jarvis.brain import JarvisBrain
from custom_jarvis.evidence import BackupManager
from custom_jarvis.failure_memory import RepairCircuitBreaker
from custom_jarvis.goal_verifier import GoalAssertion, verify_goal
from custom_jarvis.hot_repair import ContractCase, HotRepairManager
from custom_jarvis.knowledge import KnowledgeStore
from custom_jarvis import plan_state
from custom_jarvis.planner import AutonomousPlanner
from custom_jarvis.preflight import PreflightDoctor
from custom_jarvis.self_healing import FailureIncident, RepairLoop
from custom_jarvis.skills import (
    SKILL_BY_ID,
    SKILLS,
    compile_procedure_to_skill,
    judge_skill_applicability,
)
from custom_jarvis.tools import ToolRegistry
from custom_jarvis.tools import registry as source_registry


class MarkRepairProvider:
    """Use MARK's chosen background provider, not the old Groq-specific client."""

    def list_models(self):
        # This is a routing identity, not a claim about the remote model's ID.
        return {"mark-selected-provider"}

    def propose(self, model, payload):
        from core import gemini

        prompt = (
            "Review this argument-adapter repair. Return JSON with action='candidate', "
            "source containing ONLY def adapt(args), intent and confidence; or action='stop', reason. "
            "Adapters are a bounded DSL: no imports, loops, eval, exec, IO, tools or arbitrary code. "
            "Use only the provided exact regression contracts; do not broaden scope.\n"
            + json.dumps(payload, ensure_ascii=False)
        )
        answer = gemini.as_json(prompt, tier=gemini.SMART)
        if not isinstance(answer, dict):
            return {
                "action": "stop",
                "reason": "Selected MARK provider returned no valid repair.",
            }
        return answer


class TrackedRepairs(HotRepairManager):
    """Feed actual manual/runtime rollbacks into the shared repair breaker."""

    def __init__(self, directory, breaker):
        self.breaker = breaker
        super().__init__(directory)

    def rollback(self, tool, *, expected_version=None):
        context = self.context_key(tool)
        before = self.current(tool)
        changed = super().rollback(tool, expected_version=expected_version)
        if changed:
            self.breaker.record_rollback(tool, context, before, self.current(tool))
        return changed


class CustomService:
    def __init__(self, data_dir: Path | None = None, approval=None):
        if data_dir is None:
            from core.paths import state_dir
            data_dir = state_dir()
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        # The repository this code lives in. Shipping and self-updating both need
        # it, and neither should guess: it is the parent of this package.
        self.repo_dir = Path(__file__).resolve().parents[1]
        self.store = KnowledgeStore(self.data_dir / "knowledge.sqlite3")
        self.backups = BackupManager(self.data_dir / "backups")
        raw = ToolRegistry()
        # Port unique inspection/file evidence tools, not the old UI, audio or
        # desktop implementation. MARK remains the desktop/voice host.
        for name in (
            "read_file",
            "write_file",
            "list_dir",
            "execute_command",
            "run_shell",
            "get_active_window",
            "take_screenshot",
        ):
            definition = source_registry.get(name)
            raw.register(
                name=name,
                description=definition.description,
                category=definition.category,
                parameters=definition.parameters,
            )(definition.handler)
        register_addon_tools(raw)
        # Meta-cognition lives beside the knowledge store: same data directory,
        # same "bounded and local" rule, its own file because it is a record of
        # the assistant's judgement rather than of the workspace.
        self.metacog = Ledger(self.data_dir / "metacog.json")
        register_metacog_tools(raw, self.metacog)
        # Skill packs: recipes Ultron wrote for itself, kept as data beside the
        # state. They are loaded here so a skill added yesterday is present
        # today without anyone editing skills.py.
        self.packs_dir = self.data_dir
        self.pack_errors = {}
        known = [row.get("name", "") for row in raw.list_tools()]
        register_pack_tools(raw, self.packs_dir, known, on_change=self._note_change)
        self.pack_errors = skillpacks.load(self.packs_dir, known)["errors"]
        # Shipping: the tools that publish this repository and update it from it.
        # Both ask for approval; neither is in the read-only set.
        register_ship_tools(raw, self.repo_dir, self.data_dir / "ship_pending.json")
        self.control = AddonRegistry(raw, self._approve_tool, self.store, self.backups)
        self.breaker = RepairCircuitBreaker()
        self.repairs = TrackedRepairs(self.data_dir / "repairs", self.breaker)
        self.control.hot_repairs = self.repairs
        self.governor = AutonomyGovernor(knowledge=self.store)
        self.control.on_failure = self._capture_failure
        self.incident = None
        self.candidate = None
        self.cases = None
        self.last_result = None
        self.last_error = None
        self.player = None
        self.approval_override = approval
        self.busy = threading.Lock()
        self.job_id = None
        # Reuse deterministic planner logic only. No old cloud provider or model
        # is constructed; MARK controls conversation and repair provider routing.
        brain = JarvisBrain(api_key="")
        self.planner = AutonomousPlanner(
            brain=brain, tool_registry=self.control, verbose=False
        )
        self.planner.governor = self.governor
        self.planner.preflight_doctor = PreflightDoctor
        self.planner.on_step_completed = None
        selected = self.data_dir / "workspace.json"
        if selected.exists():
            try:
                workspace = Path(json.loads(selected.read_text())["path"])
                if workspace.is_dir():
                    self.control.select_workspace(workspace)
                    self._sync_workspace_policy()
            except (OSError, ValueError, TypeError, KeyError):
                pass

    def _sync_workspace_policy(self) -> None:
        """Tell core/policy.py which folder the user approved.

        Without this, every write asks for confirmation even inside the
        workspace the user just picked, which is the behaviour that made the
        gate feel like it fired at random. With it, writes inside the chosen
        folder are routine and everything outside it still asks.
        """
        try:
            workspace = getattr(self.control.engine, "workspace", None)
            policy.set_workspace_roots([workspace] if workspace else [])
        except Exception:
            policy.set_workspace_roots([])
    def _capture_failure(self, name, args, result):
        self.incident = FailureIncident.capture(
            name,
            args,
            result.error or "Tool failed",
            "Custom MARK operation",
            metadata=result.metadata,
        )

    def _ship_auto_enabled(self) -> bool:
        """Has the owner pre-authorised publishing self-evolutions?

        Off unless `ship_auto` is true in config. The owner asked for every
        change to reach GitHub; publishing is still public, so it is a named
        grant he switches on, never a default this code chooses for him.
        """
        try:
            from memory.config_manager import load_api_keys
            value = load_api_keys().get("ship_auto", False)
        except Exception:                                      # noqa: BLE001
            return False
        return value is True or str(value).strip().lower() in ("1", "true", "yes", "on")

    def _auto_ship(self, reason: str) -> dict:
        """Ship one self-evolution, in the background, and never raise."""
        from custom_jarvis.ship import Shipper, token_from_environment

        def run() -> None:
            try:
                shipper = Shipper(self.repo_dir, token_from_environment(),
                                  log_path=self.data_dir / "ship_log.json")
                shipper.ship(f"{reason}", why=reason)
            except Exception:                                  # noqa: BLE001
                pass                                           # the ship log has the truth

        threading.Thread(target=run, name="ultron-ship", daemon=True).start()
        return {"started": True, "reason": reason}

    def _note_change(self, reason: str) -> None:
        """Record a self-evolution that is waiting to be shipped.

        The owner asked for every change, however small, to reach GitHub. It must
        not reach GitHub silently, though: a push is public. So the change is
        recorded here and `ship_status` reports it, and an approval ships it.
        """
        import json as _json
        path = self.data_dir / "ship_pending.json"
        try:
            rows = _json.loads(path.read_text(encoding="utf-8"))
            rows = rows if isinstance(rows, list) else []
        except (OSError, ValueError):
            rows = []
        auto = self._ship_auto_enabled()
        rows.append({"at": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
                     "reason": str(reason)[:200],
                     "status": "shipping" if auto else "waiting"})
        try:
            path.write_text(_json.dumps(rows[-50:], indent=1), encoding="utf-8")
        except OSError:
            pass
        if auto:
            self._auto_ship(str(reason)[:200])

    def _approve_tool(self, name, arguments):
        return self.approve(name, arguments)

    def approve(self, name, arguments):
        if self.approval_override is not None:
            return bool(self.approval_override(name, arguments))
        if self.player is None:
            return False
        from core import confirm

        if confirm.pending_title():
            return False
        accepted = threading.Event()
        title = "Approve custom action: " + name

        def allow_once():
            accepted.set()
            return "One reviewed invocation approved. Inspect its separate execution result."

        message = confirm.request(
            uuid.uuid4().hex,
            title,
            json.dumps(arguments, ensure_ascii=False, indent=2),
            allow_once,
        )
        if not message.startswith("[CONFIRMATION_PENDING]"):
            return False
        deadline = time.monotonic() + confirm.TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if self.control.cancelled.is_set():
                return False
            if accepted.wait(0.05):
                return not self.control.cancelled.is_set()
        return False

    def status(self):
        return {
            "workspace": str(self.control.engine.workspace)
            if self.control.engine.workspace
            else None,
            "busy": self.busy.locked(),
            "job_id": self.job_id,
            "last_result": self.last_result,
            "last_error": self.last_error,
            "budget": self.governor.status(),
            "repair_catalog": self.repairs.inventory(),
            "breaker": self.breaker.check(
                self.incident.tool, self.incident.context_key
            )[1:]
            if self.incident
            else None,
            "incident_fingerprint": self.incident.fingerprint
            if self.incident
            else None,
            "transaction_id": self.control.engine.transaction_id,
            "scope": "Custom service only. Native MARK tools keep their own implementations and verification semantics.",
        }

    def submit(self, operation, payload, player=None):
        if operation == "status":
            return self.status()
        if operation == "stop":
            self.control.cancelled.set()
            return {
                "cancellation_requested": True,
                "warning": "Completed effects are not undone; provider calls may still be running.",
            }
        if not self.busy.acquire(blocking=False):
            raise ValueError(
                "A custom task is running; inspect status or stop it first"
            )
        self.player = player
        self.control.cancelled.clear()
        self.last_error = None
        self.last_result = None
        self.job_id = uuid.uuid4().hex
        job_id = self.job_id

        def worker():
            try:
                self.last_result = self.perform(operation, payload)
                self.publish("Custom JARVIS result", self.last_result)
            except Exception as exc:
                self.last_error = str(exc)
                self.publish("Custom JARVIS stopped", {"error": str(exc)})
            finally:
                self.busy.release()

        threading.Thread(
            target=worker, name="custom-jarvis-" + job_id[:8], daemon=True
        ).start()
        return {
            "job_id": job_id,
            "state": "started",
            "note": "Not completion. Watch the HUD or query status; approve each requested change.",
        }

    def publish(self, title, result):
        if self.player is not None:
            try:
                self.player.show_content(
                    title, json.dumps(result, ensure_ascii=False, default=str)[:65536]
                )
                self.player.write_log(
                    title
                    + ": "
                    + (
                        "failed"
                        if self.last_error
                        else "inspect evidence in the content panel"
                    )
                )
            except Exception:
                pass

    def _require_approval(self, operation, payload):
        if not self.approve(operation, payload):
            raise ValueError(
                "Explicit human approval was denied, cancelled, unavailable or expired"
            )

    def perform(self, operation, p):
        if operation in {
            "insights",
            "recommendations",
            "review_insight",
            "reject_insight",
            "forget_insights",
        }:
            from core.insights import get_insights

            engine = get_insights()
            if operation in {"insights", "recommendations"}:
                return engine.review()
            if operation == "forget_insights":
                self._require_approval(
                    operation,
                    {
                        "warning": "Delete approved insight preferences and all temporary candidates/checklists."
                    },
                )
                engine.forget()
                return {"forgotten": True}
            pending = engine.review()["pending"]
            identity = p.get("id") or (pending[0]["id"] if pending else None)
            row = next((row for row in pending if row["id"] == identity), None)
            if row is None:
                raise ValueError(
                    "Insight expired or missing; review current candidates"
                )
            if operation == "reject_insight":
                engine.reject(row["id"])
                return {"rejected": True, "saved": False}
            expected = {"key": row["key"], "value": row["value"]}
            self._require_approval(
                "save_reviewed_insight",
                {
                    **expected,
                    "evidence": row["evidence"],
                    "warning": "This exact preference will persist locally. No code or tool permissions change.",
                },
            )
            return {"approved": engine.approve(row["id"], expected)}
        if operation == "set_workspace":
            self._require_approval(operation, p)
            path = Path(p["path"]).resolve()
            self.control.select_workspace(path)
            self._sync_workspace_policy()
            (self.data_dir / "workspace.json").write_text(
                json.dumps({"path": str(path)})
            )
            return {"workspace": str(path)}
        if operation == "list_skills":
            return [
                {
                    "id": s.identity,
                    "title": s.title,
                    **judge_skill_applicability(s, self.control.engine.workspace),
                }
                for s in SKILLS
            ]
        if operation == "knowledge_status":
            return {
                "tools": self.store.statistics(),
                "models": self.store.competence(),
                "procedures": self.store.procedures(),
                "checkpoints": self.store.checkpoints(),
            }
        if operation == "list_tools":
            return self.control.list_tools()
        if operation == "tool":
            name = p["name"]
            if name not in {row["name"] for row in self.control.list_tools()}:
                raise ValueError("Unknown custom tool")
            # Never bypass ControlledRegistry.execute or workspace preparation.
            result = self.control.execute(name, **p.get("arguments", {}))
            return {
                "success": result.success,
                "output": result.output,
                "data": result.data,
                "error": result.error,
                "metadata": result.metadata,
            }
        if operation in {"run_skill", "preview_skill"}:
            if self.control.engine.workspace is None:
                raise ValueError("Select a workspace first")
            skill = SKILL_BY_ID[p["id"]]
            applicability = judge_skill_applicability(
                skill, self.control.engine.workspace
            )
            if not applicability["applicable"]:
                raise ValueError(applicability["reason"])
            steps = skill.plan(
                self.control.engine.workspace, p.get("target", "README.md")
            )
            self.planner.on_checkpoint = None
            if p.get("save_checkpoint") and operation != "preview_skill":
                self._require_approval(
                    "save_local_task_checkpoints",
                    {
                        "warning": "Task arguments and outputs will be retained locally; at most 50 checkpoints."
                    },
                )
                identity = uuid.uuid4().hex
                self.planner.on_checkpoint = lambda plan: self.store.checkpoint(
                    identity, "in_progress", plan
                )
            try:
                result = self.planner.execute(
                    skill.title,
                    prepared_steps=steps,
                    plan_only=operation == "preview_skill",
                ).to_dict()
                if self.planner.on_checkpoint is not None:
                    self.store.checkpoint(
                        identity, "finished" if result["success"] else "stopped", result
                    )
                return result
            finally:
                self.planner.on_checkpoint = None
        if operation == "verify_goal":
            if self.control.engine.workspace is None:
                raise ValueError("Select a workspace first")
            assertions = [GoalAssertion(**row) for row in p["assertions"]]
            return verify_goal(assertions, self.control.engine.workspace, [])
        if operation == "rollback_transaction":
            return self.perform(
                "tool",
                {
                    "name": "rollback_transaction",
                    "arguments": {"transaction_id": p["transaction_id"]},
                },
            )
        if operation in {"repair_test", "repair_generate", "repair_shadow"}:
            if self.control.engine.workspace is None:
                raise ValueError("Select a workspace before reviewing a repair")
            name = p.get("tool") or (self.incident.tool if self.incident else None)
            if operation == "repair_shadow":
                return self.repairs.shadow_evaluate(
                    name, p["source"], p["replay_inputs"]
                )
            cases = [
                ContractCase(row["input"], row["expected"]) for row in p["contracts"]
            ]
            if operation == "repair_generate":
                if self.incident is None:
                    raise ValueError("Capture a custom tool failure first")
                self._require_approval(
                    "send_redacted_repair_context_to_selected_provider",
                    {
                        "fingerprint": self.incident.fingerprint,
                        "contracts": p["contracts"],
                    },
                )
                outcome = RepairLoop(
                    self.repairs,
                    MarkRepairProvider(),
                    "mark-selected-provider",
                    [],
                    knowledge=self.store,
                    governor=self.governor,
                    circuit_breaker=self.breaker,
                ).run(self.incident, cases, self.control.cancelled)
                self.candidate = outcome.candidate
                self.cases = cases if self.candidate else None
                return {
                    "reason": outcome.reason,
                    "attempts": outcome.attempts,
                    "source": self.candidate.source if self.candidate else None,
                    "activated": False,
                }
            self.candidate = self.repairs.test(name, p["source"], cases)
            self.cases = cases
            return {
                "checks": self.candidate.checks,
                "source": self.candidate.source,
                "activated": False,
            }
        if operation == "repair_activate":
            if self.candidate is None:
                raise ValueError("Test a candidate first")
            self._require_approval(
                operation,
                {
                    "tool": self.candidate.tool,
                    "source": self.candidate.source,
                    "contracts": [
                        {"input": c.arguments, "expected": c.expected}
                        for c in self.cases
                    ],
                },
            )
            version = self.repairs.activate(self.candidate, self.cases)
            if self.incident and self.incident.tool == self.candidate.tool:
                row = self.store.get_fingerprint(self.incident.fingerprint)
                if row:
                    self.store.bind_fingerprint_solution(
                        self.incident.fingerprint,
                        self.candidate.source,
                        json.dumps(
                            [
                                {"input": c.arguments, "expected": c.expected}
                                for c in self.cases
                            ]
                        ),
                    )
            return {"version": version, "inventory": self.repairs.inventory()}
        if operation == "repair_rollback":
            self._require_approval(operation, p)
            return {"rolled_back": self.repairs.rollback(p["tool"])}
        if operation == "breaker_reset":
            self._require_approval(operation, p)
            self.breaker.reset()
            return {"breaker_reset": True}
        if operation == "resume_checkpoint":
            # The payload is optional: with no checkpoint given, the plan this machine
            # was running when it stopped is the one meant. That file is written by the
            # planner on every step and removed when the plan ends.
            checkpoint = p.get("checkpoint") or plan_state.load()
            if not checkpoint:
                raise ValueError(
                    "No saved plan to resume. The file is state/active_plan.json."
                )
            self._require_approval(
                operation,
                {
                    "goal": checkpoint.get("goal", ""),
                    "warning": "Only independently reverified file artifacts are skipped; remaining mutations require separate approval.",
                },
            )
            return self.planner.resume_from_checkpoint(
                checkpoint, approve_resume=True
            ).to_dict()
        if operation == "procedure_propose":
            self._require_approval(operation, p)
            return {"id": self.store.propose(p["title"], p["instructions"])}
        if operation == "procedure_approve":
            self._require_approval(operation, p)
            self.store.review(p["id"], True)
            return {"approved": True}
        if operation == "procedures":
            return self.store.procedures()
        if operation == "run_procedure":
            row = next((r for r in self.store.procedures() if r["id"] == p["id"]), None)
            if row is None or self.control.engine.workspace is None:
                raise ValueError("Select an approved procedure and a workspace")
            skill = compile_procedure_to_skill(
                row, [r["name"] for r in self.control.list_tools()]
            )
            return self.planner.execute(
                skill.title, prepared_steps=skill.plan(self.control.engine.workspace)
            ).to_dict()
        if operation == "forget":
            self._require_approval(
                operation,
                {
                    "warning": "Clear only the custom service's seven local knowledge tables, not MARK's native memory or file backups."
                },
            )
            self.store.forget()
            return {"forgotten": True}
        raise ValueError("Unknown custom operation: " + str(operation))


_singleton = None
_singleton_lock = threading.Lock()


def get_service():
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = CustomService()
        return _singleton
