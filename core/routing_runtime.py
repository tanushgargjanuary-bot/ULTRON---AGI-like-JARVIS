"""Runtime adapter from the pure routing table to configured LLM clients.

`RoutedLLM.chat` is the conversation's request path. It walks the table's
candidate routes and fails over the way the one-shot ladder in `core/gemini.py`
does: rest what failed before it answered, skip what is out of quota, and
never switch once words were spoken.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from core.routing import (
    Provider, Purpose, Refusal, Route, RoutingTable, apply_switch, parse_switch,
)

# How long a failed route's whole quota group rests, by failure kind. These are
# the same rests core/gemini.py measured for the one-shot ladder — same kinds
# of failure, same accounts, so one policy covers both request paths.
_QUOTA_REST_S = 300.0          # 429 — out of quota for minutes, not seconds
_GONE_REST_S = 6 * 3600.0      # 404/403 — not coming back today
_UNAVAILABLE_REST_S = 1800.0   # 503/504/timeout — usually passes


def _fail_kind(message: str) -> str:
    """Classify a client failure, reusing the one-shot ladder's classifiers."""
    from core.gemini import is_gone_error, is_quota_error, is_unavailable_error

    if is_quota_error(message):
        return "quota"
    if is_gone_error(message):
        return "gone"
    if is_unavailable_error(message):
        return "unavailable"
    return ""


class RoutedLLM:
    """Pipeline-compatible LLM proxy with explicit route selection and logging."""

    def __init__(self, table: RoutingTable, clients: dict[str, Any],
                 provider_ids: dict[str, str], *, log: Callable[[str], None] | None = None,
                 persist: Callable[[str], None] | None = None) -> None:
        self.table = table
        self._clients = {str(key).lower(): value for key, value in clients.items()}
        self._provider_ids = {str(key).lower(): str(value)
                              for key, value in provider_ids.items()}
        self._log = log or (lambda _message: None)
        self._persist = persist or (lambda _provider_id: None)
        self._caps = self._shared_caps()

    def _shared_caps(self) -> dict:
        """Expose only capabilities shared by every selectable model."""
        caps = [getattr(client, "caps", {}) or {} for client in self._clients.values()]
        if not caps:
            return {}
        def minimum(key):
            vals = [value.get(key) for value in caps if value.get(key) is not None]
            return min(vals) if vals else None
        return {
            "tools": all(bool(value.get("tools")) for value in caps),
            "tool_format": "openai",
            "max_tools": minimum("max_tools"),
            "max_tool_chars": minimum("max_tool_chars"),
            "vision": all(bool(value.get("vision")) for value in caps),
        }

    @property
    def caps(self) -> dict:
        return dict(self._caps)

    def select(self, purpose: Purpose | str = Purpose.CONVERSATION):
        route = self.table.choose(purpose)
        client = self._clients.get(route.provider.lower())
        if client is None:
            raise Refusal(f"{route.provider} has no active client")
        message = f"ROUTE: purpose={Purpose(purpose).value} model={route.describe()}"
        self._log(message)
        print(f"[Routing] {message}")
        return route, client

    @property
    def model(self) -> str:
        try:
            route = self.table.route_for(Purpose.CONVERSATION)
            return route.describe() if route else "unrouted"
        except Exception:
            return "unrouted"

    @property
    def base(self) -> str:
        try:
            route = self.table.route_for(Purpose.CONVERSATION)
            client = self._clients.get(route.provider.lower()) if route else None
            return str(getattr(client, "base", ""))
        except Exception:
            return ""

    async def chat(self, messages: list[dict], tools: list[dict] | None = None,
                   **kwargs):
        """Stream the conversation, walking the route ladder until one answers.

        The route order is the routing table's own: the conversation route
        first, then the fallbacks the quota and consent rules allow right now.
        A route that fails BEFORE it produced anything is rested and passed
        over, so an outage or an empty quota costs one round trip, not the
        feature. A route that fails AFTER it produced something is raised, not
        retried — the words already spoken would be spoken twice, or
        contradicted by a different model, and a failed turn is smaller than
        either.
        """
        purpose = Purpose.CONVERSATION
        candidates = self.table.candidates(purpose)
        if not candidates:
            # Raises Refusal with the routing table's own explanation, so the
            # caller reads one reason for why nothing is available.
            self.table.choose(purpose)

        last_error: Exception | None = None
        for route in candidates:
            client = self._clients.get(route.provider.lower())
            if client is None:
                self._note(f"{route.provider} is configured but has no active "
                           "client — skipped")
                continue
            produced = 0
            try:
                async for event in client.chat(messages, tools, **kwargs):
                    if produced == 0:
                        self.table.record_use(route)
                        self._announce(route)
                    produced += 1
                    yield event
            except asyncio.CancelledError:
                raise
            except Exception as error:                     # noqa: BLE001
                if produced:
                    self._note(f"{route.provider} dropped mid-answer — not "
                               "switching, or the reply would repeat or "
                               "contradict itself")
                    raise
                last_error = error
                self._rest(route, error)
                continue
            if produced == 0:
                # A clean stream that answered nothing still spent a request,
                # and the ROUTE line still belongs in the log.
                self.table.record_use(route)
                self._announce(route)
            return

        if last_error is not None:
            raise last_error
        raise Refusal("no configured provider has an active client — "
                      "check ENGINE & PROVIDERS")

    def _announce(self, route: Route) -> None:
        message = f"ROUTE: purpose=conversation model={route.describe()}"
        self._log(message)
        print(f"[Routing] {message}")

    def _note(self, message: str) -> None:
        self._log(f"ROUTE: {message}")
        print(f"[Routing] {message}")

    def _rest(self, route: Route, error: Exception) -> None:
        """Rest a route that failed before it produced anything.

        The whole quota group rests, not just this route: limits are per
        account, so a second route on the same account would only buy another
        429. The rests are the one-shot ladder's, for the same reasons.
        """
        kind = _fail_kind(str(error))
        if kind == "quota":
            self.table.record_limit(route, _QUOTA_REST_S)
            self._note(f"{route.describe()} is out of quota — resting it for "
                       f"{_QUOTA_REST_S / 60:.0f} minutes")
        elif kind == "gone":
            self.table.record_limit(route, _GONE_REST_S)
            self._note(f"{route.describe()} is unavailable to this setup — "
                       "resting it for the session")
        elif kind == "unavailable":
            self.table.record_limit(route, _UNAVAILABLE_REST_S)
            self._note(f"{route.describe()} is not answering — resting it for "
                       f"{_UNAVAILABLE_REST_S / 60:.0f} minutes")
        else:
            self._note(f"{route.describe()} failed ({type(error).__name__}: "
                       f"{str(error)[:140]})")

    def handle_switch(self, text: str) -> str | None:
        """Apply a locally parsed conversation-route command, or return None.

        It does not ask a model to interpret the control instruction. Unknown
        providers and providers without configured clients fail closed.
        """
        providers = list(self.table.providers.values())
        models = [str(getattr(client, "model", "")) for client in self._clients.values()]
        request = parse_switch(text, providers, models)
        if request is None:
            return None
        if request.purpose not in (None, Purpose.CONVERSATION):
            return None
        if request.local_only:
            local_options = [provider for provider in self.table.providers.values()
                             if provider.local and provider.key in self._clients]
            if len(local_options) != 1:
                if not local_options:
                    return "I could not switch to a local model because none is configured."
                names = ", ".join(provider.name for provider in local_options)
                return f"Several local models are configured: {names}. Name the one to use."
        try:
            applied = apply_switch(self.table, request, purposes=(Purpose.CONVERSATION,))
            route = applied[0][1]
            provider_key = route.provider.lower()
            if provider_key not in self._clients:
                raise Refusal(f"{route.provider} is configured but has no active client")
            if not route.model:
                route = self.table.set_route(
                    Purpose.CONVERSATION, route.provider,
                    str(getattr(self._clients[provider_key], "model", "") or ""),
                )
            provider_id = self._provider_ids.get(provider_key)
            if not provider_id:
                raise Refusal(f"{route.provider} cannot be persisted as an engine route")
            self._persist(provider_id)
            message = f"ROUTE: switched purpose=conversation model={route.describe()}"
            self._log(message)
            print(f"[Routing] {message}")
            return f"Conversation model switched to {route.describe()}."
        except Refusal as error:
            return f"I could not switch the conversation model: {error}."


