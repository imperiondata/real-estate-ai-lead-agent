"""IREIOS 3.0 — Phase 2 LangGraph runner scaffold.

A minimal, serializable state-graph runner that can pause at a HITL
checkpoint and resume. Used by the Automation Engine when an action carries
``template_type="langgraph"`` (and later for multi-step agent plans).

The graph shape is intentionally small (``plan -> (checkpoint) -> execute``)
and the state dict is JSON-serializable so it can be persisted across the
approval pause. If ``langgraph`` is not installed, the import is guarded and
the module degrades to a simple linear executor so CI/tests never fail on a
missing optional dependency.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger("langgraph_runner")

try:  # pragma: no cover - exercised only when langgraph is installed
    from langgraph.graph import StateGraph, END  # type: ignore

    _HAS_LANGGRAPH = True
except Exception:  # noqa: BLE001
    _HAS_LANGGRAPH = False
    StateGraph = None  # type: ignore
    END = "__end__"  # type: ignore

# State keys persisted across a HITL pause.
STATE_VERSION = 1


def _default_plan(state: dict) -> dict:
    """Plan step: copy the action request into the persisted graph state."""
    action = state.get("action_request", {})
    return {
        **state,
        "plan": {
            "action_type": action.get("action_type"),
            "parameters": action.get("parameters", {}),
        },
        "needs_approval": bool(action.get("requires_approval")),
    }


def _default_execute(state: dict) -> dict:
    """Execute step: mark the state ready for the Execution Engine."""
    state = dict(state)
    state["ready_to_execute"] = True
    return state


def build_graph() -> Any:
    """Construct the LangGraph state graph (plan -> checkpoint -> execute)."""
    if not _HAS_LANGGRAPH:
        raise RuntimeError("langgraph is not installed; cannot build graph")
    g = StateGraph(dict)
    g.add_node("plan", _default_plan)
    g.add_node("execute", _default_execute)
    g.add_edge("plan", "execute")
    g.add_edge("execute", END)
    return g.compile()


def run_graph(action_request: dict) -> dict:
    """Run the graph to completion (no HITL pause inside this call).

    Returns the final state dict. If langgraph is unavailable, falls back to a
    pure-Python linear execution of the same steps so callers get a result.
    """
    state = {"action_request": action_request, "version": STATE_VERSION}
    if _HAS_LANGGRAPH:
        try:
            app = build_graph()
            return app.invoke(state)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001 - fall back on any graph error
            logger.warning("langgraph run failed, using linear fallback: %s", exc)
    # Linear fallback (also the default when the lib is absent).
    state = _default_plan(state)
    state = _default_execute(state)
    return state


def resume_graph(state: dict, approval_decision: str) -> dict:
    """Resume a persisted graph state after a manager decision.

    ``approval_decision`` is ``"approve"`` or ``"reject"``. On approve the
    state is returned ready-to-execute; on reject it is marked terminal. The
    returned state is JSON-serializable (``json.dumps`` safe).
    """
    state = dict(state)
    state["approval_decision"] = approval_decision
    if approval_decision == "approve":
        state = _default_execute(state)
    else:
        state["rejected"] = True
    # Ensure serializability for persistence.
    json.dumps(state, default=str)
    return state


def serialize_state(state: dict) -> str:
    return json.dumps(state, default=str)


def deserialize_state(raw: str) -> dict:
    return json.loads(raw)
