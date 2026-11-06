"""core/app_resolver.py — turn "browser" into the application the user means.

WHY THIS FILE EXISTS
    Asked to open a browser, the assistant pressed Win, typed `browser` into the
    Start-menu search box and pressed Enter. Nothing on that machine is called
    "browser", so the shell offered the closest thing it had: a FOLDER called
    `browser`. A folder opened on screen and the assistant reported success.

    The bug was not a missing name in a list. It was trusting a text-matching
    search box to answer a question about meaning, and never checking what came
    back. Adding "chrome" and "edge" to a constant would have fixed one sentence
    and left the next one broken in a new way.

WHAT IT DOES INSTEAD
    1. Category words are resolved through the operating system's own opinion:
       ask it which application owns `http`. That is the user's default browser
       by definition, and it keeps working when they change it — no vendor names
       are stored here.
    2. Words with no registered owner fall back to the installed-application
       index, matched on words rather than substrings ("notes" matches "Notes",
       "Samsung Notes", "Obsidian — Notes"; it does not match "Notepad++ Helper
       Logs" because that is a different token).
    3. One clear winner is resolved; several comparable candidates are reported
       as AMBIGUOUS so the assistant can ask one short question; none at all is
       UNKNOWN, which is an honest answer the caller can speak.
    4. Any candidate whose target is a directory is rejected outright. A folder
       is never an application, however well its name matches.

    Results are cached briefly, because enumerating Start Menu entries is a
    directory walk and the answer changes about as often as software is
    installed.

WHAT IT CANNOT DO
    It cannot know that "browser" means Firefox on a machine where the default
    handler is broken, and it will not guess. The user's preference file is the
    right place for that, not a whisper of confidence here.
"""

from __future__ import annotations

import os
import platform
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from core.fuzzy import FuzzyIndex

# ─────────────────────────────────────────────────────────────────────────────
#  Category words → the URI scheme that defines them
#
#  Only categories the OPERATING SYSTEM itself resolves are listed. There is no
#  "apps that count as a browser" table anywhere in this project.
# ─────────────────────────────────────────────────────────────────────────────
CAPABILITY_SCHEMES: dict[str, tuple[str, ...]] = {
    "browser": ("http", "https"),
    "web browser": ("http",),
    "internet browser": ("http",),
    "web": ("http",),
    "email": ("mailto",),
    "mail client": ("mailto",),
}

# Category words with no scheme owner. `tokens` are matched against installed
# application names — generic nouns, never product names.
CAPABILITY_TOKENS: dict[str, tuple[str, ...]] = {
    "notes": ("note", "notes", "notepad", "memo"),
    "note taking": ("note", "notes", "memo"),
    "text editor": ("edit", "editor", "text", "write", "word"),
    "editor": ("edit", "editor", "code"),
    "calculator": ("calc",),
    "terminal": ("terminal", "console", "shell", "powershell", "command"),
    "file manager": ("explorer", "files", "finder"),
    "music": ("music", "spotify", "player", "audio"),
    "video player": ("video", "player", "media", "vlc"),
    "spreadsheet": ("excel", "sheets", "calc", "spreadsheet"),
    "presentation": ("powerpoint", "slides", "presentation", "impress"),
    "chat": ("chat", "whatsapp", "telegram", "discord", "signal", "slack"),
    "camera": ("camera",),
    "settings": ("settings", "control panel", "preferences"),
}

# Words that only make sense as a category. When one of these cannot be
# resolved, typing it into the Start menu is guaranteed to be a guess.
_CATEGORY_ONLY = frozenset(CAPABILITY_SCHEMES) | frozenset(CAPABILITY_TOKENS)

RESOLVED = "resolved"
AMBIGUOUS = "ambiguous"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class App:
    name: str
    target: str
    source: str = "index"


@dataclass(frozen=True)
class Resolution:
    status: str
    capability: str = ""
    target: str = ""
    name: str = ""
    candidates: tuple[App, ...] = field(default_factory=tuple)
    reason: str = ""
    confidence: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status == RESOLVED

    def as_facts(self) -> dict:
        facts = {"status": self.status, "requested": self.capability}
        if self.target:
            facts["resolved_to"] = self.name or self.target
        if self.candidates:
            facts["candidates"] = [c.name for c in self.candidates[:4]]
        if self.reason:
            facts["reason"] = self.reason
        return facts


