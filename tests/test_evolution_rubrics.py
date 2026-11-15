"""Tests for the dynamic evolution rubric generator and autonomous architecture selector."""

import unittest
from core.evolution_rubrics import DynamicEvolutionManager, ArchitectureCandidate


class TestDynamicEvolution(unittest.TestCase):

    def test_dynamic_rubrics_formulation_for_latency(self):
        manager = DynamicEvolutionManager()
        rubrics = manager.formulate_rubrics("Make audio buffer processing fast", "realtime audio streaming")
        self.assertTrue(any("Latency" in r.criterion for r in rubrics))
        self.assertEqual(sum(r.weight for r in rubrics), 1.0)

    def test_dynamic_rubrics_formulation_for_ui(self):
        manager = DynamicEvolutionManager()
        rubrics = manager.formulate_rubrics("Add a new HUD widget", "qt gui interface")
        self.assertTrue(any("Thread Safety" in r.criterion for r in rubrics))
        self.assertEqual(sum(r.weight for r in rubrics), 1.0)

    def test_autonomous_winner_selection(self):
        manager = DynamicEvolutionManager()
        manager.formulate_rubrics("General optimization", "core backend")

        candidates = [
            ArchitectureCandidate(
                name="Actor Model",
                paradigm="actor-based",
                rationale="Independent isolated message loops",
                code_proposal="# actor code",
                scores={"Correctness & Robustness": 0.95, "Maintainability & Elegance": 0.90, "Resource Efficiency": 0.85}
            ),
            ArchitectureCandidate(
                name="Monolithic Sync",
                paradigm="synchronous",
                rationale="Direct blocking calls",
                code_proposal="# sync code",
                scores={"Correctness & Robustness": 0.50, "Maintainability & Elegance": 0.40, "Resource Efficiency": 0.30}
            )
        ]
        winner = manager.evaluate_and_select_winner(candidates)
        self.assertEqual(winner.name, "Actor Model")
        self.assertGreater(winner.composite_score, 0.85)

    def test_user_sovereign_override(self):
        manager = DynamicEvolutionManager(user_directive="pipeline")
        manager.formulate_rubrics("Improve data movement", "io processing")

        candidates = [
            ArchitectureCandidate(
                name="PubSub Broker",
                paradigm="event-broker",
                rationale="PubSub topology",
                code_proposal="",
                scores={"Correctness & Robustness": 0.95}
            ),
            ArchitectureCandidate(
                name="Zero-Copy Pipeline",
                paradigm="pipeline",
                rationale="Direct streaming pipeline",
                code_proposal="",
                scores={"Correctness & Robustness": 0.80}
            )
        ]
        winner = manager.evaluate_and_select_winner(candidates)
        # User specified "pipeline", so user choice takes priority
        self.assertEqual(winner.name, "Zero-Copy Pipeline")


if __name__ == "__main__":
    unittest.main()
