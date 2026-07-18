"""IREIOS 3.0 — Phase 8.3: CustomerSuccessAgent.

CEO-registered active agent handling post-conversion / retention events:

    booking.confirmed / payment.received -> send a reminder/thank-you
                                            (notify_admin via AE).
    payment.due / renewal.due / document.pending -> reminder action.

Also exposes `scan_at_risk` (wrapping `prediction_service.detect_at_risk`) for
the CS cron path. Reminders are routed through AE -> EE (NotificationExecutor).
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


async def customer_success_handler(envelope: dict) -> None:
    client_id = _resolve_client_id(envelope.get("tenant_id"))
    if client_id is None:
        return
    event_type = envelope.get("event_type")
    message = _REMINDER_MESSAGES.get(event_type, "Customer success follow-up.")
    try:
        await ae_submit({
            "action_type": "notify_agent",
            "tenant_id": f"Client_{client_id}",
            "entity_id": str(envelope.get("entity_id", "cs")),
            "parameters": {"kind": "notify_admin", "message": message},
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
