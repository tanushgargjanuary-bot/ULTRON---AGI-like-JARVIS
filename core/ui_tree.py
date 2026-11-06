"""core/ui_tree.py — the screen as structure, not as pixels.

WHY THIS FILE EXISTS
    `actions/computer_control.py` drives the screen by coordinates: screenshot,
    find a shape, click at (x, y). It works, and it fails in a specific way —
    when the window has moved, when a theme changes a shade, when a hover
    reveals a second button that overlaps the first. The user then gets a click
    on whatever is now at those coordinates, reported as success.

    Every desktop operating system already publishes what that window contains:
    a tree of roles, names, values and the actions each element supports. That
    is the accessibility tree, and it is the same tree a screen reader uses.
    Reading it turns "click at 842,613" into "invoke the button named Save",
    which either works or says why it did not.

WHAT THIS MODULE OWNS — AND WHAT IT DOES NOT
    It owns the snapshot model: refs, the skeleton, drill-down, finding an
    element by what it is called, redaction, and the rules that decide when a
    ref has gone stale. All of that is plain Python and is tested offline
    (`tests/test_ui_tree.py`) against hand-built trees.

    It does NOT own the operating system bridge. Reimplementing UI Automation
    would be reimplementing Windows, not writing an algorithm; `core/ui_windows.py`
    and `core/ui_browser.py` are adapters that produce a `Node` tree from the OS
    or the DOM, and everything above them is this file.

THE REF FORMAT
    Every element gets `@<snapshot id>:e<number>`. The snapshot id is inside the
    ref on purpose: an action carrying a ref from an old snapshot can be
    rejected instead of applied to whatever now sits at that number. A bare
    `e12` is refused, because a ref without its snapshot is a guess.

WHAT A SNAPSHOT DELIBERATELY DOES NOT DO
    It does not dump the whole tree by default. A dense application exposes
    thousands of nodes and most of them are containers an agent cannot act on.
    The snapshot keeps the actionable elements, clamps depth, and marks every
    container it cut with how many children it has, so the caller can ask for
    one region instead of paying for all of them.
"""

from __future__ import annotations

import json
import re
import secrets
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

# Roles are normalised to these lowercase words. Two vocabularies arrive here —
# UI Automation's ControlType names and ARIA roles — and a caller should not have
# to know which produced a node.
ROLE_ALIASES = {
    "button": "button",
    "splitbutton": "button",
    "hyperlink": "link",
    "link": "link",
    "edit": "text_field",
    "textbox": "text_field",
    "text field": "text_field",
    "document": "document",
    "combobox": "combo_box",
    "list": "list",
    "listitem": "list_item",
    "list item": "list_item",
    "menuitem": "menu_item",
    "menu item": "menu_item",
    "menu": "menu",
    "menubar": "menu_bar",
    "tab": "tab",
    "tabitem": "tab",
    "tab item": "tab",
    "checkbox": "check_box",
    "check box": "check_box",
    "radiobutton": "radio",
    "radio button": "radio",
    "slider": "slider",
    "spinner": "spinner",
    "treeitem": "tree_item",
    "tree item": "tree_item",
    "tree": "tree",
    "datagrid": "grid",
    "dataitem": "grid_cell",
    "table": "grid",
    "cell": "grid_cell",
    "toolbar": "tool_bar",
    "scrollbar": "scroll_bar",
    "window": "window",
    "pane": "pane",
    "group": "group",
    "text": "text",
    "image": "image",
    "statusbar": "status_bar",
    "titlebar": "title_bar",
}

# Roles whose value is a secret. A snapshot that carries a password into a model
# context has leaked it into a transcript, whatever happens next, so the value is
# replaced at capture time and never stored.
SENSITIVE_ROLES = frozenset({"password_field", "password"})

# Roles that are containers only: worth walking, never worth acting on.
CONTAINER_ROLES = frozenset(
    {
        "window", "pane", "group", "document", "list", "menu", "menu_bar",
        "tool_bar", "tab", "grid", "tree", "title_bar", "status_bar",
    }
)

REF_PATTERN = re.compile(r"^@(?P<snapshot>[A-Za-z0-9]{4,32}):e(?P<index>\d{1,6})$")
MAX_NODES_DEFAULT = 400
MAX_DEPTH_DEFAULT = 6


