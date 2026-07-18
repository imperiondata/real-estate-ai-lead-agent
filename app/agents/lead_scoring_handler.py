"""IREIOS 3.0 — Phase 5/6: lead scoring handler.

CEO-registered active agent that (re)scores a lead on conversation activity
and publishes `lead.scored` so downstream agents (crm_automation, sales,
kg writers) can react. Deterministic — reuses `whatsapp_agent.score_lead`.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.agents.whatsapp_agent import score_lead
from app.clients.event_bus_client import event_bus
from database import SessionLocal
from models import Lead

logger = logging.getLogger("lead_scoring_handler")

# One score pass per turn (main emits conversation.updated after every chat).
# lead.created alone is covered by the same turn's conversation.updated.
SCORING_EVENTS = ["conversation.updated"]


def _resolve_client_id(tenant_id) -> Optional[int]:
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


async def lead_scoring_handler(envelope: dict) -> None:
    """Score the lead and publish lead.scored with the score breakdown."""
    client_id = _resolve_client_id(envelope.get("tenant_id"))
    lead_id = _lead_id(envelope)
    if client_id is None or lead_id is None:
        return

    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id, Lead.client_id == client_id).first()
        if lead is None:
            return
        scores = score_lead(lead)
        for k, v in scores.items():
            setattr(lead, k, v)
        db.commit()
    finally:
        db.close()

    try:
        await event_bus.publish(
            "lead.scored",
            f"Client_{client_id}",
            str(lead_id),
            {"lead_id": lead_id, **scores},
            source="lead_scoring_handler",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("failed to publish lead.scored: %s", e)


def register_lead_scoring(ceo) -> None:
    ceo.register_agent(
        "lead_scoring", lead_scoring_handler, subscriptions=list(SCORING_EVENTS), status="active"
    )
    logger.info("Registered lead_scoring on %d event types", len(SCORING_EVENTS))
