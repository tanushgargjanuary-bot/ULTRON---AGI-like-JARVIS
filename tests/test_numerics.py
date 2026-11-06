"""tests/test_numerics.py — the incomplete beta, checked against closed forms.

WHY THESE PARTICULAR CHECKS
    A statistical bound that is subtly wrong is worse than no bound: it looks
    authoritative and it silently moves the 0.70 line. So the tests are anchored
    to values that can be derived by hand rather than to the implementation's own
    previous output, and the ones that matter are checked twice — once against an
    analytic CDF and once through the inverse (quantile → CDF must return the
    input probability).
"""

from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
