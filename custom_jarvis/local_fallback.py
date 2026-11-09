"""Prepare an explicitly approved, small local model as a temporary fallback.

The cloud ladder remains the default. Local fallback is available only when the owner
has enabled `local_fallback_consent` in config/api_keys.json. The selected model must
be quantized and between 1.5B and 3B parameters.

Three things this module does, and one it refuses to do.

- **Finds what is installed.** `GET /api/tags` on the Ollama port.
- **Starts it.** If nothing answers and `ollama` is on PATH, `ollama serve` is started;
  then the chosen model is loaded with `keep_alive`, so the first sentence is not spent
  waiting for 2 GB to come off the disk.
- **Plans the switch**: three provider slot ids and their settings, in memory.

It does **not** write `config/api_keys.json`. The switch lives for this session only.
A day later the quota is back, the app starts on the cloud model, and nothing has to be
undone. A settings file changed by a fallback path is a settings file that is wrong for
ever — and that file holds the keys.

No dependency and no network beyond the loopback address in `DEFAULT_URL`.
"""

from __future__ import annotations

import asyncio
import inspect
import ipaddress
import json
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from importlib.util import find_spec
from typing import Any, Callable, Optional
from urllib.parse import urlsplit

DEFAULT_URL = "http://127.0.0.1:11434"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
OPENAI_ENDPOINT = "/v1/chat/completions"
KEEP_ALIVE = "30m"
START_WAIT = 10.0
SHORT = 2.0

# The providers the pipeline engine needs, by slot. `openai_compat@ollama` is one file
# that speaks to every OpenAI-compatible server; `whisper@local` is faster-whisper on
# the CPU; `system_tts` is the voice the operating system already has.
LLM_ID = "openai_compat@ollama"
STT_LOCAL = "whisper@local"
TTS_ID = "system_tts"

_SIZE = re.compile(r"(\d+(?:\.\d+)?)b", re.IGNORECASE)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A local inference probe must not redirect to another service."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _local_url(url: str) -> bool:
    """Accept only a literal loopback HTTP address with no URL credentials."""
    try:
        parsed = urlsplit(str(url))
        address = ipaddress.ip_address(parsed.hostname or "")
        return (
            parsed.scheme.lower() == "http"
            and address.is_loopback
            and parsed.port is not None
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
        )
    except (TypeError, ValueError):
        return False


def _request_json(request: urllib.request.Request | str, timeout: float) -> Optional[dict]:
    """Use loopback only, reject redirects, and cap every response body."""
    target = request.full_url if isinstance(request, urllib.request.Request) else str(request)
    if not _local_url(target):
        return None
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), _NoRedirect()
    )
    try:
        with opener.open(request, timeout=max(0.05, min(float(timeout), 60.0))) as answer:
            if answer.status != 200:
                return None
            content_length = answer.headers.get("Content-Length")
            if content_length:
                try:
                    if int(content_length) > MAX_RESPONSE_BYTES:
                        return None
                except ValueError:
                    return None
            body = answer.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                return None
            value = json.loads(body.decode("utf-8", "replace"))
            return value if isinstance(value, dict) else None
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        return None


def _get(url: str, timeout: float = SHORT) -> Optional[dict]:
    """Fetch a bounded JSON response from a literal loopback address."""
    return _request_json(url, timeout)


def _post(url: str, payload: dict, timeout: float = 30.0) -> Optional[dict]:
    """Post JSON to a literal loopback address and decode a bounded response."""
    try:
        body = json.dumps(payload).encode("utf-8")
    except (TypeError, ValueError):
        return None
    if len(body) > MAX_RESPONSE_BYTES:
        return None
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    return _request_json(request, timeout)


def installed(url: str = DEFAULT_URL) -> list[str]:
    """The model names the local server has, or an empty list when it has none."""
    answer = _get(f"{url}/api/tags")
    rows = answer.get("models") if isinstance(answer, dict) else None
    if not isinstance(rows, list):
        return []
    names = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("model") or "").strip()
        if name:
            names.append(name)
    return names


def running(url: str = DEFAULT_URL) -> bool:
    return _get(f"{url}/api/tags", timeout=1.5) is not None


