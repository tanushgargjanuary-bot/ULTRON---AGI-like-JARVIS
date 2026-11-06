"""core/ui_action.py — acting on a ref, and knowing when not to.

WHY THIS FILE EXISTS
    Reading a UI is half of computer use; the other half is doing something and
    finding out whether it worked. Two failure modes cost the most:

    1. Acting on a stale ref. The list refreshed, element 7 is now a different
       row, and the click lands on the wrong record. Anything that turns a ref
       into a click must be able to refuse when the window has moved on.
    2. Retrying something that is not safe to retry. "It failed" is not enough
       information to decide what to do next: a timeout on a button that was
       still animating is worth another attempt, a payment form that half
       submitted is not.

    So every failure here carries a **disposition** — what the caller is allowed
    to do about it — and the session marks itself stale after any action, which
    forces the agent to look again before the next one.

THE ADAPTER CONTRACT
    An adapter is anything that can produce a `Node` tree for an application and
    perform one action on one element. `core/ui_windows.py` (UI Automation) and
    `core/ui_browser.py` (DOM) implement it; `FakeAdapter` in the tests does too.
    Nothing in this file imports either, so the discipline is testable without a
    desktop, and a third backend is one class, not a rewrite.

WHAT THIS IS NOT
    It is not a permission system. Whether an action is allowed at all is
    `core/policy.py` and `core/custom_gate.py`; this file assumes the call has
    already passed them and confines itself to the mechanics of doing it safely.
"""

from __future__ import annotations
from core import failures

import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from core.ui_tree import (
    Node,
    Snapshot,
    UiTreeError,
    coerce_actions,
    is_ref,
    new_snapshot_id,
)

# What the caller is allowed to do about a failure. These are the four answers
# that change behaviour; anything more specific belongs in the message text.
RETRY_SAFE = "retry_safe"        # the same call may be repeated as-is
RESNAPSHOT = "resnapshot"        # look again, then act on the new refs
NEEDS_USER = "needs_user"        # a human has to intervene; do not loop
FATAL = "fatal"                  # this path cannot work here at all

DEFAULT_WAIT_MS = 5_000
POLL_S = 0.08

# "e12" is a ref with its snapshot torn off. It is a caller bug worth naming,
# not a name worth searching for.
_BARE_REF = re.compile(r"^e\d{1,6}$")


