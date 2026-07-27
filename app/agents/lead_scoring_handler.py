"""IREIOS 3.0 — Phase 5/6: lead scoring handler.

CEO-registered active agent that (re)scores a lead on conversation activity
and publishes `lead.scored` so downstream agents (crm_automation, sales,
kg writers) can react. Deterministic — reuses `whatsapp_agent.score_lead`.

PR #10: when HOT rule met, dual-publishes ``lead.hot`` + alias ``lead.escalated``.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.agents.whatsapp_agent import score_lead
from app.clients.event_bus_client import event_bus
from app.events.lead_hot import is_hot, publish_lead_hot
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
    """Score the lead; publish lead.scored; if hot, lead.hot + lead.escalated.

    HOT rule: conversion_probability >= 82 OR lead_temperature == hot.
    """
    client_id = _resolve_client_id(envelope.get("tenant_id"))
    lead_id = _lead_id(envelope)
    if client_id is None or lead_id is None:
        return

    payload_in = envelope.get("payload") or {}
    session_id = payload_in.get("session_id")
    chat_context = payload_in.get("chat_context") or ""

    scores = {}
    lead_snapshot = None
    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id, Lead.client_id == client_id).first()
        if lead is None:
            return
        scores = score_lead(lead)
        for k, v in scores.items():
            setattr(lead, k, v)
        db.commit()
        db.refresh(lead)
        lead_snapshot = lead
        if not session_id:
            session_id = lead.session_id
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

    if lead_snapshot is not None and is_hot(
        conversion_probability=scores.get(
            "conversion_probability", lead_snapshot.conversion_probability
        ),
        lead_temperature=scores.get(
            "lead_temperature", lead_snapshot.lead_temperature
        ),
    ):
        prob = scores.get("conversion_probability", lead_snapshot.conversion_probability)
        await publish_lead_hot(
            client_id=client_id,
            lead=lead_snapshot,
            trigger="hot_threshold",
            reason=f"HOT threshold crossed (conversion_probability={prob})",
            session_id=session_id,
            chat_context=chat_context,
            score=prob,
            source="lead_scoring_handler",
        )


def register_lead_scoring(ceo) -> None:
    ceo.register_agent(
        "lead_scoring", lead_scoring_handler, subscriptions=list(SCORING_EVENTS), status="active"
    )
    logger.info("Registered lead_scoring on %d event types", len(SCORING_EVENTS))
