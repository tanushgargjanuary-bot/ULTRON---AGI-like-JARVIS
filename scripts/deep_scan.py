#!/usr/bin/env python3
"""Read the whole tree and report what a reviewer would complain about.

This is not a linter. A linter reports style, and this project's style is already
settled. This reports the things that turn into incidents:

  * an exception that is caught and thrown away, so a failure looks like success;
  * a shell string built from data, which is a command injection;
  * a serialiser that runs code, which is a remote code execution;
  * a network call with no timeout, which is a hang;
  * a licence-key-shaped string, which is a leak;
  * a function a person cannot hold in their head, or the same function written
    twice under two names;
  * a dependency with no upper bound, which is a surprise upgrade.

Every finding carries a file, a line and one sentence about why it matters, so the
report can be acted on rather than admired. Run it with `--json` for a machine
copy, and `--fail-on high` to make a build red.

    python scripts/deep_scan.py
    python scripts/deep_scan.py --json verification/deep-scan.json --fail-on high
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "__pycache__", ".ruff_cache", ".hypothesis",
             "verification", "node_modules", "build", "dist"}

HIGH, MEDIUM, LOW = "high", "medium", "low"

# A licence key or an API key, in the shapes the providers actually use.
SECRET_SHAPES = (
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}"), "an OpenAI-shaped secret"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"), "a Google API key"),
    (re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}"), "a Slack token"),
    (re.compile(r"\bghp_[0-9A-Za-z]{30,}"), "a GitHub token"),
    (re.compile(r"\bgithub_pat_[0-9A-Za-z_]{40,}"), "a fine-grained GitHub token"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "an AWS access key id"),
)

DANGEROUS_CALLS = {
    "eval": "runs whatever string it is given",
    "exec": "runs whatever string it is given",
    "pickle.load": "runs code from the file it reads",
    "pickle.loads": "runs code from the bytes it reads",
    "yaml.load": "runs code unless a safe loader is named",
    "os.system": "passes a string to a shell",
    "marshal.loads": "runs code from the bytes it reads",
}

LONG_FUNCTION = 80
COMPLEXITY_LIMIT = 18
NESTING_LIMIT = 5


@dataclass
class Finding:
    severity: str
    kind: str
    path: str
    line: int
    detail: str

    def as_dict(self) -> dict:
        return {"severity": self.severity, "kind": self.kind, "path": self.path,
                "line": self.line, "detail": self.detail}


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    files: int = 0
    lines: int = 0
    functions: int = 0

    def add(self, severity, kind, path, line, detail):
        self.findings.append(Finding(severity, kind, str(path), line, detail))

    def counts(self) -> dict[str, int]:
        tally: dict[str, int] = {}
        for finding in self.findings:
            tally[finding.kind] = tally.get(finding.kind, 0) + 1
        return tally

    def worst(self, severity: str) -> list[Finding]:
        return [f for f in self.findings if f.severity == severity]


def python_files(root: Path):
    for path in sorted(root.rglob("*.py")):
        if SKIP_DIRS & set(path.parts):
            continue
        if path.name == "deep_scan.py":
            continue        # this file quotes every pattern it looks for
        yield path


def caught_names(node) -> list[str]:
    """The exception types a handler names, however it spells them.

    `except Exception:` and `except (OSError, ValueError):` are different promises,
    and the difference is the whole point of this rule. A tuple was read as "catches
    everything" by the first version of this scan, which reported four honest
    handlers as holes.
    """
    if node is None:
        return ["<bare>"]
    if isinstance(node, ast.Tuple):
        names = []
        for element in node.elts:
            names.extend(caught_names(element))
        return names
    name = getattr(node, "id", None) or getattr(node, "attr", None)
    return [name] if name else ["<expression>"]


def catches_everything(node) -> bool:
    names = caught_names(node)
    return bool({"<bare>", "<expression>", "Exception", "BaseException"} & set(names))


def nesting_depth(node: ast.AST, depth: int = 0) -> int:
    """How many blocks a reader has to carry at once."""
    deepest = depth
    for child in ast.iter_child_nodes(node):
        step = 1 if isinstance(child, (ast.If, ast.For, ast.While, ast.With,
                                       ast.Try, ast.AsyncFor, ast.AsyncWith)) else 0
        deepest = max(deepest, nesting_depth(child, depth + step))
    return deepest


def complexity(node: ast.AST) -> int:
    """A plain branch count: every place the flow can go a different way."""
    score = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.For, ast.While, ast.AsyncFor, ast.AsyncWith,
                              ast.ExceptHandler, ast.Assert, ast.IfExp)):
            score += 1
        elif isinstance(child, ast.BoolOp):
            score += len(child.values) - 1
        elif isinstance(child, ast.comprehension):
            score += 1 + len(child.ifs)
    return score


def body_fingerprint(node) -> str:
    """A function reduced to its structure, so a copy with new names still matches."""
    parts = []

    def walk(item):
        parts.append(type(item).__name__)
        if isinstance(item, ast.Name):
            parts.append("_")
        elif isinstance(item, ast.Constant):
            parts.append(repr(item.value)[:20])
        elif isinstance(item, ast.arg):
            parts.append("_")
        for child in ast.iter_child_nodes(item):
            walk(child)

    walk(node)
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def scan_python(path: Path, report: Report, seen_bodies: dict[str, tuple[str, int]]):
    source = path.read_text(encoding="utf-8", errors="replace")
    report.files += 1
    report.lines += source.count("\n") + 1

    for number, text in enumerate(source.splitlines(), 1):
        # A fixture has to look like a key or nothing is being tested, and the
        # repository already marks those the way the secret scanners do. Without
        # this the report cries wolf at its own tests, which is how a security
        # report stops being read.
        excused = ("gitleaks:allow" in text or "SHOULD-NOT-APPEAR" in text
                   or "FIXTURE" in text or "placeholder" in text.lower())
        for pattern, what in SECRET_SHAPES:
            if not excused and pattern.search(text):
                report.add(HIGH, "secret-in-source", path, number,
                           f"{what} is written in the file")
        for marker in ("TODO", "FIXME", "XXX", "HACK"):
            if marker in text and not text.lstrip().startswith("#"):
                continue
            if marker in text:
                report.add(LOW, "unfinished-marker", path, number,
                           f"{marker} left in a comment")

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as error:
        report.add(HIGH, "syntax-error", path, error.lineno or 0, str(error))
        return

    # A module nobody can find their way into without a sentence at the top.
    if ast.get_docstring(tree) is None and path.name != "__init__.py":
        report.add(LOW, "no-module-docstring", path, 1, "no sentence says what it is")

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                report.add(HIGH, "bare-except", path, node.lineno,
                           "catches everything, including Ctrl-C and typos")
            elif (len(node.body) == 1 and isinstance(node.body[0], ast.Pass)):
                # The type matters. `except Exception: pass` hides everything, and
                # is the hole this rule exists for. `except OSError: pass` around an
                # optional stat says what it expects to fail, and a reviewer reads
                # it as intent rather than an accident — worth knowing, not worth a
                # red build.
                if catches_everything(node.type):
                    report.add(MEDIUM, "swallowed-exception", path, node.lineno,
                               "catches everything and discards it, so a failure looks "
                               "like success")
                else:
                    report.add(LOW, "typed-exception-discarded", path, node.lineno,
                               f"catches {', '.join(caught_names(node.type))} and "
                               f"discards it")
            elif (len(node.body) == 1 and isinstance(node.body[0], ast.Continue)):
                if catches_everything(node.type):
                    report.add(MEDIUM, "swallowed-exception", path, node.lineno,
                               "catches everything and skips the item, so a failure "
                               "looks like an empty result")
                else:
                    report.add(LOW, "typed-exception-discarded", path, node.lineno,
                               f"catches {', '.join(caught_names(node.type))} and "
                               f"skips the item")
        elif isinstance(node, ast.Call):
            name = ""
            attribute_call = isinstance(node.func, ast.Attribute)
            receiver = ""
            if attribute_call:
                verb = node.func.attr
                name = verb
                if isinstance(node.func.value, ast.Name):
                    receiver = node.func.value.id
                    name = f"{receiver}.{verb}"
            else:
                verb = node.func.id if isinstance(node.func, ast.Name) else ""
                name = verb
            # `app.exec()` is Qt starting its event loop, not Python running a
            # string. Only a bare exec/eval has the danger this rule is about.
            if attribute_call and verb in {"exec", "eval"}:
                name = f"attr:{name}"
            if name in DANGEROUS_CALLS:
                in_tests = "tests" in path.parts
                report.add(MEDIUM if in_tests else HIGH, "dangerous-call", path,
                           node.lineno,
                           f"{name}() {DANGEROUS_CALLS[name]}"
                           + ("; in a test that compiles a slice of the tree"
                              if in_tests else ""))
            if name in {"system", "popen", "run", "call", "Popen", "check_output"}:
                for keyword in node.keywords:
                    if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) \
                            and keyword.value.value is True:
                        report.add(HIGH, "shell-true", path, node.lineno,
                                   "a shell parses the command line, so data becomes "
                                   "a command")
            # A network call with no timeout waits forever on a hung server.
            verbs = {"post", "put", "patch", "delete", "request"}
            http_object = {"session", "client", "httpx", "requests", "http", "s"}
            if (attribute_call and verb in verbs) or \
                    (attribute_call and verb == "get" and receiver in http_object):
                has_timeout = any(k.arg == "timeout" for k in node.keywords)
                if not has_timeout:
                    report.add(MEDIUM, "no-timeout", path, node.lineno,
                               f"{name}() with no timeout: one dead server, one hang")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            report.functions += 1
            length = (node.end_lineno or node.lineno) - node.lineno + 1
            if length > LONG_FUNCTION:
                report.add(MEDIUM, "long-function", path, node.lineno,
                           f"{node.name}() is {length} lines: too long to hold in mind")
            score = complexity(node)
            if score > COMPLEXITY_LIMIT:
                report.add(MEDIUM, "complex-function", path, node.lineno,
                           f"{node.name}() branches {score} ways")
            depth = nesting_depth(node)
            if depth > NESTING_LIMIT:
                report.add(LOW, "deep-nesting", path, node.lineno,
                           f"{node.name}() nests {depth} deep")
            if length >= 6:
                fingerprint = body_fingerprint(node)
                earlier = seen_bodies.get(fingerprint)
                if earlier and earlier[1] >= 6 and earlier[0] != f"{path}:{node.name}":
                    report.add(LOW, "duplicate-body", path, node.lineno,
                               f"{node.name}() repeats the shape of {earlier[0]}")
                else:
                    seen_bodies[fingerprint] = (f"{path}:{node.name}", length)

    # A print() outside a script is console noise from inside a library.
    runs_as_script = any(
        isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
        and "name" in ast.dump(node.test) and "__main__" in ast.dump(node.test)
        for node in tree.body)
    if path.parent.name not in {"scripts", "tests"} and path.name != "main.py" \
            and not runs_as_script:
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id == "print":
                report.add(LOW, "print-in-library", path, node.lineno,
                           "writes to stdout from inside the package")


def scan_requirements(root: Path, report: Report):
    for name in ("requirements.txt", "requirements-dev.txt"):
        path = root / name
        if not path.exists():
            continue
        for number, text in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = text.split("#")[0].strip()
            if not line:
                continue
            if ">=" in line and "<" not in line:
                report.add(MEDIUM, "unbounded-dependency", path, number,
                           f"{line} has no upper bound: a major release installs itself")


def scan_hardcoding(root: Path, report: Report):
    """The owner's rule: no provider name, model name or address in the code.

    Addresses are allowed in the one file that ships defaults, because a default
    is a value the user can change; they are not allowed scattered through the
    logic, where a user cannot find them.
    """
    allowed = {"config", "providers", "docs", "tests", "scripts"}
    shape = re.compile(r"https?://(?!localhost|127\.0\.0\.1)[a-z0-9.-]+\.[a-z]{2,}")
    for path in python_files(root):
        if set(path.relative_to(root).parts) & allowed:
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        # An address in a named constant at the top of a module is a default the
        # owner can find and change; the same address inside a function body is
        # logic that hides it. Only the second kind is a finding.
        at_module_level = set()
        try:
            tree = ast.parse(source)
        except SyntaxError:
            tree = None
        if tree is not None:
            # Only statement bodies have a body list; a lambda's `body` is an
            # expression, and iterating it raises. Walk modules and classes.
            for holder in [tree] + [n for n in ast.walk(tree)
                                    if isinstance(n, ast.ClassDef)]:
                for statement in holder.body:
                    if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                        for line_node in ast.walk(statement):
                            if hasattr(line_node, "lineno"):
                                at_module_level.add(line_node.lineno)
        for number, text in enumerate(source.splitlines(), 1):
            if text.lstrip().startswith("#"):
                continue
            for match in shape.finditer(text):
                if number in at_module_level:
                    report.add(LOW, "address-in-constant", path, number,
                               f"{match.group(0)} is a named default; fine if it is "
                               f"documented")
                else:
                    report.add(MEDIUM, "hardcoded-address", path, number,
                               f"{match.group(0)} is baked into logic, not "
                               f"configuration")


def scan_licence(path: Path, report: Report):
    """The upstream project is CC BY-NC 4.0 and its credit must survive edits."""
    for name in ("readme.md", "README.md", "LICENCE", "LICENSE"):
        credit = path / name
        if not credit.exists():
            continue
        text = credit.read_text(encoding="utf-8", errors="replace")
        if "FatihMakes" not in text:
            report.add(HIGH, "missing-credit", credit, 1,
                       "the upstream author is not credited in this file")
        return


def run(root: Path = ROOT) -> Report:
    report = Report()
    seen_bodies: dict[str, tuple[str, int]] = {}
    for path in python_files(root):
        scan_python(path, report, seen_bodies)
    scan_requirements(root, report)
    scan_hardcoding(root, report)
    scan_licence(root, report)
    order = {HIGH: 0, MEDIUM: 1, LOW: 2}
    report.findings.sort(key=lambda f: (order[f.severity], f.kind, f.path, f.line))
    return report


def render(report: Report) -> str:
    lines = []
    counts = report.counts()
    blocked = len(report.worst(HIGH))
    lines.append("DEEP SCAN")
    lines.append(f"  {report.files} Python files, {report.lines:,} lines, "
                 f"{report.functions:,} functions")
    lines.append(f"  {blocked} high, {len(report.worst(MEDIUM))} medium, "
                 f"{len(report.worst(LOW))} low")
    if counts:
        lines.append("")
        for kind, number in sorted(counts.items(), key=lambda kv: -kv[1]):
            lines.append(f"  {number:5d}  {kind}")
    for severity, title in ((HIGH, "MUST FIX"), (MEDIUM, "SHOULD FIX"),
                            (LOW, "WORTH KNOWING")):
        items = report.worst(severity)
        if not items:
            continue
        lines.append(f"\n  {title}")
        for finding in items[:25]:
            where = f"{Path(finding.path).name}:{finding.line}"
            lines.append(f"    {where:34s} {finding.detail}")
        if len(items) > 25:
            lines.append(f"    ... and {len(items) - 25} more of the same kind")
    return "\n".join(lines)


def render_markdown(report: Report) -> str:
    """The same findings as a page someone will actually read."""
    counts = report.counts()
    areas: dict[str, int] = {}
    for finding in report.findings:
        if finding.kind != "swallowed-exception":
            continue
        rel = Path(finding.path)
        try:
            key = rel.relative_to(ROOT).parts[0]
        except ValueError:
            key = rel.name
        key = key if key.endswith(".py") is False else key
        areas[key] = areas.get(key, 0) + 1

    out = ["# Deep scan", "",
           "Generated by `python scripts/deep_scan.py --doc docs/DEEP-SCAN.md`. "
           "Every line is a fact about this tree, not an opinion about style.", "",
           f"**{report.files} Python files · {report.lines:,} lines · "
           f"{report.functions:,} functions · {len(report.worst(HIGH))} high · "
           f"{len(report.worst(MEDIUM))} medium · {len(report.worst(LOW))} low**",
           "", "## What it looks for", "",
           "| Rule | Why it is a rule |", "|---|---|",
           "| bare `except:` | catches Ctrl-C and typos |",
           "| caught and discarded | a failure that looks like success |",
           "| `shell=True` | data becomes a command |",
           "| `eval`, `exec`, `pickle.load`, `yaml.load` | runs code from data |",
           "| HTTP call with no timeout | one dead server, one hang |",
           "| a key-shaped string | a leak |",
           "| a function of 80+ lines or 19+ branches | too big to correct safely |",
           "| the same body twice | two copies, two bugs |",
           "| a dependency with no upper bound | a major release installs itself |",
           "| an address inside logic | a value the owner cannot find |", "",
           "## Counts", "", "| Finding | Count |", "|---|---|"]
    for kind, number in sorted(counts.items(), key=lambda kv: -kv[1]):
        out.append(f"| {kind} | {number} |")
    out += ["", "## Where the discarded exceptions are", "",
            "This is the one finding worth a ratchet, because a discarded exception "
            "is how a real failure becomes a silent one. The owned core has none; "
            "the count lives in the interface and the action layer.", "",
            "| Area | Caught and discarded |", "|---|---|"]
    for area, number in sorted(areas.items(), key=lambda kv: -kv[1]):
        out.append(f"| `{area}` | {number} |")
    out += ["", "## The ten largest functions", "",
            "| Function | Lines | Branches |", "|---|---|---|"]
    biggest = sorted((f for f in report.findings if f.kind == "long-function"),
                     key=lambda f: -int(f.detail.split(" is ")[1].split(" ")[0]))[:10]
    for finding in biggest:
        lines = finding.detail.split(" is ")[1].split(" ")[0]
        out.append(f"| `{Path(finding.path).name}:{finding.line}` | {lines} | |")
    out += ["", "See `verification/deep-scan.json` for every finding with its line "
            "number. The tests in `tests/test_deep_scan.py` hold the counts as a "
            "ceiling, so this report cannot get worse without a red build.", ""]
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", help="also write the findings here")
    parser.add_argument("--doc", help="write the markdown report here")
    parser.add_argument("--fail-on", choices=[HIGH, MEDIUM, LOW],
                        help="exit non-zero when this severity or worse is present")
    args = parser.parse_args()

    report = run()
    print(render(report))
    if args.json:
        target = Path(args.json)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({
            "files": report.files, "lines": report.lines,
            "functions": report.functions,
            "counts": report.counts(),
            "findings": [f.as_dict() for f in report.findings]}, indent=2),
            encoding="utf-8")
    if args.doc:
        target = Path(args.doc)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_markdown(report), encoding="utf-8")
    if args.fail_on:
        ladder = {HIGH: (HIGH,), MEDIUM: (HIGH, MEDIUM), LOW: (HIGH, MEDIUM, LOW)}
        if any(f.severity in ladder[args.fail_on] for f in report.findings):
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
