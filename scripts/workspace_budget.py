#!/usr/bin/env python3
"""Keep the workspace under the size it is allowed to be.

The workspace is where the project lives, and it is saved as a whole after every
message. That has a hard cost attached: the platform stores roughly 128 MB and
10,000 files per save, and anything past that is silently not kept. It happened
once — a session installed the full dependency set inside the workspace instead of
in `/tmp`, briefly wrote 375 MB across 6,711 files, and 6,352 files were dropped on
the floor without a word.

Nothing on disk was wrong. The habit was. This script makes the size a number that
gets looked at, so a run that grows into the hundreds of megabytes is caught while it
is still a large folder rather than after a save has already lost half of it.

    python scripts/workspace_budget.py              # report, exit 1 if over budget
    python scripts/workspace_budget.py --json
    python scripts/workspace_budget.py --limit-mb 90

The budget is deliberately below the platform's own ceiling. A limit set exactly at
the edge is a limit that is discovered by crossing it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The platform keeps about 128 MB and 10,000 files per save. These sit comfortably
# under both, because the failure mode is silent and the cleanup is not free.
LIMIT_MB = 100.0
LIMIT_FILES = 5_000

# Created by running things, never by writing them. Safe to delete at any time, the
# first place a careless command puts a hundred megabytes, and never counted against
# the budget: a user's `.venv` is six hundred megabytes, it belongs to them, and
# counting it would make the number meaningless. It is reported on its own line, so
# the size stays visible without the check being switched off inside a week.
GENERATED = ("__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
             ".hypothesis", "node_modules", ".venv", ".venv.old", "build", "dist",
             # Tool caches, for when --root points at a home folder rather than the
             # project. npx alone keeps a hundred megabytes here and recreates it.
             ".npm", ".cache", ".local", ".arena", ".playwright-cli")


def _size(path: Path) -> int | None:
    """Bytes in one file, or None. A file can vanish between listing and measuring."""
    try:
        return path.stat().st_size
    except OSError:
        return None


def _total(folder: Path) -> tuple[int, int]:
    """Bytes and files under one folder, counted without walking into it twice."""
    size = 0
    count = 0
    for path in folder.rglob("*"):
        found = _size(path) if path.is_file() else None
        if found is None:
            continue
        size += found
        count += 1
    return size, count


def _generated_in(folder: str, dirs: list[str]) -> tuple[int, int, list[str]]:
    """Measure the generated folders here, and say which folders are left to walk."""
    size = 0
    count = 0
    kept = []
    for name in dirs:
        if name in GENERATED:
            extra_size, extra_count = _total(Path(folder) / name)
            size += extra_size
            count += extra_count
        else:
            kept.append(name)
    return size, count, kept


def measure(root: Path = ROOT) -> dict:
    """Size and file count of the workspace, with the folders that account for it."""
    total_bytes = 0
    total_files = 0
    generated_bytes = 0
    generated_files = 0
    by_folder: dict[str, tuple[int, int]] = {}
    for folder, dirs, files in os.walk(root):
        # A generated folder is measured, then left out of the walk: its contents are
        # reported on their own line and never counted against the budget.
        extra_bytes, extra_files, kept = _generated_in(folder, dirs)
        dirs[:] = kept
        generated_bytes += extra_bytes
        generated_files += extra_files
        for name in files:
            path = Path(folder) / name
            size = _size(path)
            if size is None:
                continue
            total_bytes += size
            total_files += 1
            relative = path.relative_to(root)
            key = relative.parts[0] if len(relative.parts) > 1 else "(top level)"
            current = by_folder.get(key, (0, 0))
            by_folder[key] = (current[0] + size, current[1] + 1)
    biggest = sorted(by_folder.items(), key=lambda item: -item[1][0])[:8]
    return {
        "mb": round(total_bytes / 1048576, 1),
        "files": total_files,
        "generated_mb": round(generated_bytes / 1048576, 1),
        "generated_files": generated_files,
        "folders": [{"name": name, "mb": round(size / 1048576, 1), "files": count}
                    for name, (size, count) in biggest],
    }


def cache_folders(root: Path = ROOT) -> list[Path]:
    found = []
    for folder, dirs, _files in os.walk(root):
        for name in list(dirs):
            if name in GENERATED:
                found.append(Path(folder) / name)
                dirs.remove(name)          # do not descend: the whole folder goes
    return found


def render(report: dict, limit_mb: float, limit_files: int) -> str:
    over = report["mb"] > limit_mb or report["files"] > limit_files
    lines = ["WORKSPACE BUDGET",
             f"  {report['mb']} MB of {limit_mb:g} MB   "
             f"{report['files']:,} files of {limit_files:,}   "
             f"{'OVER BUDGET' if over else 'inside budget'}"]
    if report.get("generated_files"):
        lines.append(f"  plus {report['generated_mb']} MB in {report['generated_files']:,} "
                     f"generated files (python caches, .venv, build output) — not counted")
    lines += ["", "  biggest folders:"]
    for folder in report["folders"]:
        lines.append(f"    {folder['mb']:8.1f} MB  {folder['files']:6d} files  "
                     f"{folder['name']}")
    if over:
        lines += [
            "",
            "  Over budget. A save at this size starts dropping files without saying so.",
            "  Fix the cause, not the number:",
            "    - install packages into /tmp, never into this folder",
            "      (pip install --target /tmp/deps, and PIP_CACHE_DIR=/tmp/pipcache)",
            "    - delete build output and __pycache__ before the end of the session",
            "    - keep big binaries out of the tree entirely; they are build output",
            "  `--clean` removes the cache folders this script knows about.",
        ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--limit-mb", type=float, default=LIMIT_MB)
    parser.add_argument("--limit-files", type=int, default=LIMIT_FILES)
    parser.add_argument("--clean", action="store_true",
                        help="delete the cache folders this script knows about")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if args.clean:
        for folder in cache_folders(root):
            try:
                for path in sorted(folder.rglob("*"), reverse=True):
                    if path.is_file():
                        path.unlink()
                folder.rmdir()
                print(f"removed {folder.relative_to(root)}")
            except OSError as error:
                print(f"could not remove {folder}: {error}")

    report = measure(root)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render(report, args.limit_mb, args.limit_files))
    return 1 if (report["mb"] > args.limit_mb
                 or report["files"] > args.limit_files) else 0


if __name__ == "__main__":
    sys.exit(main())
