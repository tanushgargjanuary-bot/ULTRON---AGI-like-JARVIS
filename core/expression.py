"""core/expression.py — what the face is feeling, as numbers.

WHY NOT JUST LIP-SYNC
    The avatar already angles its head, lifts its brows with the loudness of a
    phrase, flicks its gaze, blinks and drops its lids when asleep. All of that
    is driven by *sound* and *app state*. None of it is driven by *meaning*, so
    a sentence of sympathy and a sentence of triumph produce the same face.

    This module is the missing channel: a small, bounded parameter vector that
    the conversation can ask for, blended in `core/avatar.py` with everything
    that already moves.

WHY NUMBERS AND NOT "PLAY SADNESS"
    Named animation clips look like clips — the same canned smile every time, on
    a face that is otherwise reacting in real time. A vector can be mixed:
    "amused" plus the brow lift the voice is already producing, scaled by how
    emphatic the sentence is. It also makes the behaviour testable: given a tag
    and a sentence, the target vector is exact.

THE GUARD
    `guard()` refuses to let a positive expression through when the sentence
    being spoken is a failure report. An assistant that smiles while saying it
    could not do something is not expressive, it is broken, and this is the one
    mistake in this file that would be genuinely unsettling rather than merely
    ugly.

AMPLITUDES ARE DELIBERATELY SMALL
    Maxima live in `MAX`. A low-poly hologram at full amplitude reads as a mask;
    at a third of it, the same geometry reads as a face. Every tag below is
    scaled to stay under that line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Expression:
    """Facial parameters, each roughly -1..1 (positive = the direction named)."""

    smile: float = 0.0        # mouth corners up; negative turns them down
    brow_raise: float = 0.0   # outer lift — attention, surprise, greeting
    brow_furrow: float = 0.0  # inner pull — concentration, displeasure
    squint: float = 0.0       # lids narrowed — amusement, suspicion, effort
    lid_widen: float = 0.0    # eyes open wider — surprise, alarm
    lip_press: float = 0.0    # lips together — resolve, restraint, apology
    asym: float = 0.0         # one brow higher — wryness, doubt, amusement

    # ── maths ───────────────────────────────────────────────────────────────
    def clamped(self) -> "Expression":
        return Expression(
            smile=_clamp(self.smile),
            brow_raise=_clamp(self.brow_raise),
            brow_furrow=_clamp(self.brow_furrow),
            squint=_clamp(self.squint),
            lid_widen=_clamp(self.lid_widen),
            lip_press=_clamp(self.lip_press),
            asym=_clamp(self.asym),
        )

    def capped(self) -> "Expression":
        """Clamped, then limited to the amplitudes this renderer can carry."""
        c = self.clamped()
        return Expression(
            smile=_clamp(c.smile, -MAX.smile, MAX.smile),
            brow_raise=_clamp(c.brow_raise, -MAX.brow_raise, MAX.brow_raise),
            brow_furrow=_clamp(c.brow_furrow, -MAX.brow_furrow, MAX.brow_furrow),
            squint=_clamp(c.squint, 0.0, MAX.squint),
            lid_widen=_clamp(c.lid_widen, 0.0, MAX.lid_widen),
            lip_press=_clamp(c.lip_press, -MAX.lip_press, MAX.lip_press),
            asym=_clamp(c.asym, -MAX.asym, MAX.asym),
        )

    def blend(self, other: "Expression", t: float) -> "Expression":
        """Linear interpolation toward `other`. t is clamped to 0..1."""
        t = _clamp(float(t), 0.0, 1.0)
        return Expression(
            smile=self.smile + (other.smile - self.smile) * t,
            brow_raise=self.brow_raise + (other.brow_raise - self.brow_raise) * t,
            brow_furrow=self.brow_furrow + (other.brow_furrow - self.brow_furrow) * t,
            squint=self.squint + (other.squint - self.squint) * t,
            lid_widen=self.lid_widen + (other.lid_widen - self.lid_widen) * t,
            lip_press=self.lip_press + (other.lip_press - self.lip_press) * t,
            asym=self.asym + (other.asym - self.asym) * t,
        ).capped()

    def scaled(self, k: float) -> "Expression":
        k = float(k)
        return Expression(
            smile=self.smile * k,
            brow_raise=self.brow_raise * k,
            brow_furrow=self.brow_furrow * k,
            squint=self.squint * k,
            lid_widen=self.lid_widen * k,
            lip_press=self.lip_press * k,
            asym=self.asym * k,
        ).capped()

    def is_neutral(self, tol: float = 0.02) -> bool:
        return all(abs(v) <= tol for v in self.as_tuple())

    def as_tuple(self) -> tuple[float, ...]:
        return (self.smile, self.brow_raise, self.brow_furrow, self.squint,
                self.lid_widen, self.lip_press, self.asym)

    def as_dict(self) -> dict[str, float]:
        return {
            "smile": self.smile, "brow_raise": self.brow_raise,
            "brow_furrow": self.brow_furrow, "squint": self.squint,
            "lid_widen": self.lid_widen, "lip_press": self.lip_press,
            "asym": self.asym,
        }


def _clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if v != v:              # NaN
        return 0.0
    return max(low, min(high, v))


NEUTRAL = Expression()

# The most this renderer should ever be asked for. Beyond these the low-poly
# geometry stops reading as a face.
MAX = Expression(
    smile=0.65, brow_raise=0.90, brow_furrow=0.85,
    squint=0.70, lid_widen=0.50, lip_press=0.55, asym=0.35,
)


# ─────────────────────────────────────────────────────────────────────────────
#  Named expressions
# ─────────────────────────────────────────────────────────────────────────────
TAGS: dict[str, Expression] = {
    "neutral": NEUTRAL,
    "attentive": Expression(brow_raise=0.30, lid_widen=0.10),
    "amused": Expression(smile=0.45, squint=0.30, asym=0.22),
    "pleased": Expression(smile=0.55, squint=0.15, brow_raise=0.15),
    "warm": Expression(smile=0.35, squint=0.18),
    "curious": Expression(brow_raise=0.45, asym=0.18, lid_widen=0.12),
    "concentrating": Expression(brow_furrow=0.50, squint=0.28, lip_press=0.20),
    "thinking": Expression(brow_furrow=0.32, squint=0.22, asym=0.12),
    "concerned": Expression(brow_furrow=0.40, brow_raise=0.22, lip_press=0.30, smile=-0.20),
    "apologetic": Expression(brow_raise=0.28, lip_press=0.35, smile=-0.12),
    "surprised": Expression(brow_raise=0.72, lid_widen=0.45, smile=0.10),
    "reassuring": Expression(smile=0.30, brow_raise=0.20, squint=0.12),
    "serious": Expression(brow_furrow=0.35, lip_press=0.25, squint=0.10),
}

_ALIASES = {
    "happy": "pleased", "glad": "pleased", "smile": "pleased", "smiling": "pleased",
    "friendly": "warm", "kind": "warm", "affectionate": "warm",
    "funny": "amused", "wry": "amused", "playful": "amused", "chuckle": "amused",
    "interested": "curious", "intrigued": "curious", "questioning": "curious",
    "focus": "concentrating", "focused": "concentrating", "working": "concentrating",
    "puzzled": "thinking", "considering": "thinking",
    "worried": "concerned", "sorry": "apologetic", "regretful": "apologetic",
    "surprise": "surprised", "alarmed": "surprised",
    "calm": "reassuring", "soothing": "reassuring", "comforting": "reassuring",
    "stern": "serious", "firm": "serious", "grave": "serious",
    "calm_attentive": "attentive", "listening": "attentive",
}


def from_tag(tag: str) -> Expression:
    """Map a word the model used to a bounded expression. Unknown words are neutral."""
    text = str(tag or "").strip().lower()
    if not text:
        return NEUTRAL
    key = re.sub(r"[^a-z]+", "_", text).strip("_")
    if key in TAGS:
        return TAGS[key].capped()
    if key in _ALIASES:
        return TAGS[_ALIASES[key]].capped()
    # "slightly_amused" / "very concerned": the noun still resolves; magnitude is
    # the caller's business, via `scaled`.
    for word in key.split("_"):
        if word in TAGS:
            return TAGS[word].capped()
        if word in _ALIASES:
            return TAGS[_ALIASES[word]].capped()
    return NEUTRAL


# ─────────────────────────────────────────────────────────────────────────────
#  The guard
# ─────────────────────────────────────────────────────────────────────────────
_PROBLEM_WORDS = (
    "error", "failed", "failure", "cannot", "can't", "could not", "couldn't",
    "unable", "not able", "denied", "refused", "blocked", "warning", "problem",
    "sorry", "apolog", "unavailable", "not found", "no access", "timed out",
    "nothing", "no result", "not there",
    "cancel", "permission", "crash", "broken", "wrong", "unsafe",
)

def looks_like_problem(text: str) -> bool:
    lowered = str(text or "").lower()
    if not lowered:
        return False
    return any(word in lowered for word in _PROBLEM_WORDS)


def guard(expression: Expression, text: str) -> Expression:
    """Suppress a positive face on a sentence that reports a problem.

    Only the positive half is removed; concentration or concern is left alone,
    because those are the correct faces for bad news.
    """
    if not looks_like_problem(text):
        return expression.capped()
    values = expression.as_dict()
    if values["smile"] > 0:
        values["smile"] = -min(0.25, values["smile"] * 0.4)
    values["squint"] *= 0.5
    return Expression(**values).capped()


# ─────────────────────────────────────────────────────────────────────────────
#  Prosody
# ─────────────────────────────────────────────────────────────────────────────
def from_prosody(level: float, variance: float) -> Expression:
    """A small lift from the voice itself, so emphasis reads on the face.

    `level` is the smoothed loudness (0..1), `variance` how much it is moving.
    Both come from audio already being played; this adds no model and no call.
    """
    level = _clamp(level, 0.0, 1.0)
    variance = _clamp(variance, 0.0, 1.0)
    return Expression(
        brow_raise=0.25 * level + 0.20 * variance,
        lip_press=0.10 * (1.0 - level),
        squint=0.08 * variance,
    ).capped()


def combine(*pairs: tuple[Expression, float]) -> Expression:
    """Weighted sum of several sources, capped. Weights need not total 1."""
    total = Expression()
    for expression, weight in pairs:
        if not expression:
            continue
        total = Expression(
            smile=total.smile + expression.smile * weight,
            brow_raise=total.brow_raise + expression.brow_raise * weight,
            brow_furrow=total.brow_furrow + expression.brow_furrow * weight,
            squint=total.squint + expression.squint * weight,
            lid_widen=total.lid_widen + expression.lid_widen * weight,
            lip_press=total.lip_press + expression.lip_press * weight,
            asym=total.asym + expression.asym * weight,
        )
    return total.capped()


def from_state(state: str) -> Expression:
    """A resting face for an app state, so idle is not a blank mask."""
    st = str(state or "").upper()
    if st in ("THINKING", "PROCESSING"):
        return TAGS["thinking"]
    if st in ("LISTENING",):
        return TAGS["attentive"]
    if st in ("SLEEPING", "STANDBY", "OFFLINE"):
        return NEUTRAL
    return NEUTRAL


def with_tag(base: Expression, tag: str, weight: float = 0.65,
             spoken: str = "") -> Expression:
    """The usual mix: the state's resting face plus a tagged expression."""
    tagged = guard(from_tag(tag), spoken)
    return base.blend(combine((base, 1.0 - weight), (tagged, weight)), 1.0)


def replace_fields(expression: Expression, **fields) -> Expression:
    """Tiny convenience so callers do not have to rebuild the dataclass."""
    return replace(expression, **fields).capped()