# ─────────────────────────────────────────────────────────────────────────────
#  Backends — everything platform-specific lives here, so the logic above can
#  be tested on any OS without a Windows registry or a Start Menu.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Backends:
    scheme_handler: Callable[[str], Optional[str]] = lambda scheme: None
    installed: Callable[[], list[App]] = list
    running_labels: Callable[[], list[str]] = list
    is_directory: Callable[[str], bool] = lambda target: False


# A fuzzy match only enters the ranking past this confidence, and its score is
# mapped into 4..7 — below an exact name (10) and above a single shared word
# (1), so the tiers stay ordered no matter which one produced the number.
FUZZY_TIER_MIN = 0.75
FUZZY_TIER_BASE = 4.0
FUZZY_TIER_SPAN = 3.0


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", str(text or "").lower()).strip()


def _tokens(text: str) -> list[str]:
    return [t for t in _normalise(text).split() if t]


def capability_for(spoken: str) -> str:
    """The category this phrase names, or '' when it names none."""
    norm = _normalise(spoken)
    if not norm:
        return ""
    if norm in _CATEGORY_ONLY:
        return norm
    # "open my notes app" / "the web browser" — a category word plus filler.
    words = set(_tokens(norm))
    for phrase in _CATEGORY_ONLY:
        if set(_tokens(phrase)) <= words and set(_tokens(phrase)):
            return phrase
    return ""


def is_category_word(spoken: str) -> bool:
    """True when the phrase is a category, so name-typing would be a guess."""
    return bool(capability_for(spoken))


def _score(query_tokens: set[str], app: App, spoken: str) -> float:
    name = _normalise(app.name)
    if name == _normalise(spoken):
        return 10.0
    tokens = set(_tokens(name))
    if not tokens:
        return 0.0
    overlap = len(query_tokens & tokens)
    if not overlap:
        return 0.0
    score = float(overlap)
    if query_tokens <= tokens:          # every word of the request is in the name
        score += 1.5
    if query_tokens & {t[:4] for t in tokens}:
        score += 0.0                     # deliberately no credit for prefixes
    return score


def _candidates(spoken: str, index: list[App]) -> list[tuple[float, App]]:
    query = set(_tokens(spoken))
    capability = capability_for(spoken)
    if capability in CAPABILITY_TOKENS:
        query |= set(CAPABILITY_TOKENS[capability])
    if not query:
        return []
    scored = [(_score(query, app, spoken), app) for app in index]
    return sorted((pair for pair in scored if pair[0] > 0), key=lambda p: -p[0])


# A fuzzy match only enters the ranking past this confidence, and its score is
# mapped into 4..7 — below an exact name (10) and above a single shared word
# (1), so the tiers stay ordered no matter which one produced the number.
FUZZY_TIER_MIN = 0.75
FUZZY_TIER_BASE = 4.0
FUZZY_TIER_SPAN = 3.0


def _fuzzy_index(index: list[App]) -> FuzzyIndex:
    """The matcher's index for this installed-application scan, built once.

    `_installed_cached` hands back the same list object for its 120 s lifetime,
    so identity is the cache key: a rescan produces a new list and therefore a
    new index, with no clock to get wrong.
    """
    global _fuzzy_cache
    cached = _fuzzy_cache
    if cached is not None and cached[0] is index:
        return cached[1]
    built = FuzzyIndex(index, name_of=lambda app: app.name)
    _fuzzy_cache = (index, built)
    return built


def _fuzzy_hits(
    spoken: str, apps: list[App], threshold: float = FUZZY_TIER_MIN
) -> list[tuple[float, App]]:
    """Word overlap found nothing; ask the fuzzy matcher before giving up.

    This is the tier that stops a mispronounced name from falling through to the
    path matcher — the failure that once opened a folder called "browser". The
    index shortlists by phonetic key and by first letter, so an unproductive
    query costs a dictionary lookup per application, not a full comparison.
    """
    if not apps:
        return []
    try:
        found = _fuzzy_index(apps).query(spoken, limit=4, threshold=threshold)
    except Exception:                     # noqa: BLE001 - matching is never fatal
        return []
    span = max(1e-9, 1.0 - threshold)
    hits = [
        (FUZZY_TIER_BASE + FUZZY_TIER_SPAN * ((score - threshold) / span), app)
        for score, app in found
    ]
    return sorted(hits, key=lambda pair: -pair[0])


_lock = threading.RLock()
_index_cache: tuple[float, list[App]] | None = None
_fuzzy_cache: tuple[list[App], FuzzyIndex] | None = None
_index_clock: Callable[[], float] = time.monotonic
INDEX_TTL = 120.0


