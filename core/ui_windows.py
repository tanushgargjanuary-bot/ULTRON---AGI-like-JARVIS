"""core/ui_windows.py — the Windows side: UI Automation, without moving the mouse.

WHAT THIS ADAPTER DOES DIFFERENTLY FROM `computer_control`
    UI Automation can invoke a control through its own pattern instead of
    synthesising a click. `InvokePattern.Invoke()` does not move the pointer, does
    not raise the window and does not steal focus, which is the difference
    between an assistant that works while the user keeps typing and one that
    grabs the machine every time it acts. The user asked for background
    operation; this is where it actually comes from.

    Where a control supports no such pattern — a canvas, a game, a legacy app
    drawing its own buttons — this adapter says so (`UNSUPPORTED_ACTION`) instead
    of falling back to a blind click. The fallback is a decision for
    `core/ui_ladder.py`, not something to do silently at the bottom of a driver.

WHAT IS VERIFIED, AND WHAT IS NOT
    The bridge is written against the `uiautomation` package (which wraps
    UI Automation through comtypes) and falls back to `pywinauto`'s UIA backend.
    Neither is installed in the environment this was written in, and no Windows
    machine was available, so **the bridge itself is unverified** — it is written
    defensively, every call is wrapped, and `probe()` reports honestly when it
    cannot work. What *is* verified is everything above it: the snapshot model,
    refs, staleness and the ladder (`tests/test_ui_tree.py`, `test_ui_action.py`,
    `test_ui_ladder.py`), driven through a fake adapter.

    Do not describe this as working on Windows until it has been run there.
"""

from __future__ import annotations
from core import failures

import importlib.util
import platform
from typing import Any

from core.ui_tree import Node

# UI Automation ControlType ids -> the role names core/ui_tree.py normalises.
# The numeric ids are the stable part of the API; the names are for reading logs.
CONTROL_TYPES = {
    50000: "button", 50001: "calendar", 50002: "check_box", 50003: "combo_box",
    50004: "edit", 50005: "link", 50006: "image", 50007: "list_item",
    50008: "list", 50009: "menu", 50010: "menu_bar", 50011: "menu_item",
    50012: "progress_bar", 50013: "radio", 50014: "scroll_bar", 50015: "slider",
    50016: "spinner", 50017: "status_bar", 50018: "tab", 50019: "tab_item",
    50020: "text", 50021: "tool_bar", 50022: "tool_tip", 50023: "tree",
    50024: "tree_item", 50025: "custom", 50026: "group", 50027: "thumb",
    50028: "data_grid", 50029: "data_item", 50030: "document", 50031: "split_button",
    50032: "window", 50033: "pane", 50034: "header", 50035: "header_item",
    50036: "table", 50037: "title_bar", 50038: "separator",
}

# Pattern flags in the order they are checked. The first supported pattern wins,
# so an element that is both invokable and selectable is treated as invokable.
PATTERN_ACTIONS = (
    ("invoke", "invoke", "click"),
    ("toggle", "toggle", "toggle"),
    ("selection_item", "select", "select"),
    ("expand_collapse", "expand", "expand"),
    ("value", "set_value", "set_value"),
    ("scroll", "scroll", "scroll"),
    ("range_value", "set_value", "set_value"),
    ("text", "read", "read"),
)

MAX_WALK_NODES = 3000


# The bridge is written against `uiautomation`; the pywinauto branch below raises
# NotImplemented. That asymmetry used to be invisible here: with pywinauto
# installed — which it is on every Windows install, because three plugins import
# it directly — available() answered "yes, pywinauto", the ladder preferred the
# accessibility tree over vision exactly as the user asked, and the first real
# call raised "pywinauto fallback is not implemented". A capability that reports
# itself ready and then throws is worse than one that reports itself missing, so
# available() now names only a backend that can actually be driven.
IMPLEMENTED_BACKEND = "uiautomation"
FALLBACK_BACKEND = "pywinauto"


