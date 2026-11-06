#!/usr/bin/env python3
"""Print the instruction Ultron gives the model — from a terminal, no app needed.

The owner asked for the system prompt to be visible to them. It is a text file, and
this is the shortest path from here to reading it:

    python scripts/show_prompt.py                 # the whole prompt, placeholders filled
    python scripts/show_prompt.py --template      # the exact file, placeholders intact
    python scripts/show_prompt.py --check         # the rules an edit has to pass
    python scripts/show_prompt.py --history       # what has been changed, and why
    python scripts/show_prompt.py --json          # for a script of your own

Inside the app the same text is one sentence away: ask Ultron to show it, or to
change it. Changes need two confirmations and every version is kept.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import prompt_store


def _check(as_json: bool) -> int:
    ok, problems = prompt_store.validate(prompt_store.read())
    if as_json:
        print(json.dumps({"ok": ok, "problems": problems,
                          "characters": prompt_store.size()}, indent=2))
    else:
        print(f"{prompt_store.size()} characters, all rules passed"
              if ok else "This prompt has a problem:")
        for problem in problems:
            print(f"  - {problem}")
    return 0 if ok else 1


def _history(as_json: bool) -> int:
    rows = prompt_store.history(limit=50)
    if as_json:
        print(json.dumps(rows, indent=2))
    elif not rows:
        print("My instruction has never been changed.")
    else:
        for row in rows:
            confirmed = ", ".join(row.get("confirmations") or [])
            print(f"{row['at']}  {row.get('reason') or '(no reason)'}  "
                  f"[{confirmed}]  {row['before']} -> {row['after']} chars")
    return 0


def _versions(as_json: bool) -> int:
    kept = prompt_store.versions()
    if as_json:
        print(json.dumps([item.name for item in kept], indent=2))
    else:
        print("\n".join(item.name for item in kept) or
              "No earlier version is kept yet.")
    return 0


def _text(as_template: bool, as_json: bool) -> int:
    text = prompt_store.read() if as_template else prompt_store.preview()
    if as_json:
        print(json.dumps({"characters": len(text), "template": as_template,
                          "path": str(prompt_store.PROMPT_PATH), "text": text},
                         indent=2))
        return 0
    print(text)
    if not as_template:
        print()
        print(f"— {len(text)} characters, placeholders filled for reading. "
              f"The file itself is {prompt_store.PROMPT_PATH}.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--template", action="store_true",
                        help="the file exactly as it is, placeholders unfilled")
    parser.add_argument("--check", action="store_true",
                        help="run the rules a change must pass against what is in use")
    parser.add_argument("--history", action="store_true",
                        help="every applied change, newest first")
    parser.add_argument("--versions", action="store_true",
                        help="the kept copies of earlier prompts")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    if args.check:
        return _check(args.json)
    if args.history:
        return _history(args.json)
    if args.versions:
        return _versions(args.json)
    return _text(args.template, args.json)


if __name__ == "__main__":
    sys.exit(main())
