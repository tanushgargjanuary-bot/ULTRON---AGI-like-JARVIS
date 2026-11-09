"""core/local_detector.py — Auto-detection and metadata extraction for local models.

WHY THIS EXISTS
    Users download models through Ollama, LM Studio, Jan, llama.cpp, or Hugging Face.
    Expecting a user to know exact port numbers, base URLs, model tags, and context
    limits is friction. This module auto-discovers running local model servers and
    on-disk model weights across all major local inference runners, classifies their
    capabilities (vision, coding, parameter size), and maps them to intelligent
    execution tiers (fast, smart, heavy, vision).

INVARIANTS & CONSTRAINTS
    - Zero external network requests: probes only loopback 127.0.0.1 with tight timeouts (<= 0.5s).
    - Uses 127.0.0.1 instead of localhost (avoids Windows IPv6 ::1 DNS resolution delay).
    - Never raises: catches all socket errors, timeouts, or parsing errors and returns clean data.
    - Caches scan results briefly (10s) to avoid unnecessary I/O during multi-turn reasoning.
"""

from __future__ import annotations

from core import failures
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit

# Known loopback endpoints and their default ports
LOCAL_ENDPOINTS = (
    ("ollama", "http://127.0.0.1:11434", "/api/tags", "/v1"),
    ("lmstudio", "http://127.0.0.1:1234", "/v1/models", "/v1"),
    ("jan", "http://127.0.0.1:1337", "/v1/models", "/v1"),
    ("llamacpp", "http://127.0.0.1:8080", "/v1/models", "/v1"),
    ("vllm", "http://127.0.0.1:8000", "/v1/models", "/v1"),
    ("localai", "http://127.0.0.1:8088", "/v1/models", "/v1"),
)

# A probe is allowed to contact only these fixed loopback endpoints.
_ALLOWED_LOOPBACK_PORTS = frozenset({11434, 1234, 1337, 8080, 8000, 8088})
_MAX_PROBE_BYTES = 512 * 1024
_MAX_MODELS_PER_SCAN = 256
_scan_lock = threading.Lock()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A local model server must not redirect its probe to another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_CACHE_TTL_SECONDS = 10.0
_cached_results: list[LocalModelInfo] = []
_last_scan_time: float = 0.0


@dataclass
class LocalModelInfo:
    """Standardized metadata for a detected local model."""
    name: str
    provider_id: str
    base_url: str
    running: bool
    size_bytes: int = 0
    param_size_b: float = 0.0
    has_vision: bool = False
    has_code: bool = False
    tier: str = "smart"  # "fast", "smart", "heavy", "vision"
    location: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def size_gb(self) -> float:
        return round(self.size_bytes / (1024 ** 3), 2) if self.size_bytes else 0.0


def _quick_http_get(url: str, timeout: float = 0.5) -> Optional[dict]:
    """Read a bounded JSON response from one of the known loopback endpoints.

    Redirects and environment proxies are disabled. The host and port are checked
    before a socket is opened, and response bodies have a strict size limit.
    """
    try:
        parsed = urlsplit(str(url))
        port = parsed.port
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or port not in _ALLOWED_LOOPBACK_PORTS
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            return None
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Ultron-ModelDetector/1.0", "Accept": "application/json"},
        )
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _NoRedirect()
        )
        with opener.open(req, timeout=max(0.05, min(float(timeout), 0.5))) as resp:
            if resp.status != 200:
                return None
            content_length = resp.headers.get("Content-Length")
            if content_length:
                try:
                    if int(content_length) > _MAX_PROBE_BYTES:
                        return None
                except ValueError:
                    return None
            body = resp.read(_MAX_PROBE_BYTES + 1)
            if len(body) > _MAX_PROBE_BYTES:
                return None
            value = json.loads(body.decode("utf-8", errors="replace"))
            return value if isinstance(value, dict) else None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        # Offline local services are normal. Do not fill the failure journal
        # with one connection-refused entry for every unused model server.
        return None
    except Exception as exc:
        failures.note("local_detector._quick_http_get", exc)
        return None


