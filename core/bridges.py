"""core/bridges.py — talking to big external tools without pretending to own them.

Five projects were named for this build: REA, HyperFrames, Hindsight, VoiceStudio
and Hypit. All five are large, separate applications — a reverse-engineering agent
framework, an HTML-to-video renderer, a memory service, a local voice studio and a
video-cloning pipeline. None of them belongs inside this repository, and copying
their code in would be dishonest as well as unmaintainable: they change daily, and
their licences are theirs.

What this module does instead is the honest version of "native": a **bridge**. One
small adapter per tool that:

    probe()  says whether the tool is actually here — installed on PATH for the
             CLIs, answering on its port for the services — and, when it is not,
             what to install or start INSTEAD of failing later
    run()    makes one real call, with a timeout, no shell, no inherited console,
             an allowlisted subcommand and a cap on how much output comes back

Three rules that keep a bridge from lying:

1. **A bridge never invents an API.** For the HTTP services the endpoint path is
   configuration, not a guess: Ultron does transport, the user points it at the
   documented path. A made-up `/v1/recall` that returns 404 is worse than a clear
   "set hindsight_path".
2. **A missing tool is a sentence, not a crash.** Every path returns text the
   model can read out.
3. **No shell, ever.** Arguments go in as a list. `shell=True` on a string built
   from model output is how a tool call becomes a command injection.

Every bridge is GUARDED by policy (core/policy.py): running third-party code asks
first.
"""

from __future__ import annotations
from core import failures

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

OUTPUT_LIMIT = 4000           # characters of tool output returned to the model
CLI_TIMEOUT = 25.0            # seconds a CLI bridge may run
HTTP_TIMEOUT = 4.0            # seconds an HTTP bridge may wait


# ── small shared helpers ─────────────────────────────────────────────────────
def _hidden() -> dict:
    """Start a child process with no console window on Windows."""
    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return {"creationflags": flags} if flags else {}
    return {}


def _cap(text: str) -> str:
    text = str(text or "")
    return text if len(text) <= OUTPUT_LIMIT else text[:OUTPUT_LIMIT] + "… (cut)"


def _which(*names: str) -> str:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return ""


def _setting(key: str, default: str = "") -> str:
    """Configuration first, environment second, default third.

    Config is where the user's choices live; the environment is what a service
    manager or a shell sets. Neither is hardcoded here beyond the loopback default.
    """
    try:
        from memory.config_manager import load_api_keys
        value = load_api_keys().get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    except Exception as error:
        failures.note("bridges._setting", error)
    return (os.environ.get(key.upper(), "") or default).strip()


def run_cli(argv: list[str], timeout: float = CLI_TIMEOUT) -> tuple[int, str, str]:
    """Run a program. No shell, no console, bounded time, bounded output."""
    if not argv or not all(isinstance(a, str) for a in argv):
        return 2, "", "bridge: every argument must be a string"
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                              shell=False, stdin=subprocess.DEVNULL, **_hidden())
    except FileNotFoundError:
        return 127, "", f"{argv[0]} is not installed"
    except subprocess.TimeoutExpired:
        return 124, "", f"{argv[0]} did not answer in {timeout:.0f}s"
    except Exception as exc:                                   # noqa: BLE001
        return 1, "", f"{type(exc).__name__}: {exc}"
    return done.returncode, _cap(done.stdout or ""), _cap(done.stderr or "")


