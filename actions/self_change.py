"""Changing its own source — reachable by voice, one shown step at a time.

    "Change line X of actions/open_app.py so it stops printing twice."
        -> action "propose", path, find, replace, reason
    "Try it."          -> action "rehearse"   (in a copy, never on the body)
    "Yes, do it."      -> action "confirm": the yes is recorded and a CONFIRM banner goes
                          up with every changed line
    a press on that banner -> the second confirmation
    "Apply it."        -> action "apply"
    "Put that back."   -> action "revert"

The rules live in `core/self_change.py`. This file carries the conversation, and it
never claims a stage that has not happened: a proposal is not a change, and a
rehearsal is not an application. Action/plugin leaves can be staged only at the
next provider reconnect boundary; other code still requires a process restart.
Every one of those sentences exists because saying otherwise would be a lie the
owner could not see.

THE SECOND PLACE IS THE ONE THE MODEL CANNOT REACH
    The two confirmations used to be two `confirm` calls whose `channel` argument the MODEL wrote
    ("voice", then "panel"), so what stood between a model and an applied change was only the
    approval banner on each call, which shows call arguments and not the change. Now `confirm`
    records the first yes (the model's report that the owner said it; this code never hears the
    audio) and puts the CONFIRM banner up (`core/confirm.py`). The banner lists every changed line,
    written out (`core/display_text.py`). The second confirmation is recorded only when the owner
    presses the button, and only if the change on the banner is still the staged one. The tool takes
    no `channel` argument any more, and ignores one if a model sends it. It is the same gate the
    system prompt has (`actions/prompt_editor.py`).

    A change with more than BANNER_CHANGE_LIMIT characters of difference is not put on a banner at
    all: a cut would be a part of the change nobody saw, and the press approves all of it.
"""

from __future__ import annotations

from core import boot_guard, crash, display_text, failures, self_change
from core import confirm as hud
from core.confirm import request as put_up_the_banner      # not `hud.request`: see scripts/deep_scan.py

# What the owner is asked to read before pressing CONFIRM, in characters of difference. The banner
# scrolls, so this is a limit on what a person can fairly be asked to read, not on what fits. A change
# with more difference than this is REFUSED at `confirm`, never cut. (About two hundred lines of code.)
BANNER_CHANGE_LIMIT = 8000
# The model writes the reason and the banner shows it above the change. Left unbounded it would fill
# the banner, and the owner would read a reassuring paragraph and have to scroll for the change.
REASON_LIMIT = 200
SHOW_LIMIT = 200            # rows `show` hands back to the model; the banner has every one


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
    unreadable = _too_big_to_read(self_change.review(proposal["id"]))
    return _say([
        "Staged, not applied. Nothing in my body has changed.",
        self_change.describe(proposal["id"]),
        "",
        self_change.diff(proposal["id"], limit=20),
        "",
        unreadable or "Next: rehearse it in a copy. Then 'confirm' puts a button on the screen "
                      "with every changed line, and pressing it is the second confirmation.",
    ])


def _rehearse(parameters: dict) -> str:
    proposal_id = str(parameters.get("change") or parameters.get("proposal") or "").strip()
    if not proposal_id:
        return "Which change? Ask for 'pending' and I will name them."
    # Model-generated source must pass the full harness, not merely compile.
    # A caller cannot opt out by setting a model-controlled `full: false` flag.
    result = self_change.rehearse(proposal_id, full=True)
    if result["ok"]:
        return _say([
            f"The full test harness passed in the copy: {result['command']}",
            "Nothing in the project was written — that ran in a temporary copy of the "
            "tree.",
            "Next: 'confirm' puts a button on the screen with every changed line. Your yes and "
            "your press of that button are the two confirmations; then 'apply'.",
        ])
    return _say([
        f"The copy failed: {result['command']} exited {result['code']}.",
        result["tail"] or "(no output)",
        "Nothing was written to my body. Fix the change and stage it again.",
    ])


def _banner_text(view: dict) -> str:
    """Every changed line, written out so that it reads as it is (see core/display_text.py)."""
    return display_text.visible("\n".join(view["rows"])) or "(no line differs)"


