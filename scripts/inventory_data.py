"""scripts/inventory_data.py — what data does this install actually hold?

WHY THIS EXISTS
    Every file in `actions/` is code. So is everything in `core/`, `providers/`
    and `plugins/`. None of them contains a word the user ever said. When a
    folder looks like "the app", it is easy to assume the conversations live
    somewhere in it — and then to copy twenty .py files in the belief that the
    talks are inside.

    This script answers the question directly, from the filesystem, without
    printing a single value it finds: which data files exist, how large they
    are, how many records they hold, and — the answer that usually matters most
    — whether this build stored any conversation at all.

WHAT IT REPORTS
    <install>/config/api_keys.json     settings. Credential FIELDS named, never valued.
    <install>/memory/long_term.json    facts, preferences, projects, relationships,
                                       wishes, notes, and (older builds only) sessions
    <install>/memory/*.json            anything else memory code wrote there
    state/CustomMarkJarvis/*.json      approved insights, workspace selection
    state/CustomMarkJarvis/*.sqlite3   table names and row counts, opened read-only

WHAT IT NEVER DOES
    Writes nothing, opens the browser profile nothing, prints no memory text, no
    name, no key. `--json` gives the same report for a bug report.

HONEST LIMIT
    A transcript that was never written cannot be found by any script. In this
    build, `main.py::_save_session_summary` deliberately clears the in-RAM log
    instead of persisting it, so "conversations" is expected to read NONE. That
    is a design decision (manual memory only), not a missing file.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

MAX_JSON_BYTES = 32 * 1024 * 1024
_SECRET_HINTS = ("key", "token", "secret", "password", "credential")

# The categories long_term.json uses, per memory/memory_manager.py.
MEMORY_CATEGORIES = ("identity", "preferences", "projects", "relationships",
                     "wishes", "notes", "sessions")


def state_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "CustomMarkJarvis"
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "CustomMarkJarvis"


def _json_report(path: Path) -> dict:
    info = {"file": str(path), "bytes": path.stat().st_size, "kind": "json"}
    if info["bytes"] > MAX_JSON_BYTES:
        info["error"] = "too large to inspect"
        return info
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        info["error"] = f"unreadable: {type(exc).__name__}"
        return info
    if isinstance(data, dict):
        info["keys"] = sorted(str(k) for k in data.keys())
        info["records"] = len(data)
        counts = {}
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                counts[key] = len(value)
            else:
                counts[key] = 1
        info["record_counts"] = counts
        secret_fields = [k for k in info["keys"] if any(h in k.lower() for h in _SECRET_HINTS)]
        if secret_fields:
            info["credential_fields"] = secret_fields
            info["credential_fields_present"] = sum(
                1 for k in secret_fields if data.get(k)
            )
    elif isinstance(data, list):
        info["keys"] = []
        info["records"] = len(data)
    return info


def _sqlite_report(path: Path) -> dict:
    info = {"file": str(path), "bytes": path.stat().st_size, "kind": "sqlite"}
    try:
        uri = f"file:{path.as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        try:
            tables = [row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            counts = {}
            for table in tables:
                try:
                    counts[table] = connection.execute(
                        f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                except sqlite3.Error:
                    counts[table] = None
            info["tables"] = counts
            info["records"] = sum(v for v in counts.values() if isinstance(v, int))
        finally:
            connection.close()
    except sqlite3.Error as exc:
        info["error"] = f"unreadable: {exc}"
    return info


def inventory(install: Path, state: Path | None = None) -> dict:
    report: dict = {"install": str(install), "state": str(state or state_dir()), "files": []}
    state = Path(state or state_dir())

    candidates: list[Path] = [
        install / "config" / "api_keys.json",
        install / "memory" / "long_term.json",
    ]
    memory_dir = install / "memory"
    if memory_dir.is_dir():
        candidates += [p for p in sorted(memory_dir.glob("*.json"))
                       if p.name != "long_term.json"]

    for path in candidates:
        if path.exists() and path.is_file():
            report["files"].append(_json_report(path))

    if state.is_dir():
        for path in sorted(state.iterdir()):
            if not path.is_file():
                continue
            if path.suffix.lower() == ".json":
                report["files"].append(_json_report(path))
            elif path.suffix.lower() in (".sqlite3", ".db"):
                report["files"].append(_sqlite_report(path))

    # ── the answer everybody actually wants ─────────────────────────────────
    memory_file = next((f for f in report["files"]
                        if Path(f["file"]).name == "long_term.json"), None)
    counts = (memory_file or {}).get("record_counts", {})
    sessions = counts.get("sessions", 0) if memory_file else 0
    facts = sum(counts.get(k, 0) for k in MEMORY_CATEGORIES if k != "sessions")
    report["summary"] = {
        "data_files_found": len(report["files"]),
        "conversation_summaries": sessions,
        "saved_facts": facts,
        "verdict": (
            "no conversation history is stored in this install"
            if sessions == 0
            else f"{sessions} session summar{'y' if sessions == 1 else 'ies'} stored"
        ),
    }
    return report


def print_human(report: dict) -> None:
    print(f"install : {report['install']}")
    print(f"state   : {report['state']}")
    if not report["files"]:
        print("\nNo data files found. This install has not saved anything yet.")
        return
    print("\nDATA FILES (names, sizes and counts only — no values are printed)")
    for info in report["files"]:
        name = Path(info["file"])
        print(f"\n  {name}  ({info['bytes']} bytes)")
        if "error" in info:
            print(f"    ! {info['error']}")
            continue
        if info["kind"] == "sqlite":
            for table, rows in (info.get("tables") or {}).items():
                print(f"    table {table}: {rows} rows")
            continue
        print(f"    keys: {', '.join(info.get('keys') or []) or '(none)'}")
        for key, count in (info.get("record_counts") or {}).items():
            print(f"      {key}: {count}")
        if info.get("credential_fields"):
            print(f"    credential fields present: {', '.join(info['credential_fields'])}"
                  f" ({info.get('credential_fields_present', 0)} filled)")
    summary = report["summary"]
    print("\nSUMMARY")
    print(f"  data files found      : {summary['data_files_found']}")
    print(f"  conversation summaries: {summary['conversation_summaries']}")
    print(f"  saved memory entries  : {summary['saved_facts']}")
    print(f"  -> {summary['verdict']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report which data files an install holds, without printing values.")
    parser.add_argument("--install", default=str(Path(__file__).resolve().parents[1]),
                        help="install folder (default: this install)")
    parser.add_argument("--state", default=None,
                        help="override the CustomMarkJarvis state folder")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    install = Path(args.install).expanduser()
    if not install.is_dir():
        print(f"STOPPED: not a folder: {install}")
        return 2
    report = inventory(install, Path(args.state).expanduser() if args.state else None)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_human(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
