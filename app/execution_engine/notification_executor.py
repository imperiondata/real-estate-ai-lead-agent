"""IREIOS 3.0 — Phase 3.3 Notification Executor.

Wraps the existing ``notification_service`` patterns behind the Execution
Engine so alert/manager notifications also flow through ``AE -> EE -> Event``.
Keeps the proven escalation logic in ``notification_service`` as the source of
truth (Phase 10 may fold it in). The executor is intentionally thin: it routes
to the right existing helper based on ``parameters.kind``.

Supported ``kind`` values:
    - ``hot_lead``  -> ``notification_service.trigger_hot_lead_notification``
    - ``manager_approval`` -> ``notify_manager_approval_needed`` (log-only here)
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
                logger.info("Notification(admin): %s", message)
                return {"status": "success", "kind": "notify_admin"}
            if kind == "manager_approval":
                client_id = params.get("client_id")
                approval_id = params.get("approval_id")
                entity_id = params.get("entity_id")
                logger.info(
                    "Manager approval needed: client=%s approval=%s entity=%s",
                    client_id, approval_id, entity_id,
                )
                return {"status": "success", "kind": "manager_approval"}
            return {"status": "error", "error": f"unknown notification kind: {kind}"}
        except Exception as exc:  # noqa: BLE001 - EE captures into DLQ
            logger.error("Notification executor failed (%s): %s", kind, exc)
            return {"status": "error", "error": str(exc)}
