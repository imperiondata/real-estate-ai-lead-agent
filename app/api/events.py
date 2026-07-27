"""IREIOS 3.0 — Phase 1b early API envelopes + SSE (frontend unblock).

Exposes three routes (mounted at ``/api/v1/events``):

- ``GET  /stream``                 — tenant-scoped Server-Sent Events bridge
                                      from the Redis Streams event bus.
- ``GET  /leads/{id}/timeline``    — envelope-shaped event history for a lead
                                      (sourced from ``event_logs`` today).
- ``POST /stub``                   — admin-only publisher of sample events so
                                      the FE can receive live data on SSE
                                      without WhatsApp/LLM producers.

Contracts here are frozen for the frontend (Mayank). Producers stay stub /
``event_log``-derived until later phases fill them in.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

import jwt as jwt_lib
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.clients.event_bus_client import event_bus
from auth import SECRET_KEY, ALGORITHM, get_current_client
from config import tenant_id_ctx
from database import get_db
from models import Client, EventLog, Lead, Session as SessionModel

logger = logging.getLogger("events_api")

router = APIRouter(prefix="/api/v1/events", tags=["events"])

HEARTBEAT_SEC = 15
SSE_QUEUE_MAX = 1000
ADMIN_API_KEY_NAME = "X-Admin-Token"


# --------------------------------------------------------------------------- #
# Auth: api_key query/header (webhook-style) OR jwt HttpOnly cookie (frontend)
# --------------------------------------------------------------------------- #
async def get_events_client(
    request: Request,
    api_key: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> Client:
    # 1) API key (header X-API-Key or ?api_key=) — easy curl testing.
    header_key = request.headers.get("X-API-Key")
    candidate = api_key or header_key
    if candidate:
        client = (
            db.query(Client)
            .filter(Client.api_key == candidate, Client.is_active.is_(True))
            .first()
        )
        if client:
            tenant_id_ctx.set(f"Client_{client.id}")
            return client
    # 2) JWT HttpOnly cookie (frontend EventSource cannot set headers).
    token = request.cookies.get("jwt")
    if token:
        try:
            payload = jwt_lib.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            client_id = payload.get("sub")
            if client_id:
                client = (
                    db.query(Client)
                    .filter(Client.id == int(client_id), Client.is_active.is_(True))
                    .first()
                )
                if client:
                    tenant_id_ctx.set(f"Client_{client.id}")
                    return client
        except Exception:  # noqa: BLE001 - fall through to 401
            pass
    raise HTTPException(status_code=401, detail="Unauthorized")


def _verify_admin_key(request: Request) -> None:
    admin_key = os.getenv("ADMIN_API_KEY")
    if not admin_key or admin_key == "real-estate-super-secret-key":
        raise RuntimeError("CRITICAL SECURITY RISK: ADMIN_API_KEY is missing or insecure in .env.")
    provided = request.headers.get(ADMIN_API_KEY_NAME)
    if provided != admin_key:
        raise HTTPException(status_code=403, detail="Invalid or missing Admin API Key")


# --------------------------------------------------------------------------- #
# Task 1b.1 — SSE stream
# --------------------------------------------------------------------------- #
@router.get("/stream")
async def events_stream(
    request: Request,
    client: Client = Depends(get_events_client),
):
    """Tenant-scoped Server-Sent Events bridge from the event bus.

    The caller's ``tenant_id`` (``Client_<id>``) is used to filter envelopes;
    only events for that tenant are streamed. Sends a ``: ping`` comment every
    ``HEARTBEAT_SEC`` seconds to keep proxies from buffering/closure.
    """
    if not event_bus._running:
        raise HTTPException(status_code=503, detail="Event bus not available")

    tenant_id = f"Client_{client.id}"
    queue: asyncio.Queue = asyncio.Queue(maxsize=SSE_QUEUE_MAX)

    def _handler(envelope: dict) -> None:
        if envelope.get("tenant_id") != tenant_id:
            return
        try:
            queue.put_nowait(envelope)
        except asyncio.QueueFull:  # drop oldest pressure; never block bus loop
            pass

    event_bus.subscribe("*", _handler)

    async def _generator():
        try:
            while True:
                try:
                    envelope = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SEC)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield f"data: {json.dumps(envelope, default=str)}\n\n"
        finally:
            event_bus.unsubscribe("*", _handler)

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# --------------------------------------------------------------------------- #
# Task 1b.2 — Timeline envelope (lead -> session -> event_log)
# --------------------------------------------------------------------------- #
@router.get("/leads/{lead_id}/timeline")
async def lead_timeline(
    lead_id: int,
    client: Client = Depends(get_events_client),
    db: Session = Depends(get_db),
):
    """Return envelope-shaped events for a lead, tenant-scoped.

    Sourced from ``event_logs`` via the lead's sessions. When no logs exist
    the list is empty (stable schema for the FE). Real producers (Phase 7/9)
    will enrich this later.
    """
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.client_id == client.id).first()
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")

    session_ids = [
        s.id
        for s in db.query(SessionModel).filter(SessionModel.id == lead.session_id).all()
    ]
    events: list[dict] = []
    if session_ids:
        logs = (
            db.query(EventLog)
            .filter(EventLog.session_id.in_(session_ids), EventLog.client_id == client.id)
            .order_by(EventLog.timestamp.desc())
            .limit(100)
            .all()
        )
        for log in logs:
            events.append(
                {
                    "event_id": f"evt_{log.id}",
                    "event_type": log.event_type,
                    "tenant_id": f"Client_{log.client_id}",
                    "entity_id": str(lead_id),
                    "source": "event_log",
                    "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                    "correlation_id": None,
                    "payload": {
                        "action_type": log.action_type,
                        "agent_type": log.agent_type,
                        "latency_ms": log.latency_ms,
                    },
                }
            )
    return {"lead_id": lead_id, "events": events}


# --------------------------------------------------------------------------- #
# Task 1b.3 — Stub event publisher (admin only)
# --------------------------------------------------------------------------- #
@router.post("/stub")
async def publish_stub_event(request: Request):
    """Publish a sample event onto the bus (admin-gated).

    Body: ``{"event_type": str, "tenant_id"?: str, "entity_id"?: str,
    "payload"?: dict}``. Returns the new ``event_id`` so callers (and the FE
    SSE stream) can observe it without real WhatsApp/LLM producers.
    """
    _verify_admin_key(request)
    if not event_bus._running:
        raise HTTPException(status_code=503, detail="Event bus not available")

    body = await request.json()
    event_type = body.get("event_type")
    if not event_type:
        raise HTTPException(status_code=422, detail="event_type is required")

    tenant_id = body.get("tenant_id", "system")
    entity_id = body.get("entity_id", "stub")
    payload = body.get("payload", {})
    event_id = await event_bus.publish(event_type, tenant_id, entity_id, payload, source="stub")
    return {"status": "success", "event_id": event_id}
