"""The long-term memory: what the user has asked Ultron to remember.

`memory/long_term.json` holds six categories of facts (identity, preferences, projects,
relationships, wishes, notes) and the last session summary. This module is about not losing
or corrupting it. Writers share one lock and replace the file in one step (`core/atomic_file.py`)
instead of truncating it; a file that cannot be parsed is set aside as
`long_term.json.broken-<epoch>` and the user is told; a file that cannot be read right now is
never written over; and a save that did not happen raises `MemoryWriteError` or says so in
words, so nothing reports "remembered" for a write that failed.
Tests: `tests/test_memory_safety.py`, `tests/test_memory_changes.py`, `tests/test_edge_cases.py`.
"""

import json
import logging
import os
import re
import tempfile
import time
from datetime import datetime
from threading import Lock, RLock
from pathlib import Path
import sys

from core import failures
from core.atomic_file import replace_with_retry


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR         = get_base_dir()
MEMORY_PATH      = BASE_DIR / "memory" / "long_term.json"
# What changed, and what it was before. Kept apart from the store on purpose: a
# history inside long_term.json grows every entry and would push the real facts out
# through the size guard. This file is bounded to the last CHANGES_MAX writes.
CHANGES_PATH     = BASE_DIR / "state" / "memory_changes.json"
CHANGES_MAX      = 50
_lock            = Lock()
# One read-modify-write, indivisible.
#
# `update_memory` reads the store, merges, writes. `load_memory` and `save_memory`
# each take _lock around their own half, which does not make the WHOLE operation
# atomic: two writers both read, both merge their own key, both write, and the
# second overwrites the first. Measured: six threads, thirty writes each, 53 of
# 180 remembered facts survived — silently, no error, nothing said. Remembering
# something the user asked you to remember and then not remembering it is the
# failure this file exists to avoid.
_write_lock       = RLock()
MAX_VALUE_LENGTH = 380

# ── Why there are two very different numbers here ────────────────────────────
#
# There used to be one: MEMORY_MAX_CHARS = 2200, applied to the whole store. It
# was a *storage* limit, and it existed only because the entire memory was
# pasted into the system prompt on every connect — so growing the memory grew
# every single request. When it filled, _trim_to_limit() deleted the oldest
# entries and printed one line to a console nobody reads. A memory described as
# "deeply remembers projects, preferences and personal context" was in practice
# two pages long, and quietly forgot your sister's name after a few weeks.
#
# Storage and prompt budget are now separate concerns:
#
#   MEMORY_MAX_CHARS  — a runaway guard, not a feature limit. Nothing normal
#                       reaches it; a bug writing in a loop does.
#   PROMPT_CORE_CHARS — what actually rides in the system prompt every session.
#                       Smaller than the old whole-memory dump, so sessions
#                       start *faster* than before, not slower.
#
# Everything above the core stays on disk and is fetched on demand by the
# recall_memory tool — see search_memory() and format_memory_for_prompt().
MEMORY_MAX_CHARS  = 200_000
PROMPT_CORE_CHARS = 900
PROMPT_INDEX_CHARS = 420
# Most entries any one category may contribute to the core block, so a person
# with forty stored preferences still gets their sister into the prompt.
PROMPT_MAX_PER_CATEGORY = 6

def _empty_memory() -> dict:
    return {
        "identity":      {},
        "preferences":   {},
        "projects":      {},
        "relationships": {},
        "wishes":        {},
        "notes":         {},
    }

class MemoryWriteError(OSError):
    """The memory store could not be written. Nothing was saved, and the file on disk is
    exactly what it was: callers must not tell the user "remembered"."""


class _Unverified(dict):
    """An empty memory returned because the file EXISTS and could not be read just now.

    It is not what the user has stored, so it must never be saved over it: the old code
    turned any failed read (a file another program had open, a permissions blip) into
    "the memory is empty", merged one new fact into that, and wrote it back, replacing
    everything the user had ever asked to be remembered.
    """


