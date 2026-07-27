"""IREIOS 3.0 — Phase 3.3 Notification Executor (Wave A.5 real paths).

Wraps the existing ``notification_service`` patterns behind the Execution
Engine so alert/manager notifications also flow through ``AE -> EE -> Event``.
Keeps the proven escalation logic in ``notification_service`` as the source of
truth (Phase 10 may fold it in).

Supported ``kind`` values:
    - ``hot_lead``  -> ``notification_service.trigger_hot_lead_notification``
    - ``notify_admin`` -> WhatsApp to manager/director (Wave A.5 real path)
    - ``manager_approval`` -> WhatsApp to manager with approval link (Wave A.5)
"""
from __future__ import annotations

import logging
from typing import Any

from app.execution_engine.base_executor import BaseExecutor

logger = logging.getLogger("executor.notification")


class NotificationExecutor(BaseExecutor):
    """Triggers an internal notification via the existing notification service."""

    action_type = "notify_agent"

    async def execute(self, action_request: dict) -> dict:
        params = action_request.get("parameters", {}) or {}
        kind = params.get("kind", "hot_lead")
        try:
            if kind == "hot_lead":
                lead_id = params.get("lead_id")
                reason = params.get("reason", "High-intent behavior detected")
                if lead_id is None:
                    return {"status": "error", "error": "hot_lead requires 'lead_id'"}
                from notification_service import trigger_hot_lead_notification

                severity = params.get("severity")
                await trigger_hot_lead_notification(lead_id, reason=reason, severity=severity)
                return {"status": "success", "kind": kind, "lead_id": lead_id}

            if kind == "notify_admin":
                message = params.get("message", "")
                tenant_id = action_request.get("tenant_id", "")
                client_id = _parse_client_id(tenant_id)
                if client_id is None:
                    logger.warning("notify_admin: cannot resolve client_id from %s", tenant_id)
                    return {"status": "error", "error": "cannot resolve client_id"}
                agent_phone = _resolve_manager_phone(client_id)
                if agent_phone:
                    from app.execution_engine.outbound import send_whatsapp_via_executor as _send
                    await _send(
                        to=agent_phone,
                        body=f"[Admin Notification] {message}",
                        source="notification_executor",
                    )
                    return {"status": "success", "kind": "notify_admin", "sent_to": agent_phone}
                logger.info("notify_admin: no manager phone found for client %s", client_id)
                return {"status": "success", "kind": "notify_admin", "note": "logged only; no manager phone"}

            if kind == "manager_approval":
                client_id = params.get("client_id")
                approval_id = params.get("approval_id")
                entity_id = params.get("entity_id")
                reason = params.get("reason", "")
                tenant_id = action_request.get("tenant_id", "")
                if client_id is None:
                    client_id = _parse_client_id(tenant_id)
                if client_id is None:
                    return {"status": "error", "error": "manager_approval requires client_id"}
                agent_phone = _resolve_manager_phone(client_id)
                if agent_phone:
                    from app.execution_engine.outbound import send_whatsapp_via_executor as _send
                    body = f"[Approval Needed] {reason} — Approve/Reject #{approval_id} for {entity_id}"
                    await _send(
                        to=agent_phone,
                        body=body,
                        source="notification_executor",
                    )
                    return {"status": "success", "kind": "manager_approval", "sent_to": agent_phone}
                logger.info(
                    "manager_approval: no manager phone for client %s; logged only",
                    client_id,
                )
                return {"status": "success", "kind": "manager_approval", "note": "logged only; no manager phone"}

            return {"status": "error", "error": f"unknown notification kind: {kind}"}
        except Exception as exc:  # noqa: BLE001 - EE captures into DLQ
            logger.error("Notification executor failed (%s): %s", kind, exc)
            return {"status": "error", "error": str(exc)}


def _parse_client_id(tenant_id: str) -> int | None:
    """Extract integer client_id from a ``Client_N`` tenant string."""
    if not tenant_id:
        return None
    s = str(tenant_id)
    if s.startswith("Client_"):
        s = s.split("_", 1)[1]
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


def _resolve_manager_phone(client_id: int) -> str | None:
    """Return the phone of the first manager/director for the client, or None."""
    from database import SessionLocal
    from models import Agent
    from notification_service import pick_escalation_agent

    db = SessionLocal()
    try:
        agents = db.query(Agent).filter(Agent.client_id == client_id).all()
        if not agents:
            return None
        for tier in ("30m", "10m"):
            chosen = pick_escalation_agent(agents, tier)
            if chosen and chosen.phone:
                return chosen.phone
        return None
    finally:
        db.close()
