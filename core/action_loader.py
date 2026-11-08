"""
Action discovery, validation, and dispatch — the built-in twin of plugin_loader.

Every actions/*.py that exposes a module-level ``TOOL`` dict is auto-discovered
here, exactly like a drop-in plugin, so main.py never has to hardcode a tool
declaration or a dispatch branch for it. Adding a new bundled action is then the
same one-file operation as writing a plugin: define ``TOOL`` and a handler.

``TOOL`` shape (see actions/open_app.py for a live example):

    TOOL = {
        "name":        "open_app",              # unique, ^[a-zA-Z_][a-zA-Z0-9_]{0,63}$
        "description":  "...",                   # what Gemini reads to route the call
        "parameters":  {"type": "OBJECT", ...}, # Gemini function-declaration schema
        "handler":      open_app,                # the callable to run
    }

The handler is invoked through signature introspection: it receives ``parameters``
plus whichever of ``player`` / ``speak`` / ``response`` / ``session_memory`` it
actually declares — so existing action signatures work unchanged.

Discovery runs once at startup; import errors, validation errors, and name
collisions are logged and the offending file is skipped — they NEVER raise out
of discover_actions() and never abort the scan of the remaining files.
"""
from __future__ import annotations
from core import failures
from core.leaf_generations import clear_leaf_modules

import importlib.util
import inspect
import re
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")
_DEFAULT_PARAMS = {"type": "OBJECT", "properties": {}}
_CTX_KEYS = ("player", "speak", "response", "session_memory")


# A tool may declare that the model should NOT be held up waiting for it.
# `behavior` goes to the API with the declaration; `scheduling` decides when the
# eventual result is allowed back into the conversation:
#   WHEN_IDLE  — wait for a gap in the speech (the sane default)
#   SILENT     — record it, do not prompt a reply (the tool already announced)
#   INTERRUPT  — cut in immediately (only when the answer cannot wait)
_BEHAVIORS = ("BLOCKING", "NON_BLOCKING")
_SCHEDULING = ("WHEN_IDLE", "SILENT", "INTERRUPT")


# Keys this project puts on a declaration for its own bookkeeping. They live
# here because this file documents what a TOOL dict may contain, and both
# loaders produce them.
#
# THEY MUST NEVER REACH A VENDOR. Gemini validates function declarations
# against a fixed schema and an unknown field is an error, not something it
# ignores — so main.py calls strip_meta() before building the Live config.
#
# The definition is here rather than in providers/schema.py, which is the only
# other place that cares, because main.py must be able to strip them WITHOUT
# importing providers: a default install never loads that package, and the
# measured cost of deciding not to is the release's headline number.
META_KEYS = ("tier", "brief")


# A property type the provider accepts. Anything else in a declaration is a
# validation error on the whole request, not just on that field.
TYPE_NAMES = {"STRING", "NUMBER", "INTEGER", "BOOLEAN", "ARRAY", "OBJECT"}


def sanitize_declarations(decls):
    """Make every declaration acceptable to the provider, and say what was repaired.

    A single bad field does not fail that tool. It fails the whole session: the Live
    API answers 1007 and names the index of the declaration, so the assistant cannot
    connect at all and the activity log looks like a broken API key.

    That is exactly what happened with the five bridge plugins: each declared
    `"required": ["action"]` and never declared an `action` property, because the
    handler reads it from the call rather than from the schema. The provider rejected
    the list at index 40 and the app spent the evening asking for a new key.

    The plugins are fixed. This function is the reason one of them cannot do that
    again: a `required` name with no property behind it is removed, a property with no
    type is given one, and every repair is returned as a sentence a person can read.
    """
    clean, repairs = [], []
    for declaration in decls:
        if not isinstance(declaration, dict):
            clean.append(declaration)
            continue
        params = declaration.get("parameters")
        if not isinstance(params, dict):
            clean.append(declaration)
            continue
        props = params.get("properties")
        if not isinstance(props, dict):
            props = {}
            params = dict(params, properties=props)
        name = str(declaration.get("name") or "?")
        fixed = _repair_properties(name, props, repairs)
        out_params = dict(params, properties=fixed)
        # Only touch `required` when the declaration had one. Adding an empty list to a
        # tool that never had the key would change what a correct build sends, and this
        # pass must be invisible on a correct build.
        if "required" in params:
            out_params["required"] = _repair_required(
                name, {"properties": fixed, "required": params.get("required")}, repairs)
        clean.append(dict(declaration, parameters=out_params))
    return clean, repairs


