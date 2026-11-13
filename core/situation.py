"""core/situation.py - what is already on this machine, read as data.

Ultron should not have to be told that Minecraft is open. It should know, the
same way a good chief of staff knows which meeting is next: without being asked
and without making a fuss about it.

This module is the read behind that. It answers one question - *what is running
right now, and which version of it* - and it answers it without touching
anything. There is no start, no stop, no focus, no write. `core/process_watch.py`
owns "tell me when it finishes"; `core/appidentity.py` owns "open this";
this one owns "what do I already see".

## What it will not collect

- **Window titles.** The title is the document, the video, the person being
  messaged. `actions/ui_control` reads titles on purpose because it has to act
  on the window; a background summary does not, so it does not.
- **Command lines, except for Minecraft.** The Java command line is the only
  place a Minecraft version is written down while the game runs, so it is read
  for candidate Java processes and for nothing else.
- **Documents, chat logs, browser history, keystrokes.** None of these are
  needed to say "Chrome 141 and VS Code are open".

## Why versions are worth the trouble

"Steam is running" is not useful when the question is why a game will not
launch. "Minecraft 1.21.4 is running" is. A version also tells the model which
guide applies, so it stops inventing menu names from a different release. The
source is always the program's own metadata: the executable's version resource,
the Minecraft launcher profile, or the running game's `--version` argument.

Every read is bounded, cached by file modification time, and failure-tolerant:
a machine without psutil, a locked executable, or a corrupt profile yields an
empty string, never an exception that takes the session down with it.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

__all__ = [
    "App",
    "KNOWN_APPS",
    "foreground",
    "running_apps",
    "snapshot",
    "describe",
    "brief_line",
]

try:  # psutil is optional everywhere else in this project; stay consistent.
    import psutil
except Exception:  # pragma: no cover - exercised only on a bare interpreter
    psutil = None  # type: ignore[assignment]


# Programs worth naming in a short summary, and the word a person would use.
# The key is matched against the whole process name with its extension removed,
# never as a substring. That rule has a scar behind it: "code" as a substring
# labelled the `opencode` client as VS Code, the same way "wp" once opened WPS
# Office instead of WhatsApp. A helper with a different name is not the app.
KNOWN_APPS: dict[str, tuple[str, str]] = {
    # browsers
    "chrome": ("Chrome", "browser"),
    "msedge": ("Edge", "browser"),
    "firefox": ("Firefox", "browser"),
    "brave": ("Brave", "browser"),
    "opera": ("Opera", "browser"),
    "vivaldi": ("Vivaldi", "browser"),
    # development
    "code": ("VS Code", "editor"),
    "cursor": ("Cursor", "editor"),
    "devenv": ("Visual Studio", "editor"),
    "pycharm64": ("PyCharm", "editor"),
    "idea64": ("IntelliJ", "editor"),
    "sublime_text": ("Sublime Text", "editor"),
    "notepad++": ("Notepad++", "editor"),
    "antigravity": ("Antigravity", "editor"),
    "docker": ("Docker", "tool"),
    "ollama": ("Ollama", "tool"),
    "postman": ("Postman", "tool"),
    "opencode": ("OpenCode", "assistant"),
    "codex": ("Codex", "assistant"),
    "claude": ("Claude", "assistant"),
    # communication
    "discord": ("Discord", "chat"),
    "slack": ("Slack", "chat"),
    "teams": ("Teams", "chat"),
    "ms-teams": ("Teams", "chat"),
    "zoom": ("Zoom", "meeting"),
    "telegram": ("Telegram", "chat"),
    "whatsapp": ("WhatsApp", "chat"),
    # media and creative
    "spotify": ("Spotify", "media"),
    "obs64": ("OBS Studio", "capture"),
    "blender": ("Blender", "creative"),
    "unity": ("Unity", "creative"),
    "unrealeditor": ("Unreal Editor", "creative"),
    "photoshop": ("Photoshop", "creative"),
    "vlc": ("VLC", "media"),
    # stores and games
    "steam": ("Steam", "store"),
    "steamwebhelper": ("Steam", "store"),
    "epicgameslauncher": ("Epic Games", "store"),
    # system
    "explorer": ("Explorer", "shell"),
    "taskmgr": ("Task Manager", "system"),
}

# One Minecraft game is one Java process. These words in its command line are
# what tell a game apart from every other Java program on the machine.
_MINECRAFT_MARKERS = ("minecraft", "net.minecraft")


@dataclass(frozen=True)
class App:
    """One running program, as read. Frozen: an observation is not a handle."""

    name: str                      # the label a person would use
    pid: int
    kind: str = "other"            # browser, editor, game, ...
    version: str = ""              # detected version, or "" when unknown

    def describe(self) -> str:
        """Chrome 141.0.7390.55 / Minecraft 1.21.4 / Discord."""
        return f"{self.name} {self.version}".strip()


@dataclass
class Situation:
    """The whole answer: what is in front, and what else is worth naming."""

    foreground: App | None = None
    apps: list[App] = field(default_factory=list)
    note: str = ""                 # why the list may be short, when that matters

    def as_dict(self) -> dict:
        """Only fields a caller needs, and no window titles - see the module docstring."""
        return {
            "foreground": _app_dict(self.foreground),
            "apps": [_app_dict(app) for app in self.apps],
            "note": self.note,
        }


def _app_dict(app: App | None) -> dict | None:
    if app is None:
        return None
    return {
        "name": app.name,
        "pid": app.pid,
        "kind": app.kind,
        "version": app.version,
    }


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------
_VERSION_CACHE: dict[str, tuple[float, str]] = {}


def _file_version(path: str) -> str:
    """The executable's own version resource, or "" when it has none.

    Read from the file's metadata on Windows, from the bundle on macOS. Never
    from the file name: "chrome.exe" says nothing about which release it is.
    """
    if not path or not os.path.isfile(path):
        return ""
    stamp = _stamp(path)
    cached = _VERSION_CACHE.get(path)
    if cached and cached[0] == stamp:
        return cached[1]
    version = ""
    try:
        if os.name == "nt":
            version = _windows_file_version(path)
        elif sys.platform == "darwin":
            version = _plist_version(path)
    except Exception:
        version = ""
    _VERSION_CACHE[path] = (stamp, version)
    return version


def _stamp(path: str) -> float:
    try:
        return os.stat(path).st_mtime
    except OSError:
        return 0.0


def _windows_file_version(path: str) -> str:
    """VS_FIXEDFILEINFO from version.dll: major.minor.build.revision."""
    import ctypes
    from ctypes import wintypes

    class Fixed(ctypes.Structure):
        _fields_ = [
            ("dwSignature", wintypes.DWORD),
            ("dwStrucVersion", wintypes.DWORD),
            ("dwFileVersionMS", wintypes.DWORD),
            ("dwFileVersionLS", wintypes.DWORD),
        ]

    api = ctypes.WinDLL("version")
    size = api.GetFileVersionInfoSizeW(path, None)
    if not size:
        return ""
    buffer = ctypes.create_string_buffer(size)
    if not api.GetFileVersionInfoW(path, 0, size, buffer):
        return ""
    pointer = ctypes.c_void_p()
    length = wintypes.UINT()
    if not api.VerQueryValueW(buffer, "\\", ctypes.byref(pointer), ctypes.byref(length)):
        return ""
    if not pointer.value:
        return ""
    info = ctypes.cast(pointer, ctypes.POINTER(Fixed)).contents
    parts = (
        info.dwFileVersionMS >> 16,
        info.dwFileVersionMS & 0xFFFF,
        info.dwFileVersionLS >> 16,
        info.dwFileVersionLS & 0xFFFF,
    )
    if not any(parts):
        return ""
    # A trailing ".0" is noise on every Windows binary; keep three parts.
    text = ".".join(str(part) for part in parts)
    return text[:-2] if text.endswith(".0") else text


def _plist_version(path: str) -> str:
    """Best-effort CFBundleShortVersionString for a macOS app bundle."""
    import plistlib

    bundle = Path(path)
    for parent in bundle.parents:
        if parent.suffix == ".app":
            info = parent / "Contents" / "Info.plist"
            if info.is_file():
                with info.open("rb") as handle:
                    data = plistlib.load(handle)
                return str(data.get("CFBundleShortVersionString") or "")
    return ""


def minecraft_version(game_dir: Path | None = None) -> str:
    """The Minecraft version the launcher last used, or "" when unknown.

    The launcher writes its own record of this, so reading it is not a guess.
    Two sources, in order: the profile that was used last, then the newest
    installed version folder - a machine that cleaned its profiles still has
    the game files.
    """
    root = game_dir or _minecraft_dir()
    if root is None:
        return ""
    version = _profile_version(root)
    return version or _newest_installed_version(root)


def _minecraft_dir() -> Path | None:
    appdata = os.environ.get("APPDATA")
    candidates = []
    if appdata:
        candidates.append(Path(appdata) / ".minecraft")
    candidates.append(Path.home() / ".minecraft")
    candidates.append(Path.home() / "Library" / "Application Support" / "minecraft")
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def _profile_version(root: Path) -> str:
    """`lastVersionId` of the profile the launcher used most recently."""
    import json

    profiles = root / "launcher_profiles.json"
    if not profiles.is_file():
        return ""
    try:
        data = json.loads(profiles.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return ""
    rows = data.get("profiles")
    if not isinstance(rows, dict):
        return ""
    usable = [
        row for row in rows.values()
        if isinstance(row, dict) and str(row.get("lastVersionId") or "").strip()
    ]
    if not usable:
        return ""
    usable.sort(key=lambda row: str(row.get("lastUsed") or ""), reverse=True)
    return str(usable[0]["lastVersionId"]).strip()


def _newest_installed_version(root: Path) -> str:
    versions = root / "versions"
    if not versions.is_dir():
        return ""
    newest: tuple[float, str] = (0.0, "")
    try:
        for child in versions.iterdir():
            if child.is_dir() and child.name not in ("latest", "snapshot"):
                try:
                    stamp = child.stat().st_mtime
                except OSError:
                    continue
                if stamp > newest[0]:
                    newest = (stamp, child.name)
    except OSError:
        return ""
    return newest[1]


def _minecraft_from_cmdline(cmdline: Sequence[str]) -> str:
    """The version the running game was launched with, if the line says so."""
    parts = [str(part) for part in cmdline]
    joined = " ".join(parts).lower()
    if not any(marker in joined for marker in _MINECRAFT_MARKERS):
        return ""
    for index, part in enumerate(parts):
        if part.lower() == "--version" and index + 1 < len(parts):
            return parts[index + 1].strip()
    return ""


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def _kind(name: str, cmdline: Sequence[str] = ()) -> tuple[str, str]:
    """(label, kind) for one process name. Pure, so the table can be tested."""
    stem = os.path.splitext(name or "")[0].lower()
    if stem in ("java", "javaw"):
        if _minecraft_from_cmdline(cmdline):
            return "Minecraft", "game"
        return "Java", "runtime"
    found = KNOWN_APPS.get(stem)
    if found:
        return found
    return (stem or name or "a program"), "other"


def _iter_processes() -> Iterable[tuple[int, str, str, tuple[str, ...]]]:
    """(pid, name, exe, cmdline) for every process. Injected in tests."""
    if psutil is None:
        return []
    rows = []
    try:
        iterator = psutil.process_iter(["pid", "name", "exe"])
    except Exception:
        return []
    for proc in iterator:
        try:
            info = proc.info
            rows.append(
                (int(info.get("pid") or 0),
                 str(info.get("name") or ""),
                 str(info.get("exe") or ""),
                 ())
            )
        except Exception:
            continue
    return rows


def _cmdline(pid: int) -> tuple[str, ...]:
    """Command line, only for a process whose name already looks like Java."""
    if psutil is None:
        return ()
    try:
        return tuple(psutil.Process(pid).cmdline())
    except Exception:
        return ()


def _build_app(pid: int, name: str, exe: str, cmdline: Sequence[str], game_dir) -> App:
    label, kind = _kind(name, cmdline)
    version = _minecraft_from_cmdline(cmdline) if kind == "game" else ""
    if kind == "game" and not version:
        version = minecraft_version(game_dir)
    if not version and exe and kind not in ("shell", "system"):
        # A shell or a system tool reports the build of Windows, not its own
        # release, so its version would be noise wearing the wrong name.
        version = _file_version(exe)
    # A runtime's version resource is the JDK build; useful, but noisy in a
    # one-line summary. Keep it only when the caller asks for detail.
    return App(name=label, pid=pid, kind=kind, version=version)


def running_apps(
    only: str = "",
    limit: int = 12,
    game_dir: Path | None = None,
) -> list[App]:
    """Known programs that are running now, biggest-name-first is not a thing.

    Unknown processes are deliberately dropped: a list of every helper process
    on a Windows machine is long, unreadable, and tells the owner nothing. The
    table in `KNOWN_APPS` is the definition of "worth naming".
    """
    wanted = (only or "").strip().lower()
    seen: set[tuple[str, str]] = set()
    found: list[App] = []
    for pid, name, exe, cmdline in _iter_processes():
        label, kind = _kind(name, cmdline)
        if kind == "other":
            continue
        if wanted and wanted not in label.lower() and wanted not in name.lower():
            continue
        if kind == "runtime" and not wanted:
            continue  # Java with no game is an implementation detail
        if kind in ("game", "runtime") and not cmdline:
            cmdline = _cmdline(pid)
            label, kind = _kind(name, cmdline)
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(_build_app(pid, name, exe, cmdline, game_dir))
        if len(found) >= limit:
            break
    return found


def foreground() -> App | None:
    """The window the owner is looking at, as an app - never as a title."""
    if os.name != "nt":
        return _foreground_posix()
    try:
        import ctypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        pid_value = int(pid.value)
        if not pid_value:
            return None
        name = exe = ""
        if psutil is not None:
            try:
                proc = psutil.Process(pid_value)
                name = proc.name() or ""
                exe = proc.exe() or ""
            except Exception:
                pass
        label, kind = _kind(name)
        version = _file_version(exe) if exe else ""
        return App(name=label, pid=pid_value, kind=kind, version=version)
    except Exception:
        return None


def _foreground_posix() -> App | None:
    """Best effort elsewhere: report nothing rather than a guess."""
    return None


def snapshot(limit: int = 12, game_dir: Path | None = None) -> Situation:
    """What is in front, what else is running, and why the list may be short."""
    note = ""
    if psutil is None:
        note = ("the process library is missing, so only the front window "
                "can be named - install psutil to see the rest")
    apps = running_apps(limit=limit, game_dir=game_dir)
    front = foreground()
    if front is not None:
        # One program, one line: the front window is already named, and a second
        # Edge entry for the other profile is noise, not information.
        apps = [app for app in apps if app.name.lower() != front.name.lower()]
    return Situation(foreground=front, apps=apps, note=note)


def describe(situation: Situation | None = None, limit: int = 4) -> str:
    """One sentence a person would say out loud. Empty when nothing is known."""
    situation = situation or snapshot()
    front = situation.foreground
    pieces: list[str] = []
    if front is not None:
        # Even an unrecognised program is named. "Something is in front" is a
        # worse answer than the name of it, and leaving it out reads as "no
        # window", which is a different fact.
        pieces.append(f"{front.describe()} in front")
    names = [app.describe() for app in situation.apps[:limit]]
    if names:
        pieces.append(", ".join(names) + " also open")
    if not pieces:
        return "I cannot read the program list on this machine right now."
    sentence = ". ".join(pieces) + "."
    if situation.note:
        sentence += f" ({situation.note})"
    return sentence


def brief_line(situation: Situation | None = None) -> str:
    """The compact line for a prompt: facts only, no sentence around them.

    Kept separate from `describe` because a prompt wants the latest state in as
    few tokens as possible, while a spoken answer wants a sentence.
    """
    situation = situation or snapshot()
    parts = []
    if situation.foreground is not None:
        parts.append("front=" + situation.foreground.describe())
    if situation.apps:
        parts.append("also=" + ", ".join(app.describe() for app in situation.apps[:6]))
    if situation.note:
        parts.append("note=" + situation.note)
    return "; ".join(parts)
