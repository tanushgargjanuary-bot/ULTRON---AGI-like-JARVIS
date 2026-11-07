"""core/policy.py — risk tiers that decide whether an action needs a human.

THE PROBLEM THIS REPLACES
    `core/custom_gate.py` used to hold a four-name allowlist:

        READ_ONLY = {"recall_memory", "system_status", "web_search", "weather_report"}

    Everything else — opening a browser, a media control, a screenshot, a
    scheduled reminder — went to the HUD banner. That is not caution, it is a
    gate that fires so often it stops carrying information: the user learns to
    press CONFIRM without reading, and the one banner that mattered gets the
    same reflex. Reported as "it asks permission for even the slightest things",
    which is precisely what a four-name allowlist does to a forty-action app.

    `core/confirm.py` already states the policy this module now implements:
    confirm the genuinely irreversible, and let `core/undo.py` carry the rest.

FOUR TIERS
    observe   read-only or side-effect free. Always allowed.
    routine   reversible, bounded, and normally something the user just asked
              for: open an app, press a key, change the volume, play a video.
              Always allowed. Reversibility is what earns the exemption.
    guarded   destroys or overwrites data, touches another person or account,
              installs software, powers the machine down, or edits this program.
              Confirmed on the HUD.
    sensor    captures the screen, camera or microphone. Confirmed, and it can
              carry a visible indicator. A task may pre-authorise it for its own
              duration with `grant("screen")`; that grant dies with the task.

FAIL CLOSED ON THE UNKNOWN
    A tool nobody classified is `guarded`, not `routine`. New tools are not
    quietly trusted because they were added after this file was written; they
    have to be classified on purpose, and a plugin cannot exempt itself.

WHAT THIS IS NOT
    It is not a security boundary on its own. It decides who gets asked. The
    enforcement that matters — workspace confinement, the frozen-argument
    snapshot, the confirmation token that the model cannot construct — lives in
    `core/custom_gate.py` and stays exactly as it was.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Optional


class Tier(str, Enum):
    OBSERVE = "observe"
    ROUTINE = "routine"
    GUARDED = "guarded"
    SENSOR = "sensor"


@dataclass(frozen=True)
class Decision:
    """What the gate should do with one call."""

    tier: Tier
    allow: bool
    reason: str

    def __str__(self) -> str:  # shown in status output and logs
        verdict = "allow" if self.allow else "ask"
        return f"{self.tier.value}:{verdict} ({self.reason})"


# ─────────────────────────────────────────────────────────────────────────────
#  Classification tables
#
#  Names are the tool names the model calls, not the modules that provide them.
# ─────────────────────────────────────────────────────────────────────────────

OBSERVE_TOOLS: frozenset[str] = frozenset(
    {
        "recall_memory",
        "system_status",
        "web_search",
        "weather_report",
        "local_models",
        # `system_monitor` used to be listed here and is not a tool in this
        # build — a name in these tables is a claim about the app, and a claim
        # about a tool that does not exist is how the tables drift out of step
        # with the tools. The real name is `system_status`, which is above.
    }
)

ROUTINE_TOOLS: frozenset[str] = frozenset(
    {
        # Undo reverses something the user already approved, and close_camera
        # stops a capture. Gating either of them puts a confirmation in front of
        # the way OUT of a mistake — the one prompt that must never exist, and
        # the standing rule is that a capture has a working stop.
        "undo",
        "close_camera",
        "open_app",
        "browser_control",
        "computer_control",
        "video_player",
        "reminder",
        "desktop_control",
        "youtube_video",
        "file_processor",
        "flight_finder",
        # Local, deterministic converters. They read a string, return a string,
        # touch no file and reach no network, so a confirmation banner in front
        # of them is the "excessive prompt for a trivial action" the owner
        # rejected. The tier is per action for the mixed ones, below.
        "dev_json",
        "dev_regex",
        "dev_hash",
        "dev_cron",
        "crypto_ident",
        # Two read-only readers of public technical data. Neither changes an
        # account, a file or a device; both return what a browser would show.
        # A confirmation banner in front of "what is trending" is the excessive
        # prompting the owner rejected, so the tier is routine — and the table
        # below keeps every write-shaped action at guarded if one is ever added.
        "github_tool",
        "tech_platforms",
    }
)

GUARDED_TOOLS: frozenset[str] = frozenset(
    {
        "send_message",
        "game_updater",
        "dev_agent",
        "code_helper",
        "file_controller",
        "computer_settings",
        # Not `screen_processor`: that name belongs to no tool. The screen tool
        # is `screen_process`, and it is in SENSOR_TOOLS below — it was falling
        # through to "unclassified", so the sensor tier's grant ("this task may
        # use the screen") never applied to it and every capture raised a generic
        # prompt instead of the sensor one.
    }
)

SENSOR_TOOLS: frozenset[str] = frozenset(
    {
        "screen_process",        # the real name; captures screen or camera
        "camera",
        "screen_capture",
    }
)

# Guarded, with a reason that says what it actually is. The table above is a set,
# so it can carry the tier but not the explanation, and "can destroy, publish or
# reconfigure" is not true of remembering a note or turning the assistant off.
_GUARDED_REASONS: dict[str, str] = {
    "save_memory": "memory is permanent — remembering is approval-gated",
    "forget_memory": "memory is permanent — forgetting is approval-gated",
    "shutdown_jarvis": "turns the assistant off",
    # net_check with no action is not one of its three verbs, so it must not fall
    # through to "unclassified": it is a network tool, and the answer stays ask.
    "net_check": "probes a host the user named — say what to check",
    "rea_bridge": "drives an external reverse-engineering agent",
    "hyperframes_bridge": "spawns a renderer that writes video files",
    "hypit_bridge": "spawns a pipeline that renders and can publish video",
    "hindsight_bridge": "posts to an external memory service",
    "voicestudio_bridge": "posts to an external voice service",
}



# Tools that carry their own, stricter internal gates. `custom_jarvis` either
# runs read-only skills or routes mutations through ControlledRegistry, which
# asks per step; adding a second banner in front of it produced two prompts for
# one decision.
# `system_prompt` edits the instruction the model gives itself, which sounds like the
# last tool that should carry its own gate — so it carries the strictest one in the
# project: nothing is written until the same change is confirmed twice, in two
# different places, and every applied change keeps the version it replaced. The gate
# lives in core/prompt_store.py, where it can be tested, rather than in the policy
# table, where it would be one line somebody could delete without noticing.
BYPASS_TOOLS: frozenset[str] = frozenset({"custom_jarvis", "system_prompt"})

# A tool can be mostly one tier and answer to a dangerous action name. These
# tables are consulted before the tool-level tier and can only make things
# STRICTER or, for a read-only verb on a mixed tool, more permissive.
_ACTION_TIERS: dict[str, dict[str, Tier]] = {
    # Structure-first computer use (core/ui_tree.py). Reading the interface is a
    # sensor act: the snapshot contains whatever the window is showing, which may
    # be a message, a balance or a medical record. Acting on one named element is
    # routine and reversible; a batch is not, because it is several actions after
    # a single approval.
    "ui_control": {
        "describe": Tier.OBSERVE,
        "snapshot": Tier.SENSOR,
        "drill": Tier.SENSOR,
        "act": Tier.ROUTINE,
        "batch": Tier.GUARDED,
    },
    "computer_control": {
        "screenshot": Tier.SENSOR,
        "screen_find": Tier.SENSOR,
        "screen_click": Tier.SENSOR,
        "close_app": Tier.GUARDED,
        "user_data": Tier.GUARDED,
    },
    "computer_settings": {
        # Reversible system settings the user asks for by name. Toggling the
        # volume is not a decision that needs a second party.
        "volume": Tier.ROUTINE,
        "set_volume": Tier.ROUTINE,
        "mute": Tier.ROUTINE,
        "unmute": Tier.ROUTINE,
        "brightness": Tier.ROUTINE,
        "dark_mode": Tier.ROUTINE,
        "night_light": Tier.ROUTINE,
        "do_not_disturb": Tier.ROUTINE,
        "wallpaper": Tier.ROUTINE,
        "shutdown": Tier.GUARDED,
        "restart": Tier.GUARDED,
        "reboot": Tier.GUARDED,
        "sleep": Tier.GUARDED,
        "hibernate": Tier.GUARDED,
        "lock": Tier.GUARDED,
        "sign_out": Tier.GUARDED,
        "uninstall": Tier.GUARDED,
    },
    "browser_control": {
        "close_all": Tier.GUARDED,
        "screenshot": Tier.SENSOR,
    },
    "desktop_control": {
        "wallpaper": Tier.ROUTINE,
        "screenshot": Tier.SENSOR,
    },
    "file_controller": {
        "read": Tier.OBSERVE,
        "list": Tier.OBSERVE,
        "find": Tier.OBSERVE,
        "info": Tier.OBSERVE,
        "largest": Tier.OBSERVE,
        "disk_usage": Tier.OBSERVE,
        "delete": Tier.GUARDED,
        "move": Tier.GUARDED,
        "rename": Tier.GUARDED,
        "organize_desktop": Tier.GUARDED,
    },
    "file_processor": {
        "read": Tier.OBSERVE,
        "summarise": Tier.OBSERVE,
        "summarize": Tier.OBSERVE,
    },
    "video_player": {
        "play": Tier.ROUTINE,
        "pause": Tier.ROUTINE,
        "stop": Tier.ROUTINE,
        "seek": Tier.ROUTINE,
    },
    # net_check is three tools wearing one name. Resolving a name and reading a
    # URL's headers are reads. Checking a port on a host you do not own is a scan,
    # so it is guarded; the plugin itself also refuses a public host unless the
    # caller passes allow_public, and this table is the second lock on that door.
    "net_check": {
        "dns": Tier.OBSERVE,
        "headers": Tier.ROUTINE,
        "port": Tier.GUARDED,
    },
    # The five integrated tools. Asking one whether it is alive is a read. Making
    # it do work spawns a program, renders video, or posts to a local service, and
    # that is guarded: it can write files and it can publish.
    "rea_bridge": {"help": Tier.OBSERVE},
    "hyperframes_bridge": {"help": Tier.OBSERVE, "command": Tier.GUARDED},
    "hypit_bridge": {"help": Tier.OBSERVE, "command": Tier.GUARDED},
    "hindsight_bridge": {"status": Tier.OBSERVE, "request": Tier.GUARDED},
    "voicestudio_bridge": {"status": Tier.OBSERVE, "request": Tier.GUARDED},
}

# Verbs that write into the filesystem. Inside an approved workspace they are
# routine (the user picked that folder for exactly this); anywhere else they can
# overwrite somebody's work and stay guarded.
_WRITE_VERBS = frozenset({"write", "create_file", "create_folder", "append", "save"})
_PATH_KEYS = ("path", "file", "filename", "target", "destination", "dest", "folder")

_lock = threading.RLock()
_workspace_roots: tuple[Path, ...] = ()
_grants: dict[str, float] = {}          # scope -> monotonic expiry
_clock = None                            # injectable for tests


def _now() -> float:
    if _clock is not None:
        return float(_clock())
    import time

    return time.monotonic()


def set_workspace_roots(roots: Iterable[str | Path]) -> None:
    """Tell the policy which folders the user has approved for this session.

    Called by the custom service when a workspace is selected. Without it, every
    write is guarded — the safe default, not a broken one.
    """
    resolved: list[Path] = []
    for root in roots:
        try:
            resolved.append(Path(root).expanduser().resolve())
        except (OSError, RuntimeError):
            continue
    global _workspace_roots
    with _lock:
        _workspace_roots = tuple(resolved)


def workspace_roots() -> tuple[Path, ...]:
    with _lock:
        return _workspace_roots


def grant(scope: str, seconds: float = 600.0) -> None:
    """Pre-authorise a tier or capability for a bounded time.

    Used for task-level consent: the user said "watch the screen while I do
    this", so `grant("sensor", 900)` lets that task capture without a banner for
    fifteen minutes and no longer. Grants are deliberately explicit API calls —
    no text in the conversation silently creates one.
    """
    with _lock:
        _grants[scope] = _now() + max(0.0, float(seconds))


def revoke(scope: Optional[str] = None) -> None:
    with _lock:
        if scope is None:
            _grants.clear()
        else:
            _grants.pop(scope, None)


def grants() -> dict[str, float]:
    """Active grants as scope -> seconds remaining (expired ones pruned)."""
    now = _now()
    with _lock:
        for scope in [s for s, until in _grants.items() if until <= now]:
            _grants.pop(scope, None)
        return {s: round(until - now, 3) for s, until in _grants.items()}


# The two platform readers are routine as a whole. If a writing action is ever
# added to either, it is listed here and it asks first — the default for a name
# that is not in the table stays "guarded", so forgetting an entry fails safe.
_ACTION_TIERS.setdefault("github_tool", {})
_ACTION_TIERS["github_tool"].update({
    "trending": Tier.ROUTINE,
    "status": Tier.ROUTINE,
    "repo": Tier.ROUTINE,
    "pulls": Tier.ROUTINE,
    "checks": Tier.ROUTINE,
    "notifications": Tier.ROUTINE,
    "watch": Tier.ROUTINE,
    "unwatch": Tier.ROUTINE,
    "watchlist": Tier.ROUTINE,
    "reminders": Tier.ROUTINE,
})
_ACTION_TIERS.setdefault("tech_platforms", {})
_ACTION_TIERS["tech_platforms"].update({
    "hackernews": Tier.ROUTINE,
    "stackexchange": Tier.ROUTINE,
    "pypi": Tier.ROUTINE,
    "npm": Tier.ROUTINE,
})


def _granted(tier: Tier) -> bool:
    with _lock:
        return any(until > _now() for until in _grants.values()) and (
            tier.value in _grants
        )


def _path_inside_workspace(value: Any) -> bool:
    try:
        candidate = Path(str(value)).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    for root in workspace_roots():
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        else:
            return True
    return False


def _escalate(name: str, args: dict[str, Any]) -> Optional[Decision]:
    """A stricter or (rarely) looser verdict from the action name or its args."""
    action = str(args.get("action") or "").strip().lower()

    table = _ACTION_TIERS.get(name)
    if table and action and action in table:
        tier = table[action]
        if tier in (Tier.OBSERVE, Tier.ROUTINE):
            return Decision(tier, True, f"'{action}' is {tier.value}")
        if tier is Tier.SENSOR and _granted(Tier.SENSOR):
            return Decision(tier, True, f"'{action}' uses a sensor within a granted scope")
        return Decision(tier, False, f"'{action}' is {tier.value}")

    if name == "file_controller" and action in _WRITE_VERBS:
        for key in _PATH_KEYS:
            if key in args and _path_inside_workspace(args[key]):
                return Decision(
                    Tier.ROUTINE, True, f"'{action}' inside the approved workspace"
                )
        return Decision(
            Tier.GUARDED,
            False,
            f"'{action}' outside the approved workspace",
        )

    if name == "file_controller" and action in ("copy",):
        return Decision(Tier.ROUTINE, True, "copy leaves the original in place")

    return None


def classify(name: str, args: dict[str, Any] | None = None) -> Decision:
    """The verdict for one call. Pure apart from the grant table and roots."""
    args = dict(args or {})
    name = str(name or "")

    if name in BYPASS_TOOLS:
        return Decision(Tier.ROUTINE, True, "tool carries its own per-step gate")

    stricter = _escalate(name, args)
    if stricter is not None:
        return stricter

    if name in OBSERVE_TOOLS:
        return Decision(Tier.OBSERVE, True, "read-only")
    if name in SENSOR_TOOLS:
        if _granted(Tier.SENSOR):
            return Decision(Tier.SENSOR, True, "sensor within a granted scope")
        return Decision(Tier.SENSOR, False, "captures the screen or camera")
    if name in ROUTINE_TOOLS:
        return Decision(Tier.ROUTINE, True, "reversible, bounded")
    if name in _GUARDED_REASONS:
        return Decision(Tier.GUARDED, False, _GUARDED_REASONS[name])
    if name in GUARDED_TOOLS:
        return Decision(Tier.GUARDED, False, "can destroy, publish or reconfigure")

    # Unknown tools are not trusted because they are new.
    return Decision(Tier.GUARDED, False, "unclassified tool — treated conservatively")


def decide(name: str, args: dict[str, Any] | None = None) -> Decision:
    """`classify`, with no exceptions raised for malformed input."""
    try:
        return classify(name, args)
    except Exception as exc:  # a policy crash must never become an allow
        return Decision(Tier.GUARDED, False, f"policy error ({type(exc).__name__})")


def describe() -> str:
    """Human-readable summary for the status panel."""
    lines = [
        f"observe ({len(OBSERVE_TOOLS)}): " + ", ".join(sorted(OBSERVE_TOOLS)),
        f"routine ({len(ROUTINE_TOOLS)}): " + ", ".join(sorted(ROUTINE_TOOLS)),
        f"guarded ({len(GUARDED_TOOLS)}): " + ", ".join(sorted(GUARDED_TOOLS)),
        "sensor: screen, camera, microphone capture",
        f"workspace roots: {[str(p) for p in workspace_roots()] or 'none approved'}",
        f"active grants: {grants() or 'none'}",
    ]
    return "\n".join(lines)
