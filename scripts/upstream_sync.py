#!/usr/bin/env python3
"""Compare upstream Mark with Ultron and say, in plain words, what moved and what needs a decision.

Ultron began as a copy of FatihMakes' MARK (CC BY-NC 4.0). It is not a GitHub fork, so there is no
shared history for git to merge. `docs/upstream/PIN.json` records the upstream commit the copy came
from (the base) and the newest drop a person has reviewed. This script fetches upstream, compares three
versions of every file that changed (upstream when we copied, Ultron now, upstream now) and sorts them
into kinds a person can act on. Line endings are ignored: upstream's files use CRLF, Ultron's use LF.

It never edits the repository, never pushes and never merges. Taking anything from upstream is a
separate, reviewed change (`DECISIONS.md` section 8, `docs/UPSTREAM_SYNC.md`).

    python scripts/upstream_sync.py check                          # what moved since the last reviewed drop
    python scripts/upstream_sync.py check --full                   # everything since the copy
    python scripts/upstream_sync.py check --markdown r.md --json r.json
    python scripts/upstream_sync.py check --upstream ../Mark-LVII  # a local clone instead of GitHub
    python scripts/upstream_sync.py pin                            # the PIN.json block for upstream's head

Exit status: 0 upstream has not moved past the reviewed drop; 10 it moved; 20 it moved and a
stop-and-ask gate tripped (a licence or requirements change, rewritten history, a file that steers
agents or models); 2 the check could not be made. A check that cannot run has not passed. Any other
number is a crash in this script. One Python file that cannot be parsed is named in the report's notes
and does not stop it.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "upstream"

EXIT_SAME, EXIT_MOVED, EXIT_STOP, EXIT_ERROR = 0, 10, 20, 2
DISPOSITIONS = ("ours", "take", "merge", "later", "parked", "rejected")
GUARD_KINDS = ("test", "tripwire")
FULL_SHA = re.compile(r"[0-9a-f]{40}")
LIST_LIMIT = 12
ISSUE_LIMIT = 60000
VERSION_LIMIT = 60
# Loaded by name or by globbing a folder, so no import statement names them.
ENTRY_PACKAGES = {"actions", "plugins", "providers"}

# What each kind means, in the words the report uses. The order is the order of the report: the kinds
# that need a person come first.
KINDS = {
    "COLLIDES": "both sides changed the same place",
    "NAME_CLASH": "upstream added a file whose name Ultron already uses for something else",
    "DELETED_EDITED": "upstream deleted a file Ultron has changed",
    "MERGES": "both sides changed the file, in different places (the text merges; it still needs tests)",
    "TAKE": "only upstream changed it, so the change applies as it is",
    "NEW": "upstream added it and Ultron has nothing of that name",
    "OURS_GONE": "upstream changed a file Ultron no longer has",
    "DELETED_CLEAN": "upstream deleted a file Ultron never changed",
    "LINE_ENDINGS": "only the line endings changed",
    "SAME": "Ultron already has this version",
    "UNCHANGED": "identical to the version Ultron was copied from",
    "ALREADY_GONE": "deleted upstream, and Ultron does not have it either",
}
QUIET = {"LINE_ENDINGS", "SAME", "UNCHANGED", "ALREADY_GONE"}

# Files whose edits steer agents or models, or the rules and the licence. Upstream's version of these is
# read, never applied; a change to one of them always needs a person to look.
STEERING = (
    "AGENTS.md", "DECISIONS.md", "WORKING-PHILOSOPHY.md", "GATEKEEPERS.md", "LICENSE", "core/prompt.txt",
    "core/policy.py", "core/confirm.py", "core/self_change.py", "core/boot_guard.py",
    "core/ast_guardian.py", "scripts/proof_gate.py", "scripts/bootstrap.py", "run.bat", "run.ps1",
    ".github/*",
)

# New capabilities in upstream's added lines. A pointer for the reader, not a verdict.
RISKS = {
    "opens network connections": r"\bsocket\.|urllib\.request|urlopen\(|requests\.(?:get|post|put|delete)\(|httpx\.",
    "listens for connections": r"HTTPServer\(|\.listen\(|\.bind\(|uvicorn\.run",
    "runs other programs": r"\bsubprocess\.|os\.system\(|\bPopen\(",
    "deploys over SSH": r"\b(?:ssh|scp)\b[\"',\s]",
    "installs packages": r"-m[\"',\s]+pip\b|pip\.main|ensurepip|[\"']pip[\"'],\s*[\"']install[\"']",
    "uses the Windows registry": r"\bwinreg\b",
}
BRAND = re.compile(r"JARVIS|Jarvis|J\.A\.R\.V\.I\.S|MARK L[IVX]+|Mark L[IVX]+")
TOOL_NAME = re.compile(r'^\s*"name":\s*"([a-z][a-z0-9_]*)"', re.MULTILINE)
TITLE = re.compile(r"MARK\s+([IVXLCDM]+)\s*\((\d+)\)")


class CannotRun(RuntimeError):
    """The comparison could not be made. That is exit 2: a check that cannot run has not passed."""


class Unreadable(ValueError):
    """A Python file that cannot be parsed. One strange file in upstream must not stop the whole report."""


@dataclass
class FileChange:
    path: str
    kind: str
    decision: str = "held"          # the ledger's word for this file, or "held" when it has none
    reason: str = ""
    lines_before: int = 0
    lines_after: int = 0
    restructured: bool = False
    excluded: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    brand: int = 0
    tool: str = ""
    unwired: bool = False


@dataclass
class Context:
    clone: Path
    root: Path
    pin: dict
    ledger: dict
    exclusions: dict
    new_sha: str


# ------------------------------------------------------------------ the three data files

def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise CannotRun(f"cannot read {path}: {error}") from error
    if not isinstance(data, dict):
        raise CannotRun(f"{path} must hold one JSON object")
    return data


def need(data: object, where: str, *keys: str) -> None:
    if not isinstance(data, dict):
        raise CannotRun(f"{where} must be a JSON object")
    missing = [key for key in keys if key not in data]
    if missing:
        raise CannotRun(f"{where} is missing {', '.join(missing)}")


def check_pin(pin: dict) -> dict:
    need(pin, "PIN.json", "upstream", "base_sha", "reviewed")
    need(pin["upstream"], "PIN.json upstream", "repo_id", "name", "url")
    need(pin["reviewed"], "PIN.json reviewed", "sha", "version", "licence_sha256", "requirements_sha256")
    for sha in (pin["base_sha"], pin["reviewed"]["sha"]):
        if not FULL_SHA.fullmatch(str(sha)):
            raise CannotRun(f"PIN.json holds {sha!r}, which is not a full commit id")
    return pin


def check_ledger(ledger: dict) -> dict:
    need(ledger, "LEDGER.json", "entries")
    if not isinstance(ledger["entries"], list):
        raise CannotRun("LEDGER.json entries must be a list")
    for number, entry in enumerate(ledger["entries"], 1):
        where = f"LEDGER.json entry {number}"
        need(entry, where, "paths", "disposition", "reason")
        paths = entry["paths"]        # a bare string would be read letter by letter, and a number would crash
        if not isinstance(paths, list) or not paths or not all(isinstance(item, str) and item for item in paths):
            raise CannotRun(f"{where} needs a list of path patterns")
        if entry["disposition"] not in DISPOSITIONS:
            raise CannotRun(f"{where}: {entry['disposition']!r} is not one of {', '.join(DISPOSITIONS)}")
        if not str(entry["reason"]).strip():
            raise CannotRun(f"{where} has no reason; a decision without one is not a record")
        if "reconciled" in entry and not FULL_SHA.fullmatch(str(entry["reconciled"])):
            raise CannotRun(f"{where}: reconciled must be a full commit id")
    return ledger


def check_exclusions(data: dict) -> dict:
    need(data, "EXCLUSIONS.json", "exclusions")
    if not isinstance(data["exclusions"], list):
        raise CannotRun("EXCLUSIONS.json exclusions must be a list")
    seen: set[str] = set()
    for item in data["exclusions"]:
        need(item, "an exclusion", "id", "name", "rule", "needles", "guard")
        where = f"exclusion {item['id']}"
        if item["id"] in seen:
            raise CannotRun(f"{where} appears twice")
        seen.add(item["id"])
        need(item["guard"], f"{where} guard", "kind")
        if item["guard"]["kind"] not in GUARD_KINDS:
            raise CannotRun(f"{where}: guard kind must be one of {', '.join(GUARD_KINDS)}")
        if not isinstance(item["needles"], list) or not item["needles"]:
            raise CannotRun(f"{where} needs a list of needles, or nothing could ever notice it coming back")
        for needle in item["needles"]:
            if not isinstance(needle, str):
                raise CannotRun(f"{where}: every needle must be text")
            try:
                re.compile(needle)
            except re.error as error:
                raise CannotRun(f"{where}: needle {needle!r} is not a regular expression ({error})") from error
    return data


def load_data(folder: Path) -> tuple[dict, dict, dict]:
    pin = check_pin(read_json(folder / "PIN.json"))
    ledger = check_ledger(read_json(folder / "LEDGER.json"))
    exclusions = check_exclusions(read_json(folder / "EXCLUSIONS.json"))
    return pin, ledger, exclusions


# ------------------------------------------------------------------ git, and where upstream comes from

def run(command: list[str], cwd: Path, timeout: int = 120) -> subprocess.CompletedProcess:
    try:
        # S603: every command here is a fixed git argument list, never a shell string
        return subprocess.run(command, cwd=cwd, capture_output=True, timeout=timeout, check=False)  # noqa: S603
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CannotRun(f"could not run {command[0]!r}: {error}") from error


def text_of(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace").strip()


def git(clone: Path, *args: str) -> bytes:
    done = run(["git", *args], clone)
    if done.returncode != 0:
        raise CannotRun(f"git {' '.join(args)} failed: {text_of(done.stderr)[:300]}")
    return done.stdout


def blob(clone: Path, rev: str, path: str) -> bytes | None:
    """The file's bytes at that commit, or None when the commit has no file of that name (a folder is not one).

    A git failure is not "no such file": a commit that is missing or a repository that is broken raises
    CannotRun. Reading either as absence once made every file look new.
    """
    done = run(["git", "cat-file", "blob", f"{rev}:{path}"], clone)
    if done.returncode == 0:
        return done.stdout
    listing = git(clone, "ls-tree", "-z", rev, "--", path)        # fails loudly when the commit or the repository is bad
    entry = listing.split(b"\t", 1)[0].split()
    if len(entry) == 3 and entry[1] == b"blob":
        raise CannotRun(f"git could not read {path} at {rev[:12]}: {text_of(done.stderr)[:200]}")
    return None


def has_commit(clone: Path, sha: str) -> bool:
    return run(["git", "cat-file", "-e", f"{sha}^{{commit}}"], clone).returncode == 0


def fetch_upstream(source: str, folder: Path) -> Path:
    target = folder / "upstream"
    done = run(["git", "-c", "core.autocrlf=false", "clone", "--quiet", "--", source, str(target)], folder, 300)
    if done.returncode != 0:
        raise CannotRun(f"could not fetch upstream from {source}: {text_of(done.stderr)[:300]}")
    return target


def asked_github(repo_id: int) -> tuple[dict | None, str]:
    """What GitHub calls the upstream repository now, asked by its number so a rename cannot hide it."""
    command = ["gh", "api", f"repositories/{repo_id}", "--jq", "{name: .full_name, url: .clone_url}"]
    try:
        done = subprocess.run(command, capture_output=True, timeout=30, check=False)  # noqa: S603 - fixed arguments
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, f"gh could not be run ({error})"
    if done.returncode != 0:
        return None, f"gh said: {text_of(done.stderr)[:120]}"
    try:
        found = json.loads(done.stdout)
    except ValueError:
        return None, "gh printed something that is not JSON"
    if isinstance(found, dict) and found.get("url"):
        return found, ""
    return None, "gh did not name the repository"


def choose_source(args: argparse.Namespace, pin: dict) -> tuple[str, dict, list[str]]:
    """Where to clone from, what GitHub calls the repository now, and anything worth saying about it."""
    if args.upstream:
        local = Path(args.upstream)
        return (str(local.resolve()) if local.exists() else args.upstream), {}, []
    if args.no_api:
        return pin["upstream"]["url"], {}, ["The repository's current name was not checked (--no-api)."]
    found, why = asked_github(pin["upstream"]["repo_id"])
    if found:
        return found["url"], found, []
    return pin["upstream"]["url"], {}, [f"Could not ask GitHub what the repository is called now ({why}); used the pinned address."]


def rename_notes(found: dict, pin: dict) -> list[str]:
    if found and found.get("name") != pin["upstream"]["name"]:
        return [f"The upstream repository was renamed: {pin['upstream']['name']} is now {found.get('name')}. "
                "That is how a new Mark is published (the same repository under a new name)."]
    return []


# ------------------------------------------------------------------ the three versions of a file

def plain(data: bytes | None) -> bytes | None:
    return None if data is None else data.replace(b"\r\n", b"\n")


def is_text(data: bytes) -> bool:
    return b"\0" not in data[:8192]


def count_lines(data: bytes | None) -> int:
    if not data:
        return 0
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)


def safe_path(path: str) -> bool:
    """True for a name that is an ordinary relative path on every system this runs on.

    Git accepts names that Windows reads as something else: `a\\..\\b` climbs out of its folder, `C:x` is on another
    drive, `x.txt:stream` is a hidden stream of another file. U+FFFD is what a name that is not valid UTF-8 turns
    into when it is read here, and it cannot be looked up again. A name that fails is left out, and the report says so.
    """
    if any(char in path for char in ("\\", ":", "\0", "\ufffd")):
        return False
    posix = PurePosixPath(path)
    return bool(posix.parts) and not posix.is_absolute() and ".." not in posix.parts


def read_ours(root: Path, path: str) -> bytes | None:
    target = root / path
    return target.read_bytes() if target.is_file() else None


def merge_conflicts(ours: bytes, base: bytes, theirs: bytes) -> int:
    """How many places git cannot merge, with no shared history: the base is given explicitly."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        names = []
        for label, data in (("ours", ours), ("base", base), ("theirs", theirs)):
            target = Path(folder, label)
            target.write_bytes(data)
            names.append(str(target))
        done = run(["git", "merge-file", "-p", *names], Path(folder))
    if done.returncode < 0 or done.returncode > 127:
        raise CannotRun(f"git merge-file could not compare a file: {text_of(done.stderr)[:200]}")
    return done.returncode