class UiError(Exception):
    """A failed action, with what may be done about it."""

    def __init__(self, code: str, message: str, disposition: str = FATAL,
                 *, detail: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.disposition = disposition
        self.detail = dict(detail or {})

    @property
    def retryable(self) -> bool:
        return self.disposition in (RETRY_SAFE, RESNAPSHOT)

    def as_dict(self) -> dict:
        return {
            "ok": False,
            "code": self.code,
            "message": str(self),
            "disposition": self.disposition,
            "retryable": self.retryable,
            "detail": self.detail,
        }

    def __str__(self) -> str:
        return self.args[0] if self.args else self.code


# Codes whose disposition is fixed by meaning rather than by the caller.
_DISPOSITIONS = {
    "INVALID_ARGS": FATAL,
    "STALE_REF": RESNAPSHOT,
    "AMBIGUOUS_TARGET": NEEDS_USER,
    "NOT_FOUND": RESNAPSHOT,
    "NOT_ENABLED": RETRY_SAFE,
    "NOT_VISIBLE": RETRY_SAFE,
    "TIMEOUT": RETRY_SAFE,
    "UNSUPPORTED_ACTION": NEEDS_USER,
    "APP_GONE": RESNAPSHOT,
    "NO_TREE": FATAL,
    "NO_ADAPTER": FATAL,
    "ADAPTER_FAILED": RETRY_SAFE,
}


def ui_error(code: str, message: str, detail: dict | None = None) -> UiError:
    """A `UiError` whose disposition comes from the code's meaning."""
    return UiError(code, message, _DISPOSITIONS.get(code, FATAL), detail=detail)


def from_tree_error(exc: UiTreeError) -> UiError:
    return ui_error(exc.code, str(exc))


@dataclass
class Result:
    """What happened, in a shape both a model and a log can read."""

    ok: bool
    action: str = ""
    ref: str = ""
    app: str = ""
    message: str = ""
    snapshot_id: str = ""
    waited_ms: int = 0
    error: UiError | None = None

    def as_dict(self) -> dict:
        if not self.ok and self.error is not None:
            payload = self.error.as_dict()
            payload.update({"action": self.action, "ref": self.ref, "app": self.app})
            return payload
        return {
            "ok": True,
            "action": self.action,
            "ref": self.ref,
            "app": self.app,
            "message": self.message,
            "snapshot_id": self.snapshot_id,
            "waited_ms": self.waited_ms,
        }

    def spoken(self) -> str:
        if self.ok:
            return self.message or "done"
        return f"{self.error.code.lower().replace('_', ' ')}: {self.error}" if self.error else "failed"


@runtime_checkable
class Adapter(Protocol):
    """What a platform bridge has to provide. Four calls, no more."""

    name: str

    def capabilities(self) -> set[str]:
        """Free-form tags: 'uia', 'dom', 'keyboard', 'headless', 'vision'."""

    def snapshot(self, app: str = "", root_ref: str | None = None,
                 max_depth: int | None = None) -> Node:
        """The tree for an application (or one region of the last snapshot)."""

    def perform(self, entry, action: str, value: str = "") -> None:
        """Do one thing to one element. Raise `UiError` on failure."""

    def probe(self, entry) -> tuple[bool, bool] | None:
        """(visible, enabled) for an element right now, or None if unknown."""


class Session:
    """One task's worth of looking and acting.

    The session is deliberately stateful in exactly one way: it remembers the
    snapshot its refs came from, and refuses to use a ref after anything has
    changed. Everything else is passed in.
    """

    def __init__(self, adapter: Adapter | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 sleeper: Callable[[float], None] = time.sleep) -> None:
        self._adapter = adapter
        self._clock = clock
        self._sleep = sleeper
        self.snapshot: Snapshot | None = None
        self.dirty = True                  # no usable snapshot until one is taken
        self.history: list[Result] = []

    # ------------------------------------------------------------------ adapter
    @property
    def adapter(self) -> Adapter:
        if self._adapter is None:
            raise ui_error(
                "NO_ADAPTER",
                "no accessibility bridge is available on this machine; "
                "call core.ui_adapters.select() to find out why",
            )
        return self._adapter

    def capabilities(self) -> set[str]:
        try:
            return set(self.adapter.capabilities())
        except Exception:                 # noqa: BLE001 - a broken probe is not a capability
            return set()

    # ----------------------------------------------------------------- observe
    def observe(self, app: str = "", *, skeleton: bool = False,
                max_depth: int | None = None, max_nodes: int | None = None) -> Snapshot:
        """Take a snapshot. `skeleton=True` clamps depth for a cheap first look."""
        snapshot_id = new_snapshot_id()
        _announce_snapshot(self.adapter, snapshot_id)
        root = self.adapter.snapshot(app, None, 3 if skeleton else max_depth)
        kwargs = {}
        if max_nodes:
            kwargs["max_nodes"] = max_nodes
        self.app = app or str(getattr(root, "name", "") or "")
        self.snapshot = Snapshot.capture(
            root, app=self.app, window=str(root.name or ""),
            snapshot_id=snapshot_id, **kwargs
        )
        self.dirty = False
        return self.snapshot

    def drill(self, ref: str, *, max_depth: int | None = None) -> Snapshot:
        """Read one region as a fresh snapshot.

        agent-desktop keeps the same snapshot id when it drills, because its refs
        are globally numbered. Here a drill is a new snapshot with new refs, which
        is a deliberate difference: the property that matters is that a ref taken
        before the drill is refused afterwards rather than silently resolving to a
        different element. A new id gives that for free with any adapter, including
        ones that number elements per subtree.
        """
        current = self._require_snapshot()
        current.get(ref)                       # validates the ref before any OS call
        snapshot_id = new_snapshot_id()
        _announce_snapshot(self.adapter, snapshot_id)
        root = self.adapter.snapshot(current.app, ref, max_depth)
        self.snapshot = Snapshot.capture(
            root, app=current.app, window=current.window, snapshot_id=snapshot_id
        )
        self.dirty = False
        return self.snapshot

    def _require_snapshot(self) -> Snapshot:
        if self.snapshot is None or self.dirty:
            raise ui_error(
                "STALE_REF",
                "no current snapshot; call observe() again before using a ref",
            )
        return self.snapshot

    # -------------------------------------------------------------------- find
    def resolve(self, target: str, *, role: str = "") -> object:
        """A ref, or a name, turned into the one element it means."""
        snapshot = self._require_snapshot()
        text = str(target or "").strip()
        if not text:
            raise ui_error("INVALID_ARGS", "no target was given")
        try:
            if is_ref(text):
                return snapshot.get(text)
            if text.startswith("@") or _BARE_REF.match(text):
                raise ui_error(
                    "INVALID_ARGS",
                    f"'{text}' is not a ref: a ref carries the snapshot it came from, "
                    f"like @{snapshot.snapshot_id}:e0",
                )
            return snapshot.find(text, role)
        except UiTreeError as exc:
            raise from_tree_error(exc) from exc

    # --------------------------------------------------------------------- act
    def act(self, target: str, action: str = "click", value: str = "",
            *, role: str = "", wait_ms: int = DEFAULT_WAIT_MS,
            confirm: Callable[[object, str], bool] | None = None) -> Result:
        """Wait for the element, act on it, and mark the snapshot stale."""
        started = self._clock()
        entry = None
        try:
            entry = self.resolve(target, role=role)
            self._wait_until_ready(entry, wait_ms)
            try:
                action_name = coerce_actions(action, entry.actions)
            except UiTreeError as exc:
                raise from_tree_error(exc) from exc
            if confirm is not None and not confirm(entry, action_name):
                raise ui_error("DECLINED", "the confirmation for this action was refused",
                               {"ref": entry.ref, "action": action_name})
            self.adapter.perform(entry, action_name, value)
        except UiError as exc:
            result = Result(False, action, getattr(entry, "ref", ""), self._app(),
                            message=str(exc), error=exc,
                            snapshot_id=getattr(self.snapshot, "snapshot_id", ""),
                            waited_ms=int((self._clock() - started) * 1000))
            self.dirty = True               # a failed act still may have changed things
            self.history.append(result)
            return result
        except Exception as exc:            # noqa: BLE001 - a crash must not escape
            error = ui_error("ADAPTER_FAILED", f"{type(exc).__name__}: {exc}")
            result = Result(False, action, getattr(entry, "ref", ""), self._app(),
                            message=str(error), error=error)
            self.dirty = True
            self.history.append(result)
            return result

        self.dirty = True
        result = Result(
            True, action_name, entry.ref, self._app(),
            message=f"{action_name.replace('_', ' ')} on {entry.role} '{entry.name}'",
            snapshot_id=getattr(self.snapshot, "snapshot_id", ""),
            waited_ms=int((self._clock() - started) * 1000),
        )
        self.history.append(result)
        return result

    def _wait_until_ready(self, entry, wait_ms: int) -> None:
        """Poll until the element is visible and enabled, or say it never was."""
        probe = getattr(self.adapter, "probe", None)
        if probe is None:
            return
        deadline = self._clock() + max(0, wait_ms) / 1000.0
        while True:
            state = probe(entry)
            if state is None:
                return
            visible, enabled = state
            if visible and enabled:
                return
            if self._clock() >= deadline:
                code = "NOT_VISIBLE" if not visible else "NOT_ENABLED"
                raise ui_error(
                    code,
                    f"{entry.role} '{entry.name}' never became "
                    f"{'visible' if not visible else 'enabled'} "
                    f"within {wait_ms} ms; it may be behind a dialog",
                )
            self._sleep(POLL_S)

    # ------------------------------------------------------------------- batch
    def batch(self, operations: Sequence[dict],
              app: str | None = None) -> list[Result]:
        """Several actions, with a fresh look before each one.

        The first version did not look again between steps, so every batch of two
        or more failed on step two: an action marks the snapshot stale, on purpose,
        and the next step then had nothing legitimate to resolve against. Measured
        before the fix — a three-step form fill performed zero actions.

        Looking again has one consequence the caller has to know: a ref belongs to
        one snapshot, so a ref given for step two is stale by the time it is used.
        In a batch, refer to elements by NAME. A ref that fails that way stops the
        batch with a message saying exactly this, rather than acting on whatever
        now sits at that number.

        Stops at the first failure: continuing past a failed step is how a form
        gets filled into the wrong dialog.
        """
        results: list[Result] = []
        target_app = app if app is not None else self.app
        for operation in operations:
            if not isinstance(operation, dict):
                error = ui_error("INVALID_ARGS", "each operation must be an object")
                results.append(Result(False, message=str(error), error=error))
                break
            if self.snapshot is None or self.dirty:
                try:
                    self.observe(target_app)
                except UiError as exc:
                    results.append(Result(False, message=str(exc), error=exc))
                    break
            result = self.act(
                str(operation.get("target") or ""),
                str(operation.get("action") or operation.get("do") or "click"),
                str(operation.get("value") or ""),
                role=str(operation.get("role") or ""),
                wait_ms=int(operation.get("wait_ms") or DEFAULT_WAIT_MS),
            )
            results.append(result)
            if not result.ok:
                if result.error is not None and result.error.code == "STALE_REF":
                    result = Result(
                        False, result.action, result.ref, result.app,
                        message=(
                            "a batch looks again between steps, so a ref from step one "
                            "cannot be used in step two — use the element's name instead"
                        ),
                        snapshot_id=result.snapshot_id, error=result.error,
                    )
                    results[-1] = result
                break
        return results

    def _app(self) -> str:
        return getattr(self.snapshot, "app", "") or ""


def _announce_snapshot(adapter: Adapter, snapshot_id: str) -> None:
    """Tell an adapter the id its refs must carry, when it numbers elements itself.

    The DOM adapter writes refs into the page, so it has to be told which
    snapshot they belong to; the UI Automation adapter relies on the ordering the
    snapshot model gives it and ignores this. Adapters that do not care simply do
    not implement it.
    """
    setter = getattr(adapter, "set_snapshot_id", None)
    if callable(setter):
        try:
            setter(snapshot_id)
        except Exception as error:  # noqa: BLE001, S110
            failures.note("ui_action._announce_snapshot", error)
