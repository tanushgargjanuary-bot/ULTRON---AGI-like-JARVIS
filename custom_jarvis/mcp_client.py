"""One client for every MCP server on this machine, instead of two hundred adaptors.

MCP — the Model Context Protocol — is a small JSON-RPC conversation over a program's
standard input and output. A server says what tools it has; this client turns each one
into a declaration `core/action_loader.py` already knows how to render. The work of
supporting a hundred tools then belongs to the people who wrote those tools.

Four rules, and each one is here because the alternative is a hole:

- **The owner starts the server, not the app.** A command comes from
  `config/mcp_servers.json`. Nothing is installed, downloaded, or fetched.
- **Local process only.** No URL, no socket, no port. A config entry with a `url` is
  refused with the reason, not ignored.
- **No shell.** A command is a program and a list of arguments. A command with a space
  in it is refused, because "split this yourself" is a real answer and `shell=True` is
  not.
- **No exemption from policy.** The tool names this client returns are names
  `core/policy.py` has never heard of, and it fails closed on the unknown: they are
  `guarded`, which means the owner is asked. This module cannot make that untrue.

A server that dies is a server that died. Every failure here is an exception the caller
can catch or a string the model can read — never a process this app cannot stop.
"""

from __future__ import annotations

import contextlib
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Iterable, Optional

PROTOCOL = "2024-11-05"
CLIENT = {"name": "ultron", "version": "1"}
CONFIG_NAME = Path("config") / "mcp_servers.json"

LIST_TIMEOUT = 20.0
CALL_TIMEOUT = 120.0
STOP_TIMEOUT = 4.0
MAX_TOOLS = 200
MAX_TEXT = 20_000

# Keys that only make sense for a transport this client does not implement. Refusing
# them by name is better than starting something the description did not promise.
_REFUSED_KEYS = ("url", "endpoint", "host", "port", "socket", "transport", "shell")


class McpError(RuntimeError):
    """Anything this client refuses or cannot do, in a sentence."""


def config_path(folder: Optional[Path] = None) -> Path:
    return (Path(folder) if folder else Path(__file__).resolve().parent.parent) / CONFIG_NAME


def load_config(folder: Optional[Path] = None) -> list[dict[str, Any]]:
    """The servers the owner listed. Refuses a bad entry; never guesses at one.

    A missing file is not an error: most machines have no MCP server, and the answer
    to "why are there no MCP tools" is then "you listed none", not a traceback.
    """
    path = config_path(folder)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError as error:
        raise McpError(f"Could not read {path}: {error}") from error
    try:
        document = json.loads(raw)
    except ValueError as error:
        raise McpError(f"{path.name} is not valid JSON: {error}") from error

    entries = document.get("servers") if isinstance(document, dict) else document
    if not isinstance(entries, list):
        raise McpError(f"{path.name} must hold a list under \"servers\".")

    return [_server(entry, index) for index, entry in enumerate(entries)]


def _server(entry: Any, index: int) -> dict[str, Any]:
    """One entry, checked. Refused by name and never guessed at."""
    where = f"server {index + 1}"
    if not isinstance(entry, dict):
        raise McpError(f"{where} is not an object.")
    for key in _REFUSED_KEYS:
        if key in entry:
            raise McpError(
                f"{where} sets '{key}'. This client runs a local program only — "
                "remove it and list a command instead."
            )
    name = str(entry.get("name") or "").strip()
    if not name or not name.replace("_", "").replace("-", "").isalnum():
        raise McpError(f"{where} needs a name of letters, digits, '_' or '-'.")
    command = entry.get("command")
    if not isinstance(command, str) or not command.strip():
        raise McpError(f"{where} ({name}) needs a command.")
    if command.strip() != command or " " in command:
        raise McpError(
            f"{where} ({name}) has a space in its command. Put the program in "
            "'command' and each word after it in 'args' — a shell string is not run."
        )
    args = entry.get("args", [])
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        raise McpError(f"{where} ({name}) needs 'args' as a list of strings.")
    return {
        "name": name,
        "command": command,
        "args": list(args),
        "cwd": str(entry.get("cwd") or "").strip() or None,
    }
    return servers


def _identifier(text: str) -> str:
    """A tool name this app can call: letters, digits and underscores."""
    kept = [char if (char.isalnum() or char == "_") else "_" for char in str(text)]
    name = "".join(kept).strip("_").lower()
    while "__" in name:
        name = name.replace("__", "_")
    return name or "tool"


# The six types the provider accepts, in its spelling. MCP servers write JSON Schema,
# which is lower case; the app's declarations are upper case, and `sanitize_declarations`
# in `core/action_loader.py` would otherwise rewrite (or drop) every argument.
_TYPES = {"STRING", "NUMBER", "INTEGER", "BOOLEAN", "ARRAY", "OBJECT"}


def _kind(value: Any) -> str:
    kind = str(value or "string").upper()
    return kind if kind in _TYPES else "STRING"


