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

import json
import os
import re
import socket
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

# Known loopback endpoints and their default ports
LOCAL_ENDPOINTS = (
    ("ollama", "http://127.0.0.1:11434", "/api/tags", "/v1"),
    ("lmstudio", "http://127.0.0.1:1234", "/v1/models", "/v1"),
    ("jan", "http://127.0.0.1:1337", "/v1/models", "/v1"),
    ("llamacpp", "http://127.0.0.1:8080", "/v1/models", "/v1"),
    ("vllm", "http://127.0.0.1:8000", "/v1/models", "/v1"),
    ("localai", "http://127.0.0.1:8088", "/v1/models", "/v1"),
)

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
    """Perform a fast HTTP GET against a loopback service."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Ultron-ModelDetector/1.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                body = resp.read().decode("utf-8", errors="replace")
                return json.loads(body)
    except Exception:
        pass
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
        if pid == "ollama" and isinstance(data, dict) and "models" in data:
            for item in data.get("models", []):
                m_name = item.get("name", "")
                if not m_name:
                    continue
                m_size = int(item.get("size", 0))
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
            for item in data["data"]:
                m_id = item.get("id") or item.get("name")
                if not m_id:
                    continue
                p_size, is_vis, is_code, tier = _estimate_params_and_tier(str(m_id))
                detected.append(
                    LocalModelInfo(
                        name=str(m_id),
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


def scan_disk_models() -> list[LocalModelInfo]:
    """Inspect local storage paths for offline downloaded models."""
    detected: list[LocalModelInfo] = []
    seen_names: set[str] = set()

    # 1. Ollama manifests (~/.ollama/models/manifests)
    ollama_manifests = Path.home() / ".ollama" / "models" / "manifests"
    if ollama_manifests.is_dir():
        for manifest_file in ollama_manifests.glob("**/*"):
            if manifest_file.is_file():
                try:
                    rel = manifest_file.relative_to(ollama_manifests)
                    parts = rel.parts
                    if len(parts) >= 3:
                        # e.g. registry.ollama.ai/library/qwen3/4b -> qwen3:4b
                        # or hf.co/LiquidAI/LFM3-Omni-2B-GGUF/latest
                        if parts[0] == "registry.ollama.ai" and parts[1] == "library":
                            model_name = f"{parts[2]}:{parts[3]}"
                        else:
                            model_name = f"{'/'.join(parts[1:-1])}:{parts[-1]}"
                    else:
                        model_name = ":".join(parts)

                    if model_name in seen_names:
                        continue
                    seen_names.add(model_name)

                    # Read manifest for exact layer size
                    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
                    layers = manifest_data.get("layers", [])
                    total_bytes = sum(
                        int(l.get("size", 0))
                        for l in layers
                        if "model" in str(l.get("mediaType", "")).lower()
                    )

                    p_size, is_vis, is_code, tier = _estimate_params_and_tier(model_name, total_bytes)
                    detected.append(
                        LocalModelInfo(
                            name=model_name,
                            provider_id="ollama",
                            base_url="http://127.0.0.1:11434/v1",
                            running=False,
                            size_bytes=total_bytes,
                            param_size_b=p_size,
                            has_vision=is_vis,
                            has_code=is_code,
                            tier=tier,
                            location=str(manifest_file.parent),
                        )
                    )
                except Exception:
                    continue

    # 2. LM Studio downloaded models (~/.cache/lm-studio/models or ~/.lmstudio/models)
    for lm_path in (
        Path.home() / ".cache" / "lm-studio" / "models",
        Path.home() / ".lmstudio" / "models",
    ):
        if lm_path.is_dir():
            for f in lm_path.glob("**/*.gguf"):
                name = f.stem
                if name in seen_names:
                    continue
                seen_names.add(name)
                size = f.stat().st_size
                p_size, is_vis, is_code, tier = _estimate_params_and_tier(name, size)
                detected.append(
                    LocalModelInfo(
                        name=name,
                        provider_id="lmstudio",
                        base_url="http://127.0.0.1:1234/v1",
                        running=False,
                        size_bytes=size,
                        param_size_b=p_size,
                        has_vision=is_vis,
                        has_code=is_code,
                        tier=tier,
                        location=str(f.parent),
                    )
                )

    # 3. Jan models (%APPDATA%/Jan/models or ~/.jan/models)
    appdata = os.getenv("APPDATA", "")
    jan_paths = [Path.home() / ".jan" / "models"]
    if appdata:
        jan_paths.append(Path(appdata) / "Jan" / "models")
        
    for jp in jan_paths:
        if jp.is_dir():
            for f in jp.glob("**/*.gguf"):
                name = f.stem
                if name in seen_names:
                    continue
                seen_names.add(name)
                size = f.stat().st_size
                p_size, is_vis, is_code, tier = _estimate_params_and_tier(name, size)
                detected.append(
                    LocalModelInfo(
                        name=name,
                        provider_id="jan",
                        base_url="http://127.0.0.1:1337/v1",
                        running=False,
                        size_bytes=size,
                        param_size_b=p_size,
                        has_vision=is_vis,
                        has_code=is_code,
                        tier=tier,
                        location=str(f.parent),
                    )
                )

    return detected


def detect_all_local_models(force_refresh: bool = False) -> list[LocalModelInfo]:
    """Detect all local models, combining running servers and on-disk installations."""
    global _cached_results, _last_scan_time
    now = time.monotonic()
    
    if not force_refresh and _cached_results and (now - _last_scan_time) < _CACHE_TTL_SECONDS:
        return _cached_results

    running = scan_running_servers()
    running_names = {m.name for m in running}

    disk = scan_disk_models()
    # Mark disk models as running if detected by the live server
    combined: list[LocalModelInfo] = []
    for r in running:
        combined.append(r)

    for d in disk:
        if d.name not in running_names:
            combined.append(d)

    _cached_results = combined
    _last_scan_time = now
    return combined
