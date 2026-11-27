"""Settings and keys: the one module that reads and writes `config/api_keys.json`.

Every setter goes through a single read-modify-write (`_config_txn`): one lock held from the
read to the replace, a temporary file of its own beside the settings file, and a rename over
it (retried for a moment where Windows says another program has the file open). A file that
exists but cannot be read is never replaced by something built from a failed read, and a file
that does not parse is copied to `api_keys.json.broken-<epoch>` before the next save goes over
it. The caller of a setter is not told whether it worked unless it asks (`save_settings_strict`
raises). Tests: `tests/test_config_safety.py`, `tests/test_edge_cases.py`.
"""

import contextlib
import json
import os
import sys
import tempfile
import threading
import time

from core import failures, identity
from core.atomic_file import replace_with_retry
from pathlib import Path

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR    = get_base_dir()
CONFIG_DIR  = BASE_DIR / "config"
CONFIG_FILE = CONFIG_DIR / "api_keys.json"

def _report(where: str, message: str, error=None, detail: str = "") -> None:
    """Say that a settings operation failed: once on the console, once in the trail.

    The only print in this module. A settings failure used to be a console line that
    a packaged build never shows, or nothing; `failures.note` puts it where the
    Health Center reads it. Never raises.
    """
    print(f"❌ {message}")
    failures.note(where, error if error is not None else message, detail=detail)


def ensure_config_dir() -> bool:
    """Make sure the folder is there. False when it cannot be used.

    Measured: with `config` occupied by a file (or the folder read-only, which is
    what a copy of this program under Program Files gets), mkdir and the write
    raised OSError straight out of whatever Qt slot called a setter. PyQt6 turns
    an unhandled exception in a slot into an abort, so changing a colour in a
    folder the user cannot write to closed the application. A setting that cannot
    be saved is worth a sentence, not a crash.
    """
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        return True
    except OSError as e:
        _report("config_manager.dir", f"Cannot use the config folder {CONFIG_DIR}: {e}",
                e, str(CONFIG_DIR))
        return False

def config_exists() -> bool:
    return CONFIG_FILE.exists()

def save_api_keys(gemini_api_key: str) -> None:
    """Store the Gemini key — the same safe write as every other setter.

    This was the last function with its own open-coded read-modify-write, and so
    the last place still able to lose a damaged file's contents and to leave a
    half-written one behind. `_load_for_write` and `_write_config` are shared.
    """
    with _config_txn() as data:
        data["gemini_api_key"] = str(gemini_api_key or "").strip()

def load_api_keys() -> dict:
    """The config, or {} if it is missing, unreadable, or not an object.

    The "not an object" case mattered: a file containing a JSON list or a bare
    string parsed happily and was returned as-is, so the next `.get()` raised
    AttributeError somewhere far from here — at start-up, in whichever setting
    happened to be read first. Every caller of this function expects a dict.
    """
    if not CONFIG_FILE.exists():
        return {}
    try:
        # Under the lock so an in-process replace cannot overlap the read (on
        # Windows an open file cannot be replaced, and a file being replaced
        # cannot be opened). `utf-8-sig`: Notepad and Windows PowerShell write a
        # byte-order mark, which plain "utf-8" hands to json as a syntax error —
        # a hand-edited file then read as "no keys at all".
        with _CONFIG_LOCK:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
    except Exception as e:
        _report("config_manager.load", f"Failed to load api_keys.json: {e}", e,
                str(CONFIG_FILE))
        return {}
    return data if isinstance(data, dict) else {}

def get_gemini_key() -> str | None:
    return load_api_keys().get("gemini_api_key")

def is_configured() -> bool:
    key = get_gemini_key()
    return bool(key and len(key) > 15)


def get_assistant_name() -> str:
    """Return the configured assistant name, or 'JARVIS' if not set."""
    return load_api_keys().get("assistant_name", identity.NAME) or identity.NAME


def get_user_name() -> str:
    """Return the configured user name for addressing."""
    return load_api_keys().get("user_name", "")


def save_assistant_config(assistant_name: str, user_name: str) -> None:
    """Persist assistant name and user name to config."""
    with _config_txn() as data:
        data["assistant_name"] = assistant_name.strip() or identity.NAME
        data["user_name"] = user_name.strip()


# ── Assistant voice ──────────────────────────────────────────────────────────
# Gemini Live prebuilt voices. Names are proper nouns — identical in every
# language, so this list is safe to show verbatim in any locale.
AVAILABLE_VOICES = ["Charon", "Puck", "Kore", "Fenrir", "Aoede"]
DEFAULT_VOICE    = "Charon"


def get_voice() -> str:
    """Return the configured Live voice, falling back to the default if unset
    or if the stored value is not a voice we recognise."""
    v = load_api_keys().get("voice_name", DEFAULT_VOICE) or DEFAULT_VOICE
    return v if v in AVAILABLE_VOICES else DEFAULT_VOICE


