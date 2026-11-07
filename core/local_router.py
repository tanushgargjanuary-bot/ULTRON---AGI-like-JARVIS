"""core/local_router.py — Intelligent tier-based router and configuration for local models.

WHY THIS EXISTS
    Auto-detecting models is only half the job: using them "wisely" requires
    matching the user's intent and task requirements to the right model:
      - Quick classification, routing, and low-latency voice turns -> Fast tier (1B-3B)
      - Coding, structured data, and multi-step reasoning -> Smart tier (4B-14B)
      - Complex deep analysis -> Heavy tier (> 14B)
      - Screenshots, camera images, visual questions -> Vision tier (Multimodal)

INVARIANTS
    - Adheres to DECISIONS.md: No hardcoded model names. Selections are derived dynamically
      from detected capabilities and parameter metrics.
    - Safe fallback: If no local model is running or installed, gracefully returns None
      instead of failing.
    - Zero direct writes to config/api_keys.json: uses memory.config_manager.
"""

from __future__ import annotations

from typing import Optional

from core.local_detector import LocalModelInfo, detect_all_local_models


def choose_wise_local_model(
    tier: str = "fast",
    need_vision: bool = False,
    need_code: bool = False,
    running_only: bool = False,
) -> Optional[LocalModelInfo]:
    """Select the optimal local model based on capability and resource efficiency.

    Args:
        tier: Desired capability tier ('fast', 'smart', 'heavy', 'vision').
        need_vision: If True, model must support multimodal/image input.
        need_code: If True, prioritize models specialized in code generation.
        running_only: If True, restrict choice to actively running servers.

    Returns:
        The best matching LocalModelInfo, or None if no suitable model is detected.
    """
    models = detect_all_local_models()
    if not models:
        return None

    candidates = [m for m in models if (not running_only or m.running)]
    if not candidates and running_only:
        # Fall back to any detected candidate if none running
        candidates = models

    # 1. Vision requirement filter
    if need_vision:
        vision_candidates = [m for m in candidates if m.has_vision]
        if vision_candidates:
            # Prefer smallest vision model for speed, or running one
            vision_candidates.sort(key=lambda m: (not m.running, m.param_size_b or 999.0))
            return vision_candidates[0]

    # 2. Code requirement filter
    if need_code:
        code_candidates = [m for m in candidates if m.has_code]
        if code_candidates:
            code_candidates.sort(key=lambda m: (not m.running, -(m.param_size_b or 0.0)))
            return code_candidates[0]

    # 3. Tier matching
    target_tier = tier.lower()
    tier_matches = [m for m in candidates if m.tier == target_tier]

    if tier_matches:
        # For 'fast', choose smallest parameter size (lowest latency)
        if target_tier == "fast":
            tier_matches.sort(key=lambda m: (not m.running, m.param_size_b or 999.0))
        # For 'smart' or 'heavy', choose highest parameter size within tier
        else:
            tier_matches.sort(key=lambda m: (not m.running, -(m.param_size_b or 0.0)))
        return tier_matches[0]

    # 4. Graceful fallback ladder if exact tier match isn't available
    if target_tier == "fast":
        # If no fast model, pick the smallest available model
        candidates.sort(key=lambda m: (not m.running, m.param_size_b or 999.0))
        return candidates[0]
    else:
        # If smart/heavy requested, pick the largest available model
        candidates.sort(key=lambda m: (not m.running, -(m.param_size_b or 0.0)))
        return candidates[0]


def get_local_summary() -> dict:
    """Return a clean summary of all local models and wise tier recommendations."""
    models = detect_all_local_models(force_refresh=True)
    summary = {
        "total_detected": len(models),
        "running_servers": list({m.provider_id for m in models if m.running}),
        "fast_choice": choose_wise_local_model("fast"),
        "smart_choice": choose_wise_local_model("smart"),
        "vision_choice": choose_wise_local_model(need_vision=True),
        "models": [m.to_dict() for m in models],
    }
    return summary


def auto_configure_local_provider(tier: str = "fast", prefer_running: bool = True) -> Optional[dict]:
    """Auto-configure Ultron's provider settings to use the wisest detected local model.

    Persists the choice via memory.config_manager so the fallback ladder works seamlessly.
    """
    chosen = choose_wise_local_model(tier=tier, running_only=prefer_running)
    if not chosen:
        return None

    try:
        from memory import config_manager

        provider_id = f"openai_compat@{chosen.provider_id}"
        values = {
            "base_url": chosen.base_url,
            "model": chosen.name,
            "local": True,
            "max_tools": "14",
            "max_tool_chars": "12000",
        }
        if chosen.has_vision:
            values["vision"] = "1"
            values["vision_model"] = chosen.name

        config_manager.save_provider_config(provider_id, values)
        config_manager.save_sidecar_provider(provider_id)

        return {
            "status": "configured",
            "provider_id": provider_id,
            "model": chosen.name,
            "tier": chosen.tier,
            "base_url": chosen.base_url,
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
