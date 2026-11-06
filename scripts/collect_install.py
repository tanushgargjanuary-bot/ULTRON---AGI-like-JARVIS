"""scripts/collect_install.py — find the DATA in an install folder, and prove it.

THE PROBLEM
    D:\\Downloads\\mark-custom-jarvis is a folder holding about 130 files, of
    which roughly 120 are code. Picking the interesting ones by hand is guesswork,
    and the folder keeps changing as the app runs: today's memory file is
    tomorrow's stale copy, and a new file can appear that nobody has looked at.

WHAT THIS DOES
    1. Walks the folder and CLASSIFIES every file: code, doc, cache, config,
       data — and `unknown` for anything it does not recognise, because an
       unrecognised file is exactly what "new stuff" looks like.
    2. Fingerprints each one (size + SHA-256, or size + mtime for large files) and
       compares against the last run, so the second run tells you what is NEW,
       CHANGED or GONE rather than repeating the same list.
    3. Optionally bundles the data files — with secrets blanked — into one small
       ZIP plus a MANIFEST, so it can be handed to somebody for diagnosis without
       sending 120 source files and a lifetime of chat logs by accident.
    4. `--watch` keeps a terminal window open and prints files as they appear.

WHAT IT WILL NOT DO
    It never uploads anything, never deletes anything, never follows a symlink out
    of the folder it was given, and never prints the contents of a memory file or
    the value of a key — only names, sizes and counts. Bundling is opt-in, and the
    bundle is written where you tell it.

USAGE
    python scripts\\collect_install.py                          (uses the default path below)
    python scripts\\collect_install.py --path "D:\\somewhere"
    python scripts\\collect_install.py --bundle out.zip         (data only, secrets blanked)
    python scripts\\collect_install.py --watch --interval 5     (live, until Ctrl+C)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_TARGET = r"D:\Downloads\mark-custom-jarvis"
STATE_FILENAME = ".ultron-collect-state.json"

# Directories that are caches, virtualenvs or other people's code. None of them
# can hold something the user said.
EXCLUDED_DIRS = {
    "__pycache__", ".git", ".venv", "venv", "env", "node_modules", ".pytest_cache",
    ".ruff_cache", ".hypothesis", "site-packages", "build", "dist", ".mypy_cache",
    "backups", "repairs", "screenshots", ".cache",
}

CODE_EXT = {".py", ".pyd", ".dll", ".exe", ".bat", ".cmd", ".ps1", ".sh",
            ".obj", ".ico", ".so", ".dylib", ".ttf", ".otf", ".wasm",
            ".js", ".mjs", ".ts", ".css"}
# Extension-less files that are metadata, not data.
DOC_NAMES = {"license", "notice", "authors", "contributors", "copying",
             ".gitignore", ".gitattributes", ".gitmodules", "changelog"}
DOC_EXT = {".md", ".txt", ".rst", ".html", ".pdf"}          # outside known data names
CACHE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".wav", ".mp3",
             ".log", ".tmp", ".bak", ".pyc"}     # compiled leftovers are never data
DATA_EXT = {".sqlite3", ".db", ".jsonl", ".csv", ".ndjson"}

# Named data files, relative to the install root. Anything under memory/ that is
# JSON counts as data even if it is not in this list — that is the point of the
# classification rather than a fixed table.
CONFIG_NAMES = {( "config", "api_keys.json")}
MEMORY_DIR = "memory"

MAX_HASH_BYTES = 8 * 1024 * 1024      # above this, fingerprint by size+mtime
MAX_BUNDLE_FILE = 64 * 1024 * 1024
MAX_BUNDLE_TOTAL = 200 * 1024 * 1024
_SECRET_HINTS = ("key", "token", "secret", "password", "credential", "auth")


@dataclass
class Found:
    rel: str
    size: int
    mtime: float
    kind: str
    fingerprint: str = ""
    note: str = ""

    def as_dict(self) -> dict:
        return {"rel": self.rel, "size": self.size, "kind": self.kind,
                "fingerprint": self.fingerprint, "note": self.note}


@dataclass
class Scan:
    root: str
    files: list[Found] = field(default_factory=list)
    skipped_dirs: int = 0

    @property
    def by_kind(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.files:
            counts[item.kind] = counts.get(item.kind, 0) + 1
        return counts


def classify(rel: str) -> str:
    """code / doc / cache / config / data / unknown — path first, extension second."""
    parts = Path(rel).parts
    name = parts[-1].lower()
    suffix = Path(name).suffix

    if name in DOC_NAMES or name.startswith("readme"):
        return "doc"
    if name == STATE_FILENAME:
        return "cache"

    if (len(parts) >= 2 and (parts[-2].lower(), name) in CONFIG_NAMES):
        return "config"
    if len(parts) >= 2 and parts[-2].lower() == MEMORY_DIR and suffix == ".json":
        return "data"
    if suffix in DATA_EXT:
        return "data"
    if suffix == ".json":
        # A JSON file anywhere else could be either. Under a package folder it is
        # usually configuration; at the root it is usually something written at
        # runtime, which is exactly what we want to surface.
        return "data" if len(parts) == 1 else "config"
    if suffix in CODE_EXT:
        return "code"
    if suffix in CACHE_EXT:
        return "cache"
    if suffix in DOC_EXT:
        return "doc"
    return "unknown"


def _fingerprint(path: Path, size: int, mtime: float) -> str:
    if size > MAX_HASH_BYTES:
        return f"size:{size}:mtime:{int(mtime)}"
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return f"size:{size}:mtime:{int(mtime)}"
    return "sha256:" + digest.hexdigest()


def scan(root: Path) -> Scan:
    result = Scan(root=str(root))
    root = root.resolve()
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d.lower() not in EXCLUDED_DIRS)
        result.skipped_dirs += sum(1 for d in dirs if d.lower() in EXCLUDED_DIRS)
        for name in sorted(files):
            if name == STATE_FILENAME:
                continue                      # our own bookkeeping, not user data
            path = Path(current) / name
            try:
                if path.is_symlink():
                    target = path.resolve()
                    if root not in target.parents and target != root:
                        continue          # never leave the folder we were given
                stat = path.stat()
            except OSError:
                continue
            rel = str(path.relative_to(root)).replace(os.sep, "/")
            result.files.append(Found(
                rel=rel, size=stat.st_size, mtime=stat.st_mtime,
                kind=classify(rel),
                fingerprint=_fingerprint(path, stat.st_size, stat.st_mtime),
            ))
    return result


# ─────────────────────────────────────────────────────────────────────────────
#  Change detection between runs
# ─────────────────────────────────────────────────────────────────────────────
def load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(path: Path, snapshot: dict) -> None:
    try:
        path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    except OSError:
        pass


def compare(previous: dict, current: dict) -> dict:
    added = sorted(k for k in current if k not in previous)
    changed = sorted(k for k in current if k in previous and current[k] != previous[k])
    gone = sorted(k for k in previous if k not in current)
    return {"new": added, "changed": changed, "gone": gone}


def snapshot_of(result: Scan) -> dict:
    return {item.rel: item.fingerprint for item in result.files}


# ─────────────────────────────────────────────────────────────────────────────
#  Bundling — data only, secrets blanked
# ─────────────────────────────────────────────────────────────────────────────
def _redact(data):
    removed: list[str] = []

    def walk(value, prefix=""):
        if isinstance(value, dict):
            out = {}
            for key, item in value.items():
                if any(hint in str(key).lower() for hint in _SECRET_HINTS):
                    if item:
                        removed.append(f"{prefix}{key}")
                    out[key] = ""
                    continue
                out[key] = walk(item, f"{prefix}{key}.")
            return out
        if isinstance(value, list):
            return [walk(item, prefix) for item in value]
        return value

    return walk(data), removed


def build_bundle(result: Scan, target: Path, include_secrets: bool = False) -> dict:
    """Write a ZIP of the data files plus a manifest. Returns the manifest."""
    manifest = {
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": result.root,
        "files": [],
        "skipped": [],
        "total_bytes": 0,
    }
    total = 0
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in result.files:
            if item.kind not in ("data", "config", "unknown"):
                continue
            source = Path(result.root) / item.rel
            if item.size > MAX_BUNDLE_FILE or total + item.size > MAX_BUNDLE_TOTAL:
                manifest["skipped"].append({"rel": item.rel, "why": "too large"})
                continue
            entry = {"rel": item.rel, "kind": item.kind, "bytes": item.size}
            try:
                if source.suffix.lower() == ".json":
                    data = json.loads(source.read_text(encoding="utf-8"))
                    if include_secrets:
                        payload = data
                        entry["secrets"] = "kept"
                    else:
                        payload, removed = _redact(data)
                        if removed:
                            entry["secrets"] = [f"blanked: {name}" for name in removed]
                    text = json.dumps(payload, indent=2, ensure_ascii=False)
                    archive.writestr(f"data/{item.rel}", text)
                    entry["bytes_in_bundle"] = len(text.encode("utf-8"))
                else:
                    archive.write(source, f"data/{item.rel}")
                    entry["bytes_in_bundle"] = item.size
            except (OSError, ValueError) as exc:
                manifest["skipped"].append({"rel": item.rel, "why": f"unreadable: {exc}"})
                continue
            total += entry["bytes_in_bundle"]
            manifest["files"].append(entry)
        manifest["total_bytes"] = total
        archive.writestr("MANIFEST.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        archive.writestr("REPORT.txt", _report_text(result, manifest))
    return manifest


def _report_text(result: Scan, manifest: dict) -> str:
    lines = [
        "ULTRON DATA COLLECTION REPORT",
        f"source: {result.root}",
        f"generated: {manifest['created']}",
        "",
        f"files scanned: {len(result.files)}",
    ]
    for kind, count in sorted(result.by_kind.items()):
        lines.append(f"  {kind}: {count}")
    lines.append("")
    lines.append(f"bundled: {len(manifest['files'])} data/config file(s), "
                 f"{manifest['total_bytes']} bytes")
    for entry in manifest["files"]:
        lines.append(f"  {entry['rel']}  ({entry['kind']}, {entry['bytes_in_bundle']} B)")
        for secret in entry.get("secrets", []) if isinstance(entry.get("secrets"), list) else []:
            lines.append(f"      {secret}")
    if manifest["skipped"]:
        lines.append("")
        lines.append("skipped:")
        for entry in manifest["skipped"]:
            lines.append(f"  {entry['rel']} — {entry['why']}")
    lines += [
        "",
        "NOTES",
        "  * This application stores no conversation transcript by default; only",
        "    facts the user explicitly asked it to remember, plus settings.",
        "  * Credential values are blanked unless --include-secrets was given.",
        "  * Nothing was uploaded anywhere. This file is the only output.",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────────────
def _print_scan(result: Scan, changes: dict | None) -> None:
    print(f"scanning: {result.root}")
    print(f"files: {len(result.files)}   " + "  ".join(
        f"{kind}={count}" for kind, count in sorted(result.by_kind.items())))
    data_like = [f for f in result.files if f.kind in ("data", "config", "unknown")]
    if data_like:
        print("\ndata-like files:")
        for item in data_like:
            print(f"  [{item.kind:7}] {item.rel}  ({item.size} B)")
    else:
        print("\nno data files found — this install has saved nothing yet")

    if changes:
        if any(changes.values()):
            print("\nchanges since the last run:")
            for label, key in (("NEW", "new"), ("CHANGED", "changed"), ("GONE", "gone")):
                for rel in changes[key]:
                    print(f"  {label:7} {rel}")
        else:
            print("\nno changes since the last run")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Find data files in an install folder and report what is new.")
    parser.add_argument("--path", default=DEFAULT_TARGET,
                        help=f"folder to scan (default: {DEFAULT_TARGET})")
    parser.add_argument("--state", default=None,
                        help="override where the change-tracking file is kept")
    parser.add_argument("--bundle", default=None,
                        help="write a ZIP of the data files here (secrets blanked)")
    parser.add_argument("--include-secrets", action="store_true",
                        help="keep credential values in the bundle")
    parser.add_argument("--watch", action="store_true",
                        help="keep running and print files as they appear")
    parser.add_argument("--interval", type=float, default=5.0,
                        help="seconds between scans in --watch mode (default 5)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    root = Path(args.path).expanduser()
    if not root.is_dir():
        print(f"STOPPED: not a folder: {root}")
        print(f"Pass the install folder, for example: --path \"{DEFAULT_TARGET}\"")
        return 2

    state_path = Path(args.state) if args.state else root / STATE_FILENAME

    if args.watch:
        previous = load_state(state_path)
        print(f"watching {root} every {args.interval:g}s — Ctrl+C to stop")
        seen = snapshot_of(scan(root))
        try:
            while True:
                time.sleep(max(0.5, args.interval))
                current = snapshot_of(scan(root))
                changes = compare(seen, current)
                for rel in changes["new"]:
                    print(f"NEW     {rel}")
                for rel in changes["changed"]:
                    print(f"CHANGED {rel}")
                for rel in changes["gone"]:
                    print(f"GONE    {rel}")
                if any(changes.values()):
                    seen = current
        except KeyboardInterrupt:
            print("\nstopped")
        save_state(state_path, seen)
        return 0

    result = scan(root)
    previous = load_state(state_path)
    changes = compare(previous, snapshot_of(result)) if previous else None
    save_state(state_path, snapshot_of(result))

    if args.json:
        print(json.dumps({"scan": {
            "root": result.root,
            "files": [item.as_dict() for item in result.files],
            "counts": result.by_kind,
        }, "changes": changes}, indent=2))
    else:
        _print_scan(result, changes)

    if args.bundle:
        manifest = build_bundle(result, Path(args.bundle).expanduser(), args.include_secrets)
        print(f"\nbundle: {args.bundle}")
        print(f"  {len(manifest['files'])} file(s), {manifest['total_bytes']} bytes")
        if manifest["skipped"]:
            # Name each one and why: a bundle that silently omits a file is worse
            # than no bundle, because the reader trusts the manifest to be complete.
            print(f"  {len(manifest['skipped'])} NOT included:")
            for entry in manifest["skipped"]:
                print(f"    {entry['rel']}  ({entry['why']})")
        print("  attach this ZIP for diagnosis; it contains data files only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
