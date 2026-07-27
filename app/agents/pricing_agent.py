"""IREIOS 3.0 — Wave C: PricingAgent."""
from __future__ import annotations

import logging
from typing import Optional

from app.automation_engine.engine import submit as ae_submit
from database import SessionLocal

logger = logging.getLogger(__name__)

_EVENTS = ["pricing.query", "lead.scored"]


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


def resolve_pricing(client_id: int, location: str, budget: int) -> Optional[dict]:
    db = SessionLocal()
    try:
        from models import PricingRule
        rules = db.query(PricingRule).filter(
            PricingRule.client_id == client_id,
            PricingRule.location == location,
        ).all()
        for rule in rules:
            min_b = rule.min_budget or 0
            max_b = rule.max_budget or float("inf")
            if min_b <= budget <= max_b:
                return {
                    "rule_id": rule.id,
                    "location": rule.location,
                    "bhk": rule.bhk,
                    "list_price": rule.list_price,
                    "notes": rule.notes,
                }
        return None
    finally:
        db.close()


async def handler(envelope: dict) -> None:
    client_id = _resolve_client_id(envelope.get("tenant_id"))
    if client_id is None:
        return
    payload = envelope.get("payload") or {}
    lead_id = envelope.get("entity_id") or payload.get("lead_id")
    location = payload.get("location", "")
    budget = payload.get("budget", 0)
    if not location:
        return
    try:
        budget = int(budget)
    except (ValueError, TypeError):
        budget = 0
    match = resolve_pricing(client_id, location, budget)
    try:
        await ae_submit({
            "action_type": "notify_agent",
            "tenant_id": f"Client_{client_id}",
            "entity_id": str(lead_id or "unknown"),
            "parameters": {
                "kind": "pricing_info",
                "lead_id": lead_id,
                "pricing": match or {"note": "No matching pricing rule found"},
            },
            "source": "pricing_agent",
        })
    except Exception as e:
        logger.warning("pricing query failed: %s", e)


def register_pricing(ceo) -> None:
    ceo.register_agent("pricing_agent", handler, subscriptions=list(_EVENTS), status="active")
    logger.info("Registered pricing_agent")
