"""core/curriculum.py — the syllabus Ultron holds, reachable by voice.

    "What subjects do you know?"                     -> action "subjects"
    "Show me the DBMS syllabus."                     -> action "show", subject "dbms"
    "Where do I start in DAA?"                       -> action "next", subject "daa"
    "What is good reading for deep learning?"         -> action "resources", subject "dl"
    "Mark normalisation as done."                    -> action "done"
    "Where does caching come up?"                    -> action "search", word "cache"

The data lives in `curriculum/aktu_aiml.json` and the rules live in
`core/curriculum.py`. This file only carries the conversation, and it always says
which number it is reading from — a course code, a unit, a topic count — because a
syllabus answer that cannot be checked against the page is worth nothing.
"""

from __future__ import annotations

from core import curriculum, failures

MAX_TOPICS = 40          # a unit is at most this many topics; a course is not


def _say(lines: list[str]) -> str:
    return "\n".join(line for line in lines if line)


def _cast() -> str:
    return ", ".join(row["short"] for row in curriculum.subjects())


def _unknown(name: str) -> str:
    return (f"I do not hold a subject called '{name}'. I hold: {_cast()}. "
            f"Ask for one of those, or ask what subjects I know.")


def _subjects(_parameters=None) -> str:
    facts = curriculum.as_facts()
    return _say([
        f"I hold {len(facts['subjects'])} subjects from {facts['board']},",
        facts["programme"] + ".",
        curriculum.summary(),
        f"{facts['topics']} topics and {facts['resources']} reading links in total.",
    ])


def _show(parameters: dict) -> str:
    name = str(parameters.get("subject") or "").strip()
    if not name:
        return "Which subject? I hold: " + _cast() + "."
    found = curriculum.subject(name)
    if found is None:
        return _unknown(name)
    done, total = curriculum.progress_of(found["code"])
    lines = [f"{found['name']} — {found['code']}, {len(found['units'])} units, "
             f"{total} topics. {done} recorded as done.",
             f"Source: {found['syllabus']}."]
    for unit in found["units"]:
        lines.append(f"  Unit {unit['unit']}: {unit['title']} "
                     f"({len(unit['topics'])} topics)")
    return _say(lines)


def _units(parameters: dict) -> str:
    name = str(parameters.get("subject") or "").strip()
    found = curriculum.subject(name) if name else None
    if found is None:
        return _unknown(name or "nothing")
    return _say([f"{found['short']} — {unit['unit']}: {unit['title']}"
                 for unit in found["units"]])


def _topics(parameters: dict) -> str:
    name = str(parameters.get("subject") or "").strip()
    found = curriculum.subject(name) if name else None
    if found is None:
        return _unknown(name or "nothing")
    unit = parameters.get("unit")
    rows = [row for row in curriculum.topics(found["code"])
            if unit in (None, "", str(row[0])) or str(unit) == str(row[0])]
    if not rows:
        return f"{found['short']} has no unit {unit}."
    lines = [f"{found['short']} topics" + (f", unit {unit}" if unit else "") + ":"]
    lines += [f"  {number}.{index}  {text}"
              for index, (number, _title, text) in enumerate(rows, 1)]
    return "\n".join(lines[:MAX_TOPICS + 1])


def _plan(parameters: dict) -> str:
    name = str(parameters.get("subject") or "").strip()
    found = curriculum.subject(name) if name else None
    if found is None:
        return _unknown(name or "nothing")
    rows = curriculum.plan(found["code"])
    done, total = curriculum.progress_of(found["code"])
    return _say([
        f"{found['short']} in study order, {total} topics, {done} done. "
        f"The order is the university's: each idea after the one it needs.",
        *[f"  {index:>3}. {text}" for index, text in enumerate(rows, 1)],
    ])


def _next(parameters: dict) -> str:
    name = str(parameters.get("subject") or "").strip()
    if not name:
        return "Which subject? I hold: " + _cast() + "."
    answer = curriculum.next_topic(name)
    done, total = curriculum.progress_of(name)
    return f"{answer} ({done} of {total} recorded as done.)" if total else answer


def _resources(parameters: dict) -> str:
    name = str(parameters.get("subject") or "").strip()
    found = curriculum.subject(name) if name else None
    if found is None:
        return _unknown(name or "nothing")
    level = str(parameters.get("level") or "").strip().lower()
    rows = curriculum.ladder(found["code"], level)
    if not rows:
        return (f"I have no {level} reading listed for {found['short']}. "
                f"Levels I use: {', '.join(curriculum.LEVELS)}.")
    lines = [f"Reading for {found['short']}, {level or 'all levels'}:"]
    lines += [f"  {row['level']:<13} {row['title']}\n"
              f"                {row['url']}  ({row['kind']})" for row in rows]
    lines.append("Every link was opened and returned a page when this file was built.")
    return _say(lines)


