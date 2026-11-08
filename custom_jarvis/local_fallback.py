"""When the cloud runs out of quota, the conversation moves to this machine.

The ladder in `core/gemini.py` already steps down through the live models. This is the
rung after the last one: Ollama on `localhost`, the model that is already installed,
and the pipeline engine — the second way to hold a conversation, which exists exactly
for the day the quota is gone.

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

import json
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from importlib.util import find_spec
from typing import Any, Optional

DEFAULT_URL = "http://localhost:11434"
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


def _get(url: str, timeout: float = SHORT) -> Optional[dict]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as answer:
            return json.loads(answer.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _post(url: str, payload: dict, timeout: float = 30.0) -> Optional[dict]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            return json.loads(answer.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


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
    """Which installed model to talk to when the cloud is gone.

    Two families are known to be worth their memory on a small machine — Qwen and LFM —
    and a model that needs more than this laptop has is not a candidate at any score.
    Everything else can still win by being the only thing installed.
    """
    text = str(name).lower()
    points = 0
    if "qwen" in text:
        points += 30
    if "lfm" in text:
        points += 20
    size = size_of(text)
    if 0 < size <= 8:
        points += 10
    elif 8 < size <= 14:
        points += 2
    elif size > 14:
        points -= 20
    if "tools" in text or "instruct" in text:
        points += 2
    return points


def pick(models: list[str]) -> Optional[str]:
    # Ollama also lists vector encoders and rerankers. They answer embeddings,
    # not chat, so a name match alone must never send the conversation to one.
    non_chat = ("embed", "nomic-embed", "mxbai", "bge-", "rerank")
    candidates = [name for name in models
                  if not any(marker in str(name).lower() for marker in non_chat)]
    if not candidates:
        return None
    return sorted(candidates, key=lambda name: (-score(name), len(name), name))[0]


def warm(url: str = DEFAULT_URL, model: str = "") -> bool:
    """Load it now, so the first answer does not pay for the load."""
    if not model:
        return False
    answer = _post(f"{url}/api/generate",
                   {"model": model, "prompt": "", "keep_alive": KEEP_ALIVE},
                   timeout=60.0)
    return answer is not None


def _hearing(current: dict) -> tuple[Optional[str], str]:
    """Which speech recognition to use, and what to say if there is none."""
    if find_spec("faster_whisper") is not None:
        return STT_LOCAL, ""
    already = str(current.get("stt") or "").strip()
    if already:
        return already, f"hearing stays on {already} — faster-whisper is not installed"
    return None, ("no speech recognition on this machine: install faster-whisper "
                  "(pip install faster-whisper) or choose a Whisper API in the panel")


def plan(url: str = DEFAULT_URL, current: Optional[dict] = None,
         models: Optional[list[str]] = None) -> dict:
    """Everything needed to move the conversation here, or the reason it cannot move.

    `models` is for tests and for a caller that already asked. Nothing is written.
    """
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
    model = pick(names)
    if not model:
        if names:
            note = ("Ollama has models installed, but they are embedding-only. "
                    "In a terminal: ollama pull qwen3:4b — then say continue.")
        else:
            note = ("Ollama is running but no model is installed. In a terminal: "
                    "ollama pull qwen3:4b — then say continue.")
        return {"ok": False, "note": note}

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
