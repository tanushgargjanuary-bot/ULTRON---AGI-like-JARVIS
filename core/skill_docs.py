"""core/skill_docs.py - the written skills under `skills/`, made readable.

The folder `skills/<name>/SKILL.md` has existed for a while and nothing loaded
it, so the guidance in those files was decoration: present in the repository,
absent from the conversation. This module is the missing reader.

A skill document is plain Markdown with a small frontmatter block:

    ---
    name: computer-use
    description: One line saying when this skill applies.
    ---
    ...the body...

Two rules keep it safe and cheap:

- **A document is text, never code.** Nothing here imports, executes or shells
  out. The worst a bad document can do is read badly.
- **A document is bounded.** Only `skills/<simple-name>/SKILL.md` is reachable,
  never a path with `..`, a drive letter or a symlink out of the folder. Reads
  stop at `MAX_CHARS`, because a skill is context, and context is the budget.

`custom_jarvis/skills.py` is the other half of the same idea: those are recipes
of read-only tool calls, and these are the words that explain when to use them.
A doc never grants a capability; it only tells the model how to use one it has.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "SkillDoc",
    "DEFAULT_ROOT",
    "MAX_CHARS",
    "index",
    "read",
    "brief",
    "problems",
]

DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "skills"
MAX_CHARS = 12_000
MAX_FILE_BYTES = 64_000
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class SkillDoc:
    """One document: what it is called, when it applies, and how big it is."""

    name: str
    description: str
    path: Path
    chars: int

    def line(self) -> str:
        """One compact index line, the form a prompt can afford."""
        return f"{self.name}: {self.description}"


def _root(root: Path | None = None) -> Path:
    return Path(root) if root is not None else DEFAULT_ROOT


def _parse(text: str) -> tuple[str, str, str]:
    """(name, description, body) from a document. Missing frontmatter is fine."""
    name = description = ""
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            header = text[3:end]
            body = text[end + 4:]
            for line in header.splitlines():
                key, _, value = line.partition(":")
                key = key.strip().lower()
                value = value.strip().strip('"').strip("'")
                if key == "name" and not name:
                    name = value
                elif key == "description" and not description:
                    description = value
    if not description:
        # No frontmatter: the first non-empty prose line is the honest fallback.
        for line in body.splitlines():
            stripped = line.strip().lstrip("#").strip()
            if stripped:
                description = stripped[:160]
                break
    return name, description, body


def index(root: Path | None = None) -> list[SkillDoc]:
    """Every readable skill document, sorted by name. Never raises."""
    base = _root(root)
    if not base.is_dir():
        return []
    found: list[SkillDoc] = []
    for folder in sorted(base.iterdir()):
        if not folder.is_dir() or not _SAFE_NAME.match(folder.name):
            continue
        path = folder / "SKILL.md"
        if not path.is_file():
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        declared, description, _body = _parse(text)
        name = declared if _SAFE_NAME.match(declared) else folder.name
        found.append(SkillDoc(name=name, description=description or "(no description)",
                              path=path, chars=len(text)))
    return found


def read(name: str, root: Path | None = None) -> str:
    """The document's text, bounded. Raises ValueError for an unusable name."""
    wanted = (name or "").strip()
    for doc in index(root):
        if doc.name == wanted or doc.path.parent.name == wanted:
            text = doc.path.read_text(encoding="utf-8", errors="replace")
            if len(text) > MAX_CHARS:
                return text[:MAX_CHARS] + "\n\n[truncated - the document is longer]"
            return text
    raise ValueError(f"No skill document named {wanted!r}.")


def brief(limit: int = 20, root: Path | None = None) -> str:
    """Index lines for a prompt, capped. Empty when there are no documents."""
    docs = index(root)[:max(0, limit)]
    return "\n".join(doc.line() for doc in docs)


def problems(root: Path | None = None) -> list[str]:
    """Why a folder that looks like a skill is not one. For tests and audits."""
    base = _root(root)
    if not base.is_dir():
        return [f"no skills folder at {base}"]
    out: list[str] = []
    for folder in sorted(base.iterdir()):
        if not folder.is_dir():
            continue
        if not _SAFE_NAME.match(folder.name):
            out.append(f"{folder.name}: folder name is not a usable skill id")
            continue
        path = folder / "SKILL.md"
        if not path.is_file():
            out.append(f"{folder.name}: no SKILL.md")
            continue
        try:
            size = path.stat().st_size
        except OSError as exc:
            out.append(f"{folder.name}: cannot stat SKILL.md ({exc})")
            continue
        if size > MAX_FILE_BYTES:
            out.append(f"{folder.name}: SKILL.md is {size} bytes, over the limit")
    return out
