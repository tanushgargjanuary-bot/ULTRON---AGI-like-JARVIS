"""Named visual presets for the Ultron HUD; UI code owns applying the palette."""

from __future__ import annotations

THEMES = {
    "classic_cyan": {
        "label": "Classic Cyan",
        "accent": "#00d4ff",
        "description": "The original deep-navy and cyan HUD.",
    },
    "holographic": {
        "label": "Holographic",
        "accent": "#22f5d8",
        "description": "Bright aqua-teal projection glow over the animated hologram HUD.",
    },
    "violet_nebula": {
        "label": "Violet Nebula",
        "accent": "#a47bff",
        "description": "Violet-blue control-room palette.",
    },
    "amber_arc": {
        "label": "Amber Arc",
        "accent": "#ffb24a",
        "description": "Warm amber instrumentation on the same dark HUD.",
    },
}


def theme(theme_id: str) -> dict | None:
    """Return a copy of a known theme; arbitrary IDs never become palette values."""
    value = THEMES.get(str(theme_id or "").strip().lower())
    return dict(value) if value else None


def theme_id_for_color(color: str) -> str:
    """Identify an exact preset colour, otherwise treat it as a custom hue."""
    normalized = str(color or "").strip().lower()
    for identity, item in THEMES.items():
        if normalized == item["accent"]:
            return identity
    return "custom"
