"""custom_jarvis/ship.py — sending the work to GitHub without sending a secret.

The owner asked for one rule and one refusal:

    rule      every self-evolution, however small, is shipped to GitHub
    refusal   a push that would publish a key never happens

So this module does the unglamorous part in a fixed order, and it stops at the
first thing that is not true:

    1. scan       every tracked file, for assignment-shaped secrets
    2. guard      the ignore rules still protect the config and the memory file
    3. check      every changed Python file still parses; optionally the full gate
    4. commit     one structured message: what changed, why, what proves it
    5. push       fast-forward only, never forced, token used once and not stored

Two design decisions worth knowing before you change anything here:

- **The token is never a file in this repository.** It comes from `GITHUB_TOKEN`
  in the environment, or `github_token` in `config/api_keys.json` (which is
  ignored by git), or a file in the state directory outside the tree. It is put
  into one push URL, the command's output is scrubbed of it, and it is not
  written anywhere else.
- **A push is never silent about its branch.** The branch is read from git, the
  remote is read from git, and a divergence is a refusal with a sentence — not a
  force-push, and not a merge this assistant invented at 3 a.m.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

TIMEOUT = 120.0
SHIP_LOG = "ship_log.json"
MAX_LOG = 100

# Assignment-shaped secrets: `key = "..."`, `token: "..."`. Deliberately narrow.
# A broad pattern produces false alarms on tests and prose, and a check that
# always fires is a check nobody reads.
_SECRET = re.compile(
    r"""(?ix)
    \b (?: api[_-]?key | secret | token | passwd | password | access[_-]?key )
    \s* [:=] \s* ["'] (?! < | \$ | \{ | x{4, } | X{4, } ) [A-Za-z0-9_\-./+=]{16,} ["']
    """)

# A GitHub token has a shape. Catch it anywhere, quoted or not.
_TOKEN_SHAPES = (
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"sk-[A-Za-z0-9]{32,}"),
    re.compile(r"AIza[A-Za-z0-9_\-]{30,}"),
)

# Values that are obviously placeholders. A scanner that cries wolf on a test
# fixture is a scanner people learn to ignore, and an ignored scanner is worse
# than none: it makes the real hit look like the noise.
PLACEHOLDER = ("secret", "test", "fake", "example", "sample", "dummy", "probe",
               "placeholder", "xxxx", "abcd", "1234", "your", "todo", "changeme")

_PORCELAIN = re.compile(r"^.{1,2}\s+(.+)$")

# A fixture must look like a key to be a fixture, so the exemption is written on
# the line, in a spelling other secret scanners already understand.
_ALLOW = re.compile(r"gitleaks:allow|pragma:\s*allowlist\s*secret", re.IGNORECASE)


def _allowed(line: str) -> bool:
    return bool(_ALLOW.search(line))

SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules", "dist", "build",
             ".pytest_cache", ".mypy_cache", ".ruff_cache", "verification"}
SKIP_SUFFIX = {".pyc", ".pyo", ".so", ".dll", ".pyd", ".png", ".jpg", ".jpeg",
               ".gif", ".ico", ".wav", ".mp3", ".mp4", ".zip", ".whl", ".ttf"}


def _run(args: list[str], cwd: Path, secret: str = "") -> tuple[int, str, str]:
    """Run git. No shell, bounded time, and the token scrubbed from the output."""
    try:
        done = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True,
                              timeout=TIMEOUT, shell=False, stdin=subprocess.DEVNULL)
        out, err = done.stdout, done.stderr
    except (OSError, subprocess.SubprocessError) as error:
        return 2, "", str(error)
    if secret:
        for text in (secret,):                     # never echo a credential, ever
            out, err = out.replace(text, "***"), err.replace(text, "***")
    return done.returncode, out.strip(), err.strip()


def _looks_real(value: str) -> bool:
    """False for a value that says, in the value itself, that it is not real."""
    lowered = value.lower()
    return not any(marker in lowered for marker in PLACEHOLDER)


def find_secret(text: str) -> str:
    """The first *real* secret-shaped thing in `text`, or an empty string."""
    for pattern in _TOKEN_SHAPES:
        for match in pattern.finditer(text):
            candidate = match.group(0)
            # A real fine-grained token is 80 characters or more. Past 60, the
            # placeholder filter stops being a useful filter and starts being a
            # way to miss the one hit that matters.
            if len(candidate) > 60 or _looks_real(candidate):
                return candidate[:8] + "…"
    for match in _SECRET.finditer(text):
        if _looks_real(match.group(0)):
            return match.group(0)[:24] + "…"
    return ""


class Shipper:
    """Commit and push this repository, carefully."""

    def __init__(self, repo: Path | str, token: str = "", remote: str = "origin",
                 log_path: Path | str | None = None) -> None:
        self.repo = Path(repo)
        self.token = token or ""
        self.remote = remote or "origin"
        self.log_path = Path(log_path) if log_path else None

    # ------------------------------------------------------------------- facts
    def git(self, *args: str) -> tuple[int, str, str]:
        return _run(["git", *args], self.repo, self.token)

    def has_git(self) -> bool:
        return self.git("rev-parse", "--git-dir")[0] == 0

    def branch(self) -> str:
        code, out, _ = self.git("rev-parse", "--abbrev-ref", "HEAD")
        return out if code == 0 and out and out != "HEAD" else "main"

    def changed(self) -> list[str]:
        """The files git says are different. Parsed by pattern, not by column.

        Slicing a porcelain line at a fixed offset looked fine and was wrong: the
        whole output is stripped, so the FIRST line loses its leading space and
        every other line does not. `app.py` became `pp.py`, the syntax check
        looked at a file that does not exist, and a broken module shipped. A
        pattern that accepts either shape cannot make that mistake.
        """
        code, out, _ = self.git("status", "--porcelain")
        if code != 0:
            return []
        names = []
        for line in out.splitlines():
            match = _PORCELAIN.match(line)
            if not match:
                continue
            path = match.group(1).strip()
            if " -> " in path:                     # a rename shows both names
                path = path.split(" -> ")[-1]
            path = path.strip().strip('"')
            if path:
                names.append(path)
        return names

    def status(self) -> dict:
        ahead = behind = 0
        code, out, _ = self.git("rev-list", "--left-right", "--count",
                                f"{self.remote}/{self.branch()}...HEAD")
        if code == 0 and out:
            parts = out.split()
            if len(parts) == 2:
                behind, ahead = int(parts[0]), int(parts[1])
        return {"is_repository": self.has_git(), "branch": self.branch(),
                "changed": self.changed(), "ahead": ahead, "behind": behind,
                "remote": self.remote, "token": bool(self.token),
                "ready": bool(self.token) and self.has_git()}

    # -------------------------------------------------------------------- scan
    def scan(self) -> dict:
        """Every file that would be published, checked for a secret.

        A line that carries `gitleaks:allow` (or the equivalent
        `pragma: allowlist secret`) is skipped, and the number of such lines is
        reported. Test fixtures have to look like keys — that is the point of
        them — so the honest answer is an explicit, counted exemption written on
        the line itself, not a smarter pattern that ends up ignoring real keys.
        """
        hits = []
        allowed = 0
        files = 0
        for path in sorted(self.repo.rglob("*")):
            if not path.is_file():
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.suffix.lower() in SKIP_SUFFIX:
                continue
            if path.stat().st_size > 400_000:
                continue
            files += 1
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            rows = text.splitlines()
            found = find_secret("\n".join(line for line in rows if not _allowed(line)))
            if not found:
                allowed += sum(1 for line in rows if _ALLOW.search(line) and find_secret(line))
                continue
            lines = [index for index, line in enumerate(rows, 1)
                     if find_secret(line) and not _allowed(line)]
            allowed += sum(1 for line in rows if _ALLOW.search(line) and find_secret(line))
            hits.append({"file": str(path.relative_to(self.repo)),
                         "lines": lines[:3], "shape": found})
        return {"files": files, "hits": hits, "allowed": allowed, "clean": not hits}

    def guards(self) -> dict:
        """The ignore rules that must still hold before anything is published."""
        required = ["config/api_keys.json", "memory/long_term.json"]
        problems = []
        for name in required:
            code, _out, _err = self.git("check-ignore", "-q", name)
            if code != 0:
                problems.append(f"{name} is not ignored by git — a push would publish it")
        tracked = self.git("ls-files")[1].splitlines()
        for name in required:
            if any(row.startswith(name) for row in tracked):
                problems.append(f"{name} is tracked by git — remove it before shipping")
        return {"ok": not problems, "problems": problems}

    def check_syntax(self, files: list[str] | None = None) -> dict:
        """Every changed Python file must still parse. Cheap, and catches the worst."""
        wanted = [name for name in (files if files is not None else self.changed())
                  if str(name).endswith(".py")]
        broken = []
        for name in wanted:
            path = self.repo / name
            if not path.is_file():
                continue
            try:
                compile(path.read_text(encoding="utf-8", errors="replace"), str(path), "exec")
            except SyntaxError as error:
                broken.append(f"{name}:{error.lineno}: {error.msg}")
        return {"checked": len(wanted), "broken": broken, "ok": not broken}

    # ------------------------------------------------------------------ commit
    def commit(self, message: str, extra: str = "") -> dict:
        subject = " ".join(str(message or "").split())[:72]
        if not subject:
            return {"ok": False, "note": "A ship needs a message that says what changed."}
        self.git("add", "-A")
        staged = self.git("diff", "--cached", "--name-only")[1].splitlines()
        if not staged:
            return {"ok": False, "note": "There is nothing to ship: the tree is unchanged.",
                    "files": []}
        body = [subject, ""]
        if extra:
            body += [extra.strip(), ""]
        body += ["Files:", *[f"  {name}" for name in staged[:40]]]
        if len(staged) > 40:
            body.append(f"  … and {len(staged) - 40} more")
        # A machine with no git identity cannot commit, and failing there would
        # look like a bug in shipping. A local identity is used only when the
        # person has not set one — never in place of a real one.
        identity = []
        if self.git("config", "user.email")[1].strip() == "":
            identity = ["-c", "user.name=Ultron", "-c", "user.email=ultron@localhost"]
        code, out, err = self.git(*identity, "commit", "-m", body[0],
                                  "-m", "\n".join(body[2:]))
        if code != 0:
            return {"ok": False, "note": f"git commit failed: {err or out}", "files": staged}
        return {"ok": True, "files": staged, "note": f"Committed {len(staged)} file(s).",
                "commit": self.git("rev-parse", "--short", "HEAD")[1]}

    # -------------------------------------------------------------------- push
    def remote_url(self) -> str:
        code, out, _ = self.git("remote", "get-url", self.remote)
        if code == 0 and out:
            return out
        return ""

    def push(self) -> dict:
        """Fast-forward only. A divergence is a refusal, never a force."""
        if not self.token:
            return {"ok": False, "note": ("I have no GitHub token, so I cannot push. "
                                          "Set `github_token` in config, or GITHUB_TOKEN.")}
        url = self.remote_url()
        if not url:
            return {"ok": False, "note": "This repository has no remote called "
                                         f"'{self.remote}'."}
        branch = self.branch()
        code, out, err = self.git("fetch", self.remote, branch)
        if code != 0:
            return {"ok": False, "note": f"I could not reach the remote: {err or out}"}
        code, _out, _err = self.git("merge-base", "--is-ancestor",
                                    f"{self.remote}/{branch}", "HEAD")
        if code != 0:
            return {"ok": False, "note": ("The remote has work this copy does not have. "
                                          "I will not force it: pull first, then ship.")}
        secret_url = re.sub(r"^(https://)([^@/]+@)?", r"\1x-access-token:" + self.token + "@", url)
        code, out, err = _run(["git", "push", secret_url,
                               f"HEAD:refs/heads/{branch}"], self.repo, self.token)
        if code != 0:
            return {"ok": False, "note": f"GitHub refused the push: {err or out}"}
        # The push went to a URL, not to the configured remote, so git does not
        # move refs/remotes/<remote>/<branch> by itself. Without this, status()
        # reports "ahead 1" seconds after a successful push, which is the kind of
        # small lie this project exists to remove.
        self.git("update-ref", f"refs/remotes/{self.remote}/{branch}", "HEAD")
        return {"ok": True, "note": f"Pushed {branch} to {re.sub(r'//[^@/]+@', '//', url)}.",
                "branch": branch}

    def ship(self, message: str, *, why: str = "", check_gate: Callable[[], dict] | None = None,
             allow_empty: bool = False) -> dict:
        """Scan, guard, check, commit, push. The first failure stops the ship."""
        scan = self.scan()
        if not scan["clean"]:
            return {"ok": False, "stage": "scan", "note":
                    "I did not ship: a secret-shaped string is in the tree. Look at "
                    + ", ".join(hit["file"] for hit in scan["hits"][:3]), "hits": scan["hits"]}
        guards = self.guards()
        if not guards["ok"]:
            return {"ok": False, "stage": "guard", "note": guards["problems"][0],
                    "problems": guards["problems"]}
        syntax = self.check_syntax()
        if not syntax["ok"]:
            return {"ok": False, "stage": "syntax", "note":
                    "I did not ship: a changed file does not parse. " + syntax["broken"][0],
                    "broken": syntax["broken"]}
        evidence = [f"Secret scan: {scan['files']} files, no secret found.",
                    f"Syntax: {syntax['checked']} changed file(s) parse.",
                    "Ignore rules: the config and the memory file are still ignored."]
        if check_gate is not None:
            result = check_gate() or {}
            if not result.get("ok", False):
                return {"ok": False, "stage": "gate", "note":
                        "I did not ship: the checks failed. " + str(result.get("note", ""))}
            evidence.append(str(result.get("note", "Checks passed.")))

        committed = self.commit(message, "\n".join(["Why:", why or message, "", "Evidence:",
                                                    *[f"  {line}" for line in evidence]]))
        if not committed["ok"]:
            if allow_empty and "nothing to ship" in committed["note"]:
                return committed
            return {"ok": False, "stage": "commit", "note": committed["note"],
                    "files": committed.get("files", [])}
        pushed = self.push()
        record = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "ok": pushed["ok"],
                  "commit": committed.get("commit", ""), "files": len(committed["files"]),
                  "message": " ".join(str(message).split())[:72], "note": pushed["note"],
                  "evidence": evidence}
        self._log(record)
        if not pushed["ok"]:
            return {"ok": False, "stage": "push", "note":
                    committed["note"] + " It is committed here but not published: "
                    + pushed["note"] + " Ship again once that is fixed.",
                    **record}
        return {"ok": True, "stage": "pushed", "note": committed["note"] + " " + pushed["note"],
                **record}

    # --------------------------------------------------------------------- log
    def _log(self, record: dict) -> None:
        if not self.log_path:
            return
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            rows = json.loads(self.log_path.read_text(encoding="utf-8")) if \
                self.log_path.exists() else []
            if not isinstance(rows, list):
                rows = []
            rows.append(record)
            self.log_path.write_text(json.dumps(rows[-MAX_LOG:], indent=1),
                                     encoding="utf-8")
        except (OSError, ValueError):
            pass


def token_from_environment() -> str:
    """The token, in the order a person would look for it. Never from the tree."""
    value = (os.environ.get("GITHUB_TOKEN", "") or "").strip()
    if value:
        return value
    try:
        from memory.config_manager import load_api_keys
        value = str(load_api_keys().get("github_token") or "").strip()
        if value:
            return value
    except Exception:                                          # noqa: BLE001
        pass
    try:
        from core.paths import state_dir
        path = state_dir() / "github_token"
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    return ""


def describe(result: Any) -> str:
    """One sentence for the model, from a ship result."""
    if not isinstance(result, dict):
        return "The ship returned nothing readable."
    stage = result.get("stage", "")
    if result.get("ok"):
        return f"Shipped. {result.get('note', '')}".strip()
    return f"I did not ship ({stage or 'unknown stage'}). {result.get('note', '')}".strip()
