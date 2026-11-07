"""Which branches exist, where each one points, and which names are the same commit.

Read-only. It runs `git for-each-ref` and prints. It does not fetch, switch, merge, push,
edit a tracked file or start a session.

It exists because a shallow clone — a CI checkout, an agent sandbox — has no merge base,
so "ahead of `main` by 12 commits" is a guess there, and two names pointing at one commit
look like two branches. This prints the tip and the subject instead, and groups the names
that are the same commit.

Run: python scripts/branch_report.py [--remote origin] [--json]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

FIELDS = "%(refname:short)%09%(objectname:short=12)%09%(committerdate:short)%09%(subject)"


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], text=True, encoding="utf-8", errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def _parse_refs(raw: str) -> list[dict[str, str]]:
    """Turn `for-each-ref` output into rows. A short line is a truncated read, not a branch."""
    rows = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        name, sha, date, subject = parts[0], parts[1], parts[2], "\t".join(parts[3:])
        rows.append({"name": name.replace("heads/", "", 1),
                     "sha": sha, "date": date, "subject": subject.strip()})
    return rows


def _groups(rows: list[dict[str, str]]) -> dict[str, list[str]]:
    """sha -> the names that point at it. This is the part a branch picker cannot show."""
    groups: dict[str, list[str]] = {}
    for row in rows:
        groups.setdefault(row["sha"], []).append(row["name"])
    return groups


def _local_and_remote(remote: str) -> list[dict[str, str]]:
    local = _parse_refs(_git("for-each-ref", "--format=" + FIELDS, "refs/heads/"))
    try:
        tracking = _parse_refs(_git("for-each-ref", "--format=" + FIELDS,
                                    f"refs/remotes/{remote}/"))
    except RuntimeError:
        tracking = []
    known = {row["name"] for row in local}
    return local + [row for row in tracking if row["name"] not in known]


def _print_table(rows: list[dict[str, str]]) -> None:
    if not rows:
        print("No branches. Is this a Git repository?")
        return
    width = max(len(row["name"]) for row in rows)
    print(f"{'branch'.ljust(width)}  {'commit':12}  {'date':10}  subject")
    for row in rows:
        print(f"{row['name'].ljust(width)}  {row['sha']:12}  {row['date']:10}  {row['subject']}")


def _print_duplicates(rows: list[dict[str, str]]) -> None:
    shared = {sha: names for sha, names in _groups(rows).items() if len(names) > 1}
    if not shared:
        return
    print("\nThe same commit under more than one name:")
    for sha, names in shared.items():
        print(f"  {sha}  {', '.join(names)}")
    print("  These are one branch with two labels until one of them moves.")


def _print_history_note() -> None:
    shallow = _git("rev-parse", "--is-shallow-repository").strip()
    if shallow == "true":
        print("\nShallow clone: no merge base exists, so this report shows tips rather than "
              "counts of commits ahead. Fetch full history before quoting a distance.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", default="origin", help="remote to list (default: origin)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)
    try:
        rows = _local_and_remote(args.remote)
    except (RuntimeError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"branches": rows, "same_commit": _groups(rows)}, indent=2))
        return 0
    print(f"BRANCHES — {Path.cwd()}")
    _print_table(rows)
    _print_duplicates(rows)
    _print_history_note()
    print("\nThis report does not fetch, merge, switch branches or push.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
