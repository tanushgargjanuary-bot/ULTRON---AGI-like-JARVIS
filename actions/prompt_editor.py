"""The system prompt, reachable by voice: read it, change it, go back.

The owner asked for two things in one sentence — that the model's system prompt be
visible to them, and that they be able to instruct Ultron to change it. This file is
the tool that does both, and it is deliberately the only door.

    "Show me your system prompt."              -> action "show"
    "Make your answers shorter from now on."   -> the model stages a "change"
    "Yes, do it."                              -> action "confirm": the yes is recorded
                                                  and a CONFIRM banner goes up
    then a click on that banner                -> the change is applied

Why a staged change instead of an immediate one: a model that can rewrite its own
instruction in one step can also delete the paragraphs that stop it from doing
something. Two confirmations, in two different places, mean the owner has read the
change twice before it exists. `core/prompt_store.py` holds the rules; this file
only carries the conversation.

THE SECOND PLACE IS THE ONE THE MODEL CANNOT REACH
    This tool is exempt from the approval banner (`policy.BYPASS_TOOLS`) on the
    ground that it carries a gate of its own. That gate used to be a `channel`
    argument — and the model wrote the argument. Three calls, "stage", "confirm voice",
    "confirm panel", and the prompt was rewritten with no person involved; measured,
    not argued. The model no longer says where a confirmation came from. `confirm`
    records the first yes (the model's report that the owner said it; this code never
    hears the audio) and puts the CONFIRM banner up (`core/confirm.py`); the second
    confirmation is recorded only when the owner presses the button — the one act
    only the interface can issue.

WHAT THE OWNER IS SHOWN
    The click approves the whole change, so the banner carries the whole change: every changed
    line, written out (`core/display_text.py`), under the id and the first REASON_LIMIT characters
    of the reason, which the model writes. A change with more than BANNER_CHANGE_LIMIT characters of
    difference is refused with a sentence, at `stage` and again at `confirm`: a cut would be a part
    of the change nobody saw. `ui.ConfirmBanner` draws the text as plain text in a box that scrolls.

Everything this tool returns is a sentence, because it is read aloud as often as it
is read on screen.
"""

from __future__ import annotations

import hashlib

from core import confirm as hud, display_text, failures, philosophy, prompt_store
from core.confirm import request as put_up_the_banner

MAX_PREVIEW = 20_000        # the whole prompt fits: the owner asked to see it
# What the owner is asked to read before pressing CONFIRM, in characters of difference. The
# banner scrolls, so this is a limit on what a person can fairly be asked to read, not on what
# fits. A change with more difference than this is REFUSED, never cut: a cut is the part of the
# change nobody saw, and the click approves all of it. (One prompt line is up to 866 characters,
# so an edit of two long lines is already about 3,500.)
BANNER_CHANGE_LIMIT = 4000
# The model writes the reason, and the banner shows it above the change. Left unbounded it would
# fill the banner, so the owner sees a reassuring paragraph and has to scroll for the change.
REASON_LIMIT = 200


def _say(lines: list[str]) -> str:
    return "\n".join(lines)


def _preview_block() -> list[str]:
    text = prompt_store.preview()
    if len(text) > MAX_PREVIEW:
        text = text[:MAX_PREVIEW] + "\n… (shortened to fit one answer)"
    return ["--- the system prompt ---", text, "--- end of the system prompt ---"]


def _show() -> str:
    lines = _preview_block()
    # The file is what a person edits, but it is not the whole of what the model is
    # given: the minds are added after it, at session start. Showing the file alone
    # would make "show me your prompt" a half-truth, and this tool exists because the
    # owner asked for the whole thing.
    block = philosophy.prompt_block()
    if block:
        lines += ["", "--- added after that file, when a session starts ---", block]
    lines.append(f"{prompt_store.size()} characters, from "
                 f"{prompt_store.PROMPT_PATH.name}. The tool list and the limits "
                 f"block are filled in when a session starts.")
    history = prompt_store.history(limit=3)
    if history:
        latest = history[0]
        lines.append(f"Last change: {latest['at']} — "
                     f"{latest.get('reason') or 'no reason given'}.")
    return _say(lines)


