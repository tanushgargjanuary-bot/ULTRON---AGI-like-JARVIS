"""
core/ast_guardian.py — Production AST safety analysis for autonomous code modifications.
Rejects any proposed diff or code string containing forbidden imports, dynamic execution,
or dunder manipulation before it touches disk.

WHAT THIS IS, AND IS NOT
    A deny-list over the syntax tree: it stops the code a model writes when it is not
    trying very hard. It is not a sandbox, and no deny-list of Python can be one.
    What it reads through: `import os as o`, `from os import system as run`,
    `from os import *` (refused outright), `import builtins as b; b.exec(...)`, a name bound
    twice (every binding is kept, so reusing a name hides nothing), a plain assignment
    (`run = os.system`, `m = os; m.system(...)`), a forbidden callable named without being
    called (`map(os.system, ...)`, `[eval]`), `getattr(x, '__cl' + 'ass__')`,
    `getattr(os, 'system')`, `sys.modules['sub' + 'process']` and a bare `__builtins__`.
    What it cannot read through, each one checked in tests/test_ast_guardian_bypasses.py so
    this list cannot drift from the code: a name built from data (`getattr(x, variable)`);
    a module, rather than a callable, carried through a list, a class attribute or a
    function's return and used from there (`[os][0].system(...)`); a module reached as an
    attribute of another (`shutil.os.system(...)`); a lookup done by another function
    (`operator.attrgetter('system')(os)`, `vars(os)['system']`, `os.__dict__['system']`);
    and code fetched and run later. Where it cannot tell what a name stands for it errs on
    the side of refusing: it can over-report, and a file that uses a builtin's name for
    something of its own (a parameter called `compile`) is refused for it. It does not
    judge what a file does with the network or the disk (`urllib`, `requests`,
    `shutil.rmtree`, `open`): a change to the code that fetches a page would be unwritable
    otherwise.
    The controls that matter
    are the ones around it in `core/self_change.py` — rehearsal in a copy with the whole
    test harness, two confirmations, the owner's approval on the screen, and a backup
    that `revert` restores byte for byte.
"""

from __future__ import annotations

import ast
import hashlib
import posixpath
from dataclasses import dataclass, field
from typing import NamedTuple, Set


class Violation(NamedTuple):
    severity: str  # "BLOCK" or "WARN"
    rule: str
    line: int
    detail: str


@dataclass
class ASTAuditReport:
    file_path: str
    source_hash: str
    violations: list[Violation] = field(default_factory=list)
    approved: bool = False

    @property
    def has_blockers(self) -> bool:
        return any(v.severity == "BLOCK" for v in self.violations)


FORBIDDEN_CALL_PATTERNS = {
    ("os", "system"): "Direct OS shell execution forbidden",
    ("os", "popen"): "Direct OS shell execution forbidden",
    ("os", "startfile"): "Launching a program with os.startfile forbidden in mutations",
    ("os", "fork"): "Forking forbidden in mutations",
    ("os", "forkpty"): "Forking forbidden in mutations",
    ("os", "posix_spawn"): "Spawning a process forbidden in mutations",
    ("os", "posix_spawnp"): "Spawning a process forbidden in mutations",
    ("subprocess", "run"): "Direct subprocess forbidden in mutations",
    ("subprocess", "Popen"): "Direct subprocess forbidden in mutations",
    ("subprocess", "call"): "Direct subprocess forbidden in mutations",
    ("subprocess", "check_call"): "Direct subprocess forbidden in mutations",
    ("subprocess", "check_output"): "Direct subprocess forbidden in mutations",
    ("subprocess", "getoutput"): "Direct subprocess forbidden in mutations",
    ("subprocess", "getstatusoutput"): "Direct subprocess forbidden in mutations",
    ("asyncio", "create_subprocess_exec"): "Direct subprocess forbidden in mutations",
    ("asyncio", "create_subprocess_shell"): "Direct subprocess forbidden in mutations",
    ("runpy", "run_module"): "Running a module by name forbidden in mutations",
    ("runpy", "run_path"): "Running a file by path forbidden in mutations",
    ("pty", "spawn"): "Spawning a process forbidden in mutations",
    ("builtins", "eval"): "eval() forbidden",
    ("builtins", "exec"): "exec() forbidden",
    ("builtins", "compile"): "compile() forbidden",
    ("builtins", "__import__"): "__import__() forbidden",
    ("socket", "socket"): "Raw socket creation forbidden",
}

# `os.execv`, `os.execvp`, `os.spawnl` ... — a family, matched by what the name starts with.
FORBIDDEN_CALL_PREFIXES = {
    ("os", "exec"): "Replacing the process with os.exec* forbidden in mutations",
    ("os", "spawn"): "Spawning a process with os.spawn* forbidden in mutations",
}

