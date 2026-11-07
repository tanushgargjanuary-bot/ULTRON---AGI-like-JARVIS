"""core/intent_router.py — Routes requests to models and providers by intent.

Works beside core/routing.py to choose the appropriate model tier and provider
for conversation, evolution/coding, and adversarial review.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Callable, Optional

from core import failures
from core.routing import Provider, Purpose, Route, RoutingTable

_CRITIC_TRIGGERS = (
    "review", "critique", "critic", "audit", "verify", "inspect", "judge",
    "security check", "adversarial", "double check",
)

_EVOLUTION_TRIGGERS = (
    "code", "build", "refactor", "implement", "debug", "repair", "script",
    "develop", "fix bug", "unit test", "write function", "modify",
)

_VERIFY_DIR = Path("verification")
_VERIFY_FILE = _VERIFY_DIR / "routing.log"


def classify_intent(prompt: str) -> Purpose:
    """Classify prompt text into Purpose.CRITIC, Purpose.EVOLUTION, or Purpose.CONVERSATION."""
    text = str(prompt or "").lower().strip()
    words = set(re.findall(r"\b\w+\b", text))

    for trig in _CRITIC_TRIGGERS:
        if " " in trig and trig in text:
            return Purpose.CRITIC
        if trig in words:
            return Purpose.CRITIC

    for trig in _EVOLUTION_TRIGGERS:
        if " " in trig and trig in text:
            return Purpose.EVOLUTION
        if trig in words:
            return Purpose.EVOLUTION

    return Purpose.CONVERSATION


def default_routing_table() -> RoutingTable:
    """Construct a default routing table for active providers."""
    table = RoutingTable()
    table.add_provider(Provider("Google AI Studio", quota_group="google"))
    table.add_provider(Provider("Groq", quota_group="groq"))
    table.add_provider(Provider("Ollama", quota_group="ollama", local=True))

    table.set_route(Purpose.CONVERSATION, "Google AI Studio", "gemini-2.5-flash-lite")
    table.set_route(Purpose.EVOLUTION, "Google AI Studio", "gemini-2.5-flash")
    table.set_route(Purpose.CRITIC, "Google AI Studio", "gemini-2.5-flash")
    return table


def _record_verification_log(purpose: Purpose, route: Route) -> None:
    """Log the routed decision to verification/routing.log."""
    try:
        _VERIFY_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        line = f"{timestamp} [{purpose.value.upper()}] -> {route.describe()}\n"
        with open(_VERIFY_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as exc:
        failures.note("intent_router.log", exc)


def route_request(
    prompt: str,
    table: Optional[RoutingTable] = None,
    logger: Optional[Callable[[str], None]] = None,
) -> Route:
    """Route a request prompt to the most suitable provider and model route.

    Selects Purpose, resolves candidate Route, logs the decision to logger
    and verification/routing.log, and returns the Route.
    """
    tbl = table or default_routing_table()
    purpose = classify_intent(prompt)
    route = tbl.choose(purpose)

    msg = f"[Router] {purpose.value.capitalize()} request routed to {route.describe()}"
    if logger is not None:
        logger(msg)
    _record_verification_log(purpose, route)
    return route