def _too_big_to_read(view: dict | None) -> str:
    """'' when the owner can be shown the whole change; otherwise the sentence that says he cannot."""
    if view is None:
        return ""
    size = len(_banner_text(view))
    if size <= BANNER_CHANGE_LIMIT:
        return ""
    return (f"That change is {size:,} characters of difference, more than I can fairly ask you to read "
            f"on the screen ({BANNER_CHANGE_LIMIT:,}). I will not put up a button for it, and nothing "
            f"was applied. Stage it again as several smaller changes.")


def _banner_detail(view: dict) -> str:
    """What the banner carries: where, why (bounded), what was run, then every changed line."""
    reason = display_text.one_line(view["reason"] or "no reason given", REASON_LIMIT)
    rehearsal = view["rehearsal"]
    ran = ("the full test harness passed in a copy" if rehearsal.get("full")
           else "only a compile check passed in a copy")
    return (f"{view['id']}: {view['path']}\n"
            f"Reason, as the model wrote it: {reason}\n"
            f"Rehearsal: {ran} ({rehearsal.get('at', '?')})\n"
            f"Every changed line ({len(view['rows'])}):\n{_banner_text(view)}")


def _confirm(parameters: dict) -> str:
    """Record the first yes, then ask the owner for the press that decides.

    The `channel` argument is ignored if the model sends one. See the module note.
    """
    proposal_id = str(parameters.get("change") or parameters.get("proposal") or "").strip()
    if not proposal_id:
        return "Which change? Ask for 'pending' and I will name them."
    view = self_change.review(proposal_id)
    if view is None:
        return f"I have no change called '{proposal_id}'."
    if not view["rehearsed"]:
        return (f"{proposal_id} has not passed a rehearsal, so there is nothing to confirm yet. "
                f"Rehearse it first: it runs the full test harness in a copy, and costs a copy, "
                f"not a body.")
    unreadable = _too_big_to_read(view)
    if unreadable:
        return unreadable                   # before the yes is recorded: nothing happened at all
    if "panel" in view["confirmations"]:
        return f"{proposal_id} is already confirmed twice. Say 'apply' when you want it written."
    recorded = ""
    if "voice" not in view["confirmations"]:
        self_change.confirm(proposal_id, "voice")
        recorded = f"Your yes is recorded (1 of {self_change.CONFIRMATIONS})."
    if hud.pending_title():
        return (f"Another confirmation is waiting on the screen. Answer that one first. "
                f"{proposal_id} has not been applied.")
    shown = view["digest"]

    def after_the_press() -> str:
        # Runs only when the owner presses CONFIRM, on a worker thread. If the staged change is not
        # the one that was on the banner, nothing is recorded.
        current = self_change.review(proposal_id)
        if current is None:
            return f"{proposal_id} is gone, so nothing was recorded."
        if current["digest"] != shown:
            return f"{proposal_id} is not the change that was shown, so nothing was recorded."
        return self_change.confirm(proposal_id, "panel")

    asked = put_up_the_banner(f"self-{proposal_id}", "Change my own code", _banner_detail(view),
                              after_the_press)
    return " ".join(part for part in (recorded, asked) if part)


def _apply(parameters: dict) -> str:
    """Apply a validated self-change and report its outcome."""
    proposal_id = str(parameters.get("change") or parameters.get("proposal") or "").strip()
    if not proposal_id:
        return "Which change? Ask for 'pending' and I will name them."
    result = self_change.apply(proposal_id)
    marker = self_change.restart_required()
    net = ("If I am started with run.bat or run.ps1 and the new code does not stay up for "
           f"{int(boot_guard.HEALTHY_AFTER)} seconds, or end normally, the next start puts the old "
           "file back and says so. A start with 'python main.py' is not watched."
           if result.get("boot_watch") else "")
    changed_path = str(result.get("path") or "").replace("\\", "/")
    is_leaf = (changed_path.startswith(("actions/", "plugins/"))
               and changed_path.endswith(".py")
               and changed_path.split("/")[-1] != "__init__.py")
    if marker and marker.get("change") == proposal_id and is_leaf:
        lines = [
            f"Applied: {changed_path}.",
            "The current registry remains active until the next provider reconnect; "
            "then the action/plugin generation will be staged and checked.",
            f"To restart immediately instead: {self_change.restart_command()}",
            net,
        ]
    else:
        lines = [f"Applied: {result['path']}.", result["note"]]
        if marker and marker.get("change") == proposal_id:
            lines.append(f"To run it: {self_change.restart_command()}")
        lines.append(net)
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
                 self_change.diff(proposal_id, limit=SHOW_LIMIT)])


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
        "Every source rehearsal runs the full test harness in a copy of the tree; "
        "there is no compile-only bypass. A failed or incomplete run cannot be applied.",
        "Two confirmations, in two different places: your yes, which I report, and your press of "
        "the CONFIRM button on the screen, which lists every changed line. I cannot press it, and "
        "I cannot say that you did.",
        "The referee is off limits: " + ", ".join(self_change.PROTECTED) + ".",
        "A code change runs when the process starts again. The session survives "
        "because its state is in files. A start with run.bat or run.ps1 that does not stay up "
        "is followed by a start that puts the old file back.",
        "Every applied change keeps the bytes it replaced, so 'revert' is true.",
    ])


