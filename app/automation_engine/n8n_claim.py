"""P0 n8n claim-check hydration.

The Redis stream payload stays exactly ``{"lead_id", "tenant_id"}``. The n8n
bridge rebuilds the workflow webhook body from Postgres immediately before
POST, scoped to the tenant that owns the row. No PII is written back to the
stream and no reconstructed body is logged.

The small ``n8n_claim_context`` table carries non-PII routing context that is
not on ``Lead`` (``trigger``, ``visit_id``, ``html_link``, ``provider``,
``action_type``, ``approval_id``). It has no name, phone, email, message, or
chat-context column.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from sqlalchemy import text

from app.services.prediction_service import (
    marketing_campaign_suggestion,
    segment_leads,
)
from database import SessionLocal
from models import ApprovalRequest, Lead

logger = logging.getLogger("n8n_claim")

_EVENT_TYPES = frozenset(
    {
        "lead.hot",
        "lead.qualified",
        "site_visit.scheduled",
        "approval.requested",
        "marketing.report.generated",
    }
)

_TOP_LEVEL_KEYS = (
    "event_id",
    "event_type",
    "tenant_id",
    "entity_id",
    "source",
    "timestamp",
    "correlation_id",
)

_COLUMN_SQL = {
    "trigger": '"trigger"',
    "visit_id": "visit_id",
    "html_link": "html_link",
    "provider": "provider",
    "action_type": "action_type",
    "approval_id": "approval_id",
}

_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS n8n_claim_context (
  id SERIAL PRIMARY KEY,
  client_id INTEGER NOT NULL,
  lead_id INTEGER NOT NULL,
  event_type VARCHAR NOT NULL,
  "trigger" VARCHAR,
  visit_id TEXT,
  html_link TEXT,
  provider VARCHAR,
  action_type VARCHAR,
  approval_id INTEGER,
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (client_id, lead_id, event_type)
)
"""


def ensure_claim_table(db) -> None:
    """Create the context table when missing.

    Safe to call before every write and every hydrate. Concurrent first-run
    creates can race on the Postgres catalog; that duplicate error is benign.
    """
    try:
        db.execute(text(_TABLE_DDL))
        db.commit()
    except Exception as exc:  # noqa: BLE001 - concurrency / idempotency guard
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        message = str(exc).lower()
        if "already exists" in message or "duplicate" in message:
            return
        raise


def _coerce_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _envelope_lead_id(envelope: dict) -> Optional[int]:
    payload = envelope.get("payload")
    payload = payload if isinstance(payload, dict) else {}
    lead_id = _coerce_int(payload.get("lead_id"))
    if lead_id is None:
        lead_id = _coerce_int(envelope.get("entity_id"))
    return lead_id


def _context_row(db, client_id: int, lead_id: int, event_type: str) -> Optional[dict]:
    row = db.execute(
        text(
            """
            SELECT "trigger" AS trigger, visit_id, html_link, provider,
                   action_type, approval_id
            FROM n8n_claim_context
            WHERE client_id = :client_id
              AND lead_id = :lead_id
              AND event_type = :event_type
            """
        ),
        {
            "client_id": int(client_id),
            "lead_id": int(lead_id),
            "event_type": event_type,
        },
    ).mappings().first()
    return dict(row) if row is not None else None


def upsert_claim(
    client_id: int,
    lead_id: int,
    event_type: str,
    *,
    session_factory: Callable[[], Any] = SessionLocal,
    **fields: Any,
) -> bool:
    """Best-effort context write. Never raises; the bus publish must proceed."""
    if client_id is None or lead_id is None or not event_type:
        return False
    try:
        client_id = int(client_id)
        lead_id = int(lead_id)
    except (TypeError, ValueError):
        return False

    clean = {k: v for k, v in fields.items() if k in _COLUMN_SQL}
    columns = ["client_id", "lead_id", "event_type"]
    values = [":client_id", ":lead_id", ":event_type"]
    params: dict[str, Any] = {
        "client_id": client_id,
        "lead_id": lead_id,
        "event_type": event_type,
    }
    for key, value in clean.items():
        columns.append(_COLUMN_SQL[key])
        values.append(f":{key}")
        params[key] = value

    updates = ", ".join(f"{_COLUMN_SQL[key]} = EXCLUDED.{_COLUMN_SQL[key]}" for key in clean)
    updates = (updates + ", " if updates else "") + "updated_at = NOW()"
    statement = text(
        f"""
        INSERT INTO n8n_claim_context ({", ".join(columns)})
        VALUES ({", ".join(values)})
        ON CONFLICT (client_id, lead_id, event_type)
        DO UPDATE SET {updates}
        """
    )

    db = None
    try:
        db = session_factory()
        ensure_claim_table(db)
        db.execute(statement, params)
        db.commit()
        return True
    except Exception as exc:  # noqa: BLE001 - context write is best-effort
        if db is not None:
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
        logger.error(
            "n8n_claim context write failed event=%s client=%s lead=%s: %s",
            event_type,
            client_id,
            lead_id,
            type(exc).__name__,
        )
        return False
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:  # noqa: BLE001
                pass


