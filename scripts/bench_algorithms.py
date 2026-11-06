"""scripts/bench_algorithms.py — numbers for the algorithms in core/.

WHY A BENCH AND NOT A CLAIM
    "The matcher is better now" and "the bandit learns the good provider" are
    both checkable. This script checks them:

      fuzzy       top-1 accuracy on misheard names, and microseconds per query
                  on a 600-application index
      knapsack    how far the 2-approximation actually lands from the exact
                  optimum on random instances (the bound says 2x; reality is
                  usually far closer)
      branchbound how much of a candidate tree is pruned before a decision
      reputation  the lower bound after n successes — the number that has to
                  stay honest rather than hopeful
      bandit      regret against an oracle that knows the best arm in hindsight
      audio       per-frame speech/noise classification on synthetic signals,
                  and the cost of a 30 ms frame

USAGE
    python scripts\\bench_algorithms.py
    python scripts\\bench_algorithms.py --json
    python scripts\\bench_algorithms.py --only fuzzy bandit

Nothing here touches a network, a microphone, a model or the user's files.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# (misheard, expected) — the same shape as the fixture in tests/test_fuzzy.py,
# kept short here so this script has no dependency on the test suite.
MISHEARD = [
    ("whats app", "WhatsApp"), ("what's up", "WhatsApp"), ("whatsap", "WhatsApp"),
    ("chorme", "Google Chrome"), ("google chorme", "Google Chrome"),
    ("vs code", "Visual Studio Code"), ("vscode", "Visual Studio Code"),
    ("excel sheet", "Microsoft Excel"), ("vyber", "Viber"), ("spot ify", "Spotify"),
    ("ppt", "Microsoft PowerPoint"), ("telegram", "Telegram"), ("calc", "Calculator"),
    ("task manager", "Task Manager"), ("note pad", "Notepad"),
]

APPS = [
    "WhatsApp", "Google Chrome", "Visual Studio Code", "Notepad", "Microsoft Word",
    "Microsoft Excel", "Viber", "Telegram", "Spotify", "Calculator", "MS Paint",
    "Task Manager", "File Explorer", "Steam", "Discord", "Windows Terminal",
    "Microsoft PowerPoint", "Camera", "Settings", "Microsoft Teams",
]


def bench_fuzzy() -> dict:
    from core.fuzzy import FuzzyIndex

    index = FuzzyIndex(APPS)
    hits = 0
    for spoken, expected in MISHEARD:
        results = index.query(spoken, limit=1, threshold=0.5)
        hits += bool(results) and results[0][1] == expected

    large = FuzzyIndex([f"Program Number {i} Edition" for i in range(580)] + APPS)
    start = time.perf_counter()
    rounds = 200
    for _ in range(rounds):
        for spoken, _expected in MISHEARD:
            large.query(spoken, limit=3, threshold=0.5)
    per_query_us = (time.perf_counter() - start) * 1e6 / (rounds * len(MISHEARD))

    return {
        "top1_accuracy": round(hits / len(MISHEARD), 3),
        "cases": len(MISHEARD),
        "us_per_query_600_candidates": round(per_query_us, 1),
    }


def bench_knapsack() -> dict:
    from core.knapsack import Item, solve, solve_exact, solve_greedy

    rng = random.Random(20261106)
    ratios, greedy_times, exact_times = [], [], []
    for _ in range(200):
        items = [
            Item(f"i{n}", round(rng.uniform(0.1, 1.0), 3), rng.randint(1, 400))
            for n in range(rng.randint(5, 40))
        ]
        capacity = rng.randint(300, 2000)

        start = time.perf_counter()
        exact = solve_exact(items, capacity)
        exact_times.append((time.perf_counter() - start) * 1000)

        start = time.perf_counter()
        approx = solve_greedy(items, capacity)
        greedy_times.append((time.perf_counter() - start) * 1000)

        if exact.value > 0:
            ratios.append(approx.value / exact.value)

    dispatch = solve(
        [Item(f"block{n}", rng.uniform(0.1, 1.0), rng.randint(40, 400)) for n in range(40)],
        1200,
    )
    return {
        "mean_approx_ratio": round(statistics.mean(ratios), 4),
        "worst_approx_ratio": round(min(ratios), 4),
        "bound_guarantee": 0.5,
        "exact_ms_median": round(statistics.median(exact_times), 2),
        "greedy_ms_median": round(statistics.median(greedy_times), 3),
        "dispatch_path_exact": dispatch.exact,
    }


def bench_branchbound() -> dict:
    from core.branchbound import Candidate, decide

    rng = random.Random(7)
    explored, pruned = [], []
    for _ in range(200):
        roots = [
            Candidate(
                f"c{i}",
                rng.uniform(0.2, 0.95),
                children=[Candidate(f"c{i}.{j}", rng.uniform(0.2, 0.95)) for j in range(rng.randint(0, 4))],
            )
            for i in range(rng.randint(2, 8))
        ]
        total_nodes = sum(1 + len(list(root.children)) for root in roots)
        result = decide(roots)
        explored.append(result.explored / total_nodes)
        pruned.append(result.pruned / total_nodes)

    return {
        "nodes_explored_pct": round(100 * statistics.mean(explored), 1),
        "nodes_pruned_pct": round(100 * statistics.mean(pruned), 1),
    }


def bench_reputation() -> dict:
    from core.reputation import Reputation

    rep = Reputation()
    bounds = {}
    for n in range(1, 201):
        rep.record("t", True)
        if n in (1, 2, 4, 8, 20, 50, 100, 200):
            bounds[str(n)] = round(rep.lower("t"), 3)

    pick = Reputation()
    for _ in range(20):
        pick.record("steady", True)
    for _ in range(20):
        pick.record("lucky", True)
    for _ in range(6):
        pick.record("lucky", False)
    for _ in range(20):
        pick.record("flaky", False)
    return {
        "lower_bound_after_n_successes": bounds,
        "ranking": {name: score for name, score in pick.rank(["steady", "lucky", "flaky"])},
    }


def bench_bandit() -> dict:
    from core.bandit import UCB1, Thompson

    truths = {"good": 0.85, "ok": 0.55, "bad": 0.15}
    rounds = 2000
    best = max(truths.values())

    def regret(bandit, seed):
        rng = random.Random(seed)
        total = 0.0
        for _ in range(rounds):
            arm = bandit.choose()
            reward = 1.0 if rng.random() < truths[arm] else 0.0
            bandit.update(arm, reward)
            total += best - truths[arm]
        return total

    return {
        "rounds": rounds,
        "ucb1_regret": round(statistics.mean(regret(UCB1(truths), seed) for seed in range(5)), 1),
        "thompson_regret": round(
            statistics.mean(regret(Thompson(truths, rng=random.Random(seed)), seed) for seed in range(5)), 1
        ),
        "uniform_regret": round((best - statistics.mean(truths.values())) * rounds, 1),
    }


def bench_audio() -> dict:
    import numpy as np

    from core.audio_features import features

    rate, frame = 16000, 480
    t = np.arange(frame) / rate

    def voiced(amplitude=0.25):
        signal = sum(np.sin(2 * np.pi * 140 * k * t) / k for k in range(1, 8))
        return (amplitude * signal / 2.0)

    rng = np.random.default_rng(0)
    cases = (
        [(voiced(a), True) for a in (0.3, 0.15, 0.05, 0.02)]
        + [(rng.uniform(-0.3, 0.3, frame), False) for _ in range(4)]
        + [(np.zeros(frame), False)]
    )
    correct = sum(features(samples)["speech_like"] == expected for samples, expected in cases)

    samples = voiced()
    start = time.perf_counter()
    for _ in range(500):
        features(samples)
    per_frame_us = (time.perf_counter() - start) * 1e6 / 500

    return {
        "classification_accuracy": round(correct / len(cases), 3),
        "cases": len(cases),
        "us_per_30ms_frame": round(per_frame_us, 1),
        "realtime_fraction": round(per_frame_us / 30_000, 5),
    }


BENCHES = {
    "fuzzy": bench_fuzzy,
    "knapsack": bench_knapsack,
    "branchbound": bench_branchbound,
    "reputation": bench_reputation,
    "bandit": bench_bandit,
    "audio": bench_audio,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bench_algorithms.py", description=__doc__.splitlines()[0])
    parser.add_argument("--only", nargs="+", choices=sorted(BENCHES), help="run these only")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    results = {}
    for name in (args.only or list(BENCHES)):
        results[name] = BENCHES[name]()

    if args.json:
        print(json.dumps(results, indent=2))
        return 0

    print("algorithm benchmarks — offline, no network, no microphone\n")
    for name, payload in results.items():
        print(f"  {name}")
        for key, value in payload.items():
            print(f"    {key:<32} {value}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
