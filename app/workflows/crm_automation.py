"""IREIOS 3.0 — Phase 6.1: CRM Automation workflow.

CEO-registered active agent that reacts to lead lifecycle events and:

  1. loads the lead (tenant-scoped),
  2. ensures a sticky agent assignment (`ensure_lead_assignment`),
  3. routes a `update_crm` action through the AutomationEngine -> ExecutionEngine
     (CRMExecutor, DLQ-protected),
  4. publishes `lead.assigned` when a new assignment was made.

Idempotent: if the lead is already assigned to the same agent no duplicate
`lead.assigned` is emitted. Best-effort — a missing lead / DB error logs and
returns without crashing the bus.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.automation_engine.engine import submit as ae_submit
from app.clients.event_bus_client import event_bus
from app.intelligence.agent_matcher import ensure_lead_assignment
from database import SessionLocal
from models import Lead

logger = logging.getLogger("crm_automation")

# lead.created / qualified only — not every lead.scored (avoids CRM storm per turn).
# Field-level re-sync remains on crm_resync_job (BD-1: create path is bus-only).
CRM_EVENTS = ["lead.created", "lead.qualified"]


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


async def crm_automation_handler(envelope: dict) -> None:
    """Ensure assignment + CRM sync for a lead event; emit lead.assigned."""
    client_id = _resolve_client_id(envelope.get("tenant_id"))
    lead_id = _lead_id(envelope)
    if client_id is None or lead_id is None:
        return

    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id, Lead.client_id == client_id).first()
        if lead is None:
            logger.debug("crm_automation: lead %s not found for client %s", lead_id, client_id)
            return

        previous_agent = lead.assigned_agent
        assigned = ensure_lead_assignment(
            db, lead, client_id, lead.intent or lead.location or "", force=False
        )
        db.commit()

        newly_assigned = bool(assigned) and assigned != previous_agent
    finally:
        db.close()

    # CRM sync via AE -> EE (DLQ protected).
    try:
        await ae_submit({
            "action_type": "update_crm",
            "tenant_id": f"Client_{client_id}",
            "entity_id": f"lead:{lead_id}",
            "parameters": {"lead_id": lead_id},
            "source": "crm_automation",
        })
    except Exception as e:  # noqa: BLE001 - DLQ catches; never crash bus
        logger.warning("crm_automation CRM sync failed (DLQ may catch): %s", e)

    if newly_assigned:
        try:
            await event_bus.publish(
                "lead.assigned",
                f"Client_{client_id}",
                str(lead_id),
                {"lead_id": lead_id, "assigned_agent": assigned},
                source="crm_automation",
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("crm_automation failed to publish lead.assigned: %s", e)


def register_crm_automation(ceo) -> None:
    """Register the CRM automation workflow as an active CEO agent."""
    ceo.register_agent(
        "crm_automation", crm_automation_handler, subscriptions=list(CRM_EVENTS), status="active"
    )
    logger.info("Registered crm_automation on %d event types", len(CRM_EVENTS))
