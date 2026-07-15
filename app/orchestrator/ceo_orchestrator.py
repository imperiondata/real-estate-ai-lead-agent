"""IREIOS 3.0 — CEO Orchestrator.

Routes events from the Event Bus to registered agents. The CEO is the
single bus subscriber (wildcard ``"*"``); on each event it fans out to the
agents in ``agent_registry`` that subscribed to that event type. Placeholder
agents are listed by the registry but deliberately NOT invoked. A failing
active agent is recorded as unhealthy and a ``{agent_id}.failed`` event is
published (never crashing the bus).

Runtime: ``Event -> CEO -> Agent/Workflow -> Automation Engine -> Execution Engine -> Event``.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Optional

from app.clients.event_bus_client import EventBusClient, event_bus
from app.orchestrator.agent_registry import AgentRegistry, AgentRecord, agent_registry

logger = logging.getLogger("ceo")

Handler = Callable[[dict], Any]


class CEOOrchestrator:
    """Routes bus events to registered agents."""

    def __init__(self, registry: Optional[AgentRegistry] = None, bus: Optional[EventBusClient] = None):
        self.registry = registry or agent_registry
        self.bus: Optional[EventBusClient] = bus
        self._subscribed = False

    # ------------------------------------------------------------------ #
    # Registration (wraps the registry)
    # ------------------------------------------------------------------ #
    def register_agent(
        self,
        agent_id: str,
        handler: Handler,
        subscriptions: Optional[list[str]] = None,
        status: str = "active",
    ) -> AgentRecord:
        return self.registry.register(agent_id, handler, subscriptions, status)

    # ------------------------------------------------------------------ #
    # Bus wiring
    # ------------------------------------------------------------------ #
    def bootstrap(self) -> None:
        """Subscribe the CEO as the single wildcard handler on the bus.

        Idempotent. Using ``"*"`` (rather than per-type) keeps routing
        correct for agents registered after bootstrap and for new event
        types, at the cost of the CEO receiving every event (it no-ops when
        no agent subscribes).
        """
        bus = self.bus or event_bus
        if self._subscribed:
            return
        bus.subscribe("*", self._dispatch)
        self._subscribed = True

    # ------------------------------------------------------------------ #
    # Dispatch
    # ------------------------------------------------------------------ #
    async def _dispatch(self, envelope: dict) -> None:
        """Bus handler entry point."""
        await self.handle_event(envelope)

    async def handle_event(self, event: dict) -> None:
        """Resolve subscribers for ``event["event_type"]`` and invoke them.

        - active agents are invoked (and health-recorded)
        - placeholder agents are skipped
        - a failing active agent records failure and emits ``{agent_id}.failed``
        """
        event_type = event.get("event_type")
        subscribers = self.registry.get_subscribers(event_type)
        for rec in subscribers:
            if rec.status != "active":
                # Declared but not yet implemented — listed, not invoked.
                continue
            try:
                await self._safe_call(rec.handler, event)
                self.registry.record_success(rec.agent_id)
            except Exception as exc:  # noqa: BLE001 - isolate per agent
                self.registry.record_failure(rec.agent_id, exc)
                logger.error("agent %s failed on %s: %s", rec.agent_id, event_type, exc)
                if self.bus is not None:
                    try:
                        await self.bus.publish(
                            f"{rec.agent_id}.failed",
                            event.get("tenant_id", "system"),
                            event.get("entity_id", rec.agent_id),
                            {
                                "agent_id": rec.agent_id,
                                "event_type": event_type,
                                "error": str(exc),
                            },
                            source="ceo",
                        )
                    except Exception as pub_exc:  # noqa: BLE001 - never crash bus
                        logger.error("failed to publish %s.failed: %s", rec.agent_id, pub_exc)

    @staticmethod
    async def _safe_call(handler: Handler, event: dict):
        if asyncio.iscoroutinefunction(handler):
            return await handler(event)
        return handler(event)


# Module-level singleton (wired into the bus at bootstrap / Task 1.7 lifespan).
ceo = CEOOrchestrator()
