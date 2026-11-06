"""dev_cron — explain a cron expression in words, and say when it runs next.

Five fields (minute hour day-of-month month day-of-week) or six with seconds. The
explanation comes from the fields themselves, so an unusual expression is
described correctly instead of being rejected.
"""

from datetime import datetime, timedelta

PLUGIN = {
    "name": "dev_cron",
    "description": (
        "Explains a cron expression in plain words and lists its next run times. "
        "Use it when the user asks what a cron line means or whether a schedule "
        "will actually fire."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "expression": {"type": "STRING",
                           "description": "Cron expression, for example 0 9 * * 1-5"},
            "count": {"type": "NUMBER", "description": "How many next runs (default 5)"},
        },
        "required": ["expression"],
    },
    "tier": "ROUTINE",
}

_NAMES = ["minute", "hour", "day of month", "month", "day of week"]

_SPECIAL = {
    "@yearly": "0 0 1 1 *", "@annually": "0 0 1 1 *", "@monthly": "0 0 1 * *",
    "@weekly": "0 0 * * 0", "@daily": "0 0 * * *", "@midnight": "0 0 * * *",
    "@hourly": "0 * * * *",
}

_RANGES = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]


def _parse(expression):
    text = str(expression or "").strip()
    text = _SPECIAL.get(text.lower(), text)
    parts = text.split()
    if len(parts) == 6:          # with seconds: ignore the seconds field
        parts = parts[1:]
    if len(parts) != 5:
        raise ValueError("a cron expression has five fields (or six with seconds)")
    for value, (low, high) in zip(parts, _RANGES):
        if value == "*":
            continue
        for chunk in value.split(","):
            head = chunk.split("/")[0]
            for edge in head.split("-"):
                if edge in ("*", ""):
                    continue
                number = int(edge)
                if not low <= number <= high:
                    raise ValueError(f"{number} is outside {low}-{high} for this field")
    return parts


def _field_words(value, index):
    name = _NAMES[index]
    if value == "*":
        return f"every {name}"
    if value.startswith("*/"):
        return f"every {value[2:]} {name}s"
    if "," in value or "-" in value:
        return f"{name} {value}"
    return f"{name} {value}"


def _next_runs(parts, count):
    minute, hour, dom, month, dow = parts
    def matches(field, value, low, high):
        if field == "*":
            return True
        for chunk in field.split(","):
            step = 1
            if "/" in chunk:
                chunk, _, step_text = chunk.partition("/")
                step = int(step_text or 1)
            if chunk == "*":
                if (value - low) % step == 0:
                    return True
                continue
            if "-" in chunk:
                start, _, end = chunk.partition("-")
                if int(start) <= value <= int(end) and (value - int(start)) % step == 0:
                    return True
                continue
            if value == int(chunk) and value >= low:
                return True
        return False

    runs = []
    moment = (datetime.now() + timedelta(minutes=1)).replace(second=0, microsecond=0)
    for _ in range(60 * 24 * 366):
        if (matches(minute, moment.minute, 0, 59)
                and matches(hour, moment.hour, 0, 23)
                and matches(dom, moment.day, 1, 31)
                and matches(month, moment.month, 1, 12)
                and matches(dow, moment.isoweekday() % 7, 0, 6)):
            runs.append(moment)
            if len(runs) >= count:
                break
        moment += timedelta(minutes=1)
    return runs


def run(parameters, player=None, session_memory=None):
    try:
        parts = _parse(parameters.get("expression"))
    except (ValueError, TypeError) as exc:
        return f"That cron expression is not valid: {exc}"

    words = ", ".join(_field_words(value, index) for index, value in enumerate(parts))
    count = max(1, min(int(parameters.get("count") or 5), 20))
    runs = _next_runs(parts, count)
    if not runs:
        return f"It means {words}, but I could not find a run in the next year."
    upcoming = ", ".join(run.strftime("%a %d %b %H:%M") for run in runs)
    return f"It means {words}. Next runs: {upcoming}."
