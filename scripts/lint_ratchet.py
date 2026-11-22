"""Lint ratchet: a change may not leave a file with MORE findings of the gate's ruff rules than it
began with; it need not fix old ones.

The fast gate (`.github/workflows/fast-checks.yml`) used to run `ruff check --select E4,E7,E9,F`
on every Python file a change touched, and failed on every finding in those files. Most of the
tree predates that rule set: `ui.py` alone has 97 findings and `actions/file_processor.py` 25
(counted on cf02c0e plus this branch). So a one-line change to either could not pass the gate
without first cleaning the whole file. The history has the marks of it: one-line `style:` commits
(49aa32f, 7c8cb38, 96efb16, all 2026-11-15) whose whole content is a lint fix, and fast-checks
failed on 11 of the last 14 pushes to `main`. (The cause of each failure cannot be recovered from
here: run logs are not downloadable, so this is evidence of friction, not a count of lint failures.)

This compares each touched file with the same file at the base of the change, rule by rule:

  * a file may have no MORE findings of a rule than it had at the base (a new file had none);
  * it may have fewer. Fixing old ones is welcome and is not required.

What it does NOT do: match findings one for one. It counts them per file and per rule, so the
question it answers is "does this file now have more E402 than it had?", not "is any of these
E402 new?". A change that fixes one E402 in `ui.py` and adds another E402 to it leaves the count
where it was, and passes (`tests/test_lint_ratchet.py` holds that case). A new E402 in `ui.py`
fails when nothing in the file paid for it; where one was fixed in the same change, it does not.
The first version of this paragraph promised that a new finding always fails, which that swap
shows to be untrue. Matching individual findings across a change would need a stable identity for
a finding, and a line number is not one, so this stays a count.

It never passes because it could not run. A missing `ruff`, output that is not JSON, a base that
cannot be read: each exits 2, and the workflow step fails on any non-zero exit. (`python -m ruff`
with ruff not installed exits 1 and prints nothing to stdout, which a careless reader would take
for "no findings"; empty output is an error here.)

    python scripts/lint_ratchet.py --base origin/main     # the working tree against that base
    python scripts/lint_ratchet.py --base HEAD            # only what is uncommitted

Exit status: 0 nothing got worse, 1 something did, 2 the check could not be made.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SELECT = "E4,E7,E9,F"       # the rule set named in ruff.toml and docs/TEST_AUTOMATION.md
CONFIG_NAME = "ruff.toml"


class CannotRun(RuntimeError):
    """The comparison could not be made. That is exit 2: a gate that cannot run has not passed."""


def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(command, cwd=cwd, capture_output=True, check=False)
    except OSError as error:
        raise CannotRun(f"could not start {command[0]!r}: {error}") from error


def _text(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace").strip()


def git(args: list[str], root: Path) -> bytes:
    """Run git; any failure is CannotRun, never an empty answer."""
    done = _run(["git", *args], root)
    if done.returncode != 0:
        raise CannotRun(f"git {' '.join(args)} failed: {_text(done.stderr)[:300]}")
    return done.stdout


def parse_name_status(raw: bytes) -> list[tuple[str, str, str]]:
    """`git diff --name-status -z` output -> [(status, name at the base, name now)].

    The two names differ only for a rename. Names may hold spaces or unicode, which is why
    the output is NUL-delimited rather than split on whitespace.
    """
    parts = raw.decode("utf-8").split("\0")
    if parts and parts[-1] == "":
        parts.pop()
    rows: list[tuple[str, str, str]] = []
    index = 0
    try:
        while index < len(parts):
            status = parts[index]
            if status[:1] in ("R", "C"):
                rows.append((status[0], parts[index + 1], parts[index + 2]))
                index += 3
            else:
                rows.append((status[0], parts[index + 1], parts[index + 1]))
                index += 2
    except IndexError as error:
        raise CannotRun("git printed a change list this script cannot read") from error
    return rows


def changed_python_files(base: str, root: Path) -> list[tuple[str, str, str]]:
    """Python files the working tree changes relative to `base`, plus untracked ones."""
    diff = git(["diff", "--name-status", "-z", "-M", "--diff-filter=ACMR", base, "--", "*.py"], root)
    rows = parse_name_status(diff)
    known = {path for _status, _old, path in rows}
    untracked = git(["ls-files", "-z", "--others", "--exclude-standard", "--", "*.py"], root)
    for name in untracked.decode("utf-8").split("\0"):
        if name and name not in known:
            rows.append(("A", name, name))
    return rows


def default_base(root: Path) -> str:
    """Where this branch left `main`: the merge-base, so upstream-only changes are not ours."""
    for candidate in ("origin/main", "main"):
        if _run(["git", "rev-parse", "--verify", "--quiet", candidate], root).returncode == 0:
            return _text(git(["merge-base", "HEAD", candidate], root))
    raise CannotRun("no origin/main or main to compare with; pass --base <commit>")


def ensure_ruff(root: Path) -> None:
    done = _run([sys.executable, "-m", "ruff", "--version"], root)
    if done.returncode != 0:
        raise CannotRun("ruff is not installed for this Python (pip install -r requirements-dev.txt)")


def ruff_findings(files: list[str], select: str, cwd: Path) -> list[dict]:
    """ruff's own JSON findings for `files` (relative to `cwd`). Exit 1 means findings, not failure."""
    if not files:
        return []
    done = _run([sys.executable, "-m", "ruff", "check", "--no-cache", "--select", select,
                 "--output-format", "json", "--", *files], cwd)
    if done.returncode not in (0, 1):
        raise CannotRun(f"ruff exited {done.returncode}: {_text(done.stderr or done.stdout)[:400]}")
    text = _text(done.stdout)
    if not text:
        raise CannotRun(f"ruff printed nothing: {_text(done.stderr)[:300] or 'no explanation'}")
    try:
        findings = json.loads(text)
    except ValueError as error:
        raise CannotRun(f"ruff did not print JSON: {error}") from error
    if not isinstance(findings, list):
        raise CannotRun("ruff's JSON is not a list of findings")
    return findings


