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


def _resolve_client(tenant_id) -> Optional[int]:
    """Resolve a tenant id to an int client id, or None when unresolvable.

    Never returns a fallback tenant. ``None``, blank, or non-numeric ids
    (after stripping a ``Client_`` prefix) return ``None`` so the caller
    refuses to arm or write.
    """
    if tenant_id is None:
        return None
    s = str(tenant_id).strip()
    if not s:
        return None
    if s.lower().startswith("client_"):
        s = s[len("client_"):].strip()
    if not s or not s.isdigit():
        return None
    return int(s)


_resolve_client_id = _resolve_client


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
    client_id = _resolve_client(event.get("tenant_id"))
    if client_id is None:
        logger.debug(
            "followup_arm skip: missing/unresolvable tenant_id in event %s",
            event.get("event_type"),
        )
        return

    lead_id = _lead_id(event)
    if lead_id is not None:
        with SessionLocal() as db:
            from models import Lead

            lead = db.query(Lead).filter(Lead.id == lead_id, Lead.client_id == client_id).first()
            if lead is None or not lead.session_id:
                logger.debug(
                    "followup_arm skip: lead %s not owned by client %s or has no session", lead_id, client_id
                )
                return
            session_id = lead.session_id
        arm_followup_state(str(session_id), client_id, next_in=0)
        return

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
