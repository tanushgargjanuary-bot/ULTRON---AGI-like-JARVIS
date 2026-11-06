"""test_suite_algorithms.py — one suite file for 8 areas.

Each section below was its own test module and is kept whole, with its
header, its helpers and its tests. They were combined because the project
had sixty-five test modules of one or two hundred lines each, and a file
count that size hides the structure instead of showing it. Nothing was
removed; a name that appeared in two sections was given a suffix.

Sections:
  * test_bandit.py
  * test_knapsack.py
  * test_branchbound.py
  * test_trie.py
  * test_numerics.py
  * test_verifiers.py
  * test_reputation.py
  * test_inventory_data.py
"""

from __future__ import annotations
import random
import sys
import unittest
from pathlib import Path
from core.bandit import UCB1, Contextual, Thompson
import itertools
from core.knapsack import Item, solve, solve_exact, solve_greedy
from core.branchbound import Candidate, decide
from core.trie import Trie
import math
from core import numerics
import subprocess
import re
from core.reputation import Record, Reputation
import contextlib
import importlib.util
import io
import json
import sqlite3
import tempfile



# ══════════════════════════════════════════════════════════════════════════
# from test_bandit.py
# ══════════════════════════════════════════════════════════════════════════
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.bandit import UCB1, Contextual, Thompson


def play(bandit, truths, rng, rounds=400, blocked=()):
    """Simulate `rounds` interactions with known success probabilities."""
    for _ in range(rounds):
        arm = bandit.choose(blocked)
        reward = 1.0 if rng.random() < truths[arm] else 0.0
        bandit.update(arm, reward)


class UCB1Tests(unittest.TestCase):
    def test_every_arm_is_tried_once_first(self):
        # Choose-then-update, because an arm that never gets feedback correctly
        # keeps being chosen: the learner cannot learn about it otherwise.
        band = UCB1(["a", "b", "c"])
        first = []
        for _ in range(3):
            arm = band.choose()
            first.append(arm)
            band.update(arm, 0.5)
        self.assertEqual(sorted(first), ["a", "b", "c"])

    def test_it_concentrates_on_the_best_arm(self):
        rng = random.Random(11)
        truths = {"good": 0.9, "ok": 0.5, "bad": 0.1}
        band = UCB1(truths)
        play(band, truths, rng, rounds=600)
        stats = band.stats()
        self.assertGreater(stats["good"]["pulls"], stats["bad"]["pulls"] * 3)

    def test_a_blocked_arm_is_never_chosen(self):
        truths = {"a": 0.9, "b": 0.1}
        band = UCB1(truths)
        for _ in range(200):
            arm = band.choose(blocked={"b"})
            self.assertEqual(arm, "a")
            band.update(arm, 1.0)

    def test_all_blocked_returns_none(self):
        band = UCB1(["a", "b"])
        self.assertIsNone(band.choose(blocked={"a", "b"}))

    def test_scores_put_untried_arms_first(self):
        band = UCB1(["a", "b"])
        band.update("a", 1.0)
        scores = dict(band.scores())
        self.assertEqual(scores["b"], float("inf"))
        self.assertGreater(scores["a"], 0.0)

    def test_rewards_are_clamped(self):
        band = UCB1(["a"])
        band.update("a", 99.0)
        self.assertEqual(band.stats()["a"]["mean"], 1.0)
        band.update("a", -5.0)
        self.assertLessEqual(band.stats()["a"]["mean"], 1.0)