def _repair_properties(name: str, props: dict, repairs: list) -> dict:
    """Every property must be an object with a type the provider knows."""
    out = {}
    for key, value in props.items():
        if not isinstance(value, dict):
            repairs.append(f"{name}.{key}: not an object, sent as a string")
            value = {"type": "STRING"}
        kind = str(value.get("type") or "").upper()
        if kind not in TYPE_NAMES:
            repairs.append(f"{name}.{key}: type {value.get('type')!r} is not one the "
                           f"provider accepts, sent as STRING")
            value = dict(value, type="STRING")
        out[key] = value
    return out


def _repair_required(name: str, params: dict, repairs: list) -> list:
    """`required` may only name a property that exists.

    Written as a loop rather than a comprehension on purpose: the repair has to be
    reported, and a side effect hidden inside a filter is how a repair list ends up
    empty when it should not be.
    """
    wanted = params.get("required") or []
    props = params.get("properties") or {}
    kept = []
    for key in wanted:
        if key in props:
            kept.append(key)
        else:
            repairs.append(f"{name}: '{key}' was required but never declared")
    return kept


def strip_meta(decls):
    """Declarations without META_KEYS. Non-dict entries pass through untouched;
    a declaration carrying none is returned as the same object, so what an API
    receives is byte-for-byte what it received before these keys existed."""
    out = []
    for decl in decls:
        if isinstance(decl, dict) and any(k in decl for k in META_KEYS):
            out.append({k: v for k, v in decl.items() if k not in META_KEYS})
        else:
            out.append(decl)
    return out


def _opt_upper(value, allowed: tuple[str, ...]) -> Optional[str]:
    v = str(value or "").strip().upper()
    return v if v in allowed else None

def _opt_tier(value) -> Optional[str]:
    """"core" or "extra" from a declaration, or None when it did not say.

    Anything else is treated as "did not say" rather than as an error: a typo
    should fall back to the default ranking, not stop a working tool loading.
    """
    text = str(value or "").strip().lower()
    return text if text in ("core", "extra") else None


def _opt_text(value) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


@dataclass
class ActionRecord:
    name: str
    description: str = ""
    parameters: dict = field(default_factory=lambda: dict(_DEFAULT_PARAMS))
    handler: Optional[Callable] = None
    file: str = ""
    valid: bool = False
    error: str = ""
    behavior: Optional[str] = None     # None = the API's default (blocking)
    scheduling: Optional[str] = None   # None = the API's default (WHEN_IDLE)
    # Read by providers/schema.py when a small model gets a tool budget; never
    # sent to any API — main.py strips both before the Gemini config is built.
    #   tier   "core" | "extra" — this file's own opinion of whether it should
    #          survive a tight budget, instead of that being decided by the
    #          order files happen to be discovered in.
    #   brief  a short description used in place of the long one when a budget
    #          is in force. Nothing is deleted: Gemini still gets the full text.
    tier: Optional[str] = None
    brief: Optional[str] = None


class ActionRegistry:
    def __init__(self, actions: dict[str, ActionRecord], logger: Callable[[str], None]):
        self._actions = actions          # name -> ActionRecord, VALID entries only
        self._all_records: list[ActionRecord] = []
        self._logger = logger

    # -- called by main.py at LiveConnectConfig build time --
    def get_tool_declarations(self) -> list[dict]:
        out = []
        for rec in self._actions.values():
            decl = {"name": rec.name, "description": rec.description,
                    "parameters": rec.parameters}
            if rec.behavior:
                decl["behavior"] = rec.behavior
            # Budget metadata. NOT part of any API's schema — main.py calls
            # providers.schema.strip_meta() before the Gemini config is built,
            # and budget() consumes them on the local-engine path.
            if rec.tier:
                decl["tier"] = rec.tier
            if rec.brief:
                decl["brief"] = rec.brief
            out.append(decl)
        return out

    def has(self, name: str) -> bool:
        return name in self._actions

    def scheduling(self, name: str) -> Optional[str]:
        """How this action's result should re-enter the conversation, if it said."""
        rec = self._actions.get(name)
        return rec.scheduling if rec else None

    def names(self) -> set[str]:
        return set(self._actions.keys())

    def failures(self) -> dict[str, str]:
        """Every action file that did not load, mapped to the reason.

        Discovery has always kept these in an internal list, which meant the only
        trace of a missing capability was a line in a console the user may never
        read — and a tool the model can see in the policy tables but never call.
        Missing playwright taking `browser_control` out of the session is the case
        that prompted this: it should be a sentence, not a silence.
        """
        return {rec.file[:-3] if rec.file.endswith(".py") else rec.file: rec.error
                for rec in self._all_records if not rec.valid and rec.error}

    # -- called by main.py from _execute_tool --
    def run(self, name: str, parameters: dict, ctx: dict | None = None) -> str:
        rec = self._actions.get(name)
        if rec is None or not rec.valid:
            return f"Action '{name}' is not available."
        try:
            return _call_handler(rec.handler, _coerce_parameters(
                _clean_parameters(parameters), rec.parameters), ctx or {}) or "Done."
        except Exception as e:
            self._logger(f"Action '{name}' crashed during run(): {e}")
            if sys.stderr is not None:
                try:
                    print(_safe_traceback(), file=sys.stderr)
                except Exception as error:
                    failures.note("action_loader.run", error)
            return f"Tool '{name}' failed: {e}"


