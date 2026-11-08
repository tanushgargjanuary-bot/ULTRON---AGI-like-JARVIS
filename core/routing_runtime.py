"""Runtime adapter from the pure routing table to configured LLM clients."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.routing import (
    Provider, Purpose, Refusal, Route, RoutingTable, apply_switch, parse_switch,
)


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
        route, client = self.select(Purpose.CONVERSATION)
        self.table.record_use(route)
        async for event in client.chat(messages, tools, **kwargs):
            yield event

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
        from providers import registry
        block = get_providers()
        provider_id = configured_slot_id(purpose, block)
        if not provider_id:
            return ""
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
