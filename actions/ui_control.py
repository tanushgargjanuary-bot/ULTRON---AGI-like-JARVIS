#ui_control.py
"""actions/ui_control.py — the computer-use tool: structure first, pixels last.

WHY THIS TOOL EXISTS
    `computer_control` clicks coordinates. This one asks the window what it
    contains and acts on named elements, which is faster, does not move the
    pointer, and can tell the difference between "the button was pressed" and
    "something was at that spot".

    It follows the same loop the user asked for, in the order Ultron already
    promised: the accessibility tree first, the page DOM for web content, the
    keyboard for anything with an access key, vision only if it is configured and
    consented, and otherwise an honest question instead of a guess
    (`core/ui_ladder.py`).

WHAT IT RETURNS
    The `core/outcome.py` vocabulary, never a bare "done". A snapshot that was
    read is `done` because it is direct evidence. An action whose only evidence
    is "the call returned" is `unverified`, which is what the model will then tell
    the user — that is deliberate, not hedging: a click that reports success
    without looking is how a wrong window gets blamed on the assistant later.
"""

from __future__ import annotations

import platform

from core import outcome
from core.ui_action import Session, UiError
from core.ui_ladder import Context, Ladder, Rung, describe, next_step

_TOOL_NAME = "ui_control"

# One adapter per process. A Windows UIA adapter retains native objects across
# calls; rebuilding it every time would throw that away and make every ref stale.
_ADAPTER = None
_ADAPTER_REASON = ""
_BROWSER_PAGE = None

# The session has to survive between tool calls, and that is not an optimisation.
# It holds the snapshot id the model's refs were taken from. A fresh session per
# call takes a fresh snapshot before acting, which silently invalidates the ref
# the model just read — measured: every act-by-ref failed with STALE_REF and the
# adapter was never called. This is the whole point of having refs at all.
_SESSION = None
_SESSION_ADAPTER = None


def set_browser_page(page) -> None:
    """Let the browser owner hand over its page.

    `actions/browser_control.py` already owns a Playwright browser. Two owners of
    one profile is how the "Who's using Chrome?" picker appears on screen, so the
    page is passed in rather than launched here.
    """
    global _BROWSER_PAGE
    _BROWSER_PAGE = page


def _adapter():
    """The best bridge this machine offers, and the reason when there is none."""
    global _ADAPTER, _ADAPTER_REASON
    if _ADAPTER is not None:
        return _ADAPTER
    try:
        from core.ui_windows import WindowsAdapter, available

        usable, reason = available()
        if usable:
            _ADAPTER = WindowsAdapter()
            _ADAPTER_REASON = f"UI Automation via {reason}"
            return _ADAPTER
        _ADAPTER_REASON = reason
    except Exception as exc:                    # noqa: BLE001
        _ADAPTER_REASON = f"no Windows bridge ({type(exc).__name__}: {exc})"
    if _BROWSER_PAGE is not None:
        try:
            from core.ui_browser import BrowserAdapter

            _ADAPTER = BrowserAdapter(_BROWSER_PAGE)
            _ADAPTER_REASON = "browser DOM"
        except Exception as exc:                # noqa: BLE001
            _ADAPTER_REASON = f"no browser bridge ({type(exc).__name__}: {exc})"
    return _ADAPTER


def _session() -> Session:
    """The one session for this process, rebuilt only when the adapter changes."""
    global _SESSION, _SESSION_ADAPTER
    adapter = _adapter()
    if _SESSION is None or _SESSION_ADAPTER is not adapter:
        _SESSION = Session(adapter)
        _SESSION_ADAPTER = adapter
    return _SESSION


def reset_session() -> None:
    """Forget the current snapshot. Used when the bridge changes underneath us."""
    global _SESSION, _SESSION_ADAPTER
    _SESSION = None
    _SESSION_ADAPTER = None


def _context(session: Session, **kwargs) -> Context:
    caps = session.capabilities()
    base = {
        "has_tree": "uia" in caps or "ax" in caps or "atspi" in caps,
        "has_dom": "dom" in caps,
        "keyboard_ready": "keyboard" in caps or bool(caps),
        "ocr_ready": _ocr_ready(),
        "vision_ready": False,
    }
    base.update(kwargs)
    return Context(**base)


def _ocr_ready() -> bool:
    """True when a local OCR engine is available without cloud dependency."""
    try:
        from core.ocr import ocr_available
        usable, _ = ocr_available()
        return usable
    except Exception:
        return False


def _vision_ready() -> bool:
    """True only when a vision provider is configured, which is off by default."""
    try:
        from custom_jarvis.vision import VisionConfig

        return VisionConfig.from_env().configured
    except Exception:                           # noqa: BLE001
        return False