def save_voice(voice_name: str) -> None:
    """Persist the chosen Live voice. Unknown names collapse to the default so a
    bad value can never reach the API and break the session."""
    v = (voice_name or "").strip()
    with _config_txn() as data:
        data["voice_name"] = v if v in AVAILABLE_VOICES else DEFAULT_VOICE


def get_digest_hour() -> str:
    """When the daily digest is due, as "HH:MM". One setting, one reader."""
    value = str(load_api_keys().get("digest_hour", "") or "").strip()
    return value if value else "20:00"


def save_digest_hour(value: str) -> None:
    """Persist the digest hour. A malformed value is stored as the default, so a
    typo cannot stop the digest from ever being due."""
    hour, _, minute = str(value or "").partition(":")
    try:
        clean = f"{max(0, min(23, int(hour))):02d}:{max(0, min(59, int(minute or 0))):02d}"
    except (TypeError, ValueError):
        clean = "20:00"
    with _config_txn() as data:
        data["digest_hour"] = clean


def get_wake_word_enabled() -> bool:
    """Whether local wake-word gating is on (assistant sleeps until 'Hey Jarvis')."""
    return load_api_keys().get("wake_word_enabled", False)


def save_wake_word_enabled(enabled: bool) -> None:
    _save_flag("wake_word_enabled", enabled)


def get_push_to_talk_enabled() -> bool:
    """Hold-a-key-to-speak. When on, the mic is closed unless the chord is held."""
    return load_api_keys().get("push_to_talk_enabled", False)


def save_push_to_talk_enabled(enabled: bool) -> None:
    _save_flag("push_to_talk_enabled", enabled)


HUD_STYLES = ("face", "core")


def get_hud_style() -> str:
    """Which centrepiece the HUD draws: the animated head, or the reactor core.

    Taste, not capability — both render in the same software painter and cost
    about the same. Defaults to the head because that is what MARK LIV shipped
    with; anyone who preferred the older look can switch back in ⚙ and the
    choice survives a restart.
    """
    v = str(load_api_keys().get("hud_style", "face")).strip().lower()
    return v if v in HUD_STYLES else "face"


def save_hud_style(style: str) -> None:
    s = str(style or "").strip().lower()
    _save_flag("hud_style", s if s in HUD_STYLES else "face")


UI_SCALE_MIN = 0.85
UI_SCALE_MAX = 2.50


def get_ui_scale() -> float:
    """How much larger than designed the whole interface is drawn, or 0 for
    'work it out from the screen'.

    Read once, before the window exists — Qt only takes a scale factor at
    start-up, so a change here applies on the next launch. The range is bounded
    in both directions: a hand-edited 4.0 would draw the panel that is supposed
    to let you undo it off the bottom of the screen, and a 0.2 would draw text
    nobody can read. A value outside the range is treated as "work it out",
    which is always usable.
    """
    try:
        v = float(load_api_keys().get("ui_scale", 0) or 0)
    except (TypeError, ValueError):
        return 0.0
    if not (UI_SCALE_MIN <= v <= UI_SCALE_MAX):
        return 0.0
    return v


def save_ui_scale(scale: float) -> None:
    """Store the interface scale, clamped — never a value that traps the user."""
    try:
        v = float(scale or 0)
    except (TypeError, ValueError):
        v = 0.0
    if v <= 0:
        v = 0.0
    else:
        v = round(max(UI_SCALE_MIN, min(UI_SCALE_MAX, v)), 2)
    _save_flag("ui_scale", v)


def reset_ui_scale() -> None:
    """Back to 'work it out from the screen' — the way out of a bad number."""
    _save_flag("ui_scale", 0.0)


def get_window_size() -> tuple[int, int]:
    """The window size last used, or (0, 0) for the designed default.

    Remembered because resizing a window and finding it back at the old size
    every launch is the same complaint as an interface that cannot be resized.
    Anything implausible is ignored rather than restored: a saved 4000x3000 from
    a monitor that is no longer attached would open off-screen.
    """
    try:
        value = load_api_keys().get("window_size") or []
        w, h = int(value[0]), int(value[1])
    except Exception:
        return (0, 0)
    if 320 <= w <= 20000 and 240 <= h <= 20000:
        return (w, h)
    return (0, 0)


def save_window_size(width: int, height: int) -> None:
    """Remember the window size, in the same file as everything else."""
    try:
        w, h = int(width), int(height)
    except (TypeError, ValueError):
        return
    if 320 <= w <= 20000 and 240 <= h <= 20000:
        _save_flag("window_size", [w, h])


