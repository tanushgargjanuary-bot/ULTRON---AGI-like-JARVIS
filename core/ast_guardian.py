"""
core/ast_guardian.py — Production AST safety analysis for autonomous code modifications.
Rejects any proposed diff or code string containing forbidden imports, dynamic execution,
or dunder manipulation before it touches disk.
"""

from __future__ import annotations

import ast
import hashlib
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
    ("subprocess", "run"): "Direct subprocess forbidden in mutations",
    ("subprocess", "Popen"): "Direct subprocess forbidden in mutations",
    ("subprocess", "call"): "Direct subprocess forbidden in mutations",
    ("builtins", "eval"): "eval() forbidden",
    ("builtins", "exec"): "exec() forbidden",
    ("builtins", "compile"): "compile() forbidden",
    ("socket", "socket"): "Raw socket creation forbidden",
}

FORBIDDEN_IMPORT_MODULES: Set[str] = frozenset(
    {
        "subprocess",
        "ctypes",
        "mmap",
        "socket",
        "ssl",
        "winreg",
        "pickle",
        "dis",
        "gc",
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


class ASTGuardian:
    """Multi-pass AST analysis for self-evolution mutations."""

    def audit_source(self, source: str, file_path: str) -> ASTAuditReport:
        source_hash = hashlib.sha256(source.encode()).hexdigest()
        report = ASTAuditReport(file_path=file_path, source_hash=source_hash)

        normalized_path = file_path.replace("\\", "/")
        if normalized_path in REFEREE_FILES:
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

        self._check_imports(tree, report)
        self._check_calls(tree, report)
        self._check_dunders(tree, report)

        report.approved = not report.has_blockers
        return report

    def _check_imports(self, tree: ast.AST, report: ASTAuditReport) -> None:
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                modules = []
                if isinstance(node, ast.Import):
                    modules = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
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

    def _check_calls(self, tree: ast.AST, report: ASTAuditReport) -> None:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                key = (node.func.value.id, node.func.attr)
                if key in FORBIDDEN_CALL_PATTERNS:
                    report.violations.append(
                        Violation(
                            severity="BLOCK",
                            rule="FORBIDDEN_CALL",
                            line=node.lineno,
                            detail=FORBIDDEN_CALL_PATTERNS[key],
                        )
                    )

            if isinstance(node.func, ast.Name):
                if node.func.id in {"eval", "exec", "compile", "__import__"}:
                    report.violations.append(
                        Violation(
                            severity="BLOCK",
                            rule="FORBIDDEN_BUILTIN",
                            line=node.lineno,
                            detail=f"Forbidden builtin call: {node.func.id}()",
                        )
                    )

    def _check_dunders(self, tree: ast.AST, report: ASTAuditReport) -> None:
        dangerous = {"__class__", "__bases__", "__mro__", "__globals__", "__builtins__"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in dangerous:
                report.violations.append(
                    Violation(
                        severity="BLOCK",
                        rule="DUNDER_MANIPULATION",
                        line=node.lineno,
                        detail=f"Dangerous dunder access: {node.attr}",
                    )
                )
