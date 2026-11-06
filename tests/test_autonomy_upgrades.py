"""Offline engineering invariants; no live providers, commands or network requests."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from custom_jarvis import compat
from custom_jarvis.addon_runtime import AddonRegistry
from custom_jarvis.autonomy_governor import AutonomyGovernor, BudgetLimits
from custom_jarvis.brain import detect_intent_ambiguity, score_candidate_plan
from custom_jarvis.evidence import BackupManager, file_digest
from custom_jarvis.failure_memory import (
    RepairCircuitBreaker,
    compute_incident_fingerprint,
    normalize_error_signature,
)
from custom_jarvis.goal_verifier import (
    GoalAssertion,
    infer_goal_assertions,
    verify_goal,
)
from custom_jarvis.hot_repair import ContractCase, HotRepairManager
from custom_jarvis.knowledge import KnowledgeStore
from custom_jarvis.planner import AutonomousPlanner, PlanStep, StepStatus
from custom_jarvis.preflight import (
    CausalGraphTracker,
    PreflightDoctor,
    StateDriftGuard,
    extract_step_dependencies,
)
from custom_jarvis.repair_adapter import AdapterError, AdapterProgram
from custom_jarvis.self_healing import FailureIncident, RepairLoop
from custom_jarvis.skills import (
    SKILLS,
    Skill,
    compile_procedure_to_skill,
    judge_skill_applicability,
)
from custom_jarvis.tools import ToolRegistry, execute_command, read_file, write_file

STRIP = 'def adapt(args):\n    return dict(args, path=args["path"].strip())\n'
CASES = [ContractCase({"path": " note.txt"}, {"path": "note.txt"})]


class OfflineProvider:
    def __init__(self, answer=None):
        self.calls = 0
        self.discoveries = 0
        self.answer = answer or {"action": "stop", "reason": "manual review"}

    def list_models(self):
        self.discoveries += 1
        return {"current", "fallback"}

    def propose(self, model, payload):
        self.calls += 1
        return self.answer


class AutonomyUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / "A"
        self.root.mkdir()
        self.other = self.base / "B"
        self.other.mkdir()
        (self.root / "note.txt").write_text("hello", encoding="utf-8")
        (self.other / "other.txt").write_text("other", encoding="utf-8")
        self.store = KnowledgeStore(self.base / "knowledge.sqlite3")
        self.backups = BackupManager(self.base / "backups")
        self.raw = ToolRegistry()
        self.raw.register(name="read_file")(read_file)
        self.raw.register(name="write_file")(write_file)
        self.control = AddonRegistry(
            self.raw, lambda *args: True, self.store, self.backups
        )
        self.control.select_workspace(self.root)
        self.manager = HotRepairManager(self.base / "repairs")
        self.control.hot_repairs = self.manager

    def tearDown(self):
        self.temp.cleanup()

    def activate(self, cases=CASES):
        return self.manager.activate(
            self.manager.test("read_file", STRIP, cases), cases
        )

    def incident(self):
        return FailureIncident.capture(
            "read_file",
            CASES[0].arguments,
            "missing file",
            "Read note",
            {"repair_context_key": self.manager.context_key("read_file")},
        )

    def test_compat_process_without_psutil(self):
        with patch.dict("sys.modules", {"psutil": None}):
            self.assertGreater(compat.ProcessCompat().memory_info().rss, 0)

    def test_compat_error_type(self):
        self.assertTrue(issubclass(compat.psutil_shim.Error, Exception))

    def test_html_fallback_removes_untrusted_sections(self):
        with patch.dict("sys.modules", {"bs4": None}):
            title, text = compat.extract_webpage_text(
                "<title>Title</title><nav>hidden</nav><script>danger</script><p>A &amp; B</p>"
            )
        self.assertEqual(title, "Title")
        self.assertIn("A & B", text)
        self.assertNotIn("hidden", text)
        self.assertNotIn("danger", text)

    def test_html_fallback_nested_skipped_tags(self):
        with patch.object(compat, "HAS_BS4", False):
            _, text = compat.extract_webpage_text(
                "<svg><style>hidden</style>also hidden</svg><p>visible</p>"
            )
        self.assertEqual(text, "visible")

    def test_error_normalization(self):
        result = normalize_error_signature(
            'FAILED at 0xAB12 line 42 column 9 "/tmp/private.py"'
        )
        self.assertIn("<addr>", result)
        self.assertIn("line <n>", result)
        self.assertIn("<path>", result)
        self.assertNotIn("private", result)

    def test_fingerprint_is_deterministic_and_context_specific(self):
        a = compute_incident_fingerprint("read_file", "E", "line 1", "A")
        self.assertEqual(
            a, compute_incident_fingerprint("read_file", "E", "line 2", "A")
        )
        self.assertNotEqual(
            a, compute_incident_fingerprint("read_file", "E", "line 2", "B")
        )

    def test_fingerprint_upsert_and_bind(self):
        self.store.record_fingerprint("f", "read_file", "ctx", "E", "normalized")
        row = self.store.record_fingerprint("f", "read_file", "ctx", "E", "normalized")
        self.assertEqual(row["occurrences"], 2)
        self.store.bind_fingerprint_solution("f", STRIP, "[]")
        self.assertEqual(self.store.get_fingerprint("f")["resolved_count"], 1)

    def test_fingerprint_memory_reuses_validated_adapter(self):
        incident = self.incident()
        self.store.record_fingerprint(
            incident.fingerprint,
            incident.tool,
            incident.context_key,
            "",
            "missing file",
        )
        self.store.bind_fingerprint_solution(
            incident.fingerprint, STRIP, json.dumps([])
        )
        provider = OfflineProvider()
        result = RepairLoop(
            self.manager, provider, "current", [], knowledge=self.store
        ).run(incident, CASES, threading.Event())
        self.assertIsNotNone(result.candidate)
        self.assertEqual(result.attempts[0]["status"], "fingerprint_memory_hit")
        self.assertEqual(provider.calls, 0)
        self.assertEqual(provider.discoveries, 0)
        self.assertIsNone(self.manager.current("read_file"))

    def test_bad_memory_solution_is_not_promoted(self):
        incident = self.incident()
        self.store.record_fingerprint(
            incident.fingerprint, incident.tool, incident.context_key, "", "missing"
        )
        self.store.bind_fingerprint_solution(
            incident.fingerprint, "def adapt(args): return dict(args)", "[]"
        )
        provider = OfflineProvider()
        result = RepairLoop(
            self.manager, provider, "current", [], knowledge=self.store
        ).run(incident, CASES, threading.Event())
        self.assertIsNone(result.candidate)
        self.assertEqual(provider.calls, 1)

    def test_circuit_trip_and_cooldown(self):
        breaker = RepairCircuitBreaker(cooldown_seconds=10)
        for n in range(3):
            breaker.record_repair_attempt("read_file", "ctx", False, now=n)
        self.assertFalse(breaker.check("read_file", "ctx", now=3)[0])
        self.assertTrue(breaker.check("read_file", "ctx", now=14)[0])

    def test_circuit_breaker_blocks_repair_loop(self):
        breaker = RepairCircuitBreaker()
        incident = self.incident()
        for _ in range(3):
            breaker.record_repair_attempt(incident.tool, incident.context_key, False)
        provider = OfflineProvider()
        result = RepairLoop(
            self.manager, provider, "current", [], circuit_breaker=breaker
        ).run(incident, CASES, threading.Event())
        self.assertIn("Circuit breaker open", result.reason)
        self.assertEqual(provider.calls, 0)
        self.assertEqual(provider.discoveries, 0)

    def test_version_oscillation(self):
        breaker = RepairCircuitBreaker()
        breaker.record_rollback("tool", "ctx", "A", "B", now=0)
        breaker.record_rollback("tool", "ctx", "B", "A", now=1)
        self.assertEqual(
            breaker.check("tool", "ctx", now=2)[1], "CIRCUIT_OPEN_VERSION_OSCILLATION"
        )

    def test_rollback_storm(self):
        breaker = RepairCircuitBreaker()
        breaker.record_rollback("tool", "ctx", "A", "B", now=0)
        breaker.record_rollback("tool", "ctx", "C", "D", now=1)
        self.assertEqual(
            breaker.check("tool", "ctx", now=2)[1], "CIRCUIT_OPEN_ROLLBACK_STORM"
        )

    def test_breaker_reset_is_scoped(self):
        breaker = RepairCircuitBreaker()
        for _ in range(3):
            breaker.record_repair_attempt("tool", "ctx", False, now=0)
        breaker.reset("tool", "different")
        self.assertFalse(breaker.check("tool", "ctx", now=1)[0])
        breaker.reset("tool", "ctx")
        self.assertTrue(breaker.check("tool", "ctx", now=1)[0])

    def test_catalog_keeps_two_workspaces(self):
        a = self.activate()
        self.control.select_workspace(self.other)
        cases = [ContractCase({"path": " other.txt"}, {"path": "other.txt"})]
        b = self.activate(cases)
        self.control.select_workspace(self.root)
        self.assertEqual(self.manager.current("read_file"), a)
        self.assertTrue(self.control.execute("read_file", **CASES[0].arguments).success)
        self.control.select_workspace(self.other)
        self.assertEqual(self.manager.current("read_file"), b)

    def test_catalog_survives_restart(self):
        a = self.activate()
        self.control.select_workspace(self.other)
        self.activate([ContractCase({"path": " other.txt"}, {"path": "other.txt"})])
        restored = HotRepairManager(self.manager.directory)
        self.control.hot_repairs = restored
        self.control.select_workspace(self.root)
        self.assertEqual(restored.current("read_file"), a)

    def test_canary_graduates_after_five(self):
        version = self.activate()
        self.assertEqual(self.manager.inventory()["read_file"]["canary_remaining"], 5)
        for _ in range(5):
            self.manager.record_outcome("read_file", version, True)
        entry = self.manager.inventory()["read_file"]
        self.assertEqual(entry["canary_remaining"], 0)
        self.assertTrue(entry["canary_graduated"])

    def test_canary_failure_quarantines(self):
        version = self.activate()
        self.manager.record_outcome("read_file", version, False)
        entry = self.manager.inventory()["read_file"]
        self.assertTrue(entry["quarantined"])
        self.assertTrue(entry["failed_during_canary"])

    def test_external_failure_does_not_spend_canary(self):
        version = self.activate()
        self.manager.record_outcome("read_file", version, False, environmental=True)
        self.assertEqual(self.manager.inventory()["read_file"]["canary_remaining"], 5)

    def test_shadow_evaluation_has_no_promotion_or_disk_writes(self):
        before = list(self.manager.directory.iterdir())
        result = self.manager.shadow_evaluate("read_file", STRIP, [CASES[0].arguments])
        self.assertEqual(result["schema_valid_count"], 1)
        self.assertEqual(result["workspace_safe_count"], 1)
        self.assertFalse(result["promoted"])
        self.assertEqual(list(self.manager.directory.iterdir()), before)
        self.assertIsNone(self.manager.current("read_file"))

    def test_shadow_rejects_workspace_escape(self):
        result = self.manager.shadow_evaluate(
            "read_file",
            'def adapt(args): return dict(args,path="../secret")',
            [CASES[0].arguments],
        )
        self.assertEqual(result["workspace_safe_count"], 0)

    def test_shadow_caps_replay_count(self):
        self.assertEqual(
            self.manager.shadow_evaluate("read_file", STRIP, [CASES[0].arguments] * 50)[
                "total_cases"
            ],
            32,
        )

    def test_dsl_string_methods(self):
        for method, expected in [
            ("lstrip()", "note.txt"),
            ("rstrip()", " note.txt"),
            ('removeprefix(" ")', "note.txt"),
        ]:
            source = (
                'def adapt(args): return dict(args,path=args["path"].' + method + ")"
            )
            self.assertEqual(
                AdapterProgram(source).run({"path": " note.txt"})["path"], expected
            )

    def test_dsl_join_split_and_predicates(self):
        source = 'def adapt(args): return dict(args, parts=args["path"].split("/"), joined="/".join(args["parts"]), digits="123".isdecimal(), start="abc".startswith("a"))'
        result = AdapterProgram(source).run({"path": "a/b", "parts": ["x", "y"]})
        self.assertEqual(result["joined"], "x/y")
        self.assertTrue(result["digits"])
        self.assertEqual(result["parts"], ["a", "b"])

    def test_dsl_dictionary_views(self):
        result = AdapterProgram(
            "def adapt(args): return dict(args, names=args.keys())"
        ).run({"path": "note"})
        self.assertEqual(result["names"], ["path"])

    def test_dsl_join_rejects_expansion(self):
        with self.assertRaises(AdapterError):
            AdapterProgram(
                'def adapt(args): return {"result": args["sep"].join(args["values"])}'
            ).run({"sep": "x" * 1000, "values": [""] * 100})

    def test_preflight_requires_workspace(self):
        report = PreflightDoctor.check_plan(
            [PlanStep(1, "inspect", "inspect_python", {})], None, False
        )
        self.assertFalse(report.ready)
        self.assertEqual(report.blockers[0]["code"], "WORKSPACE_REQUIRED")

    def test_preflight_detects_missing_git(self):
        with patch("custom_jarvis.preflight.shutil.which", return_value=None):
            report = PreflightDoctor.check_plan(
                [PlanStep(1, "git", "git_inspect", {})], self.root, True
            )
        self.assertEqual(report.blockers[0]["code"], "GIT_BINARY_MISSING")

    def test_preflight_detects_missing_workspace_directory(self):
        report = PreflightDoctor.check_plan(
            [PlanStep(1, "read", "read_file", {})], self.base / "missing", False
        )
        self.assertEqual(report.blockers[0]["code"], "WORKSPACE_MISSING")

    def test_preflight_detects_unconfigured_vision(self):
        with patch.dict(
            os.environ, {"JARVIS_VISION_BASE_URL": "", "JARVIS_VISION_MODEL": ""}
        ):
            report = PreflightDoctor.check_plan(
                [PlanStep(1, "vision", "analyze_screenshot", {})], self.root, True
            )
        self.assertFalse(report.ready)

    def test_dependencies_nested_and_previous(self):
        self.assertEqual(
            extract_step_dependencies(
                {"x": ["$STEP_1_OUTPUT", {"v": "{{prev_data}}"}]}, 3
            ),
            {1, 2},
        )

    def test_causal_graph_tracks_root_and_cascade(self):
        tracker = CausalGraphTracker(self.store, "task")
        first = tracker.record(
            PlanStep(1, "capture", "take_screenshot", {}),
            "desktop",
            {"error_code": "DESKTOP_UNAVAILABLE"},
        )
        second = tracker.record(
            PlanStep(2, "read", "read_file", {"path": "$STEP_1_OUTPUT"}), "missing", {}
        )
        self.assertEqual(first["classification"], "root_cause")
        self.assertEqual(second["classification"], "cascaded_symptom")
        self.assertEqual(second["root_cause_step_id"], 1)

    def test_state_drift_blocks_clobbering_write(self):
        target = self.root / "note.txt"
        self.assertTrue(self.control.execute("read_file", path="note.txt").success)
        target.write_text("external edit", encoding="utf-8")
        result = self.control.execute(
            "write_file", path="note.txt", content="clobbered"
        )
        self.assertFalse(result.success)
        self.assertEqual(result.metadata["error_code"], "STATE_DRIFT_DETECTED")
        self.assertEqual(target.read_text(), "external edit")

    def test_state_drift_baseline_reset(self):
        guard = StateDriftGuard()
        target = self.root / "note.txt"
        guard.observe_file(target)
        target.write_text("changed")
        self.assertFalse(guard.unchanged(target))
        guard.reset()
        self.assertTrue(guard.unchanged(target))

    def test_transaction_batch_rolls_back_multiple_files(self):
        tx = self.backups.begin_transaction()
        for n in range(3):
            target = self.root / f"{n}.txt"
            target.write_text("before")
            identity, _ = self.backups.prepare(target)
            target.write_text("after")
            self.backups.finish(identity, target)
            self.backups.record_in_transaction(tx, identity)
        result = self.backups.rollback_transaction(tx, self.root)
        self.assertEqual(
            [Path(row["path"]).name for row in result["restored_files"]],
            ["2.txt", "1.txt", "0.txt"],
        )
        self.assertFalse(result["conflicts"])
        self.assertTrue(
            all((self.root / f"{n}.txt").read_text() == "before" for n in range(3))
        )

    def test_transaction_conflict_is_reported(self):
        tx = self.backups.begin_transaction()
        target = self.root / "note.txt"
        identity, _ = self.backups.prepare(target)
        target.write_text("after")
        self.backups.finish(identity, target)
        self.backups.record_in_transaction(tx, identity)
        target.write_text("external")
        result = self.backups.rollback_transaction(tx, self.root)
        self.assertEqual(len(result["conflicts"]), 1)
        self.assertEqual(target.read_text(), "external")

    def test_transaction_tool_requires_approval(self):
        self.control.approve = lambda *args: False
        result = self.control.execute(
            "rollback_transaction", transaction_id="arbitrary"
        )
        self.assertEqual(result.metadata["error_code"], "DENIED")

    def test_goal_sha_and_python_assertions(self):
        target = self.root / "code.py"
        target.write_text("x = 1\n")
        assertions = [
            GoalAssertion(
                "file_sha256",
                str(target),
                hashlib.sha256(target.read_bytes()).hexdigest(),
            ),
            GoalAssertion("python_valid", str(target)),
        ]
        result = verify_goal(assertions, self.root, [])
        self.assertTrue(result["goal_verified"])
        self.assertEqual(result["assertions_passed"], 2)

    def test_goal_json_and_key_assertions(self):
        target = self.root / "data.json"
        target.write_text('{"ok":true}')
        self.assertTrue(
            verify_goal(
                [
                    GoalAssertion(
                        "json_key_equals", str(target), {"key": "ok", "value": True}
                    )
                ],
                self.root,
                [],
            )["goal_verified"]
        )

    def test_goal_rejects_escape_and_empty_assertions(self):
        self.assertFalse(
            verify_goal([GoalAssertion("file_exists", "../secret")], self.root, [])[
                "goal_verified"
            ]
        )
        self.assertFalse(verify_goal([], self.root, [])["goal_verified"])

    def test_goal_inference_from_write(self):
        steps = [
            PlanStep(1, "write", "write_file", {"path": "new.txt", "content": "new"})
        ]
        self.assertEqual(
            [a.kind for a in infer_goal_assertions("write", steps, self.root)],
            ["file_exists", "file_sha256"],
        )

    def test_checkpoint_resume_skips_verified_completed_step(self):
        completed = PlanStep(
            1,
            "read",
            "read_file",
            {"path": "note.txt"},
            status=StepStatus.COMPLETED,
            output="hello",
            artifact_sha256=file_digest(self.root / "note.txt"),
        )
        pending = PlanStep(
            2, "write", "write_file", {"path": "new.txt", "content": "$STEP_1_OUTPUT"}
        )
        planner = AutonomousPlanner(
            brain=MagicMock(), tool_registry=self.control, verbose=False
        )
        with patch.object(self.raw, "execute", wraps=self.raw.execute) as calls:
            result = planner.resume_from_checkpoint(
                {
                    "goal": "write new.txt",
                    "steps": [completed.to_dict(), pending.to_dict()],
                }
            )
        self.assertTrue(result.success)
        self.assertEqual(calls.call_count, 1)
        self.assertEqual((self.root / "new.txt").read_text(), "hello")

    def test_checkpoint_resume_rejects_drift(self):
        row = PlanStep(
            1,
            "read",
            "read_file",
            {"path": "note.txt"},
            status=StepStatus.COMPLETED,
            artifact_sha256="wrong",
        ).to_dict()
        planner = AutonomousPlanner(
            brain=MagicMock(), tool_registry=self.control, verbose=False
        )
        with self.assertRaises(ValueError):
            planner.resume_from_checkpoint({"steps": [row]})

    def test_resume_requires_explicit_approval(self):
        with self.assertRaises(ValueError):
            AutonomousPlanner(brain=MagicMock()).resume_from_checkpoint({}, False)

    def test_skill_applicability(self):
        skill = Skill(
            "git", "Git", "inspect", (("git_inspect", {}),), required_markers=(".git",)
        )
        self.assertFalse(judge_skill_applicability(skill, self.root)["applicable"])
        self.assertEqual(len(SKILLS), 24)

    def test_compile_approved_structured_procedure(self):
        row = {
            "id": "id",
            "title": "Read",
            "status": "approved",
            "instructions": json.dumps(
                [{"tool_name": "read_file", "tool_args": {"path": "@target"}}]
            ),
        }
        skill = compile_procedure_to_skill(
            row, {"read_file", "project_snapshot", "verify_file"}
        )
        self.assertEqual(skill.calls[0][0], "project_snapshot")
        self.assertEqual(skill.calls[-1][0], "verify_file")

    def test_unapproved_procedure_rejected(self):
        with self.assertRaises(ValueError):
            compile_procedure_to_skill({"status": "proposed"}, set())

    def test_competence_ranking_uses_evidence(self):
        for _ in range(4):
            self.store.record_model_outcome("bad", "read_file", False, 10, True)
            self.store.record_model_outcome("good", "read_file", True, 10)
        self.assertEqual(
            self.store.rank_models_for_task(["bad", "good"], "read_file"),
            ["good", "bad"],
        )

    def test_sparse_competence_preserves_user_order(self):
        self.store.record_model_outcome("one", "read_file", True, 1)
        self.assertEqual(
            self.store.rank_models_for_task(["none", "one"], "read_file"),
            ["none", "one"],
        )

    def test_budget_governor_enforces_repair_limit(self):
        governor = AutonomyGovernor(self.store, BudgetLimits(max_repair_calls=1))
        self.assertTrue(governor.request_call("repair")[0])
        allowed, reason = governor.request_call("repair")
        self.assertFalse(allowed)
        self.assertEqual(reason, "SESSION_REPAIR_BUDGET_EXCEEDED")

    def test_budget_completion_limit_and_persistence(self):
        governor = AutonomyGovernor(
            self.store, BudgetLimits(max_completion_calls=1), session_id="session"
        )
        self.assertTrue(governor.request_call()[0])
        restored = AutonomyGovernor(
            self.store, BudgetLimits(max_completion_calls=1), session_id="session"
        )
        self.assertFalse(restored.request_call()[0])

    def test_budget_wall_time_and_abort_pause(self):
        governor = AutonomyGovernor(
            limits=BudgetLimits(max_wall_seconds=1, max_consecutive_aborts=1)
        )
        governor.record_task_duration(1, aborted=True)
        self.assertFalse(governor.request_call()[0])
        self.assertTrue(governor.status()["paused"])

    def test_budget_limits_repair_loop(self):
        governor = AutonomyGovernor(limits=BudgetLimits(max_repair_calls=0))
        provider = OfflineProvider()
        outcome = RepairLoop(
            self.manager, provider, "current", [], governor=governor
        ).run(self.incident(), CASES, threading.Event())
        self.assertIsNone(outcome.candidate)
        self.assertEqual(provider.calls, 0)

    def test_forget_clears_all_seven_tables(self):
        self.store.record_budget_usage("session", 1)
        self.store.record_fingerprint("f", "read_file", "ctx", "E", "sig")
        self.store.forget()
        with self.store._connect() as db:
            for table in (
                "stats",
                "procedures",
                "checkpoints",
                "failure_fingerprints",
                "model_competence",
                "budget_ledger",
                "incident_graph",
            ):
                self.assertEqual(
                    db.execute(f"SELECT count(*) FROM {table}").fetchone()[0], 0
                )

    def test_counterfactual_scoring_prefers_read_only(self):
        good = score_candidate_plan(
            [{"tool_name": "read_file"}], {}, frozenset({"read_file"})
        )
        bad = score_candidate_plan(
            [{"tool_name": "execute_command"}], {}, frozenset({"read_file"})
        )
        self.assertGreater(good["score"], bad["score"])

    def test_destructive_goal_requires_clarification(self):
        self.assertTrue(
            detect_intent_ambiguity("delete everything", self.root)["ambiguous"]
        )

    def test_duplicate_filename_requires_clarification(self):
        nested = self.root / "nested"
        nested.mkdir()
        (nested / "note.txt").write_text("other")
        self.assertTrue(
            detect_intent_ambiguity("overwrite note.txt", self.root)["ambiguous"]
        )

    def test_subprocess_cancellation_is_interruptible(self):
        event = threading.Event()
        event.set()
        proc = MagicMock()
        proc.poll.return_value = None
        with (
            patch("custom_jarvis.tools.subprocess.Popen", return_value=proc),
            patch("custom_jarvis.tools._terminate_tree") as terminate,
        ):
            result = execute_command("never run", cancel_event=event)
        self.assertEqual(result.metadata["error_code"], "CANCELLED")
        terminate.assert_called_once()

    def test_cancellation_event_is_not_in_tool_schema(self):
        raw = ToolRegistry()
        raw.register(name="execute_command")(execute_command)
        self.assertNotIn(
            "cancel_event", raw.get("execute_command").parameters["properties"]
        )

    def test_sqlite_new_indices_exist(self):
        with sqlite3.connect(self.store.path) as db:
            names = {
                row[0]
                for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='index'"
                )
            }
        db.close()
        self.assertTrue(
            {
                "idx_fingerprints_tool_ctx",
                "idx_competence_task",
                "idx_incident_task",
            }.issubset(names)
        )
