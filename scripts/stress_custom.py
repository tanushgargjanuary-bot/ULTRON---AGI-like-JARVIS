"""Reproducible local repair stress checks; no real model/provider calls.

Run: python scripts/stress_custom.py
"""

from __future__ import annotations

import json
import random
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from custom_jarvis.addon_runtime import AddonRegistry
from custom_jarvis.evidence import BackupManager
from custom_jarvis.hot_repair import ContractCase, HotRepairManager
from custom_jarvis.knowledge import KnowledgeStore
from custom_jarvis.repair_adapter import AdapterError, AdapterProgram
from custom_jarvis.tools import ToolRegistry, read_file

STRIP = 'def adapt(args):\n    result = dict(args)\n    result["path"] = args["path"].strip()\n    return result\n'


def main():
    start = time.monotonic()
    rng = random.Random(20261104)
    checks = {
        "normalization": 0,
        "bounded_attack_rejection": 0,
        "workspace_boundary": 0,
        "ambiguous_failure_quarantine": 0,
        "unreviewed_input_abstention": 0,
        "literal_filename_preservation": 0,
        "cross_workspace_abstention": 0,
        "expired_review_abstention": 0,
    }
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        project = base / "project"
        project.mkdir()
        other = base / "other"
        other.mkdir()
        raw = ToolRegistry()
        raw.register(name="read_file")(read_file)
        registry = AddonRegistry(
            raw,
            lambda *args: True,
            KnowledgeStore(base / "memory.sqlite3"),
            BackupManager(base / "backups"),
        )
        manager = HotRepairManager(base / "repairs")
        registry.hot_repairs = manager
        registry.select_workspace(project)
        for number in range(150):
            filename = f"document_{number}_{rng.randrange(100000)}.txt"
            (project / filename).write_text(str(number), encoding="utf-8")
            original = "\t " + filename + "  \n"
            cases = [ContractCase({"path": original}, {"path": filename})]
            tested = manager.test("read_file", STRIP, cases)
            manager.activate(tested, cases)
            result = registry.execute("read_file", path=original)
            assert result.success, result.error
            assert manager.current("read_file") is not None
            manager.rollback("read_file")
            checks["normalization"] += 1
        for number in range(100):
            bad = 'def adapt(args): return {"x": "a" * ' + str(10**6 + number) + "}"
            try:
                AdapterProgram(bad).run({})
            except AdapterError:
                checks["bounded_attack_rejection"] += 1
            else:
                raise AssertionError("Unsupported multiplication was allowed")
        for number in range(50):
            outside = f"../private_{number}.txt"
            source = "def adapt(args): return dict(args, path=" + repr(outside) + ")"
            case = ContractCase({"path": "document.txt"}, {"path": outside})
            try:
                manager.test("read_file", source, [case])
            except AdapterError:
                pass
            else:
                raise AssertionError("Unsafe output accepted at review")
            assert manager.current("read_file") is None
            checks["workspace_boundary"] += 1
        for number in range(50):
            original = f" missing_{number}.txt"
            cases = [ContractCase({"path": original}, {"path": original.strip()})]
            version = manager.activate(manager.test("read_file", STRIP, cases), cases)
            result = registry.execute("read_file", path=original)
            assert not result.success
            assert result.metadata["adapter_quarantined"] is True
            assert manager.current("read_file") == version
            assert manager.apply("read_file", {"path": original}) == (
                {"path": original},
                None,
            )
            manager.rollback("read_file")
            checks["ambiguous_failure_quarantine"] += 1
        for number in range(50):
            cases = [ContractCase({"path": " present.txt "}, {"path": "present.txt"})]
            version = manager.activate(manager.test("read_file", STRIP, cases), cases)
            unseen = {"path": f" unseen_{number}.txt "}
            assert manager.apply("read_file", unseen) == (unseen, None)
            assert manager.current("read_file") == version
            manager.rollback("read_file")
            checks["unreviewed_input_abstention"] += 1
        for number in range(50):
            filename = f"guard_{number}.txt"
            literal = " " + filename
            (project / filename).write_text("normal", encoding="utf-8")
            cases = [ContractCase({"path": literal}, {"path": filename})]
            manager.activate(manager.test("read_file", STRIP, cases), cases)
            (project / literal).write_text("literal", encoding="utf-8")
            result = registry.execute("read_file", path=literal)
            assert result.success and "literal" in result.output
            assert (
                result.metadata["repair_judgment"]["reason"] == "ORIGINAL_PATH_EXISTS"
            )
            manager.rollback("read_file")
            checks["literal_filename_preservation"] += 1
        for number in range(50):
            cases = [ContractCase({"path": " present.txt "}, {"path": "present.txt"})]
            manager.activate(manager.test("read_file", STRIP, cases), cases)
            registry.select_workspace(other)
            assert manager.apply("read_file", cases[0].arguments) == (
                cases[0].arguments,
                None,
            )
            registry.select_workspace(project)
            manager.rollback("read_file")
            checks["cross_workspace_abstention"] += 1
        for number in range(50):
            cases = [ContractCase({"path": " present.txt "}, {"path": "present.txt"})]
            manager.activate(manager.test("read_file", STRIP, cases), cases)
            expiry = manager.inventory()["read_file"]["judgment"]["expires_at"]
            with patch(
                "custom_jarvis.repair_judgment.time.time", return_value=expiry + 1
            ):
                assert manager.apply("read_file", cases[0].arguments) == (
                    cases[0].arguments,
                    None,
                )
            manager.rollback("read_file")
            checks["expired_review_abstention"] += 1
    # Repeated, isolated lifecycle scenarios: each invocation has its own workspace,
    # SQLite database and repair catalog. These are repetition checks, not fuzzing.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
    import unittest

    from test_autonomy_upgrades import AutonomyUpgradeTests

    extensions = [
        ("workspace_catalog_lifecycle", 100, "test_catalog_keeps_two_workspaces"),
        ("canary_countdown_lifecycle", 100, "test_canary_graduates_after_five"),
        ("circuit_breaker_lifecycle", 100, "test_circuit_breaker_blocks_repair_loop"),
        (
            "shadow_replay_lifecycle",
            100,
            "test_shadow_evaluation_has_no_promotion_or_disk_writes",
        ),
        (
            "transaction_rollback_lifecycle",
            50,
            "test_transaction_batch_rolls_back_multiple_files",
        ),
    ]
    for label, count, method in extensions:
        checks[label] = 0
        for _ in range(count):
            result = unittest.TestResult()
            AutonomyUpgradeTests(method).run(result)
            if not result.wasSuccessful() or result.testsRun != 1:
                raise AssertionError((label, result.errors, result.failures))
            checks[label] += 1
    print(
        json.dumps(
            {
                "seed": 20261104,
                "scenarios_passed": sum(checks.values()),
                "checks": checks,
                "elapsed_seconds": round(time.monotonic() - start, 3),
                "live_provider_requests": 0,
                "scope": "Scoped repair judgment, restricted adapters and execution boundaries; not model intelligence or Windows hardware",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