def start_server(url: str = DEFAULT_URL) -> bool:
    """`ollama serve`, if the program is installed and nothing is listening yet.

    Started detached and never waited on for longer than `START_WAIT`: this runs in
    the middle of a conversation, and a fallback that hangs is worse than one that
    fails with a sentence.
    """
    if running(url):
        return True
    program = shutil.which("ollama")
    if not program:
        return False
    try:
        subprocess.Popen(          # no shell: one program, no arguments from a model
            [program, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return False
    deadline = time.time() + START_WAIT
    while time.time() < deadline:
        if running(url):
            return True
        time.sleep(0.4)
    return False


def size_of(name: str) -> float:
    """`qwen3:4b` is 4.0; `lfm2:latest` is 0.0, because it does not say."""
    found = _SIZE.search(str(name).split(":")[-1] or str(name))
    return float(found.group(1)) if found else 0.0


def score(name: str) -> int:
    """Rank only models within the approved 1.5B–3B size window."""
    text = str(name).lower()
    points = 0
    if "qwen" in text:
        points += 30
    if "lfm" in text:
        points += 20
    if "tools" in text or "instruct" in text:
        points += 2
    return points


_NON_CHAT = ("embed", "nomic-embed", "mxbai", "bge-", "rerank")


def pick(models: list[str]) -> Optional[str]:
    """Choose the highest-ranked chat model in the approved 1.5B–3B size window."""
    candidates = [
        name for name in models
        if not any(marker in str(name).lower() for marker in _NON_CHAT)
        and 1.5 <= size_of(str(name)) <= 3.0
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda name: (-score(name), len(name), name))[0]


_QUANTIZED = re.compile(r"^(?:Q[2-8](?:_|$)|IQ[1-8](?:_|$))", re.IGNORECASE)


def approved_models(url: str, models: list[str]) -> list[str]:
    """Keep only 1.5B–3B chat models whose Ollama metadata confirms quantization."""
    approved = []
    for name in models:
        if not 1.5 <= size_of(name) <= 3.0:
            continue
        if any(marker in str(name).lower() for marker in _NON_CHAT):
            continue
        details = _post(f"{url}/api/show", {"model": name}, timeout=SHORT)
        row = details.get("details") if isinstance(details, dict) else None
        quantization = str((row or {}).get("quantization_level") or "").strip().upper()
        if _QUANTIZED.match(quantization):
            approved.append(name)
    return approved


def warm(url: str = DEFAULT_URL, model: str = "") -> bool:
    """Load it now, so the first answer does not pay for the load."""
    if not model:
        return False
    answer = _post(f"{url}/api/generate",
                   {"model": model, "prompt": "", "keep_alive": KEEP_ALIVE},
                   timeout=60.0)
    return answer is not None


def _notify(log: Optional[Callable[[str], Any]], message: str) -> None:
    """Send a fallback status line when the caller supplied a logger."""
    if log:
        log(message)


async def prepare_switch(
    current: Optional[dict] = None,
    *,
    consent: bool = False,
    url: str = DEFAULT_URL,
    log: Optional[Callable[[str], Any]] = None,
    plan_builder: Optional[Callable[..., dict]] = None,
    warm_model: Optional[Callable[[str, str], bool]] = None,
    stt_ready: Optional[Callable[[dict], Any]] = None,
) -> Optional[dict]:
    """Plan, warm, and validate a local fallback before handing it to the app."""
    if consent is not True:
        _notify(log, "SYS: Local fallback is disabled because explicit consent is not set.")
        return None
    loop = asyncio.get_running_loop()
    builder = plan_builder or plan
    warmer = warm_model or warm
    try:
        proposed = await loop.run_in_executor(
            None, lambda: builder(url=url, current=current, consent=consent)
        )
    except Exception as error:
        _notify(log, f"ERR: could not look for a local model — {error}")
        return None
    if not isinstance(proposed, dict):
        _notify(log, "ERR: the local-model planner returned an invalid result.")
        return None
    if not proposed.get("ok"):
        _notify(log, f"ERR: {proposed.get('note', 'no local model is available')}")
        return None

    _notify(log, f"SYS: Loading {proposed['model']} from Ollama…")
    try:
        warmed = await loop.run_in_executor(
            None, lambda: warmer(proposed.get("url") or url, proposed["model"])
        )
    except Exception as error:
        _notify(log, f"ERR: Ollama warm-up failed ({error}); staying on the cloud retry.")
        return None
    if not warmed:
        _notify(log, f"ERR: Ollama did not load {proposed['model']}; staying on the cloud retry.")
        return None

    if stt_ready is not None:
        try:
            readiness = stt_ready(proposed)
            if inspect.isawaitable(readiness):
                readiness = await readiness
        except Exception as error:
            _notify(log, f"ERR: local speech recognition could not start ({error}); "
                    "staying on the cloud retry.")
            return None
        if not readiness:
            _notify(log, "ERR: local speech recognition is not ready; staying on the cloud retry.")
            return None
    return proposed


def _hearing(current: dict) -> tuple[Optional[str], str]:
    """Which speech recognition to use, and what to say if there is none."""
    if find_spec("faster_whisper") is not None:
        return STT_LOCAL, ""
    already = str(current.get("stt") or "").strip()
    if already:
        return already, f"hearing stays on {already} — faster-whisper is not installed"
    return None, ("no speech recognition on this machine: install faster-whisper "
                  "(pip install faster-whisper) or choose a Whisper API in the panel")


def _no_model_note(names: list[str]) -> str:
    """Explain which chat-model installation constraint blocked the local switch."""
    chat_names = [name for name in names if not any(
        marker in str(name).lower() for marker in _NON_CHAT
    )]
    if names and not chat_names:
        return ("Ollama has models installed, but they are embedding-only. "
                "Install a quantized 1.5B–3B chat model to enable local fallback.")
    if names:
        return ("No installed chat model meets the local-fallback policy. "
                "Use a quantized 1.5B–3B model; other sizes and unquantized models are refused.")
    return ("Ollama is running but no model is installed. "
            "Install a quantized 1.5B–3B chat model to enable local fallback.")


def plan(url: str = DEFAULT_URL, current: Optional[dict] = None,
         models: Optional[list[str]] = None, *, consent: bool = False) -> dict:
    """Build a temporary local plan, or explain why policy refuses the switch.

    `models` is for tests and for a caller that already asked. Nothing is written.
    """
    if consent is not True:
        return {"ok": False, "note": (
            "Local fallback is disabled. Enable local_fallback_consent in "
            "config/api_keys.json only after approving local processing."
        )}
    # Asking for a server that was never probed is a guess, and a guess here starts a
    # program in the middle of a conversation. Only the real path may do that.
    probed = models is None
    names = installed(url) if probed else list(models)
    if not names and probed:
        if not start_server(url):
            return {"ok": False, "note": (
                "The cloud is out of quota and Ollama is not answering. Install it from "
                "ollama.com, or start it with 'ollama serve', and I will switch over.")}
        names = installed(url)
    eligible = approved_models(url, names)
    model = pick(eligible)
    if not model:
        return {"ok": False, "note": _no_model_note(names)}

    stt, hearing_note = _hearing(dict(current or {}))
    if not stt:
        return {"ok": False, "model": model, "note": hearing_note}

    pipeline = {"llm": LLM_ID, "stt": stt, "tts": TTS_ID}
    previous_creds = dict((current or {}).get("provider_config") or {})
    # The small-model cap is set on this instance only. The tool catalogue is the
    # part Qwen/LFM struggle with; their own provider defaults this same limit.
    creds = {
        LLM_ID: {"base_url": f"{url}/v1", "model": model, "api_key": "",
                 "max_tools": "12", "max_tool_chars": "12000"},
        stt: ({"backend": "local"} if stt == STT_LOCAL
              else dict(previous_creds.get(stt) or {})),
        TTS_ID: {},
    }
    private = stt == STT_LOCAL and not hearing_note
    note = (f"The cloud quota is used up. Talking through {model} on this machine "
            "instead — slower, free, and private."
            if private else
            f"The cloud quota is used up. Talking through {model} on this machine "
            f"instead — slower. Speech recognition still uses {stt}, so this is not "
            "fully local and may still use that service.")
    return {
        "ok": True,
        "model": model,
        "url": url,
        "pipeline": pipeline,
        "creds": creds,
        "note": note + (f" ({hearing_note})" if hearing_note else ""),
    }