def mergeable(ours: bytes, base: bytes, theirs: bytes) -> bool:
    if not (is_text(ours) and is_text(base) and is_text(theirs)):
        return False
    return merge_conflicts(ours, base, theirs) == 0


def classify(base: bytes | None, theirs: bytes | None, ours: bytes | None, raw_same: bool) -> str:
    """The kind of change one file is, from the three versions (line endings already ignored)."""
    if theirs is None:
        if base is None or ours is None:
            return "ALREADY_GONE"
        return "DELETED_CLEAN" if ours == base else "DELETED_EDITED"
    if base is None:
        if ours is None:
            return "NEW"
        return "SAME" if ours == theirs else "NAME_CLASH"
    if base == theirs:
        return "UNCHANGED" if raw_same else "LINE_ENDINGS"
    if ours is None:
        return "OURS_GONE"
    if ours == theirs:
        return "SAME"
    if ours == base:
        return "TAKE"
    return "MERGES" if mergeable(ours, base, theirs) else "COLLIDES"


def ledger_decision(ledger: dict, path: str) -> dict | None:
    """The first ledger entry whose patterns match. `*` matches anything, `/` included."""
    for entry in ledger["entries"]:
        if any(fnmatch.fnmatchcase(path, pattern) for pattern in entry["paths"]):
            return entry
    return None


