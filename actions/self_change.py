"""Changing its own source — reachable by voice, one shown step at a time.

    "Change line X of actions/open_app.py so it stops printing twice."
        -> action "propose", path, find, replace, reason
    "Try it."          -> action "rehearse"   (in a copy, never on the body)
    "Yes, do it."      -> action "confirm", channel voice
    a click in the panel -> action "confirm", channel panel
    "Apply it."        -> action "apply"
    "Put that back."   -> action "revert"

The rules live in `core/self_change.py`. This file carries the conversation, and it
never claims a stage that has not happened: a proposal is not a change, a rehearsal
is not an application, and an applied `.py` file is not running until the process
starts again. Every one of those three sentences exists because saying otherwise
would be a lie the owner could not see.
"""

from __future__ import annotations

from core import failures, self_change


def _say(lines: list[str]) -> str:
    return "\n".join(line for line in lines if line)


def _propose(parameters: dict) -> str:
    path = str(parameters.get("path") or "").strip()
    reason = str(parameters.get("reason") or "").strip()
    if not path:
        return "Which file? Give me a path inside the project, for example core/fuzzy.py."
    if not reason:
        return ("A change to my own source needs a reason recorded beside it. Say what "
                "this is for, and I will stage it.")
    proposal = self_change.propose(
        path, reason,
        new_text=parameters.get("text"),
        find=parameters.get("find"),
        replace=parameters.get("replace"),
    )
    return _say([
        "Staged, not applied. Nothing in my body has changed.",
        self_change.describe(proposal["id"]),
        "",
        self_change.diff(proposal["id"], limit=20),
        "",
        "Next: rehearse it in a copy, then confirm twice in two different places.",
    ])


def _rehearse(parameters: dict) -> str:
    proposal_id = str(parameters.get("change") or parameters.get("proposal") or "").strip()
    if not proposal_id:
        return "Which change? Ask for 'pending' and I will name them."
    result = self_change.rehearse(proposal_id, full=bool(parameters.get("full")))
    if result["ok"]:
        return _say([
            f"The copy passed: {result['command']}",
            "Nothing in the project was written — that ran in a temporary copy of the "
            "tree.",
            "Next: two confirmations, in two different places, then 'apply'.",
        ])
    return _say([
        f"The copy failed: {result['command']} exited {result['code']}.",
        result["tail"] or "(no output)",
        "Nothing was written to my body. Fix the change and stage it again.",
    ])


def _confirm(parameters: dict) -> str:
    proposal_id = str(parameters.get("change") or parameters.get("proposal") or "").strip()
    if not proposal_id:
        return "Which change? Ask for 'pending' and I will name them."
    channel = str(parameters.get("channel") or "voice").strip().lower()
    return self_change.confirm(proposal_id, channel)


def _apply(parameters: dict) -> str:
    proposal_id = str(parameters.get("change") or parameters.get("proposal") or "").strip()
    if not proposal_id:
        return "Which change? Ask for 'pending' and I will name them."
    result = self_change.apply(proposal_id)
    lines = [f"Applied: {result['path']}.", result["note"]]
    marker = self_change.restart_required()
    if marker and marker.get("change") == proposal_id:
        lines.append(f"To run it: {self_change.restart_command()}")
    return _say(lines)


def _revert(parameters: dict) -> str:
    proposal_id = str(parameters.get("change") or parameters.get("proposal") or "").strip()
    if not proposal_id:
        return ("Which change? Ask for 'history' and I will name them. Putting one "
                "back is not a guess I will make.")
    return self_change.revert(proposal_id)


def _pending(_parameters=None) -> str:
    rows = self_change.pending()
    if not rows:
        return "No change to my own source is waiting. Nothing has been staged."
    return _say(["Changes I have staged:"] + [
        f"  {row['id']}  {row['path']}  [{row['stage']}]  "
        f"{'rehearsed' if row['rehearsed'] else 'not rehearsed'}  — {row['reason']}"
        for row in rows])