def _lead_payload(lead: Lead) -> dict:
    return {
        "name": lead.name,
        "phone": lead.phone,
        "location": lead.location,
        "budget": lead.budget,
        "property_type": lead.property_type,
    }


def _hydrate_approval(
    db,
    client_id: int,
    lead_id: int,
    envelope: dict,
) -> Optional[dict]:
    entity = envelope.get("entity_id")
    entity_str = str(entity).strip() if entity is not None else None

    approval = None
    if entity_str is not None:
        query = db.query(ApprovalRequest).filter(
            ApprovalRequest.client_id == client_id,
            ApprovalRequest.entity_id == entity_str,
        )
        approval = (
            query.filter(ApprovalRequest.status == "pending")
            .order_by(ApprovalRequest.created_at.desc())
            .first()
        )
        if approval is None:
            approval = query.order_by(ApprovalRequest.created_at.desc()).first()

    context = _context_row(db, client_id, lead_id, "approval.requested")
    if approval is None and context is None:
        return None

    action_type = approval.action_type if approval is not None else (context or {}).get("action_type")
    if not action_type:
        return None

    lead = (
        db.query(Lead)
        .filter(Lead.id == lead_id, Lead.client_id == client_id)
        .first()
    )
    return {
        "approval_id": approval.id if approval is not None else None,
        "action_type": action_type,
        "name": lead.name if lead is not None else None,
    }


def _hydrate_marketing(db, client_id: int) -> dict:
    segments = segment_leads(db, client_id)
    counts = segments.get("counts") or {}
    payload = {
        "segments": {
            "hot": {"count": int(counts.get("hot", 0) or 0)},
            "warm": {"count": int(counts.get("warm", 0) or 0)},
            "cold": {"count": int(counts.get("cold", 0) or 0)},
        },
        "suggestions": [],
    }
    for segment in ("hot", "warm", "cold"):
        suggestion = marketing_campaign_suggestion(segment)
        payload["suggestions"].append(
            {
                "segment": segment,
                "channel": suggestion.get("recommended_channel"),
                "message": suggestion.get("message_hint"),
            }
        )
    return payload


def hydrate_outbound(envelope: dict) -> tuple[Optional[dict], Optional[str]]:
    """Build the tenant-owned outbound webhook body, or deny.

    Returns ``(outbound_envelope, None)`` on success and
    ``(None, deny_reason)`` when the tenant/row cannot be resolved. Every
    inbound payload field except ``lead_id`` is ignored; PII on a fat envelope
    is never copied.
    """
    from app.execution_engine.execution_engine import resolve_client_id

    if not isinstance(envelope, dict):
        return None, "bad_envelope"

    event_type = envelope.get("event_type") or ""
    client_id = resolve_client_id(envelope.get("tenant_id"))
    if client_id is None:
        return None, "bad_tenant"
    if event_type not in _EVENT_TYPES:
        return None, "unsupported_event"

    lead_id = _envelope_lead_id(envelope)
    if event_type != "marketing.report.generated" and lead_id is None:
        return None, "missing_lead_id"

    db = SessionLocal()
    try:
        ensure_claim_table(db)

        if event_type == "marketing.report.generated":
            payload = _hydrate_marketing(db, client_id)
        elif event_type == "approval.requested":
            payload = _hydrate_approval(db, client_id, lead_id, envelope)
            if payload is None:
                return None, "not_owned"
        else:
            lead = (
                db.query(Lead)
                .filter(Lead.id == lead_id, Lead.client_id == client_id)
                .first()
            )
            if lead is None:
                return None, "not_owned"

            payload = _lead_payload(lead)
            if event_type == "lead.hot":
                payload["score"] = lead.conversion_probability
                payload["assigned_agent"] = lead.assigned_agent
                context = _context_row(db, client_id, lead_id, event_type)
                if context and context.get("trigger"):
                    payload["trigger"] = context["trigger"]
            elif event_type == "lead.qualified":
                payload["visit_date"] = lead.visit_date
            elif event_type == "site_visit.scheduled":
                payload["visit_date"] = lead.visit_date
                context = _context_row(db, client_id, lead_id, event_type)
                if context:
                    for key in ("visit_id", "html_link", "provider"):
                        if context.get(key):
                            payload[key] = context[key]
    finally:
        db.close()

    outbound = {key: envelope.get(key) for key in _TOP_LEVEL_KEYS}
    outbound["payload"] = payload
    return outbound, None