def added_text(base: bytes | None, theirs: bytes) -> str:
    """The lines upstream's new version has that the copied version did not: what its change is about."""
    seen = set(base.splitlines()) if base else set()
    kept = [line for line in theirs.splitlines() if line not in seen]
    return b"\n".join(kept).decode("utf-8", errors="replace")


def excluded_ids(added: str, exclusions: dict) -> list[str]:
    return [item["id"] for item in exclusions["exclusions"]
            if any(re.search(needle, added) for needle in item["needles"])]


def add_signals(change: FileChange, base: bytes | None, theirs: bytes, ours: bytes | None, exclusions: dict) -> None:
    change.lines_before = count_lines(base)
    change.lines_after = count_lines(theirs)
    changed_here = ours is not None and base is not None and ours != base
    change.restructured = bool(changed_here and change.lines_before >= 100
                               and change.lines_after * 2 < change.lines_before)
    added = added_text(base, theirs)
    change.excluded = excluded_ids(added, exclusions)
    if change.path.endswith(".py"):
        change.risks = [name for name, pattern in RISKS.items() if re.search(pattern, added)]
        change.brand = len(BRAND.findall(added))
        found = TOOL_NAME.search(added) if change.path.startswith(("actions/", "plugins/")) else None
        change.tool = found.group(1) if found else ""