class ThompsonTests(unittest.TestCase):
    def test_untried_arms_first(self):
        band = Thompson(["a", "b"], rng=random.Random(1))
        seen = set()
        for _ in range(4):
            arm = band.choose()
            seen.add(arm)
            band.update(arm, 0.5)
        self.assertEqual(seen, {"a", "b"})

    def test_it_concentrates_on_the_best_arm(self):
        rng = random.Random(2026)
        truths = {"good": 0.85, "ok": 0.5, "bad": 0.15}
        band = Thompson(truths, rng=rng)
        play(band, truths, rng, rounds=600)
        stats = band.stats()
        self.assertGreater(stats["good"]["pulls"], stats["bad"]["pulls"] * 3)
        self.assertGreater(stats["good"]["mean"], 0.7)

    def test_posterior_moves_in_the_right_direction(self):
        band = Thompson(["a"], rng=random.Random(3))
        band.update("a", 0.0)
        alpha_zero, beta_zero = band.posterior("a")
        self.assertEqual(beta_zero, 2.0)
        band.update("a", 1.0)
        alpha_one, _ = band.posterior("a")
        self.assertGreater(alpha_one, alpha_zero)

    def test_asymmetric_prior_is_respected(self):
        # A provider believed fast-but-flaky starts from that belief.
        band = Thompson(["a", "b"], prior=(1.0, 4.0), rng=random.Random(9))
        for _ in range(2):
            band.choose()
        alpha, beta = band.posterior("a")
        self.assertLess(alpha / (alpha + beta), 0.5)

    def test_blocked_arms_are_excluded(self):
        band = Thompson(["a", "b"], rng=random.Random(4))
        for _ in range(20):
            arm = band.choose(blocked={"b"})
            self.assertEqual(arm, "a")
            band.update(arm, 0.5)

    def test_determinism_with_the_same_seed(self):
        def run():
            rng = random.Random(77)
            band = Thompson(["a", "b", "c"], rng=rng)
            truths = {"a": 0.6, "b": 0.4, "c": 0.5}
            play(band, truths, rng, rounds=100)
            return band.stats()

        self.assertEqual(run(), run())


class ContextualTests(unittest.TestCase):
    def test_contexts_learn_separately(self):
        rng = random.Random(13)
        band = Contextual(lambda arms: Thompson(arms, rng=rng))
        # A is better for "chat", B is better for "code".
        truths = {"chat": {"A": 0.9, "B": 0.1}, "code": {"A": 0.1, "B": 0.9}}
        for _ in range(400):
            for context, table in truths.items():
                arm = band.choose(context, arms=list(table))
                reward = 1.0 if rng.random() < table[arm] else 0.0
                band.update(context, arm, reward)

        stats = band.stats()
        self.assertGreater(stats["chat"]["A"]["pulls"], stats["chat"]["B"]["pulls"])
        self.assertGreater(stats["code"]["B"]["pulls"], stats["code"]["A"]["pulls"])

    def test_new_arms_can_join_a_live_context(self):
        band = Contextual(lambda arms: Thompson(arms, rng=random.Random(2)))
        band.choose("chat", arms=["A"])
        band.bandit("chat", arms=["B"])
        self.assertEqual(sorted(band.bandit("chat").names()), ["A", "B"])


class BookkeepingTests(unittest.TestCase):
    def test_add_and_forget(self):
        band = Thompson(["a"])
        band.add_arm("b")
        self.assertEqual(sorted(band.names()), ["a", "b"])
        band.forget("b")
        self.assertEqual(band.names(), ["a"])

    def test_updating_an_unknown_arm_creates_it_rather_than_crashing(self):
        band = Thompson([])
        band.update("surprise", 1.0)
        self.assertEqual(band.stats()["surprise"]["pulls"], 1)

    def test_empty_bandit_chooses_nothing(self):
        self.assertIsNone(Thompson([]).choose())
        self.assertIsNone(UCB1([]).choose())

    def test_len(self):
        self.assertEqual(len(UCB1(["a", "b"])), 2)


# ══════════════════════════════════════════════════════════════════════════
# from test_knapsack.py
# ══════════════════════════════════════════════════════════════════════════
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


# ══════════════════════════════════════════════════════════════════════════
# from test_branchbound.py
# ══════════════════════════════════════════════════════════════════════════
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.branchbound import Candidate, decide


class DecisionTests(unittest.TestCase):
    def test_clear_winner_acts(self):
        result = decide([Candidate("WhatsApp", 0.93), Candidate("Telegram", 0.41)])
        self.assertFalse(result.ask)
        self.assertEqual(result.chosen.label, "WhatsApp")
        # A rival that cannot reach the threshold is pruned before it can be a
        # "runner-up": 0.41 is not a serious alternative to 0.93, and reporting
        # it as one would make every decision look contested.
        self.assertIsNone(result.runner_up)
        self.assertAlmostEqual(result.margin, 0.93, places=6)

    def test_nothing_clears_the_threshold_asks(self):
        result = decide([Candidate("WhatsApp", 0.62), Candidate("Telegram", 0.30)])
        self.assertTrue(result.ask)
        self.assertIsNone(result.chosen)
        self.assertIn("threshold", result.reason)

    def test_a_narrow_lead_asks_even_above_the_threshold(self):
        result = decide([Candidate("Chrome", 0.74), Candidate("Chrome Remote Desktop", 0.71)])
        self.assertTrue(result.ask)
        self.assertIn("close", result.reason)
        self.assertEqual(result.question(), "Did you mean Chrome, or Chrome Remote Desktop?")

    def test_the_question_is_empty_when_not_asking(self):
        result = decide([Candidate("Notepad", 0.99)])
        self.assertEqual(result.question(), "")

    def test_no_candidates_is_a_question_not_a_crash(self):
        result = decide([])
        self.assertTrue(result.ask)
        self.assertIsNone(result.chosen)
        self.assertEqual(result.question(), "")

    def test_a_single_strong_candidate_acts_without_a_runner_up(self):
        result = decide([Candidate("Calculator", 0.95)])
        self.assertFalse(result.ask)
        self.assertIsNone(result.runner_up)
        self.assertEqual(result.margin, 0.95)


