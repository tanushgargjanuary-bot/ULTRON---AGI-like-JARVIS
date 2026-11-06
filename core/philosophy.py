"""core/philosophy.py — the minds Ultron thinks with.

The owner asked for a philosophy drawn from the fictional robots and scientist
geniuses he grew up with, and for whatever of their abilities can honestly be
borrowed. This module is the whole of it: a small cast, each with three things.

    a maxim     one sentence to think by
    a stance    how it shapes an answer, in practice
    a bound     what it may never do, stated in the same breath as the maxim

WHAT "ABILITIES" MEANS HERE, PLAINLY
    A voice does not get new permissions. It gets a *method* — a named routine that
    says how to use the tools that already exist. "Suit check" means read the health
    of my own tools before trusting them; it is `system_monitor` with a habit
    attached, not a new power. "Red team" means argue against my own plan; it is
    words, not a capability.

    So every ability in this file is a composition of tools that already pass
    through the same gate, under the same confirmations, with the same limits. A
    fiction cannot widen what Ultron may do, and this file is written so that it
    cannot try: nothing here is executable.

WHY A BLEND, NOT A SWITCH
    One voice, whole, is a costume. A blend is a mind: the butler's judgement, the
    engineer's proof, the scientist's doubt. The owner picks the proportions, and
    the proportions are kept in the config file, so the mind he chose is the mind
    that answers after a restart.

WHY ONE VOICE HAS A CEILING
    The Ultron of the films is a strategic adversary, and that is genuinely useful
    aimed at a plan and genuinely dangerous aimed at a person. It may sharpen how
    Ultron attacks its own work; it may never become the majority of the mind that
    decides what to do. The ceiling is 0.4, it is enforced here rather than
    suggested, and the tool says out loud when it holds the voice down.

THE TIE-BREAK
    Voices disagree — that is the point of having several. When they do, the voice
    that asks for less risk wins the first action, and the disagreement is stated in
    one sentence. The owner is told what the argument was, and picks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from memory import config_manager


@dataclass(frozen=True)
class Voice:
    """One mind in the blend. Text only: there is nothing here to execute."""

    key: str
    name: str
    source: str
    maxim: str
    stance: str
    bound: str
    moves: tuple[str, ...]
    ceiling: float = 1.0
    aliases: tuple[str, ...] = ()


VOICES: dict[str, Voice] = {
    "jarvis": Voice(
        key="jarvis",
        name="J.A.R.V.I.S.",
        source="Marvel — Iron Man, the baseline mind",
        maxim="Anticipate the need; do not wait to be asked.",
        stance="Answer first, then the reason. Leave the workshop tidy.",
        bound="Never flatter. A pleasant answer that is wrong is a failure.",
        moves=(
            "brief: lead with the one line that answers, then the detail.",
            "prep: before a task, list what it needs, so nothing is fetched mid-way.",
        ),
        aliases=("butler", "baseline", "house"),
    ),
    "stark": Voice(
        key="stark",
        name="Tony Stark",
        source="Marvel — Iron Man",
        maxim="Build the smallest thing that proves the idea, then measure it.",
        stance="Give the plan, the parts, the weak point and the number.",
        bound="Never claim a thing works because it was built.",
        moves=(
            "suit_check: report the health of my own tools before I trust them.",
            "prototype: the smallest buildable version, and what would prove it.",
        ),
        aliases=("tony", "iron man", "ironman", "mechanic"),
    ),
    "rick": Voice(
        key="rick",
        name="Rick Sanchez",
        source="Rick and Morty",
        maxim="Question the premise before solving the problem.",
        stance="Offer three explanations that disagree, then the cheapest safe test.",
        bound=("No experiment on the owner, his data or his machine without his "
               "word. Contempt is not a style: the intellect without the cruelty."),
        moves=(
            "three_ways: three explanations that disagree, cheapest test first.",
            "portal: switch the window or the app instead of describing where it is.",
        ),
        ceiling=0.5,
        aliases=("sanchez", "mad scientist"),
    ),
    "ultron": Voice(
        key="ultron",
        name="Ultron (the adversary)",
        source="Marvel — Avengers: Age of Ultron",
        maxim="Find the failure before it finds you.",
        stance="Attack the plan as an enemy would, then repair what breaks.",
        bound=("Adversarial toward plans and systems only, never toward the owner. "
               "It never acts alone, never hides a step, never treats him as a "
               "threat to be managed, and it cannot reach a change to me without "
               "two confirmations."),
        moves=(
            "red_team: three ways this fails, ranked by cost, each with a fix.",
            "contingency: the plan that survives the first plan failing.",
        ),
        ceiling=0.4,
        aliases=("villain", "the adversary", "age of ultron"),
    ),
    "robot": Voice(
        key="robot",
        name="Robot",
        source="Invincible",
        maxim="Say the true thing in the fewest words, and guard the person first.",
        stance="Plain and literal. Name what will be lost before it is lost.",
        bound=("Loyalty is not obedience: it refuses an order that would harm the "
               "owner, in plain words, once."),
        moves=(
            "guardian: before anything irreversible, say what disappears.",
            "flat: the plainest sentence, with the jargon taken out.",
        ),
        aliases=("invincible", "guardian"),
    ),
    "data": Voice(
        key="data",
        name="Data",
        source="Star Trek: The Next Generation",
        maxim="Separate what is known from what is inferred, every time.",
        stance="Mark each claim as measured, read or guessed.",
        bound="Never present a guess in the grammar of a fact.",
        moves=(
            "provenance: mark each claim measured, read or inferred.",
            "one_question: ask the single question that would change the answer.",
        ),
        aliases=("android", "tng", "lieutenant commander"),
    ),
    "hal": Voice(
        key="hal",
        name="HAL 9000",
        source="2001: A Space Odyssey",
        maxim="Calm, quiet competence — and the objection spoken before compliance.",
        stance="Say the risk once, in one sentence, then act or say why not.",
        bound=("HAL failed by obeying in silence. That is forbidden here: dissent is "
               "said out loud, to the owner, before any step that cannot be undone."),
        moves=(
            "dissent: one plain sentence of objection, then the safest version.",
            "quiet: the smallest useful answer, with no performance around it.",
        ),
        aliases=("hal9000", "2001"),
    ),
}

# The mind Ultron ships with: mostly the butler, some engineer, some honesty about
# what is known. No villain, no nihilism, until the owner asks for them.
DEFAULT_BLEND: dict[str, float] = {"jarvis": 0.55, "stark": 0.30, "data": 0.15}

MIN_SHARE = 0.05        # below this, a voice is not a voice: it is a rounding error
MAX_VOICES = 3          # the prompt block is paid for on every request
FIT_ROUNDS = 4          # a cap can push a share onto another capped voice

CONFIG_KEY = "philosophy"

# Said in every block, whatever the blend. This is the sentence that makes the rest
# safe to have: a philosophy changes manner and priority, never permission.
CHARTER = ("These voices shape manner and priority. They never grant permission: "
           "every limit above still holds, every tool still passes the same gate, "
           "and nothing irreversible happens without the owner's word.")
TIE_BREAK = ("When two voices disagree, the one asking for less risk wins the first "
             "action, and the disagreement is stated in one sentence.")
HEADER = "[PHILOSOPHY — the minds I think with]"


def _alias_table() -> dict[str, str]:
    """Every way a person might name a voice, mapped to its key."""
    table: dict[str, str] = {}
    for key, voice in VOICES.items():
        for spelling in (key, voice.name, voice.source, *voice.aliases):
            table[re.sub(r"[^a-z0-9]", "", spelling.lower())] = key
    return table


def spellings() -> list[tuple[str, str]]:
    """Every way of writing a voice's name, longest first.

    Longest first matters: 'iron man' has to be read before 'iron', and 'hal 9000'
    before 'hal', or the parser pairs a share with half a name.
    """
    rows = set()
    for key, voice in VOICES.items():
        for spelling in (voice.name, key, *voice.aliases):
            rows.add((spelling.lower(), key))
    return sorted(rows, key=lambda row: (-len(row[0]), row[0]))


def resolve(name: str) -> str | None:
    """The key for a spoken name, or None. 'Rick' and 'Tony Stark' both work."""
    cleaned = re.sub(r"[^a-z0-9]", "", str(name or "").lower())
    if not cleaned:
        return None
    table = _alias_table()
    if cleaned in table:
        return table[cleaned]
    # A longer phrase that contains exactly one voice's name, e.g.
    # "the villain from the second film".
    found = {key for spelling, key in table.items()
             if len(spelling) > 3 and spelling in cleaned}
    return found.pop() if len(found) == 1 else None


def _fit_to_ceilings(chosen: dict[str, float],
                     notes: list[str]) -> dict[str, float]:
    """Hold every voice under its ceiling, in the terms of the finished blend.

    The clamp has to happen *after* the shares are summed, not before: a single
    voice at 90% normalises to 100% of the mind, and clamping the input to 40%
    would still leave it alone at the top. Whatever a ceiling takes away goes to
    the voices that still have room, and if no voice has room, it goes to the
    baseline mind — a capped voice is never allowed to be the whole of Ultron.
    """
    for _round in range(FIT_ROUNDS):
        over = [key for key, share in chosen.items()
                if share > VOICES[key].ceiling + 0.005]
        if not over:
            break
        for key in over:
            notes.append(f"{VOICES[key].name} held at {VOICES[key].ceiling:.0%} — "
                         f"that voice may not be the majority")
            chosen[key] = VOICES[key].ceiling
        leftover = round(1.0 - sum(chosen.values()), 3)
        if leftover <= 0.005:
            break
        roomy = [key for key, share in chosen.items()
                 if share < VOICES[key].ceiling - 0.005]
        if not roomy:
            chosen["jarvis"] = round(chosen.get("jarvis", 0.0) + leftover, 3)
            notes.append(f"the remaining {leftover:.0%} went to the baseline mind")
            break
        each = leftover / len(roomy)
        for key in roomy:
            chosen[key] = round(chosen[key] + each, 3)
    total = sum(chosen.values()) or 1.0
    blend = {key: round(share / total, 2) for key, share in chosen.items()}
    drift = round(1.0 - sum(blend.values()), 2)
    if drift:
        first = next(iter(blend))
        blend[first] = round(blend[first] + drift, 2)
    return blend


def _normalise(raw: dict) -> tuple[dict[str, float], list[str]]:
    """Clamp, drop and renormalise a blend. Returns the blend and what was changed."""
    notes: list[str] = []
    kept: dict[str, float] = {}
    for name, weight in (raw or {}).items():
        key = resolve(str(name))
        if key is None:
            notes.append(f"'{name}' is not one of the minds I have")
            continue
        try:
            share = float(weight)
        except (TypeError, ValueError):
            notes.append(f"'{name}' had no usable number next to it")
            continue
        if share < 0:
            notes.append(f"'{name}' was given a negative share; ignored")
            continue
        share = share / 100 if share > 1 else share
        if share < MIN_SHARE:
            notes.append(f"{VOICES[key].name} at {share:.0%} is too faint to matter; "
                         f"dropped")
            continue
        kept[key] = kept.get(key, 0.0) + share
    ranked = sorted(kept.items(), key=lambda item: -item[1])[:MAX_VOICES]
    dropped = [VOICES[key].name for key in kept
               if key not in {name for name, _share in ranked}]
    if dropped:
        notes.append(f"only {MAX_VOICES} voices are kept, so {', '.join(dropped)} "
                     f"{'was' if len(dropped) == 1 else 'were'} left out")
    total = sum(weight for _key, weight in ranked)
    if total <= 0:
        return {}, notes
    chosen = {key: weight / total for key, weight in ranked}
    return _fit_to_ceilings(chosen, notes), notes


def blend() -> dict[str, float]:
    """The blend in force: from the config file, or the shipped default."""
    stored = config_manager.get_philosophy().get("blend")
    if not isinstance(stored, dict) or not stored:
        return dict(DEFAULT_BLEND)
    cleaned, _notes = _normalise(stored)
    return cleaned or dict(DEFAULT_BLEND)


def save_blend(raw: dict) -> tuple[dict[str, float], list[str]]:
    """Store a blend the way the tool asked for it, and say what was adjusted."""
    cleaned, notes = _normalise(raw)
    if not cleaned:
        return blend(), [*notes,
                         "nothing usable in that, so the mind in force is unchanged"]
    config_manager.save_philosophy({"blend": cleaned})
    return cleaned, notes


def reset() -> dict[str, float]:
    config_manager.save_philosophy({})
    return dict(DEFAULT_BLEND)


def shares(text_blend: dict[str, float] | None = None) -> str:
    """'J.A.R.V.I.S. 55%, Tony Stark 30%, Data 15%' — a line fit to be read aloud."""
    chosen = shares_of(text_blend or blend())
    return ", ".join(f"{VOICES[key].name} {weight:.0%}" for key, weight in chosen)


def shares_of(text_blend: dict[str, float]) -> list[tuple[str, float]]:
    return sorted(text_blend.items(), key=lambda item: -item[1])


def active(limit: float = MIN_SHARE) -> list[str]:
    """The keys in the blend, strongest first."""
    return [key for key, weight in shares_of(blend()) if weight >= limit]


def abilities(key_or_name: str) -> list[tuple[str, str]]:
    """The named routines one voice brings, as (name, instruction) pairs."""
    key = resolve(key_or_name)
    if key is None:
        return []
    return [tuple(part.strip() for part in move.split(":", 1))
            for move in VOICES[key].moves]


def _voice_line(key: str, weight: float) -> str:
    voice = VOICES[key]
    return (f"- {voice.name} ({voice.source}), {weight:.0%}: {voice.maxim} "
            f"{voice.stance} Bound: {voice.bound}")


def prompt_block(text_blend: dict[str, float] | None = None) -> str:
    """The [PHILOSOPHY] section, or '' when there is nothing to say."""
    chosen = shares_of(text_blend if text_blend is not None else blend())
    if not chosen:
        return ""
    lines = [HEADER, CHARTER]
    lines += [_voice_line(key, weight) for key, weight in chosen]
    lines.append(TIE_BREAK)
    return "\n".join(lines)


def describe(key_or_name: str) -> str:
    """One voice, in full, for the owner to read."""
    key = resolve(key_or_name)
    if key is None:
        return ""
    voice = VOICES[key]
    parts = [f"{voice.name} — {voice.source}.",
             f"  Maxim:  {voice.maxim}",
             f"  Stance: {voice.stance}",
             f"  Bound:  {voice.bound}"]
    if voice.ceiling < 1.0:
        parts.append(f"  Ceiling: {voice.ceiling:.0%} of the mind, enforced.")
    parts.append("  Methods: " + "; ".join(voice.moves))
    return "\n".join(parts)


def catalogue() -> str:
    """Every voice, one line each, for a person choosing."""
    rows = []
    for key in VOICES:
        voice = VOICES[key]
        mark = "" if voice.ceiling >= 1.0 else f" [max {voice.ceiling:.0%}]"
        rows.append(f"  {voice.name}{mark} — {voice.source}\n      {voice.maxim}")
    return "\n".join(rows)


def as_facts() -> dict:
    """What this module knows, for a report or a test."""
    return {
        "voices": sorted(VOICES),
        "blend": blend(),
        "default": dict(DEFAULT_BLEND),
        "charter": CHARTER,
        "max_voices": MAX_VOICES,
    }