def describe_file(context: Context, path: str) -> FileChange:
    decision = ledger_decision(context.ledger, path)
    base_rev = (decision or {}).get("reconciled") or context.pin["base_sha"]
    raw_base = blob(context.clone, base_rev, path)
    raw_new = blob(context.clone, context.new_sha, path)
    base, theirs, ours = plain(raw_base), plain(raw_new), plain(read_ours(context.root, path))
    change = FileChange(path, classify(base, theirs, ours, raw_base == raw_new),
                        (decision or {}).get("disposition", "held"), (decision or {}).get("reason", ""))
    if theirs is not None and is_text(theirs):
        add_signals(change, base, theirs, ours, context.exclusions)
    return change


# ------------------------------------------------------------------ is the new code reachable at all

def module_name(tree: Path, file: Path) -> str:
    parts = file.relative_to(tree).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def absolute_base(node: ast.ImportFrom, package: str) -> str | None:
    """The module a `from ... import` names, with its leading dots resolved against the package the file is in."""
    if not node.level:
        return node.module
    parts = package.split(".") if package else []
    keep = len(parts) - (node.level - 1)
    if keep < 0:
        return None                                  # more dots than there are packages: not a real import
    return ".".join([*parts[:keep], *([node.module] if node.module else [])])


def imported_names(source: str, package: str = "") -> set[str]:
    """Every module name this source imports. `package` is where the file lives, for imports written with dots."""
    try:
        parsed = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError, MemoryError) as error:     # a NUL byte, or nesting too deep to parse
        raise Unreadable(type(error).__name__) from error
    found: set[str] = set()
    for node in ast.walk(parsed):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = absolute_base(node, package)
            if base is None:
                continue
            if base:
                found.add(base)
            found.update(f"{base}.{alias.name}" if base else alias.name for alias in node.names)
    return found