def _importable(name: str) -> bool:
    """Is `name` installed, without importing it.

    find_spec is the right question at startup: importing pywinauto pulls in
    comtypes and takes noticeable time, and this runs before the window is shown.
    """
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:  # noqa: BLE001
        return False


def available() -> tuple[bool, str]:
    """(usable, reason). Cheap, and never raises — this runs at startup.

    `usable` means "a driver exists AND its package is installed". Never merge
    those two questions: the answer has to survive the first call.
    """
    if platform.system() != "Windows":
        return False, f"UI Automation is a Windows API; this is {platform.system()}"
    if _importable(IMPLEMENTED_BACKEND):
        return True, IMPLEMENTED_BACKEND
    if _importable(FALLBACK_BACKEND):
        return False, (
            f"{FALLBACK_BACKEND} is installed but this bridge has no "
            f"{FALLBACK_BACKEND} driver; install {IMPLEMENTED_BACKEND} "
            f"(pip install {IMPLEMENTED_BACKEND})"
        )
    return False, (
        "no UI Automation bridge installed (pip install "
        f"{IMPLEMENTED_BACKEND})"
    )


def _control_type_name(control: Any) -> str:
    try:
        control_type = control.ControlType
    except Exception:  # noqa: BLE001
        return "unknown"
    if isinstance(control_type, int):
        return CONTROL_TYPES.get(control_type, "custom")
    name = getattr(control_type, "Name", "") or ""
    return str(name).lower().replace("control", "") or "unknown"


def _call(control: Any, method: str, *args, **kwargs) -> Any:
    """Call one of uiautomation's `GetXxxPattern` helpers, or None."""
    getter = getattr(control, f"Get{method}", None)
    if getter is None:
        return None
    try:
        return getter(*args, **kwargs)
    except Exception:  # noqa: BLE001
        return None


def _actions_for(control: Any) -> tuple[str, ...]:
    found: list[str] = []
    for pattern, action, _verb in PATTERN_ACTIONS:
        attributes = {
            "invoke": "GetInvokePattern",
            "toggle": "GetTogglePattern",
            "selection_item": "GetSelectionItemPattern",
            "expand_collapse": "GetExpandCollapsePattern",
            "value": "GetValuePattern",
            "scroll": "GetScrollPattern",
            "range_value": "GetRangeValuePattern",
            "text": "GetTextPattern",
        }
        getter = getattr(control, attributes[pattern], None)
        if getter is None:
            continue
        try:
            if getter() is not None:
                found.append(action)
        except Exception as error:  # noqa: BLE001, S112
            failures.note("ui_windows._actions_for", error)
            continue
    if not found:
        return ()
    # Focus is always worth offering: it makes keyboard fallbacks possible.
    return tuple(found + ["focus"])


