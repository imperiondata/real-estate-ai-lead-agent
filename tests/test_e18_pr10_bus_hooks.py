"""PR #10 review — bus lifecycle hooks for n8n (lead.hot dual-publish, session.completed, EE calendar)."""
from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from tests.conftest import ensure_test_client


def test_is_hot_threshold_rule():
    from app.events.lead_hot import is_hot

    assert is_hot(conversion_probability=82) is True
    assert is_hot(conversion_probability=81) is False
    assert is_hot(conversion_probability=40, lead_temperature="hot") is True
    assert is_hot(conversion_probability=40, lead_temperature="warm") is False


def test_publish_lead_hot_dual_publishes_alias(monkeypatch):
    """Catalog lead.hot + PR#10 alias lead.escalated share the same payload shape."""
    from app.events import lead_hot as mod

    published = []

    async def fake_pub(etype, tenant, entity, payload, source="system", correlation_id=None):
        published.append(etype)
        return "eid"

    class Bus:
        publish = staticmethod(fake_pub)

    monkeypatch.setattr("app.clients.event_bus_client.event_bus", Bus())

    async def allow(*a, **k):
        return True

    monkeypatch.setattr(mod, "_debounce_allow", allow)

    lead = SimpleNamespace(
        id=11, session_id="s", name="N", phone="P", location="Baner",
        budget=None, property_type=None, intent=None, lead_temperature="hot",
        conversion_probability=90, assigned_agent=None,
    )

    async def run():
        return await mod.publish_lead_hot(
            client_id=1, lead=lead, trigger="hot_threshold", reason="t", source="test"
        )

    assert asyncio.run(run()) is True
    assert "lead.hot" in published
    assert "lead.escalated" in published


def test_publish_lead_hot_debounce(monkeypatch):
    from app.events import lead_hot as mod

    published = []
    n = {"c": 0}

    async def fake_pub(*a, **k):
        published.append(a[0])
        return "eid"

    class Bus:
        publish = staticmethod(fake_pub)

    monkeypatch.setattr("app.clients.event_bus_client.event_bus", Bus())

    async def debounce(*a, **k):
        n["c"] += 1
        return n["c"] == 1

    monkeypatch.setattr(mod, "_debounce_allow", debounce)

    lead = SimpleNamespace(
        id=12, session_id="s", name="N", phone="P", location=None, budget=None,
        property_type=None, intent=None, lead_temperature="hot",
        conversion_probability=85, assigned_agent=None,
    )

    async def run():
        a = await mod.publish_lead_hot(client_id=1, lead=lead, trigger="hot_threshold", reason="1")
        b = await mod.publish_lead_hot(client_id=1, lead=lead, trigger="hot_threshold", reason="2")
        return a, b

    a, b = asyncio.run(run())
    assert a is True and b is False
    assert published.count("lead.hot") == 1


def test_scoring_handler_publishes_hot_and_escalated(monkeypatch):
    from app.agents import lead_scoring_handler as h

    published = []

    async def fake_pub(etype, tenant, entity, payload, source="system", correlation_id=None):
        published.append(etype)
        return "eid"

    class Bus:
        publish = staticmethod(fake_pub)

    monkeypatch.setattr(h, "event_bus", Bus())
    monkeypatch.setattr("app.clients.event_bus_client.event_bus", Bus())
    scores = {
        "conversion_probability": 88,
        "lead_temperature": "hot",
        "engagement_score": 70,
        "urgency_level": "high",
    }
    monkeypatch.setattr(h, "score_lead", lambda lead: scores)

    lead = SimpleNamespace(
        id=601, client_id=1, session_id="sess_601", name="H", phone="+91",
        location="Baner", budget="1cr", property_type="3BHK", intent="buy",
        lead_temperature="warm", conversion_probability=40, assigned_agent="A",
    )

    class _Q:
        def filter(self, *a, **k):
            return self

        def first(self):
            return lead

    class _DB:
        def query(self, *a, **k):
            return _Q()

        def commit(self):
            pass

        def refresh(self, obj):
            for k, v in scores.items():
                setattr(obj, k, v)

        def close(self):
            pass

    monkeypatch.setattr(h, "SessionLocal", lambda: _DB())

    async def allow(*a, **k):
        return True

    monkeypatch.setattr("app.events.lead_hot._debounce_allow", allow)

    async def run():
        await h.lead_scoring_handler({
            "tenant_id": "Client_1",
            "entity_id": "601",
            "payload": {"lead_id": 601, "session_id": "sess_601", "chat_context": "User: buy"},
        })

    asyncio.run(run())
    assert "lead.scored" in published
    assert "lead.hot" in published
    assert "lead.escalated" in published