class PruningTests(unittest.TestCase):
    def _tree(self):
        # "chrome" -> {Chrome 0.88, Chrome Remote Desktop 0.31}
        # "chromium" -> 0.22, "chromecast" -> 0.12
        children = [Candidate("Chrome", 0.88), Candidate("Chrome Remote Desktop", 0.31)]
        return [
            Candidate("chrome", 0.88, children=children),
            Candidate("chromium", 0.22),
            Candidate("chromecast", 0.12),
        ]

    def test_hopeless_branches_are_pruned(self):
        result = decide(self._tree(), threshold=0.70)
        # chromium and chromecast cannot reach 0.70 and are never expanded.
        self.assertGreaterEqual(result.pruned, 2)
        self.assertFalse(result.ask)

    def test_a_tighter_bound_prunes_more(self):
        loose = decide(self._tree(), threshold=0.70)
        tight = decide(
            self._tree(),
            threshold=0.70,
            optimism=lambda node: node.score,      # no credit for children
        )
        self.assertGreaterEqual(tight.pruned, loose.pruned)

    def test_children_are_reachable_when_the_parent_is_weak(self):
        parent = Candidate("chrome", 0.40, children=[Candidate("Chrome", 0.91)])
        result = decide([parent])
        self.assertFalse(result.ask)
        self.assertEqual(result.chosen.label, "Chrome")

    def test_search_is_bounded(self):
        """A pathological expander must not hang the keystroke path."""
        wide = [
            Candidate(f"c{i}", 0.75, children=[Candidate(f"c{i}.{j}", 0.76) for j in range(50)])
            for i in range(50)
        ]
        result = decide(wide, max_nodes=25)
        self.assertLessEqual(result.explored, 25)
        self.assertTrue(result.ask or result.chosen is not None)

    def test_explored_counts_are_reported(self):
        # 3 roots + the 2 children of the only branch that survived its bound.
        result = decide(self._tree())
        self.assertEqual(result.explored, 5)
        self.assertEqual(result.pruned, 3)          # chromium, chromecast, CRD
        self.assertFalse(result.ask)


class ThresholdDisciplineTests(unittest.TestCase):
    def test_matching_the_specified_one_rule(self):
        """The 0.70 lower bound is the project's rule; this verifies the module
        implements exactly it rather than a nearby number."""
        self.assertTrue(decide([Candidate("x", 0.699)], threshold=0.70).ask)
        self.assertFalse(decide([Candidate("x", 0.701)], threshold=0.70).ask)

    def test_scores_are_clamped_into_range(self):
        self.assertEqual(Candidate("x", 5.0).score, 1.0)
        self.assertEqual(Candidate("x", -3.0).score, 0.0)

    def test_payload_survives_the_decision(self):
        result = decide([Candidate("Notepad", 0.99, payload={"app": "notepad.exe"})])
        self.assertEqual(result.chosen.payload, {"app": "notepad.exe"})


# ══════════════════════════════════════════════════════════════════════════
# from test_trie.py
# ══════════════════════════════════════════════════════════════════════════
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.trie import Trie


