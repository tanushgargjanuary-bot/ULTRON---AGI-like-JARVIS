"""One plan on disk, so a restart does not lose the work.

The planner keeps the running plan in memory. `core/crash.py` writes down how the
process died; it does not write down what the process was doing. This module is the
small half of that: the goal, the steps, and the index, in one file.

Three rules, all of them for the same reason — a file outlives the run that wrote it:

- No output, no `data`, no evidence. Those fields hold file contents and captures.
- No argument whose name looks like a secret. If one appears, the file is removed
  rather than written with a hole in it, so a resume cannot run a half-filled step.
- Nothing is applied on its own. The file is offered in one line at start.

No dependency. `json` and a path.
"""

from __future__ import annotations

import json
import logging
import math
import re
import time
from pathlib import Path
from typing import Any, Optional

FOLDER = Path(__file__).resolve().parent.parent / "state"
logger = logging.getLogger("plan_state")
NAME = "active_plan.json"
INVALID_NAME = "active_plan.invalid"

# A plan older than this is still offered, in different words. It is never resumed
# on its own, and it is never deleted on its own either: deleting the only record of
# unfinished work is the owner's decision, not a morning chore for a timer.
MAX_AGE = 24 * 60 * 60
MAX_BYTES = 2 * 1024 * 1024

# What a resume actually needs. Everything else is dropped on the way in.
STEP_FIELDS = (
    "step_id",
    "description",
    "tool_name",
    "tool_args",
    "status",
    "verification",
    "artifact_sha256",
    "backup_id",
    "approval_recorded",
)

_STEP_REFERENCE = re.compile(
    r"\$(?:PREV_OUTPUT|PREV_DATA|OUTPUT|STEP_\d+_(?:OUTPUT|DATA))|"
    r"\{\{(?:prev_output|prev_data|output|step_\d+\.(?:output|data))\}\}|"
    r"\{(?:prev_output|prev_data|output|step_\d+_output)\}",
    re.IGNORECASE,
)

_SECRET_HINTS = ("key", "token", "secret", "password", "passwd", "credential")


def _path(folder: Optional[Path] = None) -> Path:
    """Resolve the active checkpoint path for an optional state folder."""
    return (Path(folder) if folder else FOLDER) / NAME


def _invalid_path(folder: Optional[Path] = None) -> Path:
    """Resolve the sidecar that makes any stale checkpoint non-resumable."""
    return (Path(folder) if folder else FOLDER) / INVALID_NAME


def _invalidate(folder: Optional[Path] = None) -> None:
    """Delete an old checkpoint or leave a fail-closed sidecar if deletion fails."""
    if clear(folder):
        return
    try:
        marker = _invalid_path(folder)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("checkpoint update failed; do not resume\n", encoding="utf-8")
    except (OSError, ValueError) as error:
        # If storage itself is unavailable there is no durable place to mark unsafe.
        logger.warning("could not mark the active plan unsafe: %s", error)
        return


def _secret_in(value: Any) -> bool:
    """True when any dictionary key below `value` names a secret."""
    if isinstance(value, dict):
        for name, inner in value.items():
            if any(hint in str(name).lower() for hint in _SECRET_HINTS):
                return True
            if _secret_in(inner):
                return True
    elif isinstance(value, list):
        return any(_secret_in(item) for item in value)
    return False


def has_step_output_references(value: Any) -> bool:
    """True when arguments depend on output/data omitted from the disk checkpoint."""
    if isinstance(value, str):
        return bool(_STEP_REFERENCE.search(value))
    if isinstance(value, dict):
        return any(has_step_output_references(item) for item in value.values())
    if isinstance(value, list):
        return any(has_step_output_references(item) for item in value)
    return False


def _json_safe(value: Any) -> bool:
    """Reject values that cannot be safely represented as finite JSON."""
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_json_safe(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _json_safe(item)
                   for key, item in value.items())
    return False


