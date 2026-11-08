"""custom_jarvis/selfupdate.py — update from GitHub without losing the session.

The owner asked for this chain:

    a small self-evolution happens
      → Ultron ships it to GitHub
      → Ultron updates itself *from* GitHub
      → the working session is not lost

The last step is where a wall exists, and it is worth naming before the code.

**The wall.** Python cannot replace arbitrary code in a running process. A module
that is already imported stays the version it was; reloading it moves functions
but not the objects that already hold them. A live class cannot gain a method
that a running instance is bound to. Anyone who says otherwise is describing a
development server that restarts, not an application that does not.

So this module does the honest version, in three parts:

1. **Update the files.** `git pull --ff-only` from the remote. Never a merge the
   assistant invented; a divergence is a refusal with a sentence.
2. **Reload what is genuinely safe to reload.** Everything data-driven: skill
   packs (JSON), the tool catalog, the settings. Those are read from disk each
   time they are needed, so they take a new version with no process restart.
3. **Ask for the restart only when it is really needed.** Changed action/plugin
   leaves are staged by the running app at its next reconnect boundary; they do
   not interrupt a tool call. Other `.py` changes still require a process restart.
   The update is verified, a marker names files that need restart, and one sentence
   says so: session state is in files, so a restart resumes rather than starts over.

If the new code fails verification, the update is **reverted** to the commit it
came from. A self-update that leaves the machine on code that does not parse is
worse than no self-update.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Callable

TIMEOUT = 120.0
MARKER = "restart-required.json"


def _is_reloadable_leaf(path: str) -> bool:
    """Action/plugin Python leaves are staged by the app at a reconnect boundary."""
    normalized = path.replace("\\", "/")
    return (normalized.endswith(".py") and normalized.split("/")[-1] != "__init__.py"
            and normalized.startswith(("actions/", "plugins/")))


def _code_file_groups(code_files: list[str]) -> tuple[list[str], list[str], bool]:
    leaf_files = [name for name in code_files if _is_reloadable_leaf(name)]
    restart_files = [name for name in code_files if name not in leaf_files]
    return leaf_files, restart_files, bool(leaf_files) and not restart_files


def _update_note(restart_required: bool, leaf_files: list[str]) -> str:
    if restart_required:
        leaf_note = (" Action/plugin files stay inactive until that restart."
                     if leaf_files else "")
        return ("Updated. Non-leaf code is on disk; a restart is required before "
                "it runs, and the session state survives it because it lives in "
                "files, not in memory." + leaf_note)
    if leaf_files:
        return ("Updated. Action/plugin code will be staged at the next provider "
                "reconnect boundary; no process restart is needed.")
    return "Updated and reloaded. No restart needed: only data changed."


def _run(args: list[str], cwd: Path, secret: str = "") -> tuple[int, str, str]:
    try:
        done = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True,
                              timeout=TIMEOUT, shell=False, stdin=subprocess.DEVNULL)
        out, err = done.stdout, done.stderr
    except (OSError, subprocess.SubprocessError) as error:
        return 2, "", str(error)
    if secret:
        out, err = out.replace(secret, "***"), err.replace(secret, "***")
    return done.returncode, out.strip(), err.strip()


class Updater:
    """Pull a new version from the remote and say exactly what it can take."""

    def __init__(self, repo: Path | str, token: str = "", remote: str = "origin",
                 marker: Path | str | None = None,
                 reload_hooks: list[Callable[[], dict]] | None = None) -> None:
        self.repo = Path(repo)
        self.token = token or ""
        self.remote = remote or "origin"
        self.marker = Path(marker) if marker else self._default_marker()
        self.hooks = list(reload_hooks or [])

    def _default_marker(self) -> Path:
        """The marker goes in the state folder, never in the repository.

        A file written into the tree is untracked, which makes the tree dirty,
        which makes the NEXT update refuse to pull — and a marker file could be
        shipped to GitHub by accident. Beside the state is where it belongs.
        """
        try:
            from core.paths import state_dir
            return state_dir() / MARKER
        except Exception:                                      # noqa: BLE001
            return Path.home() / MARKER

    def git(self, *args: str) -> tuple[int, str, str]:
        return _run(["git", *args], self.repo, self.token)

    def branch(self) -> str:
        code, out, _ = self.git("rev-parse", "--abbrev-ref", "HEAD")
        return out if code == 0 and out and out != "HEAD" else "main"

    # ------------------------------------------------------------------ check
    def check(self) -> dict:
        """Is there a newer commit on the remote, and what does it touch?"""
        branch = self.branch()
        code, out, err = self.git("fetch", self.remote, branch)
        if code != 0:
            return {"ok": False, "note": f"I could not reach the remote: {err or out}",
                    "behind": 0}
        code, out, _ = self.git("rev-list", "--count", f"HEAD..{self.remote}/{branch}")
        behind = int(out) if code == 0 and out.isdigit() else 0
        files: list[str] = []
        if behind:
            files = [row for row in self.git("diff", "--name-only",
                                             f"HEAD..{self.remote}/{branch}")[1].splitlines()
                     if row]
        code, local, _ = self.git("rev-parse", "--short", "HEAD")
        code, remote, _ = self.git("rev-parse", "--short", f"{self.remote}/{branch}")
        return {"ok": True, "branch": branch, "behind": behind, "files": files,
                "local": local, "remote": remote,
                "note": (f"{behind} new commit(s) on {self.remote}/{branch}" if behind
                         else "This copy is up to date.")}

    def _mark_restart_if_needed(self, before: str, files: list[str],
                                leaf_reload_deferred: bool = False) -> None:
        if files:
            self._write_marker({"at": time.strftime("%Y-%m-%d %H:%M:%S"),
                                "from": before[:7],
                                "to": self.git("rev-parse", "--short", "HEAD")[1],
                                "files": files[:40],
                                "leaf_reload_deferred": bool(leaf_reload_deferred)})

    # ------------------------------------------------------------------ apply
    def apply(self, verify: Callable[[], dict] | None = None) -> dict:
        """Pull, verify, reload what is safe, and ask for a restart only if needed."""
        dirty = self.git("status", "--porcelain")[1]
        if dirty:
            return {"ok": False, "stage": "dirty", "note":
                    "The working tree has uncommitted changes, so I will not pull over "
                    "them. Ship or discard them first."}
        ahead = self.check()
        if not ahead.get("ok"):
            return {"ok": False, "stage": "check", "note": ahead["note"]}
        if not ahead["behind"]:
            return {"ok": True, "stage": "up-to-date", "note": ahead["note"],
                    "restart_required": False, "files": []}

        before = self.git("rev-parse", "HEAD")[1]
        branch = ahead["branch"]
        code, out, err = self.git("pull", "--ff-only", self.remote, branch)
        if code != 0:
            return {"ok": False, "stage": "pull", "note": f"I could not pull: {err or out}",
                    "files": ahead["files"]}

        if verify is not None:
            result = verify() or {}
            if not result.get("ok", True):
                self.git("reset", "--hard", before)
                return {"ok": False, "stage": "verify", "reverted_to": before[:7],
                        "note": ("The new version failed its own checks, so I put the "
                                 "previous one back. " + str(result.get("note", ""))),
                        "files": ahead["files"]}

        code_files = [name for name in ahead["files"] if name.endswith(".py")]
        leaf_files, restart_files, leaf_reload_pending = _code_file_groups(code_files)
        data_files = [name for name in ahead["files"] if not name.endswith(".py")]
        reloaded = {}
        for hook in self.hooks:
            try:
                reloaded[getattr(hook, "__name__", "hook")] = hook()
            except Exception as error:                         # noqa: BLE001
                reloaded[getattr(hook, "__name__", "hook")] = {"ok": False,
                                                               "note": str(error)}
        restart = bool(restart_files)
        leaf_reload_deferred = bool(restart and leaf_files)
        self._mark_restart_if_needed(before, restart_files, leaf_reload_deferred)
        note = _update_note(restart, leaf_files)
        return {"ok": True, "stage": "updated", "restart_required": restart,
                "leaf_reload_pending": leaf_reload_pending,
                "leaf_reload_deferred": leaf_reload_deferred,
                "files": ahead["files"], "code_files": code_files,
                "leaf_files": leaf_files, "restart_files": restart_files,
                "data_files": data_files, "reloaded": reloaded, "note": note}

    def restart_marker(self) -> dict:
        try:
            return json.loads(self.marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def leaf_reload_deferred(self) -> bool:
        """Whether a mixed update must keep disk leaves inactive until restart."""
        return bool(self.restart_marker().get("leaf_reload_deferred"))

    def mark_process_started(self) -> bool:
        """Clear the defer flag after a fresh process has loaded the updated code."""
        marker = self.restart_marker()
        deferred = bool(marker.get("leaf_reload_deferred"))
        if deferred:
            marker["leaf_reload_deferred"] = False
            self._write_marker(marker)
        return deferred

    def clear_marker(self) -> None:
        try:
            self.marker.unlink()
        except OSError:
            pass

    def _write_marker(self, data: dict) -> None:
        try:
            self.marker.write_text(json.dumps(data, indent=1), encoding="utf-8")
        except OSError:
            pass

    def restart_command(self) -> dict:
        """What to run to come back with the new code, keeping the same state."""
        launcher = self.repo / "run.ps1" if (self.repo / "run.ps1").exists() else None
        return {"ok": bool(launcher), "command": (r".\run.ps1" if launcher else
                                                  "python main.py"),
                "note": ("Close Ultron and run this again. Your memory, workspace and "
                         "ledger are files, so the next start continues the session "
                         "instead of beginning a new one.")}