# ── Live-session tuning ──────────────────────────────────────────────────────
# Everything here is optional and has a working default, so an untouched
# config behaves exactly like a configured one. Each value is also a way out:
# if a future model dislikes one of these, set it back and nothing else changes.

def get_thinking_enabled() -> bool:
    """Whether the Live model may spend tokens thinking before it answers.

    Off by default. A voice assistant is judged on how fast it starts talking,
    and the reasoning that actually needs deliberation in this app is delegated
    to the planning tools, which run on a separate non-Live model.
    """
    return bool(load_api_keys().get("thinking_enabled", False))


def save_thinking_enabled(enabled: bool) -> None:
    _save_flag("thinking_enabled", enabled)


def get_turn_tuning() -> dict:
    """How eagerly the server decides you have stopped speaking.

    OFF by default, and that default was earned. Cutting turns shorter looks
    like a free speed win and is not: proactive audio has to judge whether an
    utterance was even addressed to the assistant, and a turn clipped early
    gives it less to judge, so it stays quiet — and the reply to your first
    sentence only arrives once your second one has given it enough context.
    That reads as the assistant being a turn behind, which is far worse than
    the fraction of a second the tuning saves.

    Turn it on with "turn_tuning": {"enabled": true} if your own microphone and
    speaking pace suit it. `silence_ms` is the one that is felt: the pause the
    server sits through before accepting your turn is over.
    """
    cfg = load_api_keys().get("turn_tuning")
    cfg = cfg if isinstance(cfg, dict) else {}

    def _int(key, default, lo, hi):
        try:
            return max(lo, min(hi, int(cfg.get(key, default))))
        except (TypeError, ValueError):
            return default

    return {
        "enabled":    bool(cfg.get("enabled", False)),
        "silence_ms": _int("silence_ms", 550, 200, 3000),
        "prefix_ms":  _int("prefix_ms", 150, 0, 1000),
        # "high" = quicker to decide speech has ended.
        "end_sensitivity":   str(cfg.get("end_sensitivity", "high")).lower(),
        "start_sensitivity": str(cfg.get("start_sensitivity", "default")).lower(),
    }


def save_turn_tuning(values: dict) -> None:
    with _config_txn() as data:
        cur = data.get("turn_tuning")
        cur = dict(cur) if isinstance(cur, dict) else {}
        cur.update(values or {})
        data["turn_tuning"] = cur


def get_proactive_audio_enabled() -> bool:
    """Whether the model gets to decide an utterance was not aimed at it and
    stay quiet.

    On by default — it is what stops the assistant answering the room. But it
    is also the first thing to switch off if replies ever seem to arrive a turn
    late: what looks like lag is usually the model having judged your previous
    sentence as not addressed to it, and only changing its mind once the next
    one arrives.
    """
    return bool(load_api_keys().get("proactive_audio", True))


def save_proactive_audio_enabled(enabled: bool) -> None:
    _save_flag("proactive_audio", enabled)


MEDIA_RESOLUTIONS = ("default", "low", "medium", "high")


def get_media_resolution() -> str:
    """How finely the model tokenises the screenshots and camera frames it is
    sent. 'medium' keeps on-screen text readable at a fraction of the tokens a
    full-resolution frame costs; 'low' is cheaper still but starts losing small
    text, which is most of what screen captures are for."""
    v = str(load_api_keys().get("media_resolution", "medium")).strip().lower()
    return v if v in MEDIA_RESOLUTIONS else "medium"


def save_media_resolution(value: str) -> None:
    v = str(value or "").strip().lower()
    _save_flag("media_resolution", v if v in MEDIA_RESOLUTIONS else "medium")


def _save_flag(key: str, value) -> None:
    """Read-modify-write one key without disturbing the rest of the config."""
    with _config_txn() as data:
        data[key] = bool(value) if isinstance(value, bool) else value


def get_philosophy() -> dict:
    """The minds Ultron thinks with, as the owner chose them.

    One key, holding one object, because a blend is one decision rather than six
    settings that could disagree. Anything malformed reads as "not chosen" and the
    caller falls back to the shipped blend, which is always usable.
    """
    value = load_api_keys().get("philosophy")
    return value if isinstance(value, dict) else {}


def save_philosophy(value: dict) -> None:
    """Store the chosen blend through the same atomic write as every other setting."""
    _save_flag("philosophy", value if isinstance(value, dict) else {})


def get_tool_usage() -> dict:
    """Which tools have been called, and how often.

    A count and a date per tool name, nothing else. Kept in the settings file rather
    than a log so it survives a restart, and small enough that deleting it costs the
    owner nothing but the history of the count.
    """
    value = load_api_keys().get("tool_usage")
    return value if isinstance(value, dict) else {}


def save_tool_usage(value: dict) -> None:
    _save_flag("tool_usage", value if isinstance(value, dict) else {})