def schema(raw: Any) -> dict[str, Any]:
    """A server's `inputSchema`, in the shape this app sends and the provider accepts.

    Two changes and no others: the casing, and a `required` list that only names
    arguments that exist. Nothing is added, so a tool that takes no arguments stays a
    tool that takes no arguments.
    """
    if not isinstance(raw, dict):
        return {"type": "OBJECT", "properties": {}}
    properties: dict[str, Any] = {}
    for key, spec in (raw.get("properties") or {}).items():
        if not isinstance(spec, dict):
            spec = {}
        clean: dict[str, Any] = {"type": _kind(spec.get("type"))}
        if spec.get("description"):
            clean["description"] = str(spec["description"])[:500]
        if clean["type"] == "ARRAY":
            items = spec.get("items") if isinstance(spec.get("items"), dict) else {}
            clean["items"] = {"type": _kind(items.get("type"))}
        if clean["type"] == "OBJECT":
            clean["properties"] = {}
        enum = spec.get("enum")
        if isinstance(enum, list) and enum:
            clean["enum"] = [str(value)[:100] for value in enum[:50]]
        properties[str(key)] = clean
    out: dict[str, Any] = {"type": "OBJECT", "properties": properties}
    required = [str(name) for name in (raw.get("required") or []) if str(name) in properties]
    if required:
        out["required"] = required
    return out


def tool_name(server: str, tool: str) -> str:
    """`mcp_<server>_<tool>`, so a server can never shadow a native tool."""
    return f"mcp_{_identifier(server)}_{_identifier(tool)}"[:100]