def longest_known(name: str, known: dict[str, Path]) -> str | None:
    parts = name.split(".")
    while parts:
        candidate = ".".join(parts)
        if candidate in known:
            return candidate
        parts.pop()
    return None


def read_source(path: Path) -> str:
    """The text of a file inside the clone. The clone is somebody else's repository, so not everything is one.

    A link is `Unreadable` without being followed: it may lead out of the clone, to a file that is not upstream's.
    So is anything the system will not open: a folder named like a module, or a file nobody may read.
    """
    if path.is_symlink():
        raise Unreadable("a link")
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        raise Unreadable(type(error).__name__) from error


def reachable(tree: Path) -> tuple[set[str], list[str]]:
    """Modules that upstream's own main program, tools, plugins or providers can reach, and files it could not read."""
    files = {module_name(tree, item): item for item in tree.rglob("*.py") if ".git" not in item.parts}
    todo = [name for name in files if name == "main" or name.split(".")[0] in ENTRY_PACKAGES]
    seen: set[str] = set()
    unreadable: list[str] = []
    while todo:
        name = todo.pop()
        if name in seen or name not in files:
            continue
        seen.add(name)
        todo.extend(name.rsplit(".", count)[0] for count in range(1, name.count(".") + 1))
        path = files[name]
        package = name if path.name == "__init__.py" else name.rpartition(".")[0]
        try:
            imports = imported_names(read_source(path), package)
        except Unreadable:
            unreadable.append(path.relative_to(tree).as_posix())
            continue
        for target in imports:
            hit = longest_known(target, files)
            if hit and hit not in seen:
                todo.append(hit)
    return seen, sorted(unreadable)


def mark_unwired(changes: list[FileChange], tree: Path) -> list[str]:
    """Flag new modules nothing reaches. Returns the files that could not be read, which the report must admit."""
    fresh = [item for item in changes if item.kind == "NEW" and item.path.endswith(".py")]
    if not fresh:
        return []
    used, unreadable = reachable(tree)
    for item in fresh:
        name = item.path[:-3].replace("/", ".")
        name = name[:-9] if name.endswith(".__init__") else name
        item.unwired = name not in used
    return unreadable


# ------------------------------------------------------------------ gates: where a person must look first

def fingerprint(data: bytes | None) -> str:
    return "missing" if data is None else hashlib.sha256(plain(data) or b"").hexdigest()


def requirement_lines(data: bytes | None) -> set[str]:
    rows = (plain(data) or b"").decode("utf-8", errors="replace").splitlines()
    return {row.split("#")[0].strip() for row in rows if row.split("#")[0].strip()}


def requirement_changes(clone: Path, before_rev: str, now: bytes | None) -> str:
    before = requirement_lines(blob(clone, before_rev, "requirements.txt"))
    after = requirement_lines(now)
    added, removed = sorted(after - before), sorted(before - after)
    parts = []
    if added:
        parts.append("added or changed: " + "; ".join(code(item) for item in added[:6]) + (" ..." if len(added) > 6 else ""))
    if removed:
        parts.append("removed or changed from: " + "; ".join(code(item) for item in removed[:6])
                     + (" ..." if len(removed) > 6 else ""))
    return " ".join(parts) or "only comments or ordering."


def terms_gates(clone: Path, pin: dict, new_sha: str, full: bool, scope: str) -> list[str]:
    """The licence and the requirements, now against the reviewed drop (or, with --full, against the copy).

    `scope` is the commit the old requirement lines are read from: the reviewed drop, or the copy when that
    drop is no longer in upstream (the report says so, and the copy is all there is to measure from).
    """
    if full:
        before_licence = fingerprint(blob(clone, pin["base_sha"], "LICENSE"))
        before_requirements = fingerprint(blob(clone, pin["base_sha"], "requirements.txt"))
    else:
        before_licence = pin["reviewed"]["licence_sha256"]
        before_requirements = pin["reviewed"]["requirements_sha256"]
    gates = []
    licence = fingerprint(blob(clone, new_sha, "LICENSE"))
    if licence != before_licence:
        gates.append("The licence changed, or its file is gone. Read it before anything is taken: CC BY-NC 4.0 "
                     f"allows publishing, not selling. Fingerprint now {licence[:12]}, before {before_licence[:12]}.")
    requirements = blob(clone, new_sha, "requirements.txt")
    if fingerprint(requirements) != before_requirements:
        gates.append("Upstream's requirements.txt changed: " + requirement_changes(clone, scope, requirements)
                     + " A new dependency needs your consent.")
    return gates