def get_curriculum_progress() -> dict:
    """Which syllabus topics the owner has marked done, and nothing else."""
    value = load_api_keys().get("curriculum")
    return value if isinstance(value, dict) else {}


def save_curriculum_progress(value: dict) -> None:
    """Store the progress list through the same atomic write as every setting."""
    _save_flag("curriculum", value if isinstance(value, dict) else {})


def get_brief_enabled() -> bool:
    """Return the owner's choice; startup speech is opt-in on a new install."""
    value = load_api_keys().get("morning_brief_enabled", False)
    return value if isinstance(value, bool) else False


def save_brief_enabled(enabled: bool) -> None:
    _save_flag("morning_brief_enabled", enabled)


def get_native_watch_enabled() -> bool:
    """The freeze watch (`docs/FREEZE_WATCH.md`): off on a new install, and only a saved `true` turns it on.

    It starts a second program, so a value that is merely truthy ("yes", 1) is not consent.
    """
    value = load_api_keys().get("native_watch_enabled", False)
    return value if isinstance(value, bool) else False


def save_native_watch_enabled(enabled: bool) -> None:
    _save_flag("native_watch_enabled", enabled)


# ── Audio devices ────────────────────────────────────────────────────────────
# Stored as device NAMES, not sounddevice indices. Indices shift every time a
# USB device is plugged in or removed, so a saved index silently starts pointing
# at a different microphone. The empty string means "system default", which is
# both the factory setting and what an unresolvable saved device falls back to —
# so unplugging a headset degrades to the built-in speakers instead of crashing.

# One lock for every read-modify-write of api_keys.json in this process. The UI
# thread, the session's asyncio thread, the tool worker threads and the dashboard
# all save settings, and `core/tool_usage.py` saves one on EVERY tool call. Without
# a lock two saves read the same file and the later write erased the earlier one;
# worse, both wrote through one shared `api_keys.json.tmp`, so a replace could move
# a half-written file into place (measured: a burst of concurrent tool calls left a
# file with neither the Gemini key nor the providers, and readers saw torn JSON).
# An RLock, so a setter used inside another setter's transaction cannot deadlock.
_CONFIG_LOCK = threading.RLock()


class _UnreadableConfig(dict):
    """An empty settings dict that must never be written back.

    `_load_for_write` returns this when api_keys.json EXISTS but could not be
    read (a sharing violation while another process holds it, a permission
    error, a backup that could not be made). It used to return a plain `{}`, and
    the next setter then replaced the owner's whole file — every key — with the
    one value it had just been given. `_write_config` refuses this type, so every
    existing caller, including ones outside this module, is protected without
    being edited.
    """


def _load_for_write() -> dict:
    """Read api_keys.json for a read-modify-write, without losing what is in it.

    Three failures this exists to stop. The first: a truncated file (power lost
    mid-write, a full disk) used to read as `{}` and then be overwritten by the
    next setting saved — so the assistant forgot every provider key because a
    colour was changed. A file that exists but does not parse is copied to
    `api_keys.json.broken-<epoch>` first, and the new setting is then saved
    over it.
    The second: a file that exists but CANNOT BE READ right now (another process
    has it open) is not an empty file. It is returned as `_UnreadableConfig`,
    which `_write_config` refuses, so nothing is overwritten. The same applies
    when the damaged file cannot be copied aside first.
    The third: `write_text` truncates the destination before writing it, so an
    interruption leaves exactly that half-written file. Writing to a temporary
    file and replacing it is atomic on Windows and on Linux.

    Call it through `_config_txn()`, which also holds the lock until the write.
    """
    if not CONFIG_FILE.exists():
        return {}
    try:
        raw = CONFIG_FILE.read_bytes()
    except OSError as e:
        _report("config_manager.read",
                f"Could not read {CONFIG_FILE}; settings will not be changed: {e}",
                e, str(CONFIG_FILE))
        return _UnreadableConfig()
    try:
        parsed = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, RecursionError):
        parsed = None            # UnicodeDecodeError and JSONDecodeError are ValueErrors
    if isinstance(parsed, dict):
        return parsed
    if raw.strip():
        backup = CONFIG_FILE.with_name(f"{CONFIG_FILE.name}.broken-{int(time.time())}")
        try:
            backup.write_bytes(raw)
        except OSError as e:
            _report("config_manager.backup",
                    f"{CONFIG_FILE} is damaged and could not be copied to {backup.name}; "
                    f"settings will not be changed: {e}", e, str(backup))
            return _UnreadableConfig()
    return {}


_replace_with_retry = replace_with_retry     # one copy of the loop: core/atomic_file.py


