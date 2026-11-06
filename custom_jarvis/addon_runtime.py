"""Optional execution evidence layer; retains the existing approval boundary."""

from __future__ import annotations

import hashlib
import inspect
import logging
import marshal
from pathlib import Path
from typing import Any

from custom_jarvis.evidence import (
    MAX_FILE_BYTES,
    BackupManager,
    bounded_text,
    file_digest,
)
from custom_jarvis.knowledge import KnowledgeStore
from custom_jarvis.preflight import StateDriftGuard
from custom_jarvis.repair_adapter import AdapterError
from custom_jarvis.repair_judgment import RepairDecision, fingerprint
from custom_jarvis.runtime import ControlledRegistry
from custom_jarvis.tools import ToolResult

logger = logging.getLogger(__name__)
INSPECTION_TOOLS = frozenset(
    {
        "project_snapshot",
        "discover_project_files",
        "git_inspect",
        "inspect_python",
        "inspect_json",
        "verify_file",
        "preview_file_change",
        "inspect_accessibility",
        "vision_capability_status",
        # The two workspace readers added with the meta-cognitive skills.
        # They read file contents, so they are read-only; they take a path,
        # so they belong in the confinement table below.
        "search_text",
        "measure_code",
        "decide",
    }
)
PATH_ARGUMENTS = {
    name: "path"
    for name in (
        "read_file",
        "write_file",
        "list_dir",
        "project_snapshot",
        "git_inspect",
        "inspect_python",
        "inspect_json",
        "verify_file",
        "preview_file_change",
        "search_text",
        "measure_code",
    )
}
PATH_ARGUMENTS["find_files"] = "search_path"
PATH_ARGUMENTS["discover_project_files"] = "search_path"
PATH_ARGUMENTS["analyze_screenshot"] = "path"
PATH_ARGUMENTS["execute_command"] = "working_dir"
PATH_ARGUMENTS["run_shell"] = "working_dir"


