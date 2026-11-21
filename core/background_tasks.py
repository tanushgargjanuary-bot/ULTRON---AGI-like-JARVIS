"""core/background_tasks.py — keep a loop that lives as long as the process, and say how it ended.

`asyncio.create_task(x)` as a bare statement has two quiet faults. The event loop keeps only a
weak reference to a task, so one that nothing else refers to can be collected while it waits.
And an exception inside a task nobody awaits surfaces, if at all, as "Task exception was never
retrieved" when the collector gets to it: the loop is simply gone, and nothing says why.

`hold` is the fix and nothing more: the caller still creates the task,

    hold(self._background_tasks, asyncio.create_task(self._digest_loop()), "digest")

so the line that starts a loop still reads as the line that starts it (`scripts/proof_gate.py`
and `tests/test_process_watch.py` look for that text in `main.py`). `hold` keeps the task in a
set the caller owns until it ends, names it, and records a failure in `core.failures`.
"""

from __future__ import annotations

from core import failures

__all__ = ["hold"]


def hold(held: set, task, name: str):
    """Keep `task` referenced in `held` until it ends; note it in `failures` if it died of an error."""
    held.add(task)
    rename = getattr(task, "set_name", None)       # an asyncio.Task has it; a test double may not
    if rename is not None:
        rename(name)

    def finished(done):
        held.discard(done)
        if done.cancelled():
            return
        error = done.exception()
        if error is not None:
            failures.note(f"background task {name} stopped", error)

    task.add_done_callback(finished)
    return task
