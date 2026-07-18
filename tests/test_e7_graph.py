"""Expansion Phase 7 — Neo4j Knowledge Graph infra (Tasks 7.1–7.5).

Full-parity coverage of the Neo4j client + schema migrate + event writers +
GraphClient. These run without a live Neo4j (unconfigured => graceful no-op),
which is the production-safe default path.

See plans/IREIOS_3.0_EXPANSION_CHANGELOG.md (Phase 7 status).
"""
import asyncio


def test_schema_statements_are_idempotent_ddl():
    from app.knowledge_graph.neo4j_client import SCHEMA_STATEMENTS
    assert SCHEMA_STATEMENTS
    for stmt in SCHEMA_STATEMENTS:
        assert "IF NOT EXISTS" in stmt


def test_migrate_noop_when_unavailable():
    from app.knowledge_graph.neo4j_client import Neo4jClient
    c = Neo4jClient.__new__(Neo4jClient)
    c._driver = None
    c.available = False
    out = c.migrate_schema()
    assert out["migrated"] is False
    assert out["reason"] == "unavailable"


def test_kg_ops_safe_when_unavailable():
    from app.knowledge_graph.neo4j_client import Neo4jClient
    from app.knowledge_graph.neo4j_kg import KnowledgeGraph
    c = Neo4jClient.__new__(Neo4jClient)
    c._driver = None
    c.available = False
    kg = KnowledgeGraph(client=c)
    assert kg.available is False
    # All ops are no-ops returning empty; must not raise.
    kg.upsert_lead(1, 1, {"name": "x"})
    kg.link_lead_agent(1, "Raj", 1)
    assert kg.get_similar_leads(1, 1) == []
    assert kg.get_assigned_agent(1, 1) is None


def test_graph_event_writer_noop_when_unavailable():
    from app.knowledge_graph.event_writers import graph_event_writer
    # No exception even though Neo4j is unavailable.
    asyncio.run(graph_event_writer({
        "event_type": "lead.created", "tenant_id": "Client_1",
        "entity_id": "1", "payload": {"lead_id": 1, "name": "x"},
    }))


def test_resolve_client_id_helper():
    from app.knowledge_graph.event_writers import _resolve_client_id
    assert _resolve_client_id("Client_5") == 5
    assert _resolve_client_id("7") == 7
    assert _resolve_client_id("bogus") is None
    assert _resolve_client_id(None) is None