def _write_config(data: dict) -> bool:
    """Replace api_keys.json in one step, so a crash cannot leave half a file.

    Returns False when it could not be written. Nobody is obliged to look at the
    return value — every existing caller ignores it — but the ones that claim
    success to the user now can. It never raises for a disk or value problem:
    most callers are Qt slots, and PyQt6 aborts on an exception in a slot.

    The temporary file has its own unique name, so two writers can never share
    one, and it is created owner-only (mode 0600 on POSIX): this file holds API
    keys.
    """
    if isinstance(data, _UnreadableConfig):
        _report("config_manager.write",
                f"Settings were NOT saved: {CONFIG_FILE} exists but could not be "
                "read, and writing now would replace it.", detail=str(CONFIG_FILE))
        return False
    if not ensure_config_dir():
        return False
    try:
        text = json.dumps(data, indent=4)
    except (TypeError, ValueError) as e:
        _report("config_manager.write",
                f"Could not save settings: a value cannot be written as JSON: {e}",
                e, "not JSON-serialisable")
        return False
    with _CONFIG_LOCK:
        tmp = None
        try:
            fd, tmp_name = tempfile.mkstemp(dir=str(CONFIG_DIR), suffix=".tmp",
                                            prefix=f"{CONFIG_FILE.name}.")
            tmp = Path(tmp_name)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            _replace_with_retry(tmp, CONFIG_FILE)
            return True
        except OSError as e:
            _report("config_manager.write", f"Could not save settings to {CONFIG_FILE}: {e}",
                    e, str(CONFIG_FILE))
            if tmp is not None:
                try:
                    tmp.unlink(missing_ok=True)
                except OSError as cleanup_error:
                    failures.note("config_manager.write.cleanup", cleanup_error,
                                  detail=str(tmp))
            return False


@contextlib.contextmanager
def _config_txn(strict: bool = False):
    """Read-modify-write api_keys.json as ONE step.

        with _config_txn() as data:
            data["voice_name"] = "Kore"

    The lock is held from the read to the replace, so two saves from different
    threads both land. Nothing is written when the block raises, and nothing is
    written when the file could not be read (`_UnreadableConfig`). By default a
    failed write is only reported through `_write_config`'s return value, as it
    always was; with `strict=True` it raises OSError, for the one caller that
    must not say "saved" when it was not.
    """
    with _CONFIG_LOCK:
        data = _load_for_write()
        yield data
        if not _write_config(data) and strict:
            raise OSError(f"could not save settings to {CONFIG_FILE}")


def _patch_config(**fields) -> None:
    """Read-modify-write one or more keys in api_keys.json.

    Every setter in this file open-coded this. Collapsing it here means a new
    setting is one line, and there is one place where a corrupt config file is
    handled instead of nine."""
    with _config_txn() as data:
        data.update(fields)


def save_settings_strict(**fields) -> None:
    """Change named settings; raise OSError if they were not written.

    `patch_settings` and the setters report a failed write only through a return value that
    nobody reads, which is right for a colour and wrong for a caller that goes on to say "saved".
    The two UI paths that changed the persona and the identity wrote the whole file themselves
    (`API_FILE.write_text`): over a settings file that could not be read at that moment they wrote
    `{}` plus their few keys, and then announced the change. This keeps every other key, refuses
    to write over a file it could not read, and raises when nothing was written.
    """
    with _config_txn(strict=True) as data:
        data.update(fields)


def patch_settings(**fields) -> dict:
    """Read-modify-write named settings and RETURN the result.

    The public face of _patch_config, because the first-run screen used to write
    its own two-key file over the top of api_keys.json — which silently erased
    the assistant's name, voice, colour, scale and every configured provider
    whenever someone re-opened setup after an authentication error.
    """
    if fields:
        _patch_config(**fields)
    return load_api_keys()


def has_a_brain() -> bool:
    """Whether there is something for the assistant to think with.

    Named to stay clear of `is_configured` above, which only ever meant "there
    is a Gemini key of plausible length". The first-run gate demanded exactly
    that, so a perfectly good local Ollama or a Groq key could not start the
    app: setup insisted on Gemini first even for somebody who had configured
    something else. Two functions with one name and different meanings is how
    a file like this starts lying to whoever reads it next.
    """
    cfg = load_api_keys()
    if not str(cfg.get("os_system", "") or "").strip():
        return False
    if str(cfg.get("gemini_api_key", "") or "").strip():
        return True
    providers = cfg.get("providers")
    creds = providers.get("creds") if isinstance(providers, dict) else None
    if not isinstance(creds, dict):
        return False
    for entry in creds.values():
        if isinstance(entry, dict) and any(str(v).strip() for v in entry.values()):
            return True
    return False


