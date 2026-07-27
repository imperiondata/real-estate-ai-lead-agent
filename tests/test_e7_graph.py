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


def test_graph_events_include_conversation_updated():
    from app.knowledge_graph.event_writers import GRAPH_EVENTS

    assert "conversation.updated" in GRAPH_EVENTS
    assert "lead.scored" in GRAPH_EVENTS


def test_hydrate_lead_props_pg_wins_over_sparse_scored_payload(monkeypatch):
    """Wakad→Baner: sparse lead.scored must not leave stale location in Neo4j."""
    from types import SimpleNamespace
    from app.knowledge_graph import event_writers as ew

    class _Q:
        def filter(self, *a, **k):
            return self

        def first(self):
            return SimpleNamespace(
                name="Maitri",
                location="Baner",
                property_type="2BHK",
                lead_temperature="warm",
                conversion_probability=55,
                intent="buy",
            )

    class _Db:
        def query(self, *a, **k):
            return _Q()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("database.SessionLocal", lambda: _Db())
    # Import path used inside hydrate
    import database as database_mod
    monkeypatch.setattr(database_mod, "SessionLocal", lambda: _Db())

    props = ew._hydrate_lead_props(
        lead_id=1,
        client_id=1,
        payload={
            "lead_id": 1,
            "lead_temperature": "hot",
            "conversion_probability": 80,
            # deliberately no location — old bug left Wakad on the node
        },
    )
    assert props["location"] == "Baner"
    assert props["name"] == "Maitri"
    assert props["property_type"] == "2BHK"
    # PG overwrites sparse/stale score keys when present
    assert props["conversion_probability"] == 55
    assert props["lead_temperature"] == "warm"


def test_hydrate_falls_back_to_payload_when_pg_empty(monkeypatch):
    from app.knowledge_graph import event_writers as ew

    class _Q:
        def filter(self, *a, **k):
            return self

        def first(self):
            return None

    class _Db:
        def query(self, *a, **k):
            return _Q()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    import database as database_mod
    monkeypatch.setattr(database_mod, "SessionLocal", lambda: _Db())

    props = ew._hydrate_lead_props(
        9,
        1,
        {"name": "FromPayload", "location": "Wakad", "lead_temperature": "cold"},
    )
    assert props == {
        "name": "FromPayload",
        "location": "Wakad",
        "lead_temperature": "cold",
    }


def test_graph_event_writer_scored_upserts_hydrated_location(monkeypatch):
    from app.knowledge_graph import event_writers as ew

    calls = []

    class _KG:
        available = True

        def upsert_lead(self, lead_id, client_id, props):
            calls.append((lead_id, client_id, props))

    monkeypatch.setattr(ew, "knowledge_graph", _KG())
    monkeypatch.setattr(
        ew,
        "_hydrate_lead_props",
        lambda lead_id, client_id, payload: {
            "name": "Maitri",
            "location": "Baner",
            "property_type": "2BHK",
            "lead_temperature": "warm",
        },
    )

    asyncio.run(
        ew.graph_event_writer(
            {
                "event_type": "lead.scored",
                "tenant_id": "Client_2",
                "entity_id": "42",
                "payload": {"lead_id": 42, "lead_temperature": "hot"},
            }
        )
    )
    assert len(calls) == 1
    lead_id, client_id, props = calls[0]
    assert lead_id == 42
    assert client_id == 2
    assert props["location"] == "Baner"
    assert "name" in props


def test_graph_event_writer_conversation_updated_upserts(monkeypatch):
    from app.knowledge_graph import event_writers as ew

    calls = []

    class _KG:
        available = True

        def upsert_lead(self, lead_id, client_id, props):
            calls.append(props)

    monkeypatch.setattr(ew, "knowledge_graph", _KG())
    monkeypatch.setattr(
        ew,
        "_hydrate_lead_props",
        lambda *a, **k: {"location": "Baner", "name": "Maitri"},
    )

    asyncio.run(
        ew.graph_event_writer(
            {
                "event_type": "conversation.updated",
                "tenant_id": "Client_1",
                "entity_id": "7",
                "payload": {"lead_id": 7, "location": "Baner"},
            }
        )
    )
    assert calls and calls[0]["location"] == "Baner"


def test_whatsapp_agent_post_turn_snapshot_includes_location(monkeypatch):
    from types import SimpleNamespace
    from app.agents.whatsapp_agent import WhatsAppAgent

    calls = []

    class _KG:
        available = True

        def upsert_lead(self, lead_id, client_id, props):
            calls.append((lead_id, client_id, props))

    import app.knowledge_graph.neo4j_kg as kg_mod
    monkeypatch.setattr(kg_mod, "knowledge_graph", _KG())

    agent = WhatsAppAgent()
    lead = SimpleNamespace(
        id=11,
        name="Maitri",
        location="Baner",
        property_type="2BHK",
        lead_temperature="cold",
        intent="buy",
        conversion_probability=40,
    )
    agent._upsert_lead_snapshot(lead, client_id=1)
    assert len(calls) == 1
    assert calls[0][2]["location"] == "Baner"
    assert calls[0][2]["name"] == "Maitri"
