"""dev_regex — test a pattern against text and show what it matched.

Regex is the tool people get wrong in their head. This runs the pattern and shows
the match, its groups and its spans, or says the pattern will not compile.

A pattern is untrusted input, so the work is bounded: the subject is capped, the
number of matches reported is capped, and the matching runs in a child process
with a two-second deadline. That last one is not caution, it is a bug fix: `re`
has no timeout, and `(a+)+$` against forty characters of "a" ran for ninety
seconds in this very plugin, which would freeze a turn and the window with it.
Nothing is executed: the child runs a fixed script that calls `re` and prints
JSON.
"""

import json
import re
import subprocess
import sys

PLUGIN = {
    "name": "dev_regex",
    "description": (
        "Tests a regular expression against text and reports the matches, their "
        "groups and their positions. Use it when the user is debugging a regex or "
        "asks what a pattern matches in a sample of text."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "pattern": {"type": "STRING", "description": "The regular expression"},
            "text": {"type": "STRING", "description": "The text to search"},
            "flags": {"type": "STRING",
                      "description": "Any of: i (ignore case), m (multiline), s (dotall)"},
            "count": {"type": "NUMBER", "description": "How many matches to report (default 20)"},
        },
        "required": ["pattern", "text"],
    },
    "tier": "ROUTINE",
}

MAX_TEXT = 50_000
MAX_MATCHES = 200
DEADLINE = 2.0

# The child runs this exact text, never a string built from the user's pattern.
# The pattern arrives as JSON on stdin, so no quoting or injection is possible.
_CHILD = """
import json, re, sys
request = json.load(sys.stdin)
flags = 0
for letter in request["flags"]:
    flags |= {"i": re.IGNORECASE, "m": re.MULTILINE, "s": re.DOTALL}.get(letter, 0)
pattern = re.compile(request["pattern"], flags)
out = []
for match in pattern.finditer(request["text"]):
    out.append([match.group(0), match.start(), match.end(),
                [group for group in match.groups()]])
    if len(out) >= request["limit"]:
        break
json.dump({"matches": out}, sys.stdout)
"""


def _flags(spec):
    value = 0
    for letter in str(spec or "").lower():
        value |= {"i": re.IGNORECASE, "m": re.MULTILINE, "s": re.DOTALL}.get(letter, 0)
    return value


def _match_child(pattern, text, flags, limit):
    """Run the search in a child process. Returns (matches, refusal)."""
    payload = json.dumps({"pattern": pattern, "text": text,
                          "flags": flags, "limit": limit})
    command = [sys.executable, "-c", _CHILD]
    hidden = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        done = subprocess.run(command, input=payload, capture_output=True,
                              text=True, timeout=DEADLINE, shell=False,
                              creationflags=hidden)
    except subprocess.TimeoutExpired:
        return None, (f"That pattern took longer than {DEADLINE:.0f} seconds. "
                      "It is almost certainly catastrophic backtracking — "
                      "rewrite the nested quantifiers.")
    except Exception as exc:                                   # noqa: BLE001
        return None, f"I could not run the pattern: {type(exc).__name__}: {exc}"
    if done.returncode != 0:
        reason = (done.stderr or "").strip().splitlines()
        return None, f"That pattern does not compile: {reason[-1] if reason else 'unknown error'}"
    try:
        return json.loads(done.stdout or "{}").get("matches", []), ""
    except ValueError:
        return None, "The pattern ran but its answer could not be read."


def run(parameters, player=None, session_memory=None):
    pattern = str(parameters.get("pattern") or "")
    text = str(parameters.get("text") or "")[:MAX_TEXT]
    limit = max(1, min(int(parameters.get("count") or 20), MAX_MATCHES))
    flags = str(parameters.get("flags") or "")
    if not pattern:
        return "I need a pattern to test."
    try:                                     # cheap: compile errors come back fast
        re.compile(pattern, _flags(flags))
    except re.error as exc:
        return f"That pattern does not compile: {exc}"

    matches, refusal = _match_child(pattern, text, flags, limit)
    if matches is None:
        return refusal
    if not matches:
        return f"No match for /{pattern}/ in {len(text)} characters."

    lines = [f"{len(matches)} match(es) for /{pattern}/:"[:120]]
    for index, (whole, start, end, groups) in enumerate(matches, 1):
        shown = str(whole).replace("\n", "\\n")
        lines.append(f"  {index}. '{shown[:80]}' at {start}-{end}")
        if groups:
            rendered = ", ".join(f"{i + 1}={g!r}" for i, g in enumerate(groups))
            lines.append(f"     groups: {rendered[:160]}")
    return "\n".join(lines)
