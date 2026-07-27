"""IREIOS 3.0 — Base Agent lifecycle (Phase 1).

Defines the abstract agent lifecycle used by every concrete agent
(WhatsApp, Sales, Marketing, CS, ...) from Phase 5+:

    fetch_context(event) -> context
    analyze(context)      -> analysis
    decide(analysis)      -> action_request | None

``process_event`` runs the lifecycle, isolates failures (publishing
``{agent_id}.failed`` without crashing the caller), and — in Phase 1 — forwards
any produced ``action_request`` to the Automation Engine stub
(``app.automation_engine.engine.submit``), which today just dispatches to the
Execution Engine. Phase 2 fills ``submit`` with approval gating + retries;
``BaseAgent`` itself does not change.

Runtime: ``Event -> CEO -> Agent/Workflow -> Automation Engine -> Execution Engine -> Event``.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from app.clients.event_bus_client import event_bus

logger = logging.getLogger("base_agent")


class BaseAgent:
    """Abstract agent. Subclasses set ``agent_id`` / ``subscriptions`` and
    implement the three lifecycle hooks."""

    agent_id: str = "base"
    subscriptions: list[str] = []

    def __init__(self, agent_id: Optional[str] = None, bus: Any = None):
        self.agent_id = agent_id or self.agent_id
        self.bus = bus if bus is not None else event_bus

    # ------------------------------------------------------------------ #
    # Lifecycle hooks (abstract)
    # ------------------------------------------------------------------ #
    async def fetch_context(self, event: dict) -> Any:
        raise NotImplementedError

    async def analyze(self, context: Any) -> Any:
        raise NotImplementedError

    async def decide(self, analysis: Any) -> Optional[dict]:
        """Return an ``action_request`` dict, or ``None`` to take no action."""
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # Orchestration
    # ------------------------------------------------------------------ #
    async def process_event(self, event: dict) -> dict:
        """Run the lifecycle and forward any action to the Automation Engine.

        Failures are isolated: a failing hook logs, publishes
        ``{agent_id}.failed`` (best-effort, never crashes the caller), and
        returns an error dict. A ``None`` decision is a no-op.
        """
        try:
            context = await self.fetch_context(event)
            analysis = await self.analyze(context)
            action_request = await self.decide(analysis)
        except Exception as exc:  # noqa: BLE001 - isolate per agent
            logger.error("agent %s lifecycle failed: %s", self.agent_id, exc)
            await self._publish_failed(event, exc)
            return {"status": "error", "agent_id": self.agent_id, "error": str(exc)}

        if action_request is None:
            return {"status": "noop", "agent_id": self.agent_id}

        # Phase 1 temporary path: AutomationEngine stub forwards to EE.
        # Phase 2 replaces the stub body with approval/retry without touching
        # this agent code.
        from app.automation_engine.engine import submit

        return await submit(action_request)

    async def _publish_failed(self, event: dict, exc: Exception) -> None:
        if self.bus is None:
            return
        try:
            await self.bus.publish(
                f"{self.agent_id}.failed",
                event.get("tenant_id", "system"),
                event.get("entity_id", self.agent_id),
                {
                    "agent_id": self.agent_id,
                    "event_type": event.get("event_type"),
                    "error": str(exc),
                },
                source="agent",
            )
        except Exception as pub_exc:  # noqa: BLE001 - never crash the agent
            logger.error("failed to publish %s.failed: %s", self.agent_id, pub_exc)
