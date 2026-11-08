"""Transactional generations for reloadable action and plugin leaves.

The owner-approved rule is: build a candidate beside the active registry, validate it,
then swap at a reconnect boundary. Keep one prior generation. A failed import or a missing
previously-active tool leaves both the active registries and `sys.modules` as they were.

This module watches only `actions/` and `plugins/`. It never reloads the referee, `main.py`,
provider code, or any running step. `refresh()` is synchronous; callers must use it only
when a conversation session and its tool calls have ended.
"""

from __future__ import annotations

import hashlib
import importlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

_PREFIXES = ("actions.", "plugins.")


def tree_signature(roots: tuple[Path, ...]) -> str:
    """A stable digest of leaf source paths and bytes. No mtime races."""
    digest = hashlib.sha256()
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            if not path.is_file() or path.name == "__init__.py":
                continue
            digest.update(path.relative_to(root).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def attach_leaf_module(name: str, module: object) -> None:
    """Keep the parent package attribute consistent with its sys.modules entry."""
    parent_name, separator, child_name = name.rpartition(".")
    if not separator:
        return
    parent = sys.modules.get(parent_name)
    if parent is None:
        try:
            parent = importlib.import_module(parent_name)
        except ImportError:
            return
    setattr(parent, child_name, module)


def detach_leaf_module(name: str, module: object) -> None:
    parent_name, separator, child_name = name.rpartition(".")
    parent = sys.modules.get(parent_name) if separator else None
    if parent is not None and getattr(parent, "__dict__", {}).get(child_name) is module:
        delattr(parent, child_name)


def clear_leaf_modules(package: str, force_reload: bool) -> None:
    """Drop one leaf package's modules and package attributes before reload."""
    if not force_reload:
        return
    prefix = f"{package}."
    names = sorted((name for name in sys.modules if name.startswith(prefix)),
                   key=lambda name: name.count("."), reverse=True)
    for name in names:
        module = sys.modules.pop(name, None)
        if module is not None:
            detach_leaf_module(name, module)


def _modules() -> dict[str, object]:
    return {name: module for name, module in sys.modules.items()
            if name.startswith(_PREFIXES)}


def _restore_modules(saved: dict[str, object]) -> None:
    current = sorted((name for name in sys.modules if name.startswith(_PREFIXES)),
                     key=lambda name: name.count("."), reverse=True)
    for name in current:
        module = sys.modules.pop(name, None)
        if module is not None:
            detach_leaf_module(name, module)
    sys.modules.update(saved)
    for name in sorted(saved, key=lambda value: value.count(".")):
        attach_leaf_module(name, saved[name])


def _clear_bytecode(roots: tuple[Path, ...]) -> None:
    """Do not let same-second, same-size edits import stale CPython caches."""
    for root in roots:
        for cached in Path(root).rglob("*.pyc"):
            cached.unlink()


@dataclass
class Generation:
    number: int
    signature: str | None
    actions: object
    plugins: object
    modules: dict[str, object]


class LeafGenerations:
    """Active + previous action/plugin registries with fail-closed staging."""

    def __init__(self, roots: tuple[Path, ...], actions, plugins):
        self.roots = tuple(Path(root) for root in roots)
        try:
            signature = tree_signature(self.roots)
            self.initial_signature_error: str | None = None
        except OSError as error:
            # Discovery has already produced usable registries. Keep them active
            # and let refresh() retry the fingerprint at the next safe boundary.
            signature = None
            self.initial_signature_error = str(error)
        self.active = Generation(1, signature, actions, plugins, _modules())
        self.previous: Generation | None = None
        self._refused_signature: str | None = None

    @staticmethod
    def _names(registry) -> set[str]:
        return set(registry.names())

    @staticmethod
    def _failures(registry) -> dict[str, str]:
        method = getattr(registry, "failures", None)
        return dict(method()) if callable(method) else {}

    def refresh(self, build: Callable[[], tuple[object, object]]) -> dict:
        """Build and validate changed leaves. The old generation survives refusal."""
        try:
            signature = tree_signature(self.roots)
        except OSError as error:
            return {"ok": False, "changed": False, "note": f"could not scan leaves: {error}"}
        if signature == self.active.signature:
            return {"ok": True, "changed": False, "generation": self.active.number}
        if signature == self._refused_signature:
            return {"ok": False, "changed": False, "already_reported": True,
                    "note": "the same leaf candidate was already refused"}

        module_snapshot = _modules()
        try:
            _clear_bytecode(self.roots)
            actions, plugins = build()
            missing_actions = self._names(self.active.actions) - self._names(actions)
            missing_plugins = self._names(self.active.plugins) - self._names(plugins)
            old_action_failures = self._failures(self.active.actions)
            old_plugin_failures = self._failures(self.active.plugins)
            added_failures = {
                name for name, error in self._failures(actions).items()
                if old_action_failures.get(name) != error
            } | {
                name for name, error in self._failures(plugins).items()
                if old_plugin_failures.get(name) != error
            }
            if missing_actions or missing_plugins or added_failures:
                _restore_modules(module_snapshot)
                self._refused_signature = signature
                missing = sorted(missing_actions | missing_plugins | added_failures)
                return {"ok": False, "changed": False,
                        "note": "candidate was refused; active tools remain loaded: "
                                + ", ".join(missing[:8])}
        except Exception as error:
            _restore_modules(module_snapshot)
            self._refused_signature = signature
            return {"ok": False, "changed": False,
                    "note": f"candidate was refused; active tools remain loaded: {error}"}

        self._refused_signature = None
        candidate = Generation(self.active.number + 1, signature, actions, plugins, _modules())
        self.previous, self.active = self.active, candidate
        return {"ok": True, "changed": True, "generation": candidate.number,
                "note": f"leaf generation {candidate.number} is ready"}

    def rollback(self) -> dict:
        """Restore the previous registry and its module table at a safe boundary."""
        if self.previous is None:
            return {"ok": False, "note": "there is no previous leaf generation"}
        failed = self.active
        restored = self.previous
        _restore_modules(restored.modules)
        self.previous, self.active = failed, restored
        try:
            self._refused_signature = tree_signature(self.roots)
        except OSError:
            self._refused_signature = None
        return {"ok": True, "generation": restored.number,
                "note": f"restored leaf generation {restored.number}"}
