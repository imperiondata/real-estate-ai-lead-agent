"""IREIOS 3.0 — Phase 4.3 Follow-up state arming.

Ensures a ``FollowUpState`` row exists for a lead/session when a ``lead.created``
(or activity re-arm) event arrives on the bus. Idempotent: a ``UNIQUE``
``session_id`` constraint means a second insert is a no-op (we catch the
integrity error and keep the existing row).

Registered with the CEO so the runtime loop owns re-arming after a WhatsApp
reply publishes ``lead.created`` / ``conversation.updated``.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.automation_engine.engine import submit
from config import settings
from database import SessionLocal
from models import FollowUpState

logger = logging.getLogger("workflow.followup_arm")


def arm_followup_state(session_id: str, client_id: int, next_in: int = 0) -> None:
    """Create a FollowUpState for ``session_id`` if one does not already exist.

    ``next_in`` minutes until the first follow-up (0 = immediate / Day 0).
    """
    if not session_id:
        return
    with SessionLocal() as db:
        existing = db.query(FollowUpState).filter(FollowUpState.session_id == session_id).first()
        if existing:
            return
        try:
            from datetime import datetime, timedelta, timezone

            state = FollowUpState(
                session_id=session_id,
                client_id=client_id,
                follow_up_stage="Day 0",
                follow_up_status="active",
                next_follow_up_at=datetime.now(timezone.utc) + timedelta(minutes=next_in),
            )
            db.add(state)
            db.commit()
            logger.info("Armed FollowUpState for session=%s client=%s", session_id, client_id)
        except Exception as exc:  # noqa: BLE001 - duplicate row is acceptable
            db.rollback()
            logger.debug("FollowUpState arm skipped for %s: %s", session_id, exc)


def _resolve_client_id(tenant_id) -> Optional[int]:
    """Map ``Client_<id>`` (or bare int) to int; ``None`` when unresolvable.

    P0 claim-check: never default to a tenant — no default, no cross-tenant arm.
    """
    if tenant_id is None:
        return None
    s = str(tenant_id).strip()
    if s.lower().startswith("client_"):
        s = s[len("client_"):]
    return int(s) if s.isdigit() else None


def _lead_id(envelope: dict) -> Optional[int]:
    payload = envelope.get("payload") or {}
    raw = payload.get("lead_id", envelope.get("entity_id"))
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


async def on_lead_created(event: dict) -> None:
    """CEO handler: arm a follow-up state when a lead is created/updated.

    P0 claim-check: the bus payload is ``{"lead_id", "tenant_id"}`` — the
    session id comes from the lead row. A lead missing / not owned by that
    tenant is skipped (never armed, never cross-tenant).
    """
    client_id = _resolve_client_id(event.get("tenant_id"))
    lead_id = _lead_id(event)
    if client_id is None or lead_id is None:
        logger.debug("followup_arm skip: unresolvable tenant/lead in event %s", event.get("event_type"))
        return
    with SessionLocal() as db:
        from models import Lead

        lead = db.query(Lead).filter(Lead.id == lead_id, Lead.client_id == client_id).first()
        if lead is None or not lead.session_id:
            logger.debug(
                "followup_arm skip: lead %s not owned by client %s or has no session", lead_id, client_id
            )
            return
        session_id = lead.session_id
    # New leads get an immediate Day 0 window; re-arms respect the existing row.
    arm_followup_state(str(session_id), client_id, next_in=0)
