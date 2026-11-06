"""core/numerics.py — the small amount of numerical mathematics this project needs.

WHY THIS FILE EXISTS
    Several decisions in Ultron are probabilistic and have to be *numerically*
    honest rather than approximately nice:

      - "do not act unless you are at least 70 % sure" needs a confidence bound
        on a Beta posterior, not a mean.
      - a tool that succeeded 4 out of 4 times is not "100 % reliable"; its lower
        bound is around 40 %, and the difference is the whole point.

    The obvious library for that is scipy, which is ~120 MB and pulls in a BLAS
    stack for one quantile. The functions below are the three that are actually
    required, written from the standard continued-fraction expansions in
    Numerical Recipes, and checked against published values in
    tests/test_numerics.py.

WHAT IS HERE
    `betacf`, `betai`     regularised incomplete beta I_x(a, b) — the CDF of a
                          Beta distribution.
    `beta_quantile`       inverse CDF by bisection; used for lower confidence
                          bounds.
    `beta_mean`, `beta_var`
    `wilson_lower`        closed-form binomial lower bound, for the many places
                          where a Beta quantile would be overkill.

ACCURACY
    `betai` is accurate to about 1e-10 in the region this project uses
    (a, b >= 1, 0 < x < 1), which is far more than a decision threshold needs.
    The bisection is run to 1e-12 on x, so quantiles are good to ~1e-9.

NOT HERE
    Anything from a machine-learning library. This project has no business
    shipping a gradient-descent framework to answer "is this tool reliable?".
"""

from __future__ import annotations

import math

_MAX_ITER = 300
_EPS = 3.0e-14
_FPMIN = 1.0e-300


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta function (Lentz's method).

    The standard Numerical Recipes `betacf`: modified Lentz algorithm, which
    avoids the overflow that naive evaluation hits when the terms grow faster
    than the running product.
    """
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < _FPMIN:
        d = _FPMIN
    d = 1.0 / d
    h = d

    for m in range(1, _MAX_ITER + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = 1.0 + aa / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        h *= d * c

        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = 1.0 + aa / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _EPS:
            break
    return h


def betai(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta function I_x(a, b) — i.e. Beta(a, b) CDF at x.

    I_0 = 0, I_1 = 1. Uses the symmetry I_x(a,b) = 1 - I_{1-x}(b,a) to keep the
    continued fraction in its fast-converging region.
    """
    if a <= 0.0 or b <= 0.0:
        raise ValueError("betai needs a > 0 and b > 0")
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    log_front = (
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log1p(-x)
    )
    front = math.exp(log_front)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def beta_mean(a: float, b: float) -> float:
    return a / (a + b)


def beta_var(a: float, b: float) -> float:
    total = a + b
    return (a * b) / (total * total * (total + 1.0))


def beta_quantile(p: float, a: float, b: float, *, tol: float = 1e-12) -> float:
    """Inverse Beta CDF: the x where I_x(a, b) = p.

    Bisection rather than Newton: `betai` is monotone in x, the bracket is
    always [0, 1], and 60 iterations of a guaranteed-bracketed method is both
    faster to trust and faster to run than a derivative-free optimiser.
    """
    if not 0.0 < p < 1.0:
        raise ValueError("beta_quantile needs 0 < p < 1")
    low, high = 0.0, 1.0
    for _ in range(200):
        mid = 0.5 * (low + high)
        if betai(a, b, mid) < p:
            low = mid
        else:
            high = mid
        if high - low < tol:
            break
    return 0.5 * (low + high)


def wilson_lower(successes: int, trials: int, z: float = 1.959963984540054) -> float:
    """Lower bound of the Wilson score interval for a binomial proportion.

    Chosen over the normal approximation because this project evaluates small
    samples: 3 successes out of 3 should not read as a 100 % success rate, and
    the normal approximation happily gives 100 % ± 0.
    """
    if trials <= 0:
        return 0.0
    successes = max(0, min(successes, trials))
    p = successes / trials
    denom = 1.0 + z * z / trials
    centre = p + z * z / (2.0 * trials)
    spread = z * math.sqrt(max(0.0, p * (1.0 - p) / trials + z * z / (4.0 * trials * trials)))
    return max(0.0, (centre - spread) / denom)