def _stage(parameters: dict) -> str:
    reason = str(parameters.get("reason") or "").strip()
    if not reason:
        return ("I will not stage a change to my own instruction without a reason "
                "recorded beside it. Say what this change is for.")
    text = parameters.get("text")
    find = parameters.get("find")
    if text:
        proposal = prompt_store.propose_text(str(text), reason=reason)
    elif find:
        replace = parameters.get("replace")
        if replace is None:
            return "To change one passage I need both 'find' and 'replace'."
        proposal = prompt_store.propose_replace(str(find), str(replace), reason=reason)
    else:
        return ("To stage a change I need either the whole new text, or the passage "
                "to find and what to put in its place.")
    unreadable = _too_big_to_read(proposal)
    return _say([
        "Staged, not applied. Nothing about me has changed yet.",
        prompt_store.describe(proposal),
        unreadable or f"To apply it: confirm twice, in two different places — "
                      f"{prompt_store.CONFIRMATIONS} confirmations of proposal {proposal.id}.",
    ])


def _digest(proposal) -> str:
    return hashlib.sha256((proposal.before + "\x00" + proposal.after).encode("utf-8")).hexdigest()


# Every changed line, in order. Written once, in core/display_text.py, for this banner and the
# self-change banner; the name stays so `tests/test_prompt_gate.py` still checks it here.
_diff_rows = display_text.diff_rows


def _changed_lines(proposal) -> str:
    """The whole difference, written out so that it reads as it is (see core/display_text.py)."""
    rows = _diff_rows(proposal.before, proposal.after)
    return display_text.visible("\n".join(rows)) or "(no line differs)"


def _banner_detail(proposal) -> str:
    """What the banner carries: the id and a bounded reason, then every changed line."""
    reason = display_text.one_line(proposal.reason or "no reason given", REASON_LIMIT)
    return f"{proposal.id}: {reason}\n{_changed_lines(proposal)}"


def _too_big_to_read(proposal) -> str:
    """'' when the owner can be shown the whole change; otherwise the sentence that says he cannot."""
    size = len(_changed_lines(proposal))
    if size <= BANNER_CHANGE_LIMIT:
        return ""
    return (f"That change is {size:,} characters of difference, more than I can fairly ask you to "
            f"read on the screen ({BANNER_CHANGE_LIMIT:,}). I have not put up a button for it, and "
            f"nothing was applied. Stage it again as several smaller changes.")


def _confirm(parameters: dict) -> str:
    """Record the first yes, then ask the owner for the click that decides.

    The `channel` argument is ignored if the model sends one. See the module note.
    """
    proposal_id = str(parameters.get("proposal") or "").strip()
    if not proposal_id:
        return "Which proposal? Ask me for 'pending' and I will name them."
    proposal = prompt_store.load(proposal_id)
    proposal_id = proposal.id
    unreadable = _too_big_to_read(proposal)
    if unreadable:
        return unreadable                 # before the yes is recorded: nothing happened at all
    recorded = ""
    if not any(entry.get("channel") == "voice" for entry in proposal.confirmations):
        recorded = prompt_store.confirm(proposal_id, "voice")
        proposal = prompt_store.load(proposal_id)
    if hud.pending_title():
        return ("Another confirmation is waiting on the screen. Answer that one first. "
                f"{proposal_id} has not been applied.")
    shown = _digest(proposal)

    def after_the_click() -> str:
        # Runs only when the owner presses CONFIRM, on a worker thread. If the staged
        # change is not the one that was on the banner, it is not applied.
        try:
            current = prompt_store.load(proposal_id)
        except KeyError:
            return f"{proposal_id} is gone, so nothing was applied."
        if _digest(current) != shown:
            return f"{proposal_id} is not the change that was shown, so nothing was applied."
        try:
            return prompt_store.confirm(proposal_id, "panel")
        except ValueError as error:
            return str(error)

    detail = _banner_detail(proposal)
    asked = put_up_the_banner(f"prompt-{proposal_id}", "Change my own instructions",
                              detail, after_the_click)
    return " ".join(part for part in (recorded, asked) if part)


def _list_pending() -> str:
    waiting = prompt_store.pending()
    if not waiting:
        return "No prompt change is waiting for a decision."
    return _say(["Waiting for a decision:"] +
                ["  " + prompt_store.describe(item) for item in waiting])


def _reject(parameters: dict) -> str:
    proposal_id = str(parameters.get("proposal") or "").strip()
    if not proposal_id:
        return "Which proposal should I drop?"
    return prompt_store.reject(proposal_id, str(parameters.get("reason") or ""))


def _history() -> str:
    rows = prompt_store.history()
    if not rows:
        return "My instruction has never been changed."
    return _say(["Changes to my system prompt, newest first:"] + [
        f"  {row['at']}  {row.get('reason') or '(no reason)'}  "
        f"[{', '.join(row.get('confirmations') or [])}]" for row in rows])