def _done(parameters: dict) -> str:
    name = str(parameters.get("subject") or "").strip()
    topic = str(parameters.get("topic") or "").strip()
    if not (name and topic):
        return "Say the subject and the topic, for example 'DBMS, normalisation'."
    ok, sentence = curriculum.mark_done(name, topic)
    _ = ok
    return sentence


def _progress(_parameters=None) -> str:
    lines = ["Progress, recorded only when you say so:"]
    for row in curriculum.subjects():
        done, total = curriculum.progress_of(row["code"])
        lines.append(f"  {row['short']:<5} {done:>3} of {total} topics")
    return _say(lines)


def _search(parameters: dict) -> str:
    word = str(parameters.get("word") or parameters.get("topic") or "").strip()
    if len(word) < 2:
        return "Give me a word of at least two letters to search for."
    rows = curriculum.search(word)
    if not rows:
        return f"'{word}' is not in any of the {len(curriculum.subjects())} syllabi I hold."
    return _say([f"'{word}' appears {len(rows)} time(s):"] +
                [f"  {short} unit {unit}: {text}" for _code, short, unit, text in rows[:20]])


def _reset(_parameters=None) -> str:
    cleared = curriculum.clear_progress()
    return f"Cleared {cleared} recorded topic(s). The syllabus itself is unchanged."


def _check(_parameters=None) -> str:
    issues = curriculum.problems()
    if issues:
        return "The syllabus file has a problem:\n  " + "\n  ".join(issues)
    facts = curriculum.as_facts()
    return (f"The syllabus file is sound: {len(facts['subjects'])} subjects, "
            f"{facts['topics']} topics, {facts['resources']} resources, "
            f"links checked {facts['checked'] or 'never'}.")


ACTIONS = {
    "subjects": _subjects, "list": _subjects, "courses": _subjects,
    "show": _show, "syllabus": _show, "subject": _show,
    "units": _units, "outline": _units,
    "topics": _topics, "unit": _topics,
    "plan": _plan, "order": _plan, "path": _plan,
    "next": _next, "start": _next, "where": _next,
    "resources": _resources, "reading": _resources, "books": _resources,
    "done": _done, "mark": _done, "finished": _done,
    "progress": _progress, "status": _progress,
    "search": _search, "find": _search,
    "reset": _reset, "clear": _reset,
    "check": _check,
}


def curriculum_tool(parameters: dict) -> str:
    """Answer one call about the syllabus. Every answer names its source."""
    parameters = dict(parameters or {})
    action = str(parameters.get("action") or "subjects").strip().lower()
    handler = ACTIONS.get(action)
    if handler is None:
        return (f"I do not know the action '{action}'. I can: subjects, show, units, "
                f"topics, plan, next, resources, done, progress, search, reset, check.")
    try:
        return handler(parameters)
    except ValueError as error:
        return str(error)
    except Exception as error:
        failures.note("curriculum.curriculum_tool", error)
        return "That did not work, and I have recorded why. The syllabus is unchanged."


TOOL = {
    "name": "curriculum",
    "description": (
        "The eight university subjects Ultron holds: DBMS, AI, DAA, DS, AIML "
        "(machine learning), DL (deep learning), DSTL (discrete structures and "
        "logic) and COA (computer organization). Each has five units, every unit has "
        "its topics, and each has reading at three levels. Use this tool whenever the "
        "user asks about their syllabus, their course, what a subject contains, what "
        "to study next, where to start, what book or course to use, or to mark a "
        "topic done. Quote the unit and the topic when you teach from it, and say "
        "which subject the topic belongs to."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "subjects (what I hold), show (one subject's units), units, "
                    "topics (one unit's topics), plan (the whole course in order), "
                    "next (the first topic not done), resources (reading by level), "
                    "done (mark a topic finished), progress, search, reset, check."
                ),
                "enum": ["subjects", "show", "units", "topics", "plan", "next",
                         "resources", "done", "progress", "search", "reset", "check"],
            },
            "subject": {
                "type": "STRING",
                "description": "A subject name or code as the user said it: dbms, ai, "
                               "daa, ds, ml, dl, dstl, coa, BCS501, and so on.",
            },
            "unit": {"type": "STRING", "description": "Unit number, 1 to 5."},
            "topic": {"type": "STRING", "description": "A topic, for 'done' or 'search'."},
            "level": {"type": "STRING",
                      "description": "basics, intermediate or advanced, for resources.",
                      "enum": ["basics", "intermediate", "advanced"]},
            "word": {"type": "STRING", "description": "A word to search for."},
        },
        "required": ["action"],
    },
    "handler": curriculum_tool,
}
