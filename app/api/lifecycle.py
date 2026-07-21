"""IREIOS 3.0 — Wave A.2: Lifecycle Event Producers.

Admin-gated endpoint for injecting lifecycle events (payment.due, booking.confirmed,
document.pending, etc.) that wake the CustomerSuccessAgent and other consumers.

Also emits ``booking.confirmed`` automatically when a visit is scheduled
successfully via the EE CalendarExecutor path.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import Lead

logger = logging.getLogger("lifecycle_api")

router = APIRouter(prefix="/api/v1/lifecycle", tags=["lifecycle"])

ADMIN_API_KEY_NAME = "X-Admin-Token"
admin_api_key_header = APIKeyHeader(name=ADMIN_API_KEY_NAME, auto_error=True)

_LIFECYCLE_EVENT_TYPES = {
    "booking.confirmed",
    "payment.received",
    "payment.due",
    "renewal.due",
    "document.pending",
    "customer.onboarded",
}


class LifecycleEventBody(BaseModel):
    event_type: str
    lead_id: int
    payload: dict = {}


def _verify_admin_key(api_key: str = Depends(admin_api_key_header)):
    admin_key = settings.ADMIN_API_KEY
    if not admin_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ADMIN_API_KEY not configured",
        )
    if api_key != admin_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Admin API Key",
        )
    return api_key


async def _publish_event(event_type: str, client_id: int, entity_id: str, payload: dict) -> None:
    """Publish a lifecycle event to the Redis Streams bus."""
    envelope = {
        "event_id": f"lifecycle_{event_type}_{entity_id}",
        "event_type": event_type,
        "tenant_id": f"Client_{client_id}",
        "entity_id": str(entity_id),
        "source": "lifecycle_api",
        "payload": payload,
    }
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        await r.xadd(settings.EVENT_STREAM_KEY, {"data": json.dumps(envelope, default=str)})
    finally:
        try:
            await r.aclose()
        except Exception:
            pass


@router.post("/events")
async def inject_lifecycle_event(
    body: LifecycleEventBody,
    _admin=Depends(_verify_admin_key),
    db: Session = Depends(get_db),
):
    """Inject a lifecycle event for a lead. Requires X-Admin-Token header.

    Valid event_types: booking.confirmed, payment.received, payment.due,
    renewal.due, document.pending, customer.onboarded.

    The lead_id is validated for existence and tenant context is resolved
    from the lead's client_id.
    """
    if body.event_type not in _LIFECYCLE_EVENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid event_type. Must be one of: {sorted(_LIFECYCLE_EVENT_TYPES)}",
        )

    lead = db.query(Lead).filter(Lead.id == body.lead_id).first()
    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead {body.lead_id} not found",
        )

    payload = {"lead_id": lead.id, **body.payload}
    try:
        await _publish_event(body.event_type, lead.client_id, str(lead.id), payload)
    except Exception as e:
        logger.error("lifecycle publish failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to publish event: {e}",
        )

    return {
        "status": "success",
        "event_type": body.event_type,
        "lead_id": lead.id,
        "client_id": lead.client_id,
    }
