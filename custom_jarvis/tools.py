"""
Core tools for Custom Jarvis Desktop Agent.

Combines the best advantages of Open Interpreter (robust shell execution, file manipulation,
and timeout-guarded process management) and Claude Computer Use (GUI vision, mouse/keyboard
control, desktop application launching, and screen inspection).

Provides a unified ToolRegistry with multi-provider JSON schemas (OpenAI, Anthropic, Gemini)
for seamless function calling and autonomous agent loops.
"""

from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes
import functools
import inspect
import json
import logging
import os
import re
import shlex
import signal
import subprocess
import threading
import time
import types
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

try:
    import psutil
except ImportError:
    from custom_jarvis.compat import psutil_shim as psutil
import requests

from custom_jarvis import settings as config
from custom_jarvis.compat import HAS_PSUTIL, extract_webpage_text
from core import failures

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

logger = logging.getLogger("JarvisTools")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(name)s] %(levelname)s: %(message)s",
    )


# Enable Per-Monitor DPI awareness on Windows to prevent coordinate scaling offsets
def _enable_dpi_awareness():
    if os.name == "nt":
        try:
            # Per-Monitor DPI Aware (Windows 8.1 / 10 / 11)
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                # System DPI Aware (Windows Vista / 7)
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


# MARK owns process DPI and Qt setup; do not change it on import.


def get_screen_bounds() -> Tuple[int, int, int, int]:
    """Get the bounding rectangle of the full desktop across all monitors.

    Returns:
        (min_x, min_y, max_x, max_y)
    """
    if os.name == "nt":
        try:
            user32 = ctypes.windll.user32
            min_x = user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
            min_y = user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
            width = user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
            height = user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
            if width > 0 and height > 0:
                return (min_x, min_y, min_x + width, min_y + height)
        except Exception:
            pass
    try:
        import pyautogui

        w, h = pyautogui.size()
        return (0, 0, w, h)
    except Exception:
        return (0, 0, 1920, 1080)


# Attempt to configure pyautogui safely for desktop agent automation
try:
    import pyautogui

    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0.05
except Exception:
    pass


@dataclass
class ToolResult:
    """Standardized result returned by all tools.

    Provides dual compatibility:
    - String output (.output) for text display and LLM prompts.
    - Structured data (.data) for programmatic access.
    """

    success: bool
    output: str = ""
    data: Any = None
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert ToolResult to a dictionary."""
        return {
            "success": self.success,
            "output": self.output,
            "data": self.data,
            "error": self.error,
            "execution_time": self.execution_time,
            "metadata": self.metadata,
        }

    def to_json(self, indent: Optional[int] = 2) -> str:
        """Convert to formatted JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)