class BasicsTests(unittest.TestCase):
    def test_insert_and_contains(self):
        trie = Trie(["chrome", "chromium", "chromecast"])
        self.assertEqual(len(trie), 3)
        self.assertIn("chrome", trie)
        self.assertNotIn("chrom", trie)
        self.assertNotIn("chromium browser", trie)

    def test_reinsert_keeps_the_highest_weight(self):
        trie = Trie()
        trie.insert("whatsapp", 1.0)
        trie.insert("whatsapp", 9.0)
        trie.insert("whatsapp", 2.0)
        self.assertEqual(len(trie), 1)
        self.assertEqual(dict(trie.complete("what"))["whatsapp"], 9.0)

    def test_empty_key_is_ignored(self):
        trie = Trie(["", "x"])
        self.assertEqual(len(trie), 1)

    def test_duplicate_keys_count_once(self):
        trie = Trie(["a", "a", "a"])
        self.assertEqual(len(trie), 1)


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.trie = Trie([("chrome", 3.0), ("chromium", 1.0), ("chromecast", 2.0), ("firefox", 5.0)])

    def test_prefix_returns_the_subtree(self):
        self.assertEqual(
            [key for key, _ in self.trie.complete("chrom")],
            ["chrome", "chromecast", "chromium"],
        )

    def test_ordering_is_weight_then_alphabet(self):
        results = self.trie.complete("chrom")
        self.assertEqual(results[0][0], "chrome")          # 3.0
        self.assertEqual(results[1][0], "chromecast")      # 2.0
        self.assertEqual(results[2][0], "chromium")        # 1.0

    def test_limit_bounds_the_work_not_just_the_output(self):
        self.assertEqual(len(self.trie.complete("chrom", limit=2)), 2)
        self.assertEqual(self.trie.complete("chrom", limit=0), [])

    def test_unknown_prefix_is_empty(self):
        self.assertEqual(self.trie.complete("zzz"), [])
        self.assertEqual(self.trie.complete(""), sorted(
            ((key, weight) for key, weight in self.trie.complete("")),
            key=lambda pair: (-pair[1], pair[0]),
        ))

    def test_longest_prefix(self):
        trie = Trie(["chro", "chrome", "chromium"])
        self.assertEqual(trie.longest_prefix("chromex"), "chrome")
        self.assertEqual(trie.longest_prefix("chromi"), "chro")   # chromium is not a prefix
        self.assertEqual(trie.longest_prefix("zzz"), "")

    def test_keys_enumerates_everything_once(self):
        self.assertEqual(sorted(self.trie.keys()), ["chrome", "chromecast", "chromium", "firefox"])


class RobustnessTests(unittest.TestCase):
    def test_deep_keys_do_not_recurse(self):
        """A recursive traversal takes the app down on one long path."""
        deep = "p/" * 4000 + "file.txt"
        trie = Trie([deep])
        self.assertIn(deep, trie)
        self.assertEqual(trie.complete("p/" * 3999, limit=1)[0][0], deep)

    def test_unicode_keys(self):
        trie = Trie(["café", "cafe"])
        self.assertEqual({key for key, _ in trie.complete("caf")}, {"café", "cafe"})

    def test_scale(self):
        keys = [f"tool_{i:05d}" for i in range(5000)]
        trie = Trie(keys)
        self.assertEqual(len(trie), 5000)
        self.assertEqual(len(trie.complete("tool_0499", limit=10)), 10)


# ══════════════════════════════════════════════════════════════════════════
# from test_numerics.py
# ══════════════════════════════════════════════════════════════════════════
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import numerics


class IncompleteBetaTests(unittest.TestCase):
    def test_uniform_is_the_identity(self):
        # Beta(1,1) is uniform, so its CDF is x.
        for x in (0.0, 0.01, 0.25, 0.5, 0.7, 0.999, 1.0):
            with self.subTest(x=x):
                self.assertAlmostEqual(numerics.betai(1, 1, x), x, places=9)

    def test_closed_form_for_beta_2_3(self):
        # Beta(2,3): CDF(x) = 12(x^2/2 - 2x^3/3 + x^4/4).
        def closed(x):
            return 12.0 * (x * x / 2 - 2 * x ** 3 / 3 + x ** 4 / 4)

        for x in (0.1, 0.25, 0.5, 0.75, 0.9):
            with self.subTest(x=x):
                self.assertAlmostEqual(numerics.betai(2, 3, x), closed(x), places=9)

    def test_symmetry_identity(self):
        # I_x(a,b) = 1 - I_{1-x}(b,a)
        for a, b, x in ((2, 5, 0.3), (7, 2, 0.6), (1, 3, 0.45), (12, 12, 0.5)):
            with self.subTest(a=a, b=b, x=x):
                self.assertAlmostEqual(
                    numerics.betai(a, b, x), 1.0 - numerics.betai(b, a, 1.0 - x), places=9
                )

    def test_boundaries_and_bad_input(self):
        self.assertEqual(numerics.betai(2, 3, 0.0), 0.0)
        self.assertEqual(numerics.betai(2, 3, 1.0), 1.0)
        with self.assertRaises(ValueError):
            numerics.betai(0, 1, 0.5)

    def test_monotone_in_x(self):
        previous = -1.0
        for step in range(1, 100):
            value = numerics.betai(3, 4, step / 100)
            self.assertGreaterEqual(value, previous)
            previous = value


