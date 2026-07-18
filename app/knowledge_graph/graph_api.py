"""IREIOS 3.0 — Phase 7.3: Graph API routes (tenant-scoped).

Mounted at ``/api/v1/graph``:

- ``GET  /health``               — driver availability + schema version (no data).
- ``GET  /leads/{id}/context``   — graph context for a lead (tenant-scoped, 404
                                    if not owned by the caller's client).
- ``POST /upsert``               — admin/service-gated node upsert.

Neo4j down => health reports unavailable and context returns an empty graph
(Postgres remains the source of truth). Reuses the events-API auth so both the
API key and the FE JWT cookie work.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.events import get_events_client, _verify_admin_key
from app.clients.graph_client import graph_client
from app.knowledge_graph.neo4j_client import neo4j_client
from app.knowledge_graph.neo4j_kg import knowledge_graph
from database import get_db
from models import Client, Lead

logger = logging.getLogger("graph_api")

router = APIRouter(prefix="/api/v1/graph", tags=["graph"])


@router.get("/health")
async def graph_health():
    """Neo4j connectivity + schema version. No tenant data exposed."""
    return {"status": "success", **neo4j_client.health()}


@router.get("/leads/{lead_id}/context")
async def graph_lead_context(
    lead_id: int,
    client: Client = Depends(get_events_client),
    db: Session = Depends(get_db),
):
    """Graph context for a lead, tenant-scoped (404 if not owned)."""
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.client_id == client.id).first()
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    context = graph_client.get_lead_context(lead_id, client.id)
    return {
        "lead_id": lead_id,
        "available": graph_client.available,
        "context": context,
    }


@router.post("/upsert")
async def graph_upsert(request: Request, db: Session = Depends(get_db)):
    """Admin/service-gated Lead node upsert.

    Body: ``{"lead_id": int, "client_id": int, "props": {...},
    "agent_name"?: str}``.
    """
    _verify_admin_key(request)
    body = await request.json()
    lead_id = body.get("lead_id")
    client_id = body.get("client_id")
    if lead_id is None or client_id is None:
        raise HTTPException(status_code=422, detail="lead_id and client_id are required")
    if not knowledge_graph.available:
        return {"status": "skipped", "reason": "graph_unavailable"}
    knowledge_graph.upsert_lead(int(lead_id), int(client_id), body.get("props") or {})
    agent_name = body.get("agent_name")
    if agent_name:
        knowledge_graph.link_lead_agent(int(lead_id), str(agent_name), int(client_id))
    return {"status": "success", "lead_id": lead_id}