def _coerce_parameters(parameters: dict, schema: dict | None) -> dict:
    """Give each value the type the tool DECLARED for it.

    Dropping nulls was not enough: a model that sends `{"action": 5}` or
    `{"volume": "40"}` got "Tool 'video_player' failed: 'int' object has no
    attribute 'strip'" back — a crash the model cannot act on, for a value the
    declaration already says is text. Coercing to the declared type is exactly
    what the declaration promised, so no handler has to defend itself, including
    the ones written later. Values that cannot be coerced are left alone: the
    handler refuses them in words, which is the answer the model can use.
    """
    properties = (schema or {}).get("properties") if isinstance(schema, dict) else None
    if not isinstance(properties, dict) or not properties:
        return parameters
    out = {}
    for key, value in parameters.items():
        kind = str((properties.get(key) or {}).get("type") or "").upper()
        if kind == "STRING" and isinstance(value, (int, float, bool)):
            out[key] = str(value)
        elif kind in ("NUMBER", "INTEGER") and isinstance(value, str):
            try:
                out[key] = float(value) if kind == "NUMBER" else int(float(value))
            except (TypeError, ValueError):
                out[key] = value
        elif kind == "BOOLEAN" and isinstance(value, str):
            low = value.strip().lower()
            out[key] = True if low in ("true", "1", "yes") else (
                False if low in ("false", "0", "no") else value)
        else:
            out[key] = value
    return out


def _clean_parameters(parameters):
    """Strip explicit `None` values before a handler sees them.

    A model that omits an optional argument and a model that sends
    `"action": null` are saying the same thing, but only the first reaches a
    handler safely: `params.get("action", "")` returns the default only when the
    key is ABSENT, so an explicit null comes back as None and `.lower()` raises
    AttributeError. Measured: six of the seventeen actions crashed this way on a
    single null — the model gets back "Tool 'file_controller' failed:
    'NoneType' object has no attribute 'lower'", which it cannot act on.

    Dropping nulls here fixes all of them and every future action, at the one
    place every tool call passes through.
    """
    if not isinstance(parameters, dict):
        return {} if parameters is None else parameters
    return {k: v for k, v in parameters.items() if v is not None}


def _call_handler(fn: Callable, parameters: dict, ctx: dict) -> str:
    """Invoke the handler passing only the context kwargs it actually declares
    (or all of them if it has **kwargs), so each action's existing signature
    works unchanged."""
    sig = inspect.signature(fn)
    has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
    kwargs = {}
    for key in _CTX_KEYS:
        if has_var_kw or key in sig.parameters:
            kwargs[key] = ctx.get(key)
    return fn(parameters=_clean_parameters(parameters), **kwargs)


