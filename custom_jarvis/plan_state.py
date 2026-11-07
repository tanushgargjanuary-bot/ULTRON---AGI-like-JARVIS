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
import time
from pathlib import Path
from typing import Any, Optional

FOLDER = Path(__file__).resolve().parent.parent / "state"
NAME = "active_plan.json"

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
    "resolved_args",
)

_SECRET_HINTS = ("key", "token", "secret", "password", "passwd", "credential")


def _path(folder: Optional[Path] = None) -> Path:
    return (Path(folder) if folder else FOLDER) / NAME


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


def keep(plan: dict) -> dict:
    """Reduce a `Plan.to_dict()` to the fields a resume can use."""
    steps = []
    for row in plan.get("steps") or []:
        steps.append({name: row.get(name) for name in STEP_FIELDS})
    return {
        "goal": str(plan.get("goal") or "")[:500],
        "steps": steps,
        "current_step_index": int(plan.get("current_step_index") or 0),
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
        clear(folder)
        return False

    record = keep(plan)
    text = json.dumps(record, ensure_ascii=False, default=str)
    if len(text.encode("utf-8")) > MAX_BYTES:
        clear(folder)
        return False

    path = _path(folder)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(text, encoding="utf-8")
        temp.replace(path)          # a half-written plan must never be readable
        return True
    except (OSError, ValueError):
        return False


def load(folder: Optional[Path] = None) -> Optional[dict]:
    """The saved plan, or None. A damaged file is treated as no file."""
    try:
        raw = _path(folder).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        record = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(record, dict) or not record.get("steps"):
        return None
    return record


def clear(folder: Optional[Path] = None) -> bool:
    """Remove the file. True when it is gone afterwards."""
    try:
        _path(folder).unlink()
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


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
    return f'step {index + 1} of {total} — "{goal[:80]}"'


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
        return (f"SYS: A plan from {days} day(s) ago is still on disk — {describe(record)}. "
                "It is not resumed by itself. Say \"resume the last plan\", "
                "or delete state/active_plan.json.")
    return f"SYS: A plan stopped at {describe(record)}. Say \"resume the last plan\" to continue."
