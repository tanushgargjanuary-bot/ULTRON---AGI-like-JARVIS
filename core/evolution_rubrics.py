"""Dynamic rubric generation and multi-paradigm architecture tournament for Ultron.

Allows Ultron autonomous free-will to invent problem-specific evaluation rubrics,
explore arbitrary design architectures, and self-select the winning implementation,
while giving the user sovereign override control and preserving immutable safety.
"""

from typing import Dict, List, Optional
import logging
from dataclasses import dataclass

logger = logging.getLogger("UltronEvolution")


@dataclass
class RubricCriterion:
    criterion: str
    weight: float
    measurement: str


@dataclass
class ArchitectureCandidate:
    name: str
    paradigm: str
    rationale: str
    code_proposal: str
    scores: Dict[str, float]
    composite_score: float = 0.0


class DynamicEvolutionManager:
    """Orchestrates autonomous rubric invention and multi-paradigm self-selection."""

    def __init__(self, user_directive: Optional[str] = None):
        self.user_directive = user_directive
        self.rubrics: List[RubricCriterion] = []
        self.candidates: List[ArchitectureCandidate] = []
        self.selected_winner: Optional[ArchitectureCandidate] = None

    def formulate_rubrics(self, task_goal: str, domain_context: str) -> List[RubricCriterion]:
        """Dynamically generate evaluation criteria tailored to the specific problem."""
        # Baseline balanced rubric with dynamic weighting
        if "latency" in task_goal.lower() or "speed" in task_goal.lower() or "audio" in domain_context.lower():
            self.rubrics = [
                RubricCriterion("Latency & Throughput", 0.45, "Sub-millisecond processing without frame drops"),
                RubricCriterion("Memory Footprint", 0.25, "Bounded working set growth with zero memory leaks"),
                RubricCriterion("Structural Clarity", 0.30, "Clean separation of concerns and maintainability"),
            ]
        elif "ui" in task_goal.lower() or "qt" in domain_context.lower():
            self.rubrics = [
                RubricCriterion("Thread Safety & No Stutter", 0.50, "Zero widget operations on background worker threads"),
                RubricCriterion("Visual Responsiveness", 0.30, "Immediate UI signal response under 16ms"),
                RubricCriterion("Simplicity & Modularity", 0.20, "Declarative components with minimal state"),
            ]
        else:
            self.rubrics = [
                RubricCriterion("Correctness & Robustness", 0.40, "Zero unhandled exceptions and full edge-case coverage"),
                RubricCriterion("Maintainability & Elegance", 0.30, "High readability and ease of future self-modification"),
                RubricCriterion("Resource Efficiency", 0.30, "Minimal CPU cycles and memory allocations"),
            ]
        return self.rubrics

    def evaluate_and_select_winner(self, candidates: List[ArchitectureCandidate]) -> ArchitectureCandidate:
        """Score candidates across the dynamic rubric matrix and crown the winner."""
        if not candidates:
            raise ValueError("No architecture candidates provided for evaluation.")

        # If user gave an explicit architectural directive, prioritize matching candidates
        if self.user_directive:
            target_lower = self.user_directive.lower()
            for cand in candidates:
                if target_lower in cand.paradigm.lower() or target_lower in cand.name.lower():
                    cand.composite_score = 1.0
                    self.selected_winner = cand
                    logger.info(f"User sovereign override active: Selected '{cand.name}' matching directive '{self.user_directive}'")
                    return cand

        # Autonomous evaluation against the dynamic rubric
        for cand in candidates:
            total = 0.0
            for r in self.rubrics:
                score = cand.scores.get(r.criterion, 0.5)
                total += score * r.weight
            cand.composite_score = round(total, 4)

        # Crown highest scoring candidate
        candidates.sort(key=lambda c: c.composite_score, reverse=True)
        winner = candidates[0]
        self.selected_winner = winner
        logger.info(f"Autonomous selection complete: Winner '{winner.name}' ({winner.paradigm}) scored {winner.composite_score}")
        return winner