def _estimate_params_and_tier(name: str, size_bytes: int = 0) -> tuple[float, bool, bool, str]:
    """Extract parameter count, vision capability, coding capability, and recommended tier."""
    low = name.lower()
    
    # 1. Vision detection
    vision_cues = ("vl", "vision", "omni", "llava", "minicpm-v", "pixtral", "gemma3", "internvl", "moondream")
    has_vision = any(c in low for c in vision_cues)
    
    # 2. Code detection
    code_cues = ("coder", "code", "starcoder", "deepseek-coder", "qwen2.5-coder")
    has_code = any(c in low for c in code_cues)
    
    # 3. Parameter count extraction (e.g., "qwen3:4b", "2b", "0.5b", "70b")
    match = re.search(r"(\d+(?:\.\d+)?)\s*[bB]", name)
    param_size = float(match.group(1)) if match else 0.0
    
    # If not in name, estimate roughly from size in bytes
    if param_size == 0.0 and size_bytes > 0:
        gb = size_bytes / (1024 ** 3)
        if gb <= 2.2:
            param_size = 2.0
        elif gb <= 5.5:
            param_size = 4.0
        elif gb <= 9.0:
            param_size = 7.0
        elif gb <= 16.0:
            param_size = 14.0
        else:
            param_size = 32.0

    # 4. Tier assignment
    if has_vision:
        tier = "vision"
    elif param_size > 0 and param_size <= 3.5:
        tier = "fast"
    elif param_size > 14.0:
        tier = "heavy"
    else:
        tier = "smart"

    return param_size, has_vision, has_code, tier


def scan_running_servers() -> list[LocalModelInfo]:
    """Check running loopback endpoints for loaded/available models."""
    detected: list[LocalModelInfo] = []
    
    for pid, base, endpoint, api_v1 in LOCAL_ENDPOINTS:
        url = f"{base}{endpoint}"
        data = _quick_http_get(url, timeout=0.4)
        if not data:
            continue
            
        full_base = f"{base}{api_v1}"
        
        # Ollama API: /api/tags returns {"models": [{"name": "...", "size": ...}, ...]}
        if pid == "ollama" and isinstance(data, dict) and isinstance(data.get("models"), list):
            for item in data.get("models", [])[:_MAX_MODELS_PER_SCAN]:
                if not isinstance(item, dict):
                    continue
                m_name = str(item.get("name") or "").strip()[:160]
                if not m_name:
                    continue
                try:
                    m_size = max(0, int(item.get("size", 0) or 0))
                except (TypeError, ValueError):
                    m_size = 0
                p_size, is_vis, is_code, tier = _estimate_params_and_tier(m_name, m_size)
                detected.append(
                    LocalModelInfo(
                        name=m_name,
                        provider_id="ollama",
                        base_url=full_base,
                        running=True,
                        size_bytes=m_size,
                        param_size_b=p_size,
                        has_vision=is_vis,
                        has_code=is_code,
                        tier=tier,
                        location=f"Ollama server ({base})",
                    )
                )
                
        # OpenAI-compatible /v1/models returns {"data": [{"id": "...", ...}]}
        elif isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
            for item in data["data"][:_MAX_MODELS_PER_SCAN]:
                if not isinstance(item, dict):
                    continue
                m_id = str(item.get("id") or item.get("name") or "").strip()[:160]
                if not m_id:
                    continue
                p_size, is_vis, is_code, tier = _estimate_params_and_tier(m_id)
                detected.append(
                    LocalModelInfo(
                        name=m_id,
                        provider_id=pid,
                        base_url=full_base,
                        running=True,
                        size_bytes=0,
                        param_size_b=p_size,
                        has_vision=is_vis,
                        has_code=is_code,
                        tier=tier,
                        location=f"{pid.upper()} server ({base})",
                    )
                )

    return detected


def _parse_manifest_entry(manifest_file: Path, base_dir: Path) -> tuple[str, int]:
    rel = manifest_file.relative_to(base_dir)
    parts = rel.parts
    if len(parts) >= 3:
        if parts[0] == "registry.ollama.ai" and parts[1] == "library":
            model_name = f"{parts[2]}:{parts[3]}"
        else:
            model_name = f"{'/'.join(parts[1:-1])}:{parts[-1]}"
    else:
        model_name = ":".join(parts)

    data = json.loads(manifest_file.read_text(encoding="utf-8"))
    layers = data.get("layers", [])
    total_bytes = sum(
        int(l.get("size", 0))
        for l in layers
        if "model" in str(l.get("mediaType", "")).lower()
    )
    return model_name, total_bytes