def _number(value: Any, *, integer: bool = False) -> bool:
    """Validate a finite numeric checkpoint field and optional integer form."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        finite = math.isfinite(value)
    except (OverflowError, ValueError):
        return False
    if not finite:
        return False
    return not integer or not isinstance(value, float) or value.is_integer()


_VALID_STATUSES = {"pending", "running", "completed", "failed", "skipped", "retrying"}


def _valid_step(row: Any) -> Optional[int]:
    """Return a step id only when its resume fields are well formed."""
    if not isinstance(row, dict):
        return None
    step_id = row.get("step_id")
    if isinstance(step_id, bool) or not isinstance(step_id, int) or step_id < 1:
        return None
    if not isinstance(row.get("tool_name"), str) or not row["tool_name"].strip():
        return None
    if not isinstance(row.get("description"), str):
        return None
    arguments = row.get("tool_args")
    if not isinstance(arguments, dict) or not _json_safe(arguments):
        return None
    if row.get("status") not in _VALID_STATUSES:
        return None
    if not isinstance(row.get("approval_recorded", False), bool):
        return None
    return step_id


def _valid_record(record: Any) -> bool:
    """Validate the checkpoint structure before it is offered for resume."""
    if not isinstance(record, dict):
        return False
    steps = record.get("steps")
    if not isinstance(steps, list) or not steps:
        return False
    index = record.get("current_step_index")
    saved = record.get("saved")
    if not isinstance(record.get("goal"), str):
        return False
    if isinstance(index, bool) or not isinstance(index, int):
        return False
    if not _number(saved) or saved > time.time() + 300:
        return False
    if not 0 <= index <= len(steps):
        return False
    workspace = record.get("workspace")
    if workspace is not None and not isinstance(workspace, str):
        return False
    step_ids = set()
    for row in steps:
        step_id = _valid_step(row)
        if step_id is None or step_id in step_ids:
            return False
        step_ids.add(step_id)
    return True


def keep(plan: dict) -> dict:
    """Reduce a `Plan.to_dict()` to the fields a resume can use."""
    steps = []
    for row in plan.get("steps") or []:
        kept = {name: row.get(name) for name in STEP_FIELDS}
        kept["approval_recorded"] = bool(row.get("approval_recorded"))
        steps.append(kept)
    workspace = plan.get("workspace")
    return {
        "goal": str(plan.get("goal") or "")[:500],
        "workspace": str(workspace) if workspace is not None else None,
        "steps": steps,
        "current_step_index": plan.get("current_step_index", 0),
        "saved": time.time(),
    }


def save(plan: dict, folder: Optional[Path] = None) -> bool:
    """Write the plan. False when it was not written, and why is not a failure.

    A plan that touches a secret is not saved, and any older copy of it is removed.
    The run continues. The cost is one lost resume; the alternative is a password in
    a plain file beside the app.
    """
    if any(_secret_in(row.get("tool_args")) or _secret_in(row.get("resolved_args"))
           for row in plan.get("steps") or []):
        _invalidate(folder)
        return False

    path = _path(folder)
    temp = path.with_suffix(".tmp")
    try:
        record = keep(plan)
        if not _valid_record(record):
            _invalidate(folder)
            return False
        text = json.dumps(record, ensure_ascii=False, allow_nan=False)
        if len(text.encode("utf-8")) > MAX_BYTES:
            _invalidate(folder)
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        temp.write_text(text, encoding="utf-8")
        temp.replace(path)          # a half-written plan must never be readable
        marker = _invalid_path(folder)
        try:
            marker.unlink(missing_ok=True)
        except (OSError, ValueError):
            _invalidate(folder)
            return False
        return True
    except (OSError, TypeError, ValueError):
        # An older checkpoint may describe an action that already ran. If the new
        # state could not be saved, do not leave that stale record resumable.
        _invalidate(folder)
        return False
    finally:
        try:
            temp.unlink(missing_ok=True)
        except (OSError, ValueError) as error:
            logger.warning("could not remove checkpoint temp file: %s", error)


def load(folder: Optional[Path] = None) -> Optional[dict]:
    """The saved plan, or None. A damaged or invalidated file is not resumable."""
    try:
        if _invalid_path(folder).exists():
            return None
        raw = _path(folder).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        record = json.loads(raw)
    except ValueError:
        return None
    if not _valid_record(record):
        return None
    return record


def clear(folder: Optional[Path] = None) -> bool:
    """Remove the active checkpoint and any unsafe sidecar."""
    removed = True
    for target in (_path(folder), _invalid_path(folder)):
        try:
            target.unlink(missing_ok=True)
        except (OSError, ValueError):
            removed = False
    return removed


def pending(folder: Optional[Path] = None, now: Optional[float] = None) -> Optional[dict]:
    """The saved plan with its age in hours, or None."""
    record = load(folder)
    if record is None:
        return None
    saved = float(record.get("saved") or 0.0)
    age = max(0.0, (now if now is not None else time.time()) - saved)
    record["age_seconds"] = age
    record["stale"] = age > MAX_AGE
    return record


def describe(record: dict) -> str:
    """`step 3 of 5 — "Tidy Downloads"`, for a notice and for a log."""
    total = len(record.get("steps") or [])
    index = min(int(record.get("current_step_index") or 0), total)
    goal = str(record.get("goal") or "").strip().strip("\"'") or "a plan with no name"
    confirmation = ""
    steps = record.get("steps") or []
    if index < total and steps[index].get("approval_recorded"):
        confirmation = " (confirmed earlier; will ask again)"
    return f'step {index + 1} of {total} — "{goal[:60]}"{confirmation}'


def startup_notice(folder: Optional[Path] = None, now: Optional[float] = None) -> str:
    """One line for the activity log when a plan is still on disk, or an empty string.

    Two sentences, never a question. The owner is starting their assistant. The offer
    to continue is the sentence they choose next, and it is a sentence the assistant
    can already answer: `resume_checkpoint` reads this same file.
    """
    record = pending(folder, now)
    if record is None:
        return ""
    if record["stale"]:
        days = max(1, int(record["age_seconds"] // 86400))
        return (f"SYS: Saved plan ({days}d old), {describe(record)}. "
                "Not resumed automatically. Say \"resume the last plan\" or "
                "\"discard the saved plan\"; writes need fresh approval.")
    return (f"SYS: Saved plan, {describe(record)}. Say \"resume the last plan\" or "
            "\"discard the saved plan\"; writes need fresh approval.")
