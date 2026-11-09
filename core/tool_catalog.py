"""core/tool_catalog.py — Ultron's knowledge of its own hands.

An assistant that cannot say what it can do is guessing. This module builds one
list of every tool Ultron actually has, from the four places tools can come from,
and annotates each with what it is for, which group it belongs to, and whether it
can be used on this machine right now:

    inline   the eight handlers woven into main.py's session (memory, screen,
             camera, status, shutdown, undo, digest)
    action   actions/*.py, auto-discovered by the action loader
    plugin   plugins/*.py, validated by the plugin loader
    bridge   the five external tools wired through core/bridges.py

Sources are read the way the app reads them, not from a hand-written list, so the
catalog cannot drift away from reality: an action that fails to import shows up
as unavailable with the loader's own reason, and a plugin that fails validation
shows up with its error instead of quietly disappearing.

The catalog is deliberately cheap. Inline declarations are read by parsing
main.py, never by importing it (importing main starts the whole engine), and
plugins are read through their loader so a broken file cannot crash the panel.
"""

from __future__ import annotations
from core import failures

import ast
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Which group a tool belongs to, for the tab list and for the model's own picture
# of itself. An explicit table beats a guess from the file name: `file_controller`
# and `dev_agent` both sound like development, and only one of them is.
CATEGORIES: dict[str, str] = {
    # system and computer use
    "system_status": "system", "computer_settings": "system", "computer_control": "system",
    "open_app": "system", "desktop_control": "system", "shutdown_jarvis": "system",
    "manage_monitor": "system", "ui_control": "system", "game_updater": "system",
    # files and documents
    "file_controller": "files", "file_processor": "files", "code_helper": "files",
    "dev_agent": "files",
    # knowledge and time
    "web_search": "knowledge", "web_read": "knowledge", "weather_report": "knowledge", "recall_memory": "knowledge",
    "local_models": "developer",
    "save_memory": "knowledge", "daily_digest": "knowledge", "reminder": "knowledge",
    "flight_finder": "knowledge", "system_monitor": "knowledge",
    # media
    "video_player": "media", "youtube_video": "media", "screen_process": "media",
    "close_camera": "media",
    # communication
    "send_message": "communication",
    # external tools (bridges)
    "rea_bridge": "security", "hyperframes_bridge": "media",
    "hindsight_bridge": "memory", "voicestudio_bridge": "media", "hypit_bridge": "media",
    "dev_json": "developer", "dev_regex": "developer", "dev_hash": "developer",
    "dev_cron": "developer", "crypto_ident": "security", "net_check": "security",
}

CATEGORY_ORDER = ["system", "files", "knowledge", "media", "security", "memory",
                  "communication", "developer", "other"]

CATEGORY_TITLES = {
    "system": "SYSTEM & CONTROL",
    "files": "FILES & CODE",
    "knowledge": "KNOWLEDGE & TIME",
    "media": "MEDIA & VOICE",
    "security": "SECURITY & RESEARCH",
    "memory": "MEMORY",
    "communication": "COMMUNICATION",
    "developer": "DEVELOPER",
    "other": "OTHER",
}


@dataclass(frozen=True)
class Entry:
    name: str
    kind: str                 # inline | action | plugin | bridge
    category: str
    summary: str
    available: bool = True
    reason: str = ""

    @property
    def label(self) -> str:
        """The name a human reads: `bridge:rea` is the integration for REA."""
        return self.name.split(":", 1)[1] if self.name.startswith("bridge:") else self.name

    def line(self) -> str:
        mark = "ok " if self.available else "-- "
        kind = "external" if self.kind == "bridge" else self.kind
        text = f"{mark}{self.label} [{kind}] — {self.summary}"
        return text if self.available else f"{text}  ({self.reason})"


def _summary(text: str, limit: int = 110) -> str:
    clean = " ".join(str(text or "").split())
    if not clean:
        return "no description"
    first = clean.split(". ")[0]
    clean = first if len(first) > 20 else clean
    return clean if len(clean) <= limit else clean[: limit - 1] + "…"


# ── sources ──────────────────────────────────────────────────────────────────
def _inline_entries(main_py: Path | None = None) -> list[Entry]:
    """Read TOOL_DECLARATIONS out of main.py without importing it.

    `ast.literal_eval` on the assignment keeps the catalog in step with the file:
    a new inline tool appears here the moment it is declared, with no second list
    to update.
    """
    path = main_py or (ROOT / "main.py")
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", "") == "TOOL_DECLARATIONS" for t in node.targets):
            try:
                declarations = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                return []
            return [Entry(name=str(d.get("name", "")), kind="inline",
                          category=CATEGORIES.get(str(d.get("name", "")), "other"),
                          summary=_summary(d.get("description", "")))
                    for d in declarations if isinstance(d, dict) and d.get("name")]
    return []


