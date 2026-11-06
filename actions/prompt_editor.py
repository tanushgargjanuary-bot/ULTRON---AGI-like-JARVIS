"""The system prompt, reachable by voice: read it, change it, go back.

The owner asked for two things in one sentence — that the model's system prompt be
visible to them, and that they be able to instruct Ultron to change it. This file is
the tool that does both, and it is deliberately the only door.

    "Show me your system prompt."              -> action "show"
    "Make your answers shorter from now on."   -> the model stages a "change"
    "Yes, do it."                              -> action "confirm", channel voice
    then a click in the panel                  -> action "confirm", channel panel

Why a staged change instead of an immediate one: a model that can rewrite its own
instruction in one step can also delete the paragraphs that stop it from doing
something. Two confirmations, in two different places, mean the owner has read the
change twice before it exists. `core/prompt_store.py` holds the rules; this file
only carries the conversation.

Everything this tool returns is a sentence, because it is read aloud as often as it
is read on screen.
"""

from __future__ import annotations

from core import failures, prompt_store

MAX_PREVIEW = 20_000        # the whole prompt fits: the owner asked to see it


def _say(lines: list[str]) -> str:
    return "\n".join(lines)


def _preview_block() -> list[str]:
    text = prompt_store.preview()
    if len(text) > MAX_PREVIEW:
        text = text[:MAX_PREVIEW] + "\n… (shortened to fit one answer)"
    return ["--- the system prompt ---", text, "--- end of the system prompt ---"]


def _show() -> str:
    lines = _preview_block()
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
    return _say([
        "Staged, not applied. Nothing about me has changed yet.",
        prompt_store.describe(proposal),
        f"To apply it: confirm twice, in two different places — "
        f"{prompt_store.CONFIRMATIONS} confirmations of proposal {proposal.id}.",
    ])


def _confirm(parameters: dict) -> str:
    proposal_id = str(parameters.get("proposal") or "").strip()
    if not proposal_id:
        return "Which proposal? Ask me for 'pending' and I will name them."
    channel = str(parameters.get("channel") or "voice").strip().lower()
    return prompt_store.confirm(proposal_id, channel)


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
        "and say plainly that it is not in effect yet. It applies only after the user "
        "confirms twice in two different places, so never claim a change is active "
        "until 'confirm' has returned the applied message. Every change is versioned "
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
            "channel": {"type": "STRING",
                        "description": "Where the confirmation came from: voice | panel | cli."},
            "version": {"type": "STRING",
                        "description": "A kept version name, for revert."},
        },
        "required": ["action"],
    },
    "handler": system_prompt,
}
