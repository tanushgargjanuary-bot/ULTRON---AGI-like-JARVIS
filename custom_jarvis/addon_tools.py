"""Additive, bounded inspection skills. No imports execute projects or install packages."""

from __future__ import annotations

import ast
import difflib
import json
import os
import subprocess
from pathlib import Path

from custom_jarvis.evidence import bounded_text, file_digest
from custom_jarvis.tools import ToolRegistry, ToolResult


def register_addon_tools(registry: ToolRegistry) -> None:
    if registry.get("project_snapshot"):
        return

    def register(name, description, properties, required):
        return registry.register(
            name=name,
            description=description,
            category="inspection",
            parameters={
                "type": "object",
                "properties": properties,
                "required": required,
            },
        )

    path_schema = {
        "path": {"type": "string", "description": "Path inside the selected workspace"}
    }

    @register(
        "project_snapshot",
        "Inspect top-level project structure and markers without running project code.",
        path_schema,
        ["path"],
    )
    def project_snapshot(path: str = ".") -> ToolResult:
        root = Path(path).resolve()
        try:
            names = []
            truncated = False
            with os.scandir(root) as entries:
                for entry in entries:
                    names.append(entry.name)
                    if len(names) >= 300:
                        truncated = True
                        break
            markers = [
                name
                for name in (
                    "pyproject.toml",
                    "requirements.txt",
                    "package.json",
                    "Cargo.toml",
                    "go.mod",
                    "README.md",
                    ".git",
                )
                if (root / name).exists()
            ]
            data = {
                "root": str(root),
                "entries": sorted(names),
                "markers": markers,
                "truncated": truncated,
                "project_code_executed": False,
            }
            return ToolResult(True, output=json.dumps(data, indent=2), data=data)
        except OSError as exc:
            return ToolResult(False, error=str(exc))

    @register(
        "discover_project_files",
        "Bounded project file discovery excluding dependency, cache and VCS directories.",
        {
            "search_path": {"type": "string"},
            "pattern": {"type": "string"},
            "max_results": {"type": "integer"},
        },
        ["search_path", "pattern"],
    )
    def discover_project_files(
        search_path: str, pattern: str, max_results: int = 100
    ) -> ToolResult:
        import fnmatch

        root = Path(search_path).resolve()
        if not root.is_dir():
            return ToolResult(False, error="Project directory does not exist")
        excluded = {
            ".git",
            ".venv",
            "venv",
            "node_modules",
            "__pycache__",
            ".next",
            "dist",
            "build",
        }
        matches = []
        visited = 0
        limited = False
        errors = []

        def onerror(error):
            errors.append(str(error))

        for folder, directories, files in os.walk(
            root, followlinks=False, onerror=onerror
        ):
            directories[:] = sorted(d for d in directories if d not in excluded)
            for name in sorted(files):
                visited += 1
                path = Path(folder) / name
                if fnmatch.fnmatch(name, pattern) and path.resolve().is_relative_to(
                    root
                ):
                    matches.append(str(path.relative_to(root)))
                if visited >= 5000 or len(matches) >= min(100, max(1, max_results)):
                    limited = True
                    break
            if limited:
                break
        data = {
            "matches": matches,
            "files_visited": visited,
            "limited": limited,
            "excluded_directories": sorted(excluded),
            "errors": errors[:10],
        }
        return ToolResult(True, output=json.dumps(data, indent=2), data=data)

    @register(
        "git_inspect",
        "Read Git status/diff/log with no shell or project scripts.",
        {**path_schema, "view": {"type": "string", "enum": ["status", "diff", "log"]}},
        ["path"],
    )
    def git_inspect(path: str = ".", view: str = "status") -> ToolResult:
        commands = {
            "status": ["status", "--porcelain=v1", "--untracked-files=no"],
            "diff": ["diff", "--no-ext-diff", "--no-textconv", "--stat"],
            "log": ["log", "-5", "--oneline", "--no-decorate"],
        }
        if view not in commands:
            return ToolResult(False, error="Unsupported Git view")
        try:
            # A bounded temporary file avoids retaining arbitrary repository output in RAM.
            import tempfile

            with tempfile.TemporaryFile() as output:
                result = subprocess.run(
                    [
                        "git",
                        "--no-pager",
                        "--no-optional-locks",
                        "-c",
                        "core.fsmonitor=false",
                        *commands[view],
                    ],
                    cwd=Path(path).resolve(),
                    stdout=output,
                    stderr=output,
                    timeout=15,
                    check=False,
                )
                output.seek(0)
                text = output.read(64001).decode("utf-8", errors="replace")
            return ToolResult(
                result.returncode == 0,
                output=text[:64000],
                error=None if result.returncode == 0 else "Git inspection failed",
                data={"view": view, "truncated": len(text) > 64000},
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ToolResult(False, error=str(exc))

    @register(
        "inspect_python",
        "Parse Python syntax and list definitions/imports without importing or running it.",
        path_schema,
        ["path"],
    )
    def inspect_python(path: str) -> ToolResult:
        try:
            text = bounded_text(Path(path))
            tree = ast.parse(text, filename=path)
            definitions, imports = [], []
            for node in ast.walk(tree):
                if len(definitions) < 200 and isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ):
                    definitions.append(node.name)
                if len(imports) < 200 and isinstance(
                    node, (ast.Import, ast.ImportFrom)
                ):
                    imports.append(ast.unparse(node))
                if len(definitions) == 200 and len(imports) == 200:
                    break
            data = {
                "syntax_valid": True,
                "definitions": definitions,
                "imports": imports,
            }
            return ToolResult(
                True,
                output=json.dumps(data, indent=2),
                data=data,
                metadata={"verification": "verified", "evidence": "Python AST parse"},
            )
        except (OSError, UnicodeError, ValueError, SyntaxError, RecursionError) as exc:
            return ToolResult(False, error=str(exc))

    @register(
        "inspect_json",
        "Validate JSON and report shape without executing it.",
        path_schema,
        ["path"],
    )
    def inspect_json(path: str) -> ToolResult:
        try:
            data = json.loads(bounded_text(Path(path)))
            shape = {
                "valid": True,
                "type": type(data).__name__,
                "top_level_keys": list(data)[:100] if isinstance(data, dict) else [],
                "count": len(data) if isinstance(data, (dict, list)) else None,
            }
            return ToolResult(
                True,
                output=json.dumps(shape),
                data=shape,
                metadata={"verification": "verified", "evidence": "JSON parse"},
            )
        except (OSError, UnicodeError, ValueError, RecursionError) as exc:
            return ToolResult(False, error=str(exc))

    @register(
        "verify_file",
        "Check file existence and optional exact text or SHA-256 postconditions.",
        {
            **path_schema,
            "expected_text": {"type": "string"},
            "sha256": {"type": "string"},
        },
        ["path"],
    )
    def verify_file(
        path: str, expected_text: str | None = None, sha256: str | None = None
    ) -> ToolResult:
        try:
            target = Path(path)
            exists = target.is_file()
            digest = (
                file_digest(target)
                if exists and target.stat().st_size <= 8 * 1024 * 1024
                else None
            )
            passed = exists
            if expected_text is not None:
                passed = passed and bounded_text(target) == expected_text
            if sha256 is not None:
                passed = passed and digest == sha256.lower()
            data = {
                "exists": exists,
                "sha256": digest,
                "passed": passed,
                "scope": "requested file conditions only, not overall task correctness",
            }
            return ToolResult(
                passed,
                output=json.dumps(data),
                data=data,
                error=None if passed else "Requested file postcondition failed",
                metadata={"verification": "verified" if passed else "failed"},
            )
        except (OSError, UnicodeError, ValueError) as exc:
            return ToolResult(False, error=str(exc))

    @register(
        "preview_file_change",
        "Produce a bounded diff without modifying the file.",
        {**path_schema, "content": {"type": "string"}},
        ["path", "content"],
    )
    def preview_file_change(path: str, content: str) -> ToolResult:
        try:
            if len(content.encode("utf-8")) > 1024 * 1024:
                raise ValueError("Proposed content exceeds 1 MB diff limit")
            target = Path(path)
            old = bounded_text(target) if target.exists() else ""
            # difflib can be expensive on huge/repetitive input; bound lines as well.
            if max(len(old.splitlines()), len(content.splitlines())) > 10000:
                raise ValueError("Diff exceeds 10,000-line limit")
            import itertools

            lines = difflib.unified_diff(
                old.splitlines(True),
                content.splitlines(True),
                fromfile=path,
                tofile=path + " (proposed)",
            )
            diff = "".join(itertools.islice(lines, 2000))
            return ToolResult(
                True,
                output=diff[:64000] or "No changes",
                data={
                    "changed": old != content,
                    "written": False,
                    "output_may_be_truncated": True,
                },
            )
        except (OSError, UnicodeError, ValueError) as exc:
            return ToolResult(False, error=str(exc))

    @register(
        "inspect_accessibility",
        "Inspect foreground Windows accessibility elements; no clicks or typing.",
        {},
        [],
    )
    def inspect_accessibility() -> ToolResult:
        if os.name != "nt":
            return ToolResult(
                False,
                error="Windows UI Automation requires Windows",
                metadata={"requires_user_action": True},
            )
        try:
            import ctypes

            from pywinauto import Desktop

            handle = ctypes.windll.user32.GetForegroundWindow()
            if not handle:
                raise ValueError("No foreground window")
            window = Desktop(backend="uia").window(handle=handle).wrapper_object()
            elements = []
            # Direct children are intentionally bounded; no recursive tree crawl.
            for element in window.children()[:100]:
                info = element.element_info
                elements.append(
                    {
                        "name": info.name[:200],
                        "control_type": info.control_type,
                        "automation_id": info.automation_id,
                        "rectangle": str(info.rectangle),
                    }
                )
            data = {
                "window": window.window_text(),
                "children": elements,
                "scope": "foreground direct children, not full application understanding",
            }
            return ToolResult(
                True, output=json.dumps(data, ensure_ascii=False), data=data
            )
        except Exception as exc:
            return ToolResult(
                False,
                error=f"Accessibility inspection unavailable: {exc}",
                metadata={"requires_user_action": True},
            )

    @register(
        "analyze_screenshot",
        "Describe screenshot evidence using an explicitly configured vision provider. Requires action approval and upload consent.",
        {**path_schema, "question": {"type": "string"}},
        ["path"],
    )
    def analyze_screenshot(
        path: str,
        question: str = "Describe the visible application state and any obstacles.",
    ) -> ToolResult:
        from custom_jarvis.vision import VisionClient, VisionConfig

        try:
            text = VisionClient(VisionConfig.from_env()).describe(Path(path), question)
            return ToolResult(
                True,
                output=text,
                metadata={
                    "verification": "executed_unverified",
                    "evidence": "Model interpretation, not deterministic verification",
                },
            )
        except Exception as exc:
            return ToolResult(
                False,
                error=f"Vision unavailable: {exc}",
                metadata={"requires_user_action": True},
            )

    @register(
        "vision_capability_status",
        "Report vision configuration without contacting a provider or uploading images.",
        {},
        [],
    )
    def vision_capability_status() -> ToolResult:
        from custom_jarvis.vision import VisionConfig

        config = VisionConfig.from_env()
        data = {
            "vision_configured": config.configured,
            "uploads_enabled": config.allow_uploads,
            "model": config.model,
            "provider_reachability": "not tested",
        }
        return ToolResult(True, output=json.dumps(data), data=data)

    @register(
        "search_text",
        "Search file contents for a literal string or regular expression and return "
        "path:line hits. Read-only, bounded, and it never runs project code.",
        {
            **path_schema,
            "query": {"type": "string", "description": "Literal text or a regex"},
            "max_results": {"type": "integer"},
            "regex": {"type": "boolean", "description": "Treat the query as a regex"},
        },
        ["path", "query"],
    )
    def search_text(path: str = ".", query: str = "", max_results: int = 60,
                    regex: bool = False) -> ToolResult:
        import re as _re

        text = str(query or "")
        if not text:
            return ToolResult(False, error="A search needs a query.")
        root = Path(path).resolve()
        if not root.is_dir():
            return ToolResult(False, error=f"Not a directory inside the workspace: {root}")
        try:
            pattern = _re.compile(text if regex else _re.escape(text))
        except _re.error as exc:
            return ToolResult(False, error=f"That pattern does not compile: {exc}")

        limit = max(1, min(int(max_results or 60), 200))
        skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv",
                     "dist", "build", ".ruff_cache", ".pytest_cache"}
        hits, scanned, capped = [], 0, False
        for candidate in sorted(root.rglob("*")):
            if len(hits) >= limit:
                capped = True
                break
            if not candidate.is_file() or any(part in skip_dirs for part in candidate.parts):
                continue
            try:
                if candidate.stat().st_size > 1_000_000:
                    continue
                raw = candidate.read_bytes()
            except OSError:
                continue
            if b"\x00" in raw[:2048]:          # binary
                continue
            scanned += 1
            for number, line in enumerate(
                    raw.decode("utf-8", "replace").splitlines(), 1):
                if pattern.search(line):
                    hits.append({
                        "file": str(candidate.relative_to(root)),
                        "line": number,
                        "text": line.strip()[:200],
                    })
                    if len(hits) >= limit:
                        capped = True
                        break
        data = {"query": text, "files_scanned": scanned, "hits": hits,
                "truncated": capped}
        summary = (f"{len(hits)} hit(s) in {scanned} file(s)"
                   + (" — stopped at the limit" if capped else ""))
        return ToolResult(True, output=json.dumps(data, ensure_ascii=False), data=data,
                          metadata={"summary": summary})

    @register(
        "measure_code",
        "Count files, lines and languages in a folder, biggest files first. The "
        "answer to \"how big is this project\" without guessing.",
        {**path_schema, "max_files": {"type": "integer"}},
        ["path"],
    )
    def measure_code(path: str = ".", max_files: int = 4000) -> ToolResult:
        root = Path(path).resolve()
        if not root.is_dir():
            return ToolResult(False, error=f"Not a directory inside the workspace: {root}")
        limit = max(1, min(int(max_files or 4000), 20000))
        skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv",
                     "dist", "build", ".ruff_cache", ".pytest_cache"}
        by_language: dict = {}
        biggest, scanned, stopped = [], 0, False
        for candidate in root.rglob("*"):
            if not candidate.is_file():
                continue
            if any(part in skip_dirs for part in candidate.parts):
                continue
            if scanned >= limit:
                stopped = True
                break
            try:
                size = candidate.stat().st_size
                if size > 4_000_000:
                    continue
                lines = sum(1 for _ in candidate.open("rb"))
            except OSError:
                continue
            scanned += 1
            suffix = candidate.suffix.lower() or "(none)"
            row = by_language.setdefault(suffix, {"files": 0, "lines": 0})
            row["files"] += 1
            row["lines"] += lines
            biggest.append((lines, str(candidate.relative_to(root))))
        biggest.sort(reverse=True)
        data = {
            "files": scanned,
            "lines": sum(row["lines"] for row in by_language.values()),
            "languages": dict(sorted(by_language.items(),
                                     key=lambda item: item[1]["lines"], reverse=True)[:15]),
            "biggest": [{"lines": lines, "file": name} for lines, name in biggest[:10]],
            "truncated": stopped,
        }
        return ToolResult(True, output=json.dumps(data, ensure_ascii=False), data=data)