def ui_control(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = dict(parameters or {})
    action = str(params.get("action") or "snapshot").strip().lower()
    app = str(params.get("app") or "").strip()
    target = str(params.get("target") or "").strip()
    verb = str(params.get("do") or "click").strip().lower()
    value = str(params.get("value") or "")
    role = str(params.get("role") or "").strip()
    skeleton = bool(params.get("skeleton"))
    max_lines = int(params.get("max_lines") or 120)

    session = _session()
    if _adapter() is None and action not in ("describe", "capabilities"):
        reason = _ADAPTER_REASON or "no accessibility bridge on this machine"
        return outcome.ask(
            _TOOL_NAME,
            f"I cannot read this machine's interface: {reason}. "
            "Tell the user that, and offer to do it another way rather than clicking blindly.",
            reason=reason,
        )

    try:
        if action in ("describe", "capabilities"):
            ctx = _context(session, vision_ready=_vision_ready())
            return outcome.done(_TOOL_NAME, reach=describe(ctx, platform_name=platform.system()))

        if action in ("snapshot", "look", "observe"):
            snapshot = session.observe(app, skeleton=skeleton)
            return outcome.done(
                _TOOL_NAME,
                app=app or snapshot.app or "the foreground window",
                elements=len(snapshot),
                snapshot=snapshot.render(max_lines=max_lines),
            )

        if action == "drill":
            if not target:
                return outcome.failed(_TOOL_NAME, "drill needs the ref of a region")
            current = session.snapshot
            if current is None:
                return outcome.failed(_TOOL_NAME, "take a snapshot before drilling")
            try:
                entry = current.get(target)
            except Exception as exc:  # noqa: BLE001
                return outcome.failed(_TOOL_NAME, f"that ref is not usable: {exc}")
            if not entry.truncated:
                return outcome.failed(
                    _TOOL_NAME, f"{entry.role} '{entry.name}' was not truncated; nothing to drill"
                )
            drilled = session.drill(target)
            return outcome.done(
                _TOOL_NAME,
                region=entry.name or entry.ref,
                elements=len(drilled),
                snapshot=drilled.render(max_lines=max_lines),
            )

        if action in ("act", "do", "click", "type", "press"):
            ladder = Ladder()
            if session.snapshot is None or session.dirty:
                try:
                    session.observe(app)
                    ladder.record(Rung.TREE, True, "snapshot")
                except UiError as exc:
                    step = next_step(exc, _context(session, vision_ready=_vision_ready()))
                    return _ladder_refusal(step, exc, app)
            result = session.act(target, verb, value, role=role)
            ladder.record(Rung.TREE, result.ok, result.message)
            if result.ok:
                # The action was accepted, but nothing was observed afterwards.
                return outcome.unverified(
                    _TOOL_NAME,
                    "the action was performed through the interface; take a snapshot to confirm it worked",
                    app=app or result.app,
                    ref=result.ref,
                    did=result.message or result.action,
                    snapshot_id=result.snapshot_id,
                )
            step = next_step(
                result.error,
                _context(
                    session,
                    vision_ready=_vision_ready(),
                    hotkey=_hotkey_for(session, result.ref),
                    attempts=ladder.attempts(),
                    tried=ladder.tried(),
                ),
            )
            return _ladder_refusal(step, result.error, app)

        if action == "batch":
            operations = params.get("operations") or []
            if not isinstance(operations, list) or not operations:
                return outcome.failed(_TOOL_NAME, "batch needs a list of operations")
            if session.snapshot is None:
                session.observe(app)
            results = session.batch(operations)
            done_count = sum(1 for item in results if item.ok)
            if done_count == len(results):
                return outcome.unverified(
                    _TOOL_NAME,
                    "every step was performed; take a snapshot to confirm the result",
                    steps=done_count,
                )
            first_bad = next(item for item in results if not item.ok)
            return outcome.failed(
                _TOOL_NAME,
                f"stopped after {done_count} of {len(results)} steps: {first_bad.message}",
                failed_at=first_bad.action,
            )

        return outcome.failed(_TOOL_NAME, f"'{action}' is not an action this tool knows")
    except UiError as exc:
        step = next_step(exc, _context(session, vision_ready=_vision_ready()))
        return _ladder_refusal(step, exc, app)
    except Exception as exc:                    # noqa: BLE001
        return outcome.failed(_TOOL_NAME, f"{type(exc).__name__}: {exc}")


def _hotkey_for(session: Session, ref: str) -> str:
    """The access key of the element that failed, if it has one."""
    try:
        from core.ui_ladder import access_key

        entry = session.snapshot.get(ref) if session.snapshot and ref else None
        return access_key(entry.name) if entry is not None else ""
    except Exception:                           # noqa: BLE001
        return ""


def _ladder_refusal(step, error, app: str) -> str:
    """Turn a ladder decision into something the model can act on or say."""
    detail = str(error) if error is not None else ""
    if step.rung is Rung.ASK:
        return outcome.ask(
            _TOOL_NAME,
            f"{detail}. Ask the user before trying anything else.".strip(),
            ladder=step.rung.value,
            why=step.reason,
        )
    if step.rung is Rung.OCR:
        return outcome.unverified(
            _TOOL_NAME,
            "There is no structural tree; try local OCR on screenshot to find text before resorting to vision.",
            ladder=step.rung.value,
            why=step.reason,
        )
    if step.rung is Rung.VISION:
        return outcome.ask(
            _TOOL_NAME,
            "There is no structural way to reach that control. Reading the screen "
            "would need a screenshot, which the user has to agree to. Say that, "
            "and do not guess at coordinates.",
            ladder=step.rung.value,
            why=step.reason,
        )
    if step.rung is Rung.KEYBOARD:
        return outcome.unverified(
            _TOOL_NAME,
            f"Use computer_control to send the shortcut {step.hotkey or 'for that control'} "
            "instead; there is no invocable pattern on it.",
            ladder=step.rung.value,
            hotkey=step.hotkey,
        )
    if step.rung is Rung.DOM:
        return outcome.unverified(
            _TOOL_NAME,
            "This is web content with no usable desktop tree; use browser_control, "
            "which reads the page itself.",
            ladder=step.rung.value,
        )
    return outcome.failed(_TOOL_NAME, detail or step.reason, ladder=step.rung.value)


TOOL = {
    "name": _TOOL_NAME,
    "description": (
        "Reads and operates the screen as structure instead of pixels: it asks "
        "the operating system's accessibility tree what the window contains, "
        "returns a numbered ref for every element that can be acted on, and then "
        "acts on those refs. Does not move the mouse or steal focus. "
        "Use it INSTEAD of computer_control whenever the target is a named "
        "control — a button, field, tab, menu item, checkbox. Use "
        "computer_control only for what has no name: dragging, drawing, a "
        "canvas, a game. "
        "The loop is: action='snapshot' for the app you are working in, read the "
        "elements, then action='act' with the ref or the element's name. A ref "
        "carries the snapshot it came from, so after ANY action the refs are dead "
        "— take a snapshot again before the next one. If an element was truncated "
        "(it says 'drill with @...'), use action='drill' on that ref rather than "
        "asking for a bigger dump. "
        "An action that returns unverified means it was performed but not "
        "confirmed: say so, then snapshot to confirm. If this tool returns ask, "
        "the window offers no reliable way to do it — tell the user rather than "
        "clicking at a guessed position. Never claim you clicked something "
        "without calling this tool."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "What to do: snapshot, drill, act, batch, describe.",
                "enum": ["snapshot", "drill", "act", "batch", "describe"],
            },
            "app": {
                "type": "STRING",
                "description": (
                    "The application or window title to work in, as the user named "
                    "it. Leave empty for the window the user is looking at. "
                    "Partial names work; 'Chrome' finds the running browser window."
                ),
            },
            "target": {
                "type": "STRING",
                "description": (
                    "For act: the ref from a snapshot (like @a1b2c3d4e5:e7) or the "
                    "element's visible name, such as 'Save'. For drill: the ref of "
                    "the truncated region."
                ),
            },
            "do": {
                "type": "STRING",
                "description": (
                    "For act: what to do to the element. click, type, toggle, "
                    "select, expand, scroll, focus. The closest supported action is "
                    "chosen automatically, so 'click' on a text field focuses it."
                ),
                "enum": ["click", "type", "toggle", "select", "expand", "scroll", "focus"],
            },
            "value": {
                "type": "STRING",
                "description": "For do='type': the text to put in the field.",
            },
            "role": {
                "type": "STRING",
                "description": (
                    "Optional role to disambiguate a name: button, link, text_field, "
                    "tab, check_box, list_item, menu_item. Use it when two elements "
                    "share a name."
                ),
            },
            "skeleton": {
                "type": "BOOLEAN",
                "description": (
                    "For snapshot: read only the top few levels. Cheaper, and the "
                    "right first look in a dense app; drill into what you need."
                ),
            },
            "operations": {
                "type": "ARRAY",
                "description": (
                    "For batch: a list of {target, do, value, role} objects, run in "
                    "order. Stops at the first failure."
                ),
                "items": {"type": "OBJECT"},
            },
            "max_lines": {
                "type": "INTEGER",
                "description": "For snapshot: how many element lines to return. Default 120.",
            },
        },
        "required": ["action"],
    },
    "handler": ui_control,
}