def _quarantine_damaged(error) -> bool:
    """Move a store that is not valid JSON aside, so the next save cannot destroy it.

    Returns True when the damaged file is out of the way (or there was nothing in it to
    keep). Damage is what a crash in the middle of a write leaves, and what a text editor
    that adds a byte-order mark used to look like to `json.loads`; both used to end the
    same way: an empty memory, then the next save replaced the file with it.
    """
    try:
        size = MEMORY_PATH.stat().st_size
    except OSError as stat_error:
        failures.note("memory.quarantine", stat_error, detail=str(MEMORY_PATH))
        size = None
    if size == 0:
        return True                          # an empty file holds nothing to keep
    stamp = int(time.time())
    target = MEMORY_PATH.with_name(f"{MEMORY_PATH.name}.broken-{stamp}")
    suffix = 0
    while target.exists():                   # two in one second must not overwrite each other
        suffix += 1
        target = MEMORY_PATH.with_name(f"{MEMORY_PATH.name}.broken-{stamp}-{suffix}")
    try:
        os.replace(MEMORY_PATH, target)
    except OSError as move_error:
        failures.note("memory.quarantine", move_error, detail=str(MEMORY_PATH))
        return False
    failures.note("memory.load", error,
                  detail=f"{MEMORY_PATH.name} could not be read; kept as {target.name}")
    if _trim_notifier:
        try:
            _trim_notifier(f"SYS: My saved memory could not be read ({error}). The file is "
                           f"kept as {target.name} in the same folder, and I am starting "
                           "with an empty memory.")
        except Exception as notify_error:
            failures.note("memory.notify", notify_error)
    return True


def load_memory() -> dict:
    if not MEMORY_PATH.exists():
        return _empty_memory()
    with _lock:
        try:
            # utf-8-sig: a store saved by Notepad starts with a byte-order mark, which
            # plain utf-8 hands to json.loads as an illegal first character.
            raw = MEMORY_PATH.read_text(encoding="utf-8-sig")
        except OSError as error:
            failures.note("memory.load", error, detail=f"{MEMORY_PATH}: not readable now")
            return _Unverified(_empty_memory())
        except ValueError as error:           # not text at all
            return _empty_memory() if _quarantine_damaged(error) else _Unverified(_empty_memory())
        if not raw.strip():
            return _empty_memory()
        try:
            data = json.loads(raw)
        except ValueError as error:
            return _empty_memory() if _quarantine_damaged(error) else _Unverified(_empty_memory())
        if not isinstance(data, dict):
            error = TypeError(f"the top level is a {type(data).__name__}, not an object")
            return _empty_memory() if _quarantine_damaged(error) else _Unverified(_empty_memory())
        for key in _empty_memory():
            if key not in data:
                data[key] = {}
        return data

def _all_entries(memory: dict) -> list[tuple]:
    entries = []
    for cat, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            if isinstance(entry, dict) and "value" in entry:
                entries.append((cat, key, entry))
    return entries


# Set by main.py so a trim can reach the activity log. Deleting something a
# person told you and mentioning it only on stdout is how a memory loses trust.
_trim_notifier = None


def set_trim_notifier(fn) -> None:
    """Register a callable(str) that surfaces trims to the user."""
    global _trim_notifier
    _trim_notifier = fn


def _trim_to_limit(memory: dict) -> dict:
    """Reduce stored memory while retaining the most useful facts."""
    if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
        return memory
    entries = _all_entries(memory)
    entries.sort(key=lambda t: t[2].get("updated_at") or
                 t[2].get("updated", "0000-00-00"))
    dropped = []
    for cat, key, _ in entries:
        if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
            break
        del memory[cat][key]
        dropped.append(f"{cat}/{key}")
        print(f"[Memory] 🗑️  Trimmed {cat}/{key}")
    if dropped and _trim_notifier:
        try:
            _trim_notifier(
                f"SYS: Memory full — forgot {len(dropped)} oldest entries "
                f"({', '.join(dropped[:3])}{'…' if len(dropped) > 3 else ''})"
            )
        except Exception:
            pass
    return memory

