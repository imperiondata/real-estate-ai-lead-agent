"""IREIOS 3.0 — Wave C: InventoryAgent."""
from __future__ import annotations

import logging
from typing import Optional

from app.automation_engine.engine import submit as ae_submit
from database import SessionLocal

logger = logging.getLogger(__name__)

_EVENTS = ["inventory.query", "inventory.hold"]


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


def query_inventory(client_id: int, location: str = "", bhk: str = "", budget: int = 0) -> list[dict]:
    db = SessionLocal()
    try:
        from models import InventoryUnit
        q = db.query(InventoryUnit).filter(InventoryUnit.client_id == client_id, InventoryUnit.status == "available")
        if location:
            q = q.filter(InventoryUnit.location.ilike(f"%{location}%"))
        if bhk:
            q = q.filter(InventoryUnit.bhk == bhk)
        units = q.all()
        result = []
        for u in units:
            if budget and u.list_price and budget < u.list_price:
                continue
            result.append({
                "id": u.id,
                "project_name": u.project_name,
                "tower": u.tower,
                "unit_code": u.unit_code,
                "bhk": u.bhk,
                "location": u.location,
                "list_price": u.list_price,
                "status": u.status,
                "carpet_sqft": u.carpet_sqft,
            })
        return result
    finally:
        db.close()


async def handler(envelope: dict) -> None:
    client_id = _resolve_client_id(envelope.get("tenant_id"))
    if client_id is None:
        return
    payload = envelope.get("payload") or {}
    lead_id = envelope.get("entity_id") or payload.get("lead_id")
    location = payload.get("location", "")
    bhk = payload.get("bhk", "")
    budget = payload.get("budget", 0)
    try:
        budget = int(budget)
    except (ValueError, TypeError):
        budget = 0
    units = query_inventory(client_id, location, bhk, budget)
    try:
        await ae_submit({
            "action_type": "notify_agent",
            "tenant_id": f"Client_{client_id}",
            "entity_id": str(lead_id or "unknown"),
            "parameters": {
                "kind": "inventory_data",
                "lead_id": lead_id,
                "units": units,
                "count": len(units),
            },
            "source": "inventory_agent",
        })
    except Exception as e:
        logger.warning("inventory query failed: %s", e)


def register_inventory(ceo) -> None:
    ceo.register_agent("inventory_agent", handler, subscriptions=list(_EVENTS), status="active")
    logger.info("Registered inventory_agent")
