"""IREIOS 3.0 — Phase 2 HITL (Human-in-the-Loop) approval module.

When an agent/workflow emits an action with ``requires_approval=True``, the
Automation Engine pauses the action and creates an ``ApprovalRequest`` here.
Managers approve/reject via the dashboard (``main.py`` approve/reject routes,
Task 2.6); on approve the original action is resumed (re-submitted to the
Automation Engine without the approval flag), on reject it is dropped.

Runtime: ``Event -> CEO -> Agent/Workflow -> Automation Engine (pause) -> HITL -> Manager -> resume/reject -> Execution Engine -> Event``.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.clients.event_bus_client import event_bus
from database import SessionLocal
from models import ApprovalRequest

logger = logging.getLogger("hitl")


async def request_approval(
    action_request: dict,
    tenant_id: Any,
    entity_id: Optional[str] = None,
    requested_by: Optional[str] = None,
) -> dict:
    """Persist a pending approval and publish ``approval.requested``.

    Returns the created ``ApprovalRequest`` row (as a dict) so callers can
    reference the ``id`` / ``correlation_id``.
    """
    client_id = _resolve_client_id(tenant_id)
    action_type = action_request.get("action_type")
    payload = {
        "action_type": action_type,
        "tenant_id": tenant_id,
        "entity_id": entity_id or action_request.get("entity_id"),
        "parameters": action_request.get("parameters", {}),
        "correlation_id": action_request.get("correlation_id"),
    }
    correlation_id = action_request.get("correlation_id") or _new_corr()

    row = ApprovalRequest(
        client_id=client_id,
        entity_id=entity_id or action_request.get("entity_id"),
        action_type=action_type,
        action_payload=payload,
        status="pending",
        requested_by=requested_by,
        correlation_id=correlation_id,
    )
    with SessionLocal() as db:
        db.add(row)
        db.commit()
        db.refresh(row)
        result = _row_to_dict(row)

    # Notify managers / dashboard via the bus (fire-and-forget).
    try:
        await event_bus.publish(
            "approval.requested",
            f"Client_{client_id}" if client_id is not None else "system",
            entity_id or action_request.get("entity_id", "approval"),
            {
                "approval_id": result["id"],
                "correlation_id": correlation_id,
                "action_type": action_type,
                "entity_id": entity_id or action_request.get("entity_id"),
            },
            source="hitl",
        )
    except Exception as exc:  # noqa: BLE001 - never block the pause path
        logger.error("failed to publish approval.requested: %s", exc)

    # Best-effort manager notification (log + allow real WhatsApp later).
    try:
        from notification_service import notify_manager_approval_needed  # type: ignore

        notify_manager_approval_needed(client_id, result["id"], action_type)
    except Exception as exc:  # noqa: BLE001 - optional dependency
        logger.debug("manager notify skipped: %s", exc)

    return result


async def resolve(
    approval_id: int,
    decision: str,
    manager_id: Optional[str] = None,
    reason: Optional[str] = None,
    db: Optional[Session] = None,
) -> dict:
    """Approve/reject an approval request.

    - approve: returns the stored ``action_payload`` so the caller can resume
      execution (re-submit through the Automation Engine without the flag).
    - reject: marks the request rejected and publishes ``approval.resolved``.
    """
    decision = decision.lower()
    if decision not in ("approve", "approved", "reject", "rejected"):
        raise ValueError(f"decision must be approve/reject, got {decision!r}")

    own_db = db is None
    if own_db:
        db = SessionLocal()
    try:
        row = db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()
        if row is None:
            raise LookupError(f"approval {approval_id} not found")
        if row.status != "pending":
            raise ValueError(f"approval {approval_id} already {row.status}")

        row.status = "approved" if decision.startswith("approve") else "rejected"
        row.resolved_by = manager_id
        row.reason = reason
        row.resolved_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
        result = _row_to_dict(row)
    finally:
        if own_db:
            db.close()

    try:
        await event_bus.publish(
            "approval.resolved",
            f"Client_{result['client_id']}" if result["client_id"] is not None else "system",
            result["entity_id"] or str(approval_id),
            result,
            source="hitl",
        )
    except Exception as exc:  # noqa: BLE001 - never block resolution
        logger.error("failed to publish approval.resolved: %s", exc)

    if result["status"] == "approved":
        return {"status": "approved", "action_request": result["action_payload"]}
    return {"status": "rejected", "action_request": None}


def get_pending(client_id: Optional[int] = None, db: Optional[Session] = None) -> list[dict]:
    """Return pending approvals (optionally scoped to a tenant)."""
    own_db = db is None
    if own_db:
        db = SessionLocal()
    try:
        q = db.query(ApprovalRequest).filter(ApprovalRequest.status == "pending")
        if client_id is not None:
            q = q.filter(ApprovalRequest.client_id == client_id)
        return [_row_to_dict(r) for r in q.order_by(ApprovalRequest.created_at.desc()).all()]
    finally:
        if own_db:
            db.close()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _resolve_client_id(tenant_id: Any) -> Optional[int]:
    if tenant_id is None:
        return None
    s = str(tenant_id).strip()
    if s.lower().startswith("client_"):
        s = s[len("client_"):]
    return int(s) if s.isdigit() else None


def _new_corr() -> str:
    import uuid

    return str(uuid.uuid4())


def _row_to_dict(row: ApprovalRequest) -> dict:
    return {
        "id": row.id,
        "client_id": row.client_id,
        "entity_id": row.entity_id,
        "action_type": row.action_type,
        "action_payload": row.action_payload,
        "status": row.status,
        "requested_by": row.requested_by,
        "resolved_by": row.resolved_by,
        "reason": row.reason,
        "correlation_id": row.correlation_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
    }