def _installed_cached(backends: Backends) -> list[App]:
    global _index_cache
    now = _index_clock()
    with _lock:
        if _index_cache and now - _index_cache[0] < INDEX_TTL:
            return _index_cache[1]
    try:
        index = list(backends.installed())
    except Exception:
        index = []
    with _lock:
        _index_cache = (now, index)
    return index


def clear_cache() -> None:
    """For tests and for the moment software is installed while MARK runs."""
    global _index_cache, _fuzzy_cache
    with _lock:
        _index_cache = None
        _fuzzy_cache = None


def _reject_directory(backends: Backends, app: App) -> Optional[App]:
    try:
        if backends.is_directory(app.target):
            return None
    except Exception:
        return app
    return app


# ─────────────────────────────────────────────────────────────────────────────
#  Resolution
# ─────────────────────────────────────────────────────────────────────────────
def resolve(spoken: str, backends: Optional[Backends] = None) -> Resolution:
    """Decide what the user meant, or say honestly that it is not clear."""
    backends = backends or default_backends()
    spoken = (spoken or "").strip()
    if not spoken:
        return Resolution(status=UNKNOWN, reason="no application name was given")

    capability = capability_for(spoken)

    # 1. The operating system's own answer, for categories it defines.
    for scheme in CAPABILITY_SCHEMES.get(capability, ()):
        handler = None
        try:
            handler = backends.scheme_handler(scheme)
        except Exception:
            handler = None
        # Whatever a backend hands back is checked here, not in the backend:
        # the Windows registry can hold a sentence just as easily as xdg-mime
        # can print one, and a resolution that names prose is worse than no
        # resolution at all.
        handler = _handler_from(handler) if handler else None
        if handler and not _is_dir(backends, handler):
            name = _stem(handler) or scheme
            return Resolution(
                status=RESOLVED,
                capability=capability,
                target=handler,
                name=name,
                reason=f"the system's default handler for {scheme}",
                confidence=0.95,
            )

    # 2. Reuse something already running that answers to the same words.
    running = []
    try:
        running = list(backends.running_labels())
    except Exception:
        running = []
    running_apps = [App(name=n, target=n, source="running") for n in running]
    running_hits = _candidates(spoken, running_apps)
    if not running_hits:
        # A window title is not a name, so word overlap is often too strict here.
        # The bar is raised (0.85 rather than 0.75) because reusing a running
        # window is a claim about the same program, not a suggestion.
        running_hits = _fuzzy_hits(spoken, running_apps, threshold=0.85)
    if running_hits and running_hits[0][0] >= 2.0:
        best = running_hits[0][1]
        return Resolution(
            status=RESOLVED,
            capability=capability,
            target=best.target,
            name=best.name,
            reason="already running",
            confidence=0.8,
        )

    # 3. The installed-application index.
    index = _installed_cached(backends)
    hits = _candidates(spoken, index)
    by_similarity = False
    if not hits:
        hits = _fuzzy_hits(spoken, index)
        by_similarity = bool(hits)
    if not hits:
        reason = (
            f"nothing installed answers to '{spoken}'"
            if not capability
            else f"no application is registered for '{capability}' and none installed matches it"
        )
        return Resolution(
            status=UNKNOWN, capability=capability, reason=reason,
            candidates=tuple(),
        )

    hits = [(score, app) for score, app in hits if _reject_directory(backends, app)]
    if not hits:
        return Resolution(
            status=UNKNOWN,
            capability=capability,
            reason=f"the only match for '{spoken}' is a folder, which is not an application",
        )

    top_score, top = hits[0]
    rivals = [app for score, app in hits[1:] if score >= top_score * 0.75]
    if rivals:
        pool = tuple([top] + rivals[:3])
        return Resolution(
            status=AMBIGUOUS,
            capability=capability,
            candidates=pool,
            reason=f"{len(pool)} applications match '{spoken}'",
            confidence=0.4,
        )

    if by_similarity:
        return Resolution(
            status=RESOLVED,
            capability=capability,
            target=top.target,
            name=top.name,
            reason=f"installed application '{top.name}', matched by name similarity",
            confidence=min(0.85, 0.45 + 0.06 * top_score),
        )

    return Resolution(
        status=RESOLVED,
        capability=capability,
        target=top.target,
        name=top.name,
        reason=f"installed application '{top.name}'",
        confidence=min(0.9, 0.5 + 0.1 * top_score),
    )


def _is_dir(backends: Backends, target: str) -> bool:
    try:
        return bool(backends.is_directory(target))
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
#  Platform backends
# ─────────────────────────────────────────────────────────────────────────────

_NOT_A_HANDLER = ("no ", "not ", "error", "unknown", "none", "usage", "cannot")


