"""IREIOS 3.0 — Phase 2 Automation Engine.

The brain of actions. ``submit`` validates an ``action_request``, pauses for
HITL when ``requires_approval`` is set, otherwise executes via the Execution
Engine with bounded retry/backoff. A failed action falls back to an optional
``fallback_action`` before the Execution Engine writes a DLQ row.

This module owns the approval/retry policy. Agents and ``BaseAgent`` keep
calling ``submit`` unchanged — Phase 1's thin forwarder is replaced here
without touching agent code.

Runtime: ``Event -> CEO -> Agent/Workflow -> Automation Engine -> Execution Engine -> Event``.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from app.clients.event_bus_client import event_bus
from app.automation_engine.hitl import request_approval
from app.execution_engine.execution_engine import execution_engine
from config import settings
from models import ApprovalRequest

logger = logging.getLogger("automation_engine")

# Maximum attempts before the EE/DLQ path is taken (Path D).
_MAX_ATTEMPTS = 3

# Required keys on every incoming action request (tenant scoping is mandatory).
_REQUIRED_KEYS = ("action_type", "tenant_id", "entity_id", "parameters")


async def submit(action_request: dict, attempt: int = 1) -> dict:
    """Validate and execute an action request.

    Returns the Execution Engine result dict. On ``requires_approval`` the
    action is paused and a ``pending_approval`` result is returned (the
    original action is resumed by :func:`resume` once a manager approves).
    """
    if not isinstance(action_request, dict):
        return {"status": "error", "error": "action_request must be a dict"}

    missing = [k for k in _REQUIRED_KEYS if k not in action_request]
    if missing:
        logger.error("AutomationEngine rejected action (missing %s)", missing)
        await _publish_dropped(action_request, f"missing_keys:{missing}")
        return {"status": "error", "error": f"missing required keys: {missing}"}

    # HITL pause — short-circuit the Execution Engine.
    if action_request.get("requires_approval"):
        requested_by = action_request.get("requested_by") or action_request.get("source")
        approval = await request_approval(
            action_request,
            tenant_id=action_request["tenant_id"],
            entity_id=action_request.get("entity_id"),
            requested_by=requested_by,
        )
        logger.info("HITL pause: action=%s approval_id=%s", action_request["action_type"], approval["id"])
        return {"status": "pending_approval", "approval_id": approval["id"]}

    # Linear / template_type default to "linear". LangGraph/n8n are wired in
    # their respective runner modules (Tasks 2.4/2.5); for now we execute via EE.
    template_type = action_request.get("template_type", "linear")
    if template_type not in ("linear", "langgraph", "n8n"):
        template_type = "linear"
    action_request = {**action_request, "template_type": template_type}

    # Execute with bounded retry/backoff (Path D).
    result = await _execute_with_retry(action_request, attempt)

    # On EE failure, optionally run the declared fallback action once.
    if result.get("status") == "error" and action_request.get("fallback_action"):
        logger.info("running fallback_action for %s", action_request["action_type"])
        fallback = dict(action_request["fallback_action"])
        fallback.setdefault("tenant_id", action_request["tenant_id"])
        fallback.setdefault("entity_id", action_request["entity_id"])
        fallback.setdefault("parameters", {})
        result = await _execute_with_retry(fallback, 1)

    return result


async def resume(approval_id: int, manager_id: Optional[str] = None, reason: Optional[str] = None) -> dict:
    """Resume an approved action through the Automation Engine (flag stripped)."""
    from app.automation_engine.hitl import resolve as hitl_resolve

    res = await hitl_resolve(approval_id, "approve", manager_id=manager_id, reason=reason)
    if res.get("status") != "approved":
        return res
    action_request = dict(res["action_request"])
    action_request.pop("requires_approval", None)
    return await submit(action_request, attempt=1)


def reject(approval_id: int, manager_id: Optional[str] = None, reason: Optional[str] = None) -> dict:
    """Reject a pending approval (sync wrapper around HITL.resolve)."""
    from app.automation_engine.hitl import resolve as hitl_resolve

    async def _run():
        return await hitl_resolve(approval_id, "reject", manager_id=manager_id, reason=reason)

    return asyncio.get_event_loop().run_until_complete(_run())


async def _execute_with_retry(action_request: dict, attempt: int) -> dict:
    result = await execution_engine.dispatch(action_request)
    if result.get("status") == "success" or attempt >= _MAX_ATTEMPTS:
        return result

    backoff = 0.5 * (2 ** (attempt - 1))
    logger.warning(
        "action %s attempt %d failed (%s); retrying in %.1fs",
        action_request["action_type"], attempt, result.get("error"), backoff,
    )
    await asyncio.sleep(backoff)
    return await _execute_with_retry(action_request, attempt + 1)


async def _publish_dropped(action_request: dict, error: str) -> None:
    try:
        await event_bus.publish(
            "automation.dropped",
            action_request.get("tenant_id", "system"),
            action_request.get("entity_id", "unknown"),
            {"error": error, "action_type": action_request.get("action_type")},
            source="automation_engine",
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("failed to publish automation.dropped: %s", exc)


def expire_stale_approvals(max_age_hours: int = 24) -> int:
    """Mark pending approvals older than ``max_age_hours`` as expired.

    Returns the number expired. Should be wired to a scheduler cron so a stuck
    HITL queue cannot block actions forever.
    """
    from datetime import datetime, timedelta, timezone

    from database import SessionLocal

    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    expired = 0
    with SessionLocal() as db:
        rows = db.query(ApprovalRequest).filter(
            ApprovalRequest.status == "pending",
            ApprovalRequest.created_at < cutoff,
        ).all()
        for row in rows:
            row.status = "expired"
            row.resolved_at = datetime.now(timezone.utc)
            expired += 1
        if expired:
            db.commit()
    if expired:
        logger.info("expired %d stale approval requests", expired)
    return expired
