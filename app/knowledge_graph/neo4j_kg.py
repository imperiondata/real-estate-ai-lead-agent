"""IREIOS 3.0 — Phase 7.1–7.4: Knowledge Graph (Neo4j).

`KnowledgeGraph` wraps Neo4j. When `NEO4J_URI` is empty (the default in this
repo until the Neo4j service is provisioned) the graph is **unavailable** and
every operation is a safe no-op returning an empty result — the rest of the
system must keep working without the KG.

This module does NOT hard-import the `neo4j` driver at module load; the driver
is imported lazily inside `_connect` so the backend boots and tests run even
when the driver is not installed. When Neo4j is configured but unreachable,
calls are caught and return empty (graceful degradation).

See plans/IREIOS_3.0_STEP_BY_STEP_EXPANSION.md (Phase 7) and
plans/IREIOS_3.0_EXPANSION_CHANGELOG.md.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from config import settings

logger = logging.getLogger("knowledge_graph")


class KnowledgeGraph:
    """Thin, fail-safe wrapper over a Neo4j lead/agent graph.

    Backed by the shared `neo4j_client` (Phase 7.2) so there is a single
    connection/driver. All ops are safe no-ops when Neo4j is unavailable.
    """

    def __init__(self, client=None) -> None:
        from app.knowledge_graph.neo4j_client import neo4j_client
        self._client = client or neo4j_client

    @property
    def available(self) -> bool:
        return bool(getattr(self._client, "available", False))

    def _run(self, cypher: str, params: dict) -> list:
        return self._client.run(cypher, **params)

    # ---- Public API (all safe when unavailable) ----

    def upsert_lead(self, lead_id: int, client_id: int, props: dict) -> None:
        self._run(
            "MERGE (l:Lead {lead_id:$lead_id, client_id:$client_id}) "
            "SET l += $props",
            {"lead_id": lead_id, "client_id": client_id, "props": props},
        )

    def link_lead_agent(self, lead_id: int, agent_name: str, client_id: int) -> None:
        self._run(
            "MATCH (l:Lead {lead_id:$lead_id, client_id:$client_id}) "
            "MERGE (a:Agent {name:$agent_name, client_id:$client_id}) "
            "MERGE (l)-[:ASSIGNED_TO]->(a)",
            {"lead_id": lead_id, "agent_name": agent_name, "client_id": client_id},
        )

    def get_similar_leads(self, lead_id: int, client_id: int, limit: int = 5) -> list:
        """Return leads sharing location (and optional property_type) with the given lead."""
        rows = self._run(
            "MATCH (l:Lead {lead_id:$lead_id, client_id:$client_id}) "
            "MATCH (o:Lead {client_id:$client_id}) "
            "WHERE o.lead_id <> $lead_id AND o.location IS NOT NULL "
            "AND o.location = l.location "
            "RETURN o.lead_id AS lead_id, o.location AS location, "
            "o.property_type AS property_type, o.lead_temperature AS lead_temperature "
            "LIMIT $limit",
            {"lead_id": lead_id, "client_id": client_id, "limit": limit},
        )
        return [dict(r) for r in rows]

    def get_assigned_agent(self, lead_id: int, client_id: int) -> Optional[str]:
        """Return assigned agent name from graph, or None."""
        rows = self._run(
            "MATCH (l:Lead {lead_id:$lead_id, client_id:$client_id})"
            "-[:ASSIGNED_TO]->(a:Agent) "
            "RETURN a.name AS name LIMIT 1",
            {"lead_id": lead_id, "client_id": client_id},
        )
        if not rows:
            return None
        return rows[0].get("name")

    def close(self) -> None:  # pragma: no cover
        self._client.close()


knowledge_graph = KnowledgeGraph()