FORBIDDEN_BUILTINS = frozenset({"eval", "exec", "compile", "__import__"})

# `getattr(x, "name")` and its three relatives reach an attribute by a string.
_ATTRIBUTE_BY_NAME = frozenset({"getattr", "setattr", "delattr", "hasattr"})
# Calls that fetch a module from the table of loaded modules by name.
_MODULE_TABLE_LOOKUPS = frozenset({"sys.modules.get", "sys.modules.pop", "sys.modules.setdefault"})

# The modules a forbidden call lives in: `from <one of these> import *` cannot be checked.
_MODULES_WITH_FORBIDDEN_CALLS = frozenset(
    {module for module, _ in FORBIDDEN_CALL_PATTERNS} | {module for module, _ in FORBIDDEN_CALL_PREFIXES}
)

FORBIDDEN_IMPORT_MODULES: Set[str] = frozenset(
    {
        "subprocess",
        "ctypes",
        "_ctypes",
        "cffi",
        "mmap",
        "socket",
        "ssl",
        "winreg",
        "pickle",
        "dis",
        "gc",
        "importlib",
        # The same reach as `subprocess`, by another door.
        "multiprocessing",
        "runpy",
        "pty",
        "code",
        "codeop",
        "marshal",
    }
)

DANGEROUS_ATTRIBUTES = frozenset(
    {
        "__class__",
        "__bases__",
        "__mro__",
        "__globals__",
        "__builtins__",
        "__code__",
        "co_code",
        "__func__",
        "__closure__",
        "__subclasses__",
        "f_globals",
        "f_builtins",
        "f_back",
        "gi_frame",
        "cr_frame",
        "tb_frame",
    }
)

REFEREE_FILES: Set[str] = frozenset(
    {
        "core/policy.py",
        "core/confirm.py",
        "core/self_change.py",
        "scripts/proof_gate.py",
        "config/api_keys.json",
        "core/ast_guardian.py",
    }
)


def _normalise(path: str) -> str:
    """`./core//policy.py`, `core/../core/policy.py` and `CORE/Policy.py` are one file."""
    text = posixpath.normpath(str(path).replace("\\", "/"))
    return text.lower()


_REFEREE_NORMALISED = frozenset(_normalise(name) for name in REFEREE_FILES)


def _is_referee(path: str) -> bool:
    text = _normalise(path)
    if text in _REFEREE_NORMALISED:
        return True
    # An absolute path cannot be compared with a project-relative list for equality;
    # it is a referee file if it ends in one. A relative path never gets this reading,
    # so `plugins/core/policy.py` is not mistaken for `core/policy.py`.
    absolute = text.startswith("/") or (len(text) > 1 and text[1] == ":")
    return absolute and any(text.endswith("/" + name) for name in _REFEREE_NORMALISED)


def _aliases(tree: ast.AST) -> dict[str, set[str]]:
    """Local name -> everything it may stand for, from the file's own imports and assignments.

    `import os as o` makes `o` mean `os`; `from os import system as run` makes `run`
    mean `os.system`; `run = os.system` makes `run` mean that too. Without this every rule
    below is defeated by renaming.

    The table keeps EVERY binding of a name, wherever in the file it is made, and a lookup
    tries them all (see `_candidates`). Keeping only the last one let a second binding hide
    a reading instead of adding one: after `import os as o`, a function that said
    `import json as o` made `o.system(...)` read as `json.system`. Now the worst a second
    binding can do is add a reading, never remove one.
    """
    table: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        _bind_import(node, table)

    # `name = <a plain name or dotted chain>`: a few passes, so the order of the lines does not matter.
    for _ in range(4):
        if not _bind_assignments(tree, table):
            break
    return table


def _add_binding(table: dict[str, set[str]], name: str, target: str) -> bool:
    """Record that `name` may mean `target`. True when that was news."""
    known = table.setdefault(name, set())
    if target in known:
        return False
    known.add(target)
    return True


def _bind_import(node: ast.AST, table: dict[str, set[str]]) -> None:
    """The names an `import` or `from ... import` statement gives a module or a member."""
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.asname:
                _add_binding(table, alias.asname, alias.name)
    elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
        for alias in node.names:
            _add_binding(table, alias.asname or alias.name, f"{node.module}.{alias.name}")


def _assignment_parts(node: ast.AST):
    """(targets, value) for `a = b`, `a: T = b` and `(a := b)`; None for anything else."""
    if isinstance(node, ast.Assign):
        return node.targets, node.value
    if isinstance(node, (ast.AnnAssign, ast.NamedExpr)) and node.value is not None:
        return [node.target], node.value
    return None


