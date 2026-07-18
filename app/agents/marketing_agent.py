"""IREIOS 3.0 — Phase 8.2: MarketingAgent.

CEO-registered active agent that produces marketing segmentation + campaign
suggestions on `cron.weekly_report` / `campaign.completed`, then publishes
`marketing.report.generated`. Deterministic — wraps `prediction_service`
(`segment_leads` / `marketing_campaign_suggestion`).

Spend-changing actions would require HITL; this agent only reports/suggests,
so no approval gate is engaged here (it never mutates spend directly).
"""
from __future__ import annotations

import logging
from typing import Optional

from app.clients.event_bus_client import event_bus
from app.services.prediction_service import marketing_campaign_suggestion, segment_leads
from database import SessionLocal

logger = logging.getLogger("marketing_agent")

MARKETING_EVENTS = ["cron.weekly_report", "campaign.completed"]


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


def build_marketing_report(db, client_id: int) -> dict:
    """Segment a client's leads and attach a campaign suggestion per segment."""
    segments = segment_leads(db, client_id)
    suggestions = {
        seg: marketing_campaign_suggestion(seg) for seg in ("hot", "warm", "cold")
    }
    return {"segments": segments, "suggestions": suggestions}


async def marketing_agent_handler(envelope: dict) -> None:
    client_id = _resolve_client_id(envelope.get("tenant_id"))
    if client_id is None:
        return
    db = SessionLocal()
    try:
        report = build_marketing_report(db, client_id)
    finally:
        db.close()
    try:
        await event_bus.publish(
            "marketing.report.generated",
            f"Client_{client_id}",
            "marketing",
            report,
            source="marketing_agent",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("failed to publish marketing.report.generated: %s", e)


def register_marketing_agent(ceo) -> None:
    ceo.register_agent(
        "marketing_agent", marketing_agent_handler, subscriptions=list(MARKETING_EVENTS), status="active"
    )
    logger.info("Registered marketing_agent on %d event types", len(MARKETING_EVENTS))