def steering_gates(changes: list[FileChange]) -> list[str]:
    hit = [item.path for item in changes if item.kind not in QUIET
           and any(fnmatch.fnmatchcase(item.path, pattern) for pattern in STEERING)]
    if not hit:
        return []
    return [f"Upstream changed {names(hit)}. These steer agents, models or the rules here: read them; "
            "they are never applied automatically."]


# ------------------------------------------------------------------ the survey

def clean(text: str, limit: int) -> str:
    """One line of plain text: whatever is not printable becomes a space, spaces collapse, and it is cut at `limit`."""
    flat = " ".join("".join(char if char.isprintable() else " " for char in text).split())
    return flat if len(flat) <= limit else flat[:limit - 3].rstrip() + "..."


def code(text: str) -> str:
    """Text from upstream as an inline code span that nothing inside it can end early or turn into a new line.

    A span closes at the next run of backticks as long as the one that opened it, so the fence is one longer
    than the longest run in the text; a text that starts or ends with a backtick or a space gets a space inside
    the fence, which Markdown takes away again. Anything unprintable (a line break, an escape) becomes `?`.
    """
    text = "".join(char if char.isprintable() else "?" for char in text)
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * (longest + 1)
    pad = " " if text[:1] in ("`", " ") or text[-1:] in ("`", " ") else ""
    return f"{fence}{pad}{text}{pad}{fence}"


def version_of(clone: Path, rev: str) -> str:
    """What upstream calls this version, from the first line of its readme, kept short enough for an issue title."""
    for name in ("readme.md", "README.md"):
        text = plain(blob(clone, rev, name))
        if text:
            first = text.split(b"\n")[0].decode("utf-8", errors="replace")
            found = TITLE.search(first)
            return clean(f"MARK {found.group(1)} ({found.group(2)})" if found else first.strip("# "), VERSION_LIMIT) or "unknown"
    return "unknown"


def changed_paths(clone: Path, scope: str, new_sha: str) -> list[str]:
    raw = git(clone, "diff", "--name-only", "--no-renames", "-z", scope, new_sha)
    return [item for item in raw.decode("utf-8", errors="replace").split("\0") if item]


def scope_for(clone: Path, pin: dict, full: bool) -> tuple[str, list[str]]:
    """The commit to measure from, and a gate if the reviewed commit has vanished from upstream."""
    reviewed = pin["reviewed"]["sha"]
    if full:
        return pin["base_sha"], []
    if has_commit(clone, reviewed):
        return reviewed, []
    return pin["base_sha"], [f"The reviewed commit {reviewed[:12]} is no longer in upstream: its history was "
                             "rewritten or the repository replaced. Everything since the copy is listed instead."]


def summarise(changes: list[FileChange]) -> dict:
    counts: dict[str, int] = {}
    for item in changes:
        counts[item.kind] = counts.get(item.kind, 0) + 1
    return {kind: counts[kind] for kind in KINDS if kind in counts}


def survey(clone: Path, pin: dict, ledger: dict, exclusions: dict, root: Path, full: bool) -> dict:
    new_sha = text_of(git(clone, "rev-parse", "HEAD"))
    if not has_commit(clone, pin["base_sha"]):
        raise CannotRun("the pinned base commit is no longer in upstream (history rewritten?); re-pin by hand")
    for number, entry in enumerate(ledger["entries"], 1):
        if "reconciled" in entry and not has_commit(clone, entry["reconciled"]):
            raise CannotRun(f"LEDGER.json entry {number}: the reconciled commit {entry['reconciled'][:12]} is not in "
                            "upstream (history rewritten?); fix or remove it")
    report = {"new_sha": new_sha, "date": text_of(git(clone, "log", "-1", "--format=%cs", "HEAD")),
              "version": version_of(clone, new_sha), "reviewed_version": pin["reviewed"]["version"],
              "reviewed_sha": pin["reviewed"]["sha"], "base_sha": pin["base_sha"], "gates": [], "notes": [],
              "full": full}
    if new_sha == pin["reviewed"]["sha"] and not full:
        return {**report, "moved": False, "files": [], "counts": {}, "commits": 0}
    scope, gates = scope_for(clone, pin, full)
    context = Context(clone, root, pin, ledger, exclusions, new_sha)
    every = changed_paths(clone, scope, new_sha)
    paths = [path for path in every if safe_path(path)]
    refused = [path for path in every if not safe_path(path)]
    changes = [describe_file(context, path) for path in paths]
    unreadable = mark_unwired(changes, clone)
    gates += terms_gates(clone, pin, new_sha, full, scope) + steering_gates(changes)
    commits = int(text_of(git(clone, "rev-list", "--count", f"{scope}..{new_sha}")) or 0)
    notes = []
    if refused:
        notes.append(f"{len(refused)} path(s) in upstream were left out because their names are not plain relative paths "
                     f"(a '..', a backslash, a colon or an unreadable character): {names(refused)}.")
    if unreadable:
        notes.append(f"{len(unreadable)} Python file(s) in upstream could not be read to see what they import ({names(unreadable)}), "
                     "so the list of new code nothing imports may be incomplete.")
    return {**report, "moved": True, "gates": gates, "notes": notes, "files": [asdict(item) for item in changes],
            "counts": summarise(changes), "commits": commits, "scope": scope}


