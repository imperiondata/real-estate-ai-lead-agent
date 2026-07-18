"""IREIOS 3.0 — Phase 7.4: Neo4j async event writers.

Subscribes (via the CEO/registry as an active agent) to core lifecycle events
and projects them into the Neo4j graph asynchronously. Writes are best-effort:
failures log (and could DLQ) but never fail the producing agent, and the graph
being unavailable is a clean no-op (Postgres stays the source of truth).

Handled events:
    lead.created / lead.qualified / lead.scored -> upsert Lead node
    lead.assigned                                -> Lead-[:ASSIGNED_TO]->Agent
    site_visit.scheduled                         -> Lead visit props
"""
from __future__ import annotations

import logging
from typing import Optional

from app.knowledge_graph.neo4j_kg import knowledge_graph

logger = logging.getLogger("kg_writers")

GRAPH_EVENTS = [
    "lead.created",
    "lead.qualified",
    "lead.scored",
    "lead.assigned",
    "site_visit.scheduled",
]


def _resolve_client_id(tenant_id) -> Optional[int]:
    """Map ``Client_<id>`` (or bare int) tenant id to an integer client id."""
    if tenant_id is None:
        return None
    s = str(tenant_id)
    if s.startswith("Client_"):
        s = s.split("_", 1)[1]
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


def _lead_id(envelope: dict) -> Optional[int]:
    payload = envelope.get("payload") or {}
    raw = payload.get("lead_id", envelope.get("entity_id"))
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


async def graph_event_writer(envelope: dict) -> None:
    """CEO-registered handler: project a bus event into Neo4j (best-effort)."""
    if not knowledge_graph.available:
        return
    event_type = envelope.get("event_type")
    client_id = _resolve_client_id(envelope.get("tenant_id"))
    lead_id = _lead_id(envelope)
    if client_id is None or lead_id is None:
        return
    payload = envelope.get("payload") or {}
    try:
        if event_type in ("lead.created", "lead.qualified", "lead.scored"):
            props = {
                k: payload[k]
                for k in ("name", "location", "property_type", "lead_temperature",
                          "conversion_probability", "intent")
                if payload.get(k) is not None
            }
            knowledge_graph.upsert_lead(lead_id, client_id, props)
        elif event_type == "lead.assigned":
            agent_name = payload.get("assigned_agent") or payload.get("agent_name")
            knowledge_graph.upsert_lead(lead_id, client_id, {})
            if agent_name:
                knowledge_graph.link_lead_agent(lead_id, str(agent_name), client_id)
        elif event_type == "site_visit.scheduled":
            props = {
                "visit_id": payload.get("visit_id"),
                "visit_date": payload.get("visit_date"),
            }
            knowledge_graph.upsert_lead(lead_id, client_id, {k: v for k, v in props.items() if v})
    except Exception as e:  # noqa: BLE001 - writer never fails the agent
        logger.warning("graph writer failed for %s lead=%s: %s", event_type, lead_id, e)


def register_graph_writers(ceo) -> None:
    """Register the graph writer as an active CEO agent on core events."""
    ceo.register_agent(
        "kg_event_writer", graph_event_writer, subscriptions=list(GRAPH_EVENTS), status="active"
    )
    logger.info("Registered kg_event_writer on %d event types", len(GRAPH_EVENTS))
