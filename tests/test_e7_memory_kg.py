"""Expansion Phase 7 — Neo4j KG + Memory (Tasks 7.1–7.7).

Tracks Step 16 (Expansion Phase 7). Exercises the fail-safe KnowledgeGraph
(no-op when Neo4j is unconfigured) and the persistent ConversationMemory layer.

See plans/IREIOS_3.0_EXPANSION_CHANGELOG.md (Phase 7 status).
"""
from app.knowledge_graph.neo4j_kg import KnowledgeGraph, knowledge_graph
from app.memory.conversation_memory import ConversationMemory, conversation_memory
from models import Lead, LeadMemory, Session


def _clean(db, sid):
    db.query(LeadMemory).filter(LeadMemory.session_id == sid).delete()
    db.query(Lead).filter(Lead.session_id == sid).delete()
    db.query(Session).filter(Session.id == sid).delete()
    db.commit()


def test_kg_unavailable_is_safe():
    from app.knowledge_graph.neo4j_client import Neo4jClient

    c = Neo4jClient.__new__(Neo4jClient)
    c._driver = None
    c.available = False
    kg = KnowledgeGraph(client=c)
    assert kg.available is False
    kg.upsert_lead(1, 1, {"x": 1})
    kg.link_lead_agent(1, "A", 1)
    assert kg.get_similar_leads(1, 1) == []


def test_kg_module_singleton_type():
    assert isinstance(knowledge_graph, KnowledgeGraph)
    # available depends on local NEO4J_URI; either state is valid
    assert isinstance(knowledge_graph.available, bool)


def test_memory_remember_recall():
    mem = ConversationMemory()
    with __import__("database").SessionLocal() as db:
        _clean(db, "sess_mem_1")
        db.add(Session(id="sess_mem_1", client_id=1, status="active"))
        lead = Lead(session_id="sess_mem_1", client_id=1, name="M", location="Wakad")
        db.add(lead)
        db.commit()
        lead_id = lead.id
        mem.remember(db, lead_id=lead_id, client_id=1, key="budget", value="80L",
                     session_id="sess_mem_1", memory_type="fact")
        items = mem.recall(db, lead_id=lead_id, client_id=1, key="budget")
        assert len(items) == 1
        assert items[0].value == "80L"
        _clean(db, "sess_mem_1")


def test_memory_extract_from_lead():
    mem = ConversationMemory()
    with __import__("database").SessionLocal() as db:
        _clean(db, "sess_mem_2")
        db.add(Session(id="sess_mem_2", client_id=1, status="active"))
        lead = Lead(session_id="sess_mem_2", client_id=1, name="A", location="Wakad",
                    budget="80L", property_type="2BHK", intent="buy")
        db.add(lead)
        db.commit()
        lead_id = lead.id
        created = mem.extract_and_store(db, lead=lead, client_id=1, user_message="hi")
        assert len(created) == 5
        _clean(db, "sess_mem_2")
