"""dev_json — look at JSON properly instead of guessing.

Four actions and no network: format, minify, validate, and read one value out by
a dotted path. Model output and config files both arrive malformed often enough
that "it is invalid at line 3, column 12" is worth more than a stack trace.
"""

import json

PLUGIN = {
    "name": "dev_json",
    "description": (
        "Formats, minifies, validates JSON or reads one value out of it by a "
        "dotted path (a.b.0.c). Use it when the user pastes JSON, asks why a "
        "JSON file is invalid, or wants one field from a JSON document."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING",
                       "description": "format | minify | validate | get"},
            "text": {"type": "STRING", "description": "The JSON text"},
            "path": {"type": "STRING",
                     "description": "For action=get: dotted path, for example user.name"},
        },
        "required": ["action", "text"],
    },
    "tier": "ROUTINE",
}

MAX_INPUT = 200_000


def _load(text):
    return json.loads(text)


def _walk(value, path):
    current = value
    for part in str(path or "").split("."):
        if not part:
            continue
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current[part]
        else:
            raise KeyError(f"'{part}' cannot be read from {type(current).__name__}")
    return current


def run(parameters, player=None, session_memory=None):
    action = str(parameters.get("action") or "validate").strip().lower()
    text = str(parameters.get("text") or "")
    if len(text) > MAX_INPUT:
        return f"That is too much JSON for me to read at once ({len(text)} characters)."
    if not text.strip():
        return "There is no JSON in that."

    try:
        data = _load(text)
    except json.JSONDecodeError as exc:
        return f"That JSON is not valid: {exc.msg} at line {exc.lineno}, column {exc.colno}."

    if action == "validate":
        kind = type(data).__name__
        size = len(data) if isinstance(data, (dict, list)) else 0
        return f"That JSON is valid. The top level is a {kind}" + (
            f" with {size} entries." if size else ".")
    if action == "format":
        return json.dumps(data, indent=2, ensure_ascii=False)[:8000]
    if action == "minify":
        return json.dumps(data, separators=(",", ":"), ensure_ascii=False)[:8000]
    if action == "get":
        try:
            value = _walk(data, parameters.get("path"))
        except (KeyError, IndexError, ValueError) as exc:
            return f"I could not read that path: {exc}"
        return json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    return "I can format, minify, validate or get a value. Which one?"
