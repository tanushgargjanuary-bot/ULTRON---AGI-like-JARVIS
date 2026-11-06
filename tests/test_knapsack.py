"""tests/test_knapsack.py — the budget allocator, checked against brute force.

THE ONE TEST THAT MATTERS
    `test_greedy_is_within_the_proved_ratio` compares the approximation against
    an exhaustive search on small random instances. The 2-approximation is a
    proven bound, not a hope, and the test is what stops a future "small
    optimisation" from quietly turning it into an unbounded heuristic.
"""

from __future__ import annotations

import itertools
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.knapsack import Item, solve, solve_exact, solve_greedy


def brute_force(items, capacity):
    """Exhaustive optimum: correct by definition, and only usable on tiny inputs."""
    best = (0.0, [])
    for size in range(len(items) + 1):
        for combo in itertools.combinations(items, size):
            weight = sum(item.weight for item in combo)
            if weight <= capacity:
                value = sum(item.value for item in combo)
                if value > best[0]:
                    best = (value, list(combo))
    return best


def make_items(count, rng, max_weight=12):
    return [
        Item(name=f"i{n}", value=round(rng.uniform(0.1, 10.0), 3),
             weight=rng.randint(0, max_weight))
        for n in range(count)
    ]


class ExactTests(unittest.TestCase):
    def test_matches_brute_force_on_random_instances(self):
        rng = random.Random(20261106)
        for trial in range(40):
            items = make_items(rng.randint(1, 8), rng)
            capacity = rng.randint(0, 30)
            with self.subTest(trial=trial):
                result = solve_exact(items, capacity)
                best_value, _ = brute_force(items, capacity)
                self.assertAlmostEqual(result.value, best_value, places=4)
                self.assertLessEqual(result.weight, capacity)
                self.assertTrue(result.exact)

    def test_it_actually_picks_the_right_items(self):
        items = [Item("cheap_and_dull", 1.0, 10), Item("dense", 9.0, 4), Item("dense2", 8.0, 4)]
        result = solve_exact(items, 8)
        self.assertEqual(sorted(item.name for item in result.chosen), ["dense", "dense2"])
        self.assertEqual(result.weight, 8)

    def test_zero_capacity_and_empty(self):
        self.assertEqual(solve_exact([], 10).chosen, [])
        self.assertEqual(solve_exact([Item("x", 5.0, 3)], 0).chosen, [])

    def test_free_items_are_always_taken(self):
        items = [Item("free", 2.0, 0), Item("paid", 1.0, 5)]
        result = solve_exact(items, 5)
        self.assertEqual({item.name for item in result.chosen}, {"free", "paid"})

    def test_items_that_do_not_fit_are_not_taken(self):
        result = solve_exact([Item("huge", 100.0, 999)], 10)
        self.assertEqual(result.chosen, [])
        self.assertLessEqual(result.weight, 10)


class GreedyTests(unittest.TestCase):
    def test_greedy_takes_the_break_item_when_it_is_better(self):
        """The case a bare greedy prefix gets wrong: one heavy item at the front
        blocks everything else, and the ratio sort puts it first."""
        items = [Item("hog", 10.0, 10), Item("a", 3.0, 5), Item("b", 3.0, 5)]
        greedy = solve_greedy(items, 10)
        self.assertEqual(greedy.value, 10.0)
        self.assertEqual([item.name for item in greedy.chosen], ["hog"])

    def test_greedy_is_within_the_proved_ratio(self):
        rng = random.Random(4242)
        for trial in range(30):
            items = make_items(rng.randint(2, 7), rng)
            capacity = rng.randint(1, 20)
            optimal, _ = brute_force(items, capacity)
            result = solve_greedy(items, capacity)
            with self.subTest(trial=trial):
                self.assertLessEqual(result.weight, capacity)
                if optimal > 0:
                    # max(greedy prefix, break item) >= OPT / 2
                    self.assertGreaterEqual(result.value + 1e-9, optimal / 2.0)


class DispatchTests(unittest.TestCase):
    def test_exact_path_is_used_when_affordable(self):
        result = solve([Item("x", 5.0, 2)], 10)
        self.assertTrue(result.exact)
        self.assertEqual(result.method, "exact")

    def test_greedy_path_is_used_when_the_table_is_too_big(self):
        items = [Item(f"i{n}", 1.0, 3) for n in range(1000)]
        result = solve(items, 5000, exact_cells=10_000)
        self.assertFalse(result.exact)
        self.assertLessEqual(result.weight, 5000)

    def test_solve_agrees_with_exact_when_it_takes_that_path(self):
        rng = random.Random(7)
        items = make_items(6, rng)
        self.assertEqual(
            round(solve(items, 15).value, 6), round(solve_exact(items, 15).value, 6)
        )

    def test_degenerate_inputs(self):
        self.assertEqual(solve([], 10).chosen, [])
        self.assertEqual(solve([Item("x", 5.0, 1)], 0).chosen, [])
        # Negative value would let the optimiser "pay" for capacity it does not have.
        self.assertEqual(solve([Item("bad", -5.0, 1)], 10).chosen, [])

    def test_a_realistic_context_budget(self):
        """40 candidate blocks, 1200 tokens: the shape the memory formatter has."""
        rng = random.Random(99)
        items = [Item(f"block{n}", rng.uniform(0.1, 1.0), rng.randint(40, 400))
                 for n in range(40)]
        result = solve(items, 1200)
        self.assertLessEqual(result.weight, 1200)
        self.assertGreater(len(result.chosen), 3)
        self.assertGreater(result.value, 0)


if __name__ == "__main__":
    unittest.main()