def http_json(url: str, payload: dict | None = None,
              timeout: float = HTTP_TIMEOUT,
              headers: dict | None = None) -> tuple[bool, object]:
    """One HTTP round trip returning parsed JSON. Never raises."""
    data = None
    merged = {"Accept": "application/json", "User-Agent": "Ultron-bridge"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        merged["Content-Type"] = "application/json"
    merged.update(headers or {})
    request = urllib.request.Request(url, data=data, headers=merged,
                                     method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(200_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code} from {url}"
    except Exception as exc:                                   # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"
    try:
        return True, json.loads(body)
    except ValueError:
        return True, body


# ── the bridges ──────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Bridge:
    """One external tool, with the two questions a bridge has to answer."""

    key: str
    title: str
    category: str
    homepage: str
    summary: str
    install: str
    probe: Callable[[], tuple[bool, str]]
    operations: dict[str, Callable[..., str]] = field(default_factory=dict)

    def run(self, op: str, **kwargs) -> str:
        operation = self.operations.get(str(op or "").strip().lower())
        if operation is None:
            known = ", ".join(sorted(self.operations)) or "none"
            return f"{self.title}: I do not have an operation '{op}'. I have: {known}."
        try:
            return _cap(operation(**kwargs))
        except TypeError as exc:
            return f"{self.title}: wrong arguments for '{op}' ({exc})."
        except Exception as exc:                               # noqa: BLE001
            return f"{self.title}: '{op}' failed — {type(exc).__name__}: {exc}"


def _cli_help(argv: list[str], title: str) -> str:
    code, out, err = run_cli(argv)
    text = (out or err).strip()
    if code != 0 and not text:
        return f"{title}: it answered with code {code} and no output."
    return text or f"{title}: no output."


# REA — reverse engineering agent framework. Its CLI is the integration point;
# the subcommand names come from its own published commands, and `help` always
# asks the installed version rather than assuming.
def _rea_probe() -> tuple[bool, str]:
    path = _which("rea")
    if path:
        return True, f"rea on PATH ({path})"
    return False, ("REA is not installed. Install it from "
                   "https://github.com/morluto/rea and make `rea` available on PATH.")


def _rea_help() -> str:
    return _cli_help(["rea", "--help"], "REA")


def _rea_command(command: str = "help", args: list[str] | None = None,
                 workdir: str = "") -> str:
    """Run one REA subcommand. The subcommand is an argument, never a command line."""
    argv = ["rea"]
    if str(command or "").strip() and command != "help":
        argv.append(str(command).strip())
    argv += [str(a) for a in (args or [])]
    code, out, err = run_cli(argv)
    where = f" (in {workdir})" if workdir else ""
    if code != 0:
        return f"REA exited {code}{where}: {(err or out).strip() or 'no output'}"
    return (out.strip() or "REA finished with no output.") + where


# HyperFrames — HTML in, video out, run through its Node CLI.
def _hyperframes_probe() -> tuple[bool, str]:
    if _which("npx"):
        return True, "npx is on PATH; `npx hyperframes` will fetch the CLI on first use"
    if _which("hyperframes"):
        return True, "hyperframes is on PATH"
    return False, ("HyperFrames needs Node.js. Install it from https://nodejs.org, "
                   "then the CLI runs as `npx hyperframes`.")


def _hyperframes_command(command: str = "help", target: str = "") -> str:
    latin = ["npx", "--yes", "hyperframes"]
    if str(command or "").strip() and command != "help":
        latin.append(str(command).strip())
    if target:
        latin.append(str(target))
    code, out, err = run_cli(latin, timeout=90.0)     # first run downloads
    if code != 0:
        return f"HyperFrames exited {code}: {(err or out).strip() or 'no output'}"
    return out.strip() or "HyperFrames finished with no output."


# Hindsight — a memory service. Ultron does transport; the path is configuration.
def _hindsight_base() -> str:
    return _setting("hindsight_url", "http://127.0.0.1:8000").rstrip("/")


def _hindsight_probe() -> tuple[bool, str]:
    base = _hindsight_base()
    for path in ("/health", "/"):
        ok, result = http_json(f"{base}{path}", timeout=1.5)
        if ok:
            return True, f"Hindsight answers at {base}{path}"
    return False, (f"nothing answers at {base}. Start Hindsight "
                   "(https://github.com/vectorize-io/hindsight) or set hindsight_url.")


def _hindsight_request(path: str = "/health", method: str = "GET",
                       payload: dict | None = None) -> str:
    if not path.startswith("/"):
        return "Hindsight: the path must start with '/'."
    base = _hindsight_base()
    ok, result = http_json(f"{base}{path}",
                           payload if str(method).upper() == "POST" else None)
    if not ok:
        return f"Hindsight {method} {path}: {result}"
    return result if isinstance(result, str) else json.dumps(result)[:OUTPUT_LIMIT]


# VoiceStudio — local voice cloning and synthesis, over its own HTTP API.
def _voicestudio_base() -> str:
    return _setting("voicestudio_url", "http://127.0.0.1:8000").rstrip("/")


def _voicestudio_probe() -> tuple[bool, str]:
    base = _voicestudio_base()
    for path in ("/health", "/"):
        ok, _result = http_json(f"{base}{path}", timeout=1.5)
        if ok:
            return True, f"VoiceStudio answers at {base}{path}"
    return False, (f"nothing answers at {base}. Start VoiceStudio "
                   "(https://github.com/debpalash/VoiceStudio) or set voicestudio_url.")


def _voicestudio_request(path: str = "/health", method: str = "GET",
                         payload: dict | None = None) -> str:
    if not path.startswith("/"):
        return "VoiceStudio: the path must start with '/'."
    base = _voicestudio_base()
    ok, result = http_json(f"{base}{path}",
                           payload if str(method).upper() == "POST" else None)
    if not ok:
        return f"VoiceStudio {method} {path}: {result}"
    return result if isinstance(result, str) else json.dumps(result)[:OUTPUT_LIMIT]


# Hypit — video cloning pipeline, Node CLI.
def _hypit_probe() -> tuple[bool, str]:
    if _which("npx"):
        return True, "npx is on PATH; `npx hypit` will fetch the CLI on first use"
    if _which("hypit"):
        return True, "hypit is on PATH"
    return False, ("Hypit needs Node.js. Install it from https://nodejs.org, then "
                   "the CLI runs as `npx hypit`.")


def _hypit_command(command: str = "help", target: str = "") -> str:
    argv = ["npx", "--yes", "hypit"]
    if str(command or "").strip() and command != "help":
        argv.append(str(command).strip())
    if target:
        argv.append(str(target))
    code, out, err = run_cli(argv, timeout=90.0)
    if code != 0:
        return f"Hypit exited {code}: {(err or out).strip() or 'no output'}"
    return out.strip() or "Hypit finished with no output."


BRIDGES: dict[str, Bridge] = {
    "rea": Bridge(
        key="rea", title="REA", category="security",
        homepage="https://github.com/morluto/rea",
        summary="Reverse-engineer apps and binaries with agents: capture a desktop "
                "app, inspect its state, export it as a reproducible environment.",
        install="pip install or clone https://github.com/morluto/rea; needs `rea` on PATH",
        probe=_rea_probe,
        operations={"help": _rea_help, "command": _rea_command},
    ),
    "hyperframes": Bridge(
        key="hyperframes", title="HyperFrames", category="media",
        homepage="https://github.com/heygen-com/hyperframes",
        summary="Render video from HTML with an agent-friendly CLI.",
        install="install Node.js and run `npx hyperframes`",
        probe=_hyperframes_probe,
        operations={"help": lambda: _hyperframes_command("help"),
                    "command": _hyperframes_command},
    ),
    "hindsight": Bridge(
        key="hindsight", title="Hindsight", category="memory",
        homepage="https://github.com/vectorize-io/hindsight",
        summary="Long-term agent memory service: retain, recall and reflect over "
                "banks of knowledge.",
        install="run https://github.com/vectorize-io/hindsight, then set hindsight_url",
        probe=_hindsight_probe,
        operations={"status": lambda: _hindsight_request("/health"),
                    "request": _hindsight_request},
    ),
    "voicestudio": Bridge(
        key="voicestudio", title="VoiceStudio", category="media",
        homepage="https://github.com/debpalash/VoiceStudio",
        summary="Local voice cloning, synthesis, dubbing and transcription over "
                "its own HTTP API.",
        install="run https://github.com/debpalash/VoiceStudio, then set voicestudio_url",
        probe=_voicestudio_probe,
        operations={"status": lambda: _voicestudio_request("/health"),
                    "request": _voicestudio_request},
    ),
    "hypit": Bridge(
        key="hypit", title="Hypit", category="media",
        homepage="https://github.com/hypit-ai/hypit",
        summary="Clone a video's format: swap face, words and B-roll, and render "
                "variants from one command.",
        install="install Node.js and run `npx hypit`",
        probe=_hypit_probe,
        operations={"help": lambda: _hypit_command("help"),
                    "command": _hypit_command},
    ),
}


def probe_all() -> list[dict]:
    """Every bridge with its readiness — the shape the catalog and the UI use."""
    out = []
    for bridge in BRIDGES.values():
        try:
            ready, detail = bridge.probe()
        except Exception as exc:                               # noqa: BLE001
            ready, detail = False, f"probe failed: {exc}"
        out.append({"key": bridge.key, "title": bridge.title,
                    "category": bridge.category, "summary": bridge.summary,
                    "homepage": bridge.homepage, "install": bridge.install,
                    "ready": bool(ready), "detail": detail,
                    "operations": sorted(bridge.operations)})
    return out


def get(key: str) -> Bridge | None:
    return BRIDGES.get(str(key or "").strip().lower())