@dataclass
class ToolDefinition:
    """Metadata, parameters schema, and handler for a registered tool."""

    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable[..., Any]
    category: str = "general"

    def to_openai_schema(self) -> Dict[str, Any]:
        """Format as OpenAI / Groq function calling schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_anthropic_schema(self) -> Dict[str, Any]:
        """Format as Anthropic Claude Computer-Use tool schema."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }

    def to_gemini_schema(self) -> Dict[str, Any]:
        """Format as Google Gemini FunctionDeclaration schema."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


# ==============================================================================
# TOOL REGISTRY
# ==============================================================================


class ToolRegistry:
    """Central registry for discovering, inspecting, and invoking tools."""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}

    @property
    def tool_count(self) -> int:
        """Count tools without allocating full schema dictionaries."""
        return len(self._tools)

    def register(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        category: str = "general",
    ) -> Callable:
        """Decorator to register a tool function in the registry."""

        def decorator(func: Callable) -> Callable:
            tool_name = name or func.__name__
            tool_desc = description or (func.__doc__ or "").strip().split("\n")[0]

            # Auto-generate parameters schema from type hints if not explicitly provided
            param_schema = parameters
            if param_schema is None:
                sig = inspect.signature(func)
                props = {}
                reqs = []
                try:
                    hints = get_type_hints(func)
                except (NameError, TypeError):
                    hints = {}
                type_names = {
                    str: "string",
                    int: "integer",
                    float: "number",
                    bool: "boolean",
                    dict: "object",
                    list: "array",
                    type(None): "null",
                    "str": "string",
                    "int": "integer",
                    "float": "number",
                    "bool": "boolean",
                    "dict": "object",
                    "list": "array",
                }
                for p_name, param in sig.parameters.items():
                    if p_name in ("self", "cls", "cancel_event"):
                        continue
                    annotation = hints.get(p_name, param.annotation)
                    choices = (
                        get_args(annotation)
                        if get_origin(annotation) in (Union, types.UnionType)
                        else (annotation,)
                    )
                    names = list(
                        dict.fromkeys(
                            type_names.get(get_origin(choice) or choice, "string")
                            for choice in choices
                        )
                    )
                    props[p_name] = {"type": names[0] if len(names) == 1 else names}
                    if param.default == inspect.Parameter.empty:
                        reqs.append(p_name)

                param_schema = {
                    "type": "object",
                    "properties": props,
                    "required": reqs,
                }

            tool_def = ToolDefinition(
                name=tool_name,
                description=tool_desc,
                parameters=param_schema,
                handler=func,
                category=category,
            )
            self._tools[tool_name] = tool_def

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)

            return wrapper

        return decorator

    def register_alias(self, alias_name: str, target_name: str):
        """Register an alternative name pointing to an existing tool."""
        if target_name in self._tools:
            target = self._tools[target_name]
            alias_def = ToolDefinition(
                name=alias_name,
                description=f"Alias for {target_name}. {target.description}",
                parameters=target.parameters,
                handler=target.handler,
                category=target.category,
            )
            self._tools[alias_name] = alias_def

    def get(self, name: str) -> Optional[ToolDefinition]:
        """Retrieve tool definition by name."""
        return self._tools.get(name)

    def get_tool(self, name: str) -> Optional[Callable]:
        """Retrieve tool handler callable by name (compatibility helper)."""
        tool_def = self.get(name)
        return tool_def.handler if tool_def else None

    def list_tools(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """List metadata and schemas for all registered tools."""
        tools_list = []
        for name, tool in self._tools.items():
            if category and tool.category != category:
                continue
            tools_list.append(
                {
                    "name": tool.name,
                    "category": tool.category,
                    "description": tool.description,
                    "parameters": tool.parameters,
                }
            )
        return tools_list

    def get_schemas(self, format: str = "openai") -> List[Dict[str, Any]]:
        """Generate schema definitions for LLM function calling.

        Supported formats: 'openai', 'anthropic', 'gemini'.
        """
        fmt = format.lower()
        if fmt == "anthropic":
            return [tool.to_anthropic_schema() for tool in self._tools.values()]
        elif fmt == "gemini":
            return [tool.to_gemini_schema() for tool in self._tools.values()]
        else:
            return [tool.to_openai_schema() for tool in self._tools.values()]

    def execute(self, name: str, **kwargs) -> ToolResult:
        """Execute a tool by name with arguments and return a standardized ToolResult."""
        tool = self.get(name)
        if not tool:
            return ToolResult(
                success=False,
                output="",
                error=f"Tool '{name}' is not registered. Available: {list(self._tools.keys())}",
            )

        start_time = time.perf_counter()
        try:
            res = tool.handler(**kwargs)
            duration = round(time.perf_counter() - start_time, 3)

            if isinstance(res, ToolResult):
                if res.execution_time == 0.0:
                    res.execution_time = duration
                return res
            elif isinstance(res, dict):
                # Check for success flag in dictionary
                success = res.get("success", True)
                err = res.get("error")
                out = res.get("output", "")
                if not out:
                    # Provide formatted string if output not explicitly given
                    if "stdout" in res:
                        out = res["stdout"] or res.get("stderr", "")
                    elif "content" in res:
                        out = str(res["content"])
                    elif "message" in res:
                        out = str(res["message"])
                    else:
                        out = json.dumps(res, indent=2, default=str)
                return ToolResult(
                    success=success,
                    output=out,
                    data=res,
                    error=err,
                    execution_time=duration,
                    metadata=res.get("metadata", {}),
                )
            else:
                return ToolResult(
                    success=True,
                    output=str(res),
                    data=res,
                    error=None,
                    execution_time=duration,
                )
        except TypeError as te:
            duration = round(time.perf_counter() - start_time, 3)
            logger.error(f"Invalid arguments for tool '{name}': {te}", exc_info=True)
            return ToolResult(
                success=False,
                output="",
                error=f"Invalid arguments for tool '{name}': {str(te)}",
                execution_time=duration,
            )
        except Exception as e:
            duration = round(time.perf_counter() - start_time, 3)
            logger.error(f"Execution error in tool '{name}': {e}", exc_info=True)
            return ToolResult(
                success=False,
                output="",
                error=f"Exception in tool '{name}': {type(e).__name__}: {str(e)}",
                execution_time=duration,
            )


# Default global tool registry instance
registry = ToolRegistry()
default_registry = registry  # Alias for swarm compatibility


# ==============================================================================
# 1. SHELL EXECUTION (Open Interpreter Advantages)
# ==============================================================================


def _prepare_powershell_command(command: str) -> str:
    """Ensure PowerShell command executes executables and paths with spaces correctly."""
    cmd = command.strip()
    # 1. If the command starts with a quoted executable without call operator '&', prepend '& '
    if (cmd.startswith('"') or cmd.startswith("'")) and not cmd.startswith("&"):
        cmd = f"& {cmd}"

    # 2. Auto-quote unquoted drive-letter paths containing spaces (e.g. C:\Users\Tanush Garg\file.txt)
    pattern = r'(?<!["\'])\b([A-Za-z]:\\[^"\'\n\r\t<>|;]+?\s+[^"\'\n\r\t<>|;]*[^\s"\'\n\r\t<>|;])(?!["\'])'
    cmd = re.sub(pattern, lambda m: f'"{m.group(1)}"', cmd)
    return cmd


def _terminate_tree(proc):
    try:
        if HAS_PSUTIL:
            parent = psutil.Process(proc.pid)
            for child in parent.children(recursive=True):
                child.kill()
            parent.kill()
        elif os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=5,
                check=False,
            )
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        proc.kill()


@registry.register(
    name="execute_command",
    category="shell",
    description=(
        "Execute a shell command via PowerShell or CMD on Windows with real-time "
        "stdout/stderr capture, exit code tracking, timeout guard, and execution metrics."
    ),
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The exact shell command to execute.",
            },
            "shell": {
                "type": "string",
                "enum": ["powershell", "cmd"],
                "default": "powershell",
                "description": "Shell environment to use. Defaults to powershell.",
            },
            "timeout": {
                "type": "integer",
                "default": config.COMMAND_TIMEOUT_SECONDS,
                "description": "Maximum seconds to wait before terminating the process.",
            },
            "working_dir": {
                "type": "string",
                "description": "Optional working directory in which to execute.",
            },
        },
        "required": ["command"],
    },
)
def execute_command(
    command: str,
    shell: str = "powershell",
    timeout: int = config.COMMAND_TIMEOUT_SECONDS,
    working_dir: Optional[str] = None,
    cancel_event: threading.Event | None = None,
) -> ToolResult:
    """Execute command in PowerShell or CMD safely."""
    shell_lower = shell.lower()
    if shell_lower == "powershell":
        sanitized_command = _prepare_powershell_command(command)
        cmd_args = [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            sanitized_command,
        ]
    elif shell_lower == "cmd":
        cmd_args = ["cmd.exe", "/c", command]
    else:
        return ToolResult(
            success=False,
            output="",
            error=f"Unsupported shell '{shell}'. Supported: 'powershell', 'cmd'.",
        )

    cwd = str(Path(working_dir).resolve()) if working_dir else None
    start_time = time.perf_counter()

    try:
        proc = subprocess.Popen(
            cmd_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            start_new_session=(os.name != "nt"),
        )
        try:
            deadline = time.monotonic() + timeout
            while proc.poll() is None:
                if cancel_event is not None and cancel_event.is_set():
                    _terminate_tree(proc)
                    try:
                        proc.communicate(timeout=2)
                    except subprocess.TimeoutExpired:
                        pass
                    return ToolResult(
                        False,
                        error="Command terminated by user cancellation.",
                        metadata={
                            "requires_user_action": True,
                            "error_code": "CANCELLED",
                        },
                    )
                if time.monotonic() > deadline:
                    raise subprocess.TimeoutExpired(cmd_args, timeout)
                try:
                    stdout, stderr = proc.communicate(
                        timeout=min(0.05, max(0.001, deadline - time.monotonic()))
                    )
                    break
                except subprocess.TimeoutExpired:
                    continue
            else:
                stdout, stderr = proc.communicate(timeout=2)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            stdout_clean = stdout.strip() if stdout else ""
            stderr_clean = stderr.strip() if stderr else ""

            is_success = proc.returncode == 0
            primary_output = (
                stdout_clean or "(Command completed with no standard output)"
            )
            if not is_success and stderr_clean:
                primary_output = stderr_clean

            return ToolResult(
                success=is_success,
                output=primary_output,
                data={
                    "command": command,
                    "shell": shell,
                    "exit_code": proc.returncode,
                    "stdout": stdout_clean,
                    "stderr": stderr_clean,
                    "timed_out": False,
                    "duration_ms": duration_ms,
                },
                error=stderr_clean if not is_success else None,
                execution_time=round(duration_ms / 1000.0, 3),
                metadata={"returncode": proc.returncode, "timed_out": False},
            )
        except subprocess.TimeoutExpired:
            _terminate_tree(proc)

            try:
                stdout, stderr = proc.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                stdout, stderr = "", "Output pipes did not close after termination"
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            err_msg = (
                f"Command timed out after {timeout} seconds. Process tree terminated."
            )
            return ToolResult(
                success=False,
                output="",
                data={
                    "command": command,
                    "shell": shell,
                    "exit_code": -1,
                    "stdout": stdout or "",
                    "stderr": stderr or "",
                    "timed_out": True,
                    "duration_ms": duration_ms,
                },
                error=err_msg,
                execution_time=round(duration_ms / 1000.0, 3),
                metadata={"returncode": -1, "timed_out": True},
            )
    except Exception as e:
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return ToolResult(
            success=False,
            output="",
            error=f"Failed to spawn process: {type(e).__name__}: {str(e)}",
            execution_time=round(duration_ms / 1000.0, 3),
        )


# Backward compatibility alias for planner.py
@registry.register(
    name="run_shell",
    category="shell",
    description="Execute a shell command via PowerShell and capture output.",
)
def run_shell(
    command: str,
    timeout: int = config.COMMAND_TIMEOUT_SECONDS,
    cancel_event: threading.Event | None = None,
    working_dir: Optional[str] = None,
) -> ToolResult:
    """Compatibility wrapper calling execute_command."""
    return execute_command(
        command=command,
        shell="powershell",
        timeout=timeout,
        cancel_event=cancel_event,
        working_dir=working_dir,
    )


# ==============================================================================
# 2. FILE OPERATIONS
# ==============================================================================


@registry.register(
    name="read_file",
    category="file",
    description="Read file contents with support for line slicing and byte limits.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute or relative path to the file.",
            },
            "start_line": {
                "type": "integer",
                "description": "Optional 1-based start line number.",
            },
            "end_line": {
                "type": "integer",
                "description": "Optional 1-based end line number (inclusive).",
            },
            "max_bytes": {
                "type": "integer",
                "default": 100000,
                "description": "Maximum bytes to read before truncating (default 100KB).",
            },
        },
        "required": ["path"],
    },
)
def read_file(
    path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    max_bytes: int = 100000,
) -> ToolResult:
    """Read contents of a file safely."""
    try:
        target_path = Path(path).resolve()
        if not target_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"File not found: '{path}'",
            )
        if target_path.is_dir():
            return ToolResult(
                success=False,
                output="",
                error=f"Target is a directory, not a file: '{path}'",
            )

        with open(target_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        total_lines = len(lines)
        s_idx = max(0, (start_line - 1)) if start_line is not None else 0
        e_idx = end_line if end_line is not None else total_lines

        selected_lines = lines[s_idx:e_idx]
        content = "".join(selected_lines)

        truncated = False
        if len(content.encode("utf-8")) > max_bytes:
            content = content.encode("utf-8")[:max_bytes].decode(
                "utf-8", errors="ignore"
            )
            truncated = True

        return ToolResult(
            success=True,
            output=content,
            data={
                "path": str(target_path),
                "total_lines": total_lines,
                "start_line": s_idx + 1 if total_lines > 0 else 0,
                "end_line": min(e_idx, total_lines),
                "truncated": truncated,
                "size_bytes": target_path.stat().st_size,
            },
            metadata={
                "size_bytes": target_path.stat().st_size,
                "path": str(target_path),
            },
        )
    except Exception as e:
        return ToolResult(
            success=False,
            output="",
            error=f"Error reading file '{path}': {str(e)}",
        )


@registry.register(
    name="write_file",
    category="file",
    description="Write or append content to a file, automatically creating parent directories.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Target file path.",
            },
            "content": {
                "type": "string",
                "description": "The text content to write.",
            },
            "mode": {
                "type": "string",
                "enum": ["w", "a"],
                "default": "w",
                "description": "'w' for overwrite, 'a' for append. Defaults to 'w'.",
            },
            "append": {
                "type": "boolean",
                "default": False,
                "description": "Alternative boolean to append content. If True, overrides mode to 'a'.",
            },
            "make_parents": {
                "type": "boolean",
                "default": True,
                "description": "Whether to create missing parent directories. Defaults to True.",
            },
        },
        "required": ["path", "content"],
    },
)
def write_file(
    path: str,
    content: str,
    mode: str = "w",
    append: bool = False,
    make_parents: bool = True,
) -> ToolResult:
    """Write or append text content to a file on disk."""
    try:
        target_path = Path(path).resolve()
        if make_parents:
            target_path.parent.mkdir(parents=True, exist_ok=True)

        write_mode = "a" if (append or mode == "a") else "w"
        with open(target_path, write_mode, encoding="utf-8") as f:
            f.write(content)

        action = "appended to" if write_mode == "a" else "written to"
        msg = f"Successfully {action} '{target_path}' ({len(content)} characters)."

        return ToolResult(
            success=True,
            output=msg,
            data={
                "path": str(target_path),
                "mode": write_mode,
                "bytes_written": len(content.encode("utf-8")),
                "total_file_size": target_path.stat().st_size,
            },
            metadata={"path": str(target_path), "bytes_written": len(content)},
        )
    except Exception as e:
        return ToolResult(
            success=False,
            output="",
            error=f"Error writing to file '{path}': {str(e)}",
        )


@registry.register(
    name="list_dir",
    category="file",
    description="List directory contents with file metadata (size, modification time, type).",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "default": ".",
                "description": "Directory path to list. Defaults to current directory.",
            },
            "recursive": {
                "type": "boolean",
                "default": False,
                "description": "Whether to list subdirectories recursively.",
            },
            "max_depth": {
                "type": "integer",
                "default": 2,
                "description": "Maximum directory recursion depth if recursive is True.",
            },
        },
    },
)
def list_dir(
    path: str = ".",
    recursive: bool = False,
    max_depth: int = 2,
) -> ToolResult:
    """List directory contents with structured metadata."""
    try:
        target_path = Path(path).resolve()
        if not target_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Directory not found: '{path}'",
            )
        if not target_path.is_dir():
            return ToolResult(
                success=False,
                output="",
                error=f"Target is not a directory: '{path}'",
            )

        entries = []
        text_lines = []

        def scan(current_dir: Path, current_depth: int):
            try:
                for item in sorted(current_dir.iterdir()):
                    try:
                        stat = item.stat()
                        is_d = item.is_dir()
                        kind = "[DIR]" if is_d else "[FILE]"
                        size_str = f"{stat.st_size} bytes" if not is_d else "-"
                        text_lines.append(f"{kind:<6} {item.name:<30} {size_str}")
                        entries.append(
                            {
                                "name": item.name,
                                "path": str(item),
                                "is_dir": is_d,
                                "size_bytes": stat.st_size if not is_d else None,
                                "modified": datetime.fromtimestamp(
                                    stat.st_mtime
                                ).isoformat(),
                            }
                        )
                        if recursive and is_d and current_depth < max_depth:
                            scan(item, current_depth + 1)
                    except PermissionError:
                        pass
            except PermissionError:
                pass

        scan(target_path, 1)
        output_text = "\n".join(text_lines) if text_lines else "(Directory is empty)"

        return ToolResult(
            success=True,
            output=output_text,
            data={
                "directory": str(target_path),
                "total_items": len(entries),
                "items": entries,
            },
            metadata={"path": str(target_path), "count": len(entries)},
        )
    except Exception as e:
        return ToolResult(
            success=False,
            output="",
            error=f"Error listing directory '{path}': {str(e)}",
        )


# Backward compatibility alias
registry.register_alias("list_directory", "list_dir")


@registry.register(
    name="find_files",
    category="file",
    description="Find files matching a glob pattern starting from a search directory.",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern (e.g. '*.py', '*config*', '*.json').",
            },
            "search_path": {
                "type": "string",
                "default": ".",
                "description": "Base directory to search in. Defaults to current directory.",
            },
            "max_results": {
                "type": "integer",
                "default": 50,
                "description": "Maximum number of matching files to return.",
            },
        },
        "required": ["pattern"],
    },
)
def find_files(
    pattern: str,
    search_path: str = ".",
    max_results: int = 50,
) -> ToolResult:
    """Find files by glob pattern."""
    try:
        base_path = Path(search_path).resolve()
        if not base_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Search path not found: '{search_path}'",
            )

        matches = []
        text_lines = []
        for match in base_path.rglob(pattern):
            try:
                stat = match.stat()
                is_d = match.is_dir()
                matches.append(
                    {
                        "name": match.name,
                        "path": str(match.resolve()),
                        "is_dir": is_d,
                        "size_bytes": stat.st_size if not is_d else None,
                    }
                )
                kind = "[DIR]" if is_d else "[FILE]"
                text_lines.append(f"{kind} {match.resolve()}")
                if len(matches) >= max_results:
                    break
            except PermissionError:
                pass

        output_text = (
            "\n".join(text_lines)
            if text_lines
            else f"No files matching '{pattern}' found."
        )
        return ToolResult(
            success=True,
            output=output_text,
            data={
                "search_path": str(base_path),
                "pattern": pattern,
                "count": len(matches),
                "matches": matches,
            },
            metadata={"pattern": pattern, "count": len(matches)},
        )
    except Exception as e:
        return ToolResult(
            success=False,
            output="",
            error=f"Error finding files matching '{pattern}': {str(e)}",
        )


# ==============================================================================
# 3. DESKTOP & APP AUTOMATION
# ==============================================================================

APP_ALIASES: Dict[str, str] = {
    "notepad": "notepad.exe",
    "calc": "calc.exe",
    "calculator": "calc.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "edge": "msedge.exe",
    "msedge": "msedge.exe",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "powershell": "powershell.exe",
    "terminal": "wt.exe",
    "paint": "mspaint.exe",
    "mspaint": "mspaint.exe",
    "spotify": "spotify",
    "code": "code",
    "vscode": "code",
}


@registry.register(
    name="launch_app",
    category="desktop",
    description=(
        "Launch a desktop application on Windows (e.g. notepad, chrome, explorer, "
        "spotify, calc, terminal, code, or custom executable path)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "app_name": {
                "type": "string",
                "description": "Application name alias (e.g. 'notepad', 'chrome', 'spotify', 'calc') or binary path.",
            },
            "args": {
                "description": "Optional argument string or list of arguments to pass to the application.",
            },
        },
        "required": ["app_name"],
    },
)
def launch_app(
    app_name: str,
    args: Optional[Union[List[str], str]] = None,
) -> ToolResult:
    """Launch application in a non-blocking process."""
    clean_name = app_name.strip().lower()
    target = APP_ALIASES.get(clean_name, app_name)

    arg_list: List[str] = []
    if args:
        if isinstance(args, str):
            arg_list = shlex.split(args)
        elif isinstance(args, list):
            arg_list = [str(a) for a in args]

    cmd_to_run = [target] + arg_list
    proc = None

    try:
        proc = subprocess.Popen(
            cmd_to_run,
            shell=(clean_name in ["spotify", "terminal", "code"]),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        msg = f"Successfully launched '{app_name}' (PID: {proc.pid})."
        return ToolResult(
            success=True,
            output=msg,
            data={
                "app_name": app_name,
                "executable": target,
                "launched": True,
                "pid": proc.pid,
            },
            metadata={"pid": proc.pid, "executable": target},
        )
    except Exception as e_popen:
        # Fallback to os.startfile for registered shell protocols (e.g. spotify:, ms-settings:)
        try:
            if hasattr(os, "startfile"):
                os.startfile(target)
                msg = (
                    f"Successfully initiated launch of '{app_name}' via Windows Shell."
                )
                return ToolResult(
                    success=True,
                    output=msg,
                    data={
                        "app_name": app_name,
                        "executable": target,
                        "launched": True,
                        "pid": None,
                    },
                    metadata={"executable": target},
                )
        except Exception as e_start:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to launch '{app_name}': {e_popen}; shell fallback failed: {e_start}",
            )

        return ToolResult(
            success=False,
            output="",
            error=f"Failed to launch '{app_name}': {str(e_popen)}",
        )


# Backward compatibility alias
registry.register_alias("open_application", "launch_app")


def _is_process_elevated(pid: int) -> bool:
    """Check if process has Administrator / elevated token under Windows."""
    if not pid or os.name != "nt":
        return False
    try:
        process_query = 0x1000
        token_query = 0x0008
        token_elevation = 20
        h_proc = ctypes.windll.kernel32.OpenProcess(process_query, False, pid)
        if not h_proc:
            return False
        h_token = ctypes.wintypes.HANDLE()
        if not ctypes.windll.advapi32.OpenProcessToken(h_proc, token_query, ctypes.byref(h_token)):
            ctypes.windll.kernel32.CloseHandle(h_proc)
            return False

        class _TokenElevation(ctypes.Structure):
            _fields_ = [("TokenIsElevated", ctypes.wintypes.DWORD)]

        elev = _TokenElevation()
        ret_len = ctypes.wintypes.DWORD()
        success = ctypes.windll.advapi32.GetTokenInformation(
            h_token, token_elevation, ctypes.byref(elev), ctypes.sizeof(elev), ctypes.byref(ret_len)
        )
        ctypes.windll.kernel32.CloseHandle(h_token)
        ctypes.windll.kernel32.CloseHandle(h_proc)
        return bool(success and elev.TokenIsElevated != 0)
    except Exception as exc:
        failures.note("tools.process_elevation", exc)
        return False


def _find_top_application_window() -> int:
    """Find the top-most visible application window in Z-order excluding Ultron/Taskbar."""
    if os.name != "nt":
        return 0
    found_hwnd = 0
    my_pid = os.getpid()

    def enum_cb(h, _lparam):
        nonlocal found_hwnd
        if not ctypes.windll.user32.IsWindowVisible(h):
            return True
        length = ctypes.windll.user32.GetWindowTextLengthW(h)
        if length == 0:
            return True
        buff = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(h, buff, length + 1)
        win_title = buff.value.strip()
        if not win_title or win_title in ("Program Manager", "Task Switching", "Windows Input Experience"):
            return True
        h_pid = ctypes.wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(h, ctypes.byref(h_pid))
        if h_pid.value == my_pid:
            return True
        found_hwnd = h
        return False

    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    try:
        ctypes.windll.user32.EnumWindows(enum_proc(enum_cb), 0)
    except Exception as exc:
        failures.note("tools.find_top_window", exc)
    return found_hwnd


@registry.register(
    name="get_active_window",
    category="desktop",
    description="Retrieve title, process ID, and process name of the current active foreground window.",
    parameters={
        "type": "object",
        "properties": {},
    },
)
def get_active_window() -> ToolResult:
    """Get information about the currently active foreground window with elevation and focus awareness."""
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            hwnd = _find_top_application_window()
        if not hwnd:
            return ToolResult(
                success=True,
                output="Active Window: Desktop / No active window focused.",
                data={
                    "hwnd": 0,
                    "title": "Desktop / No Active Window",
                    "pid": None,
                    "process_name": "Unknown",
                    "is_elevated": False,
                },
            )

        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1) if length > 0 else ctypes.create_unicode_buffer(1)
        if length > 0:
            ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
        title = buff.value

        pid = ctypes.wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        my_pid = os.getpid()

        # If current foreground is Ultron itself or desktop, resolve top application in Z-order
        if pid.value == my_pid or title in ("Program Manager", "Shell_TrayWnd", ""):
            fallback_h = _find_top_application_window()
            if fallback_h:
                hwnd = fallback_h
                length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                buff = ctypes.create_unicode_buffer(length + 1) if length > 0 else ctypes.create_unicode_buffer(1)
                if length > 0:
                    ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value
                ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        proc_name = "Unknown"
        if pid.value:
            try:
                proc_name = psutil.Process(pid.value).name()
            except Exception as exc:
                failures.note("tools.process_name", exc)

        is_elevated = _is_process_elevated(pid.value) if pid.value else False
        resolved_title = title or "Untitled Window"
        elevation_note = " [ADMIN/ELEVATED — UIPI active]" if is_elevated else ""
        msg = f"Active Window: '{resolved_title}' (Process: {proc_name}, PID: {pid.value}){elevation_note}"

        return ToolResult(
            success=True,
            output=msg,
            data={
                "hwnd": hwnd,
                "title": resolved_title,
                "pid": pid.value if pid.value else None,
                "process_name": proc_name,
                "is_elevated": is_elevated,
            },
            metadata={"pid": pid.value, "title": resolved_title, "process": proc_name, "is_elevated": is_elevated},
        )
    except Exception as e:
        return ToolResult(
            success=False,
            output="",
            error=f"Failed to inspect active foreground window: {str(e)}",
        )


# ==============================================================================
# 4. CLAUDE COMPUTER USE VISION & GUI AUTOMATION
# ==============================================================================


@registry.register(
    name="take_screenshot",
    category="gui",
    description=(
        "Capture a full screenshot of the desktop and save it to disk. "
        "Returns the saved file path, resolution, file size, and optional base64 representation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Optional custom filename (e.g. 'screen.png'). Defaults to timestamped name.",
            },
            "save_dir": {
                "type": "string",
                "description": "Optional directory to save screenshot in. Defaults to config.SCREENSHOTS_DIR.",
            },
            "include_base64": {
                "type": "boolean",
                "default": False,
                "description": "Whether to return the base64-encoded PNG image data for direct LLM multimodal inspection.",
            },
        },
    },
)
def take_screenshot(
    filename: Optional[str] = None,
    save_dir: Optional[str] = None,
    include_base64: bool = False,
) -> ToolResult:
    """Capture screen and save image to disk and report locked/headless sessions as failures."""
    try:
        target_dir = Path(save_dir).resolve() if save_dir else config.SCREENSHOTS_DIR
        target_dir.mkdir(parents=True, exist_ok=True)

        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"screenshot_{timestamp}.png"
        elif not filename.lower().endswith((".png", ".jpg", ".jpeg")):
            filename = f"{filename}.png"

        filepath = target_dir / filename
        img = None
        is_fallback = False
        status_note = "Screen captured successfully."

        # Attempt standard live desktop capture across all monitors
        try:
            from PIL import ImageGrab

            img = ImageGrab.grab(all_screens=True)
        except Exception as e_grab:
            try:
                import pyautogui

                img = pyautogui.screenshot()
            except Exception as e_pyauto:
                return ToolResult(
                    success=False,
                    error=(
                        "Desktop capture unavailable. Unlock Windows and run J.A.R.V.I.S. "
                        "in the signed-in interactive desktop (not a service or disconnected "
                        "remote session), then retry. "
                        f"Capture errors: {e_grab}; {e_pyauto}"
                    ),
                    data={"is_fallback": True, "capture_available": False},
                    metadata={
                        "error_code": "DESKTOP_UNAVAILABLE",
                        "requires_user_action": True,
                    },
                )

        if img is None or img.width <= 0 or img.height <= 0:
            return ToolResult(success=False, error="Capture returned an empty image.")

        img.save(filepath, format="PNG")
        width, height = img.size

        data_dict = {
            "path": str(filepath.resolve()),
            "filename": filepath.name,
            "width": width,
            "height": height,
            "size_bytes": filepath.stat().st_size,
            "is_fallback": is_fallback,
            "note": status_note,
        }

        if include_base64:
            with open(filepath, "rb") as f:
                data_dict["base64"] = base64.b64encode(f.read()).decode("utf-8")

        msg = f"Screenshot saved to: '{filepath.resolve()}' ({width}x{height}, {filepath.stat().st_size} bytes)"
        return ToolResult(
            success=True,
            output=msg,
            data=data_dict,
            metadata={
                "path": str(filepath.resolve()),
                "dimensions": (width, height),
                "is_fallback": is_fallback,
            },
        )
    except Exception as e:
        return ToolResult(
            success=False,
            output="",
            error=f"Failed to capture screenshot: {str(e)}",
        )


@registry.register(
    name="click_at",
    category="gui",
    description="Move mouse cursor to coordinates (x, y) and perform a mouse click.",
    parameters={
        "type": "object",
        "properties": {
            "x": {
                "type": "integer",
                "description": "X coordinate in screen pixels.",
            },
            "y": {
                "type": "integer",
                "description": "Y coordinate in screen pixels.",
            },
            "button": {
                "type": "string",
                "enum": ["left", "right", "middle"],
                "default": "left",
                "description": "Mouse button to click.",
            },
            "clicks": {
                "type": "integer",
                "default": 1,
                "description": "Number of clicks (e.g. 1 for single, 2 for double).",
            },
        },
        "required": ["x", "y"],
    },
)
def click_at(
    x: int,
    y: int,
    button: str = "left",
    clicks: int = 1,
) -> ToolResult:
    """Click at coordinate (x, y) with multi-monitor and high-DPI bounds validation."""
    try:
        import pyautogui

        min_x, min_y, max_x, max_y = get_screen_bounds()
        if x < min_x or x >= max_x or y < min_y or y >= max_y:
            return ToolResult(
                success=False,
                output="",
                error=(
                    f"Coordinates ({x}, {y}) out of screen bounds. "
                    f"Virtual desktop bounds: X in [{min_x}, {max_x}), Y in [{min_y}, {max_y})."
                ),
            )

        pyautogui.click(x=x, y=y, clicks=clicks, button=button)
        msg = f"Clicked at coordinates ({x}, {y}) button={button} count={clicks}."
        return ToolResult(
            success=True,
            output=msg,
            data={
                "x": x,
                "y": y,
                "button": button,
                "clicks": clicks,
                "bounds": {
                    "min_x": min_x,
                    "min_y": min_y,
                    "max_x": max_x,
                    "max_y": max_y,
                },
            },
        )
    except Exception as e:
        return ToolResult(
            success=False,
            output="",
            error=f"GUI click failed: {str(e)}",
        )


# Backward compatibility alias
registry.register_alias("gui_click", "click_at")


@registry.register(
    name="type_text",
    category="gui",
    description="Type text string via simulated keyboard events.",
    parameters={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Text content to type into the currently focused element.",
            },
            "interval": {
                "type": "number",
                "default": 0.01,
                "description": "Delay in seconds between keystrokes.",
            },
        },
        "required": ["text"],
    },
)
def type_text(text: str, interval: float = 0.01) -> ToolResult:
    """Type text into active input field."""
    try:
        import pyautogui

        pyautogui.write(text, interval=interval)
        msg = f"Successfully typed {len(text)} characters."
        return ToolResult(
            success=True,
            output=msg,
            data={"typed_length": len(text), "interval": interval},
        )
    except Exception as e:
        return ToolResult(
            success=False,
            output="",
            error=f"GUI typing failed: {str(e)}",
        )


# Backward compatibility alias
registry.register_alias("gui_type", "type_text")


@registry.register(
    name="press_hotkey",
    category="gui",
    description="Trigger a keyboard hotkey combination (e.g. ['ctrl', 'c'], ['win', 'r'], or 'ctrl+shift+esc').",
    parameters={
        "type": "object",
        "properties": {
            "keys": {
                "description": "List of key names or '+'-separated string (e.g. ['ctrl', 'c'] or 'ctrl+c').",
            },
        },
        "required": ["keys"],
    },
)
def press_hotkey(keys: Union[List[str], str]) -> ToolResult:
    """Press a key combination."""
    try:
        import pyautogui

        if isinstance(keys, str):
            key_list = [k.strip().lower() for k in keys.replace("+", " ").split()]
        elif isinstance(keys, list):
            key_list = [str(k).strip().lower() for k in keys]
        else:
            return ToolResult(
                success=False,
                output="",
                error="Argument 'keys' must be a list of strings or a string (e.g. ['ctrl', 'c']).",
            )

        pyautogui.hotkey(*key_list)
        msg = f"Successfully triggered hotkey combination: {key_list}"
        return ToolResult(
            success=True,
            output=msg,
            data={"pressed_keys": key_list},
        )
    except Exception as e:
        return ToolResult(
            success=False,
            output="",
            error=f"Hotkey execution failed: {str(e)}",
        )


# ==============================================================================
# 5. WEB SEARCH & SCRAPING
# ==============================================================================


@registry.register(
    name="fetch_web_page",
    category="web",
    description="Fetch a web page via HTTP, extract clean readable text, and strip clutter (scripts, styles).",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Full URL of the web page to fetch (e.g. 'https://en.wikipedia.org/wiki/Artificial_intelligence').",
            },
            "timeout": {
                "type": "integer",
                "default": 15,
                "description": "HTTP request timeout in seconds.",
            },
            "max_chars": {
                "type": "integer",
                "default": 50000,
                "description": "Maximum characters of text to return before truncating.",
            },
        },
        "required": ["url"],
    },
)
def fetch_web_page(
    url: str,
    timeout: int = 15,
    max_chars: int = 50000,
) -> ToolResult:
    """Fetch URL and extract readable text with timeout, SSL, and encoding guards."""
    try:
        clean_url = url.strip()
        if not (clean_url.startswith("http://") or clean_url.startswith("https://")):
            clean_url = "https://" + clean_url

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36 CustomJarvis/1.0"
            ),
        }

        resp = None
        try:
            resp = requests.get(clean_url, headers=headers, timeout=timeout)
            resp.raise_for_status()
        except requests.exceptions.SSLError as ssl_err:
            # Fallback for development servers with self-signed SSL or corporate proxies
            logger.warning(
                f"SSL certificate verification failed for '{clean_url}': {ssl_err}. Retrying with verify=False..."
            )
            try:
                import urllib3

                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                resp = requests.get(
                    clean_url, headers=headers, timeout=timeout, verify=False
                )
                resp.raise_for_status()
            except Exception as e_verify:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"SSL certificate validation failed for '{clean_url}': {ssl_err}; insecure fallback failed: {e_verify}",
                )
        except requests.exceptions.Timeout:
            return ToolResult(
                success=False,
                output="",
                error=f"Request timed out after {timeout} seconds fetching '{clean_url}'.",
            )
        except requests.exceptions.RequestException as req_err:
            return ToolResult(
                success=False,
                output="",
                error=f"Network error fetching '{clean_url}': {req_err}",
            )

        if resp is None:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to obtain HTTP response from '{clean_url}'.",
            )

        resp.encoding = resp.apparent_encoding or "utf-8"
        title, text = extract_webpage_text(resp.text)

        truncated = False
        if len(text) > max_chars:
            text = text[:max_chars]
            truncated = True

        out_summary = f"Title: {title}\nURL: {clean_url}\n\nContent:\n{text}"
        return ToolResult(
            success=True,
            output=out_summary,
            data={
                "url": clean_url,
                "status_code": resp.status_code,
                "title": title,
                "content": text,
                "char_count": len(text),
                "truncated": truncated,
            },
            metadata={"status_code": resp.status_code, "title": title},
        )
    except Exception as e:
        return ToolResult(
            success=False,
            output="",
            error=f"Failed to fetch web page '{url}': {str(e)}",
        )


@registry.register(
    name="web_search",
    category="web",
    description="Search the web for information using DuckDuckGo Instant Answer and Wikipedia search.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query terms.",
            },
            "max_results": {
                "type": "integer",
                "default": 5,
                "description": "Maximum search result items to return.",
            },
        },
        "required": ["query"],
    },
)
def web_search(query: str, max_results: int = 5) -> ToolResult:
    """Search the web for quick information lookup with multi-engine fallback."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36 CustomJarvis/1.0"
        ),
    }
    results = []

    # 1. DuckDuckGo Instant Answer API
    try:
        ddg_resp = requests.get(
            f"https://api.duckduckgo.com/?q={requests.utils.quote(query)}&format=json&no_html=1",
            headers=headers,
            timeout=8,
        )
        if ddg_resp.status_code == 200:
            try:
                ddg_data = ddg_resp.json()
                if isinstance(ddg_data, dict):
                    if ddg_data.get("AbstractText"):
                        results.append(
                            {
                                "title": ddg_data.get("Heading") or query,
                                "url": ddg_data.get("AbstractURL")
                                or "https://duckduckgo.com",
                                "snippet": ddg_data.get("AbstractText"),
                                "source": "DuckDuckGo Instant Answer",
                            }
                        )
                    for topic in ddg_data.get("RelatedTopics", []):
                        if (
                            isinstance(topic, dict)
                            and "Text" in topic
                            and "FirstURL" in topic
                        ):
                            results.append(
                                {
                                    "title": topic.get("Text")[:80] + "...",
                                    "url": topic.get("FirstURL"),
                                    "snippet": topic.get("Text"),
                                    "source": "DuckDuckGo Topic",
                                }
                            )
                        if len(results) >= max_results:
                            break
            except Exception:
                pass
    except Exception:
        pass

    # 2. DuckDuckGo HTML Search Scraper Fallback
    if len(results) < max_results:
        try:
            ddg_html_resp = requests.get(
                f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}",
                headers=headers,
                timeout=8,
            )
            if ddg_html_resp.status_code == 200 and BeautifulSoup is not None:
                soup = BeautifulSoup(ddg_html_resp.text, "html.parser")
                result_elements = soup.select(
                    ".result, .web-result, .results_links, .result__body"
                )
                for elem in result_elements:
                    title_elem = elem.select_one(".result__title, .result__a, h2")
                    snippet_elem = elem.select_one(".result__snippet, .snippet")
                    url_elem = elem.select_one(".result__url, .result__a")

                    title_text = title_elem.get_text(strip=True) if title_elem else ""
                    snippet_text = (
                        snippet_elem.get_text(strip=True) if snippet_elem else ""
                    )
                    href = url_elem.get("href", "") if url_elem else ""

                    if title_text and (snippet_text or href):
                        results.append(
                            {
                                "title": title_text,
                                "url": href or "https://duckduckgo.com",
                                "snippet": snippet_text or title_text,
                                "source": "DuckDuckGo Web",
                            }
                        )
                    if len(results) >= max_results:
                        break
        except Exception:
            pass

    # 3. Wikipedia search API supplement
    if len(results) < max_results:
        try:
            wiki_resp = requests.get(
                f"https://en.wikipedia.org/w/api.php?action=opensearch&search={requests.utils.quote(query)}&limit={max_results}&namespace=0&format=json",
                headers=headers,
                timeout=8,
            )
            if wiki_resp.status_code == 200:
                try:
                    wiki_data = wiki_resp.json()
                    if isinstance(wiki_data, list) and len(wiki_data) >= 4:
                        titles = wiki_data[1]
                        snippets = wiki_data[2]
                        urls = wiki_data[3]
                        for t, s, u in zip(titles, snippets, urls):
                            results.append(
                                {
                                    "title": t,
                                    "url": u,
                                    "snippet": s or t,
                                    "source": "Wikipedia",
                                }
                            )
                            if len(results) >= max_results:
                                break
                except Exception:
                    pass
        except Exception:
            pass

    # Format output text for planner and user
    if results:
        formatted = []
        for r in results[:max_results]:
            formatted.append(
                f"Title: {r['title']}\nSnippet: {r['snippet']}\nLink: {r['url']}\n"
            )
        output_text = "\n---\n".join(formatted)
    else:
        output_text = f"No results found for query: '{query}'."

    return ToolResult(
        success=True,
        output=output_text,
        data={
            "query": query,
            "count": len(results[:max_results]),
            "results": results[:max_results],
        },
        metadata={"query": query, "count": len(results[:max_results])},
    )


# Backward compatibility alias
registry.register_alias("search_web", "web_search")
