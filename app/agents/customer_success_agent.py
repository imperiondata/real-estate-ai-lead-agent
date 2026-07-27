"""IREIOS 3.0 — Phase 8.3 + Wave B.3: CustomerSuccessAgent.

CEO-registered active agent handling post-conversion / retention events:

    booking.confirmed / payment.received -> send welcome/thank-you
                                            WhatsApp to customer phone.
    payment.due / renewal.due / document.pending -> WhatsApp reminder.
    customer.onboarded -> kick off onboarding checklist.

When the lead phone is known the agent sends WhatsApp via AE (send_whatsapp),
otherwise falls back to notify_admin (Wave A.5 real path or logged).

Also exposes `scan_at_risk` (wrapping `prediction_service.detect_at_risk`) for
the CS cron path.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.automation_engine.engine import submit as ae_submit
from app.services.prediction_service import detect_at_risk
from database import SessionLocal

logger = logging.getLogger("customer_success_agent")

CS_EVENTS = [
    "booking.confirmed",
    "payment.received",
    "payment.due",
    "renewal.due",
    "document.pending",
    "customer.onboarded",
]

_REMINDER_MESSAGES = {
    "booking.confirmed": "Booking confirmed — send welcome + next-steps checklist.",
    "payment.received": "Payment received — send receipt + thank-you.",
    "payment.due": "Payment due — send a gentle reminder.",
    "renewal.due": "Renewal due — reach out to retain the customer.",
    "document.pending": "Document pending — nudge the customer to complete it.",
}


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


async def _resolve_lead_phone(lead_id: int) -> Optional[str]:
    try:
        db = SessionLocal()
        from models import Lead as LeadModel
        lead = db.query(LeadModel).filter(LeadModel.id == lead_id).first()
        return lead.phone if lead else None
    except Exception:  # noqa: BLE001
        return None
    finally:
        db.close()


async def customer_success_handler(envelope: dict) -> None:
    client_id = _resolve_client_id(envelope.get("tenant_id"))
    if client_id is None:
        return
    event_type = envelope.get("event_type")
    message = _REMINDER_MESSAGES.get(event_type, "Customer success follow-up.")
    lead_id = envelope.get("entity_id") or envelope.get("payload", {}).get("lead_id")
    phone = None
    if lead_id:
        phone = await _resolve_lead_phone(int(lead_id))
    try:
        if phone:
            await ae_submit({
                "action_type": "send_whatsapp",
                "tenant_id": f"Client_{client_id}",
                "entity_id": str(lead_id or "cs"),
                "parameters": {"to": phone, "body": message},
                "source": "customer_success_agent",
            })
        else:
            await ae_submit({
                "action_type": "notify_agent",
                "tenant_id": f"Client_{client_id}",
                "entity_id": str(lead_id or "cs"),
                "parameters": {"kind": "notify_admin", "message": message + " (no customer phone)"},
                "source": "customer_success_agent",
            })
    except Exception as e:  # noqa: BLE001
        logger.warning("CS reminder failed (DLQ may catch): %s", e)


def scan_at_risk(db, client_id: int, inactivity_days: int = 7) -> list:
    """CS cron helper — return at-risk leads for a client."""
    return detect_at_risk(db, client_id, inactivity_days=inactivity_days)


def register_customer_success(ceo) -> None:
    ceo.register_agent(
        "customer_success_agent", customer_success_handler, subscriptions=list(CS_EVENTS), status="active"
    )
    logger.info("Registered customer_success_agent on %d event types", len(CS_EVENTS))
