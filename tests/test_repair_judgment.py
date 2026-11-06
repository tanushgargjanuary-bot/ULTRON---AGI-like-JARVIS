"""Judgment gates, real file outcomes, fault injection and generated lifecycle tests."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

try:
    from hypothesis import settings
    from hypothesis.stateful import RuleBasedStateMachine, invariant, rule
except ImportError:

    def settings(**kwargs):
        return None

    def rule(*args, **kwargs):
        return lambda function: function

    def invariant(*args, **kwargs):
        return lambda function: function

    @unittest.skip("hypothesis not installed")
    class _MissingLifecycle(unittest.TestCase):
        def runTest(self):
            pass

    class RuleBasedStateMachine:
        TestCase = _MissingLifecycle


from custom_jarvis.addon_runtime import AddonRegistry
from custom_jarvis.evidence import BackupManager
from custom_jarvis.hot_repair import ContractCase, HotRepairManager
from custom_jarvis.knowledge import KnowledgeStore
from custom_jarvis.repair_adapter import AdapterError, AdapterProgram
from custom_jarvis.repair_judgment import fingerprint, judge
from custom_jarvis.self_healing import FailureIncident, RepairLoop
from custom_jarvis.tools import ToolRegistry, ToolResult, read_file

STRIP = 'def adapt(args):\n    return dict(args, path=args["path"].strip())\n'
INPUT = {"path": " note.txt"}
EXPECTED = {"path": "note.txt"}
CASES = [ContractCase(INPUT, EXPECTED), ContractCase(EXPECTED, EXPECTED)]


class NoProvider:
    def list_models(self):
        raise AssertionError("No discovery request should occur")

    def propose(self, *args):
        raise AssertionError("No completion request should occur")


class JudgmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.project = self.base / "project"
        self.other = self.base / "other"
        self.project.mkdir()
        self.other.mkdir()
        (self.project / "note.txt").write_text("intended document", encoding="utf-8")
        self.raw = ToolRegistry()
        self.raw.register(name="read_file")(read_file)
        self.registry = AddonRegistry(
            self.raw,
            lambda *args: True,
            KnowledgeStore(self.base / "knowledge.sqlite3"),
            BackupManager(self.base / "backups"),
        )
        self.registry.select_workspace(self.project)
        self.manager = HotRepairManager(self.base / "repairs")
        self.registry.hot_repairs = self.manager

    def tearDown(self):
        self.temp.cleanup()

    def activate(self, cases=CASES):
        return self.manager.activate(
            self.manager.test("read_file", STRIP, cases), cases
        )

    def test_exact_contract_reads_intended_document(self):
        version = self.activate()
        result = self.registry.execute("read_file", **INPUT)
        self.assertTrue(result.success)
        self.assertIn("intended document", result.output)
        self.assertEqual(result.metadata["adapter_version"], version)
        self.assertEqual(
            self.manager.inventory()["read_file"]["execution_successes"], 1
        )

    def test_unreviewed_input_never_runs_adapter(self):
        self.activate()
        with patch.object(
            AdapterProgram, "run", side_effect=AssertionError("must abstain")
        ):
            output, version = self.manager.apply("read_file", {"path": " other.txt"})
        self.assertEqual(output, {"path": " other.txt"})
        self.assertIsNone(version)
        self.assertEqual(
            self.manager.recent_decisions()[-1]["reason"], "UNREVIEWED_INPUT"
        )

    def test_extra_arguments_need_a_new_review(self):
        self.activate()
        self.assertEqual(
            self.manager.decision("read_file", dict(INPUT, encoding="utf-8")).reason,
            "UNREVIEWED_INPUT",
        )

    def test_unchanged_contract_abstains(self):
        self.activate()
        self.assertEqual(
            self.manager.decision("read_file", EXPECTED).reason, "REVIEWED_NO_CHANGE"
        )

    def test_no_change_candidate_is_rejected(self):
        with self.assertRaisesRegex(AdapterError, "No repair needed"):
            self.manager.test(
                "read_file",
                "def adapt(args): return dict(args)",
                [ContractCase(EXPECTED, EXPECTED)],
            )

    def test_cross_workspace_abstains(self):
        self.activate()
        self.registry.select_workspace(self.other)
        output, version = self.manager.apply("read_file", INPUT)
        self.assertEqual(output, INPUT)
        self.assertIsNone(version)
        self.assertEqual(
            self.manager.decision("read_file", INPUT).reason,
            "WORKSPACE_SCHEMA_OR_IMPLEMENTATION_CHANGED",
        )

    def test_returning_to_original_workspace_restores_eligibility(self):
        version = self.activate()
        self.registry.select_workspace(self.other)
        self.registry.select_workspace(self.project)
        self.assertEqual(self.manager.apply("read_file", INPUT), (EXPECTED, version))

    def test_schema_change_invalidates_scope(self):
        self.activate()
        self.raw.get("read_file").parameters["description"] = "revised tool contract"
        self.assertEqual(self.manager.decision("read_file", INPUT).action, "abstain")

    def test_handler_change_invalidates_scope(self):
        self.activate()
        self.raw.get("read_file").handler = lambda **kwargs: ToolResult(
            True, output="different"
        )
        self.assertEqual(self.manager.decision("read_file", INPUT).action, "abstain")

    def test_workspace_change_rejects_activation(self):
        tested = self.manager.test("read_file", STRIP, CASES)
        self.registry.select_workspace(self.other)
        with self.assertRaisesRegex(AdapterError, "changed"):
            self.manager.activate(tested, CASES)

    def test_schema_change_rejects_activation(self):
        tested = self.manager.test("read_file", STRIP, CASES)
        self.raw.get("read_file").parameters["description"] = "changed"
        with self.assertRaisesRegex(AdapterError, "changed"):
            self.manager.activate(tested, CASES)

    def test_changed_contracts_require_retesting(self):
        tested = self.manager.test("read_file", STRIP, CASES)
        with self.assertRaisesRegex(AdapterError, "Contracts changed"):
            self.manager.activate(tested, CASES[:1])

    def test_stale_incident_refuses_local_test(self):
        context = self.manager.context_key("read_file")
        self.registry.select_workspace(self.other)
        with self.assertRaisesRegex(AdapterError, "changed"):
            self.manager.test("read_file", STRIP, CASES, expected_context=context)

    def test_no_workspace_refuses_review(self):
        self.registry.engine.workspace = None
        with self.assertRaisesRegex(AdapterError, "workspace"):
            self.manager.test("read_file", STRIP, CASES)

    def test_schema_invalid_expected_arguments_rejected(self):
        source = "def adapt(args): return dict(args, path=123)"
        with self.assertRaisesRegex(AdapterError, "schema"):
            self.manager.test("read_file", source, [ContractCase(INPUT, {"path": 123})])

    def test_unknown_output_arguments_rejected(self):
        source = 'def adapt(args): return dict(args, unknown="x")'
        with self.assertRaisesRegex(AdapterError, "undeclared"):
            self.manager.test(
                "read_file",
                source,
                [ContractCase(EXPECTED, dict(EXPECTED, unknown="x"))],
            )

    def test_bool_is_not_schema_integer(self):
        schema = self.raw.get("read_file").parameters
        schema["properties"]["count"] = {"type": "integer"}
        with self.assertRaisesRegex(AdapterError, "schema"):
            self.manager.test(
                "read_file",
                "def adapt(args): return dict(args, count=True)",
                [ContractCase(EXPECTED, dict(EXPECTED, count=True))],
            )

    def test_existing_literal_filename_is_not_redirected(self):
        self.activate()
        (self.project / INPUT["path"]).write_text(
            "literal spaced name", encoding="utf-8"
        )
        result = self.registry.execute("read_file", **INPUT)
        self.assertTrue(result.success)
        self.assertIn("literal spaced name", result.output)
        self.assertEqual(
            result.metadata["repair_judgment"]["reason"], "ORIGINAL_PATH_EXISTS"
        )
        self.assertNotIn("adapter_version", result.metadata)

    def test_uncertain_path_precondition_blocks_without_blame(self):
        version = self.activate()
        with (
            patch.object(
                self.registry.engine,
                "prepare_args",
                side_effect=OSError("stat unavailable"),
            ),
            patch.object(self.raw, "execute") as raw,
        ):
            result = self.registry.execute("read_file", **INPUT)
            raw.assert_not_called()
        self.assertEqual(result.metadata["error_code"], "REPAIR_PRECONDITION_UNCERTAIN")
        self.assertEqual(self.manager.current("read_file"), version)

    def test_expired_scope_abstains(self):
        self.activate()
        expiry = self.manager.inventory()["read_file"]["judgment"]["expires_at"]
        with patch("custom_jarvis.repair_judgment.time.time", return_value=expiry + 1):
            self.assertEqual(
                self.manager.decision("read_file", INPUT).reason, "REVIEW_EXPIRED"
            )

    def test_expired_candidate_cannot_activate(self):
        tested = self.manager.test("read_file", STRIP, CASES)
        with self.assertRaisesRegex(AdapterError, "expired"):
            self.manager.activate(replace(tested, expires_at=0), CASES)

    def test_legacy_adapter_never_runs(self):
        version = self.activate()
        del self.manager.active["read_file"]["judgment"]
        with patch.object(
            AdapterProgram, "run", side_effect=AssertionError("legacy source ran")
        ):
            self.assertEqual(self.manager.apply("read_file", INPUT), (INPUT, None))
        self.assertEqual(self.manager.current("read_file"), version)

    def test_invalid_scope_and_expiry_abstain(self):
        self.activate()
        entry = self.manager.inventory()["read_file"]
        for expiry in (None, "tomorrow", float("nan"), float("inf"), True):
            entry["judgment"]["expires_at"] = expiry
            self.assertEqual(
                judge(entry, INPUT, self.manager.context_key("read_file")).action,
                "abstain",
            )
        entry["judgment"]["policy_version"] = 999
        self.assertEqual(judge(entry, INPUT, "x").reason, "LEGACY_OR_UNKNOWN_POLICY")

    def test_preview_and_cancel_do_not_evaluate_or_retire_adapter(self):
        version = self.activate()
        for mode in ("preview", "cancel"):
            self.registry.preview = mode == "preview"
            self.registry.cancelled.set() if mode == "cancel" else self.registry.cancelled.clear()
            with patch.object(
                self.manager, "apply", side_effect=AssertionError("evaluated")
            ):
                result = self.registry.execute("read_file", **INPUT)
            self.assertFalse(result.success)
            self.assertEqual(self.manager.current("read_file"), version)
            self.assertNotIn("quarantined", self.manager.inventory()["read_file"])

    def test_structured_environment_failure_retains_adapter(self):
        version = self.activate()
        failed = ToolResult(
            False, error="offline", metadata={"error_code": "PROVIDER_UNAVAILABLE"}
        )
        with patch.object(self.raw, "execute", return_value=failed) as raw:
            result = self.registry.execute("read_file", **INPUT)
            self.assertEqual(raw.call_count, 1)
        self.assertEqual(self.manager.current("read_file"), version)
        self.assertFalse(result.metadata["adapter_quarantined"])
        self.assertEqual(self.manager.decision("read_file", INPUT).action, "apply")

    def test_ambiguous_failure_quarantines_without_rollback_or_replay(self):
        first = self.activate()
        version = self.activate()
        with patch.object(
            self.raw, "execute", return_value=ToolResult(False, error="uncertain")
        ) as raw:
            result = self.registry.execute("read_file", **INPUT)
            self.assertEqual(raw.call_count, 1)
        self.assertTrue(result.metadata["adapter_quarantined"])
        self.assertEqual(self.manager.current("read_file"), version)
        self.assertNotEqual(version, first)
        self.assertEqual(
            self.manager.decision("read_file", INPUT).reason, "QUARANTINED_NEEDS_REVIEW"
        )

    def test_quarantine_survives_restart(self):
        self.activate()
        self.manager.record_outcome(
            "read_file", self.manager.current("read_file"), False
        )
        restored = HotRepairManager(self.manager.directory)
        self.registry.hot_repairs = restored
        self.assertEqual(
            restored.decision("read_file", INPUT).reason, "QUARANTINED_NEEDS_REVIEW"
        )

    def test_old_failure_cannot_retire_newer_version(self):
        old = self.activate()
        latest = self.activate()
        self.assertFalse(self.manager.rollback("read_file", expected_version=old))
        self.manager.record_outcome("read_file", old, False)
        self.assertEqual(self.manager.current("read_file"), latest)
        self.assertEqual(self.manager.decision("read_file", INPUT).action, "apply")

    def test_rollback_restores_previous_scope(self):
        first = self.activate()
        original_scope = self.manager.inventory()["read_file"]["judgment"]
        self.activate()
        self.manager.rollback("read_file")
        self.assertEqual(self.manager.current("read_file"), first)
        self.assertEqual(
            self.manager.inventory()["read_file"]["judgment"], original_scope
        )
        self.assertEqual(self.manager.apply("read_file", INPUT), (EXPECTED, first))

    def test_runtime_index_error_is_normalized(self):
        with self.assertRaisesRegex(AdapterError, "runtime"):
            AdapterProgram(
                'def adapt(args): return dict(args, path=args["path"][0])'
            ).run({"path": ""})

    def test_runtime_contract_mismatch_blocks_and_rolls_back(self):
        self.activate()
        with (
            patch.object(AdapterProgram, "run", return_value={"path": "wrong.txt"}),
            patch.object(self.raw, "execute") as raw,
        ):
            result = self.registry.execute("read_file", **INPUT)
            raw.assert_not_called()
        self.assertFalse(result.success)
        self.assertEqual(result.metadata["error_code"], "ADAPTER_FAILED")
        self.assertIsNone(self.manager.current("read_file"))

    def test_rollback_error_preserves_primary_boundary_failure(self):
        first = self.activate()
        self.activate()
        (self.manager.directory / f"{first}.py").write_text("corrupt")
        self.registry.on_failure = lambda *args: setattr(
            self, "captured", args[-1].error
        )
        with (
            patch.object(
                self.registry.engine,
                "prepare_args",
                side_effect=[
                    {"path": str(self.project / INPUT["path"])},
                    ValueError("boundary failure"),
                ],
            ),
            patch.object(self.raw, "execute") as raw,
        ):
            result = self.registry.execute("read_file", **INPUT)
            raw.assert_not_called()
        self.assertEqual(result.metadata["error_code"], "WORKSPACE_BOUNDARY")
        self.assertIn("boundary failure", self.captured)
        self.assertIn("rollback_warning", result.metadata)
        self.assertIsNone(self.manager.current("read_file"))

    def test_storage_failure_blocks_further_repair_dispatch(self):
        self.activate()
        with patch.object(self.manager, "_save", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.manager.record_outcome(
                    "read_file", self.manager.current("read_file"), False
                )
        self.assertEqual(self.manager.decision("read_file", INPUT).action, "block")
        with patch.object(self.raw, "execute") as raw:
            result = self.registry.execute("read_file", **INPUT)
            raw.assert_not_called()
        self.assertFalse(result.success)

    def test_inventory_does_not_expose_mutable_active_policy(self):
        self.activate()
        self.manager.inventory()["read_file"]["judgment"]["approved_inputs"].clear()
        self.assertEqual(self.manager.decision("read_file", INPUT).action, "apply")

    def test_journal_does_not_store_raw_inputs_or_workspace(self):
        self.activate()
        self.manager.apply("read_file", INPUT)
        state = json.dumps(self.manager.inventory()) + json.dumps(
            self.manager.recent_decisions()
        )
        self.assertNotIn(INPUT["path"], state)
        self.assertNotIn(str(self.project), state)

    def test_decision_history_is_bounded(self):
        self.activate()
        for _ in range(225):
            self.manager.apply("read_file", EXPECTED)
        self.assertEqual(len(self.manager.recent_decisions()), 200)

    def test_context_changed_incident_never_contacts_provider(self):
        incident = FailureIncident.capture(
            "read_file",
            INPUT,
            "missing",
            "Read note",
            {"repair_context_key": self.manager.context_key("read_file")},
        )
        self.registry.select_workspace(self.other)
        result = RepairLoop(self.manager, NoProvider(), "current", []).run(
            incident, CASES, threading.Event()
        )
        self.assertIsNone(result.candidate)
        self.assertIn("No provider", result.reason)

    def test_no_change_contract_never_contacts_provider(self):
        incident = FailureIncident.capture(
            "read_file", INPUT, "missing", "Read note", {}
        )
        result = RepairLoop(self.manager, NoProvider(), "current", []).run(
            incident, [ContractCase(EXPECTED, EXPECTED)], threading.Event()
        )
        self.assertIn("No patch needed", result.reason)

    def test_policy_and_environment_failures_never_contact_provider(self):
        for code in (
            "DENIED",
            "CANCELLED",
            "PREVIEW",
            "ADAPTER_FAILED",
            "PROVIDER_UNAVAILABLE",
            "DEPENDENCY_MISSING",
            "RATE_LIMITED",
            "PERMISSION_DENIED",
        ):
            incident = FailureIncident.capture(
                "read_file", INPUT, "failure", "Read note", {"error_code": code}
            )
            result = RepairLoop(self.manager, NoProvider(), "current", []).run(
                incident, CASES, threading.Event()
            )
            self.assertIsNone(result.candidate)

    def test_outside_workspace_contract_rejected_before_provider(self):
        incident = FailureIncident.capture(
            "read_file", INPUT, "missing", "Read note", {}
        )
        with self.assertRaisesRegex(AdapterError, "workspace safeguards"):
            RepairLoop(self.manager, NoProvider(), "current", []).run(
                incident,
                [ContractCase(INPUT, {"path": "../private.txt"})],
                threading.Event(),
            )

    def test_fingerprints_distinguish_json_types(self):
        self.assertNotEqual(fingerprint({"n": True}), fingerprint({"n": 1}))
        self.assertNotEqual(fingerprint({"n": 1}), fingerprint({"n": "1"}))

    def test_negative_contract_prevents_overbroad_normalization(self):
        source = 'def adapt(args): return dict(args, path=args["path"].strip().lower())'
        negative = ContractCase({"path": "KEEP.txt"}, {"path": "KEEP.txt"})
        with self.assertRaisesRegex(AdapterError, "Contract 2"):
            self.manager.test("read_file", source, [CASES[0], negative])

    def test_context_change_before_dispatch_blocks_tool(self):
        version = self.activate()
        prepare = self.registry.engine.prepare_args
        calls = []

        def changing_context(name, args):
            calls.append(name)
            if len(calls) == 2:
                self.registry.select_workspace(self.other)
            return prepare(name, args)

        with (
            patch.object(
                self.registry.engine, "prepare_args", side_effect=changing_context
            ),
            patch.object(self.raw, "execute") as raw,
        ):
            result = self.registry.execute("read_file", **INPUT)
            raw.assert_not_called()
        self.assertEqual(result.metadata["error_code"], "REPAIR_CONTEXT_CHANGED")
        self.assertEqual(self.manager.current("read_file"), version)

    def test_context_failure_does_not_hide_original_failure_hook(self):
        self.activate()
        captured = []
        self.registry.on_failure = lambda *args: captured.append(args[-1].error)
        self.registry.preview = True
        with patch.object(
            self.manager, "context_key", side_effect=AdapterError("context unavailable")
        ):
            result = self.registry.execute("read_file", **INPUT)
        self.assertEqual(result.metadata["error_code"], "PREVIEW")
        self.assertEqual(
            result.metadata["repair_judgment"]["reason"], "CONTEXT_UNAVAILABLE"
        )
        self.assertEqual(captured, [result.error])

    def test_rollback_save_failure_preserves_primary_adapter_error(self):
        version = self.activate()
        with (
            patch.object(
                self.manager._programs[version],
                "run",
                side_effect=AdapterError("primary fault"),
            ),
            patch.object(self.manager, "_save", side_effect=OSError("disk full")),
        ):
            with self.assertRaisesRegex(AdapterError, "primary fault"):
                self.manager.apply("read_file", INPUT)
        self.assertEqual(self.manager.decision("read_file", INPUT).action, "block")

    def test_corrupt_previous_metadata_fails_closed(self):
        self.activate()
        self.activate()
        self.manager.active["read_file"]["previous_entry"] = ["malformed"]
        with self.assertRaisesRegex(AdapterError, "disabled"):
            self.manager.rollback("read_file")
        self.assertIsNone(self.manager.current("read_file"))

    def test_invalid_utf8_previous_source_fails_closed(self):
        previous = self.activate()
        self.activate()
        (self.manager.directory / f"{previous}.py").write_bytes(b"\xff")
        with self.assertRaisesRegex(AdapterError, "disabled"):
            self.manager.rollback("read_file")
        self.assertIsNone(self.manager.current("read_file"))

    def test_oversized_or_deep_pointer_does_not_load_code(self):
        for text in (" " * 262145, "[" * 1200 + "]" * 1200):
            self.manager.pointer.write_text(text)
            self.assertEqual(HotRepairManager(self.manager.directory).inventory(), {})

    def test_outcome_storage_failure_does_not_claim_tool_was_not_executed(self):
        self.activate()
        with patch.object(self.manager, "_save", side_effect=OSError("disk full")):
            result = self.registry.execute("read_file", **INPUT)
        self.assertTrue(result.success)
        self.assertIn("intended document", result.output)
        self.assertIn("repair_storage_error", result.metadata)
        self.assertEqual(self.manager.decision("read_file", INPUT).action, "block")

    def test_ambiguous_incident_requests_review_not_another_patch(self):
        incident = FailureIncident.capture(
            "read_file", INPUT, "uncertain", "Read note", {"adapter_quarantined": True}
        )
        self.assertEqual(incident.category, "ambiguous_downstream_review")
        result = RepairLoop(self.manager, NoProvider(), "current", []).run(
            incident, CASES, threading.Event()
        )
        self.assertIsNone(result.candidate)

    def test_context_change_during_proposal_stops_escalation(self):
        incident = FailureIncident.capture(
            "read_file",
            INPUT,
            "missing",
            "Read note",
            {"repair_context_key": self.manager.context_key("read_file")},
        )
        owner = self

        class Provider:
            calls = 0

            def list_models(self):
                return {"current", "fallback"}

            def propose(self, *args):
                self.calls += 1
                owner.registry.select_workspace(owner.other)
                return {"action": "candidate", "source": STRIP}

        provider = Provider()
        result = RepairLoop(self.manager, provider, "current", ["fallback"]).run(
            incident, CASES, threading.Event()
        )
        self.assertIsNone(result.candidate)
        self.assertEqual(provider.calls, 1)
        self.assertIn("context changed", result.reason)

    def test_nonrepairable_custom_tool_is_not_blocked_by_schema_lookup(self):
        result = self.registry.execute("restore_file_backup", backup_id="missing")
        self.assertFalse(result.success)
        self.assertNotEqual(result.metadata.get("error_code"), "ADAPTER_FAILED")

    def test_type_only_correction_is_not_mistaken_for_no_change(self):
        cases = [
            ContractCase(
                {"path": "note.txt", "max_bytes": True},
                {"path": "note.txt", "max_bytes": 1},
            )
        ]
        incident = FailureIncident.capture(
            "read_file", cases[0].arguments, "bad type", "Read note", {}
        )

        class Provider:
            def list_models(self):
                return {"current"}

            def propose(self, *args):
                return {
                    "action": "candidate",
                    "source": 'def adapt(args): return dict(args, max_bytes=int(args["max_bytes"]))',
                }

        result = RepairLoop(self.manager, Provider(), "current", []).run(
            incident, cases, threading.Event()
        )
        self.assertIsNotNone(result.candidate)


class RepairLifecycle(RuleBasedStateMachine):
    """A model of contextual eligibility through arbitrary operation sequences."""

    def __init__(self):
        super().__init__()
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.context = "A"
        self.manager = self.make_manager()
        self.stack = []

    def make_manager(self):
        manager = HotRepairManager(self.directory)
        manager.context_provider = lambda tool: {"workspace": self.context}
        return manager

    @rule()
    def activate(self):
        candidate = self.manager.test("read_file", STRIP, CASES)
        version = self.manager.activate(candidate, CASES)
        # The manager intentionally retains just one rollback generation.
        previous = self.stack[-1] if self.stack else None
        self.stack = ([previous] if previous else []) + [(version, self.context, False)]

    @rule()
    def switch_workspace(self):
        self.context = "B" if self.context == "A" else "A"

    @rule()
    def restart(self):
        self.manager = self.make_manager()

    @rule()
    def quarantine(self):
        if self.stack:
            version, context, _ = self.stack[-1]
            self.manager.record_outcome("read_file", version, False)
            self.stack[-1] = (version, context, True)

    @rule()
    def external_failure(self):
        if self.stack:
            self.manager.record_outcome(
                "read_file", self.stack[-1][0], False, environmental=True
            )

    @rule()
    def success(self):
        if self.stack:
            self.manager.record_outcome("read_file", self.stack[-1][0], True)

    @rule()
    def rollback(self):
        self.manager.rollback("read_file")
        if self.stack:
            self.stack.pop()
            if len(self.stack) > 1:
                self.stack = [self.stack[-1]]

    @invariant()
    def only_eligible_reviewed_inputs_change(self):
        active = self.stack[-1] if self.stack else None
        eligible = active and active[1] == self.context and not active[2]
        output, version = self.manager.apply("read_file", INPUT)
        assert output == (EXPECTED if eligible else INPUT)
        assert version == (active[0] if eligible else None)
        unseen = {"path": " another.txt"}
        assert self.manager.apply("read_file", unseen) == (unseen, None)
        assert self.manager.current("read_file") == (active[0] if active else None)

    def teardown(self):
        self.temp.cleanup()


TestRepairLifecycle = RepairLifecycle.TestCase
TestRepairLifecycle.settings = settings(
    max_examples=100, stateful_step_count=40, deadline=None, derandomize=True
)

# Avoid collecting the optional placeholder twice under its internal alias.
if "_MissingLifecycle" in globals():
    del _MissingLifecycle
