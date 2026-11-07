"""Report repository changes so agents can orient before planning work.

Read-only by default. It compares the current branch with a local base ref, reports
commits since a per-worktree acknowledgement, incoming base commits, and local edits.
It does not fetch, switch branches, merge, or modify tracked files. Use --ack only
after reviewing the report; acknowledgement metadata is written under Git's private
worktree metadata directory, not into the repository.

Run: python scripts/agent_workspace.py [--base origin/main] [--patch]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


MAX_PATCH_LINES = 2000
DEFAULT_PATCH_LINES = 240
MAX_COMMITS = 30


class GitError(RuntimeError):
    """A required Git command failed."""


def _git(*args: str, cwd: Path | None = None, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, text=True, encoding="utf-8", errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if check and result.returncode:
        raise GitError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def _repo_root() -> Path:
    try:
        return Path(_git("rev-parse", "--show-toplevel")).resolve()
    except (GitError, FileNotFoundError) as exc:
        raise GitError("Not inside a Git repository, or git is unavailable.") from exc


def _parse_name_status(raw: str) -> list[tuple[str, str, str | None]]:
    """Parse `git diff --name-status -z`; rename/copy entries have two paths."""
    fields = raw.split("\0")
    entries: list[tuple[str, str, str | None]] = []
    index = 0
    while index < len(fields):
        status = fields[index]
        index += 1
        if not status:
            continue
        if index >= len(fields):
            break
        first = fields[index]
        index += 1
        if not first:
            # "M\\0" is truncated output, not a file whose path is empty.
            break
        second = None
        if status[:1] in ("R", "C") and index < len(fields):
            second = fields[index]
            index += 1
        entries.append((status, first, second))
    return entries


_RANGE_CACHE: dict[str, str | None] = {"value": None}


def _range(base: str, root: Path) -> str:
    """Return the diff range to compare with: `...` when history is shared, `..` when not.

    A shallow clone — a CI checkout, an agent sandbox — has grafted roots and no merge
    base, so the three-dot form fails with "no merge base" and the whole report dies on
    its first comparison. The two-dot form still answers the question the report asks.
    """
    if _RANGE_CACHE.get("value") is None:
        try:
            _git("merge-base", base, "HEAD", cwd=root)
            _RANGE_CACHE["value"] = "..."
        except GitError:
            print(f"No merge base with {base} (shallow or unrelated history): comparing the "
                  "two tips instead of the branch point.")
            _RANGE_CACHE["value"] = ".."
    return _RANGE_CACHE["value"]


def _state_path(root: Path, branch: str) -> Path:
    git_dir = Path(_git("rev-parse", "--git-path", "ultron-agent-workspace", cwd=root))
    if not git_dir.is_absolute():
        git_dir = root / git_dir
    key = hashlib.sha256(branch.encode("utf-8")).hexdigest()[:16]
    return git_dir / f"{key}.json"


def _valid_commit(ref: str, root: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    return result.returncode == 0


def _print_entries(title: str, entries: list[tuple[str, str, str | None]]) -> None:
    print(f"\n{title} ({len(entries)}):")
    if not entries:
        print("  none")
        return
    for status, first, second in entries:
        if second is None:
            print(f"  {status:>4}  {first}")
        else:
            print(f"  {status:>4}  {first} -> {second}")


def _commits(rev: str, root: Path) -> list[str]:
    output = _git("log", f"--max-count={MAX_COMMITS}", "--date=short",
                  "--pretty=format:%h %ad %s", rev, cwd=root)
    return output.splitlines() if output else []


def _bounded_patch(base: str, head: str, root: Path, max_lines: int) -> None:
    span = _range(base, root)
    paths = _parse_name_status(_git("diff", "--name-status", "-z", f"{base}{span}{head}", cwd=root))
    if not paths:
        print("\nPatch: no committed branch changes against the base.")
        return
    lines_left = max_lines
    print(f"\nPatch (at most {max_lines} lines; inspect full files for context):")
    for _status, old_path, new_path in paths:
        if lines_left <= 0:
            print("\n[patch truncated at configured line limit]")
            break
        path = new_path or old_path
        result = subprocess.run(
            ["git", "diff", "--no-ext-diff", "--unified=3", f"{base}{span}{head}", "--", path],
            cwd=root, text=True, encoding="utf-8", errors="replace",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if result.returncode:
            print(f"[could not read patch for {path}: {result.stderr.strip()}]")
            continue
        chunk = result.stdout.splitlines()
        if len(chunk) > lines_left:
            print("\n".join(chunk[:lines_left]))
            lines_left = 0
        else:
            print("\n".join(chunk))
            lines_left -= len(chunk)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main", help="local ref to compare with (default: origin/main)")
    parser.add_argument("--patch", action="store_true", help="print a bounded patch for committed branch changes")
    parser.add_argument("--max-lines", type=int, default=DEFAULT_PATCH_LINES,
                        help=f"patch line cap, 1..{MAX_PATCH_LINES} (default: {DEFAULT_PATCH_LINES})")
    parser.add_argument("--ack", action="store_true", help="record HEAD as reviewed after printing this report")
    return parser


def _print_header(root: Path, branch: str, head: str, base: str) -> None:
    print("ULTRON AGENT WORKSPACE REPORT")
    print(f"Repository: {root}\nBranch: {branch}\nHEAD: {head[:12]}\nBase: {base}")
    try:
        upstream = _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", cwd=root)
    except GitError:
        upstream = "(no upstream configured)"
    print(f"Upstream: {upstream}")


def _last_acknowledgement(state_file: Path) -> str | None:
    if not state_file.exists():
        return None
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
        return state.get("head")
    except (OSError, ValueError, AttributeError):
        print("Warning: prior acknowledgement state is unreadable; treating this as first review.")
        return None


def _print_changes_since_ack(last_seen: str | None, base: str, root: Path) -> None:
    """The commits and paths this agent has not reviewed yet, or the whole snapshot."""
    span = _range(base, root)
    if last_seen and _valid_commit(str(last_seen), root):
        if _git("merge-base", "--is-ancestor", str(last_seen), "HEAD", cwd=root, check=False) == "":
            recent = _commits(f"{last_seen}..HEAD", root)
            paths = _parse_name_status(_git("diff", "--name-status", "-z", f"{last_seen}..HEAD", cwd=root))
            print(f"\nSince last acknowledgement ({str(last_seen)[:12]}):")
        else:
            recent = _commits("HEAD", root)
            paths = _parse_name_status(_git("diff", "--name-status", "-z", f"{base}{span}HEAD", cwd=root))
            print("\nPrior acknowledged commit is not an ancestor (history rewrote/diverged); showing current branch snapshot.")
    else:
        recent = _commits("HEAD", root)
        paths = _parse_name_status(_git("diff", "--name-status", "-z", f"{base}{span}HEAD", cwd=root))
        print("\nFirst review in this worktree; showing branch history and current branch snapshot.")
    for line in recent or ["none"]:
        print(f"  {line}")
    _print_entries("Changed paths since acknowledgement / snapshot", paths)


def _print_incoming(base: str, root: Path) -> None:
    """Base commits this branch does not have. Reported, never merged."""
    span = _range(base, root)
    incoming = _commits(f"HEAD..{base}", root)
    incoming_paths = _parse_name_status(_git("diff", "--name-status", "-z", f"HEAD{span}{base}", cwd=root))
    print(f"\nBase commits not in this branch ({len(incoming)} shown, newest {MAX_COMMITS} max):")
    for line in incoming or ["none"]:
        print(f"  {line}")
    _print_entries("Paths differing between the two tips" if span == ".."
                   else "Paths changed on base since branch point", incoming_paths)


def _write_acknowledgement(state_file: Path, branch: str, head: str) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({
        "branch": branch,
        "head": head,
        "acknowledged_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2) + "\n", encoding="utf-8")
    print(f"\nAcknowledged HEAD {head[:12]} for this local worktree only.")


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if not 1 <= args.max_lines <= MAX_PATCH_LINES:
        parser.error(f"--max-lines must be between 1 and {MAX_PATCH_LINES}")
    try:
        root = _repo_root()
        head = _git("rev-parse", "HEAD", cwd=root)
        branch = _git("branch", "--show-current", cwd=root) or "detached"
        base = args.base
        if not _valid_commit(base, root):
            alternatives = [ref for ref in ("origin/main", "main") if _valid_commit(ref, root)]
            hint = f" Available local alternatives: {', '.join(alternatives)}." if alternatives else ""
            print(f"Base ref {base!r} is not available locally.{hint} Fetch refs or pass --base REF.", file=sys.stderr)
            return 2

        _print_header(root, branch, head, base)
        state_file = _state_path(root, branch)
        _print_changes_since_ack(_last_acknowledgement(state_file), base, root)

        span = _range(base, root)
        branch_paths = _parse_name_status(
            _git("diff", "--name-status", "-z", f"{base}{span}HEAD", cwd=root))
        _print_entries("Committed branch changes vs base" if span == "..."
                       else "Files that differ from the base tip", branch_paths)
        _print_incoming(base, root)

        status = _git("status", "--short", "--untracked-files=all", cwd=root)
        print("\nUncommitted working-tree changes:")
        print(status if status else "  clean")
        print("\nPLAN NEXT: read the relevant commits and full files; compare intent with DECISIONS.md; preserve unrelated edits; define acceptance tests before coding.")
        print("This report does not fetch, merge, edit tracked files, or run tests. Re-run after updating refs or pulling.")

        if args.patch:
            _bounded_patch(base, "HEAD", root, args.max_lines)
        if args.ack:
            _write_acknowledgement(state_file, branch, head)
        return 0
    except (GitError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