def apply_first_run(*, os_name: str = "", gemini_api_key: str = "",
                    providers: list | None = None, mode: str = "") -> dict:
    """Write the first-run answers without losing anything already set.

    `providers` is a list of {"id": "<provider>@<service>", "values": {...}}.
    An empty key is never written — a blank field means "I did not type one",
    not "delete the one I had". Returns the config as it stands afterwards.
    """
    # One transaction: the old version read with load_api_keys() and wrote the
    # WHOLE config back with _patch_config(**cfg), so any setting saved between
    # the two (a tool call counts itself on a worker thread) was overwritten by
    # the stale copy. `strict`: the caller (MainWindow) reports an exception on
    # screen and otherwise assumes the answers were saved, so a refused or failed
    # write must raise instead of returning a config that is not on disk.
    with _config_txn(strict=True) as cfg:
        _apply_first_run_answers(cfg, os_name=os_name, gemini_api_key=gemini_api_key,
                                 providers=providers, mode=mode)
    return dict(cfg)


def _apply_first_run_answers(cfg: dict, *, os_name: str, gemini_api_key: str,
                             providers: list | None, mode: str) -> None:
    """Merge the first-run answers into `cfg` in place (see `apply_first_run`)."""
    if str(os_name or "").strip():
        cfg["os_system"] = str(os_name).strip()
    key = str(gemini_api_key or "").strip()
    if key:
        cfg["gemini_api_key"] = key

    block = cfg.get("providers")
    block = dict(block) if isinstance(block, dict) else {}
    creds = block.get("creds")
    creds = dict(creds) if isinstance(creds, dict) else {}
    added = 0
    first_pid = ""
    for row in providers or ():
        if not isinstance(row, dict):
            continue
        pid = str(row.get("id", "") or "").strip()
        values = row.get("values")
        if not pid or not isinstance(values, dict):
            continue
        current = creds.get(pid)
        merged = dict(current) if isinstance(current, dict) else {}
        # Blank strings never overwrite a stored credential, and a row with
        # nothing in it at all is not a provider: storing an empty dict
        # leaves a ghost entry the panel lists and the runtime tries.
        merged.update({k: v for k, v in values.items() if str(v).strip()})
        if not merged:
            continue
        creds[pid] = merged
        added += 1
        if not first_pid:
            first_pid = pid
    if added:
        block["creds"] = creds

    chosen = str(mode or "").strip().lower()
    if chosen in (PROVIDER_MODE_GEMINI, PROVIDER_MODE_PIPELINE):
        block["mode"] = chosen
    elif not str(cfg.get("gemini_api_key", "") or "").strip() and added:
        block["mode"] = PROVIDER_MODE_PIPELINE
        pipe = block.get("pipeline")
        pipe = dict(pipe) if isinstance(pipe, dict) else {}
        if not str(pipe.get("llm", "") or "").strip():
            # `providers[0]` was the obvious way to write this and the wrong one:
            # a row that was skipped above (not a dict, or all blank) can be
            # first in the list, and indexing it raised AttributeError inside the
            # save path — after the setup screen had already been dismissed.
            pipe["llm"] = first_pid
        block["pipeline"] = pipe
    if block:
        cfg["providers"] = block


def get_input_device() -> str:
    """Microphone device name, or '' for the system default."""
    return (load_api_keys().get("input_device", "") or "").strip()


def save_input_device(name: str) -> None:
    _patch_config(input_device=(name or "").strip())


def get_output_device() -> str:
    """Speaker device name, or '' for the system default."""
    return (load_api_keys().get("output_device", "") or "").strip()


def save_output_device(name: str) -> None:
    _patch_config(output_device=(name or "").strip())


def get_plugin_enabled(plugin_name: str) -> bool:
    """Plugins are enabled by default the moment they're discovered (opt-out model)."""
    return load_api_keys().get("plugins_enabled", {}).get(plugin_name, True)


# ── Per-plugin settings ("tokens" / connection details) ───────────────────────
# Generic store so a plugin can declare its own config fields (PLUGIN_SETTINGS)
# and the settings UI renders + persists them WITHOUT any core edit — keeping the
# drop-in model intact. Values live under plugin_config[<namespace>][<key>].
# A namespace defaults to the plugin name, but a suite of plugins (e.g. the
# several printer plugins) can share ONE namespace.
def get_plugin_config(namespace: str) -> dict:
    """All stored values for a namespace (empty dict if none set yet)."""
    cfg = load_api_keys().get("plugin_config")
    val = cfg.get(namespace) if isinstance(cfg, dict) else None
    return dict(val) if isinstance(val, dict) else {}


def get_plugin_setting(namespace: str, key: str, default=None):
    """A single value from a namespace, or `default` if unset."""
    return get_plugin_config(namespace).get(key, default)


