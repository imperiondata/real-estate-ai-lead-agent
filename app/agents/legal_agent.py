"""IREIOS 3.0 — Wave C: LegalAgent."""
from __future__ import annotations

import logging
from typing import Optional

from app.automation_engine.engine import submit as ae_submit
from database import SessionLocal

logger = logging.getLogger(__name__)

_EVENTS = ["document.required", "legal.review"]


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


async def handler(envelope: dict) -> None:
    client_id = _resolve_client_id(envelope.get("tenant_id"))
    if client_id is None:
        return
    payload = envelope.get("payload") or {}
    lead_id = envelope.get("entity_id") or payload.get("lead_id")
    event_type = envelope.get("event_type")
    docs = payload.get("documents", [])
    if event_type == "document.required" and not docs:
        docs = ["Agreement", "KYC", "Title Deed"]
    doc_list = ", ".join(docs) if isinstance(docs, list) else str(docs)
    try:
        await ae_submit({
            "action_type": "notify_agent",
            "tenant_id": f"Client_{client_id}",
            "entity_id": str(lead_id or "unknown"),
            "parameters": {
                "kind": "notify_admin",
                "lead_id": lead_id,
                "documents_required": doc_list,
                "message": f"Legal {'review' if event_type == 'legal.review' else 'documents'} required for lead {lead_id or 'unknown'}: {doc_list}",
            },
            "source": "legal_agent",
        })
    except Exception as e:
        logger.warning("legal handler failed: %s", e)


def register_legal(ceo) -> None:
    ceo.register_agent("legal_agent", handler, subscriptions=list(_EVENTS), status="active")
    logger.info("Registered legal_agent")
