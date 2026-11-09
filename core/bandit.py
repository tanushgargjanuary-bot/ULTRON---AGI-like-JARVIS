"""core/bandit.py — choosing between options you can only learn about by using.

WHERE THIS GOES
    `core/routing.py` picks a provider per purpose from a static table. That
    table is a reasonable default and a poor optimum: which provider is fastest
    for "short factual answer" depends on the user's network, the time of day and
    the provider's own load, and it changes. The same machinery suits tool
    ordering (which search backend answers first) and suggestion ranking.

    The learner is a multi-armed bandit — AIML Unit V's reinforcement learning,
    cut down to the part that actually converges on this data volume.

WHY NOT Q-LEARNING OR DEEP RL
    A personal assistant produces 20–50 episodes a day, non-stationary, with no
    simulator. Deep RL would not converge, and an unconverged policy in the
    routing path is worse than a static table. A bandit needs a few hundred
    pulls to separate arms, handles non-stationarity with a discount, and its
    failure mode is "keeps exploring slightly too much" rather than "does
    something strange once and permanently".

THE TWO ALGORITHMS
    `UCB1`     deterministic optimism: pick the arm with the best lower
               confidence bound. No randomness, so behaviour is reproducible in
               a test, and the exploration is proportional to how little is
               known — the c·sqrt(ln n / n_i) term IS the "try it and see".
    `Thompson` probabilistic: sample each arm's posterior from a Beta and pick
               the sample maximum. Explores in proportion to uncertainty too,
               but it degrades more gracefully when a reward is noisy.

    Both take a `blocked` set so a caller can subtract arms the quota ledger has
    exhausted. Filtering beats penalising: a blocked arm should not be sampled
    at all, or the learner spends its exploration budget on something it cannot
    use.

NO CREDENTIAL GAMES
    This chooses among providers the user configured. It never rotates keys to
    evade a rate limit; `blocked` comes from `QuotaLedger` and honours 429s as
    they are meant to be honoured.
"""

from __future__ import annotations

import math
import random
import threading
from dataclasses import dataclass


@dataclass
class Arm:
    """One option: a provider id, a tool name, a suggestion."""

    name: str
    pulls: float = 0.0
    total_reward: float = 0.0

    @property
    def mean(self) -> float:
        return self.total_reward / self.pulls if self.pulls else 0.0


class _Base:
    """Shared bookkeeping: which arms exist and what they have earned."""

    def __init__(self, arms, *, default_reward: float = 0.5) -> None:
        self._lock = threading.RLock()
        self._arms: dict[str, Arm] = {}
        self._default_reward = float(default_reward)
        for name in arms:
            self._arms[str(name)] = Arm(name=str(name))

    # ── state ────────────────────────────────────────────────────────────────
    def __len__(self) -> int:
        return len(self._arms)

    def names(self) -> list[str]:
        with self._lock:
            return list(self._arms)

    def stats(self) -> dict[str, dict]:
        with self._lock:
            pulls = {}
            for name, arm in self._arms.items():
                count = float(arm.pulls)
                pulls[name] = int(count) if count.is_integer() else round(count, 4)
            return {name: {"pulls": pulls[name], "mean": round(arm.mean, 4)}
                    for name, arm in self._arms.items()}

    def add_arm(self, name: str) -> None:
        with self._lock:
            self._arms.setdefault(str(name), Arm(name=str(name)))

    def forget(self, name: str) -> None:
        with self._lock:
            self._arms.pop(str(name), None)

    # ── learning ─────────────────────────────────────────────────────────────
    def update(self, name: str, reward: float, weight: float = 1.0) -> None:
        """Record a reward in 0..1 with an optional non-negative sample weight.

        Fractional weights let callers discount older evidence without counting
        every historical observation as a full-strength pull.
        """
        reward = float(reward)
        weight = float(weight)
        if not math.isfinite(reward) or not math.isfinite(weight):
            raise ValueError("reward and weight must be finite numbers")
        reward = max(0.0, min(1.0, reward))
        weight = max(0.0, weight)
        with self._lock:
            arm = self._arms.get(str(name))
            if arm is None:
                arm = self._arms[str(name)] = Arm(name=str(name))
            arm.pulls += weight
            arm.total_reward += reward * weight

    def _eligible(self, blocked) -> list[Arm]:
        blocked = {str(name) for name in (blocked or ())}
        return [arm for name, arm in self._arms.items() if name not in blocked]

    def choose(self, blocked=()):
        raise NotImplementedError

    def _untried(self, arms: list[Arm]):
        """Unpulled arms first — pure exploitation on an unseen arm is a guess
        dressed as a decision."""
        for arm in arms:
            if arm.pulls == 0:
                return arm
        return None