def save_plugin_config(namespace: str, values: dict) -> None:
    """Merge `values` into a namespace's stored config (read-modify-write, like
    every other helper here). Only the provided keys are touched."""
    with _config_txn() as data:
        pc = data.get("plugin_config")
        if not isinstance(pc, dict):
            pc = {}
        cur = pc.get(namespace)
        if not isinstance(cur, dict):
            cur = {}
        cur.update(values)
        pc[namespace] = cur
        data["plugin_config"] = pc


def save_plugin_enabled(plugin_name: str, enabled: bool) -> None:
    with _config_txn() as data:
        plugins_cfg = data.get("plugins_enabled")
        if not isinstance(plugins_cfg, dict):
            plugins_cfg = {}
        plugins_cfg[plugin_name] = enabled
        data["plugins_enabled"] = plugins_cfg

# ── Providers: local STT/LLM/TTS and non-Gemini APIs ─────────────────────────
# Stored here rather than in a file of their own, for the same reason plugin
# settings are: one config to back up, one already in .gitignore, one place a
# user knows to look.
#
# The important property is what happens when nobody has configured anything.
# `get_provider_mode()` returns "gemini" on a config that has never heard of
# providers, and every caller checks that BEFORE importing the providers
# package — so an ordinary install never executes a line of it. This is the
# whole basis of the claim that the folder costs nothing when unused.
PROVIDER_MODE_GEMINI = "gemini"      # the conversation runs on the Live API
PROVIDER_MODE_PIPELINE = "pipeline"  # STT -> LLM -> TTS, assembled from providers


def _upgrade_ids(block: dict) -> dict:
    """Give every catalog service its own id and its own stored settings.

    One provider serves Ollama, OpenAI, MiniMax and a dozen more, and they used
    to share ONE block of settings under "openai_compat" — so the fallback and
    ② THINKING could not be two different services, picking one overwrote the
    other's address, and an API key typed for MiniMax was sent to OpenAI after
    a switch. Each service is now "<provider>@<entry>", e.g.
    "openai_compat@minimax", with settings of its own.

    An older config is converted as it is read, not by a migration step: the
    shared block moves to the service its "catalog" key names (its key belonged
    to that service and nothing else), and every reference to it follows.
    Writing the providers block back persists it; until then nothing on disk
    changes."""
    creds = block.get("creds")
    if not isinstance(creds, dict):
        return block
    creds = dict(creds)
    moved: dict = {}
    for pid, cfg in list(creds.items()):
        if "@" in pid or not isinstance(cfg, dict):
            continue
        eid = str(cfg.get("catalog") or "").strip()
        if not eid:
            continue
        new = f"{pid}@{eid}"
        creds.setdefault(new, dict(cfg))
        del creds[pid]
        moved[pid] = new
    if not moved:
        return block
    block = dict(block)
    block["creds"] = creds
    pipe = block.get("pipeline")
    if isinstance(pipe, dict):
        block["pipeline"] = {k: moved.get(v, v) for k, v in pipe.items()}
    for key in ("sidecar", "coding"):
        if block.get(key) in moved:
            block[key] = moved[block[key]]
    return block


def _providers_in(cfg: dict) -> dict:
    """The providers block of an already-loaded config, upgraded, as a copy."""
    val = cfg.get("providers")
    return _upgrade_ids(dict(val)) if isinstance(val, dict) else {}


def get_providers() -> dict:
    """The whole providers block, or an empty dict."""
    return _providers_in(load_api_keys())


def get_provider_mode() -> str:
    """Which engine holds the conversation. Defaults to Gemini Live."""
    mode = str(get_providers().get("mode", "") or "").strip().lower()
    return mode if mode in (PROVIDER_MODE_GEMINI, PROVIDER_MODE_PIPELINE) \
        else PROVIDER_MODE_GEMINI


def get_provider_config(provider_id: str) -> dict:
    """Stored settings for one provider — address, model, key, limits."""
    creds = get_providers().get("creds")
    val = creds.get(provider_id) if isinstance(creds, dict) else None
    return dict(val) if isinstance(val, dict) else {}


def get_pipeline() -> dict:
    """Which provider fills each slot of the pipeline engine."""
    val = get_providers().get("pipeline")
    return dict(val) if isinstance(val, dict) else {}


def get_sidecar_provider() -> str:
    """The provider id used for one-shot calls when Gemini cannot answer them,
    or '' for none.

    Separate from the conversation on purpose: these are different jobs with
    different failure modes. Gemini's Live quota and its text quota are separate
    pools, and on the free tier it is the text pool that runs out first — which
    kills document reading, screen reasoning and code generation while the
    conversation carries on. Being able to point only those at another model,
    without changing the voice at all, is the cheapest useful thing this whole
    folder does.
    """
    return str(get_providers().get("sidecar", "") or "").strip()


def _patch_providers(**fields) -> None:
    with _config_txn() as data:
        p = _providers_in(data)
        p.update(fields)
        data["providers"] = p