class QuantileTests(unittest.TestCase):
    def test_round_trip(self):
        for a, b in ((1, 1), (2, 3), (5, 5), (10, 2), (1, 40)):
            for p in (0.01, 0.05, 0.5, 0.9):
                with self.subTest(a=a, b=b, p=p):
                    x = numerics.beta_quantile(p, a, b)
                    self.assertAlmostEqual(numerics.betai(a, b, x), p, places=7)

    def test_small_samples_are_not_confident(self):
        """The reason this file exists: 2/2 must not read as 100 % certain."""
        self.assertLess(numerics.beta_quantile(0.05, 3.0, 1.0), 0.45)   # 2 successes
        self.assertGreater(numerics.beta_quantile(0.05, 41.0, 3.0), 0.83)  # 40/42
        self.assertGreater(
            numerics.beta_quantile(0.05, 41.0, 3.0),
            numerics.beta_quantile(0.05, 3.0, 1.0),
        )

    def test_bad_probability_is_refused(self):
        with self.assertRaises(ValueError):
            numerics.beta_quantile(0.0, 2, 2)
        with self.assertRaises(ValueError):
            numerics.beta_quantile(1.0, 2, 2)


class SummaryTests(unittest.TestCase):
    def test_mean_and_variance(self):
        self.assertAlmostEqual(numerics.beta_mean(2, 3), 0.4)
        self.assertAlmostEqual(numerics.beta_var(2, 3), (6) / (25 * 6), places=12)

    def test_wilson_lower_matches_known_values(self):
        # Published value for 3/3 at 95 %: 0.4385
        self.assertAlmostEqual(numerics.wilson_lower(3, 3), 0.4385, places=3)
        # 0/0 says nothing at all.
        self.assertEqual(numerics.wilson_lower(0, 0), 0.0)
        # A perfect record over more trials is more convincing than over fewer.
        self.assertGreater(numerics.wilson_lower(100, 100), numerics.wilson_lower(3, 3))
        # And it never exceeds the observed rate.
        self.assertLessEqual(numerics.wilson_lower(7, 10), 0.7 + 1e-12)

    def test_wilson_is_sane_at_the_edges(self):
        self.assertEqual(numerics.wilson_lower(0, 10), 0.0)
        self.assertTrue(math.isfinite(numerics.wilson_lower(10, 10)))


# ══════════════════════════════════════════════════════════════════════════
# from test_verifiers.py
# ══════════════════════════════════════════════════════════════════════════
import subprocess
import sys
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

VERIFIERS = [
    "verify_windows.py",
    "verify_display.py",
    "verify_capture.py",
    "verify_audio.py",
    "verify_browser.py",
    "verify_all.py",
]


