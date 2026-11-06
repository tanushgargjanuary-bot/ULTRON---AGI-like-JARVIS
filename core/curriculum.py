"""core/curriculum.py — the eight subjects Ultron holds, from basics to advanced.

The owner uploaded his AKTU syllabus for B.Tech CSE (AI & ML) and asked for the
topics to live inside Ultron, with material to take each subject from basics to
advanced. This module is the shelf:

    curriculum/aktu_aiml.json    the data — 8 subjects, 40 units, 284 topics,
                                 42 checked resources

Data, not code. The topics are facts about a university course: they belong in a
file a person can read and correct, not in a Python literal. Four subjects (DBMS,
AI, DAA, AIML) come from the PDF the owner supplied. Three (DS, DSTL, COA) are
earlier AKTU courses that are not in that PDF, so their unit outlines come from the
university's published outline. DL is a standard curriculum, because the whole point
of the subject is that the field moves faster than a syllabus.

WHAT THIS MODULE DOES NOT DO
    It does not teach. It says what the course contains, in what order, and where
    the good reading is. The teaching is the model's job, at the moment of asking.
    That split matters: a syllabus is stable for years, an explanation is not.

PROGRESS IS OPT-IN
    Nothing is recorded until the owner says a topic is done. What is recorded is one
    list of topic keys in the settings file, and "what is next" is derived from it.
"""

from __future__ import annotations

import json
from pathlib import Path

from memory import config_manager

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "curriculum" / "aktu_aiml.json"

LEVELS = ("basics", "intermediate", "advanced")
PROGRESS_KEY = "curriculum_done"

_loaded: dict | None = None


def load() -> dict:
    """The curriculum file, read once and kept.

    A missing or damaged file is an empty shelf rather than a crash: the app has to
    start whether or not a data file survived, and `problems()` says what is wrong.
    """
    global _loaded
    if _loaded is None:
        try:
            _loaded = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _loaded = {"subjects": [], "board": "", "programme": "", "note": ""}
    return _loaded


def reload() -> dict:
    """Drop the cache. For a test, or for after an edit to the file."""
    global _loaded
    _loaded = None
    return load()


def subjects() -> list[dict]:
    return list(load().get("subjects") or [])


def _keys(subject: dict) -> set[str]:
    raw = {subject.get("code", ""), subject.get("short", ""), subject.get("name", "")}
    raw |= set(subject.get("aliases") or [])
    return {str(key).strip().lower() for key in raw if key}


def resolve(name: str) -> str | None:
    """The course code for a spoken name: 'dbms', 'Database', 'BCS501' all work."""
    wanted = str(name or "").strip().lower()
    if not wanted:
        return None
    for subject in subjects():
        if wanted in _keys(subject):
            return subject["code"]
    # A phrase that contains exactly one subject's name, e.g. "the DBMS syllabus".
    found = [subject["code"] for subject in subjects()
             if any(len(key) > 2 and key in wanted for key in _keys(subject))]
    return found[0] if len(found) == 1 else None


def subject(name: str) -> dict | None:
    code = resolve(name)
    if code is None:
        return None
    return next((row for row in subjects() if row["code"] == code), None)


def units(name: str) -> list[dict]:
    found = subject(name)
    return list(found["units"]) if found else []


def topics(name: str) -> list[tuple[int, str, str]]:
    """Every topic as (unit number, unit title, topic), in course order."""
    rows = []
    for unit in units(name):
        for topic in unit["topics"]:
            rows.append((unit["unit"], unit["title"], topic))
    return rows


def plan(name: str) -> list[str]:
    """The whole course in the order to study it, one topic per line.

    The order is the university's: unit by unit. A student who follows it meets each
    idea after the idea it depends on, which is the only ordering claim this file
    makes — it does not pretend to know a cleverer one.
    """
    return [topic for _unit, _title, topic in topics(name)]


def key(code: str, unit: int, topic: str) -> str:
    return f"{code}#{unit}#{topic}"


def done() -> list[str]:
    value = config_manager.get_curriculum_progress().get(PROGRESS_KEY)
    return [str(item) for item in value] if isinstance(value, list) else []


