"""Read-only inventory of local inference servers and cached models."""

from __future__ import annotations

import re

from core import failures
from core.local_detector import LocalModelInfo, detect_all_local_models

PLUGIN = {
    "name": "local_models",
    "description": (
        "Lists local AI models found in Ollama, LM Studio, Jan, llama.cpp, "
        "vLLM, LocalAI, and known on-disk model folders. This tool is read-only. "
        "It does not download models, start servers, change settings, or select a model."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Use 'status' to inspect locally available models.",
                "enum": ["status"],
            },
        },
        "required": ["action"],
    },
    "tier": "OBSERVE",
}


def _safe_label(value: object, limit: int = 100) -> str:
    """Keep model-provided labels on one line and bounded in tool output."""
    clean = re.sub(r"[\x00-\x1f\x7f]", " ", str(value or ""))
    return " ".join(clean.split())[:limit]


def _render(models: list[LocalModelInfo]) -> str:
    lines = [f"Local model inventory: {len(models)} model(s) found."]
    for model in models[:40]:
        name = _safe_label(model.name)
        provider = _safe_label(model.provider_id, 24).upper()
        state = "RUNNING" if model.running else "ON DISK"
        size = f"{model.param_size_b:g}B" if model.param_size_b else "size unknown"
        capabilities = []
        if model.has_vision:
            capabilities.append("vision")
        if model.has_code:
            capabilities.append("code")
        suffix = f" · {', '.join(capabilities)}" if capabilities else ""
        lines.append(f"- {name} [{provider}] — {state}, {size}, tier={model.tier}{suffix}")
    if len(models) > 40:
        lines.append(f"... {len(models) - 40} additional model(s) omitted.")
    return "\n".join(lines)


def run(parameters: dict, player=None, session_memory=None) -> str:
    """Return model inventory only; configuration and activation are not supported."""
    action = str((parameters or {}).get("action") or "status").strip().lower()
    if action != "status":
        return "This plugin supports read-only status only. It cannot configure or activate models."
    try:
        models = detect_all_local_models(force_refresh=True)
        result = _render(models) if models else (
            "No local models were found in the supported inference servers or model folders."
        )
        if player is not None:
            try:
                player.show_content("LOCAL MODEL INVENTORY", result)
            except Exception as exc:
                failures.note("local_models.show_content", exc)
        return result
    except Exception as exc:
        failures.note("local_models.run", exc)
        return f"Local model inventory failed: {type(exc).__name__}: {exc}"
