"""Targeted seeded mutation checks; not a comprehensive mutation score.

Copies source into isolated temporary directories; never edits the running tree.
Run: python scripts/check_mutations.py
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MUTATIONS = [
    (
        "workspace_gate",
        "custom_jarvis/repair_judgment.py",
        [('if scope.get("context_key") != context_key:', "if False:")],
        "test_cross_workspace_abstains",
    ),
    (
        "expiry_gate",
        "custom_jarvis/repair_judgment.py",
        [("if (time.time() if now is None else now) >= expiry:", "if False:")],
        "test_expired_scope_abstains",
    ),
    (
        "quarantine_gate",
        "custom_jarvis/repair_judgment.py",
        [('if entry.get("quarantined"):', "if False:")],
        "test_quarantine_survives_restart",
    ),
    (
        "no_change_gate",
        "custom_jarvis/repair_judgment.py",
        [("if approved[key] == key:", "if False:")],
        "test_unchanged_contract_abstains",
    ),
    (
        "unreviewed_input_gate",
        "custom_jarvis/repair_judgment.py",
        [
            ("if not isinstance(approved, dict) or key not in approved:", "if False:"),
            ("if approved[key] == key:", "if approved.get(key) == key:"),
        ],
        "test_unreviewed_input_never_runs_adapter",
    ),
    (
        "schema_gate",
        "custom_jarvis/repair_judgment.py",
        [
            (
                "def validate_arguments(arguments: dict, schema: dict | None) -> None:",
                "def validate_arguments(arguments: dict, schema: dict | None) -> None:\n    return",
            )
        ],
        "test_schema_invalid_expected_arguments_rejected",
    ),
    (
        "literal_path_gate",
        "custom_jarvis/addon_runtime.py",
        [("if exists:", "if False:")],
        "test_existing_literal_filename_is_not_redirected",
    ),
    (
        "version_rollback_gate",
        "custom_jarvis/hot_repair.py",
        [
            (
                'if old is None or (\n                expected_version is not None and old["current"] != expected_version\n            ):',
                "if old is None:",
            )
        ],
        "test_old_failure_cannot_retire_newer_version",
    ),
    (
        "index_error_boundary",
        "custom_jarvis/repair_adapter.py",
        [("            LookupError,", "            KeyError,")],
        "test_runtime_index_error_is_normalized",
    ),
    (
        "contract_freeze_gate",
        "custom_jarvis/hot_repair.py",
        [("if self.contracts_hash(cases) != candidate.contracts_sha256:", "if False:")],
        "test_changed_contracts_require_retesting",
    ),
]


MUTATIONS += [
    (
        "circuit_breaker_gate",
        "custom_jarvis/self_healing.py",
        [("if self.circuit_breaker is not None:", "if False:")],
        "test_autonomy_upgrades.AutonomyUpgradeTests.test_circuit_breaker_blocks_repair_loop",
    ),
    (
        "fingerprint_memory_gate",
        "custom_jarvis/self_healing.py",
        [("if self.knowledge is not None and incident.fingerprint:", "if False:")],
        "test_autonomy_upgrades.AutonomyUpgradeTests.test_fingerprint_memory_reuses_validated_adapter",
    ),
    (
        "state_drift_gate",
        "custom_jarvis/addon_runtime.py",
        [
            (
                'if name == "write_file" and not self.drift_guard.unchanged(Path(args["path"])):',
                "if False:",
            )
        ],
        "test_autonomy_upgrades.AutonomyUpgradeTests.test_state_drift_blocks_clobbering_write",
    ),
    (
        "repair_budget_gate",
        "custom_jarvis/autonomy_governor.py",
        [
            (
                'and self.usage["repair_calls"] >= self.limits.max_repair_calls',
                "and False",
            )
        ],
        "test_autonomy_upgrades.AutonomyUpgradeTests.test_budget_governor_enforces_repair_limit",
    ),
    (
        "transaction_lifo_gate",
        "custom_jarvis/evidence.py",
        [("for backup_id in reversed(ids):", "for backup_id in ids:")],
        "test_autonomy_upgrades.AutonomyUpgradeTests.test_transaction_batch_rolls_back_multiple_files",
    ),
]


def run_test(directory, names):
    environment = dict(
        os.environ,
        PYTHONPATH=os.pathsep.join((str(directory), str(directory / "tests"))),
    )
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            *[
                name if "." in name else "test_repair_judgment.JudgmentTests." + name
                for name in names
            ],
        ],
        check=False,
        cwd=directory,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )


def main():
    baseline = run_test(ROOT, [row[3] for row in MUTATIONS])
    if baseline.returncode:
        raise RuntimeError(
            "Baseline must pass before seeding defects:\n" + baseline.stderr
        )
    results = []
    for name, filename, edits, test in MUTATIONS:
        with tempfile.TemporaryDirectory(
            prefix="jarvis-judgment-mutation-"
        ) as temporary:
            directory = Path(temporary) / "app"
            shutil.copytree(
                ROOT,
                directory,
                ignore=shutil.ignore_patterns(
                    "__pycache__", ".git", ".coverage", ".hypothesis", ".ruff_cache"
                ),
            )
            target = directory / filename
            text = target.read_text(encoding="utf-8")
            for old, new in edits:
                if text.count(old) != 1:
                    raise RuntimeError(f"Mutation {name}: source anchor changed")
                text = text.replace(old, new, 1)
            ast.parse(text)
            target.write_text(text, encoding="utf-8")
            result = run_test(directory, [test])
            output = result.stdout + result.stderr
            detected = (
                result.returncode != 0
                and test.split(".")[-1] in output
                and "Ran 1 test" in output
            )
            results.append({"mutation": name, "test": test, "detected": detected})
    print(
        json.dumps(
            {
                "baseline_passed": True,
                "seeded_mutations": len(results),
                "detected": sum(row["detected"] for row in results),
                "results": results,
                "live_provider_requests": 0,
                "scope": "Fifteen deliberately seeded gate defects; not comprehensive mutation coverage",
            },
            indent=2,
        )
    )
    return 0 if all(row["detected"] for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
