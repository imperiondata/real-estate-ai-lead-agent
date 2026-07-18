"""IREIOS 3.0 — Phase 7.5: GraphClient for agents.

Read-only convenience wrapper agents use to fetch graph context for a lead.
Postgres remains the source of truth: when Neo4j is unavailable this returns
`{}` and logs — it never raises and never blocks the chat path.

Used on the WhatsApp reply path (BD-5) so similar-lead micro-market signals
can influence the LLM without inventing other buyers' private data.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.knowledge_graph.neo4j_kg import knowledge_graph

logger = logging.getLogger("graph_client")


def format_graph_context_for_llm(ctx: dict) -> str:
    """Turn graph context into a short LLM-safe instruction block (no PII dump)."""
    if not ctx:
        return ""
    parts: list[str] = []
    similar = ctx.get("similar_leads") or []
    if similar:
        n = len(similar)
        locs = sorted({str(s.get("location")) for s in similar if s.get("location")})
        pts = sorted({str(s.get("property_type")) for s in similar if s.get("property_type")})
        bit = f"{n} similar prior lead(s) in graph"
        if locs:
            bit += f" near {', '.join(locs[:3])}"
        if pts:
            bit += f" ({', '.join(pts[:3])})"
        parts.append(bit + ".")
        parts.append(
            "Use this only as micro-market confidence (demand exists here). "
            "Do NOT invent other buyers' names, phones, or private details."
        )
    agent = ctx.get("assigned_agent")
    if agent:
        parts.append(f"Graph assignment: {agent}.")
    return " ".join(parts).strip()


class GraphClient:
    """Agent-facing graph reads with graceful degradation."""

    def __init__(self, kg=None) -> None:
        self._kg = kg or knowledge_graph

    @property
    def available(self) -> bool:
        return bool(getattr(self._kg, "available", False))

    def get_lead_context(self, lead_id: int, client_id: int, limit: int = 5) -> dict:
        """Return graph context for a lead, or `{}` when down."""
        if not self.available:
            return {}
        try:
            similar = self._kg.get_similar_leads(lead_id, client_id, limit=limit)
            assigned = None
            if hasattr(self._kg, "get_assigned_agent"):
                assigned = self._kg.get_assigned_agent(lead_id, client_id)
            out: dict[str, Any] = {"similar_leads": similar}
            if assigned:
                out["assigned_agent"] = assigned
            return out
        except Exception as e:  # noqa: BLE001 - never break the caller
            logger.warning("graph_client.get_lead_context degraded: %s", e)
            return {}


graph_client = GraphClient()