Counts = dict[str, dict[str, list[tuple[int, str]]]]       # path -> rule -> [(line, message)]


def by_file_and_rule(findings: list[dict], folder: Path) -> Counts:
    """Group ruff's findings by file (relative to `folder`) and rule code."""
    base = folder.resolve()
    grouped: Counts = {}
    for item in findings:
        name = Path(item["filename"]).resolve().relative_to(base).as_posix()
        code = item.get("code") or "syntax-error"
        row = (item.get("location") or {}).get("row", 0)
        grouped.setdefault(name, {}).setdefault(code, []).append((row, str(item.get("message", ""))))
    return grouped


def regressions(before: Counts, now: Counts) -> list[str]:
    """One line for every (file, rule) that has more findings now than at the base."""
    lines = []
    for path in sorted(now):
        for code in sorted(now[path]):
            found = sorted(now[path][code])
            was = len(before.get(path, {}).get(code, []))
            if len(found) > was:
                rows = ", ".join(str(row) for row, _message in found[:6])
                more = ", ..." if len(found) > 6 else ""
                lines.append(f"{path}: {code} {len(found)} now, {was} at the base "
                             f"(lines {rows}{more}) - {found[0][1]}")
    return lines


def _total(counts: Counts) -> int:
    return sum(len(rows) for codes in counts.values() for rows in codes.values())


def _base_counts(base: str, rows: list[tuple[str, str, str]], select: str, root: Path) -> Counts:
    """The same files as they were at `base`, linted under the SAME configuration.

    They are written to a scratch folder together with the current `ruff.toml`, so that a
    per-file ignore (main.py is exempt from E402) applies to both sides alike, and so that a
    change to the configuration itself cannot show up as a regression.
    """
    with tempfile.TemporaryDirectory() as folder:
        mirror = Path(folder)
        config = root / CONFIG_NAME
        if config.is_file():
            shutil.copyfile(config, mirror / CONFIG_NAME)
        written = []
        for status, old, path in rows:
            if status == "A":
                continue                    # it did not exist at the base: zero findings
            target = mirror / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(git(["show", f"{base}:{old}"], root))
            written.append(path)
        return by_file_and_rule(ruff_findings(written, select, mirror), mirror)


def check(base: str | None, select: str, root: Path) -> int:
    ensure_ruff(root)
    base = base or default_base(root)
    rows = [row for row in changed_python_files(base, root) if (root / row[2]).is_file()]
    if not rows:
        print("lint ratchet: no changed Python files.")
        return 0
    now = by_file_and_rule(ruff_findings([path for _s, _o, path in rows], select, root), root)
    before = _base_counts(base, rows, select, root)
    worse = regressions(before, now)
    print(f"lint ratchet (ruff {select}): {len(rows)} changed Python file(s), "
          f"{_total(now)} finding(s) in them, {_total(before)} at the base")
    if not worse:
        print("OK: nothing got worse." + (f" {_total(now)} finding(s) were already there and "
                                          "are not counted against this change." if now else ""))
        return 0
    print(f"FAIL: {len(worse)} rule(s) got worse (findings that were already there are not counted):")
    for line in worse:
        print("  " + line)
    return 1


def main(argv: list[str] | None = None, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description="Fail when a change adds ruff findings.")
    parser.add_argument("--base", help="commit to compare with (default: where this branch left main)")
    parser.add_argument("--select", default=DEFAULT_SELECT, help="ruff rules (default: %(default)s)")
    args = parser.parse_args(argv)
    try:
        return check(args.base, args.select, root)
    except CannotRun as error:
        print(f"lint ratchet could not run, so it has NOT passed: {error}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