def _action_entries(actions_dir: Path | None = None) -> list[Entry]:
    """Every actions/*.py the real loader can load, plus the ones it could not."""
    from core.action_loader import discover_actions

    folder = actions_dir or (ROOT / "actions")
    if not folder.is_dir():
        return []                     # a missing folder is zero tools, not a crash
    registry = discover_actions(folder, logger=lambda _m: None)
    entries = []
    for declaration in registry.get_tool_declarations():
        name = str(declaration.get("name", ""))
        if name:
            entries.append(Entry(name=name, kind="action",
                                 category=CATEGORIES.get(name, "other"),
                                 summary=_summary(declaration.get("description", ""))))
    # The loader's failure map {file: reason} is the most useful thing this panel
    # can show: a tool the model expects and cannot call is a silence otherwise.
    failures = getattr(registry, "failures", None)
    if callable(failures):
        try:
            failures = failures()
        except Exception:                                  # noqa: BLE001
            failures = {}
    for filename, reason in (failures or {}).items():
        name = Path(str(filename)).stem or "unknown"
        entries.append(Entry(name=name, kind="action", category="other",
                             summary="could not be loaded", available=False,
                             reason=str(reason or "unknown error")))
    return entries


def _plugin_entries(plugins_dir: Path | None = None) -> list[Entry]:
    from core.plugin_loader import discover_plugins

    folder = plugins_dir or (ROOT / "plugins")
    if not folder.is_dir():
        return []
    registry = discover_plugins(folder, core_tool_names=set(), logger=lambda _m: None)
    entries = []
    for record in registry.list_for_ui():
        entries.append(Entry(
            name=str(record.get("name", "")), kind="plugin",
            category=CATEGORIES.get(str(record.get("name", "")), "developer"),
            summary=_summary(record.get("description", "")),
            available=bool(record.get("valid")),
            reason=str(record.get("error", "") or "")))
    return entries


def _bridge_entries() -> list[Entry]:
    from core import bridges

    entries = []
    for item in bridges.probe_all():
        entries.append(Entry(name=f"bridge:{item['key']}", kind="bridge",
                             category=CATEGORIES.get(f"bridge:{item['key']}",
                                                     CATEGORIES.get(f"{item['key']}_bridge",
                                                                    item["category"])),
                             summary=_summary(item["summary"]),
                             available=bool(item["ready"]),
                             reason="" if item["ready"] else str(item["detail"])))
    return entries


def build(include_bridges: bool = True) -> list[Entry]:
    """The whole catalog, deduplicated by name, in a stable order."""
    entries: list[Entry] = []
    for source in (_inline_entries(), _action_entries(), _plugin_entries()):
        try:
            entries.extend(source)
        except Exception as error:                                      # noqa: BLE001
            failures.note("tool_catalog.build", error)
            continue
    if include_bridges:
        try:
            entries.extend(_bridge_entries())
        except Exception as error:                                      # noqa: BLE001
            failures.note("tool_catalog.build", error)

    seen: set[str] = set()
    unique: list[Entry] = []
    for entry in entries:
        if entry.name and entry.name not in seen:
            seen.add(entry.name)
            unique.append(entry)
    return unique


def grouped(entries: list[Entry] | None = None) -> dict[str, list[Entry]]:
    """Category -> entries, in CATEGORY_ORDER, empty groups dropped."""
    out: dict[str, list[Entry]] = {}
    for entry in entries if entries is not None else build():
        out.setdefault(entry.category, []).append(entry)
    for group in out.values():
        group.sort(key=lambda e: (not e.available, e.name))
    return {name: out[name] for name in CATEGORY_ORDER if name in out}


def render_text(entries: list[Entry] | None = None) -> str:
    """The catalog as text — what Ultron reads when asked what it can do."""
    entries = build() if entries is None else entries
    groups = grouped(entries)
    ready = sum(1 for e in entries if e.available)
    lines = [f"I have {len(entries)} tools, {ready} usable on this machine."]
    for category, items in groups.items():
        lines.append("")
        lines.append(f"{CATEGORY_TITLES.get(category, category.upper())}:")
        for entry in items:
            lines.append("  " + entry.line())
    return "\n".join(lines)


def describe(name: str, entries: list[Entry] | None = None) -> str:
    """One tool, in full — the answer to "what does your X do?"."""
    wanted = str(name or "").strip().lower()
    for entry in (build() if entries is None else entries):
        if entry.name.lower() == wanted or entry.name.lower().endswith(wanted):
            state = "is usable now" if entry.available else f"cannot be used: {entry.reason}"
            summary = entry.summary.rstrip(". ")
            return (f"{entry.label} ({entry.kind}, {entry.category}) — {summary}. "
                    f"It {state}.")
    return f"I do not have a tool called '{name}'."