def _crashes(parameters: dict) -> str:
    """What actually broke, newest first — the evidence a repair should start from.

    Asked as "why did you crash", "what broke", "what went wrong lately". The answer
    reads the reports on disk, not a memory of them, and offers to show the traceback
    of the newest one, because the traceback is the part that names the fault.
    """
    try:
        wanted = int(parameters.get("count") or 3)
    except (TypeError, ValueError):
        wanted = 3
    rows = crash.history(limit=max(1, min(20, wanted)))
    if not rows:
        return ("I have no crash report on this machine. Either I have not crashed, or "
                "I crashed before I could write one down — a native fault is recorded "
                f"in {crash.folder()}/faulthandler.log if there is one.")
    lines = [f"I have {len(crash.paths())} crash report(s) in {crash.folder()}. "
             f"The newest {len(rows)}:"]
    for row in rows:
        lines.append(f"  {row.get('time', '?')} — {row.get('kind', '?')} at "
                     f"{row.get('where', '?')}: {row.get('message', '')[:120]}")
    if str(parameters.get("trace") or "").strip().lower() in ("1", "true", "yes"):
        lines.append("")
        lines.append(f"The newest traceback, from {rows[0]['path']}:")
        lines.append(crash.last_trace(root=None) or "  (the report holds no traceback)")
    else:
        lines.append(f"Ask again with trace to read {rows[0]['path']}, or propose a "
                     f"change with action=propose and I will start from this.")
    return _say(lines)


ACTIONS = {
    "crashes": _crashes, "crash": _crashes, "broke": _crashes, "why": _crashes,
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
        return (f"I do not know the action '{action}'. I can: crashes, propose, "
                f"rehearse, confirm, apply, revert, pending, show, history, rules.")
    try:
        with self_change.change_lock():
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
        "capability to yourself. Use 'crashes' when the user asks why you crashed or "
        "what broke lately: it reads the crash reports on disk, newest first, with the "
        "traceback on request, so a repair starts from the fault. Use 'propose' with a "
        "path inside the project plus either 'text' (the whole new file) or 'find' and "
        "'replace' (one passage), and a 'reason'. Then 'rehearse' runs the change in a "
        "temporary copy with the full test harness (no compile-only bypass). 'confirm' "
        "records the owner's yes and puts a CONFIRM button on the screen that lists every "
        "changed line; the owner pressing it is the second confirmation, and you cannot press "
        "it or say that it was pressed. Only then 'apply'. 'revert' puts "
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
                "description": ("crashes (what actually broke, newest first) | "
                                "propose | rehearse | confirm | apply | revert | "
                                "pending | show | history | rules"),
                "enum": ["crashes", "propose", "rehearse", "confirm", "apply",
                         "revert", "pending", "show", "history", "rules"],
            },
            "path": {"type": "STRING",
                     "description": "A file inside the project, e.g. actions/open_app.py"},
            "reason": {"type": "STRING", "description": "Why this change is being made."},
            "find": {"type": "STRING", "description": "The exact passage to replace."},
            "replace": {"type": "STRING", "description": "What that passage becomes."},
            "text": {"type": "STRING", "description": "The whole new file, if replacing it."},
            "change": {"type": "STRING", "description": "The proposal id, e.g. c1a2b3c4d5e6f."},
            "count": {"type": "INTEGER",
                      "description": "For crashes: how many reports to list, 1 to 20."},
            "trace": {"type": "BOOLEAN",
                      "description": "For crashes: also show the newest traceback."},
        },
        "required": ["action"],
    },
    "handler": self_modify,
}
