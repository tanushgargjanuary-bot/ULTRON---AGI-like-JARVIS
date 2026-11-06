"""Bounded repair-loop, adversarial adapter, routing, persistence and rollback tests.

Providers here are scripted test doubles, not live model calls or quality claims.
"""

import json
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from custom_jarvis.hot_repair import ContractCase, HotRepairManager, check_candidate
from custom_jarvis.repair_adapter import AdapterError, AdapterProgram
from custom_jarvis.self_healing import (
    FailureIncident,
    GroqRepairProvider,
    RepairLoop,
    redact,
)

STRIP = 'def adapt(args):\n    result = dict(args)\n    result["path"] = str(args.get("path", "")).strip()\n    return result\n'
IDENTITY = "def adapt(args):\n    return dict(args)\n"
STRICT_STRIP = 'def adapt(args):\n    result = dict(args)\n    result["path"] = args["path"].strip()\n    return result\n'
CASES = [
    ContractCase({"path": " note.txt ", "limit": 4}, {"path": "note.txt", "limit": 4})
]


class ScriptedProvider:
    def __init__(self, answers, available=("current", "fallback")):
        self.answers = list(answers)
        self.available = set(available)
        self.calls = []
        self.discoveries = 0

    def list_models(self):
        self.discoveries += 1
        return self.available

    def propose(self, model, payload):
        self.calls.append((model, payload))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def candidate(source=STRIP):
    return {
        "action": "candidate",
        "source": source,
        "intent": "Read the requested note",
        "confidence": 0.8,
    }


