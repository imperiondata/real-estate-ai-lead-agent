"""IREIOS 3.0 — Phase 7.4: Neo4j async event writers.

Subscribes (via the CEO/registry as an active agent) to core lifecycle events
and projects them into the Neo4j graph asynchronously. Writes are best-effort:
failures log (and could DLQ) but never fail the producing agent, and the graph
being unavailable is a clean no-op (Postgres stays the source of truth).

Handled events:
    lead.created / lead.qualified / lead.scored / conversation.updated
        -> upsert Lead node (props hydrated from live Postgres row)
    lead.assigned
        -> Lead-[:ASSIGNED_TO]->Agent (+ full Lead refresh from PG)
    site_visit.scheduled
        -> Lead visit props
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.knowledge_graph.neo4j_kg import knowledge_graph

logger = logging.getLogger("kg_writers")

GRAPH_EVENTS = [
    "lead.created",
    "lead.qualified",
    "lead.scored",
    "conversation.updated",
    "lead.assigned",
    "site_visit.scheduled",
]

# Demographic + score fields projected onto :Lead. Postgres wins over sparse payloads.
LEAD_PROP_FIELDS = (
    "name",
    "location",
    "property_type",
    "lead_temperature",
    "conversion_probability",
    "intent",
)

_UPSERT_EVENTS = frozenset(
    {"lead.created", "lead.qualified", "lead.scored", "conversation.updated"}
)


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


def _props_from_payload(payload: dict) -> dict:
    return {
        k: payload[k]
        for k in LEAD_PROP_FIELDS
        if payload.get(k) is not None
    }


def _props_from_lead_row(lead: Any) -> dict:
    props = {}
    for k in LEAD_PROP_FIELDS:
        v = getattr(lead, k, None)
        if v is not None:
            props[k] = v
    return props


def _hydrate_lead_props(lead_id: int, client_id: int, payload: dict) -> dict:
    """Build Lead props: event payload as base, live Postgres row overwrites.

    Sparse events like ``lead.scored`` only carry scores; without PG hydration
    location/name stay stuck at first-create values in Neo4j.
    """
    props = _props_from_payload(payload or {})
    try:
        from database import SessionLocal
        from models import Lead

        with SessionLocal() as db:
            lead = (
                db.query(Lead)
                .filter(Lead.id == lead_id, Lead.client_id == client_id)
                .first()
            )
            if lead is not None:
                props.update(_props_from_lead_row(lead))
    except Exception as e:  # noqa: BLE001 - never fail the writer on DB blips
        logger.debug("kg hydrate from PG failed lead=%s: %s", lead_id, e)
    return props


def _assigned_agent_from_row(lead_id: int, client_id: int) -> Optional[str]:
    """Read ``assigned_agent`` from the lead row (payload is identifiers-only)."""
    try:
        from database import SessionLocal
        from models import Lead

        with SessionLocal() as db:
            lead = (
                db.query(Lead.assigned_agent)
                .filter(Lead.id == lead_id, Lead.client_id == client_id)
                .first()
            )
        if lead is not None:
            return lead.assigned_agent
    except Exception as e:  # noqa: BLE001 - never fail the writer on DB blips
        logger.debug("kg assigned_agent read failed lead=%s: %s", lead_id, e)
    return None


def _visit_date_from_row(lead_id: int, client_id: int) -> Optional[Any]:
    """Read ``visit_date`` from the lead row (payload is identifiers-only)."""
    try:
        from database import SessionLocal
        from models import Lead

        with SessionLocal() as db:
            lead = (
                db.query(Lead.visit_date)
                .filter(Lead.id == lead_id, Lead.client_id == client_id)
                .first()
            )
        if lead is not None:
            return lead.visit_date
    except Exception as e:  # noqa: BLE001 - never fail the writer on DB blips
        logger.debug("kg visit_date read failed lead=%s: %s", lead_id, e)
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
        if event_type in _UPSERT_EVENTS:
            props = _hydrate_lead_props(lead_id, client_id, payload)
            knowledge_graph.upsert_lead(lead_id, client_id, props)
        elif event_type == "lead.assigned":
            props = _hydrate_lead_props(lead_id, client_id, payload)
            knowledge_graph.upsert_lead(lead_id, client_id, props)
            # P0 claim-check: payload is identifiers-only — read the assignee
            # from the live row (crm_automation commits before publish).
            agent_name = _assigned_agent_from_row(lead_id, client_id)
            if agent_name:
                knowledge_graph.link_lead_agent(lead_id, str(agent_name), client_id)
        elif event_type == "site_visit.scheduled":
            # P0 claim-check: visit_date comes from the lead row. visit_id is
            # not persisted on Lead and no longer travels on the bus.
            visit_date = _visit_date_from_row(lead_id, client_id)
            if visit_date:
                knowledge_graph.upsert_lead(lead_id, client_id, {"visit_date": visit_date})
    except Exception as e:  # noqa: BLE001 - writer never fails the agent
        logger.warning("graph writer failed for %s lead=%s: %s", event_type, lead_id, e)


def register_graph_writers(ceo) -> None:
    """Register the graph writer as an active CEO agent on core events."""
    ceo.register_agent(
        "kg_event_writer", graph_event_writer, subscriptions=list(GRAPH_EVENTS), status="active"
    )
    logger.info("Registered kg_event_writer on %d event types", len(GRAPH_EVENTS))