def _show(parameters: dict) -> str:
    proposal_id = str(parameters.get("change") or parameters.get("proposal") or "").strip()
    if not proposal_id:
        return _pending(parameters)
    return _say([self_change.describe(proposal_id), "",
                 self_change.diff(proposal_id)])


def _history(_parameters=None) -> str:
    rows = self_change.ledger()
    if not rows:
        return "I have never changed my own source."
    return _say(["Changes to my own body, newest first:"] + [
        f"  {row.get('at')}  {row.get('event', '?'):<10}  {row.get('path') or ''}  "
        f"{row.get('reason') or ''}".rstrip() for row in rows])


def _rules(_parameters=None) -> str:
    return _say([
        "Five stages, in order, and no other door: propose, rehearse, confirm, apply, "
        "revert.",
        "Rehearsal runs in a copy of the tree, so a broken draft costs a temporary "
        "folder and never the body.",
        f"Two confirmations, in two different places: {', '.join(self_change.CHANNELS)}.",
        "The referee is off limits: " + ", ".join(self_change.PROTECTED) + ".",
        "A code change runs when the process starts again. The session survives "
        "because its state is in files.",
        "Every applied change keeps the bytes it replaced, so 'revert' is true.",
    ])


ACTIONS = {
    "propose": _propose, "stage": _propose, "change": _propose,
    "rehearse": _rehearse, "test": _rehearse, "try": _rehearse,
    "confirm": _confirm, "approve": _confirm,
    "apply": _apply, "commit": _apply,
    "revert": _revert, "undo": _revert, "restore": _revert,
    "pending": _pending, "list": _pending,
    "show": _show, "diff": _show,
    "history": _history, "ledger": _history,
    "rules": _rules, "limits": _rules,
}


def self_modify(parameters: dict) -> str:
    """Stage, rehearse, confirm, apply or revert a change to Ultron's own source."""
    parameters = dict(parameters or {})
    action = str(parameters.get("action") or "pending").strip().lower()
    handler = ACTIONS.get(action)
    if handler is None:
        return (f"I do not know the action '{action}'. I can: propose, rehearse, "
                f"confirm, apply, revert, pending, show, history, rules.")
    try:
        return handler(parameters)
    except ValueError as error:
        return str(error)
    except Exception as error:
        failures.note("self_change.self_modify", error)
        return "That did not work, and I have recorded why. Nothing was written."


TOOL = {
    "name": "self_modify",
    "description": (
        "Change Ultron's own source code, safely and in the open. Use when the user asks "
        "you to change your own code, repair a fault in yourself, or add a "
        "capability to yourself. Use 'propose' with a "
        "path inside the project plus either 'text' (the whole new file) or 'find' and "
        "'replace' (one passage), and a 'reason'. Then 'rehearse' runs the change in a "
        "temporary copy of the project with the test harness, 'confirm' twice in two "
        "different channels (voice, panel, cli), and only then 'apply'. 'revert' puts "
        "back the exact bytes that were replaced. Never say a change is active before "
        "'apply' has returned the applied message, and never say it is running if the "
        "answer says a restart is required. Files that decide permissions or record "
        "changes are refused on purpose."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": ("propose | rehearse | confirm | apply | revert | "
                                "pending | show | history | rules"),
                "enum": ["propose", "rehearse", "confirm", "apply", "revert",
                         "pending", "show", "history", "rules"],
            },
            "path": {"type": "STRING",
                     "description": "A file inside the project, e.g. actions/open_app.py"},
            "reason": {"type": "STRING", "description": "Why this change is being made."},
            "find": {"type": "STRING", "description": "The exact passage to replace."},
            "replace": {"type": "STRING", "description": "What that passage becomes."},
            "text": {"type": "STRING", "description": "The whole new file, if replacing it."},
            "change": {"type": "STRING", "description": "The proposal id, e.g. c1a2b3c4d5e6f."},
            "channel": {"type": "STRING",
                        "description": "Where the confirmation came from: voice | panel | cli."},
            "full": {"type": "BOOLEAN",
                     "description": "Run the whole test suite in the copy, not just a "
                                    "compile check."},
        },
        "required": ["action"],
    },
    "handler": self_modify,
}