def _write_store(memory: dict) -> None:
    """Replace the store in one step, or leave it exactly as it was and raise.

    `Path.write_text` truncates the file and then writes it: a crash, a full disk or a
    kill in between leaves a half file, and a half file used to become an empty memory.
    The text goes to a temporary file in the same folder, is flushed to disk, and is moved
    over the store. Raises MemoryWriteError; never returns having written nothing.
    """
    temp_path = None
    try:
        text = json.dumps(memory, indent=2, ensure_ascii=False)
        MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{MEMORY_PATH.name}.", suffix=".tmp", dir=MEMORY_PATH.parent)
        temp_path = Path(temp_name)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        replace_with_retry(temp_path, MEMORY_PATH)
        temp_path = None
    except (OSError, TypeError, ValueError) as error:
        failures.note("memory.save", error, detail=str(MEMORY_PATH))
        raise MemoryWriteError(f"the memory file could not be written: {error}") from error
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError as cleanup_error:
                failures.note("memory.save.cleanup", cleanup_error, detail=str(temp_path))


def _refuse_unverified(memory) -> None:
    if isinstance(memory, _Unverified):
        error = MemoryWriteError(
            "the memory file exists but could not be read, so saving now would replace "
            "what is in it with an almost empty one; nothing was written")
        failures.note("memory.save", error, detail=str(MEMORY_PATH))
        raise error


def save_memory(memory: dict) -> None:
    """Store `memory`. Raises MemoryWriteError when it could not be written."""
    if not isinstance(memory, dict):
        return
    _refuse_unverified(memory)
    memory = _trim_to_limit(memory)
    with _lock:
        _write_store(memory)


def set_top_level(key: str, value) -> None:
    """Replace one top-level entry of the store (e.g. "monitors"), under the writer lock.

    `actions/background_monitor.py` did its own load, assignment and `write_text`, taking
    only `_lock`, so it could interleave with `update_memory` and discard its write.
    """
    with _write_lock:
        memory = load_memory()
        memory[key] = value
        save_memory(memory)


def _truncate_value(val: str) -> str:
    if isinstance(val, str) and len(val) > MAX_VALUE_LENGTH:
        return val[:MAX_VALUE_LENGTH].rstrip() + "…"
    return val


def _recursive_update(target: dict, updates: dict, changes: list | None = None,
                      trail: tuple = ()) -> bool:
    """Merge nested memory facts and collect bounded change records."""
    changed = False
    for key, value in updates.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, dict) and "value" not in value:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
                changed = True
            if _recursive_update(target[key], value, changes, trail + (key,)):
                changed = True
        else:
            existing_cat = target.get(key)
            if isinstance(existing_cat, dict) and "value" not in existing_cat:
                # A string where a category of entries belongs. Writing it would
                # turn {"notes": {"dentist": {...}}} into {"notes": "not a dict"}
                # and every entry in the category would be gone — measured, this
                # is exactly what a malformed update did to a live store.
                print(f"[Memory] ⚠️ Refusing to replace the '{key}' group with a "
                      f"single value — entries would be lost.")
                continue
            new_val  = _truncate_value(str(value["value"] if isinstance(value, dict) else value))
            now = datetime.now()
            entry = {"value": new_val, "updated": now.strftime("%Y-%m-%d"),
                     "updated_at": now.isoformat(timespec="seconds")}
            existing = target.get(key, {})
            if not isinstance(existing, dict) or existing.get("value") != new_val:
                if changes is not None:
                    # What it said before, so "you told me the opposite last week" is a
                    # sentence this assistant can answer instead of deny.
                    changes.append({
                        "at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "path": "/".join(trail + (key,)),
                        "from": _entry_value(existing),
                        "to": new_val,
                    })
                target[key] = entry
                changed = True
    return changed


def update_memory(memory_update: dict) -> dict:
    """Atomically merge a memory update and record its history."""
    if not isinstance(memory_update, dict) or not memory_update:
        return load_memory()
    with _write_lock:
        memory = load_memory()
        changes: list = []
        if _recursive_update(memory, memory_update, changes):
            save_memory(memory)           # raises MemoryWriteError if it did not happen
            # The fact is already written. History failure cannot lose it.
            _record_changes(changes)
            print(f"[Memory] 💾 Saved: {list(memory_update.keys())}")
        return memory


def _record_changes(rows: list) -> None:
    """Newest first, bounded. A history that grows without a limit is a disk leak."""
    if not rows:
        return
    known = changes(limit=CHANGES_MAX)
    kept = (list(reversed(rows)) + known)[:CHANGES_MAX]
    temp_path = None
    try:
        CHANGES_PATH.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{CHANGES_PATH.name}.", suffix=".tmp", dir=CHANGES_PATH.parent
        )
        temp_path = Path(temp_name)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(kept, indent=2, ensure_ascii=False))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, CHANGES_PATH)
    except OSError as error:
        logging.getLogger("memory").warning("could not record memory change: %s", error)
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError as error:
                logging.getLogger("memory").warning(
                    "could not remove temporary memory history: %s", error
                )