class UCB1(_Base):
    """Upper Confidence Bound: deterministic, provably logarithmic regret.

    score = mean + c * sqrt(ln(N) / n_i)

    `c` is the exploration dial. sqrt(2) is the theoretical default for rewards
    in [0, 1]; it can be lowered when the caller knows the arms are stable.
    """

    def __init__(self, arms, *, c: float = math.sqrt(2.0)) -> None:
        super().__init__(arms)
        self._c = float(c)

    def scores(self, blocked=()) -> list[tuple[str, float]]:
        with self._lock:
            arms = self._eligible(blocked)
            total = sum(arm.pulls for arm in arms)
            if total == 0:
                return [(arm.name, float("inf")) for arm in arms]
            log_total = math.log(total)
            scored = []
            for arm in arms:
                if arm.pulls == 0:
                    scored.append((arm.name, float("inf")))
                else:
                    bonus = self._c * math.sqrt(log_total / arm.pulls)
                    scored.append((arm.name, arm.mean + bonus))
            scored.sort(key=lambda pair: (-pair[1], pair[0]))
            return scored

    def choose(self, blocked=()):
        with self._lock:
            arms = self._eligible(blocked)
            if not arms:
                return None
            untried = self._untried(arms)
            if untried is not None:
                return untried.name
        scored = self.scores(blocked)
        return scored[0][0] if scored else None


class Thompson(_Base):
    """Beta-Thompson sampling over arms with a configurable prior.

    `prior=(1, 1)` is uniform: "I know nothing about this arm". A caller that
    has a real prior — a provider known to be fast but rate-limited — can pass
    an asymmetric one, and the learner starts from belief instead of ignorance.
    """

    def __init__(self, arms, *, prior: tuple[float, float] = (1.0, 1.0),
                 rng: random.Random | None = None) -> None:
        super().__init__(arms)
        self._alpha0, self._beta0 = float(prior[0]), float(prior[1])
        self._rng = rng or random.Random()
        self._alpha: dict[str, float] = {}
        self._beta: dict[str, float] = {}

    def _params(self, name: str) -> tuple[float, float]:
        return (self._alpha.get(name, self._alpha0), self._beta.get(name, self._beta0))

    def update(self, name: str, reward: float, weight: float = 1.0) -> None:
        reward = float(reward)
        weight = float(weight)
        if not math.isfinite(reward) or not math.isfinite(weight):
            raise ValueError("reward and weight must be finite numbers")
        reward = max(0.0, min(1.0, reward))
        weight = max(0.0, weight)
        with self._lock:
            alpha, beta = self._params(str(name))
            self._alpha[str(name)] = alpha + (reward * weight)
            self._beta[str(name)] = beta + ((1.0 - reward) * weight)
            super().update(name, reward, weight=weight)

    def posterior(self, name: str) -> tuple[float, float]:
        with self._lock:
            return self._params(str(name))

    def choose(self, blocked=()):
        with self._lock:
            arms = self._eligible(blocked)
            if not arms:
                return None
            untried = self._untried(arms)
            if untried is not None:
                return untried.name
            best_name, best_sample = None, -1.0
            for arm in arms:
                alpha, beta = self._params(arm.name)
                sample = self._rng.betavariate(alpha, beta)
                if sample > best_sample:
                    best_name, best_sample = arm.name, sample
            return best_name


class Contextual:
    """One bandit per context (a routing "purpose", a command class).

    Contexts are learned separately because pooling them is how a bandit
    averages "explain this code" with "open chrome" and then picks a provider
    that is mediocre at both.
    """

    def __init__(self, factory=None) -> None:
        self._factory = factory or (lambda arms: Thompson(arms))
        self._lock = threading.RLock()
        self._bands: dict[str, object] = {}

    def bandit(self, context: str, arms=()):
        context = str(context)
        with self._lock:
            band = self._bands.get(context)
            if band is None:
                band = self._factory(list(arms))
                self._bands[context] = band
            else:
                for name in arms:
                    band.add_arm(name)
            return band

    def choose(self, context: str, arms=(), blocked=()):
        return self.bandit(context, arms).choose(blocked)

    def update(self, context: str, name: str, reward: float) -> None:
        self.bandit(context).update(name, reward)

    def stats(self) -> dict[str, dict]:
        with self._lock:
            return {context: band.stats() for context, band in self._bands.items()}