def mark_done(name: str, topic: str, unit: int | None = None) -> tuple[bool, str]:
    """Record one topic as done. Returns (recorded, the sentence to say)."""
    found = subject(name)
    if found is None:
        return False, f"I do not hold a subject called '{name}'."
    rows = [(number, title, text) for number, title, text in topics(found["code"])
            if text.lower() == str(topic).strip().lower()
            or str(topic).strip().lower() in text.lower()]
    if not rows:
        return False, f"'{topic}' is not one of the topics in {found['short']}."
    chosen = [row for row in rows if unit is None or row[0] == unit] or rows
    number, _title, text = chosen[0]
    entry = key(found["code"], number, text)
    kept = done()
    if entry in kept:
        return True, f"'{text}' was already recorded as done."
    kept.append(entry)
    config_manager.save_curriculum_progress({PROGRESS_KEY: kept})
    return True, f"Recorded: '{text}' ({found['short']}, unit {number})."


def clear_progress() -> int:
    kept = done()
    config_manager.save_curriculum_progress({PROGRESS_KEY: []})
    return len(kept)


def next_topic(name: str) -> str:
    """The first topic in course order that is not recorded as done."""
    found = subject(name)
    if found is None:
        return f"I do not hold a subject called '{name}'."
    finished = set(done())
    for number, title, text in topics(found["code"]):
        if key(found["code"], number, text) not in finished:
            return (f"Next in {found['short']}: unit {number}, {title} — {text}.")
    return f"Every topic in {found['short']} is recorded as done. Say 'reset' to start again."


def progress_of(name: str) -> tuple[int, int]:
    found = subject(name)
    if found is None:
        return (0, 0)
    finished = set(done())
    total = len(topics(found["code"]))
    return (sum(1 for number, _t, text in topics(found["code"])
                if key(found["code"], number, text) in finished), total)


def ladder(name: str, level: str | None = None) -> list[dict]:
    """The reading, filtered to one level: basics, intermediate or advanced."""
    found = subject(name)
    if found is None:
        return []
    rows = list(found.get("ladder") or [])
    wanted = str(level or "").strip().lower()
    return [row for row in rows if row["level"] == wanted] if wanted else rows


def search(word: str) -> list[tuple[str, str, int, str]]:
    """Every topic containing a word, as (code, short, unit, topic)."""
    needle = str(word or "").strip().lower()
    if len(needle) < 2:
        return []
    found = []
    for row in subjects():
        for unit in row["units"]:
            for topic in unit["topics"]:
                if needle in topic.lower():
                    found.append((row["code"], row["short"], unit["unit"], topic))
    return found


def summary() -> str:
    """One line per subject: code, name, units, topics."""
    rows = []
    for row in subjects():
        count = sum(len(unit["topics"]) for unit in row["units"])
        rows.append(f"  {row['short']:<5} {row['code']:<8} {row['name']} — "
                    f"{len(row['units'])} units, {count} topics")
    return "\n".join(rows)


def problems() -> list[str]:
    """What is wrong with the data file, in sentences. Empty means nothing is."""
    issues = []
    if not subjects():
        return [f"the curriculum file {DATA_PATH} is missing or empty"]
    seen = set()
    for row in subjects():
        code = row.get("code")
        if not code:
            issues.append("a subject has no course code")
            continue
        if code in seen:
            issues.append(f"{code} appears twice")
        seen.add(code)
        if not row.get("units"):
            issues.append(f"{code} has no units")
        for unit in row.get("units") or []:
            if not unit.get("topics"):
                issues.append(f"{code} unit {unit.get('unit')} has no topics")
        for item in row.get("ladder") or []:
            if item.get("level") not in LEVELS:
                issues.append(f"{code} has a resource at unknown level "
                              f"'{item.get('level')}'")
    return issues


def as_facts() -> dict:
    return {
        "board": load().get("board", ""),
        "programme": load().get("programme", ""),
        "subjects": [row["code"] for row in subjects()],
        "topics": sum(len(unit["topics"]) for row in subjects() for unit in row["units"]),
        "resources": sum(len(row.get("ladder") or []) for row in subjects()),
        "checked": load().get("checked", ""),
    }
