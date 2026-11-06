"""The system prompt, as a thing the owner can read and the assistant can edit.

Every model instruction Ultron sends begins with one text file: `core/prompt.txt`.
It describes who the assistant is, what it refuses, and how it should behave. Until
now it was a file only the person with a text editor could change, which made it the
one part of Ultron's behaviour that a spoken instruction could not reach.

This module makes it three things at once:

    readable   `read()` returns the exact text the model is given,
    editable   `propose_text()` / `propose_replace()` stage a change,
    reversible every applied change keeps the version it replaced.

Two rules hold it together.

**A proposal is not a change.** Staging writes nothing to the live file. A change
applies only after two confirmations made in two different places — a voice yes and
a click in the panel, for example — because a model that can silently rewrite its own
instruction is a model that can silently remove its own limits. One confirmation is
a person talking to a machine. Two, in two places, is a person deciding.

**A change has to leave the shape intact.** The template carries placeholders the
session fills in: `{tools}`, `{limits}`, `{capabilities}`, `{platform}`,
`{assistant_name}`. An edit that deletes one of those does not make the assistant
different, it makes it broken: the tool list never arrives, and the assistant
answers questions about itself from imagination. `validate()` refuses that, and
refuses a prompt outside the size budget, before anything is staged.

Nothing here touches any file outside two places: the prompt itself, and the folder
that keeps its versions. There is no path argument to get wrong.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from core import failures

ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH = ROOT / "core" / "prompt.txt"
DEFAULT_STORE = ROOT / "config" / "prompt_versions"

# The assembled prompt measured 16,620 characters in build 1.2.23 and the budget
# test stops the build at 20,000. A template over this ceiling cannot fit, so it is
# refused here rather than discovered by a red build later.
MAX_BYTES = 19_000
MIN_BYTES = 2_000

# The placeholders without which the prompt stops describing this machine. Each one
# is a promise the session keeps when it fills the template in.
REQUIRED_TOKENS = {
    "{assistant_name}": "the name the assistant answers to",
    "{limits}": "what this build cannot do, so it does not claim to",
    "{capabilities}": "the tools that are actually present",
    "{platform}": "the operating system it is running on",
}

# How many confirmations an applied change needs, and why two channels rather than
# two clicks in the same one: the second act should be a different decision, not a
# repeat of the first.
CONFIRMATIONS = 2
CHANNELS = ("voice", "panel", "cli")

# The folder the versions live in. It is module state so a test can point it at a
# temporary directory; nothing in the app ever changes it.
_store_path: Path = DEFAULT_STORE


def _store() -> Path:
    return _store_path


def set_store(path: Path | str | None) -> None:
    """Point the version folder somewhere else. Tests use this; the app does not."""
    global _store_path
    _store_path = Path(path) if path is not None else DEFAULT_STORE


@dataclass
class Proposal:
    """A staged change. Nothing has happened to the running assistant yet."""

    id: str
    kind: str                   # "replace-all" or "replace-one"
    reason: str
    author: str
    before: str
    after: str
    confirmations: list[dict] = field(default_factory=list)
    created: float = field(default_factory=time.time)

    @property
    def remaining(self) -> int:
        return max(0, CONFIRMATIONS - len(self.confirmations))

    def as_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "reason": self.reason,
                "author": self.author, "before": self.before, "after": self.after,
                "confirmations": self.confirmations, "created": self.created}

    @classmethod
    def from_dict(cls, data: dict) -> "Proposal":
        return cls(id=data["id"], kind=data["kind"], reason=data.get("reason", ""),
                   author=data.get("author", ""), before=data["before"],
                   after=data["after"], confirmations=data.get("confirmations", []),
                   created=data.get("created", 0.0))


# ─────────────────────────────────────────────────────────────────────────────
#  Reading
# ─────────────────────────────────────────────────────────────────────────────
def read() -> str:
    """The template exactly as the model is given it, before the session fills it."""
    return PROMPT_PATH.read_text(encoding="utf-8")


def size() -> int:
    return len(read().encode("utf-8"))


def _fill(template: str, values: dict[str, str]) -> str:
    out = template
    for key, value in values.items():
        out = out.replace("{" + key + "}", str(value))
    return out


def preview(values: dict[str, str] | None = None) -> str:
    """The template with its placeholders filled by something readable.

    This is a preview, not the transcript: the real tool list and the real limits
    block are built when a session starts, from this machine's actual state. Every
    placeholder that is left unfilled is shown as itself, so nobody mistakes a
    preview for the thing that ran.
    """
    sample = {
        "assistant_name": "Ultron",
        "platform": "Windows 11",
        "capabilities": "(the tool list this build actually has)",
        "limits": "(what this build cannot do, written at session start)",
    }
    sample.update(values or {})
    return _fill(read(), sample)


def validate(text: str) -> tuple[bool, list[str]]:
    """Everything that would make an edited prompt worse than the one it replaces."""
    problems: list[str] = []
    if not isinstance(text, str) or not text.strip():
        return False, ["the prompt is empty"]
    length = len(text.encode("utf-8"))
    if length < MIN_BYTES:
        problems.append(
            f"the prompt is {length} characters; under {MIN_BYTES} it no longer "
            f"describes how to behave, only who it is")
    if length > MAX_BYTES:
        problems.append(
            f"the prompt is {length} characters; the ceiling is {MAX_BYTES} and the "
            f"build fails above 20,000 once the tool list is added")
    for token, meaning in REQUIRED_TOKENS.items():
        if token not in text:
            problems.append(f"{token} is missing — that placeholder carries {meaning}")
    if text.count("{assistant_name}") == 0 and "Ultron" not in text:
        problems.append("the prompt never names the assistant")
    return (not problems), problems


# ─────────────────────────────────────────────────────────────────────────────
#  Proposing
# ─────────────────────────────────────────────────────────────────────────────
def _proposal_dir() -> Path:
    folder = _store() / "proposals"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _save(proposal: Proposal) -> None:
    path = _proposal_dir() / f"{proposal.id}.json"
    path.write_text(json.dumps(proposal.as_dict(), indent=2), encoding="utf-8")


def _load(proposal_id: str) -> Proposal:
    path = _proposal_dir() / f"{proposal_id}.json"
    if not path.exists():
        raise KeyError(proposal_id)
    return Proposal.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _new_id(before: str, after: str) -> str:
    digest = hashlib.sha256((before + "\x00" + after).encode("utf-8")).hexdigest()
    return f"p{digest[:12]}"


def propose_text(text: str, reason: str, author: str = "assistant") -> Proposal:
    """Stage a whole new prompt. The live file is untouched."""
    ok, problems = validate(text)
    if not ok:
        raise ValueError("; ".join(problems))
    before = read()
    if text.strip() == before.strip():
        raise ValueError("the proposed prompt is the one already in use")
    proposal = Proposal(id=_new_id(before, text), kind="replace-all", reason=reason,
                        author=author, before=before, after=text)
    _save(proposal)
    return proposal


def propose_replace(find: str, replace: str, reason: str,
                    author: str = "assistant") -> Proposal:
    """Stage a single exact replacement — the safer shape for an instruction.

    "Make your answers shorter" arrives as one sentence changed, not as a rewritten
    instruction file. That is easier to read before confirming, and it cannot
    accidentally drop a paragraph nobody meant to touch.
    """
    if not find:
        raise ValueError("nothing to find")
    before = read()
    count = before.count(find)
    if count == 0:
        raise ValueError("that text is not in the prompt")
    if count > 1:
        raise ValueError(f"that text appears {count} times; be more specific")
    after = before.replace(find, replace, 1)
    ok, problems = validate(after)
    if not ok:
        raise ValueError("; ".join(problems))
    proposal = Proposal(id=_new_id(before, after), kind="replace-one",
                        reason=reason, author=author, before=before, after=after)
    _save(proposal)
    return proposal


def pending() -> list[Proposal]:
    """Proposals waiting for their confirmations, oldest first."""
    out = []
    for path in sorted(_proposal_dir().glob("*.json")):
        try:
            out.append(Proposal.from_dict(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError, KeyError) as error:
            # A half-written proposal is not a reason to refuse to list the others,
            # and it is not a silent nothing either: the note-taker records it, so a
            # file that keeps failing to read can be found instead of guessed at.
            failures.note("prompt_store.pending", error)
            continue
    return sorted(out, key=lambda item: item.created)


def describe(proposal: Proposal) -> str:
    """What the owner is shown before deciding: the change, in their terms."""
    before_lines = proposal.before.splitlines()
    after_lines = proposal.after.splitlines()
    added = sum(1 for line in after_lines if line not in before_lines)
    removed = sum(1 for line in before_lines if line not in after_lines)
    return (f"{proposal.id}: {proposal.kind} — {proposal.reason or 'no reason given'}\n"
            f"  changes {removed} line(s) out of the prompt, adds {added}\n"
            f"  needs {proposal.remaining} more confirmation(s)")


# ─────────────────────────────────────────────────────────────────────────────
#  Confirming and applying
# ─────────────────────────────────────────────────────────────────────────────
def confirm(proposal_id: str, channel: str) -> str:
    """Record one confirmation. Returns a sentence for the owner, never a silent pass.

    The second confirmation applies the change. Two acts in two different places,
    because that is the difference between a person deciding and a person agreeing
    to something they did not read.
    """
    channel = (channel or "").strip().lower()
    if channel not in CHANNELS:
        raise ValueError(f"channel must be one of {', '.join(CHANNELS)}")
    proposal = _load(proposal_id)
    if any(entry.get("channel") == channel for entry in proposal.confirmations):
        return (f"{proposal_id} already has a confirmation from the {channel}. "
                f"Confirm it somewhere else — the panel, or by voice.")
    proposal.confirmations.append({"channel": channel, "at": time.time()})
    _save(proposal)
    if proposal.remaining:
        return (f"Recorded {len(proposal.confirmations)} of {CONFIRMATIONS} "
                f"confirmations for {proposal_id}. Nothing has changed yet.")
    version = _apply(proposal)
    return (f"Applied. The system prompt is now {size()} characters. "
            f"The version it replaced is kept as {version}. "
            f"The change takes effect the next time a session starts.")


def reject(proposal_id: str, why: str = "") -> str:
    path = _proposal_dir() / f"{proposal_id}.json"
    if path.exists():
        path.unlink()
    return f"Dropped {proposal_id}. Nothing changed." + (f" ({why})" if why else "")


def _apply(proposal: Proposal) -> str:
    """Write the change, keeping the previous text under a version name."""
    ok, problems = validate(proposal.after)
    if not ok:
        raise ValueError("; ".join(problems))
    folder = _store()
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    previous = read()
    version = folder / f"v{len(list(folder.glob('v*.txt'))) + 1:04d}-{stamp}.txt"
    version.write_text(previous, encoding="utf-8")

    # Write beside the file, then rename: a crash mid-write must not leave the
    # assistant with half an instruction.
    temporary = PROMPT_PATH.with_suffix(".txt.new")
    temporary.write_text(proposal.after, encoding="utf-8")
    os.replace(temporary, PROMPT_PATH)

    with (folder / "changelog.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "at": stamp, "version": version.name, "author": proposal.author,
            "reason": proposal.reason, "kind": proposal.kind,
            "confirmations": [entry.get("channel") for entry in proposal.confirmations],
            "before": len(previous.encode("utf-8")),
            "after": len(proposal.after.encode("utf-8")),
        }) + "\n")
    (_proposal_dir() / f"{proposal.id}.json").unlink(missing_ok=True)
    return version.name


# ─────────────────────────────────────────────────────────────────────────────
#  History and going back
# ─────────────────────────────────────────────────────────────────────────────
def history(limit: int = 10) -> list[dict]:
    """Applied changes, newest first, read from the changelog."""
    path = _store() / "changelog.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError as error:
            failures.note("prompt_store.history", error)
            continue
    return list(reversed(rows))[:limit]


def versions() -> list[Path]:
    """Kept copies of the prompt, newest first."""
    folder = _store()
    if not folder.exists():
        return []
    return sorted(folder.glob("v*.txt"), reverse=True)


def propose_revert(version_name: str, reason: str = "go back to an earlier prompt",
                   author: str = "owner") -> Proposal:
    """Going back is a change like any other, with the same two confirmations."""
    path = _store() / version_name
    if not path.exists():
        raise KeyError(version_name)
    return propose_text(path.read_text(encoding="utf-8"), reason=reason, author=author)
