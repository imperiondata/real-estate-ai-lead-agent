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


async def on_lead_created(event: dict) -> None:
    """CEO handler: arm a follow-up state when a lead is created/updated."""
    tenant_id = event.get("tenant_id", "Client_1")
    client_id = _resolve_client(tenant_id)
    payload = event.get("payload") or {}
    # Prefer explicit session_id (entity_id is often lead_id on lifecycle events).
    session_id = payload.get("session_id") or event.get("entity_id")
    if not session_id or str(session_id).isdigit():
        # entity_id was a bare lead id with no session — cannot arm.
        if not payload.get("session_id"):
            logger.debug("followup_arm skip: no session_id in event %s", event.get("event_type"))
            return
        session_id = payload.get("session_id")
    # New leads get an immediate Day 0 window; re-arms respect the existing row.
    arm_followup_state(str(session_id), client_id, next_in=0)


def _resolve_client(tenant_id) -> int:
    if tenant_id is None:
        return 1
    s = str(tenant_id).strip()
    if s.lower().startswith("client_"):
        s = s[len("client_"):]
    return int(s) if s.isdigit() else 1