class Client:
    """One server: start it, ask what it has, call it, stop it.

    One reader thread, one queue. A request waits for the reply with its own id and
    nothing else: a notification, a log line, or a server's idle chatter is dropped
    instead of being mistaken for an answer.
    """

    def __init__(self, entry: dict[str, Any], timeout: float = CALL_TIMEOUT):
        self.name = str(entry.get("name") or "server")
        self.command = str(entry.get("command") or "")
        self.args = [str(arg) for arg in entry.get("args") or []]
        self.cwd = entry.get("cwd")
        self.timeout = float(timeout)
        self._process: Optional[subprocess.Popen] = None
        self._replies: "queue.Queue[dict[str, Any]]" = queue.Queue()
        self._pending: dict[int, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._next_id = 0
        self._dead = ""
        self.stderr_tail: list[str] = []

    # ── lifecycle ───────────────────────────────────────────────────────────
    def start(self) -> None:
        """Run the program, then shake hands. Raises McpError with a readable reason."""
        if self._process is not None:
            return
        if not self.command:
            raise McpError(f"{self.name}: no command.")
        found = shutil.which(self.command) or (self.command if Path(self.command).is_file() else None)
        if not found:
            raise McpError(
                f"{self.name}: '{self.command}' was not found. Install it yourself; "
                "this app does not install servers."
            )
        try:
            self._process = subprocess.Popen(
                [found, *self.args],
                cwd=self.cwd or None,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                start_new_session=(os.name != "nt"),
            )
        except OSError as error:
            raise McpError(f"{self.name}: could not start '{self.command}': {error}") from error

        threading.Thread(target=self._read_stdout, daemon=True,
                         name=f"mcp-{self.name}").start()
        threading.Thread(target=self._read_stderr, daemon=True,
                         name=f"mcp-{self.name}-err").start()

        self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL,
                "capabilities": {},
                "clientInfo": CLIENT,
            },
            timeout=min(LIST_TIMEOUT, self.timeout),
        )
        self.notify("notifications/initialized")

    def close(self) -> None:
        """End the process whether or not it wants to.

        Called from a `finally`, on app exit, and by tests. An orphan here would be a
        program the owner did not start twice.
        """
        process = self._process
        self._process = None
        self._dead = self._dead or "closed"
        if process is None:
            return
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=STOP_TIMEOUT)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=STOP_TIMEOUT)
        except OSError:
            process.kill()          # it would not stop politely; it stops anyway
        finally:
            for stream in (process.stdin, process.stdout, process.stderr):
                with contextlib.suppress(OSError):
                    if stream is not None:
                        stream.close()

    def __enter__(self) -> "Client":
        self.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def alive(self) -> bool:
        return self._process is not None and self._process.poll() is None and not self._dead

    # ── the conversation ────────────────────────────────────────────────────
    def _read_stdout(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            text = line.strip()
            if not text:
                continue
            message: Any = None
            with contextlib.suppress(ValueError):
                message = json.loads(text)   # not ours? a server may print anything
            if not isinstance(message, dict) or "id" not in message:
                continue                    # a notification or a log
            with self._lock:
                slot = self._pending.get(message.get("id"))
            if slot is not None:
                slot["reply"] = message
                slot["event"].set()
        self._dead = self._dead or "the server stopped"

    def _read_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        for line in process.stderr:
            self.stderr_tail.append(line.rstrip()[:400])
            del self.stderr_tail[:-20]      # a bounded tail, never a growing file

    def _write(self, payload: dict[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            raise McpError(f"{self.name}: {self._dead or 'the server is not running'}.")
        try:
            process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            process.stdin.flush()
        except (OSError, ValueError) as error:
            raise McpError(f"{self.name}: the server closed its input ({error}).") from error

    def notify(self, method: str, params: Optional[dict[str, Any]] = None) -> None:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self._write(payload)

    def request(self, method: str, params: Optional[dict[str, Any]] = None,
                timeout: Optional[float] = None) -> Any:
        """Send one request, wait for the reply with its id, return `result`."""
        with self._lock:
            self._next_id += 1
            identity = self._next_id
            slot = {"event": threading.Event(), "reply": None}
            self._pending[identity] = slot
        try:
            self._write({"jsonrpc": "2.0", "id": identity, "method": method,
                         "params": params or {}})
            if not slot["event"].wait(float(timeout or self.timeout)):
                raise McpError(f"{self.name}: no answer to '{method}' in "
                               f"{int(timeout or self.timeout)}s.")
        finally:
            with self._lock:
                self._pending.pop(identity, None)

        reply = slot["reply"]
        if not isinstance(reply, dict):
            raise McpError(f"{self.name}: no answer to '{method}'.")
        if "error" in reply:
            error = reply.get("error") or {}
            raise McpError(f"{self.name}: {error.get('message') or 'the server refused'}"
                           f" (code {error.get('code')}).")
        return reply.get("result")

    # ── what the app needs ──────────────────────────────────────────────────
    def list_tools(self) -> list[dict[str, Any]]:
        result = self.request("tools/list", {}, timeout=min(LIST_TIMEOUT, self.timeout)) or {}
        tools = result.get("tools") if isinstance(result, dict) else None
        if not isinstance(tools, list):
            raise McpError(f"{self.name}: tools/list returned no list.")
        return [tool for tool in tools if isinstance(tool, dict) and tool.get("name")][:MAX_TOOLS]

    def call(self, tool: str, arguments: Optional[dict[str, Any]] = None,
             timeout: Optional[float] = None) -> dict[str, Any]:
        """Call one tool. The server's answer is returned as text this app can show."""
        result = self.request("tools/call",
                              {"name": tool, "arguments": arguments or {}},
                              timeout=timeout) or {}
        return _flatten(result)

    def declarations(self) -> list[dict[str, Any]]:
        """One declaration per tool, shaped the way `core/action_loader.py` reads them.

        `handler` runs the call. The name is prefixed, so policy has never seen it and
        answers with the fail-closed default: ask. Nothing here can change that.
        """
        rows = []
        for tool in self.list_tools():
            remote = str(tool.get("name"))
            name = tool_name(self.name, remote)
            declared = tool.get("inputSchema") or tool.get("input_schema") or {}
            rows.append(
                {
                    "name": name,
                    "description": str(tool.get("description") or f"{remote} on {self.name}")[:1000],
                    "parameters": schema(declared),
                    "handler": self._handler(remote),
                    "tier": "extra",
                    "brief": f"MCP: {self.name}",
                }
            )
        return rows

    def _handler(self, remote: str):
        def run(parameters: Optional[dict[str, Any]] = None, **_ignored) -> str:
            answer = self.call(remote, parameters or {})
            return answer["text"]

        return run


def _flatten(result: Any) -> dict[str, Any]:
    """The text of a tools/call answer, capped, plus whether the server said it failed."""
    if not isinstance(result, dict):
        return {"text": str(result)[:MAX_TEXT], "is_error": False}
    parts = []
    for item in result.get("content") or []:
        if isinstance(item, dict):
            if item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
            else:
                parts.append(f"[{item.get('type') or 'content'}]")
    if not parts and result.get("structuredContent") is not None:
        parts.append(json.dumps(result["structuredContent"], ensure_ascii=False, default=str))
    text = "\n".join(parts).strip() or "(no text in the answer)"
    return {"text": text[:MAX_TEXT], "is_error": bool(result.get("isError"))}


def connect_all(folder: Optional[Path] = None) -> tuple[list[Client], list[str]]:
    """Start every listed server that works. Returns the living clients and the refusals.

    One broken entry does not stop the others: a server the owner mistyped is one
    sentence in the log, not a start-up that fails.
    """
    clients: list[Client] = []
    notes: list[str] = []
    for entry in load_config(folder):
        client = Client(entry)
        try:
            client.start()
            clients.append(client)
        except McpError as error:
            notes.append(str(error))
            client.close()
    return clients, notes


def close_all(clients: Iterable[Client]) -> None:
    for client in clients:
        # One server that will not close must not leave the other ones running.
        with contextlib.suppress(Exception):
            client.close()


__all__ = [
    "Client",
    "McpError",
    "close_all",
    "config_path",
    "connect_all",
    "load_config",
    "tool_name",
]