def _versions() -> str:
    kept = prompt_store.versions()
    if not kept:
        return "No earlier version is kept yet — the prompt has not changed."
    return "Kept versions, newest first: " + ", ".join(item.name for item in kept)


def _revert(parameters: dict) -> str:
    name = str(parameters.get("version") or "").strip()
    if not name:
        return ("Which version? Ask for 'versions' and I will list them. Going back "
                "is a change like any other — it needs the same two confirmations.")
    proposal = prompt_store.propose_revert(name)
    return _say(["Staged a return to that version. Nothing has changed yet.",
                 prompt_store.describe(proposal)])


def _check() -> str:
    ok, problems = prompt_store.validate(prompt_store.read())
    if ok:
        return (f"The prompt in use passes every rule: {prompt_store.size()} "
                f"characters, all {len(prompt_store.REQUIRED_TOKENS)} placeholders "
                f"intact.")
    return "The prompt in use has a problem:\n  " + "\n  ".join(problems)


# action name -> the function that answers it. A table rather than a chain of ifs:
# the chain was 116 lines with 40 branches, which is a function nobody can be sure
# about — and this one edits the instruction that governs everything else.
ACTIONS = {
    "show": _show, "read": _show, "view": _show, "template": prompt_store.read,
    "stage": _stage, "propose": _stage, "edit": _stage,
    "confirm": _confirm, "approve": _confirm,
    "pending": _list_pending, "list": _list_pending,
    "reject": _reject, "drop": _reject, "cancel": _reject,
    "history": _history, "changelog": _history,
    "versions": _versions, "snapshots": _versions,
    "revert": _revert, "undo": _revert, "restore": _revert,
    "check": _check,
}


def system_prompt(parameters: dict) -> str:
    """Read, stage, confirm or undo a change to Ultron's own system prompt."""
    parameters = dict(parameters or {})
    action = str(parameters.get("action") or "show").strip().lower()
    handler = ACTIONS.get(action)
    try:
        if handler is None:
            return (f"I do not know the action '{action}'. I can: show, template, "
                    f"stage, pending, confirm, reject, history, versions, revert, "
                    f"check.")
        if handler in (_stage, _confirm, _reject, _revert):
            return handler(parameters)
        return handler()
    except KeyError:
        return "I have no proposal or version with that name."
    except ValueError as error:
        # A refusal is the answer, not a crash: the reason is written to be said.
        return str(error)
    except Exception as error:
        failures.note("prompt_editor.system_prompt", error)
        return "That did not work, and I have recorded why. Nothing was changed."


TOOL = {
    "name": "system_prompt",
    "description": (
        "Read or change the instruction that shapes your own behaviour — the text "
        "at the start of every conversation. Use 'show' when the user asks what your "
        "instructions are, what you were told, or why you behave a certain way. Use "
        "'stage' with either 'find' and 'replace' (one passage) or 'text' (the whole "
        "prompt) when the user asks you to behave differently from now on, such as "
        "being shorter, more formal, or never using a certain phrase: stage a change "
        "and say plainly that it is not in effect yet. Call 'confirm' only after the "
        "user has said yes: it records that and puts a CONFIRM button on the screen; "
        "the change applies only when the user presses that button, which is theirs "
        "and not yours, so after 'confirm' say that it is waiting for them and never "
        "claim a change is active. A change too big for the user to read on the screen "
        "is refused rather than cut, so stage it as several smaller ones. "
        "Every change is versioned "
        "and can be reverted. Do not use this to change what you are allowed to do in "
        "the wider system: permissions, approvals and file limits live in code, not "
        "in this text, and editing the text does not change them."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": ("show | template | stage | pending | confirm | "
                                "reject | history | versions | revert | check")
            },
            "reason": {"type": "STRING",
                       "description": "Why this change is being made. Required to stage."},
            "text": {"type": "STRING",
                     "description": "The whole new prompt, for a full replacement."},
            "find": {"type": "STRING",
                     "description": "The exact passage to replace, for a one-passage change."},
            "replace": {"type": "STRING",
                        "description": "What that passage becomes."},
            "proposal": {"type": "STRING",
                         "description": "The id of a staged change, e.g. p1a2b3c4d5e6f."},
            "version": {"type": "STRING",
                        "description": "A kept version name, for revert."},
        },
        "required": ["action"],
    },
    "handler": system_prompt,
}
