"""Versioned hot adapters: contract testing, atomic activation and safe rollback."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from custom_jarvis.repair_adapter import AdapterError, AdapterProgram, bounded
from custom_jarvis.repair_judgment import (
    DEFAULT_LIFETIME,
    POLICY_VERSION,
    RepairDecision,
    fingerprint,
    judge,
    validate_arguments,
)

REPAIRABLE_TOOLS = frozenset(
    {
        "read_file",
        "list_dir",
        "find_files",
        "project_snapshot",
        "discover_project_files",
        "inspect_python",
        "inspect_json",
        "verify_file",
        "preview_file_change",
        "git_inspect",
    }
)


@dataclass(frozen=True)
class ContractCase:
    arguments: dict[str, Any]
    expected: dict[str, Any]


@dataclass(frozen=True)
class TestedCandidate:
    tool: str
    source: str
    source_sha256: str
    base_version: str | None
    checks: int
    context_key: str
    contracts_sha256: str
    expires_at: float


def check_candidate(source: str, cases: list[ContractCase]) -> int:
    if not 1 <= len(cases) <= 16:
        raise AdapterError("Provide 1–16 user-reviewed regression contracts")
    program = AdapterProgram(source)
    for index, case in enumerate(cases, 1):
        bounded(case.expected)
        if json.dumps(
            program.run(case.arguments), sort_keys=True, allow_nan=False
        ) != json.dumps(case.expected, sort_keys=True, allow_nan=False):
            raise AdapterError(
                f"Contract {index}: output does not match reviewed expected arguments"
            )
        # Every reviewed valid output must remain stable on a subsequent call.
        if json.dumps(
            program.run(case.expected), sort_keys=True, allow_nan=False
        ) != json.dumps(case.expected, sort_keys=True, allow_nan=False):
            raise AdapterError(
                f"Contract {index}: adapter is not idempotent on expected arguments"
            )
        probe = "_compat_" + uuid.uuid4().hex
        extra = {"preserve": [1, "unrelated", True]}
        augmented_input = dict(case.arguments, **{probe: extra})
        augmented_expected = dict(case.expected, **{probe: extra})
        if json.dumps(
            program.run(augmented_input), sort_keys=True, allow_nan=False
        ) != json.dumps(augmented_expected, sort_keys=True, allow_nan=False):
            raise AdapterError(
                f"Contract {index}: adapter dropped or changed an unrelated field"
            )
    return len(cases) * 3


class HotRepairManager:
    """No core modules are rewritten or reloaded. All active code is interpreted DSL.

    Promotion is only called by the UI's explicit activation button. Pointer writes
    are atomic; in-process locking prevents overlapping activations. Separate app
    processes sharing this directory are not coordinated (single writer only).
    """

    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.pointer = directory / "active.json"
        self.lock = threading.RLock()
        self.context_provider = None
        self.schema_provider = None
        self.preflight = None
        self.events = deque(maxlen=200)
        self._disabled = set()
        self._programs = {}
        self.active = self._load()
        self.scoped_catalog = self._load_catalog()
        self.circuit_breaker = None

    @staticmethod
    def _valid_version(version):
        return (
            isinstance(version, str)
            and len(version) == 32
            and all(c in "0123456789abcdef" for c in version)
        )

    def _load(self):
        try:
            with self.pointer.open(encoding="utf-8") as stream:
                text = stream.read(262145)
            if len(text) > 262144:
                return {}
            state = json.loads(text)
            if not isinstance(state, dict):
                return {}
            return {
                tool: entry
                for tool, entry in state.items()
                if tool in REPAIRABLE_TOOLS
                and isinstance(entry, dict)
                and self._valid_version(entry.get("current"))
                and (
                    entry.get("previous") is None
                    or self._valid_version(entry.get("previous"))
                )
            }
        except (OSError, ValueError, RecursionError):
            return {}

    def _save(self):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.directory,
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                catalog = json.loads(json.dumps(self.scoped_catalog))
                for tool, entry in self.active.items():
                    key = entry.get("judgment", {}).get("context_key")
                    if key:
                        catalog.setdefault(tool, {})[key] = entry
                json.dump(dict(self.active, _scoped_catalog=catalog), stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.pointer)
            self.scoped_catalog = catalog
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def current(self, tool: str) -> str | None:
        with self.lock:
            return self.active.get(tool, {}).get("current")

    def inventory(self) -> dict:
        with self.lock:
            return json.loads(json.dumps(self.active))

    def context_key(self, tool: str) -> str:
        context = self.context_provider(tool) if self.context_provider else {}
        return fingerprint({"policy_version": POLICY_VERSION, "context": context})

    def schema(self, tool: str):
        return self.schema_provider(tool) if self.schema_provider else None

    @staticmethod
    def contracts_hash(cases):
        return fingerprint(
            [
                {"input": fingerprint(c.arguments), "expected": fingerprint(c.expected)}
                for c in cases
            ]
        )

    def decision(self, tool, arguments):
        with self.lock:
            if tool in self._disabled:
                return RepairDecision(
                    "block", "PERSISTENCE_FAILURE_REVIEW_REQUIRED", self.current(tool)
                )
            if tool not in self.active:
                return RepairDecision("no_repair", "NO_ACTIVE_REPAIR")
            return judge(self.active.get(tool), arguments, self.context_key(tool))

    def note(self, tool, decision):
        with self.lock:
            self.events.append({"tool": tool, **decision.to_dict()})

    def recent_decisions(self):
        with self.lock:
            return [dict(event) for event in self.events]

    def review_cases(self, tool, cases, *, expected_context=None):
        if not 1 <= len(cases) <= 16:
            raise AdapterError("Provide 1–16 reviewed contracts")
        context = self.context_key(tool)
        if expected_context is not None and context != expected_context:
            raise AdapterError("Workspace or schema changed since the incident")
        if (
            self.context_provider
            and self.context_provider(tool).get("workspace") is None
        ):
            raise AdapterError("Select a workspace before testing a scoped repair")
        if not any(fingerprint(c.arguments) != fingerprint(c.expected) for c in cases):
            raise AdapterError(
                "No repair needed: contracts contain no changed argument"
            )
        for case in cases:
            bounded(case.arguments)
            validate_arguments(case.expected, self.schema(tool))
            if self.preflight:
                try:
                    self.preflight(tool, case.expected)
                except (TypeError, ValueError, OSError) as exc:
                    raise AdapterError(
                        f"Reviewed output violates workspace safeguards: {exc}"
                    ) from exc
        if self.context_key(tool) != context:
            raise AdapterError("Repair context changed during review")
        return context

    def test(
        self,
        tool: str,
        source: str,
        cases: list[ContractCase],
        *,
        expected_context: str | None = None,
    ) -> TestedCandidate:
        if tool not in REPAIRABLE_TOOLS:
            raise AdapterError("This feature is not eligible for live argument repair")
        context = self.review_cases(tool, cases, expected_context=expected_context)
        base = self.current(tool)
        checks = check_candidate(source, cases)
        if self.context_key(tool) != context:
            raise AdapterError("Repair context changed during testing")
        return TestedCandidate(
            tool,
            source,
            hashlib.sha256(source.encode()).hexdigest(),
            base,
            checks,
            context,
            self.contracts_hash(cases),
            time.time() + DEFAULT_LIFETIME,
        )

    def activate(self, candidate: TestedCandidate, cases: list[ContractCase]) -> str:
        if candidate.tool not in REPAIRABLE_TOOLS:
            raise AdapterError("Unsupported live-repair target")
        if (
            hashlib.sha256(candidate.source.encode()).hexdigest()
            != candidate.source_sha256
        ):
            raise AdapterError("Candidate changed after testing")
        if self.contracts_hash(cases) != candidate.contracts_sha256:
            raise AdapterError("Contracts changed after testing; test again")
        if self.context_key(candidate.tool) != candidate.context_key:
            raise AdapterError("Workspace or tool schema changed after testing")
        if time.time() >= candidate.expires_at:
            raise AdapterError("Candidate review expired; test again")
        check_candidate(candidate.source, cases)
        for case in cases:
            validate_arguments(case.expected, self.schema(candidate.tool))
            if self.preflight:
                try:
                    self.preflight(candidate.tool, case.expected)
                except (TypeError, ValueError, OSError) as exc:
                    raise AdapterError(
                        f"Reviewed output violates workspace safeguards: {exc}"
                    ) from exc
        with self.lock:
            if self.context_key(candidate.tool) != candidate.context_key:
                raise AdapterError("Repair context changed during activation")
            if self.current(candidate.tool) != candidate.base_version:
                raise AdapterError(
                    "Stale candidate: active adapter changed during repair"
                )
            version = uuid.uuid4().hex
            source_path = self.directory / f"{version}.py"
            with source_path.open("w", encoding="utf-8") as stream:
                stream.write(candidate.source)
                stream.flush()
                os.fsync(stream.fileno())
            previous_entry = self.active.get(candidate.tool)
            self.active[candidate.tool] = {
                "current": version,
                "canary_remaining": 5,
                "judgment": {
                    "policy_version": POLICY_VERSION,
                    "context_key": candidate.context_key,
                    "approved_inputs": {
                        fingerprint(c.arguments): fingerprint(c.expected) for c in cases
                    },
                    "contracts_sha256": candidate.contracts_sha256,
                    "expires_at": candidate.expires_at,
                },
                "previous_entry": {
                    k: v
                    for k, v in previous_entry.items()
                    if k not in ("previous_entry", "previous", "previous_sha256")
                }
                if previous_entry
                else None,
                "previous": candidate.base_version,
                "sha256": candidate.source_sha256,
                "previous_sha256": previous_entry.get("sha256")
                if previous_entry
                else None,
            }
            try:
                self._save()
            except OSError:
                if previous_entry is None:
                    self.active.pop(candidate.tool, None)
                else:
                    self.active[candidate.tool] = previous_entry
                source_path.unlink(missing_ok=True)
                raise
            self._programs[version] = AdapterProgram(candidate.source)
            while len(self._programs) > 8:
                self._programs.pop(next(iter(self._programs)))
            self._disabled.discard(candidate.tool)
            return version

    def rollback(self, tool: str, *, expected_version: str | None = None) -> bool:
        with self.lock:
            old = self.active.get(tool)
            if old is None or (
                expected_version is not None and old["current"] != expected_version
            ):
                return False
            previous = old.get("previous")
            warning = None
            if previous:
                try:
                    source = (self.directory / f"{previous}.py").read_text(
                        encoding="utf-8"
                    )
                    if hashlib.sha256(source.encode()).hexdigest() != old.get(
                        "previous_sha256"
                    ):
                        raise AdapterError(
                            "Previous version failed its integrity check"
                        )
                    AdapterProgram(source)
                    restored = old.get("previous_entry") or {
                        "current": previous,
                        "sha256": old["previous_sha256"],
                    }
                    if not isinstance(restored, dict):
                        raise AdapterError("Previous version metadata is malformed")
                    if (
                        restored.get("current") != previous
                        or restored.get("sha256") != old["previous_sha256"]
                    ):
                        raise AdapterError("Previous version metadata mismatch")
                    self.active[tool] = dict(restored, previous=None)
                except (OSError, AdapterError, UnicodeError):
                    self.active.pop(tool, None)
                    warning = "No trustworthy previous version; adapter disabled without running a tool"
            else:
                self.active.pop(tool, None)
            catalog_before = json.loads(json.dumps(self.scoped_catalog))
            old_key = old.get("judgment", {}).get("context_key")
            self.scoped_catalog.get(tool, {}).pop(old_key, None)
            try:
                self._save()
            except OSError:
                self.scoped_catalog = catalog_before
                self.active[tool] = old
                self._disabled.add(tool)
                raise
            self._disabled.discard(tool)
            if self.circuit_breaker:
                self.circuit_breaker.record_rollback(
                    tool,
                    old.get("judgment", {}).get("context_key", ""),
                    old["current"],
                    self.current(tool),
                )
            if warning:
                raise AdapterError(warning)
            return True

    def record_outcome(self, tool, version, success, *, environmental=False):
        """Success is execution evidence, not a proof of intent. Ambiguity quarantines.

        Only structured external/policy failures keep an adapter eligible.
        """
        with self.lock:
            old = self.active.get(tool)
            if old is None or old["current"] != version:
                return
            updated = dict(old)
            key = (
                "execution_successes"
                if success
                else "external_failures"
                if environmental
                else "ambiguous_failures"
            )
            count = updated.get(key, 0)
            updated[key] = min(
                (count if type(count) is int and count >= 0 else 0) + 1, 1000000
            )
            if success and updated.get("canary_remaining", 0) > 0:
                updated["canary_remaining"] -= 1
                if updated["canary_remaining"] == 0:
                    updated["canary_graduated"] = True
            if not success and not environmental:
                updated["quarantined"] = True
                updated["failed_during_canary"] = bool(
                    updated.get("canary_remaining", 0) > 0
                )
            self.active[tool] = updated
            try:
                self._save()
            except OSError:
                self._disabled.add(tool)
                raise

    def apply(
        self, tool: str, arguments: dict[str, Any]
    ) -> tuple[dict[str, Any], str | None]:
        with self.lock:
            decision = self.decision(tool, arguments)
            self.note(tool, decision)
            if decision.action == "block":
                raise AdapterError(decision.reason)
            if decision.action != "apply":
                return arguments, None
            entry = self.active[tool]
            version = entry["current"]
            try:
                # Verify disk integrity on each use, including after app restarts.
                source = (self.directory / f"{version}.py").read_text(encoding="utf-8")
                if hashlib.sha256(source.encode()).hexdigest() != entry.get("sha256"):
                    raise AdapterError("Active adapter source changed on disk")
                program = self._programs.get(version)
                if program is None:
                    program = AdapterProgram(source)
                    self._programs[version] = program
                    while len(self._programs) > 8:
                        self._programs.pop(next(iter(self._programs)))
                output = program.run(arguments)
                if (
                    fingerprint(output)
                    != entry["judgment"]["approved_inputs"][fingerprint(arguments)]
                ):
                    raise AdapterError(
                        "Runtime output differs from the reviewed contract"
                    )
                validate_arguments(output, self.schema(tool))
                return output, version
            except (OSError, AdapterError, ValueError, TypeError) as exc:
                try:
                    self.rollback(tool, expected_version=version)
                except (AdapterError, OSError) as rollback_error:
                    raise AdapterError(
                        f"Repair failed; no tool ran. Rollback warning: {rollback_error}; original: {exc}"
                    ) from exc
                raise AdapterError(
                    f"Active repair failed and was rolled back; no tool ran: {exc}"
                ) from exc

    def _load_catalog(self):
        try:
            with self.pointer.open(encoding="utf-8") as stream:
                data = json.loads(stream.read(2097153))
            if not isinstance(data, dict):
                return {}
            catalog = data.get("_scoped_catalog", {})
            if not isinstance(catalog, dict):
                return {}
            return {
                tool: {
                    key: entry
                    for key, entry in scopes.items()
                    if isinstance(entry, dict)
                    and self._valid_version(entry.get("current"))
                }
                for tool, scopes in catalog.items()
                if tool in REPAIRABLE_TOOLS and isinstance(scopes, dict)
            }
        except (OSError, ValueError, RecursionError):
            return {}

    def sync_workspace_scope(self, tool):
        with self.lock:
            if tool in self._disabled:
                return
            key = self.context_key(tool)
            entry = self.scoped_catalog.get(tool, {}).get(key)
            if (
                not entry
                or entry.get("judgment", {}).get("expires_at", 0) <= time.time()
            ):
                return
            source = (self.directory / (entry["current"] + ".py")).read_text(
                encoding="utf-8"
            )
            if hashlib.sha256(source.encode()).hexdigest() != entry.get("sha256"):
                raise AdapterError("Scoped catalog source failed integrity check")
            AdapterProgram(source)
            self.active[tool] = json.loads(json.dumps(entry))

    def shadow_evaluate(self, tool, candidate_source, replay_inputs):
        candidate = AdapterProgram(candidate_source)
        cases = []
        for arguments in replay_inputs[:32]:
            started = time.perf_counter_ns()
            row = {
                "schema_valid": False,
                "workspace_safe": False,
                "changed_vs_original": False,
                "changed_vs_current_adapter": False,
            }
            try:
                current = arguments
                with self.lock:
                    decision = self.decision(tool, arguments)
                    if decision.action == "apply":
                        entry = self.active[tool]
                        source = (
                            self.directory / (entry["current"] + ".py")
                        ).read_text(encoding="utf-8")
                        if hashlib.sha256(source.encode()).hexdigest() != entry.get(
                            "sha256"
                        ):
                            raise AdapterError("Current source integrity mismatch")
                        current = AdapterProgram(source).run(arguments)
                output = candidate.run(arguments)
                row["changed_vs_original"] = fingerprint(output) != fingerprint(
                    arguments
                )
                row["changed_vs_current_adapter"] = fingerprint(output) != fingerprint(
                    current
                )
                validate_arguments(output, self.schema(tool))
                row["schema_valid"] = True
                if self.preflight:
                    self.preflight(tool, output)
                row["workspace_safe"] = True
            except (AdapterError, ValueError, TypeError, OSError) as exc:
                row["error"] = str(exc)
            row["latency_us"] = (time.perf_counter_ns() - started) / 1000
            cases.append(row)
        return {
            "tool": tool,
            "total_cases": len(cases),
            "schema_valid_count": sum(c["schema_valid"] for c in cases),
            "workspace_safe_count": sum(c["workspace_safe"] for c in cases),
            "changed_vs_original_count": sum(c["changed_vs_original"] for c in cases),
            "changed_vs_current_adapter_count": sum(
                c["changed_vs_current_adapter"] for c in cases
            ),
            "mean_latency_us": sum(c["latency_us"] for c in cases) / max(1, len(cases)),
            "cases": cases,
            "promoted": False,
        }