def _bind_assignments(tree: ast.AST, table: dict[str, set[str]]) -> bool:
    """One pass over the file's assignments; True when any name learned a new meaning."""
    grew = False
    for node in ast.walk(tree):
        parts = _assignment_parts(node)
        if parts is None:
            continue
        targets, value = parts
        found = _candidates(value, table)
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            for item in found:
                if item != target.id and _add_binding(table, target.id, item):
                    grew = True
    return grew


def _candidates(node: ast.AST, aliases: dict[str, set[str]]) -> set[str]:
    """Every dotted name `node` may mean — `o.system` -> {"o.system", "os.system"} — or an
    empty set if it is not a plain chain of names.

    The name as written is always one of them: a file that never imports `os` as `o` may
    still have a variable called `o`, and a file that rebinds `os` may still have the module.
    """
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return set()
    tail = list(reversed(parts))
    heads = {node.id} | aliases.get(node.id, set())
    return {".".join([head, *tail]) for head in heads}


def _forbidden_callable(dotted: str) -> tuple[str, str] | None:
    """(rule, detail) if `dotted` names something a mutation may not call, else None."""
    module, _, attr = dotted.rpartition(".")
    detail = FORBIDDEN_CALL_PATTERNS.get((module, attr))
    if detail is None:
        for (family, prefix), text in FORBIDDEN_CALL_PREFIXES.items():
            if module == family and attr.startswith(prefix):
                detail = text
                break
    if detail is not None:
        return "FORBIDDEN_CALL", detail
    if not module and attr in FORBIDDEN_BUILTINS:
        return "FORBIDDEN_BUILTIN", f"Forbidden builtin call: {attr}()"
    return None