# ------------------------------------------------------------------ the report, in plain words

def short(sha: str) -> str:
    return sha[:7]


def joined(items: list[str], limit: int = LIST_LIMIT) -> str:
    shown = ", ".join(items[:limit])
    return shown + (f" and {len(items) - limit} more" if len(items) > limit else "")


def names(paths: list[str]) -> str:
    return joined([code(path) for path in paths])


def top_folder(path: str) -> str:
    return path.split("/")[0] if "/" in path else "(top level)"


def of_kind(report: dict, *kinds: str) -> list[dict]:
    return [item for item in report["files"] if item["kind"] in kinds]


def headline(report: dict) -> list[str]:
    old, new = report["reviewed_version"], report["version"]
    if report["full"]:
        title = f"{code(new)}, everything since the copy"
        scope = f"since the copy (`{short(report['base_sha'])}`)"
        opening = "**Full comparison.**"
    else:
        title = f"{code(old)} -> {code(new)}" if old != new else f"{code(new)}, new commits"
        scope = f"since the drop you last reviewed (`{short(report['reviewed_sha'])}`)"
        opening = "**Yes, upstream moved.**"
    return [f"# Upstream watch: {title}", "",
            f"{opening} {report['commits']} commit(s) {scope}; upstream's head is "
            f"`{short(report['new_sha'])}` ({report['date']}). {len(report['files'])} file(s) differ.", ""]


def section(title: str, lines: list[str]) -> list[str]:
    return [f"## {title}", "", *lines, ""] if lines else []


def kinds_table(report: dict) -> list[str]:
    rows = [f"| {KINDS[kind]} | {count} |" for kind, count in report["counts"].items()]
    return ["| What it is | Files |", "|---|---:|", *rows] if rows else []


def decision_lists(report: dict) -> list[str]:
    lines = []
    for kind in ("COLLIDES", "NAME_CLASH", "DELETED_EDITED", "MERGES"):
        rows = [item for item in of_kind(report, kind) if item["decision"] == "held"]
        if rows:
            lines.append(f"- **{KINDS[kind].capitalize()}** ({len(rows)}): {names([item['path'] for item in rows])}")
    return lines


def decided_lines(report: dict) -> list[str]:
    groups: dict[str, list[str]] = {}
    for row in report["files"]:
        if row["decision"] != "held" and row["kind"] not in QUIET:
            groups.setdefault(row["decision"], []).append(row["path"])
    return [f"- **{decision}** ({len(paths)}): {names(paths)}" for decision, paths in groups.items()]


def new_by_folder(report: dict) -> list[str]:
    folders: dict[str, int] = {}
    for item in of_kind(report, "NEW"):
        folders[top_folder(item["path"])] = folders.get(top_folder(item["path"]), 0) + item["lines_after"]
    if not folders:
        return []
    biggest = sorted(folders.items(), key=lambda pair: -pair[1])
    return ["- New code by folder: " + joined([f"{code(top)} {lines:,} lines" for top, lines in biggest])]


def held_lines(report: dict) -> list[str]:
    rows = [row for row in report["files"] if row["decision"] == "held" and row["kind"] not in QUIET]
    if not rows:
        return []
    folders: dict[str, int] = {}
    for row in rows:
        folders[top_folder(row["path"])] = folders.get(top_folder(row["path"]), 0) + 1
    biggest = sorted(folders.items(), key=lambda pair: -pair[1])
    return [f"- {len(rows)} file(s) have no ledger decision yet, so they are held and not copied: "
            + joined([f"{code(top)} {count}" for top, count in biggest])]


def exclusion_lines(report: dict, exclusions: dict) -> list[str]:
    lines = []
    for item in exclusions["exclusions"]:
        hits = [row["path"] for row in report["files"] if item["id"] in row["excluded"]]
        if hits:
            lines.append(f"- **{item['id']} {item['name']}** stays out ({item['guard']['kind']} guard): upstream's "
                         f"new or changed lines mention it in {names(hits)}.")
    return lines


