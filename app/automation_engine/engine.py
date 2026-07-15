"""IREIOS 3.0 — Automation Engine (Phase 1 stub).

Phase 1: ``submit`` is a thin forwarder to the Execution Engine so agents can
produce side-effects without the full approval/retry machinery. Phase 2
replaces this body with: validate request, HITL pause when
``requires_approval`` is set, else ``_execute_with_retry`` -> EE. ``BaseAgent``
and callers must not change when that lands.
"""
from __future__ import annotations

from typing import Any

from app.execution_engine.execution_engine import execution_engine


async def submit(action_request: dict) -> dict:
    """Phase 1: forward directly to the Execution Engine."""
    return await execution_engine.dispatch(action_request)
