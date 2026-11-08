"""Where a failure goes when nothing can be done about it.

Ultron runs on top of a desktop it does not own. A window that will not take focus,
a sound card that will not open, an accessibility API that answers `E_FAIL`, a
plugin that will not import — none of these can be repaired from here, and each one
was previously handled by catching the error and throwing it away:

    try:
        bring_to_front(window)
    except Exception:
        pass

That is how a real failure becomes a silent one. The assistant then does the wrong
thing with no trace, and the only symptom is the owner saying "it did not work".

This module is the one-line replacement. It records the failure, keeps the last few
hundred in memory, and never raises — because a note-taker that can fail is worse
than no note-taker. Nothing here decides anything: the caller still carries on
exactly as before, but the trail now exists and can be read back with `recent()`.

Reading it:

    >>> from core import failures
    >>> for line in failures.recent():
    ...     print(line["where"], line["error"])

The trail is bounded on purpose. This is a diagnostic, not a log file, and an
assistant that runs for a week must not grow a list in memory that nobody prunes.
"""

from __future__ import annotations

import logging
import threading
import traceback

# Long enough to explain a session, short enough that nobody notices the memory.
KEEP = 200

_lock = threading.Lock()
_notes: list[dict] = []
_listeners: set = set()
_log = logging.getLogger("ultron.failures")


def subscribe(listener):
    """Receive future failure notes; callbacks run outside the journal lock.

    Listener errors are isolated in ``note`` so instrumentation cannot break the
    feature that was already handling the original failure.
    """
    if not callable(listener):
        raise TypeError("listener must be callable")
    with _lock:
        _listeners.add(listener)

    def unsubscribe():
        with _lock:
            _listeners.discard(listener)

    return unsubscribe


def note(where: str, error: BaseException | str, *, detail: str = "") -> None:
    """Record a failure that the caller has decided not to raise.

    `where` is a short, greppable name — `"appidentity.focus"`, not a sentence.
    It is what the owner will read in a trail, so it says which part of the
    assistant gave up, not why the programmer thought it was acceptable.

    Never raises. If the note cannot be built (a hostile `__str__`, a closed
    interpreter), it is dropped: losing a diagnostic is survivable, and losing the
    assistant to its own diagnostics is not.
    """
    try:
        if isinstance(error, BaseException):
            kind = type(error).__name__
            text = str(error)
            trace = "".join(traceback.format_exception_only(type(error), error)).strip()
            frames = traceback.extract_tb(error.__traceback__, limit=4)
            at = f"{frames[-1].filename.rsplit('/', 1)[-1]}:{frames[-1].lineno}" \
                if frames else ""
        else:
            kind, text, trace, at = "Message", str(error), str(error), ""
        entry = {"where": where, "kind": kind, "error": text, "trace": trace,
                 "at": at, "detail": detail}
        with _lock:
            _notes.append(entry)
            if len(_notes) > KEEP:
                del _notes[: len(_notes) - KEEP]
            listeners = tuple(_listeners)
        _log.debug("%s could not proceed: %s: %s", where, kind, text)
        for listener in listeners:
            try:
                listener(dict(entry))
            except Exception:
                # Notifications are best-effort; failure capture itself must survive.
                continue
    except Exception:
        # Deliberately silent, and deliberately the only such place in the project:
        # this is the note-taker's own fallback, and it has nowhere left to write.
        return


def recent(limit: int = 50) -> list[dict]:
    """The most recent notes, oldest first, so a trail reads in order."""
    with _lock:
        return list(_notes[-limit:])


def summary() -> dict[str, int]:
    """How many notes each part of the assistant produced.

    A part that appears here more than the others is the part that most often
    cannot do its job, which is a better lead than any guess::

        {'appidentity.focus': 12, 'audio_devices.open': 3}
    """
    with _lock:
        counts: dict[str, int] = {}
        for entry in _notes:
            counts[entry["where"]] = counts.get(entry["where"], 0) + 1
        return counts


def clear() -> None:
    """Forget the trail. Tests use this; the app does not need to."""
    with _lock:
        _notes.clear()
