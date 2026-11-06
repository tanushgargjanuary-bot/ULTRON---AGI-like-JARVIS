"""Every algorithm that says which unit it implements, and a check that says if it lies.

A citation is one line, on the function itself:

    @implements("DAA", 4, "All-pairs shortest paths: Warshall and Floyd")

Three things make that worth more than a comment.

    it is attached    the unit travels with the function object, so no doc can drift
                      from the code it describes;
    it is checked     `verify()` imports the function's module and calls `callable()`
                      on it, so a citation on code that was deleted is an error, not a
                      memory;
    it is matched     `verify()` compares the citation to the topic list in
                      `curriculum/aktu_aiml.json`. Cite a topic the course does not
                      contain for that unit and the check fails, which is how the map
                      stays honest when a syllabus changes.

The decorator returns the function unchanged. It attaches one attribute and moves on:
nothing here may alter behaviour, because most of what it decorates was written and
tested long before the citation existed.
"""

from __future__ import annotations

import importlib
import inspect

from core import curriculum

# The modules scanned for citations. A list rather than a package walk: importing
# every module in the project to build a map would be slow and could have side
# effects, and a map that is slow is a map nobody asks for.
SCANNED = (
    "core.mental.logic",
    "core.mental.plan",
    "core.mental.choose",
    "core.mental.context",
    "core.fuzzy",
    "core.trie",
    "core.knapsack",
    "core.branchbound",
    "core.bandit",
    "core.numerics",
    "core.self_change",
    "memory.config_manager",
)


def implements(course: str, unit: int, topic: str):
    """Attach the unit this function implements. Behaviour is not touched."""
    citation = {"course": str(course), "unit": int(unit), "topic": str(topic)}

    def remember(function):
        held = tuple(getattr(function, "implements", ()))
        function.implements = held + (citation,)
        return function

    return remember


BROKEN: dict[str, str] = {}


def _modules():
    for name in SCANNED:
        try:
            yield name, importlib.import_module(name)
        except Exception as error:                          # noqa: BLE001
            # A module that will not import is not skipped quietly: the citation map
            # would silently lose its evidence and still look complete.
            BROKEN[name] = f"{type(error).__name__}: {error}"


def catalogue() -> list[dict]:
    """Every citation in the project: module, function, course, unit, topic."""
    rows = []
    for module_name, module in _modules():
        for attribute, value in inspect.getmembers(module, callable):
            for citation in getattr(value, "implements", ()):
                rows.append({**citation, "module": module_name,
                             "function": f"{module_name}.{attribute}"})
    return sorted(rows, key=lambda row: (row["course"], row["unit"], row["topic"]))


def _known(course: str, unit: int, topic: str) -> bool:
    found = curriculum.subject(course)
    if found is None:
        return False
    for row in found["units"]:
        if row["unit"] == unit:
            return topic in row["topics"]
    return False


def verify() -> list[str]:
    """What is wrong with the citations. Empty means every one is true."""
    rows = catalogue()          # this is what fills BROKEN, so it comes first
    problems = [f"{name} will not import, so its citations cannot be checked: {why}"
                for name, why in sorted(BROKEN.items())]
    for row in rows:
        if not callable(getattr(importlib.import_module(row["module"]),
                                row["function"].split(".")[-1], None)):
            problems.append(f"{row['function']} is cited but is not callable")
        if not _known(row["course"], row["unit"], row["topic"]):
            problems.append(f"{row['function']} cites {row['course']} unit "
                            f"{row['unit']} '{row['topic']}', which is not in the "
                            f"syllabus for that unit")
    return problems


def short(course: str) -> str:
    """The short name of a course, given either its code or its short name.

    The syllabus is keyed by course code (BCS503) and people speak the short name
    (DAA). Both are accepted here, because a citation map that fails on the way the
    owner says the words is a map that fails.
    """
    text = str(course).strip()
    for subject in curriculum.subjects():
        if text.upper() in (subject["short"].upper(), subject["code"].upper()):
            return subject["short"]
    return text.upper()


def by_course(course_code: str) -> list[dict]:
    wanted = short(course_code)
    return [row for row in catalogue() if short(row["course"]) == wanted]


def unit_title(course: str, unit: int) -> str:
    """The title of one unit, for a citation line that reads like the syllabus does."""
    found = curriculum.subject(short(course))
    if found is None:
        return ""
    for row in found["units"]:
        if row["unit"] == int(unit):
            return str(row["title"])
    return ""


def coverage() -> dict:
    """How much of each course is running as code, and how much is only listed."""
    rows = {}
    for subject in curriculum.subjects():
        code = subject["code"]
        total = sum(len(unit["topics"]) for unit in subject["units"])
        running = len({row["topic"] for row in by_course(code)})
        rows[subject["short"]] = {"code": code, "topics": total, "implemented": running}
    return rows
