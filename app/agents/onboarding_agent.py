"""IREIOS 3.0 — Wave C: OnboardingAgent."""
from __future__ import annotations

import logging
from typing import Optional

from app.automation_engine.engine import submit as ae_submit
from database import SessionLocal

logger = logging.getLogger(__name__)

_EVENTS = ["customer.onboarded", "booking.confirmed"]


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
    except Exception:
        return None
    finally:
        db.close()


_WELCOME_CHECKLIST = (
    "Welcome aboard! Here is your onboarding checklist:\n"
    "1. Sign the booking agreement\n"
    "2. Submit KYC documents (Aadhaar, PAN)\n"
    "3. Review payment schedule\n"
    "4. Schedule site visit\n"
    "5. Meet our relationship manager\n\n"
    "Let us know if you need any help!"
)


async def handler(envelope: dict) -> None:
    client_id = _resolve_client_id(envelope.get("tenant_id"))
    if client_id is None:
        return
    lead_id = envelope.get("entity_id") or envelope.get("payload", {}).get("lead_id")
    if lead_id is None:
        return
    try:
        lead_id = int(lead_id)
    except (ValueError, TypeError):
        return
    phone = await _resolve_lead_phone(lead_id)
    try:
        if phone:
            await ae_submit({
                "action_type": "send_whatsapp",
                "tenant_id": f"Client_{client_id}",
                "entity_id": str(lead_id),
                "parameters": {"to": phone, "body": _WELCOME_CHECKLIST},
                "source": "onboarding_agent",
            })
        else:
            await ae_submit({
                "action_type": "notify_agent",
                "tenant_id": f"Client_{client_id}",
                "entity_id": str(lead_id),
                "parameters": {
                    "kind": "notify_admin",
                    "message": f"Onboarding checklist ready for lead {lead_id} — no phone on record",
                },
                "source": "onboarding_agent",
            })
    except Exception as e:
        logger.warning("onboarding send failed: %s", e)


def register_onboarding(ceo) -> None:
    ceo.register_agent("onboarding_agent", handler, subscriptions=list(_EVENTS), status="active")
    logger.info("Registered onboarding_agent")