def test_handoff_and_qualify_source_wire_bus():
    import agent as agent_mod

    src = inspect.getsource(agent_mod.process_chat)
    assert "publish_lead_hot" in src
    assert "human_handoff" in src
    assert "publish_session_completed" in src
    assert "fully_qualified" in src or "close_reason" in src


def test_session_completed_publish(monkeypatch):
    from app.events import lead_hot as mod

    published = []

    async def fake_pub(etype, tenant, entity, payload, source="system", correlation_id=None):
        published.append((etype, payload))
        return "eid"

    class Bus:
        publish = staticmethod(fake_pub)

    monkeypatch.setattr("app.clients.event_bus_client.event_bus", Bus())

    lead = SimpleNamespace(
        id=3, name="A", phone="1", location="X", budget="1", property_type="2BHK",
        intent="buy", lead_temperature="hot", conversion_probability=90,
        assigned_agent=None,
    )

    async def run():
        return await mod.publish_session_completed(
            client_id=1,
            lead=lead,
            session_id="1_s",
            close_reason="human_handoff",
            chat_context="User: agent please",
        )

    assert asyncio.run(run()) is True
    assert published[0][0] == "session.completed"
    assert published[0][1]["close_reason"] == "human_handoff"
    assert "agent" in published[0][1]["chat_context"]


def test_emit_turn_events_chat_context(monkeypatch):
    import main as main_mod
    from database import SessionLocal
    from models import Lead, Message, Session

    cid = ensure_test_client(1)
    sid = f"e18_pr10_{uuid4().hex[:8]}"
    published = []

    async def capture(etype, client_id, entity_id, payload=None, source="main"):
        published.append((etype, payload or {}))
        return "eid"

    monkeypatch.setattr(main_mod, "_publish_bus_event", capture)

    with SessionLocal() as db:
        db.add(Session(id=sid, client_id=cid, status="active"))
        lead = Lead(
            session_id=sid, client_id=cid, name="C", phone="+9191",
            location="Wakad", budget="50L", property_type="2BHK",
        )
        db.add(lead)
        db.add(Message(session_id=sid, client_id=cid, role="user", content="Need Baner flat"))
        db.commit()
        db.refresh(lead)
        lid = lead.id

        async def run():
            await main_mod._emit_turn_events(
                client_id=cid,
                scoped_session_id=sid,
                lead=lead,
                source_channel="chat",
                is_new_lead=False,
                message="hi",
                db=db,
            )

        try:
            asyncio.run(run())
        finally:
            db.query(Message).filter(Message.session_id == sid).delete()
            db.query(Lead).filter(Lead.id == lid).delete()
            db.query(Session).filter(Session.id == sid).delete()
            db.commit()

    conv = next(p for p in published if p[0] == "conversation.updated")
    assert "Baner" in (conv[1].get("chat_context") or "")


def test_ee_site_visit_merged_payload():
    from app.execution_engine.base_executor import BaseExecutor
    from app.execution_engine.execution_engine import ExecutionEngine

    published = []

    class FakeBus:
        async def publish(self, etype, tenant, entity, payload, source="ee", correlation_id=None):
            published.append((etype, payload))
            return "eid"

    class CalEx(BaseExecutor):
        action_type = "schedule_visit"

        async def execute(self, action_request):
            return {
                "status": "success",
                "visit_id": "visit_xyz",
                "provider": "stub",
                "visit_date": "2026-08-01T10:00:00Z",
            }

    ee = ExecutionEngine(session_factory=lambda: MagicMock(), bus=FakeBus())
    ee.register("schedule_visit", CalEx())
    ee.register_event("schedule_visit", "site_visit.scheduled")

    async def run():
        return await ee.dispatch({
            "action_type": "schedule_visit",
            "tenant_id": "Client_1",
            "entity_id": "77",
            "parameters": {"name": "John", "phone": "+91", "visit_date": "2026-08-01T10:00:00Z"},
        })

    res = asyncio.run(run())
    assert res["status"] == "success"
    assert published[0][0] == "site_visit.scheduled"
    assert published[0][1]["name"] == "John"
    assert published[0][1]["visit_id"] == "visit_xyz"
    assert published[0][1]["lead_id"] == 77


def test_calendar_executor_docstring_no_direct_publish():
    from app.execution_engine import calendar_executor as ce
    import inspect as insp

    src = insp.getsource(ce.CalendarExecutor.execute)
    assert "event_bus.publish" not in src
    assert "Execution Engine" in ce.__doc__ or "does **not** call" in ce.__doc__


def test_registry_maps_schedule_visit():
    from app.execution_engine.registry import register_executors
    from app.execution_engine.execution_engine import execution_engine

    register_executors()
    assert execution_engine._event_map.get("schedule_visit") == "site_visit.scheduled"
