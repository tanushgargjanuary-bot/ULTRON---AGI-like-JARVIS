"""plugins/caveman.py — Deterministic token saver in the spirit of the Caveman skill.

Caveman compresses a message into a primitive, filler-free style, so fewer
tokens are spent saying the same thing. This is a deterministic, stdlib
version: a short list of rewrite rules (drop filler, drop articles, collapse
whitespace) applied in order. Nothing is sent to a model, which is the point:
compression should cost nothing.

The token count is an estimate — four characters per token, the same
convention the pipeline engine uses for its history budget. An estimate is
enough to compare two versions of one message; it is not a billing figure.

`run()` returns a short summary and puts the compressed text on screen
through `player.show_content`, because the compressed text itself belongs on
the display, not in the speech.
"""

from __future__ import annotations

import re

from core import failures

PLUGIN = {
    "name": "caveman",
    "description": (
        "Compresses text into a primitive, filler-free style to save tokens, "
        "or estimates how many tokens a message costs. Use it when the user "
        "wants a shorter message, asks to save tokens, or wants a token count "
        "before sending something long to a model."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "compress | estimate | explain",
            },
            "text": {
                "type": "STRING",
                "description": "The text to compress or estimate",
            },
            "aggressive": {
                "type": "boolean",
                "description": "Also phrase-shorten and drop articles",
            },
        },
        "required": ["action"],
    },
    "tier": "ROUTINE",
}

# Filler words dropped in every round. Plain words, not a dictionary of
# abbreviations: the point is removing what carries no meaning.
_FILLER = (
    "just", "really", "very", "actually", "basically", "simply", "quite",
    "literally", "honestly", "obviously", "certainly", "definitely",
)

# Phrases first, longer than single words, so "in order to" is read before
# "order" could be dropped by something else.
_PHRASES = (
    ("in order to", "to"),
    ("at the end of the day", ""),
    ("for all intents and purposes", ""),
    ("please note that", ""),
    ("it is important to", ""),
    ("it is worth noting", ""),
    ("a large number of", "many"),
)


def tokens(text: str) -> int:
    return (len(text) + 3) // 4


def _compress(text: str, aggressive: bool = False) -> str:
    out = str(text or "")
    out = " ".join(out.split())
    low = out.lower()
    for phrase, replacement in _PHRASES:
        if phrase in low:
            out = re.sub(re.escape(phrase), replacement, out, flags=re.IGNORECASE)
    # Drop filler words (kept hyphenated/possessives: "justice" is not "just").
    out = re.sub(r"\b(?:" + "|".join(_FILLER) + r")\b[, ]*", "", out, flags=re.IGNORECASE)
    if aggressive:
        # Drop articles: aggressive mode changes wording, so it is opt-in.
        out = re.sub(r"\b(?:a|an|the)\b +", "", out, flags=re.IGNORECASE)
    out = " ".join(out.split())
    return out.strip(" ,;\n")


def run(parameters: dict, player=None, session_memory=None) -> str:
    action = str(parameters.get("action") or "compress").strip().lower()
    text = str(parameters.get("text") or "")
    try:
        if action == "estimate":
            if not text:
                return "There is nothing to estimate."
            return (f"{len(text)} characters, {len(text.split())} words, "
                    f"about {tokens(text)} tokens.")
        if action == "explain":
            return ("Caveman drops filler words and phrases, collapses extra "
                    "space and, in aggressive mode, drops articles. Token "
                    "counts are estimated at four characters per token.")
        if action == "compress":
            if not text:
                return "There is nothing to compress."
            before = tokens(text)
            compressed = _compress(text, bool(parameters.get("aggressive")))
            after = tokens(compressed)
            saved = max(before - after, 0)
            pct = round(100 * saved / before, 1) if before else 0.0
            if player and hasattr(player, "show_content"):
                try:
                    player.show_content("Caveman output", compressed)
                except Exception as e:
                    failures.note("caveman.show", e)
                return f"{before} tokens down to {after}. Saved {saved} ({pct}%), shown on screen."
            return (f"{before} tokens down to {after}. Saved {saved} ({pct}%). "
                    f"Compressed: {compressed[:200]}")
    except Exception as error:  # noqa: BLE001
        return f"That did not compress: {type(error).__name__}: {error}"
    return "I can compress text, estimate its cost, or explain caveman mode."

