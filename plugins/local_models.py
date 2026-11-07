"""plugins/local_models.py — Ultron tool to inspect and configure auto-detected local models.

Auto-discovers running local model servers (Ollama, LM Studio, Jan, llama.cpp, vLLM)
and offline model weights, classifies their capabilities, and maps them to intelligent tiers.
"""

from __future__ import annotations

from core import failures, local_router

PLUGIN = {
    "name": "local_models",
    "description": (
        "Auto-detects all downloaded local models on the system (Ollama, LM Studio, Jan, llama.cpp) "
        "and maps them to intelligent execution tiers. Use it when the user asks what local models "
        "are downloaded, asks to scan the system for local models, or wants to check offline AI readiness."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "'status' to inspect detected models, or 'configure' to set active local fallback.",
            },
            "tier": {
                "type": "STRING",
                "description": "Target tier for configuration: 'fast', 'smart', or 'vision'. Default 'fast'.",
            },
        },
        "required": [],
    },
    "tier": "OBSERVE",
}


def _format_summary_card(summary: dict) -> str:
    count = summary["total_detected"]
    lines = [f"### Auto-Detected Local Models ({count} found)\n"]
    for m in summary["models"]:
        status_badge = "[RUNNING]" if m["running"] else "[ON DISK]"
        vision_badge = " · Vision" if m["has_vision"] else ""
        lines.append(
            f"- **{m['name']}** ({m['provider_id'].upper()})\n"
            f"  {status_badge} · Size: {m.get('size_bytes', 0) / (1024**3):.2f} GB · Tier: `{m['tier']}`{vision_badge}\n"
        )

    lines.append("\n**Optimal Routing Assignments:**")
    fast_m = summary.get("fast_choice")
    smart_m = summary.get("smart_choice")
    vis_m = summary.get("vision_choice")
    if fast_m:
        lines.append(f"- **Fast Tier (Low latency)**: `{fast_m.name}`")
    if smart_m:
        lines.append(f"- **Smart Tier (Reasoning)**: `{smart_m.name}`")
    if vis_m:
        lines.append(f"- **Vision Tier (Multimodal)**: `{vis_m.name}`")
    return "\n".join(lines)


def _handle_configure(tier: str) -> str:
    res = local_router.auto_configure_local_provider(tier=tier)
    if not res or res.get("status") == "error":
        return f"Sir, I could not configure a local model for tier '{tier}'."
    return (
        f"Sir, I have configured {res.get('model')} on {res.get('provider_id')} "
        f"as your active local fallback."
    )


def run(parameters: dict, player=None, session_memory=None) -> str:
    action = str(parameters.get("action") or "status").strip().lower()
    tier = str(parameters.get("tier") or "fast").strip().lower()

    try:
        if action == "configure":
            return _handle_configure(tier)

        summary = local_router.get_local_summary()
        count = summary["total_detected"]
        if count == 0:
            if player:
                try:
                    player.show_content("LOCAL MODELS", "No local models found in Ollama, LM Studio, or Jan.")
                except Exception as exc:
                    failures.note("local_models.show_content", exc)
            return "Sir, no downloaded local models were detected on the system."

        card_text = _format_summary_card(summary)
        if player:
            try:
                player.show_content("LOCAL MODELS", card_text)
            except Exception as exc:
                failures.note("local_models.show_content", exc)

        fast_m = summary.get("fast_choice")
        smart_m = summary.get("smart_choice")
        fast_name = fast_m.name if fast_m else "none"
        smart_name = smart_m.name if smart_m else "none"
        return (
            f"Sir, I detected {count} local models. I will use {fast_name} for rapid responses, "
            f"and {smart_name} for complex reasoning."
        )

    except Exception as exc:
        failures.note("local_models.run", exc)
        return f"Sir, local model inspection encountered an error: {exc}"