def _constant_text(node: ast.AST) -> str | None:
    """The string a node evaluates to when it is built only from literals, else None.

    `'__cl' + 'ass__'` and `f"__cl{'ass'}__"` are the same attribute as `'__class__'`.
    A name built from a variable is not judged: nothing here can know what it holds.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _constant_text(node.left), _constant_text(node.right)
        return None if left is None or right is None else left + right
    if isinstance(node, ast.JoinedStr):
        pieces = []
        for part in node.values:
            inner = part.value if isinstance(part, ast.FormattedValue) else part
            text = _constant_text(inner)
            if text is None:
                return None
            pieces.append(text)
        return "".join(pieces)
    return None


class ASTGuardian:
    """Multi-pass AST analysis for self-evolution mutations."""

    def audit_source(self, source: str, file_path: str) -> ASTAuditReport:
        source_hash = hashlib.sha256(source.encode()).hexdigest()
        report = ASTAuditReport(file_path=file_path, source_hash=source_hash)

        if _is_referee(file_path):
            report.violations.append(
                Violation(
                    severity="BLOCK",
                    rule="REFEREE_IMMUTABILITY",
                    line=0,
                    detail=f"File {file_path} is an immutable referee file",
                )
            )
            return report

        try:
            tree = ast.parse(source, filename=file_path)
        except SyntaxError as e:
            report.violations.append(
                Violation(
                    severity="BLOCK",
                    rule="SYNTAX_ERROR",
                    line=e.lineno or 0,
                    detail=str(e),
                )
            )
            return report

        aliases = _aliases(tree)
        self._check_imports(tree, report)
        self._check_calls(tree, report, aliases)
        self._check_references(tree, report, aliases)
        self._check_dunders(tree, report, aliases)

        report.approved = not report.has_blockers
        return report

    def _check_imports(self, tree: ast.AST, report: ASTAuditReport) -> None:
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                modules = []
                if isinstance(node, ast.Import):
                    modules = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                    # A relative import (`from .code import x`) names a sibling file,
                    # never the standard-library module of the same name.
                    modules = [node.module.split(".")[0]]

                for mod in modules:
                    if mod in FORBIDDEN_IMPORT_MODULES:
                        report.violations.append(
                            Violation(
                                severity="BLOCK",
                                rule="FORBIDDEN_IMPORT",
                                line=node.lineno,
                                detail=f"Forbidden module import: {mod}",
                            )
                        )
                # `from os import *` brings `system` in under its own name, and there is no
                # list of what it brought. Only modules that have a forbidden call are refused.
                if (isinstance(node, ast.ImportFrom) and node.module and not node.level
                        and any(alias.name == "*" for alias in node.names)
                        and node.module in _MODULES_WITH_FORBIDDEN_CALLS
                        and node.module.split(".")[0] not in FORBIDDEN_IMPORT_MODULES):
                    report.violations.append(
                        Violation(
                            severity="BLOCK",
                            rule="FORBIDDEN_IMPORT",
                            line=node.lineno,
                            detail=(f"Wildcard import from {node.module}: the names it brings in "
                                    "cannot be checked, so import the ones you need by name"),
                        )
                    )

    def _check_calls(self, tree: ast.AST, report: ASTAuditReport,
                     aliases: dict[str, set[str]] | None = None) -> None:
        aliases = _aliases(tree) if aliases is None else aliases
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            candidates = sorted(_candidates(node.func, aliases))
            self._report_first_forbidden(candidates, node.lineno, report)
            if node.args and any(c in _MODULE_TABLE_LOOKUPS for c in candidates):
                self._check_module_key(node.args[0], node.lineno, report)
            self._check_named_attribute(node, report, aliases)

    @staticmethod
    def _report_first_forbidden(readings: list[str], line: int, report: ASTAuditReport,
                                suffix: str = "") -> None:
        """One violation for a call, however many things its name may stand for."""
        for dotted in readings:
            found = _forbidden_callable(dotted)
            if found is not None:
                rule, detail = found
                report.violations.append(
                    Violation(severity="BLOCK", rule=rule, line=line, detail=detail + suffix)
                )
                return

    def _check_named_attribute(self, node: ast.Call, report: ASTAuditReport,
                               aliases: dict[str, set[str]]) -> None:
        """`getattr(x, "__cl" + "ass__")` is `x.__class__` with extra steps, and
        `getattr(os, "system")` is `os.system`."""
        if not (isinstance(node.func, ast.Name) and node.func.id in _ATTRIBUTE_BY_NAME
                and len(node.args) >= 2):
            return
        name = _constant_text(node.args[1])
        if name in DANGEROUS_ATTRIBUTES:
            report.violations.append(
                Violation(
                    severity="BLOCK",
                    rule="DUNDER_MANIPULATION",
                    line=node.lineno,
                    detail=f"Dangerous dunder access: {name}",
                )
            )
        elif name:
            readings = [f"{base}.{name}" for base in sorted(_candidates(node.args[0], aliases))]
            self._report_first_forbidden(readings, node.lineno, report,
                                         f" (reached with {node.func.id})")

    def _check_references(self, tree: ast.AST, report: ASTAuditReport,
                          aliases: dict[str, set[str]] | None = None) -> None:
        """A forbidden callable that is named but not called: stored, passed on or returned.

        `run = os.system` does nothing by itself; the harm is `run(...)` later, or
        `map(os.system, commands)`. Nothing here follows a value that far, so naming one at all
        is refused. (A call is reported by `_check_calls`, and not twice.)
        """
        aliases = _aliases(tree) if aliases is None else aliases
        called = {id(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
        for node in ast.walk(tree):
            if id(node) in called:
                continue
            if not (isinstance(node, (ast.Attribute, ast.Name)) and isinstance(node.ctx, ast.Load)):
                continue
            for dotted in sorted(_candidates(node, aliases)):
                found = _forbidden_callable(dotted)
                if found is not None:
                    rule, detail = found
                    report.violations.append(
                        Violation(severity="BLOCK", rule=rule, line=node.lineno,
                                  detail=f"{detail} (named here without being called: {dotted})")
                    )
                    break

    @staticmethod
    def _check_module_key(key: ast.AST, line: int, report: ASTAuditReport) -> None:
        """`sys.modules['subprocess']` reaches a forbidden module without importing it."""
        name = _constant_text(key)
        if name is not None and name.split(".")[0] in FORBIDDEN_IMPORT_MODULES:
            report.violations.append(
                Violation(
                    severity="BLOCK",
                    rule="FORBIDDEN_IMPORT",
                    line=line,
                    detail=f"Forbidden module reached through sys.modules: {name}",
                )
            )

    def _check_dunders(self, tree: ast.AST, report: ASTAuditReport,
                       aliases: dict[str, set[str]] | None = None) -> None:
        aliases = _aliases(tree) if aliases is None else aliases
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in DANGEROUS_ATTRIBUTES:
                report.violations.append(
                    Violation(
                        severity="BLOCK",
                        rule="DUNDER_MANIPULATION",
                        line=node.lineno,
                        detail=f"Dangerous dunder access: {node.attr}",
                    )
                )
            elif isinstance(node, ast.Name) and node.id == "__builtins__":
                report.violations.append(
                    Violation(
                        severity="BLOCK",
                        rule="DUNDER_MANIPULATION",
                        line=node.lineno,
                        detail="Dangerous dunder access: __builtins__",
                    )
                )
            elif isinstance(node, ast.Subscript) and "sys.modules" in _candidates(node.value, aliases):
                self._check_module_key(node.slice, node.lineno, report)
