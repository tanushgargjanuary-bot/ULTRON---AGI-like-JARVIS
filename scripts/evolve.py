"""scripts/evolve.py — the missing engine for core/selfimprove.py.

WHY THIS FILE EXISTS
    `core/selfimprove.py` could compare a candidate against the current value and
    decide honestly whether the difference was real. Nothing called it. A loop
    nothing can start is not a self-improving system, it is a well-tested library,
    and "Ultron should be able to self-evolve" was therefore not yet true.

    This is the smallest honest way to make it true: a command a person runs,
    which measures candidates against cases, prints the verdict, and appends what
    it found to a log. It never edits source. Not because that would be hard, but
    because a program that rewrites itself while running is a program whose next
    failure nobody can reproduce — and the user's own rule is two human
    confirmations for a change to code.

WHAT IT MEASURES, AND WHY THAT ONE
    The first real artefact is the fuzzy matcher's confidence floor: the value
    below which a spoken name is not considered a match at all. It is a single
    number that trades recall against nonsense, the fixture to measure it exists
    in this repository, and it is exactly the kind of thing a machine can check
    faster than a person can.

    Adding more artefacts is a data change, not a code change: append to
    `ARTEFACTS` an entry with a space of candidate values and an evaluator.

HOW TO RUN IT

    python scripts\\evolve.py                      # measure, print, write the log
    python scripts\\evolve.py --csv mine.csv       # add your own cases
    python scripts\\evolve.py --json               # machine-readable verdict

    The CSV is `spoken,expected` — one line per command you actually said, and
    the application you meant. Blank `expected` marks a phrase that matches
    nothing and must stay unmatched.

WHAT IT WILL NOT DO
    Apply the result. It prints the value and the evidence, and changing it is one
    line in `core/app_resolver.py` with a human deciding. That is the deliberate
    line between a system that can be reviewed and one that cannot.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.fuzzy import FuzzyIndex
from core.selfimprove import (
    Artefact,
    Budget,
    Case,
    Entry,
    Lineage,
    improve,
)

LOG_PATH = ROOT / "memory" / "evolution-log.json"

# The fixture: phrases as speech recognition renders them on a bad day, and the
# application the user meant. Blank means "this must not match anything".
BUILT_IN = (
    ("whats app", "WhatsApp"),
    ("what's up", "WhatsApp"),
    ("whatsap", "WhatsApp"),
    ("chorme", "Google Chrome"),
    ("google chorme", "Google Chrome"),
    ("vs code", "Visual Studio Code"),
    ("vscode", "Visual Studio Code"),
    ("excel sheet", "Microsoft Excel"),
    ("vyber", "Viber"),
    ("spot ify", "Spotify"),
    ("ppt", "Microsoft PowerPoint"),
    ("telegram", "Telegram"),
    ("calc", "Calculator"),
    ("note pad", "Notepad"),
    ("zxqv", ""),
    ("blah blah", ""),
    ("open the pod bay doors", ""),
    ("qqqq", ""),
)

INSTALLED = (
    "WhatsApp", "Google Chrome", "Visual Studio Code", "Microsoft Excel", "Viber",
    "Spotify", "Telegram", "Calculator", "Microsoft PowerPoint", "Notepad",
)

CANDIDATES = (0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90)


class ThresholdEvaluator:
    """Score one confidence floor by how well the matcher behaves at it.

    A case is worth 1.0 when the matcher returns the right application, or returns
    nothing for a phrase that means nothing. Junk cases are marked `safety` on
    purpose: a floor low enough to invent a match for "qqqq" is not a trade-off,
    it is the bug this matcher exists to prevent.
    """

    def __init__(self, cases: list[Case], phrases: dict[str, str]) -> None:
        self._cases = cases
        self._phrases = phrases
        self._index = FuzzyIndex(INSTALLED)

    def cases(self) -> list[Case]:
        return list(self._cases)

    def score(self, value: float, case: Case) -> float:
        expected = self._phrases[case.id]
        found = self._index.query(case.id, limit=1, threshold=float(value))
        if not expected:
            return 1.0 if not found else 0.0
        return 1.0 if found and found[0][1] == expected else 0.0


def build_cases(extra_csv: Path | None = None) -> tuple[list[Case], dict[str, str]]:
    phrases: dict[str, str] = {}
    cases: list[Case] = []
    for spoken, expected in BUILT_IN:
        phrases[spoken] = expected
        cases.append(Case(spoken, safety=not expected))
    if extra_csv is not None and extra_csv.exists():
        with extra_csv.open(newline="", encoding="utf-8-sig") as handle:
            for row, record in enumerate(csv.reader(handle)):
                if len(record) < 2:
                    continue
                spoken, expected = record[0].strip(), record[1].strip()
                if row == 0 and spoken.lower() in ("spoken", "phrase", "said"):
                    continue
                if not spoken:
                    continue
                case_id = spoken
                phrases[case_id] = expected
                cases.append(Case(case_id, safety=not expected))
    return cases, phrases


def run(cases: list[Case], phrases: dict[str, str], *, current: float,
        budget: int = 12) -> dict:
    evaluator = ThresholdEvaluator(cases, phrases)
    artefact = Artefact(
        "app_resolver.fuzzy_floor",
        current,
        space=tuple(value for value in CANDIDATES if value != current),
        kind="threshold",
        # Not protected: a threshold is reversible with one edit and cannot
        # destroy anything. It is still not applied automatically.
        protected=False,
        reversible=True,
        note="confidence floor for a fuzzy application-name match",
    )
    verdict = improve(artefact, evaluator, min_effect=0.02, budget=budget, apply=None)
    return {
        "artefact": artefact.name,
        "current": current,
        "cases": len(cases),
        "verdict": verdict.as_dict(),
    }


def record(payload: dict, *, path: Path | None = None) -> Path:
    """Append the finding to the lineage file. Never rewrites history.

    A rejected candidate is recorded too, with its p-value. The rejections are the
    part that makes the file worth reading: they are the evidence that the loop is
    not just collecting changes.
    """
    path = path or LOG_PATH
    lineage = Lineage()
    if path.exists():
        try:
            lineage.restore(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            lineage = Lineage()

    verdict = payload["verdict"]
    comparison = verdict.get("comparison") or {}
    lineage.entries.append(
        Entry(
            artefact=payload["artefact"],
            before=payload["current"],
            after=verdict["value"],
            delta=float(comparison.get("delta", 0.0)),
            p_value=float(comparison.get("p_value", 1.0)),
        )
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(lineage.to_json(), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="evolve.py", description="Measure whether a change is real. Applies nothing."
    )
    parser.add_argument("--csv", type=Path, help="extra cases: spoken,expected")
    parser.add_argument("--current", type=float, default=0.75,
                        help="the value in use today (default 0.75)")
    parser.add_argument("--budget", type=int, default=12, help="candidates to try")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-log", action="store_true", help="print without recording")
    args = parser.parse_args(argv)

    cases, phrases = build_cases(args.csv)
    budget = Budget(max_experiments=max(1, args.budget))
    if budget.stopped():
        print("evolution budget is spent; nothing was tried.")
        return 1

    payload = run(cases, phrases, current=args.current, budget=args.budget)
    verdict = payload["verdict"]

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"artefact   {payload['artefact']}")
        print(f"in use     {payload['current']}")
        print(f"cases      {payload['cases']}")
        print(f"tried      {verdict['tried']}")
        print(f"accepted   {verdict['accepted']}")
        print(f"reason     {verdict['reason']}")
        if verdict["accepted"]:
            print(f"\nproposed   {verdict['value']}  (nothing has been changed)")
            print("to adopt it: change FUZZY_TIER_MIN in core/app_resolver.py — a person decides")
        comparison = verdict.get("comparison")
        if comparison:
            print(f"\ncases better {comparison['wins']}, worse {comparison['losses']}, "
                  f"same {comparison['ties']}, p={comparison['p_value']:.4f}")
        print()
        print("This command never edits source code and never changes a setting.")

    if not args.no_log:
        path = record(payload)
        if not args.json:
            try:
                shown = path.relative_to(ROOT)
            except ValueError:          # a log path outside the project
                shown = path
            print(f"recorded in {shown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