class AdapterTests(unittest.TestCase):
    def test_valid_pure_adapter_preserves_unrelated_fields(self):
        args = {"path": " note.txt ", "limit": 4}
        self.assertEqual(AdapterProgram(STRIP).run(args), CASES[0].expected)
        self.assertEqual(args["path"], " note.txt ")

    def test_numeric_normalization_and_conditionals(self):
        source = 'def adapt(args):\n    result = dict(args)\n    if "max_results" in args:\n        result["max_results"] = max(1, min(100, int(args["max_results"])))\n    return result\n'
        self.assertEqual(
            AdapterProgram(source).run({"max_results": "20"}), {"max_results": 20}
        )

    def test_short_circuit_and_dictionary_constructor(self):
        source = 'def adapt(args):\n    return dict(args, path=args.get("path") or "README.md")\n'
        self.assertEqual(AdapterProgram(source).run({}), {"path": "README.md"})

    def test_malicious_and_unbounded_syntax_is_rejected(self):
        attacks = [
            "import os\ndef adapt(args): return args",
            "def adapt(args):\n    while True: pass",
            "def adapt(args): return [x for x in args]",
            "def adapt(args): return args.__class__",
            'def adapt(args): return open("secret")',
            'def adapt(args): return eval("1")',
            'def adapt(args): return __import__("os")',
            "def adapt(args): return (lambda: args)()",
            'def adapt(args): return {"x": "a" * 1000000000}',
            'def adapt(args): return {"x": 2 ** 1000000000}',
            'def adapt(args): return {"x": "{0.__class__}".format(args)}',
            "def adapt(args):\n    args = {}\n    return args",
            "@decorator\ndef adapt(args): return args",
        ]
        for source in attacks:
            with self.subTest(source=source):
                with self.assertRaises(AdapterError):
                    AdapterProgram(source).run({})

    def test_replace_expansion_is_bounded_before_allocation(self):
        source = (
            'def adapt(args):\n    return {"x": args["x"].replace("", args["y"])}\n'
        )
        with self.assertRaises(AdapterError):
            AdapterProgram(source).run({"x": "a" * 1000, "y": "b" * 1000})

    def test_cycles_are_rejected(self):
        source = 'def adapt(args):\n    result = dict(args)\n    result["self"] = result\n    return result\n'
        with self.assertRaises(AdapterError):
            AdapterProgram(source).run({})

    def test_size_and_numeric_limits(self):
        with self.assertRaises(AdapterError):
            AdapterProgram(IDENTITY + "#" * 9000)
        with self.assertRaises(AdapterError):
            AdapterProgram(IDENTITY).run({"x": "a" * 70000})
        with self.assertRaises(AdapterError):
            AdapterProgram('def adapt(args): return {"x": 1e100}').run({})
        with self.assertRaises(AdapterError):
            AdapterProgram(IDENTITY).run({"x": float("nan")})

    def test_boolean_is_not_equivalent_to_integer_contract(self):
        with self.assertRaises(AdapterError):
            check_candidate(
                'def adapt(args): return {"count": True}',
                [ContractCase({}, {"count": 1})],
            )

    def test_must_return_json_dictionary(self):
        with self.assertRaises(AdapterError):
            AdapterProgram("def adapt(args): return 4").run({})

    def test_idempotence_is_required(self):
        source = 'def adapt(args): return {"n": args["n"] + 1}'
        with self.assertRaises(AdapterError):
            check_candidate(source, [ContractCase({"n": 0}, {"n": 1})])

    def test_supported_scalar_expressions_and_dictionary_methods(self):
        source = 'def adapt(args):\n    result = args.copy()\n    result["n"] = -(-args["n"]) + 2 - 1\n    result["ok"] = 0 < args["n"] <= 10 and not False\n    result["text"] = args["text"].upper().lower().replace("a", "b", 1)\n    result["choice"] = "yes" if args["n"] > 0 else "no"\n    return result\n'
        output = AdapterProgram(source).run({"n": 2, "text": "Aab"})
        self.assertEqual(output["n"], 3)
        self.assertTrue(output["ok"])
        self.assertEqual(output["text"], "bab")
        self.assertEqual(output["choice"], "yes")

    def test_invalid_runtime_shapes_are_bounded_errors(self):
        sources = [
            "def adapt(args): return missing",
            "def adapt(args): return dict(args, n=1/0)",
            "def adapt(args): return dict(args, n=[1] + [2])",
            "def adapt(args): return {**args}",
            'def adapt(args): return {"n": -"text"}',
            'def adapt(args):\n    result = []\n    result["x"] = 1\n    return args',
            'def adapt(args): return dict(args, text="x".replace("x", "y", "bad"))',
            'def adapt(args): return dict(args, text="x".replace(1, 2))',
        ]
        for source in sources:
            with self.subTest(source=source), self.assertRaises(AdapterError):
                AdapterProgram(source).run({})

    def test_input_signature_missing_return_and_ast_budget(self):
        with self.assertRaises(AdapterError):
            AdapterProgram(IDENTITY).run([])
        with self.assertRaises(AdapterError):
            AdapterProgram("def adapt(args):\n    result = dict(args)\n").run({})
        with self.assertRaises(AdapterError):
            AdapterProgram("def adapt(args, extra): return args")
        with self.assertRaises(AdapterError):
            AdapterProgram(
                "def adapt(args):\n" + "    x = 1\n" * 100 + "    return args"
            )
        with self.assertRaises(AdapterError):
            AdapterProgram._tick([0])

    def test_explicit_legacy_key_removal_preserves_other_fields(self):
        source = 'def adapt(args):\n    result = dict(args)\n    ignored = result.pop("legacy", None)\n    return result\n'
        cases = [ContractCase({"path": "note", "legacy": True}, {"path": "note"})]
        self.assertEqual(check_candidate(source, cases), 3)

    def test_missing_contracts_fail(self):
        with self.assertRaises(AdapterError):
            check_candidate(IDENTITY, [])


class HotRepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.manager = HotRepairManager(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def activate(self, source=STRIP):
        tested = self.manager.test("read_file", source, CASES)
        return self.manager.activate(tested, CASES)

    def test_test_does_not_activate(self):
        tested = self.manager.test("read_file", STRIP, CASES)
        self.assertEqual(tested.checks, 3)
        self.assertIsNone(self.manager.current("read_file"))

    def test_activation_changes_next_call_without_restart(self):
        version = self.activate()
        output, active = self.manager.apply("read_file", CASES[0].arguments)
        self.assertEqual(output, CASES[0].expected)
        self.assertEqual(active, version)

    def test_persistence_reloads_validated_source(self):
        version = self.activate()
        restored = HotRepairManager(self.path)
        self.assertEqual(restored.apply("read_file", CASES[0].arguments)[1], version)

    def test_core_and_shell_repair_targets_are_protected(self):
        for name in (
            "execute_command",
            "write_file",
            "app.py",
            "planner",
            "../core/runtime.py",
        ):
            with self.subTest(name=name), self.assertRaises(AdapterError):
                self.manager.test(name, STRIP, CASES)

    def test_tampered_source_is_not_used(self):
        version = self.activate()
        (self.path / f"{version}.py").write_text(IDENTITY)
        with self.assertRaises(AdapterError):
            self.manager.apply("read_file", CASES[0].arguments)
        self.assertIsNone(self.manager.current("read_file"))

    def test_runtime_failure_reverts_to_previous_adapter(self):
        first = self.activate()
        second = self.activate(STRICT_STRIP)
        with patch.object(
            self.manager._programs[second],
            "run",
            side_effect=AdapterError("runtime fault"),
        ):
            with self.assertRaises(AdapterError):
                self.manager.apply("read_file", CASES[0].arguments)
        self.assertEqual(self.manager.current("read_file"), first)
        self.assertEqual(
            self.manager.apply("read_file", CASES[0].arguments)[0], CASES[0].expected
        )

    def test_corrupt_previous_version_is_disabled_not_activated(self):
        first = self.activate()
        self.activate(STRICT_STRIP)
        (self.path / f"{first}.py").write_text(IDENTITY)
        with self.assertRaises(AdapterError):
            self.manager.rollback("read_file")
        self.assertIsNone(self.manager.current("read_file"))
        self.assertIsNone(HotRepairManager(self.path).current("read_file"))

    def test_explicit_rollback_disables_first_version(self):
        self.activate()
        self.manager.rollback("read_file")
        self.assertIsNone(self.manager.current("read_file"))

    def test_stale_candidate_is_rejected(self):
        tested = self.manager.test("read_file", STRIP, CASES)
        self.activate()
        with self.assertRaises(AdapterError):
            self.manager.activate(tested, CASES)

    def test_candidate_mutation_is_rejected(self):
        tested = self.manager.test("read_file", STRIP, CASES)
        with self.assertRaises(AdapterError):
            self.manager.activate(replace(tested, source=IDENTITY), CASES)

    def test_failed_atomic_write_preserves_previous_active_state(self):
        first = self.activate()
        tested = self.manager.test("read_file", STRICT_STRIP, CASES)
        with patch(
            "custom_jarvis.hot_repair.os.replace", side_effect=OSError("disk full")
        ):
            with self.assertRaises(OSError):
                self.manager.activate(tested, CASES)
        self.assertEqual(self.manager.current("read_file"), first)
        self.assertEqual(HotRepairManager(self.path).current("read_file"), first)
        self.assertEqual(list(self.path.glob("*.tmp")), [])

    def test_malformed_pointer_never_selects_arbitrary_paths(self):
        (self.path / "active.json").write_text(
            '{"read_file":{"current":"../../evil.py"}}'
        )
        loaded = HotRepairManager(self.path)
        self.assertIsNone(loaded.current("read_file"))


class ProviderTransportTests(unittest.TestCase):
    def test_provider_discovers_ids_and_requests_json_with_deadline(self):
        client = MagicMock()
        client.models.list.return_value.data = [
            SimpleNamespace(id="current"),
            SimpleNamespace(id="fallback"),
        ]
        client.chat.completions.create.return_value.choices = [
            SimpleNamespace(message=SimpleNamespace(content=json.dumps(candidate())))
        ]
        provider = GroqRepairProvider(client)
        self.assertEqual(provider.list_models(), {"current", "fallback"})
        self.assertEqual(
            provider.propose("current", {"incident": {}})["action"], "candidate"
        )
        call = client.chat.completions.create.call_args.kwargs
        self.assertEqual(call["timeout"], 30)
        self.assertEqual(call["response_format"], {"type": "json_object"})

    def test_missing_connection_and_invalid_json_fail_closed(self):
        with self.assertRaises(ValueError):
            GroqRepairProvider(None)
        client = MagicMock()
        client.chat.completions.create.return_value.choices = [
            SimpleNamespace(message=SimpleNamespace(content="not JSON"))
        ]
        with self.assertRaises(ValueError):
            GroqRepairProvider(client).propose("current", {})

    def test_oversized_provider_response_is_rejected(self):
        client = MagicMock()
        client.chat.completions.create.return_value.choices = [
            SimpleNamespace(message=SimpleNamespace(content="x" * 20001))
        ]
        with self.assertRaises(ValueError):
            GroqRepairProvider(client).propose("current", {})


class RepairLoopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.manager = HotRepairManager(Path(self.temp.name))
        self.incident = FailureIncident.capture(
            "read_file", CASES[0].arguments, "File not found", "Read note.txt", {}
        )
        self.cancelled = threading.Event()

    def tearDown(self):
        self.temp.cleanup()

    def run_loop(self, provider, **options):
        return RepairLoop(
            self.manager, provider, "current", ["fallback"], **options
        ).run(self.incident, CASES, self.cancelled)

    def test_failed_prompt_then_fix_is_tested_not_activated(self):
        provider = ScriptedProvider([candidate(IDENTITY), candidate()])
        result = self.run_loop(provider)
        self.assertIsNotNone(result.candidate)
        self.assertEqual(
            [model for model, _ in provider.calls], ["current", "fallback"]
        )
        self.assertIn(
            "Contract 1",
            provider.calls[1][1]["previous_attempt_feedback"][0]["feedback"],
        )
        self.assertIsNone(self.manager.current("read_file"))

    def test_model_can_explicitly_select_allowed_fallback(self):
        provider = ScriptedProvider(
            [
                {
                    "action": "escalate",
                    "next_model": "fallback",
                    "reason": "Try configured coding alternative",
                },
                candidate(),
            ]
        )
        result = self.run_loop(provider)
        self.assertIsNotNone(result.candidate)
        self.assertEqual(provider.calls[1][0], "fallback")

    def test_hallucinated_model_is_never_called(self):
        provider = ScriptedProvider(
            [{"action": "escalate", "next_model": "not-real"}, candidate()]
        )
        self.run_loop(provider)
        self.assertNotIn("not-real", [model for model, _ in provider.calls])

    def test_unavailable_current_routes_only_to_available_allowlisted_model(self):
        provider = ScriptedProvider(
            [candidate()], available=["fallback", "unconfigured"]
        )
        result = self.run_loop(provider)
        self.assertIsNotNone(result.candidate)
        self.assertEqual(provider.calls[0][0], "fallback")

    def test_maximum_prompt_budget_is_enforced(self):
        provider = ScriptedProvider([candidate(IDENTITY)] * 10)
        result = self.run_loop(provider)
        self.assertIsNone(result.candidate)
        self.assertEqual(len(provider.calls), 3)

    def test_single_model_budget_prevents_escalation(self):
        provider = ScriptedProvider([candidate(IDENTITY)] * 3)
        self.run_loop(provider, max_models=1)
        self.assertEqual({model for model, _ in provider.calls}, {"current"})

    def test_cancel_before_network_discovery(self):
        provider = ScriptedProvider([])
        self.cancelled.set()
        result = self.run_loop(provider)
        self.assertIsNone(result.candidate)
        self.assertEqual(provider.discoveries, 0)

    def test_cancel_after_response_discards_candidate(self):
        provider = ScriptedProvider([candidate()])
        original = provider.propose

        def respond(*args):
            result = original(*args)
            self.cancelled.set()
            return result

        provider.propose = respond
        self.assertIsNone(self.run_loop(provider).candidate)

    def test_time_budget_discards_late_response(self):
        provider = ScriptedProvider([candidate()])
        clock = [0]
        original = provider.propose

        def respond(*args):
            result = original(*args)
            clock[0] = 100
            return result

        provider.propose = respond
        with patch(
            "custom_jarvis.self_healing.time.monotonic", side_effect=lambda: clock[0]
        ):
            self.assertIsNone(self.run_loop(provider).candidate)

    def test_provider_exception_allows_configured_fallback(self):
        provider = ScriptedProvider([RuntimeError("provider overloaded"), candidate()])
        self.assertIsNotNone(self.run_loop(provider).candidate)
        self.assertEqual(provider.calls[1][0], "fallback")

    def test_environment_failure_does_not_call_models(self):
        incident = FailureIncident.capture(
            "read_file", {}, "Permission denied", "Read a file", {}
        )
        provider = ScriptedProvider([])
        result = RepairLoop(self.manager, provider, "current", []).run(
            incident, CASES, self.cancelled
        )
        self.assertIsNone(result.candidate)
        self.assertEqual(provider.discoveries, 0)

    def test_denied_permission_cannot_trigger_self_repair(self):
        incident = FailureIncident.capture(
            "read_file", {}, "Denied", "Read a file", {"error_code": "DENIED"}
        )
        provider = ScriptedProvider([])
        result = RepairLoop(self.manager, provider, "current", []).run(
            incident, CASES, self.cancelled
        )
        self.assertIn("permission", result.reason)
        self.assertEqual(provider.calls, [])

    def test_no_available_model_fails_without_completion_calls(self):
        provider = ScriptedProvider([], available=["not_allowlisted"])
        result = self.run_loop(provider)
        self.assertIsNone(result.candidate)
        self.assertEqual(provider.calls, [])

    def test_invalid_budgets_and_oversized_context_are_rejected(self):
        provider = ScriptedProvider([])
        with self.assertRaises(ValueError):
            RepairLoop(self.manager, provider, "current", [], max_attempts=100)
        with self.assertRaises(ValueError):
            RepairLoop(self.manager, provider, "current", []).run(
                self.incident, [], self.cancelled
            )
        large = [
            ContractCase({"x": str(i) * 8000}, {"x": "y" * 8000}) for i in range(3)
        ]
        with self.assertRaises(ValueError):
            RepairLoop.payload(self.incident, large, [], [])

    def test_malformed_provider_action_and_confidence_do_not_promote_unchecked_code(
        self,
    ):
        provider = ScriptedProvider(
            [{"action": "unknown"}, dict(candidate(), confidence="not-a-number")]
        )
        result = self.run_loop(provider)
        self.assertIsNotNone(result.candidate)
        self.assertEqual(result.confidence, 0)

    def test_model_can_stop_without_patching(self):
        provider = ScriptedProvider(
            [{"action": "stop", "reason": "Needs a deeper code fix"}]
        )
        self.assertIn("deeper", self.run_loop(provider).reason)
        self.assertEqual(len(provider.calls), 1)

    def test_redaction_preserves_structure_and_masks_known_secrets(self):
        output = redact(
            {
                "password": "abc",
                "nested": {"api_key": "xyz"},
                "text": "Bearer sensitive gsk_123456789012345",
            }
        )
        self.assertNotIn("sensitive", json.dumps(output))
        self.assertEqual(output["nested"]["api_key"], "[redacted]")

    def test_100_failure_repair_scenarios_converge_within_budget(self):
        for number in range(100):
            with self.subTest(scenario=number):
                path = f" document_{number}.txt "
                cases = [ContractCase({"path": path}, {"path": path.strip()})]
                provider = ScriptedProvider(
                    [
                        candidate('def adapt(args): return {"path": "wrong"}'),
                        candidate(),
                    ]
                )
                result = RepairLoop(
                    self.manager, provider, "current", ["fallback"]
                ).run(self.incident, cases, self.cancelled)
                self.assertIsNotNone(result.candidate)
                self.assertEqual(len(provider.calls), 2)
                self.assertEqual(result.candidate.checks, 3)


if __name__ == "__main__":
    unittest.main()
