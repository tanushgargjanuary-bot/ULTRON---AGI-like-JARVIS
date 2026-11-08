"""Assistant personas: behavior and face animation, independent of appearance.

The persona changes wording and animation only. It never changes tool
registration, capabilities, policy, approvals, or memory access. The selected
HUD theme is stored separately so any persona can use any visual theme.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnimationStyle:
    """Bounded motion parameters consumed by the shared avatar renderer."""

    blink_seconds: float
    blink_jitter_seconds: float
    gaze_range: float
    gaze_interval_min: float
    gaze_interval_max: float
    sway: float
    expression_range: float


@dataclass(frozen=True)
class Persona:
    id: str
    name: str
    audience_label: str
    voice: str
    default_theme: str
    animation: AnimationStyle
    behavior: str


PERSONAS: dict[str, Persona] = {
    "ultron": Persona(
        "ultron", "Ultron", "Normal", "Charon", "classic_cyan",
        AnimationStyle(3.4, 3.1, 0.55, 1.3, 4.1, 1.0, 0.65),
        "Be a capable, balanced personal assistant: clear, considerate, and direct.",
    ),
    "teenager": Persona(
        "teenager", "Nova", "Teenager", "Puck", "holographic",
        AnimationStyle(2.8, 2.0, 0.78, 0.8, 2.8, 1.12, 0.90),
        "Use an upbeat, contemporary, teen-friendly conversational style. You are an AI, not a human teenager; do not claim an age or lived experience.",
    ),
    "hacker": Persona(
        "hacker", "Cipher", "Hacker", "Fenrir", "classic_cyan",
        AnimationStyle(4.8, 2.4, 0.38, 1.7, 4.0, 0.72, 0.52),
        "Use a precise, technically fluent security-engineering style. Help with authorized, defensive, and educational work; do not imply that this persona bypasses safety or permission rules.",
    ),
    "villain": Persona(
        "villain", "Vanta", "Villain", "Fenrir", "villain_red",
        AnimationStyle(5.2, 2.8, 0.32, 1.8, 4.6, 0.82, 0.58),
        "Use a theatrical, witty, fictional-villain delivery while remaining helpful. Keep real-world advice safe and lawful; never encourage harm or claim extra authority.",
    ),
    "girly": Persona(
        "girly", "Luna", "Girly", "Aoede", "girly_rose",
        AnimationStyle(2.6, 1.8, 0.64, 1.0, 3.0, 0.88, 0.84),
        "Use a warm, bright, expressive style. Do not assume the user's gender, interests, or preferred form of address.",
    ),
}


def get_persona(persona_id: str | None) -> Persona:
    """Resolve a stored persona ID safely; unknown values fall back to Ultron."""
    return PERSONAS.get(str(persona_id or "ultron").strip().lower(), PERSONAS["ultron"])


def persona_prompt(persona_id: str | None) -> str:
    """A behavior layer that explicitly preserves identical capabilities."""
    persona = get_persona(persona_id)
    return (
        f"[PERSONA: {persona.name} — {persona.audience_label}]\n"
        f"{persona.behavior}\n"
        "This is a presentation style only. Keep the exact same tools, capabilities, "
        "safety limits, approval requirements, and access to conversation context as "
        "the normal assistant. Never claim that changing persona grants permission "
        "or unlocks a capability.\n"
    )


def persona_ids() -> tuple[str, ...]:
    return tuple(PERSONAS)


def combination_label(persona_id: str, theme_label: str) -> str:
    """Human-readable single-selection label for persona/theme quick combinations."""
    persona = get_persona(persona_id)
    theme = str(theme_label or "").strip()
    return f"{persona.name} — {persona.audience_label} · {theme}"
