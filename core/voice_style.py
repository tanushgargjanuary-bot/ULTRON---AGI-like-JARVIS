"""core/voice_style.py — make written text survive being spoken.

THE COMPLAINT THIS ANSWERS
    "It still outputs like an LLM." A model writes for a page: bold labels,
    bullet lists, headings, emoji, and openers like "Certainly! Here's a quick
    breakdown:". Printed, that reads fine. Spoken by a voice, it is instantly
    recognisable as a machine reading a document aloud — asterisks pronounced as
    pauses, "dash dash" between items, an emoji swallowed and a sentence that
    starts with "Certainly" before it says anything.

    The prompt already asks for finished sentences. A prompt is a request, not a
    guarantee, and this is the last place the text exists as text, so it is the
    right place to make the guarantee.

WHAT IT DOES NOT DO
    It does not rewrite meaning, summarise, or reorder. It removes the artefacts
    of formatting and converts a list into the sentence a person would have said.
    A number, a path or a name is left exactly as the model wrote it.

WHERE IT APPLIES
    The pipeline engine's text-to-speech path (`providers/engine_pipeline.py`,
    `_speakable`). Gemini Live generates audio natively and never passes through
    here — for that engine the persona in `core/prompt.txt` is the only control,
    and no amount of post-processing can reach inside a waveform.
"""

from __future__ import annotations

import re

# Openers that carry no information and cost a second before the answer.
_PREAMBLE = (
    "certainly", "sure", "of course", "absolutely", "great question",
    "good question", "excellent question", "no problem", "happy to help",
    "i'd be happy to help", "i would be happy to help", "here is", "here's",
    "here you go", "let me", "okay", "alright", "as an ai", "as a language model",
    "as an ai language model", "i'm just an ai", "i am just an ai",
)

_BULLET = re.compile(r"^\s*(?:[-*•·–—]|\d{1,2}[.)])\s+", re.MULTILINE)
_HEADING = re.compile(r"^\s*#{1,6}\s*", re.MULTILINE)
_QUOTE = re.compile(r"^\s*>\s?", re.MULTILINE)
_EMPHASIS = re.compile(r"(\*{1,3}|_{1,3}|~~)(?=\S)(.+?)(?<=\S)\1")
_CODE_TICK = re.compile(r"`{1,3}")
_LINK = re.compile(r"\[([^\]]+)\]\((?:[^)]+)\)")
_RULE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$", re.MULTILINE)
_SPACES = re.compile(r"[ \t]{2,}")
_BLANK_LINES = re.compile(r"\n{2,}")


def strip_markup(text: str) -> str:
    """Remove formatting a voice cannot say, keep the words it can."""
    out = str(text or "")
    out = _CODE_TICK.sub("", out)
    out = _RULE.sub("", out)
    out = _HEADING.sub("", out)
    out = _QUOTE.sub("", out)
    out = _LINK.sub(r"\1", out)
    out = _EMPHASIS.sub(r"\2", out)
    return out


def bullets_to_sentences(text: str) -> str:
    """Turn a bullet list into sentences, because a list cannot be read aloud.

    Each item keeps its own words and gains a full stop if it had none, so the
    result is "Check the drive. Copy the file. Restart." rather than
    "dash check the drive dash copy the file".
    """
    lines = str(text or "").splitlines()
    if not any(_BULLET.match(line) for line in lines):
        return text
    out: list[str] = []
    for line in lines:
        if _BULLET.match(line):
            item = _BULLET.sub("", line).strip()
            if item and item[-1] not in ".!?;:":
                item += "."
            out.append(item)
        else:
            out.append(line)
    # Blank lines between items become nothing: a spoken list has no gaps.
    return "\n".join(line for line in out if line.strip())


def drop_preamble(text: str) -> str:
    """Remove information-free openers, but never the answer with them.

    Iterative on purpose: models stack them ("Sure! Certainly, here you go:"),
    and one pass leaves the second one in front of the sentence.
    """
    out = str(text or "").strip()
    for _ in range(4):
        lowered = out.lower().lstrip("\"'(")
        matched = False
        for phrase in _PREAMBLE:
            if not lowered.startswith(phrase):
                continue
            remainder = out[len(phrase):].lstrip(" ,:;—–-!.\"'")
            # Only drop it when something substantive follows. "Sure." alone is a
            # complete answer and removing it would leave silence.
            if len(remainder.split()) >= 3 or remainder.endswith((".", "!", "?")):
                out = remainder
                matched = True
                break
        if not matched:
            break
    return out.strip()


def spoken(text: str) -> str:
    """The full pass: markup out, list flattened, opener dropped, space tidied."""
    out = strip_markup(text)
    out = bullets_to_sentences(out)
    out = _BLANK_LINES.sub("\n", out)
    out = _SPACES.sub(" ", out)
    out = drop_preamble(out.strip())
    return _SPACES.sub(" ", out).strip()


def is_written_register(text: str) -> bool:
    """True when a reply still looks like a document rather than speech.

    Used by tests and by the HUD to flag output that will sound wrong before it
    is spoken, rather than after.
    """
    raw = str(text or "")
    return bool(
        _BULLET.search(raw)
        or _HEADING.search(raw)
        or _EMPHASIS.search(raw)
        or _CODE_TICK.search(raw)
        or len(raw.splitlines()) > 2
    )
