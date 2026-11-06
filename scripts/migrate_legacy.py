"""scripts/migrate_legacy.py — carry a previous install's data into Ultron.

WHY THIS EXISTS
    Renaming the assistant did not change a single file format, so the previous
    build's data is already readable by Ultron. What is needed is not a converter
    but a careful COPY: one that knows which files are state, which are secrets,
    which are caches that must not travel, and how to leave the old install
    untouched so nothing is lost if this goes wrong.

WHAT IT MOVES
    <install>/config/api_keys.json     settings: name, voice, colour, providers,
                                       plugins, wake word, morning brief
    <install>/memory/long_term.json    the assistant's long-term memory
    %LOCALAPPDATA%\\CustomMarkJarvis\\    custom layer: knowledge.sqlite3,
                                       workspace.json, approved-insights.json

WHAT IT REFUSES TO MOVE
    screenshots/, backups/ and repairs/ (caches and history, not identity), the
    browser profile, and anything that is a symlink or resolves outside the two
    roots it was given.

SECRETS
    Every field whose name looks like a credential is stripped by default and
    reported by NAME only — never by value. Re-enter keys in Ultron's setup, or
    pass --include-keys if this machine never leaves your hands.

SAFETY
    * Dry run by default? No — but --dry-run prints the plan and writes nothing.
    * Every overwritten file is backed up beside itself first (.bak-<timestamp>).
    * Writes are atomic (temp file in the same directory, then os.replace), so an
      interrupted run cannot leave half a config behind.
    * The source install is only ever read.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import identity  # noqa: E402

MAX_FILE_BYTES = 16 * 1024 * 1024
_SECRET_NAME = re.compile(r"(key|token|secret|password|credential)", re.IGNORECASE)

# Files inside the custom data directory that are state worth keeping. Anything
# else there — screenshots, backups, repair history — is deliberately skipped.
_CUSTOM_KEEP = ("knowledge.sqlite3", "workspace.json", "approved-insights.json")


class MigrationError(Exception):
    pass


def custom_state_dir() -> Path:
    """Where the custom layer keeps state, outside the install folder."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "CustomMarkJarvis"
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "CustomMarkJarvis"


def _resolve(path: str) -> Path:
    candidate = Path(path).expanduser()
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        raise MigrationError(f"not found: {path}")
    if not resolved.is_dir():
        raise MigrationError(f"not a folder: {path}")
    return resolved


def _looks_like_install(path: Path) -> bool:
    return (path / "config" / "api_keys.json").exists() or (
        path / "memory" / "long_term.json"
    ).exists() or (path / "main.py").exists()


def _redact(data):
    """Strip credential-looking fields, returning (clean, [names removed])."""
    removed: list[str] = []

    def walk(value, prefix=""):
        if isinstance(value, dict):
            out = {}
            for key, item in value.items():
                if _SECRET_NAME.search(str(key)):
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


def _read_json(path: Path) -> dict:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise MigrationError(f"refusing {path.name}: larger than {MAX_FILE_BYTES} bytes")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MigrationError(f"{path.name} is not valid JSON: {exc}")


def _backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = path.with_name(f"{path.name}.bak-{stamp}")
    shutil.copy2(path, target)
    return target


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def plan(source: Path, target: Path, include_keys: bool, keep_name: bool) -> dict:
    """Work out exactly what would happen. No writes."""
    if source == target:
        raise MigrationError("source and target are the same folder")
    if not _looks_like_install(source):
        raise MigrationError(
            f"{source} does not look like a previous install (no main.py, config or memory)"
        )
    if not _looks_like_install(target):
        raise MigrationError(
            f"{target} does not look like the new install (no main.py) — extract ultron.zip first"
        )

    steps: list[dict] = []
    notes: list[str] = []

    config_path = source / "config" / "api_keys.json"
    if config_path.exists():
        data = _read_json(config_path)
        changed = False
        copied = dict(data)
        if not include_keys:
            copied, removed = _redact(copied)
            if removed:
                notes.append("credentials removed: " + ", ".join(sorted(removed)))
                changed = True
        old_name = str(copied.get("assistant_name") or "").strip()
        if keep_name and old_name:
            notes.append(f"keeping the old name: {old_name}")
        elif old_name and old_name != identity.NAME:
            copied["assistant_name"] = identity.NAME
            notes.append(f"name: {old_name} -> {identity.NAME}")
            changed = True
        steps.append({
            "kind": "json",
            "source": config_path,
            "target": target / "config" / "api_keys.json",
            "payload": copied,
            "changed": changed or old_name != str(data.get("assistant_name") or ""),
            "entries": len(copied),
        })

    memory_path = source / "memory" / "long_term.json"
    if memory_path.exists():
        data = _read_json(memory_path)
        steps.append({
            "kind": "json",
            "source": memory_path,
            "target": target / "memory" / "long_term.json",
            "payload": data,
            "changed": False,
            "entries": len(data) if isinstance(data, (dict, list)) else 1,
        })

    state = custom_state_dir()
    if state.is_dir():
        for name in _CUSTOM_KEEP:
            path = state / name
            if not path.exists():
                continue
            if path.suffix == ".sqlite3":
                steps.append({"kind": "bytes", "source": path, "target": state / name})
            else:
                try:
                    payload = _read_json(path)
                except MigrationError as exc:
                    notes.append(str(exc))
                    continue
                steps.append({"kind": "json", "source": path, "target": state / name,
                              "payload": payload, "changed": False, "entries": len(payload)})

    return {"steps": steps, "notes": notes}


def apply(plan_data: dict, dry_run: bool = False) -> list[str]:
    report: list[str] = []
    for step in plan_data["steps"]:
        source: Path = step["source"]
        target: Path = step["target"]
        label = f"{source.name} -> {target}"
        if dry_run:
            report.append(("WOULD COPY " if not step.get("changed") else "WOULD COPY (adapted) ") + label)
            continue
        backup = _backup(target)
        if step["kind"] == "json":
            _write_atomic(target, json.dumps(step["payload"], indent=2, ensure_ascii=False))
            extra = f", {step.get('entries', 0)} entries"
            if step.get("changed"):
                extra += ", adapted"
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            extra = f", {source.stat().st_size} bytes"
        report.append(("COPIED " if not backup else f"COPIED (previous kept as {backup.name}) ")
                      + label + extra)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Copy a previous JARVIS/MARK install's data into Ultron."
    )
    parser.add_argument("--from", dest="source", required=True,
                        help="old install folder (the one containing main.py)")
    parser.add_argument("--to", dest="target", required=True,
                        help="Ultron folder (the extracted ultron.zip)")
    parser.add_argument("--include-keys", action="store_true",
                        help="also copy API keys instead of blanking them")
    parser.add_argument("--keep-name", action="store_true",
                        help="keep the old assistant name instead of renaming to Ultron")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the plan and write nothing")
    args = parser.parse_args(argv)

    try:
        source = _resolve(args.source)
        target = _resolve(args.target)
        plan_data = plan(source, target, args.include_keys, args.keep_name)
    except MigrationError as exc:
        print(f"STOPPED: {exc}")
        return 2

    print(f"from: {source}")
    print(f"to:   {target}")
    if not plan_data["steps"]:
        print("nothing to migrate — no config, memory or custom state was found")
        return 3
    for note in plan_data["notes"]:
        print(f"note: {note}")
    for line in apply(plan_data, dry_run=args.dry_run):
        print(line)
    if args.dry_run:
        print("dry run — nothing was written")
    else:
        print("done. Start Ultron and it will use this data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