class VerifierTests(unittest.TestCase):
    def test_every_verifier_exists(self):
        for name in VERIFIERS:
            with self.subTest(script=name):
                self.assertTrue((SCRIPTS / name).is_file(), f"{name} is missing")

    def test_every_verifier_answers_help(self):
        for name in VERIFIERS:
            with self.subTest(script=name):
                done = subprocess.run(
                    [sys.executable, str(SCRIPTS / name), "--help"],
                    capture_output=True, text=True, timeout=180, cwd=str(ROOT),
                )
                self.assertEqual(done.returncode, 0, done.stderr[-800:])
                self.assertIn("usage", done.stdout.lower())

    def test_runner_knows_each_verifier(self):
        module = self._runner()
        wired = {entry[1] for entry in module.VERIFIERS}
        for name in VERIFIERS:
            if name == "verify_all.py":
                continue
            with self.subTest(script=name):
                self.assertIn(name, wired, f"{name} is never run by verify_all.py")
                self.assertTrue((SCRIPTS / name).is_file())

    def test_runner_reports_skip_as_not_a_failure(self):
        """A SKIP must never be counted as a failure — the whole point."""
        module = self._runner()
        self.assertEqual(module.verdict_for({"passed": 3, "failed": 0, "skipped": 0}),
                         "WORKS")
        self.assertEqual(module.verdict_for({"passed": 2, "failed": 0, "skipped": 14}),
                         "PARTLY TESTED")
        self.assertEqual(module.verdict_for({"passed": 0, "failed": 0, "skipped": 5}),
                         "NOT TESTED HERE")
        self.assertEqual(module.verdict_for({"passed": 1, "failed": 1, "skipped": 0}),
                         "BROKEN")

    @staticmethod
    def _runner():
        import importlib.util

        spec = importlib.util.spec_from_file_location("verify_all_mod",
                                                     SCRIPTS / "verify_all.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module




class WorkflowArguments(unittest.TestCase):
    """The CI file and the scripts must agree, or the first push is red.

    Both defects found on the first real CI run were of this shape: the workflow
    passed a flag the script did not have (`--json` to a script that takes
    `--report`), and asked a script to write into a folder that does not exist on
    a fresh clone. Neither could be caught here by running the script.
    """

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.workflow = (self.root / ".github" / "workflows" / "verify.yml").read_text(encoding="utf-8")

    def test_every_flag_the_workflow_passes_exists_in_its_script(self):
        calls = re.findall(r"python scripts/([\w]+\.py)([^\n|]*)", self.workflow)
        self.assertTrue(calls, "no script call found in the workflow")
        for script, rest in calls:
            for flag in re.findall(r"--[a-z][\w-]*", rest):
                source = (self.root / "scripts" / script).read_text(encoding="utf-8")
                self.assertIn(f'"{flag}"', source,
                              f"{script} is called with {flag}, which its parser does not declare")

    def test_the_workflow_runs_the_scripts_that_exist(self):
        for script in re.findall(r"python scripts/([\w]+\.py)", self.workflow):
            self.assertTrue((self.root / "scripts" / script).exists(), script)


class SkipVersusFail(unittest.TestCase):
    """A missing device is "not tested here"; a present one that fails is broken.

    The first real Windows CI run reported the whole audio area as BROKEN because
    a build server has no microphone, and the browser area as BROKEN because a
    lean CI install has no Playwright. Both were the instrument mis-reporting the
    machine as the product.
    """

    def test_zero_devices_is_a_skip_and_any_device_is_a_pass(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        import verify_audio

        self.assertEqual(verify_audio.device_status(0), "SKIP")
        self.assertEqual(verify_audio.device_status(1), "PASS")
        self.assertEqual(verify_audio.device_status(7), "PASS")

    def test_the_three_scripts_agree_about_a_missing_device(self):
        root = Path(__file__).resolve().parents[1] / "scripts"
        audio = (root / "verify_audio.py").read_text(encoding="utf-8")
        windows = (root / "verify_windows.py").read_text(encoding="utf-8")
        browser = (root / "verify_browser.py").read_text(encoding="utf-8")
        self.assertIn('return "PASS" if count else "SKIP"', audio)
        self.assertIn('return ("SKIP", "no input device', windows)
        self.assertIn('"playwright installed", "SKIP"', browser)


# ══════════════════════════════════════════════════════════════════════════
# from test_reputation.py
# ══════════════════════════════════════════════════════════════════════════
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.reputation import Record, Reputation


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class EvidenceTests(unittest.TestCase):
    def test_a_fresh_record_knows_nothing(self):
        record = Record("tool")
        self.assertEqual(record.samples, 0)
        self.assertAlmostEqual(record.mean, 0.5)
        self.assertGreater(record.lower(), 0.0)
        self.assertLess(record.lower(), 0.2)

    def test_successes_raise_the_bound_and_failures_lower_it(self):
        good, bad = Reputation(), Reputation()
        for _ in range(9):
            good.record("t", True)
            bad.record("t", False)
        self.assertGreater(good.lower("t"), 0.6)
        self.assertLess(bad.lower("t"), 0.2)

    def test_four_out_of_four_is_not_certainty(self):
        rep = Reputation()
        for _ in range(4):
            rep.record("t", True)
        self.assertLess(rep.lower("t"), 0.6)
        self.assertGreater(rep.get("t").mean, 0.8)

    def test_weighted_evidence(self):
        rep = Reputation()
        rep.record("t", True, weight=5.0)
        self.assertAlmostEqual(rep.get("t").alpha, 6.0)
        rep.record("t", False, weight=0.5)
        self.assertAlmostEqual(rep.get("t").beta, 1.5)

    def test_zero_weight_records_nothing_useful_but_counts_a_sample(self):
        rep = Reputation()
        rep.record("t", True, weight=0.0)
        self.assertEqual(rep.get("t").samples, 1)
        self.assertAlmostEqual(rep.get("t").evidence, 0.0)


class RankingTests(unittest.TestCase):
    def test_proven_beats_unproven(self):
        rep = Reputation()
        for _ in range(trials := 20):
            rep.record("reliable", True)
        rep.record("newcomer", True)
        self.assertEqual(rep.ranked_tools(["reliable", "newcomer"])[0], "reliable")
        self.assertGreater(trials, 0)

    def test_unproven_tools_answer_none_at_a_minimum(self):
        rep = Reputation()
        rep.record("a", True)                       # 1/1, lower bound ~0.1
        self.assertIsNone(rep.best(["a"], minimum=0.5))
        for _ in range(19):
            rep.record("a", True)
        self.assertEqual(rep.best(["a"], minimum=0.5), "a")

    def test_a_flaky_tool_loses_to_a_steady_one(self):
        rep = Reputation()
        for ok in (True, False, True, False, True, False, True, False):
            rep.record("flaky", ok)
        for _ in range(8):
            rep.record("steady", True)
        self.assertEqual(rep.ranked_tools(["flaky", "steady"])[0], "steady")

    def test_ranking_is_complete_and_deterministic(self):
        rep = Reputation()
        names = ["b", "a", "c"]
        self.assertEqual(sorted(rep.ranked_tools(names)), sorted(names))
        self.assertEqual(rep.ranked_tools(names), rep.ranked_tools(names))

    def test_empty_input_ranks_to_nothing(self):
        self.assertEqual(Reputation().rank([]), [])
        self.assertIsNone(Reputation().best([]))


class DecayTests(unittest.TestCase):
    def test_evidence_fades_but_the_prior_remains(self):
        clock = Clock()
        rep = Reputation(half_life=24 * 3600, clock=clock)
        for _ in range(20):
            rep.record("t", True)
        fresh = rep.lower("t")
        clock.advance(24 * 3600)                     # one half-life
        aged = rep.lower("t")
        self.assertLess(aged, fresh)
        self.assertGreater(aged, 0.0)

    def test_a_bad_week_beats_a_good_month(self):
        clock = Clock()
        rep = Reputation(half_life=7 * 24 * 3600, clock=clock)
        for _ in range(20):
            rep.record("t", True)                    # a good month
        clock.advance(30 * 24 * 3600)
        for _ in range(6):
            rep.record("t", False)                   # then a bad week
        self.assertLess(rep.get("t").mean, 0.55)

    def test_decay_never_produces_invalid_parameters(self):
        clock = Clock()
        rep = Reputation(half_life=60, clock=clock)
        rep.record("t", True)
        clock.advance(10 ** 7)
        record = rep.get("t")
        self.assertGreater(record.alpha, 0.0)
        self.assertGreater(record.beta, 0.0)
        self.assertTrue(0.0 < record.lower() < 1.0)


class StateTests(unittest.TestCase):
    def test_snapshot_restore_round_trip(self):
        rep = Reputation()
        for ok in (True, True, False, True):
            rep.record("tool_a", ok)
        snapshot = rep.snapshot()

        clone = Reputation()
        clone.restore(snapshot)
        self.assertAlmostEqual(clone.lower("tool_a"), rep.lower("tool_a"), places=9)
        self.assertEqual(clone.get("tool_a").samples, 4)

    def test_restore_tolerates_junk(self):
        rep = Reputation()
        rep.restore({})
        rep.restore({"records": {"x": "not a dict"}})
        rep.restore(None)                                    # type: ignore[arg-type]
        self.assertEqual(rep.get("x").samples, 0)

    def test_reset_clears_everything(self):
        rep = Reputation()
        rep.record("a", True)
        rep.reset()
        self.assertEqual(rep.get("a").samples, 0)

    def test_snapshot_is_serialisable(self):
        import json

        rep = Reputation()
        rep.record("a", True)
        json.dumps(rep.snapshot())          # must not raise


# ══════════════════════════════════════════════════════════════════════════
# from test_inventory_data.py
# ══════════════════════════════════════════════════════════════════════════
import contextlib
import importlib.util
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "inventory_data", ROOT / "scripts" / "inventory_data.py"
)
inventory_data = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(inventory_data)

SECRET = "AIza-THIS-IS-THE-SECRET"
FACT = "My sister is called Priya"


def build_install(base: Path, *, sessions=None, facts=None, key=SECRET) -> Path:
    install = base / "install"
    (install / "config").mkdir(parents=True)
    (install / "memory").mkdir(parents=True)
    (install / "config" / "api_keys.json").write_text(json.dumps({
        "gemini_api_key": key,
        "assistant_name": "JARVIS",
        "providers": {"groq": {"api_key": "gsk_another_secret", "model": "x"}},
    }), encoding="utf-8")
    memory = {
        "identity": {"name": FACT} if facts else {},
        "preferences": {},
        "sessions": sessions or [],
    }
    (install / "memory" / "long_term.json").write_text(
        json.dumps(memory), encoding="utf-8")
    return install


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.state = self.base / "state"
        self.state.mkdir()

    def report(self, install):
        return inventory_data.inventory(install, self.state)

    def test_empty_install_reports_nothing(self):
        report = self.report(self.base / "nothing")
        self.assertEqual(report["files"], [])
        self.assertEqual(report["summary"]["conversation_summaries"], 0)

    def test_files_and_counts_are_reported(self):
        install = build_install(self.base, sessions=[{"date": "2026-11-05", "summary": "x"}],
                                facts=True)
        report = self.report(install)
        self.assertEqual(report["summary"]["conversation_summaries"], 1)
        self.assertEqual(report["summary"]["saved_facts"], 1)

    def test_no_sessions_means_the_honest_verdict(self):
        install = build_install(self.base)
        report = self.report(install)
        self.assertEqual(report["summary"]["conversation_summaries"], 0)
        self.assertIn("no conversation history", report["summary"]["verdict"])

    def test_credential_fields_are_named_but_not_valued(self):
        install = build_install(self.base)
        report = self.report(install)
        config = next(f for f in report["files"] if f["file"].endswith("api_keys.json"))
        self.assertIn("gemini_api_key", config["credential_fields"])
        self.assertEqual(config["credential_fields_present"], 1)
        self.assertNotIn(SECRET, json.dumps(report))

    def test_printed_output_contains_no_memory_and_no_secret(self):
        install = build_install(self.base, facts=True)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            inventory_data.print_human(self.report(install))
        output = buffer.getvalue()
        self.assertNotIn(SECRET, output)
        self.assertNotIn("Priya", output, "a stored memory must never be printed")
        self.assertIn("gemini_api_key", output)

    def test_sqlite_tables_and_rows_are_counted(self):
        database = self.state / "knowledge.sqlite3"
        connection = sqlite3.connect(database)
        connection.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY, name TEXT)")
        connection.executemany("INSERT INTO tasks (name) VALUES (?)", [("a",), ("b",)])
        connection.commit()
        connection.close()
        report = self.report(build_install(self.base))
        sqlite_report = next(f for f in report["files"] if f["kind"] == "sqlite")
        self.assertEqual(sqlite_report["tables"]["tasks"], 2)

    def test_state_json_is_included(self):
        (self.state / "approved-insights.json").write_text(
            json.dumps({"response_length": "concise"}), encoding="utf-8")
        report = self.report(build_install(self.base))
        names = [Path(f["file"]).name for f in report["files"]]
        self.assertIn("approved-insights.json", names)

    def test_broken_json_is_reported_not_raised(self):
        install = build_install(self.base)
        (install / "memory" / "long_term.json").write_text("{broken", encoding="utf-8")
        report = self.report(install)
        entry = next(f for f in report["files"] if f["file"].endswith("long_term.json"))
        self.assertIn("error", entry)

    def test_cli_json_output_parses(self):
        install = build_install(self.base)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = inventory_data.main(["--install", str(install),
                                        "--state", str(self.state), "--json"])
        self.assertEqual(code, 0)
        self.assertIn("summary", json.loads(buffer.getvalue()))

    def test_cli_rejects_a_missing_folder(self):
        self.assertEqual(inventory_data.main(["--install", str(self.base / "nope")]), 2)


if __name__ == "__main__":
    unittest.main()