class EvidenceEngine:
    def __init__(self, registry, store: KnowledgeStore, backups: BackupManager) -> None:
        self.registry = registry
        self.store = store
        self.backups = backups
        self.workspace: Path | None = None
        self.learning = True
        self.backups_enabled = True
        self.drift_guard = StateDriftGuard()
        self.transaction_id = None
        self.cancel_event = None

    def list_tools(self, *args, **kwargs):
        return self.registry.list_tools(*args, **kwargs)

    def canonical_name(self, name: str) -> str:
        definition = self.registry.get(name)
        handler_name = (
            getattr(definition.handler, "__name__", name) if definition else name
        )
        return (
            handler_name
            if handler_name in PATH_ARGUMENTS or handler_name == "write_file"
            else name
        )

    def prepare_args(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        name = self.canonical_name(name)
        args = dict(args)
        if self.workspace is None:
            if name in PATH_ARGUMENTS:
                raise ValueError(
                    "Select a workspace before using project inspection tools"
                )
            return args
        key = PATH_ARGUMENTS.get(name)
        if key:
            raw = Path(
                (args.get(key) or ".") if key == "working_dir" else args.get(key, ".")
            )
            target = (
                (self.workspace / raw).resolve()
                if not raw.is_absolute()
                else raw.resolve()
            )
            if not target.is_relative_to(self.workspace):
                raise ValueError(
                    "Path is outside the selected workspace (including symlink targets)"
                )
            args[key] = str(target)
        if name in ("find_files", "discover_project_files"):
            pattern = Path(args.get("pattern", "*"))
            if pattern.is_absolute() or ".." in pattern.parts:
                raise ValueError("Search patterns must not escape the workspace")
        if name == "take_screenshot":
            directory = Path(
                args.get("save_dir") or self.workspace / ".jarvis" / "screenshots"
            )
            directory = (
                (self.workspace / directory).resolve()
                if not directory.is_absolute()
                else directory.resolve()
            )
            if not directory.is_relative_to(self.workspace):
                raise ValueError("Screenshot directory must be inside the workspace")
            args["save_dir"] = str(directory)
            if args.get("filename") and Path(args["filename"]).name != args["filename"]:
                raise ValueError("Screenshot filename must not contain a directory")
        return args

    def execute(self, name: str, **args: Any) -> ToolResult:
        requested_name = name
        name = self.canonical_name(name)
        backup_id = None
        previous = ""
        # This method is reached only after ControlledRegistry's approval checks.
        if name == "write_file" and not self.drift_guard.unchanged(Path(args["path"])):
            return ToolResult(
                False,
                error="File changed after observation; write blocked",
                metadata={
                    "error_code": "STATE_DRIFT_DETECTED",
                    "requires_user_action": True,
                },
            )
        observed_digest = None
        observed_path = None
        if name in {"read_file", "preview_file_change"} and isinstance(
            args.get("path"), str
        ):
            observed_path = Path(args["path"])
            try:
                if (
                    observed_path.is_file()
                    and observed_path.stat().st_size <= MAX_FILE_BYTES
                ):
                    observed_digest = file_digest(observed_path)
            except OSError:
                observed_digest = None
        if name == "write_file" and self.workspace is not None and self.backups_enabled:
            try:
                backup_id, previous = self.backups.prepare(Path(args["path"]))
                if self.transaction_id is None:
                    self.transaction_id = self.backups.begin_transaction()
                self.backups.record_in_transaction(self.transaction_id, backup_id)
            except (OSError, UnicodeError, ValueError) as exc:
                return ToolResult(
                    False,
                    error=f"Pre-write backup failed; write blocked: {exc}",
                    metadata={"requires_user_action": True},
                )
        if name == "rollback_transaction":
            try:
                if self.workspace is None:
                    raise ValueError(
                        "Select a workspace before rolling back a transaction"
                    )
                data = self.backups.rollback_transaction(
                    args["transaction_id"], self.workspace
                )
                return ToolResult(
                    not data["conflicts"],
                    output=str(data),
                    data=data,
                    metadata={
                        "verification": "verified"
                        if not data["conflicts"]
                        else "failed",
                        "requires_user_action": bool(data["conflicts"]),
                    },
                )
            except (OSError, ValueError, KeyError) as exc:
                return ToolResult(
                    False, error=str(exc), metadata={"requires_user_action": True}
                )
        if name == "restore_file_backup":
            try:
                if self.workspace is None:
                    raise ValueError("Select a workspace before restoring a backup")
                data = self.backups.restore(args["backup_id"], self.workspace)
                result = ToolResult(
                    True,
                    output=f"Restored: {data['path']}",
                    data=data,
                    metadata={
                        "verification": "verified",
                        "evidence": "Conflict-checked backup restoration",
                    },
                )
            except (OSError, ValueError, KeyError) as exc:
                result = ToolResult(
                    False, error=str(exc), metadata={"requires_user_action": True}
                )
        else:
            definition = self.registry.get(requested_name)
            if (
                definition
                and name in {"execute_command", "run_shell"}
                and "cancel_event" in inspect.signature(definition.handler).parameters
            ):
                args["cancel_event"] = self.cancel_event
            result = self.registry.execute(requested_name, **args)
        if result.success and observed_digest and observed_path:
            if file_digest(observed_path) != observed_digest:
                return ToolResult(
                    False,
                    error="File changed during observation",
                    metadata={
                        "error_code": "STATE_DRIFT_DETECTED",
                        "requires_user_action": True,
                    },
                )
            self.drift_guard.observe_file(observed_path, observed_digest)
        if (
            result.success
            and name == "get_active_window"
            and isinstance(result.data, dict)
        ):
            self.drift_guard.last_observed_window_title = result.data.get("title")
        result.metadata.setdefault(
            "verification", "executed_unverified" if result.success else "failed"
        )
        if result.success and name == "write_file":
            try:
                target = Path(args["path"])
                if backup_id:
                    self.backups.finish(backup_id, target)
                    result.metadata["backup_id"] = backup_id
                # Verify text exactly; append verification requires known prior content.
                appending = args.get("append") or args.get("mode") == "a"
                if appending and backup_id is None:
                    result.metadata["verification"] = "executed_unverified"
                else:
                    expected = (previous if appending else "") + args["content"]
                    actual = bounded_text(target)
                    normalized = expected.replace("\r\n", "\n").replace("\r", "\n")
                    if actual != normalized:
                        raise ValueError("Written file does not match expected text")
                    result.metadata.update(
                        verification="verified",
                        evidence="File read-back matches requested text",
                    )
            except (OSError, UnicodeError, ValueError, KeyError) as exc:
                result.success = False
                result.error = f"Write executed but verification failed: {exc}"
                result.metadata.update(verification="failed", requires_user_action=True)
        elif result.success and name == "take_screenshot":
            try:
                from PIL import Image

                with Image.open(result.data["path"]) as image:
                    image.verify()
                if result.data.get("is_fallback"):
                    raise ValueError("Placeholder is not live screen evidence")
                result.metadata.update(
                    verification="verified",
                    evidence="Captured image decodes; contents not interpreted",
                )
            except (OSError, ValueError, KeyError, TypeError) as exc:
                result.success = False
                result.error = f"Capture verification failed: {exc}"
                result.metadata.update(verification="failed", requires_user_action=True)
        if not result.success and name not in (
            ControlledRegistry.READ_ONLY | INSPECTION_TOOLS
        ):
            result.metadata.update(
                requires_user_action=True, retry_safety="manual_review"
            )
            result.error = (
                (result.error or "Action failed")
                + " Review current state before retrying; partial side effects may have occurred."
            )
        if result.success and isinstance(args.get("path"), str):
            try:
                target = Path(args["path"])
                if target.is_file() and target.stat().st_size <= MAX_FILE_BYTES:
                    result.metadata["artifact_sha256"] = file_digest(target)
                    if name == "write_file":
                        self.drift_guard.observe_file(
                            target, result.metadata["artifact_sha256"]
                        )
            except OSError:
                pass
        if self.learning:
            try:
                self.store.observe(
                    name,
                    result.success,
                    result.metadata["verification"] == "verified",
                    result.execution_time,
                )
            except Exception:
                logger.exception("Could not record non-sensitive capability counters")
        return result


class AddonRegistry(ControlledRegistry):
    READ_ONLY = ControlledRegistry.READ_ONLY | INSPECTION_TOOLS

    def __init__(
        self, registry, approve, store: KnowledgeStore, backups: BackupManager
    ):
        self.hot_repairs = None
        self.on_failure = None
        self.engine = EvidenceEngine(registry, store, backups)
        super().__init__(self.engine, approve)
        self.engine.cancel_event = self.cancelled

    def select_workspace(self, workspace: str | Path) -> None:
        path = Path(workspace).resolve()
        if not path.is_dir():
            raise ValueError("Workspace must be an existing directory")
        self.engine.workspace = path
        self.engine.drift_guard.reset()
        if self.hot_repairs:
            for tool in list(self.hot_repairs.scoped_catalog):
                self.hot_repairs.sync_workspace_scope(tool)

    def list_tools(self, *args, **kwargs):
        tools = super().list_tools(*args, **kwargs)
        if self.engine.learning:
            try:
                observations = {
                    row["tool"]: row for row in self.engine.store.statistics()
                }
                tools = [
                    dict(tool, observed_reliability=observations[tool["name"]])
                    if tool["name"] in observations
                    else tool
                    for tool in tools
                ]
            except Exception:
                logger.exception("Could not read capability observations")
        tools.append(
            {
                "name": "restore_file_backup",
                "category": "recovery",
                "description": "Restore a backed-up write only if the current file has not changed. Requires approval.",
                "parameters": {
                    "type": "object",
                    "properties": {"backup_id": {"type": "string"}},
                    "required": ["backup_id"],
                },
            }
        )
        tools.append(
            {
                "name": "rollback_transaction",
                "category": "recovery",
                "description": "Conflict-checked LIFO rollback of a file transaction; requires approval",
                "parameters": {
                    "type": "object",
                    "properties": {"transaction_id": {"type": "string"}},
                    "required": ["transaction_id"],
                },
            }
        )
        return tools

    def begin_plan(self):
        self.engine.drift_guard.reset()
        self.engine.transaction_id = self.engine.backups.begin_transaction()
        return self.engine.transaction_id

    @property
    def hot_repairs(self):
        return self._hot_repairs

    @hot_repairs.setter
    def hot_repairs(self, manager):
        self._hot_repairs = manager
        if manager is not None:
            manager.context_provider = self.repair_context
            manager.schema_provider = self.repair_schema
            manager.preflight = self.engine.prepare_args

    def repair_schema(self, name):
        definition = self.engine.registry.get(name)
        if definition is None:
            raise AdapterError("Repair target is not registered")
        return definition.parameters

    def repair_context(self, name):
        root = self.engine.workspace
        definition = self.engine.registry.get(name)
        code = (
            getattr(inspect.unwrap(definition.handler), "__code__", None)
            if definition
            else None
        )
        return {
            "workspace": fingerprint(str(root.resolve())) if root is not None else None,
            "schema": fingerprint(self.repair_schema(name)),
            "implementation": hashlib.sha256(marshal.dumps(code)).hexdigest()
            if code
            else None,
        }

    def _report_failure(self, name, arguments, result):
        if (
            self.hot_repairs
            and name in self.hot_repairs.inventory()
            and "repair_judgment" not in result.metadata
        ):
            try:
                result.metadata["repair_judgment"] = self.hot_repairs.decision(
                    name, arguments
                ).to_dict()
            except (AdapterError, OSError, TypeError):
                result.metadata["repair_judgment"] = RepairDecision(
                    "block", "CONTEXT_UNAVAILABLE"
                ).to_dict()
        if not result.success and self.on_failure:
            if self.hot_repairs:
                from custom_jarvis.hot_repair import REPAIRABLE_TOOLS

                if name in REPAIRABLE_TOOLS:
                    try:
                        result.metadata["repair_context_key"] = (
                            self.hot_repairs.context_key(name)
                        )
                    except (AdapterError, OSError, TypeError):
                        logger.warning(
                            "Repair context unavailable; preserving original failure"
                        )
            try:
                from custom_jarvis.failure_memory import (
                    compute_incident_fingerprint,
                    normalize_error_signature,
                )

                if self.engine.learning:
                    key = compute_incident_fingerprint(
                        name,
                        result.metadata.get("error_code", ""),
                        result.error or "",
                        result.metadata.get("repair_context_key", ""),
                    )
                    result.metadata["known_solution"] = (
                        self.engine.store.record_fingerprint(
                            key,
                            name,
                            result.metadata.get("repair_context_key", ""),
                            result.metadata.get("error_code", ""),
                            normalize_error_signature(result.error or ""),
                        )
                    )
                self.on_failure(name, arguments, result)
            except Exception:
                logger.exception("Failure capture hook failed")
        return result

    def _rollback_failed_version(self, name, version, result):
        try:
            result.metadata["adapter_rolled_back"] = self.hot_repairs.rollback(
                name, expected_version=version
            )
        except (AdapterError, OSError) as exc:
            result.metadata["rollback_warning"] = str(exc)
            result.metadata["requires_user_action"] = True
        return result

    def execute(self, name: str, **kwargs: Any) -> ToolResult:
        original = dict(kwargs)
        version = None
        # Cancellation/preview are not evidence against an adapter. Do not even
        # evaluate source or probe a path when the operation is already blocked.
        if self.cancelled.is_set() or self.preview:
            return self._report_failure(name, original, super().execute(name, **kwargs))
        decision = RepairDecision("no_repair", "NO_ACTIVE_REPAIR")
        try:
            if self.hot_repairs is not None:
                kwargs, version = self.hot_repairs.apply(name, kwargs)
                decision = (
                    RepairDecision("apply", "EXACT_REVIEWED_CONTRACT", version)
                    if version
                    else self.hot_repairs.decision(name, original)
                )
                key = PATH_ARGUMENTS.get(self.engine.canonical_name(name))
                if version and key and original.get(key) != kwargs.get(key):
                    # A real filename may contain whitespace. Never silently
                    # redirect an existing original target to a different one.
                    try:
                        prepared = self.engine.prepare_args(name, original)
                        exists = Path(prepared[key]).exists()
                    except TypeError:
                        exists = False  # A reviewed type correction may be valid.
                    except (ValueError, OSError) as exc:
                        result = self.blocked(
                            f"Original path cannot be safely inspected: {exc}",
                            "REPAIR_PRECONDITION_UNCERTAIN",
                        )
                        result.metadata["repair_judgment"] = RepairDecision(
                            "block", "ORIGINAL_PATH_UNCERTAIN", version
                        ).to_dict()
                        return self._report_failure(name, original, result)
                    if exists:
                        kwargs, version = original, None
                        decision = RepairDecision(
                            "abstain", "ORIGINAL_PATH_EXISTS", decision.version
                        )
                        self.hot_repairs.note(name, decision)
        except (AdapterError, OSError) as exc:
            result = self.blocked(str(exc), "ADAPTER_FAILED")
            result.metadata["repair_judgment"] = RepairDecision(
                "block", "ADAPTER_RUNTIME_FAULT"
            ).to_dict()
            return self._report_failure(name, original, result)
        try:
            args = self.engine.prepare_args(name, kwargs)
        except (TypeError, ValueError, OSError) as exc:
            result = self.blocked(str(exc), "WORKSPACE_BOUNDARY")
            result.metadata["repair_judgment"] = decision.to_dict()
            if version:
                self._rollback_failed_version(name, version, result)
            return self._report_failure(name, original, result)
        if version and self.hot_repairs.decision(name, original).action != "apply":
            result = self.blocked(
                "Repair context changed before dispatch; no tool ran",
                "REPAIR_CONTEXT_CHANGED",
            )
            result.metadata["repair_judgment"] = RepairDecision(
                "block", "CONTEXT_CHANGED_BEFORE_DISPATCH", version
            ).to_dict()
            return self._report_failure(name, original, result)
        result = super().execute(name, **args)
        result.metadata["repair_judgment"] = decision.to_dict()
        if version:
            result.metadata["adapter_version"] = version
            external = (
                result.metadata.get("error_code")
                in {
                    "DENIED",
                    "CANCELLED",
                    "PREVIEW",
                    "PROVIDER_UNAVAILABLE",
                    "DEPENDENCY_MISSING",
                    "PERMISSION_DENIED",
                    "RATE_LIMITED",
                }
                or result.metadata.get("failure_kind") == "environment"
            )
            try:
                self.hot_repairs.record_outcome(
                    name, version, result.success, environmental=external
                )
            except OSError as exc:
                result.metadata.update(
                    repair_storage_error=str(exc), requires_user_action=True
                )
            if not result.success:
                result.metadata.update(
                    requires_user_action=True,
                    adapter_quarantined=not external,
                    repair_failure_cause="external" if external else "ambiguous",
                )
                result.error = (
                    (result.error or "Feature failed")
                    + (
                        " External/policy failure; adapter retained."
                        if external
                        else " Cause uncertain; adapter quarantined pending review, not blamed or rolled back."
                    )
                    + " No automatic replay was attempted."
                )
        return self._report_failure(name, original, result)
