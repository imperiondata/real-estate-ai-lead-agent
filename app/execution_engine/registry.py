"""IREIOS 3.0 — Execution Engine executor registration.

Central place that wires every concrete ``BaseExecutor`` and the success
``event_map`` into the module-level ``execution_engine`` singleton. Called once
from the app lifespan (after ``event_bus.start()``) so the production path uses
real executors.

Runtime: ``... -> Execution Engine -> Event`` (event_map publishes on success).
"""
from __future__ import annotations

import logging

from app.execution_engine.calendar_executor import CalendarExecutor
from app.execution_engine.crm_executor import CRMExecutor
from app.execution_engine.execution_engine import execution_engine
from app.execution_engine.notification_executor import NotificationExecutor
from app.execution_engine.task_executor import TaskExecutor
from app.execution_engine.whatsapp_executor import WhatsAppExecutor

logger = logging.getLogger("execution_engine.registry")

_REGISTERED = False


def register_executors() -> None:
    """Idempotently register all executors + success event map."""
    global _REGISTERED
    if _REGISTERED:
        return

    execution_engine.register("send_whatsapp", WhatsAppExecutor())
    execution_engine.register("update_crm", CRMExecutor())
    execution_engine.register("schedule_visit", CalendarExecutor())
    execution_engine.register("notify_agent", NotificationExecutor())
    execution_engine.register("create_task", TaskExecutor())

    # Success event map: action_type -> downstream event_type.
    execution_engine.register_event("send_whatsapp", "whatsapp.sent")
    execution_engine.register_event("update_crm", "lead.crm_synced")
    execution_engine.register_event("schedule_visit", "site_visit.scheduled")
    execution_engine.register_event("notify_agent", "notification.sent")
    execution_engine.register_event("create_task", "task.created")

    _REGISTERED = True
    logger.info(
        "Execution Engine executors registered "
        "(send_whatsapp, update_crm, schedule_visit, notify_agent, create_task)"
    )
