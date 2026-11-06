"""Bounded file verification and conflict-aware write backups."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

MAX_FILE_BYTES = 8 * 1024 * 1024


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bounded_text(path: Path) -> str:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("File exceeds the 8 MB inspection/backup limit")
    return path.read_text(encoding="utf-8")


class BackupManager:
    """Back up approved text writes. Does not undo shell/GUI/external actions."""

    def __init__(
        self,
        directory: Path,
        max_backups: int = 100,
        max_bytes: int = 512 * 1024 * 1024,
    ) -> None:
        if max_backups < 1 or max_bytes < MAX_FILE_BYTES:
            raise ValueError("Backup retention must allow at least one 8 MB file")
        self.transactions = {}
        self.last_transaction_id = None
        self.transaction_lock = threading.RLock()
        self.directory = directory
        self.max_backups = max_backups
        self.max_bytes = max_bytes
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _prune(self, incoming_bytes: int) -> None:
        folders = sorted(
            (
                p
                for p in self.directory.iterdir()
                if p.is_dir()
                and not p.is_symlink()
                and len(p.name) == 32
                and all(ch in "0123456789abcdef" for ch in p.name)
            ),
            key=lambda p: p.stat().st_mtime,
        )
        sizes = {
            p: sum(f.stat().st_size for f in p.iterdir() if f.is_file())
            for p in folders
        }
        total = sum(sizes.values())
        while folders and (
            len(folders) >= self.max_backups or total + incoming_bytes > self.max_bytes
        ):
            oldest = folders.pop(0)
            total -= sizes[oldest]
            shutil.rmtree(oldest)

    def prepare(self, path: Path) -> tuple[str, str]:
        old = bounded_text(path) if path.exists() else ""
        self._prune(path.stat().st_size if path.exists() else 0)
        identity = uuid.uuid4().hex
        folder = self.directory / identity
        folder.mkdir(mode=0o700)
        existed = path.exists()
        if existed:
            shutil.copy2(path, folder / "before")
        manifest = {
            "path": str(path),
            "existed": existed,
            "after_sha256": None,
            "before_sha256": file_digest(folder / "before") if existed else None,
        }
        (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return identity, old

    def finish(self, identity: str, path: Path) -> None:
        folder = self._folder(identity)
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        manifest["after_sha256"] = file_digest(path)
        (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def _folder(self, identity: str) -> Path:
        if len(identity) != 32 or any(ch not in "0123456789abcdef" for ch in identity):
            raise ValueError("Invalid backup ID")
        return self.directory / identity

    def restore(self, identity: str, workspace: Path) -> dict[str, Any]:
        folder = self._folder(identity)
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        path = Path(manifest["path"]).resolve()
        if not path.is_relative_to(workspace.resolve()):
            raise ValueError("Backup target is outside the selected workspace")
        if not path.is_file() or file_digest(path) != manifest["after_sha256"]:
            raise ValueError(
                "Restore blocked: target changed since this write or backup was incomplete"
            )
        if manifest["existed"]:
            if file_digest(folder / "before") != manifest.get("before_sha256"):
                raise ValueError(
                    "Restore blocked: backup contents changed or are corrupt"
                )
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                temporary = Path(stream.name)
            try:
                shutil.copy2(folder / "before", temporary)
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        else:
            path.unlink()
        return {"path": str(path), "restored": True, "backup_id": identity}

    def begin_transaction(self):
        with self.transaction_lock:
            identity = uuid.uuid4().hex
            self.transactions[identity] = []
            self.last_transaction_id = identity
            return identity

    def record_in_transaction(self, tx_id, backup_id):
        with self.transaction_lock:
            if tx_id not in self.transactions:
                raise ValueError("Unknown transaction")
            self._folder(backup_id)
            self.transactions[tx_id].append(backup_id)

    def rollback_transaction(self, tx_id, workspace):
        with self.transaction_lock:
            if tx_id not in self.transactions:
                raise ValueError("Unknown transaction")
            ids = list(self.transactions[tx_id])
            restored, conflicts = [], []
            for backup_id in reversed(ids):
                try:
                    restored.append(self.restore(backup_id, workspace))
                    self.transactions[tx_id].remove(backup_id)
                except (ValueError, OSError, KeyError) as exc:
                    conflicts.append({"backup_id": backup_id, "error": str(exc)})
            return {
                "transaction_id": tx_id,
                "restored_files": restored,
                "conflicts": conflicts,
            }


class TransactionBatch:
    def __init__(self, backups):
        self.backups = backups
        self.identity = backups.begin_transaction()

    def record(self, backup_id):
        self.backups.record_in_transaction(self.identity, backup_id)

    def rollback(self, workspace):
        return self.backups.rollback_transaction(self.identity, workspace)