def signal_lines(report: dict) -> list[str]:
    files = report["files"]
    lines = []
    tools = [f"{code(row['path'])} (tool {row['tool']})" for row in files if row["tool"]]
    restructured = [row["path"] for row in files if row["restructured"]]
    unwired = [row["path"] for row in files if row["unwired"]]
    if tools:
        lines.append(f"- New tools: {joined(tools)}")
    if restructured:
        lines.append(f"- Restructured upstream (lost over half its lines while Ultron changed it): {names(restructured)}")
    if unwired:
        lines.append(f"- New code that nothing in upstream's own program imports: {names(unwired)}")
    for risk in RISKS:
        rows = [row["path"] for row in files if risk in row["risks"]]
        if rows:
            lines.append(f"- New code that {risk}: {names(rows)}")
    total = sum(row["brand"] for row in files)
    if total:
        lines.append(f"- {total} added string(s) say JARVIS or MARK/Mark LVII; Ultron's name is Ultron.")
    return lines


def render(report: dict, exclusions: dict) -> str:
    if not report["moved"]:
        return (f"**No.** Upstream has not moved past the drop last reviewed ({code(report['reviewed_version'])}, "
                f"`{short(report['reviewed_sha'])}`).\n")
    parts = headline(report)
    parts += section("Stop and ask", [f"- {gate}" for gate in report["gates"]])
    parts += section("What changed", kinds_table(report))
    parts += section("Needs a decision", decision_lists(report) + held_lines(report))
    parts += section("Already decided by the ledger", decided_lines(report))
    parts += section("New code", new_by_folder(report))
    parts += section("Touches what you excluded", exclusion_lines(report, exclusions))
    parts += section("Worth knowing", signal_lines(report))
    parts += section("Notes", [f"- {note}" for note in report["notes"]])
    parts += ["Nothing has been applied. This report only reads. To act on it, say which slice to port; "
              "each one is a separate, tested change (docs/UPSTREAM_SYNC.md).", ""]
    text = "\n".join(parts)
    if len(text) > ISSUE_LIMIT:
        text = text[:ISSUE_LIMIT] + "\n\n(cut: longer than an issue can hold; run the script for all of it)\n"
    return text


# ------------------------------------------------------------------ the command line

def command_check(args: argparse.Namespace) -> int:
    pin, ledger, exclusions = load_data(args.data)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        source, found, notes = choose_source(args, pin)
        report = survey(fetch_upstream(source, Path(folder)), pin, ledger, exclusions, args.root, args.full)
    report["notes"] = notes + rename_notes(found, pin) + report["notes"]
    text = render(report, exclusions)
    if args.markdown:
        Path(args.markdown).write_text(text, encoding="utf-8")
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(text)
    if not report["moved"]:
        return EXIT_SAME
    return EXIT_STOP if report["gates"] else EXIT_MOVED


def command_pin(args: argparse.Namespace) -> int:
    pin = check_pin(read_json(args.data / "PIN.json"))
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        source, _found, _notes = choose_source(args, pin)
        clone = fetch_upstream(source, Path(folder))
        sha = text_of(git(clone, "rev-parse", "HEAD"))
        block = {"sha": sha, "date": text_of(git(clone, "log", "-1", "--format=%cs", "HEAD")),
                 "version": version_of(clone, sha), "licence_sha256": fingerprint(blob(clone, sha, "LICENSE")),
                 "requirements_sha256": fingerprint(blob(clone, sha, "requirements.txt"))}
    print(json.dumps({"reviewed": block}, indent=2))
    return EXIT_SAME


COMMANDS = {"check": command_check, "pin": command_pin}


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare upstream Mark with Ultron. Read-only.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, text in (("check", "report what moved upstream"), ("pin", "print the PIN.json block for upstream's head")):
        sub = commands.add_parser(name, help=text)
        sub.add_argument("--upstream", help="clone from this address or folder instead of asking GitHub")
        sub.add_argument("--no-api", action="store_true", help="do not ask GitHub what the repository is called now")
        sub.add_argument("--data", type=Path, default=DATA, help="the folder holding PIN.json, LEDGER.json, EXCLUSIONS.json")
        sub.add_argument("--root", type=Path, default=ROOT, help="the Ultron tree to compare against")
    check = commands.choices["check"]
    check.add_argument("--full", action="store_true", help="everything since the copy, not only since the reviewed drop")
    check.add_argument("--markdown", help="also write the report here")
    check.add_argument("--json", help="also write the machine copy here")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except CannotRun as error:
        print(f"upstream_sync: {error}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