def _handler_from(line: str) -> Optional[str]:
    """The program named on one line of `xdg-mime`/`gio` output, or None.

    Measured: on a machine with no default browser, `xdg-mime query default
    x-scheme-handler/http` exits 0 and prints
        No default applications for “x-scheme-handler/http”
    which was taken as the handler. The assistant then reported success for
    "open the browser" and tried to launch an application called
    `http”`. An error message is not an answer: anything that reads as prose,
    or as one of those sentences, is refused here and the resolver moves on to
    the next strategy.
    """
    text = " ".join((line or "").split()).strip().strip("\"'")
    if not text:
        return None
    # `gio mime` prefixes the type: "x-scheme-handler/http: firefox.desktop"
    if text.startswith("x-scheme-handler/") and ":" in text:
        text = text.split(":", 1)[1].strip()
    low = text.lower()
    if low.startswith(_NOT_A_HANDLER):
        return None
    if len(text) > 120:
        return None
    if " " in text and not text.endswith((".desktop", ".app")):
        return None                      # a sentence, not a program
    return text

def _windows_backends() -> Backends:
    def scheme_handler(scheme: str) -> Optional[str]:
        try:
            import winreg
        except ImportError:
            return None
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            path = rf"Software\Classes\{scheme}\shell\open\command"
            try:
                with winreg.OpenKey(root, path) as key:
                    command, _ = winreg.QueryValueEx(key, "")
            except OSError:
                continue
            exe = _exe_from_command(command)
            if exe:
                return exe
        return None

    def installed() -> list[App]:
        roots = [
            Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs",
            Path(os.environ.get("PROGRAMDATA", "")) / r"Microsoft\Windows\Start Menu\Programs",
        ]
        apps: list[App] = []
        for root in roots:
            if not root.is_dir():
                continue
            try:
                entries = list(root.rglob("*.lnk"))
            except OSError:
                continue
            apps += [App(name=p.stem, target=str(p), source="start menu") for p in entries]
        return apps

    def running_labels() -> list[str]:
        try:
            from core import appidentity

            return [m.label for m in appidentity.running("", include_self=False)][:200]
        except Exception:
            return []

    return Backends(
        scheme_handler=scheme_handler,
        installed=installed,
        running_labels=running_labels,
        is_directory=lambda target: Path(target).is_dir(),
    )


def _posix_backends() -> Backends:
    def scheme_handler(scheme: str) -> Optional[str]:
        import subprocess

        for command in (["xdg-mime", "query", "default", f"x-scheme-handler/{scheme}"],
                        ["gio", "mime", f"x-scheme-handler/{scheme}"]):
            try:
                out = subprocess.run(command, capture_output=True, text=True, timeout=3)
            except (OSError, subprocess.SubprocessError):
                continue
            for line in (out.stdout or "").splitlines():
                candidate = _handler_from(line)
                if candidate and out.returncode == 0:
                    return candidate
        return None

    def installed() -> list[App]:
        apps: list[App] = []
        for root in (Path("/usr/share/applications"), Path.home() / ".local/share/applications",
                     Path("/Applications")):
            if not root.is_dir():
                continue
            try:
                entries = list(root.glob("*.desktop")) or list(root.glob("*.app"))
            except OSError:
                continue
            apps += [App(name=p.stem.replace("-", " "), target=str(p), source="desktop entry")
                     for p in entries]
        return apps

    return Backends(
        scheme_handler=scheme_handler,
        installed=installed,
        running_labels=list,
        is_directory=lambda target: Path(target).is_dir(),
    )


def default_backends() -> Backends:
    system = platform.system()
    if system == "Windows":
        return _windows_backends()
    if system in ("Linux", "Darwin"):
        return _posix_backends()
    return Backends()


def _stem(target: str) -> str:
    """`msedge` from `C:\\Apps\\msedge.exe`, on any platform.

    `Path(...).stem` is not portable enough here: on Linux a Windows path is one
    long filename with backslashes in it, so the "stem" comes back as the whole
    path. This splits on both separators instead.
    """
    text = str(target or "").replace("\\", "/").rstrip("/")
    base = text.rsplit("/", 1)[-1]
    return base.rsplit(".", 1)[0] if "." in base else base


def _exe_from_command(command: str) -> Optional[str]:
    """Pull the executable out of a `"C:\\...\\browser.exe" -- "%1"` command."""
    text = str(command or "").strip()
    if not text:
        return None
    match = re.match(r'^"([^"]+)"', text) or re.match(r"^([^\s]+)", text)
    return match.group(1) if match else None