def provider_for_id(table: RoutingTable, provider_ids: dict[str, str], provider_id: str) -> Provider | None:
    """Find the router provider whose configured ID matches a settings slot."""
    target = str(provider_id or "").strip()
    for name, configured in provider_ids.items():
        if str(configured) == target:
            return table.provider(name)
    return None


def configured_slot_id(purpose: Purpose | str, providers_block: dict) -> str:
    """Map a routing purpose to the configured engine slot, without guessing."""
    purpose = Purpose(purpose)
    block = providers_block if isinstance(providers_block, dict) else {}
    if purpose is Purpose.CONVERSATION:
        pipeline = block.get("pipeline")
        return str((pipeline or {}).get("llm") or "").strip() if isinstance(pipeline, dict) else ""
    if purpose is Purpose.EVOLUTION:
        return str(block.get("coding") or "").strip()
    return str(block.get("sidecar") or "").strip()


def configured_provider_id(purpose: Purpose | str) -> str:
    """Resolve and report the provider selected for a configured request purpose."""
    try:
        from memory.config_manager import get_providers, get_provider_config
        block = get_providers()
        provider_id = configured_slot_id(purpose, block)
        if not provider_id:
            return ""
        # Keep the Gemini-only default path independent of optional providers.
        # Import the registry only after a provider is explicitly configured.
        from providers import registry
        config = get_provider_config(provider_id)
        model = str(config.get("model") or "").strip()
        catalog = registry.catalog_entry(provider_id)
        label = str(catalog.get("label") or provider_id)
        message = f"ROUTE: purpose={Purpose(purpose).value} model={label}/{model or 'configured default'}"
        print(f"[Routing] {message}")
        return provider_id
    except Exception as error:
        print(f"[Routing] purpose={Purpose(purpose).value} unavailable ({type(error).__name__})")
        return ""