class UiTreeError(ValueError):
    """A problem with a snapshot, a ref or a search — before any OS call."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class Node:
    """One element as an adapter found it. The only input to a `Snapshot`."""

    role: str
    name: str = ""
    value: str = ""
    node_id: str = ""                     # native id, used to notice replacement
    enabled: bool = True
    visible: bool = True
    bounds: tuple[int, int, int, int] | None = None
    actions: tuple[str, ...] = ()
    children: tuple[Node, ...] = ()
    sensitive: bool = False

    def normalised_role(self) -> str:
        key = str(self.role or "").strip().lower()
        return ROLE_ALIASES.get(key, key or "unknown")

    def walk(self) -> Iterator[Node]:
        """Depth-first, iterative: a deep tree must not be able to crash this."""
        stack = [self]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(reversed(node.children))


@dataclass
class Entry:
    """A node inside a snapshot, with the ref it is addressed by."""

    ref: str
    role: str
    name: str
    value: str
    node_id: str
    enabled: bool
    visible: bool
    actions: tuple[str, ...]
    depth: int
    parent: str | None = None
    children: list[str] = field(default_factory=list)
    children_total: int = 0            # every child the platform reports
    truncated: bool = False            # children withheld by depth or node budget
    sensitive: bool = False

    @property
    def actionable(self) -> bool:
        return bool(self.actions) and not self.sensitive

    def line(self) -> str:
        """One line for the model: role, name, ref, and what can be done."""
        bits = [self.role]
        if self.name:
            bits.append(f'"{_truncate(self.name, 60)}"')
        if self.value and not self.sensitive:
            bits.append(f"= {_truncate(self.value, 40)}")
        if self.sensitive:
            bits.append("= [redacted]")
        for state in (
            "" if self.enabled else " disabled",
            "" if self.visible else " hidden",
        ):
            if state:
                bits.append(state.strip())
        text = " ".join(bits) + f"  {self.ref}"
        if self.actions:
            text += "  [" + ",".join(self.actions) + "]"
        if self.truncated:
            text += f"  (+{self.children_total - len(self.children)} more"
            text += f", drill with {self.ref})"
        return text


def _truncate(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def new_snapshot_id() -> str:
    """A short id that is unique per snapshot, not per process."""
    return secrets.token_hex(6)[:10]


class Snapshot:
    """Everything one look at one window produced, addressable by ref."""

    __slots__ = (
        "_order",
        "app",
        "entries",
        "max_depth",
        "max_nodes",
        "redacted_count",
        "regions",
        "snapshot_id",
        "truncated_count",
        "window",
    )

    def __init__(self, app: str, window: str, snapshot_id: str | None = None) -> None:
        self.app = app
        self.window = window
        self.snapshot_id = snapshot_id or new_snapshot_id()
        self.entries: dict[str, Entry] = {}
        self._order: list[str] = []
        self.regions: dict[str, tuple[str, ...]] = {}
        self.truncated_count = 0
        self.redacted_count = 0
        self.max_depth = MAX_DEPTH_DEFAULT
        self.max_nodes = MAX_NODES_DEFAULT

    # ---------------------------------------------------------------- capture
    @classmethod
    def capture(
        cls,
        root: Node,
        app: str = "",
        window: str = "",
        max_depth: int = MAX_DEPTH_DEFAULT,
        max_nodes: int = MAX_NODES_DEFAULT,
        snapshot_id: str | None = None,
        root_ref: str | None = None,
    ) -> Snapshot:
        """Build a snapshot from an adapter's tree.

        `root_ref` is how a drill-down stays in the same snapshot: the new
        region keeps the id of the snapshot it belongs to, so a ref taken before
        the drill is still refused afterwards rather than silently reinterpreted.
        """
        snap = cls(app=app, window=window, snapshot_id=snapshot_id)
        snap.max_depth = max_depth
        snap.max_nodes = max_nodes
        snap._fill(root, root_ref=root_ref)
        return snap

    def _fill(self, root: Node, root_ref: str | None) -> None:
        stack: list[tuple[Node, int, str | None, bool]] = [(root, 0, root_ref, False)]
        while stack:
            if len(self._order) >= self.max_nodes:
                # Rather than silently dropping the rest, the element that would
                # have been next is marked as cut so the caller can drill.
                self.truncated_count += 1
                break
            node, depth, parent, forced_truncate = stack.pop()
            entry = self._add(node, depth, parent, forced_truncate)
            if depth >= self.max_depth and node.children:
                entry.truncated = True
                self.truncated_count += 1
                continue
            push: list[tuple[Node, int, str | None, bool]] = []
            for child in node.children:
                push.append((child, depth + 1, entry.ref, False))
            entry.children_total = len(node.children)
            stack.extend(reversed(push))

    def _add(self, node: Node, depth: int, parent: str | None, truncated: bool) -> Entry:
        role = node.normalised_role()
        sensitive = bool(node.sensitive) or role in SENSITIVE_ROLES
        ref = f"@{self.snapshot_id}:e{len(self._order)}"
        entry = Entry(
            ref=ref,
            role=role,
            name=str(node.name or ""),
            value="" if sensitive else str(node.value or ""),
            node_id=str(node.node_id or ""),
            enabled=bool(node.enabled),
            visible=bool(node.visible),
            actions=tuple(sorted({str(a).strip().lower() for a in node.actions if a})),
            depth=depth,
            parent=parent,
            children_total=len(node.children),
            truncated=truncated,
            sensitive=sensitive,
        )
        if sensitive:
            self.redacted_count += 1
        self.entries[ref] = entry
        self._order.append(ref)
        if parent and parent in self.entries:
            self.entries[parent].children.append(ref)
        return entry

    # ------------------------------------------------------------------ access
    def __len__(self) -> int:
        return len(self._order)

    def __iter__(self) -> Iterator[Entry]:
        for ref in self._order:
            yield self.entries[ref]

    def refs(self) -> tuple[str, ...]:
        return tuple(self._order)

    def get(self, ref: str) -> Entry:
        """The entry for a ref, or a specific refusal.

        Three different mistakes are three different errors on purpose: a
        malformed ref is the caller's bug, a ref from another snapshot means
        look again, and a ref that no longer exists means the window changed.
        """
        match = REF_PATTERN.match(str(ref or "").strip())
        if not match:
            raise UiTreeError(
                "INVALID_ARGS",
                f"'{ref}' is not a ref; refs look like @{self.snapshot_id}:e0 and must "
                "carry the snapshot they came from",
            )
        if match.group("snapshot") != self.snapshot_id:
            raise UiTreeError(
                "STALE_REF",
                f"ref {ref} belongs to snapshot {match.group('snapshot')}, "
                f"not {self.snapshot_id}",
            )
        entry = self.entries.get(f"@{self.snapshot_id}:e{match.group('index')}")
        if entry is None:
            raise UiTreeError("STALE_REF", f"ref {ref} is not in snapshot {self.snapshot_id}")
        return entry

    def find(
        self,
        name: str = "",
        role: str = "",
        *,
        exact: bool = False,
        include_hidden: bool = False,
        actionable_only: bool = True,
    ) -> Entry:
        """The one element that answers to this name and role.

        Ambiguity is an error, not a coin toss: two buttons called "Save" in two
        toolbars is a real situation, and picking one silently is how an agent
        saves the wrong document.
        """
        wanted_name = " ".join(str(name or "").split()).lower()
        wanted_role = ROLE_ALIASES.get(str(role or "").strip().lower(), str(role or "").strip().lower())

        def search(actionable: bool) -> list[Entry]:
            found: list[Entry] = []
            for entry in self:
                if entry.sensitive:
                    continue
                if actionable and not entry.actionable:
                    continue
                if not include_hidden and not entry.visible:
                    continue
                if wanted_role and entry.role != wanted_role:
                    continue
                haystack = " ".join(entry.name.split()).lower()
                if not wanted_name or (
                    haystack == wanted_name if exact else wanted_name in haystack
                ):
                    found.append(entry)
            return found

        matches = search(actionable_only)
        if not matches and actionable_only:
            # A container has nothing to act on, but it is still a name the caller
            # may want — "Report" is how you drill into the document. Preferring
            # actionable matches and falling back here keeps "Save" from returning
            # the toolbar named after it.
            matches = search(False)
        if not matches:
            raise UiTreeError(
                "NOT_FOUND",
                f"nothing in {self.app or 'this window'} matches "
                f"{wanted_role or 'any element'} '{name}'",
            )
        if len(matches) > 1:
            names = ", ".join(f"{m.role} '{m.name}' {m.ref}" for m in matches[:5])
            raise UiTreeError(
                "AMBIGUOUS_TARGET",
                f"{len(matches)} elements match '{name}' ({names}); "
                "use one of those refs",
            )
        return matches[0]

    def region(self, ref: str) -> tuple[Entry, ...]:
        """The subtree under a ref, including the ref itself."""
        root = self.get(ref)
        out = [root]
        stack = list(root.children)
        while stack:
            entry = self.entries.get(stack.pop())
            if entry is None:
                continue
            out.append(entry)
            stack.extend(entry.children)
        return tuple(out)

    def drill_targets(self) -> tuple[Entry, ...]:
        return tuple(entry for entry in self if entry.truncated)

    # ------------------------------------------------------------------ render
    def render(self, *, max_lines: int = 120, only_actionable: bool = True) -> str:
        """The text a model reads. One element per line, parents indented.

        Kept terse on purpose. A snapshot is paid for in prompt tokens on every
        turn of a task, so the format carries no punctuation that does not
        change a decision, and containers with nothing to do are dropped.
        """
        lines: list[str] = []
        for entry in self:
            if (
                only_actionable
                and not entry.actionable
                and not entry.truncated
                and (entry.role in CONTAINER_ROLES or not entry.name)
            ):
                continue
            if len(lines) >= max_lines:
                lines.append(f"… {len(self._order) - len(lines)} more elements; drill to narrow")
                break
            lines.append("  " * min(entry.depth, 6) + entry.line())
        header = f"snapshot {self.snapshot_id} · {self.app or 'app'} · {len(self._order)} elements"
        if self.redacted_count:
            header += f" · {self.redacted_count} redacted"
        if self.truncated_count:
            header += f" · {self.truncated_count} truncated"
        return header + "\n" + "\n".join(lines)

    def to_dict(self) -> dict:
        """The JSON envelope. Same shape as `render`, for programmatic callers."""
        return {
            "snapshot_id": self.snapshot_id,
            "app": self.app,
            "window": self.window,
            "count": len(self._order),
            "redacted": self.redacted_count,
            "truncated": self.truncated_count,
            "elements": [
                {
                    "ref": e.ref,
                    "role": e.role,
                    "name": e.name,
                    "value": e.value,
                    "enabled": e.enabled,
                    "visible": e.visible,
                    "actions": list(e.actions),
                    "depth": e.depth,
                    "parent": e.parent,
                    "children_total": e.children_total,
                    "truncated": e.truncated,
                }
                for e in self
            ],
        }

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def summary(self) -> str:
        """One sentence for speech: what is on screen, and how much of it."""
        count = len(self._order)
        actionable = sum(1 for entry in self if entry.actionable)
        where = self.window or self.app or "the window"
        return f"{where}: {count} elements, {actionable} you can act on."


def is_ref(value: str) -> bool:
    return bool(REF_PATTERN.match(str(value or "").strip()))


def coerce_actions(action: str, available: Iterable[str]) -> str:
    """The action to run, or the closest one this element supports.

    A model that says "click" on a text field, or "press" on a button, is not
    wrong about intent. The mapping below is the small set of equivalences that
    hold across UI Automation and ARIA, and beyond it the answer is a refusal
    naming what the element does support.
    """
    wanted = str(action or "").strip().lower().replace(" ", "_")
    supported = {str(a).strip().lower().replace(" ", "_") for a in available}
    if not supported:
        raise UiTreeError("UNSUPPORTED_ACTION", "this element reports no actions")
    if wanted in supported:
        return wanted
    equivalents = {
        "click": ("invoke", "press", "select", "toggle", "focus"),
        "invoke": ("click",),
        "press": ("invoke", "click"),
        "type": ("set_value", "setvalue", "value"),
        "set_value": ("type", "setvalue", "value"),
        "toggle": ("check", "click"),
        "check": ("toggle",),
        "expand": ("click",),
        "select": ("click", "select_item", "setfocus"),
        "focus": ("setfocus", "select"),
    }
    for candidate in equivalents.get(wanted, ()):
        if candidate in supported:
            return candidate
    offered = ", ".join(sorted(supported))
    raise UiTreeError(
        "UNSUPPORTED_ACTION",
        f"'{action}' is not available here; this element supports: {offered}",
    )