def _validate(module, filename: str) -> ActionRecord:
    """Returns an ActionRecord; .valid=False + .error set on any problem. Never raises."""
    tool = getattr(module, "TOOL", None)
    if not isinstance(tool, dict):
        return ActionRecord(name=Path(filename).stem, file=filename,
                            error="No module-level TOOL dict (not a discoverable action).")

    name = tool.get("name")
    if not isinstance(name, str) or not _NAME_RE.match(name):
        return ActionRecord(name=str(name or Path(filename).stem), file=filename,
                            error="TOOL['name'] missing or not a valid identifier.")

    description = tool.get("description")
    if not isinstance(description, str) or not description.strip():
        return ActionRecord(name=name, file=filename,
                            error="TOOL['description'] missing or empty.")

    parameters = tool.get("parameters", _DEFAULT_PARAMS)
    if not isinstance(parameters, dict) or parameters.get("type") != "OBJECT":
        return ActionRecord(name=name, file=filename,
                            error="TOOL['parameters'] must be a dict with \"type\": \"OBJECT\".")

    handler = tool.get("handler")
    if not callable(handler):
        return ActionRecord(name=name, file=filename,
                            error="TOOL['handler'] missing or not callable.")

    return ActionRecord(name=name, description=description.strip(), parameters=parameters,
                        handler=handler, file=filename, valid=True, error="",
                        behavior=_opt_upper(tool.get("behavior"), _BEHAVIORS),
                        scheduling=_opt_upper(tool.get("scheduling"), _SCHEDULING),
                        tier=_opt_tier(tool.get("tier")),
                        brief=_opt_text(tool.get("brief")))


def _safe_traceback() -> str:
    """The current exception's traceback as text, or "" when there is nowhere to
    write it.

    `traceback.print_exc()` writes to sys.stderr, and under pythonw — the
    launcher that shows no console — sys.stderr is None, so printing raises
    AttributeError from inside the handler that was trying to be helpful and takes
    action discovery down with it. Formatting first and printing second cannot
    fail that way.
    """
    try:
        return traceback.format_exc()
    except Exception:
        return ""


def _load_action_module(path: Path, name: str, force_reload: bool):
    module = sys.modules.get(name)
    if module is not None and not force_reload:
        return module
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("could not build import spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        if force_reload:
            Path(importlib.util.cache_from_source(str(path))).unlink(missing_ok=True)
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


def discover_actions(actions_dir: Path, reserved_names: set[str] | None = None,
                     logger: Callable[[str], None] = print,
                     force_reload: bool = False) -> ActionRegistry:
    """
    Scans actions_dir for *.py files (skips files starting with '_'). A file is
    only treated as an action if it exposes a module-level TOOL dict; files
    without one (shared helpers, capture-only modules) are silently ignored.
    Import/validation errors and name collisions are logged and the file is
    skipped — they NEVER raise out of this function.
    """
    reserved = reserved_names or set()
    actions_dir.mkdir(parents=True, exist_ok=True)
    clear_leaf_modules("actions", force_reload)
    valid: dict[str, ActionRecord] = {}
    all_records: list[ActionRecord] = []

    files = sorted(actions_dir.glob("*.py"), key=lambda p: p.name)  # deterministic order
    for path in files:
        if path.name.startswith("_"):
            continue
        try:
            module_name = f"actions.{path.stem}"
            # Startup reuses modules. A staged generation asks for fresh leaves.
            module = _load_action_module(path, module_name, force_reload)

            if getattr(module, "TOOL", None) is None:
                continue   # not an action file — a helper/capture-only module

            rec = _validate(module, path.name)

            if rec.valid and rec.name in reserved:
                rec = ActionRecord(name=rec.name, file=path.name,
                                   error=f"Name '{rec.name}' collides with a reserved core tool — rejected.")
            elif rec.valid and rec.name in valid:
                other = valid[rec.name].file
                rec = ActionRecord(name=rec.name, file=path.name,
                                   error=f"Name '{rec.name}' already used by action '{other}' — rejected.")

        except Exception as e:
            reason = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
            rec = ActionRecord(name=path.stem, file=path.name,
                               error=f"Failed to load: {reason}")
            # One sentence the user can act on, then the detail for whoever is
            # reading the console. Neither may raise.
            logger(f"Action unavailable: {path.stem} — {reason}")
            if sys.stderr is not None:
                try:
                    print(_safe_traceback(), file=sys.stderr)
                except Exception as error:
                    failures.note("action_loader.discover_actions", error)

        all_records.append(rec)
        if rec.valid:
            valid[rec.name] = rec
            logger(f"Action loaded: {rec.name} ({path.name})")
        else:
            # Only log a rejection if the file actually tried to be an action.
            logger(f"Action rejected: {path.name} — {rec.error}")

    registry = ActionRegistry(valid, logger)
    registry._all_records = all_records
    logger(f"Action discovery complete: {len(valid)} active.")
    return registry
