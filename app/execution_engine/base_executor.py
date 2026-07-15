"""IREIOS 3.0 — Base executor for the Execution Engine.

An executor turns a concrete ``action_request`` (produced by an Agent's
``decide`` or by the Automation Engine) into an external side-effect, via the
Execution Engine only. Phase 1 only needs a ``NoopExecutor`` for tests; the
real Twilio/CRM/calendar executors land in Phase 3.

Runtime: ``Event -> CEO -> Agent/Workflow -> Automation Engine -> Execution Engine -> Event``.
"""
from __future__ import annotations

from typing import Any


class BaseExecutor:
    """Abstract executor. Subclasses implement ``execute``.

    ``action_type`` is the registry key the Execution Engine uses to dispatch a
    request. Subclasses should set it explicitly.
    """

    action_type: str = ""

    async def execute(self, action_request: dict) -> dict:
        """Run the action and return a result envelope.

        Convention: return ``{"status": "success", ...}`` on success or
        ``{"status": "error", "error": <str>, ...}`` on failure. Raising is
        also acceptable — the Execution Engine captures it as an error result
        and writes a DLQ row.
        """
        raise NotImplementedError


class NoopExecutor(BaseExecutor):
    """Test / placeholder executor — succeeds without side effects."""

    action_type = "noop"

    async def execute(self, action_request: dict) -> dict:
        return {
            "status": "success",
            "action_type": self.action_type,
            "result": "noop",
            "request": action_request,
        }