def _scan_ollama_manifests(seen: set[str]) -> list[LocalModelInfo]:
    detected = []
    base_dir = Path.home() / ".ollama" / "models" / "manifests"
    if not base_dir.is_dir():
        return detected

    for path in base_dir.glob("**/*"):
        if len(detected) >= _MAX_MODELS_PER_SCAN:
            break
        if not path.is_file() or path.is_symlink():
            continue
        try:
            if not path.resolve().is_relative_to(base_dir.resolve()):
                continue
            name, size = _parse_manifest_entry(path, base_dir)
            if name in seen:
                continue
            seen.add(name)
            p_size, is_vis, is_code, tier = _estimate_params_and_tier(name, size)
            detected.append(
                LocalModelInfo(
                    name=name,
                    provider_id="ollama",
                    base_url="http://127.0.0.1:11434/v1",
                    running=False,
                    size_bytes=size,
                    param_size_b=p_size,
                    has_vision=is_vis,
                    has_code=is_code,
                    tier=tier,
                    location=str(path.parent),
                )
            )
        except Exception as exc:
            failures.note("local_detector.scan_manifest", exc)
    return detected


def _scan_gguf_folder(folder: Path, pid: str, base_url: str, seen: set[str]) -> list[LocalModelInfo]:
    detected = []
    if not folder.is_dir():
        return detected
    for f in folder.glob("**/*.gguf"):
        if len(detected) >= _MAX_MODELS_PER_SCAN:
            break
        try:
            if f.is_symlink() or not f.is_file():
                continue
            if not f.resolve().is_relative_to(folder.resolve()):
                continue
            name = f.stem[:160]
            if not name or name in seen:
                continue
            size = max(0, f.stat().st_size)
            p_size, is_vis, is_code, tier = _estimate_params_and_tier(name, size)
            seen.add(name)
            detected.append(
                LocalModelInfo(
                    name=name,
                    provider_id=pid,
                    base_url=base_url,
                    running=False,
                    size_bytes=size,
                    param_size_b=p_size,
                    has_vision=is_vis,
                    has_code=is_code,
                    tier=tier,
                    location=str(f.parent),
                )
            )
        except OSError as exc:
            failures.note("local_detector.scan_gguf", exc)
    return detected


def scan_disk_models() -> list[LocalModelInfo]:
    """Inspect local storage paths for offline downloaded models."""
    seen_names: set[str] = set()
    detected = _scan_ollama_manifests(seen_names)

    # LM Studio
    for lm_path in (
        Path.home() / ".cache" / "lm-studio" / "models",
        Path.home() / ".lmstudio" / "models",
    ):
        detected.extend(_scan_gguf_folder(lm_path, "lmstudio", "http://127.0.0.1:1234/v1", seen_names))

    # Jan
    appdata = os.getenv("APPDATA", "")
    jan_paths = [Path.home() / ".jan" / "models"]
    if appdata:
        jan_paths.append(Path(appdata) / "Jan" / "models")
    for jp in jan_paths:
        detected.extend(_scan_gguf_folder(jp, "jan", "http://127.0.0.1:1337/v1", seen_names))

    return detected


def detect_all_local_models(force_refresh: bool = False) -> list[LocalModelInfo]:
    """Detect local models, combining live loopback services and local model caches."""
    global _cached_results, _last_scan_time
    with _scan_lock:
        now = time.monotonic()
        if not force_refresh and _cached_results and (now - _last_scan_time) < _CACHE_TTL_SECONDS:
            return list(_cached_results)

        running = scan_running_servers()
        running_names = {model.name for model in running}
        disk = scan_disk_models()
        combined = list(running)
        for model in disk:
            if model.name not in running_names:
                combined.append(model)
            if len(combined) >= _MAX_MODELS_PER_SCAN:
                break

        _cached_results = combined
        _last_scan_time = time.monotonic()
        return list(_cached_results)


def clear_cache() -> None:
    """Clear cached inventory. Used by deterministic tests."""
    global _cached_results, _last_scan_time
    with _scan_lock:
        _cached_results = []
        _last_scan_time = 0.0