class WindowsAdapter:
    """UI Automation as an `core.ui_action.Adapter`.

    Native objects are retained per snapshot on purpose. Re-finding an element by
    name at action time would let a removed row resolve to a surviving row with
    the same label — the exact silent-mismatch failure this design exists to
    prevent. A retained object that has died returns STALE_REF, which is
    recoverable; a wrong row is not.
    """

    name = "windows"
    backend = ""

    def __init__(self, max_depth: int = 6, retain: bool = True) -> None:
        self.max_depth = max_depth
        self.retain = retain
        self._controls: dict[str, Any] = {}
        self._snapshot_id = ""

    # ---------------------------------------------------------------- capability
    def capabilities(self) -> set[str]:
        usable, backend = available()
        if not usable:
            return set()
        self.backend = backend
        return {"uia", "headless", "keyboard", backend}

    # ------------------------------------------------------------------- lookup
    def _module(self):
        usable, backend = available()
        if not usable:
            raise RuntimeError(backend)
        if backend == IMPLEMENTED_BACKEND:
            import uiautomation as uia
            return uia
        # Unreachable through available(), and deliberately kept: if a later
        # change starts returning the fallback from available(), this fails
        # loudly here instead of pretending to walk a tree.
        raise RuntimeError(
            f"no driver for backend {backend!r}; the implemented backend is "
            f"{IMPLEMENTED_BACKEND}"
        )

    def _window(self, app: str):
        """The top-level window for `app`, or the foreground window when unnamed."""
        uia = self._module()
        app = str(app or "").strip()
        if app:
            # SubName does a case-insensitive substring match, which is what a
            # spoken application name actually is. Exact matching misses
            # "Document1 - Word" for "Word".
            for kwargs in ({"SubName": app}, {"RegexName": f".*{app}.*"}):
                try:
                    window = uia.WindowControl(searchDepth=1, **kwargs)
                    if window.Exists(0.4, 0.1):
                        return window
                # A window that cannot be queried is a window that is not this
                # one; try the next. Anything else would abort the search over a
                # single unresponsive process.
                except Exception as error:  # noqa: BLE001, S112
                    failures.note("ui_windows._window", error)
                    continue
            raise RuntimeError(f"no window matches '{app}'")
        try:
            window = uia.GetForegroundControl()
            if window is not None:
                return window
        except Exception as error:  # noqa: BLE001, S110
            failures.note("ui_windows._window", error)
        raise RuntimeError("no foreground window")

    def foreground(self) -> dict:
        """Which window the user is working in, read as data.

        The claim "it works in the background without taking the keyboard from
        you" needs this before and after an action, and the gate called a method
        that had never been written — `AttributeError: 'WindowsAdapter' object has
        no attribute 'foreground'`, on the only platform that can reach it. Reading
        the foreground window takes no focus and sends no input; the comparison is
        what turns the claim from a promise into a check.
        """
        uia = self._module()
        try:
            window = uia.GetForegroundControl()
        except Exception as exc:                               # noqa: BLE001
            raise RuntimeError(f"the foreground window cannot be read: {exc}") from exc
        if window is None:
            raise RuntimeError("there is no foreground window to read")
        try:
            title = str(window.Name or "")
        except Exception:                                      # noqa: BLE001
            title = ""
        try:
            handle = int(getattr(window, "NativeWindowHandle", 0) or 0)
        except Exception:                                      # noqa: BLE001
            handle = 0
        return {"title": title[:120], "handle": handle}

    # ------------------------------------------------------------------ snapshot
    def snapshot(self, app: str = "", root_ref: str | None = None,
                 max_depth: int | None = None) -> Node:
        from core.ui_action import ui_error

        try:
            window = self._window(app)
        except RuntimeError as exc:
            raise ui_error("APP_GONE", str(exc)) from exc
        except Exception as exc:   # rewritten with a disposition just below
            raise ui_error("NO_TREE", f"UI Automation unavailable: {exc}") from exc

        depth = self.max_depth if max_depth is None else max_depth
        self._controls = {}
        counter = [0]
        try:
            root = self._build(window, depth, counter, entry_ref=None)
        except RuntimeError as exc:
            raise ui_error("NO_TREE", str(exc)) from exc
        if root is None:
            raise ui_error(
                "NO_TREE",
                f"'{app or 'the window'}' exposes no accessibility tree; "
                "this application does not publish one",
            )
        return root

    def _build(self, control: Any, depth: int, counter: list[int],
               entry_ref: str | None) -> Node | None:
        if counter[0] >= MAX_WALK_NODES:
            return None
        counter[0] += 1
        try:
            name = control.Name or ""
        except Exception:  # noqa: BLE001
            name = ""
        try:
            value = ""
            value_pattern = _call(control, "GetValuePattern")
            if value_pattern is not None:
                value = str(getattr(value_pattern, "Value", "") or "")
        except Exception:  # noqa: BLE001
            value = ""
        try:
            enabled = bool(control.IsEnabled)
        except Exception:  # noqa: BLE001
            enabled = True
        try:
            visible = not bool(control.IsOffscreen)
        except Exception:  # noqa: BLE001
            visible = True
        try:
            rect = control.BoundingRectangle
            bounds = (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
        except Exception:  # noqa: BLE001
            bounds = None
        try:
            runtime_id = str(control.GetRuntimeId() or "")
        except Exception:  # noqa: BLE001
            runtime_id = str(id(control))

        role = _control_type_name(control)
        actions = _actions_for(control)
        sensitive = role in ("edit",) and bool(getattr(control, "IsPassword", False))

        children: list[Node] = []
        if depth > 0:
            try:
                raw_children = control.GetChildren() or []
            except Exception:  # noqa: BLE001
                raw_children = []
            for child in raw_children:
                node = self._build(child, depth - 1, counter, entry_ref)
                if node is not None:
                    children.append(node)

        node = Node(
            role=role, name=str(name), value=value if not sensitive else "",
            node_id=runtime_id, enabled=enabled, visible=visible, bounds=bounds,
            actions=actions, children=tuple(children), sensitive=sensitive,
        )
        if self.retain and actions:
            # Only addressable elements are retained: containers cannot be acted on.
            self._controls[runtime_id] = control
        return node

    # -------------------------------------------------------------------- action
    def perform(self, entry, action: str, value: str = "") -> None:
        from core.ui_action import ui_error

        control = self._controls.get(getattr(entry, "node_id", ""))
        if control is None:
            raise ui_error(
                "STALE_REF",
                f"the control behind {entry.ref} is no longer held; take a new snapshot",
            )
        verb = str(action or "").strip().lower()
        try:
            if verb in ("click", "invoke", "press"):
                pattern = _call(control, "GetInvokePattern")
                if pattern is not None:
                    pattern.Invoke()
                    return
                selection = _call(control, "GetSelectionItemPattern")
                if selection is not None:
                    selection.Select()
                    return
                toggle = _call(control, "GetTogglePattern")
                if toggle is not None:
                    toggle.Toggle()
                    return
                raise ui_error(
                    "UNSUPPORTED_ACTION",
                    f"{entry.role} '{entry.name}' supports no invoke pattern; "
                    "a synthetic click would be a guess at the coordinates",
                )
            if verb in ("type", "set_value"):
                pattern = _call(control, "GetValuePattern")
                if pattern is not None:
                    pattern.SetValue(str(value))
                    return
                raise ui_error(
                    "UNSUPPORTED_ACTION",
                    f"{entry.role} '{entry.name}' does not accept a value through UI Automation",
                )
            if verb == "toggle":
                pattern = _call(control, "GetTogglePattern")
                if pattern is None:
                    raise ui_error("UNSUPPORTED_ACTION", "this element cannot be toggled")
                pattern.Toggle()
                return
            if verb == "select":
                pattern = _call(control, "GetSelectionItemPattern")
                if pattern is None:
                    raise ui_error("UNSUPPORTED_ACTION", "this element cannot be selected")
                pattern.Select()
                return
            if verb == "expand":
                pattern = _call(control, "GetExpandCollapsePattern")
                if pattern is None:
                    raise ui_error("UNSUPPORTED_ACTION", "this element cannot be expanded")
                pattern.Expand()
                return
            if verb == "focus":
                control.SetFocus()
                return
            if verb == "scroll":
                pattern = _call(control, "GetScrollPattern")
                if pattern is None:
                    raise ui_error("UNSUPPORTED_ACTION", "this element cannot scroll")
                pattern.Scroll(0, 1)          # one page down, the common case
                return
            if verb == "read":
                pattern = _call(control, "GetTextPattern")
                if pattern is None:
                    raise ui_error("UNSUPPORTED_ACTION", "this element has no readable text")
                return
            raise ui_error("UNSUPPORTED_ACTION", f"'{verb}' is not a supported action")
        except Exception as exc:              # a COM failure is a retryable failure
            if getattr(exc, "code", None):
                raise
            raise ui_error("ADAPTER_FAILED", f"{type(exc).__name__}: {exc}") from exc

    # --------------------------------------------------------------------- probe
    def probe(self, entry) -> tuple[bool, bool] | None:
        control = self._controls.get(getattr(entry, "node_id", ""))
        if control is None:
            return None
        try:
            return (not bool(control.IsOffscreen), bool(control.IsEnabled))
        except Exception:  # noqa: BLE001
            return None
