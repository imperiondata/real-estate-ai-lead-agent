"""IREIOS 3.0 — Wave C: FinanceAgent."""
from __future__ import annotations

import logging
from typing import Optional

from app.automation_engine.engine import submit as ae_submit
from database import SessionLocal

logger = logging.getLogger(__name__)

_EVENTS = ["payment.query", "finance.schedule"]


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


async def handler(envelope: dict) -> None:
    client_id = _resolve_client_id(envelope.get("tenant_id"))
    if client_id is None:
        return
    payload = envelope.get("payload") or {}
    lead_id = envelope.get("entity_id") or payload.get("lead_id")
    event_type = envelope.get("event_type")
    schedule_info = None
    if event_type == "finance.schedule":
        schedule_info = payload.get("schedule", {})
    try:
        await ae_submit({
            "action_type": "notify_agent",
            "tenant_id": f"Client_{client_id}",
            "entity_id": str(lead_id or "unknown"),
            "parameters": {
                "kind": "payment_info",
                "lead_id": lead_id,
                "query": payload.get("query", ""),
                "schedule": schedule_info,
                "message": f"Payment {'schedule' if schedule_info else 'query'} processed for lead {lead_id or 'unknown'}",
            },
            "source": "finance_agent",
        })
    except Exception as e:
        logger.warning("finance handler failed: %s", e)


def register_finance(ceo) -> None:
    ceo.register_agent("finance_agent", handler, subscriptions=list(_EVENTS), status="active")
    logger.info("Registered finance_agent")
