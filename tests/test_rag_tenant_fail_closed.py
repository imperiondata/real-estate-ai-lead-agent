"""P0 SEC01/SEC03 — RAG and graph reads fail closed without a tenant. No live DB."""
import asyncio
import inspect
from pathlib import Path

import numpy as np

import rag
from app.clients.graph_client import GraphClient
from app.knowledge_graph.neo4j_kg import KnowledgeGraph

REPO = Path(__file__).resolve().parent.parent


class BoomDb:
    def query(self, *a, **k):
        raise AssertionError("query")

    def add(self, obj):
        raise AssertionError("add")

    def commit(self):
        raise AssertionError("commit")


class BoomIndex:
    def search(self, *a, **k):
        raise AssertionError("search")


class BoomGraph:
    available = True

    def get_similar_leads(self, *a, **k):
        raise AssertionError("graph")

    def get_assigned_agent(self, *a, **k):
        raise AssertionError("graph")


class BoomNeo4j:
    available = True

    def run(self, *a, **k):
        raise AssertionError("cypher")


def test_retrieve_missing_client_does_not_search(monkeypatch):
    monkeypatch.setattr(rag, "index", BoomIndex())
    monkeypatch.setattr(rag, "RAG_AVAILABLE", True)
    monkeypatch.setattr(rag, "data", [{"shared": True, "location": "Baner"}])
    assert rag.retrieve("wakad", 1, None) == ([], 0.0)
    assert rag.retrieve("wakad", 1, "") == ([], 0.0)


def test_retrieve_keeps_shared_drops_foreign(monkeypatch):
    items = [
        {"client_id": 9, "location": "Baner"},
        {"shared": True, "location": "Wakad"},
    ]
    seen = {}

    class Idx:
        def search(self, emb, k):
            seen["k"] = k
            return np.array([[0.1, 0.2]]), np.array([[0, 1]])

    monkeypatch.setattr(rag, "index", Idx())
    monkeypatch.setattr(rag, "RAG_AVAILABLE", True)
    monkeypatch.setattr(rag, "data", items)
    monkeypatch.setattr(rag, "get_query_embedding_cached", lambda q: [0.0])
    results, score = rag.retrieve("q", 1, 3)
    assert results == [items[1]]
    assert score == 0.2
    assert seen["k"] == 2


def test_mark_platform_faq_stamps_untagged_only():
    rows = [{"location": "Baner"}, {"location": "Wakad", "client_id": 4}]
    rag._mark_platform_faq(rows)
    assert rows[0]["shared"] is True
    assert "shared" not in rows[1]


def test_no_tenant_one_default():
    agent_src = (REPO / "agent.py").read_text(encoding="utf-8")
    wa_src = (REPO / "app" / "agents" / "whatsapp_agent.py").read_text(encoding="utf-8")
    assert "client_id: int = 1" not in agent_src
    assert "client_id: int = 1" not in wa_src
    assert "lead.client_id if lead else None" not in agent_src


def test_process_chat_missing_client_does_not_query():
    from agent import log_event_async, process_chat

    assert asyncio.run(process_chat("s", "hi", BoomDb(), client_id=None)) == ""
    assert asyncio.run(log_event_async("s", "message_sent", client_id=None)) is None


def test_whatsapp_missing_client_does_not_qualify():
    from app.agents.whatsapp_agent import WhatsAppAgent

    assert asyncio.run(WhatsAppAgent().process_chat("s", "hi", BoomDb(), client_id=None)) == ""


def test_graph_missing_client_does_not_query():
    assert GraphClient(BoomGraph()).get_lead_context(1, None) == {}
    kg = KnowledgeGraph(BoomNeo4j())
    assert kg.get_similar_leads(1, None) == []
    assert kg.get_assigned_agent(1, "") is None
    kg.upsert_lead(1, None, {"location": "Baner"})
    kg.link_lead_agent(1, "A", None)


def test_process_chat_checks_owner_before_write():
    from agent import process_chat

    src = inspect.getsource(process_chat)
    assert "tenant mismatch" in src
    assert "_owned" in src