def changes(limit: int = 10) -> list:
    """The last `limit` changes, newest first. Never raises: this is a record, not a guard."""
    try:
        rows = json.loads(CHANGES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(rows, list):
        return []
    clean = [row for row in rows if isinstance(row, dict)]
    return clean[:max(1, int(limit))]

def _entry_value(entry) -> str:
    """Accept both the {'value': ..., 'updated': ...} shape and a bare string,
    because early versions of the store wrote plain strings."""
    if isinstance(entry, dict):
        return str(entry.get("value", "") or "").strip()
    return str(entry or "").strip()


def _pretty(key: str) -> str:
    return key.replace("_", " ").strip()


# Identity is always in the prompt; these categories compete for the remaining
# budget by recency.
_CATEGORY_LABELS = {
    "preferences":   "Preferences",
    "projects":      "Active projects / goals",
    "relationships": "People in their life",
    "wishes":        "Wishes / plans",
    "notes":         "Notes",
}

_IDENTITY_FIELDS = ["name", "age", "birthday", "city", "job",
                    "language", "school", "nationality"]


def format_memory_for_prompt(memory: dict | None) -> str:
    """Build the memory block that goes into the system prompt.

    This used to dump everything. It now sends three things:

      1. IDENTITY  - always, in full. It is small, and it is wrong for the
         assistant to have to look up your name.
      2. RECENT    - the most recently updated entries from every other
         category, up to PROMPT_CORE_CHARS. Recency is the cheapest useful
         relevance signal available without embeddings.
      3. AN INDEX  - the *keys* of everything else, values omitted.

    Point 3 is what makes recall work at all. A model cannot decide to look
    something up if it does not know the thing exists: with only points 1 and 2,
    "who is Ayse?" would get "I don't know" while ayse_sister sat on disk
    unread. The index costs a few hundred characters and turns recall from a
    gamble into a lookup.

    Net effect on latency: this block is SMALLER than the old full dump, so
    every session connects with fewer tokens. Occasionally the model spends one
    extra round trip on recall_memory - covered by the acknowledgment it
    already speaks before any slow step."""
    if not memory:
        return ""

    core_lines: list[str] = []

    # 1. Identity - always, in full
    identity = memory.get("identity", {}) or {}
    for field in _IDENTITY_FIELDS:
        val = _entry_value(identity.get(field))
        if not val:
            continue
        if field == "language":
            # Labelled as an observation, not a setting. A bare "Language:
            # English" line written months ago reads like a standing order and
            # was one of the reasons a Turkish question came back in English.
            core_lines.append(
                f"Has spoken to you in: {val} (an observation about the past — "
                f"always answer in the language of their CURRENT message)")
        else:
            core_lines.append(f"{field.title()}: {val}")
    for key, entry in identity.items():
        if key in _IDENTITY_FIELDS:
            continue
        val = _entry_value(entry)
        if val:
            core_lines.append(f"{_pretty(key).title()}: {val}")

    # 2. Everything else, most recently updated first
    rest: list[tuple[str, str, str, str]] = []   # (updated, cat, key, value)
    for cat in _CATEGORY_LABELS:
        for key, entry in (memory.get(cat, {}) or {}).items():
            val = _entry_value(entry)
            if not val:
                continue
            updated = ((entry.get("updated_at") or entry.get("updated", ""))
                       if isinstance(entry, dict) else "") or "0000-00-00"
            rest.append((updated, cat, key, val))
    rest.sort(key=lambda t: t[0], reverse=True)

    used    = sum(len(line) + 1 for line in core_lines)
    shown: dict[str, list[str]] = {}
    overflow: dict[str, list[str]] = {}

    # Recency decides order, but no single category may take the whole budget.
    # Without the cap, someone with forty stored preferences gets a prompt that
    # is forty preferences and not one person's name — the categories that
    # matter most in conversation are also the ones that change least often, so
    # pure recency systematically buries them.
    per_cat_used: dict[str, int] = {}
    for _updated, cat, key, val in rest:
        line = f"  - {_pretty(key).title()}: {val}"
        if (per_cat_used.get(cat, 0) < PROMPT_MAX_PER_CATEGORY
                and used + len(line) + 1 <= PROMPT_CORE_CHARS):
            shown.setdefault(cat, []).append(line)
            per_cat_used[cat] = per_cat_used.get(cat, 0) + 1
            used += len(line) + 1
        else:
            overflow.setdefault(cat, []).append(_pretty(key))

    # The index is a table of contents, so it is interleaved across categories
    # rather than continuing in recency order. Sorted by recency it would list
    # twenty-four preferences before the first relationship, and the one entry
    # the index exists for — the old fact the model has no other way to know
    # about — would fall off the end.
    indexed: list[str] = []
    if overflow:
        cats  = [c for c in _CATEGORY_LABELS if overflow.get(c)]
        cursor = {c: 0 for c in cats}
        while cats:
            for cat in list(cats):
                i = cursor[cat]
                if i >= len(overflow[cat]):
                    cats.remove(cat)
                    continue
                indexed.append(overflow[cat][i])
                cursor[cat] = i + 1

    for cat, label in _CATEGORY_LABELS.items():
        if shown.get(cat):
            core_lines.append("")
            core_lines.append(f"{label}:")
            core_lines.extend(shown[cat])

    if not core_lines and not indexed:
        return ""

    out = [
        "[WHAT YOU KNOW ABOUT THIS PERSON — use naturally, never recite like a list]",
        *core_lines,
    ]

    # 3. The index of what is on disk but not in this prompt
    if indexed:
        budget, names = PROMPT_INDEX_CHARS, []
        for n in indexed:
            if budget - len(n) - 2 < 0:
                break
            names.append(n)
            budget -= len(n) + 2
        if names:
            out.append("")
            out.append(
                "[ALSO REMEMBERED — values not shown here. Call recall_memory "
                "with a keyword to read any of these before saying you do not know]"
            )
            out.append(", ".join(names)
                       + (f" (+{len(indexed) - len(names)} more)"
                          if len(indexed) > len(names) else ""))

    return "\n".join(out) + "\n"


# ── Recall ────────────────────────────────────────────────────────────────────

def _score(query_words: list[str], cat: str, key: str, value: str) -> int:
    """Cheap lexical relevance. No embeddings, no network, no model call - this
    runs in well under a millisecond, which is the entire point: recall must
    cost one model round trip, never two."""
    hay_key = _pretty(key).lower()
    hay_val = value.lower()
    score   = 0
    for w in query_words:
        if not w:
            continue
        if w == hay_key:
            score += 10
        elif w in hay_key:
            score += 6
        if w in hay_val:
            score += 3
        if w in cat:
            score += 1
    return score


def _search_sessions(sessions: list, words: list[str]) -> list[tuple[int, str, str, str, str]]:
    """Rank saved session summaries for recall, including temporal queries."""
    results: list[tuple[int, str, str, str, str]] = []
    if not isinstance(sessions, list):
        return results
    temporal_cues = {"yesterday", "last", "session", "previous", "history", "earlier", "past", "day"}
    is_temporal = any(word in temporal_cues for word in words)
    for index, session in enumerate(reversed(sessions)):
        if not isinstance(session, dict):
            continue
        date = str(session.get("date", ""))
        summary = str(session.get("summary", ""))
        if not summary:
            continue
        score = 3 if is_temporal and index < 3 else 0
        if words:
            for word in words:
                if word in date.lower() or word in summary.lower():
                    score += 2
        else:
            score = 1
        if score > 0:
            results.append((score, "session", date, summary, ""))
    return results


def search_memory(query: str, limit: int = 8) -> str:
    """Find stored facts matching `query`. Backs the recall_memory tool.

    An empty query is treated as "show me everything you know", capped - the
    model asks that when the user says "what do you remember about me?"."""
    memory = load_memory()
    words  = [w for w in re.split(r"[^\w]+", (query or "").lower()) if len(w) > 1]

    rows: list[tuple[int, str, str, str, str]] = []
    for cat, items in memory.items():
        if not isinstance(items, dict):
            continue                     # skip 'sessions', which is a list
        for key, entry in items.items():
            val = _entry_value(entry)
            if not val:
                continue
            s = _score(words, cat, key, val) if words else 1
            if s > 0:
                updated = ((entry.get("updated_at") or entry.get("updated", ""))
                           if isinstance(entry, dict) else "")
                rows.append((s, cat, key, val, updated))

    rows.extend(_search_sessions(memory.get("sessions", []), words))

    if not rows:
        return (f"Nothing stored about '{query}'." if query
                else "I have not stored anything about this person yet.")

    rows.sort(key=lambda r: (-r[0], r[2]))
    lines = [f"{cat}/{_pretty(key)}: {val}"
             + (f" (last updated {updated})" if updated else "")
             for _s, cat, key, val, updated in rows[:max(1, limit)]]
    head  = (f"Stored facts matching '{query}':" if query
             else "Everything currently stored:")
    more  = (f"\n(+{len(rows) - len(lines)} more — search with a narrower keyword)"
             if len(rows) > len(lines) else "")
    return head + "\n" + "\n".join(lines) + more


def all_entries_for_ui() -> list[dict]:
    """Flat list for the memory panel: what JARVIS knows, and when it learned it.
    Sorted newest first so the panel opens on what changed most recently."""
    memory = load_memory()
    rows = []
    for cat, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            val = _entry_value(entry)
            if not val:
                continue
            rows.append({
                "category": cat,
                "key":      key,
                "value":    val,
                "updated":  ((entry.get("updated_at") or entry.get("updated", ""))
                             if isinstance(entry, dict) else ""),
            })
    rows.sort(key=lambda r: (r["updated"] or "0000-00-00"), reverse=True)
    return rows

def remember(key: str, value: str, category: str = "notes") -> str:
    valid = {"identity", "preferences", "projects", "relationships", "wishes", "notes"}
    if category not in valid:
        category = "notes"
    try:
        update_memory({category: {key: {"value": value}}})
    except MemoryWriteError as error:
        return f"Nothing was saved: {error}"
    return f"Remembered: {category}/{key} = {value}"


def forget(key: str, category: str = "notes") -> str:
    with _write_lock:
        memory = load_memory()
        cat    = memory.get(category, {})
        if key in cat:
            del cat[key]
            memory[category] = cat
            try:
                save_memory(memory)
            except MemoryWriteError as error:
                return f"Nothing was changed: {error}"
            return f"Forgotten: {category}/{key}"
        return f"Not found: {category}/{key}"


forget_memory = forget


# ── Session memory ─────────────────────────────────────────────────────────────

_SESSION_MAX = 3   # safety cap — in practice 0-1 entries after pop


def save_session_summary(summary: str, language: str = "") -> None:
    """Append a 1-2 sentence session summary to long_term.json['sessions']."""
    summary = (summary or "").strip()
    if not summary:
        return
    with _write_lock:
        memory   = load_memory()
        sessions = memory.get("sessions", [])
        if not isinstance(sessions, list):
            sessions = []
        entry: dict = {
            "date":    datetime.now().strftime("%Y-%m-%d"),
            "summary": summary[:280],
        }
        if language:
            entry["language"] = language
        sessions.append(entry)
        memory["sessions"] = sessions[-_SESSION_MAX:]
        try:
            with _lock:
                _refuse_unverified(memory)
                _write_store(memory)
        except MemoryWriteError as error:
            print(f"[Memory] Session summary not saved: {error}")
            return
    print(f"[Memory] 📝 Session saved ({entry['date']}): {summary[:60]}…")


def pop_last_session() -> dict | None:
    """
    Return AND remove the most recent session entry.
    Calling this consumes the entry so it is never repeated in future briefings.
    """
    with _write_lock:
        with _lock:
            if not MEMORY_PATH.exists():
                return None
            try:
                memory   = json.loads(MEMORY_PATH.read_text(encoding="utf-8-sig"))
                sessions = memory.get("sessions", [])
                if not isinstance(sessions, list) or not sessions:
                    return None
                entry = sessions.pop()          # remove the last entry
                memory["sessions"] = sessions
                _write_store(memory)
                return entry
            except Exception as e:
                print(f"[Memory] ⚠️ pop_last_session error: {e}")
                return None