def save_provider_mode(mode: str) -> None:
    mode = (mode or "").strip().lower()
    _patch_providers(mode=mode if mode in (PROVIDER_MODE_GEMINI,
                                           PROVIDER_MODE_PIPELINE)
                     else PROVIDER_MODE_GEMINI)


def save_provider_config(provider_id: str, values: dict) -> None:
    """Merge settings for one provider. Only the given keys are touched, so the
    panel can save one field without reading and rewriting the rest."""
    with _config_txn() as data:
        p = _providers_in(data)
        creds = p.get("creds")
        if not isinstance(creds, dict):
            creds = {}
        cur = creds.get(provider_id)
        cur = dict(cur) if isinstance(cur, dict) else {}
        cur.update(values or {})
        creds[provider_id] = cur
        p["creds"] = creds
        data["providers"] = p


def save_pipeline(stt: str = None, llm: str = None, tts: str = None) -> None:
    """Set one or more pipeline slots. `None` leaves a slot alone; '' clears it."""
    with _config_txn() as data:
        p = _providers_in(data)
        pipe = p.get("pipeline")
        pipe = dict(pipe) if isinstance(pipe, dict) else {}
        for slot, value in (("stt", stt), ("llm", llm), ("tts", tts)):
            if value is not None:
                pipe[slot] = str(value).strip()
        p["pipeline"] = pipe
        data["providers"] = p


def save_sidecar_provider(provider_id: str) -> None:
    _patch_providers(sidecar=(provider_id or "").strip())


def get_coding_provider() -> str:
    """The service dev_agent writes code with, or '' to use whatever answers
    background requests.

    Its own setting because coding is the one background job where the model
    matters most and the request is longest — somebody may well want a strong
    coding model there and something cheap and fast for reading the screen."""
    return str(get_providers().get("coding", "") or "").strip()


def save_coding_provider(provider_id: str) -> None:
    _patch_providers(coding=(provider_id or "").strip())


def get_local_fallback_consent() -> bool:
    """Has the owner agreed that a model on THIS machine may answer when the
    hosted ones cannot? Only a literal `true` counts, as in main.py: the string
    "true" or the number 1 in a hand-edited file is not consent."""
    return load_api_keys().get("local_fallback_consent") is True


def get_sidecar_first() -> bool:
    """Whether the side-call provider is tried BEFORE Gemini rather than after.

    Off by default: measured in core/gemini.py, the Gemini rungs answer a short
    request in well under a second, and a local model on ordinary hardware does
    not. On means something specific — 'I would rather this stayed on my
    machine, and I accept it being slower' — so it is a choice someone makes,
    never a default they inherit.
    """
    return bool(get_providers().get("sidecar_first", False))


def save_sidecar_first(enabled: bool) -> None:
    _patch_providers(sidecar_first=bool(enabled))


def save_providers(mode: str = None, pipeline: dict = None, creds: dict = None,
                   sidecar: str = None, sidecar_first: bool = None,
                   coding: str = None) -> None:
    """Write the whole providers block in ONE file write.

    The settings panel used to call five setters in a row — one per provider's
    credentials, then the mode, then the pipeline, then the two side-call
    keys — and every one of them was a separate read-modify-write of
    api_keys.json. Five reads and five writes of the same file, in sequence,
    while the panel's own APPLY was already triggering a reconnect that makes
    main.py write to it too. Any interleaving loses whichever key was written
    first, and the one people noticed was the mode: set MY OWN SETUP, save,
    reopen, and it says Gemini again.

    `None` leaves a section alone; `creds` is merged per provider so a panel
    that only edited one does not have to send the others.
    """
    with _config_txn() as data:
        block = data.get("providers")
        block = _upgrade_ids(dict(block)) if isinstance(block, dict) else {}

        if mode is not None:
            m = str(mode).strip().lower()
            block["mode"] = m if m in (PROVIDER_MODE_GEMINI,
                                       PROVIDER_MODE_PIPELINE) else PROVIDER_MODE_GEMINI
        if pipeline is not None:
            current = block.get("pipeline")
            current = dict(current) if isinstance(current, dict) else {}
            current.update({k: str(v or "").strip() for k, v in pipeline.items()})
            block["pipeline"] = current
        if creds is not None:
            store = block.get("creds")
            store = dict(store) if isinstance(store, dict) else {}
            for pid, values in (creds or {}).items():
                one = store.get(pid)
                one = dict(one) if isinstance(one, dict) else {}
                one.update(values or {})
                store[pid] = one
            block["creds"] = store
        if sidecar is not None:
            block["sidecar"] = str(sidecar or "").strip()
        if sidecar_first is not None:
            block["sidecar_first"] = bool(sidecar_first)
        if coding is not None:
            block["coding"] = str(coding or "").strip()

        data["providers"] = block
