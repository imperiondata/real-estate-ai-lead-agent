"""IREIOS 3.0 — Execution Engine (Phase 1 skeleton).

Dispatches an ``action_request`` to the registered ``BaseExecutor``. An
unknown action type, an executor that raises, or an executor that returns
``status == "error"`` all result in a DLQ row (`DLQEvent`) being written via
the injected session factory, and an error dict returned (never an uncaught
raise in the production path).

On success, if the action type maps to an event type in ``_EVENT_MAP``, the
engine publishes that event on the bus (fire-and-forget, via
``asyncio.create_task``) so the runtime loop closes: ``... -> Execution
Engine -> Event``. The map starts empty (populated in Phase 3).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

from app.clients.event_bus_client import event_bus
from app.execution_engine.base_executor import BaseExecutor
from database import SessionLocal
from models import DLQEvent

logger = logging.getLogger("execution_engine")


def resolve_client_id(tenant_id: Any) -> Optional[int]:
    """Map a bus/action ``tenant_id`` to an integer ``clients.id``.

    The codebase consistently identifies tenants as ``Client_<id>`` (see
    ``auth.py`` / ``main.py`` ``tenant_id_ctx``), but envelopes may also carry
    a bare integer string. Returns ``None`` when the id cannot be parsed so a
    DLQ row is still written (with a nullable ``client_id``).
    """
    if tenant_id is None:
        return None
    s = str(tenant_id).strip()
    if s.lower().startswith("client_"):
        s = s[len("client_"):]
    if s.isdigit():
        return int(s)
    return None


class ExecutionEngine:
    """Routes action requests to executors and owns DLQ writes."""

    def __init__(
        self,
        session_factory: Optional[Callable[[], Any]] = None,
        bus: Any = None,
    ):
        self._executors: dict[str, BaseExecutor] = {}
        # Injectable for tests; default to the real SQLAlchemy SessionLocal.
        self._session_factory = session_factory or SessionLocal
        self.bus = bus if bus is not None else event_bus
        # action_type -> event_type published on success (Phase 3 fills this).
        self._event_map: dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # Registration
    # ------------------------------------------------------------------ #
    def register(self, action_type: str, executor: BaseExecutor) -> None:
        self._executors[action_type] = executor

    def register_event(self, action_type: str, event_type: str) -> None:
        """Map a successful action type to a downstream event type."""
        self._event_map[action_type] = event_type

    # ------------------------------------------------------------------ #
    # Dispatch
    # ------------------------------------------------------------------ #
    async def dispatch(self, action_request: dict) -> dict:
        action_type = (action_request or {}).get("action_type")
        executor = self._executors.get(action_type)
        if executor is None:
            return self._fail(action_request, action_type, "no_executor")

        try:
            result = await executor.execute(action_request)
        except Exception as exc:  # noqa: BLE001 - capture into DLQ, never raise
            return self._fail(action_request, action_type, str(exc))

        if not isinstance(result, dict) or result.get("status") == "error":
            error = (result or {}).get("error", "executor_error")
            return self._fail(action_request, action_type, str(error))

        await self._publish_success(action_request, result)
        return result

    # ------------------------------------------------------------------ #
    # Error / DLQ
    # ------------------------------------------------------------------ #
    def _fail(self, action_request: dict, action_type: Any, error: str) -> dict:
        logger.error("ExecutionEngine action=%s failed: %s", action_type, error)
        self._write_dlq(action_request, action_type, error)
        return {"status": "error", "action_type": action_type, "error": error}

    def _write_dlq(self, action_request: dict, action_type: Any, error: str) -> None:
        tenant_id = (action_request or {}).get("tenant_id")
        try:
            with self._session_factory() as db:
                db.add(
                    DLQEvent(
                        client_id=resolve_client_id(tenant_id),
                        target_endpoint=str(action_type or "unknown"),
                        payload=action_request,
                        error_trace=error,
                        status="pending",
                    )
                )
                db.commit()
        except Exception as exc:  # noqa: BLE001 - DLQ write must never crash dispatch
            logger.error("DLQ write failed for action=%s: %s", action_type, exc)

    # ------------------------------------------------------------------ #
    # Success event publish
    # ------------------------------------------------------------------ #
    async def _publish_success(self, action_request: dict, result: dict) -> None:
        action_type = action_request.get("action_type")
        event_type = self._event_map.get(action_type)
        if event_type is None:
            return
        if self.bus is None:
            return
        try:
            await self.bus.publish(
                event_type,
                action_request.get("tenant_id", "system"),
                action_request.get("entity_id", action_type),
                result,
                source="execution_engine",
                correlation_id=action_request.get("correlation_id"),
            )
        except Exception as exc:  # noqa: BLE001 - fire-and-forget must not crash
            logger.error("post-success event publish failed for %s: %s", event_type, exc)


# Module-level singleton consumed by the Automation Engine stub (Task 1.6)
# and wired into real executors from Phase 3 onward.
execution_engine = ExecutionEngine()
