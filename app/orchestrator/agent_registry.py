"""IREIOS 3.0 — Agent registry.

In-memory registry of agents/handlers that the CEO orchestrator (Task 1.4)
dispatches events to. Pure Python (single-process, asyncio is
single-threaded) so a plain dict is safe — no locks required.

A record may be ``active`` (invoked by the CEO) or ``placeholder`` (declared
but not yet implemented; still listed so the CEO can skip it deliberately
and G2 evidence can enumerate the full agent roster).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

Handler = Callable[[dict], object]

VALID_STATUSES = ("active", "placeholder")


@dataclass
class AgentRecord:
    agent_id: str
    handler: Handler
    subscriptions: list[str] = field(default_factory=list)
    status: str = "active"
    last_error: Optional[str] = None
    last_seen: Optional[datetime] = None

    def __post_init__(self) -> None:
        if self.status not in VALID_STATUSES:
            raise ValueError(f"agent status must be one of {VALID_STATUSES}, got {self.status!r}")


class AgentRegistry:
    """Registry of agents keyed by ``agent_id``."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentRecord] = {}

    # ------------------------------------------------------------------ #
    # Registration
    # ------------------------------------------------------------------ #
    def register(
        self,
        agent_id: str,
        handler: Handler,
        subscriptions: Optional[list[str]] = None,
        status: str = "active",
    ) -> AgentRecord:
        """Upsert an agent record.

        ``subscriptions`` is a list of event types (may include ``"*"``).
        ``status`` must be ``"active"`` or ``"placeholder"``.
        """
        record = AgentRecord(
            agent_id=agent_id,
            handler=handler,
            subscriptions=list(subscriptions or []),
            status=status,
        )
        self._agents[agent_id] = record
        return record

    def unregister(self, agent_id: str) -> None:
        """Remove an agent. No-op if it is not registered."""
        self._agents.pop(agent_id, None)

    # ------------------------------------------------------------------ #
    # Lookup
    # ------------------------------------------------------------------ #
    def get_subscribers(self, event_type: str) -> list[AgentRecord]:
        """Return all agents subscribed to ``event_type`` (active AND placeholder).

        An agent subscribed to ``"*"`` matches every event type. Order is
        stable (sorted by ``agent_id``) so dispatch is deterministic. The
        CEO (Task 1.4) is responsible for skipping ``placeholder`` records.
        """
        return [
            rec
            for rec in sorted(self._agents.values(), key=lambda r: r.agent_id)
            if event_type in rec.subscriptions or "*" in rec.subscriptions
        ]

    def list_agents(self) -> list[AgentRecord]:
        """Return all registered agents (for inspection / G2 evidence)."""
        return list(sorted(self._agents.values(), key=lambda r: r.agent_id))

    # ------------------------------------------------------------------ #
    # Health tracking
    # ------------------------------------------------------------------ #
    def record_success(self, agent_id: str) -> None:
        rec = self._agents.get(agent_id)
        if rec is None:
            return
        rec.last_seen = datetime.now(timezone.utc)
        rec.last_error = None

    def record_failure(self, agent_id: str, error: object) -> None:
        rec = self._agents.get(agent_id)
        if rec is None:
            return
        rec.last_seen = datetime.now(timezone.utc)
        rec.last_error = str(error)


# Module-level singleton consumed by the CEO orchestrator (Task 1.4).
agent_registry = AgentRegistry()
