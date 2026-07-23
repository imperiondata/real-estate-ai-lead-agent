"""Automations closeout BA-1…BA-5 — lead.hot, chat_context, EE merge, HITL paths, calendar API.

See plans/PHASE3_AUTOMATIONS_CLOSEOUT.md.
"""
from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from tests.conftest import ensure_test_client


# --------------------------------------------------------------------------- #
# BA-1 — lead.hot helpers + scoring publish
# --------------------------------------------------------------------------- #
def test_is_hot_threshold_rule():
    """HOT when conversion_probability >= 82 OR lead_temperature == hot."""
    from app.events.lead_hot import is_hot

    assert is_hot(conversion_probability=82) is True
    assert is_hot(conversion_probability=81) is False
    assert is_hot(conversion_probability=50, lead_temperature="hot") is True
    assert is_hot(conversion_probability=50, lead_temperature="HOT") is True
    assert is_hot(conversion_probability=50, lead_temperature="warm") is False


def test_build_lead_hot_payload_trigger_fields():
    from app.events.lead_hot import build_lead_hot_payload

    lead = SimpleNamespace(
        id=42,
        session_id="1_+91",
        name="Ada",
        phone="+9199",
        location="Baner",
        budget="80L",
        property_type="2BHK",
        intent="buy",
        lead_temperature="hot",
        conversion_probability=90,
        assigned_agent="Sneha",
    )
    p = build_lead_hot_payload(
        lead, trigger="hot_threshold", reason="crossed", chat_context="User: hi"
    )
    assert p["trigger"] == "hot_threshold"
    assert p["score"] == 90
    assert p["chat_context"] == "User: hi"
    assert p["lead_id"] == 42


def test_publish_lead_hot_calls_bus(monkeypatch):
    from app.events import lead_hot as mod

    published = []

    async def fake_pub(etype, tenant, entity, payload, source="system", correlation_id=None):
        published.append((etype, tenant, entity, payload, source))
        return "eid"

    class Bus:
        _running = True
        publish = staticmethod(fake_pub)

    monkeypatch.setattr("app.clients.event_bus_client.event_bus", Bus())

    async def allow(*a, **k):
        return True

    monkeypatch.setattr(mod, "_debounce_allow", allow)

    lead = SimpleNamespace(
        id=7, session_id="s", name="N", phone="P", location=None, budget=None,
        property_type=None, intent=None, lead_temperature="hot",
        conversion_probability=85, assigned_agent=None,
    )

    async def run():
        return await mod.publish_lead_hot(
            client_id=1, lead=lead, trigger="hot_threshold", reason="t", source="test"
        )

    ok = asyncio.run(run())
    assert ok is True
    assert len(published) == 1
    assert published[0][0] == "lead.hot"
    assert published[0][1] == "Client_1"
    assert published[0][3]["trigger"] == "hot_threshold"


def test_publish_lead_hot_debounce_skips_second(monkeypatch):
    from app.events import lead_hot as mod

    published = []
    calls = {"n": 0}

    async def fake_pub(*a, **k):
        published.append(a)
        return "eid"

    class Bus:
        _running = True
        publish = staticmethod(fake_pub)

    monkeypatch.setattr("app.clients.event_bus_client.event_bus", Bus())

    async def debounce(client_id, lead_id, trigger):
        calls["n"] += 1
        return calls["n"] == 1  # first only

    monkeypatch.setattr(mod, "_debounce_allow", debounce)

    lead = SimpleNamespace(
        id=9, session_id="s", name="N", phone="P", location=None, budget=None,
        property_type=None, intent=None, lead_temperature="hot",
        conversion_probability=90, assigned_agent=None,
    )

    async def run():
        a = await mod.publish_lead_hot(
            client_id=1, lead=lead, trigger="hot_threshold", reason="1"
        )
        b = await mod.publish_lead_hot(
            client_id=1, lead=lead, trigger="hot_threshold", reason="2"
        )
        return a, b

    a, b = asyncio.run(run())
    assert a is True and b is False
    assert len(published) == 1


def test_lead_scoring_handler_publishes_lead_hot(monkeypatch):
    """When score_lead returns hot scores, handler publishes lead.hot."""
    from app.agents import lead_scoring_handler as h

    published = []

    async def fake_pub(etype, tenant, entity, payload, source="system", correlation_id=None):
        published.append((etype, payload, source))
        return "eid"

    class Bus:
        _running = True
        publish = staticmethod(fake_pub)

    monkeypatch.setattr(h, "event_bus", Bus())
    monkeypatch.setattr(
        "app.clients.event_bus_client.event_bus",
        Bus(),
    )

    scores = {
        "conversion_probability": 88,
        "lead_temperature": "hot",
        "engagement_score": 70,
        "urgency_level": "high",
    }
    monkeypatch.setattr(h, "score_lead", lambda lead: scores)

    lead = SimpleNamespace(
        id=501,
        client_id=1,
        session_id="sess_hot_501",
        name="Hot",
        phone="+91",
        location="Baner",
        budget="1cr",
        property_type="3BHK",
        intent="buy",
        lead_temperature="warm",
        conversion_probability=40,
        assigned_agent="A",
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
            "entity_id": "501",
            "payload": {
                "lead_id": 501,
                "session_id": "sess_hot_501",
                "chat_context": "User: buy now",
            },
        })

    asyncio.run(run())
    types = [p[0] for p in published]
    assert "lead.scored" in types
    assert "lead.hot" in types
    hot = next(p for p in published if p[0] == "lead.hot")
    assert hot[1]["trigger"] == "hot_threshold"
    assert hot[1]["chat_context"] == "User: buy now"


def test_agent_handoff_source_publishes_human_handoff():
    """Handoff intercept source must call publish_lead_hot with human_handoff."""
    import agent as agent_mod

    src = inspect.getsource(agent_mod.process_chat)
    assert "publish_lead_hot" in src
    assert "human_handoff" in src
    assert "HUMAN HANDOFF" in src


# --------------------------------------------------------------------------- #
# BA-2 — chat_context on turn events
# --------------------------------------------------------------------------- #
def test_emit_turn_events_includes_chat_context(monkeypatch):
    import main as main_mod
    from database import SessionLocal
    from models import Lead, Message, Session

    cid = ensure_test_client(1)
    sid = f"e18_ctx_{uuid4().hex[:8]}"
    published = []

    async def capture(etype, client_id, entity_id, payload=None, source="main"):
        published.append((etype, payload or {}))
        return "eid"

    monkeypatch.setattr(main_mod, "_publish_bus_event", capture)

    with SessionLocal() as db:
        db.add(Session(id=sid, client_id=cid, status="active"))
        lead = Lead(
            session_id=sid,
            client_id=cid,
            name="Ctx",
            phone="+919111111111",
            location="Wakad",
            budget="50L",
            property_type="2BHK",
        )
        db.add(lead)
        db.add(Message(session_id=sid, client_id=cid, role="user", content="Looking in Baner"))
        db.add(Message(session_id=sid, client_id=cid, role="assistant", content="Budget?"))
        db.commit()
        db.refresh(lead)
        lead_id = lead.id

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
            db.query(Lead).filter(Lead.id == lead_id).delete()
            db.query(Session).filter(Session.id == sid).delete()
            db.commit()

    assert published
    conv = next(p for p in published if p[0] == "conversation.updated")
    assert "chat_context" in conv[1]
    assert "Baner" in (conv[1].get("chat_context") or "")


def test_emit_turn_events_empty_chat_context_without_db(monkeypatch):
    import main as main_mod

    published = []

    async def capture(etype, client_id, entity_id, payload=None, source="main"):
        published.append(payload or {})
        return "eid"

    monkeypatch.setattr(main_mod, "_publish_bus_event", capture)

    lead = SimpleNamespace(
        id=1, name="A", phone="1", location=None, budget=None,
        property_type=None, intent=None, lead_temperature=None,
        conversion_probability=None, budget_alignment_status=None,
        visit_date=None,
    )

    async def run():
        await main_mod._emit_turn_events(
            client_id=1,
            scoped_session_id="s",
            lead=lead,
            source_channel="chat",
            is_new_lead=False,
            message="x",
            db=None,
        )

    asyncio.run(run())
    assert published
    assert published[0].get("chat_context") == ""


# --------------------------------------------------------------------------- #
# BA-3 — EE success payload merge
# --------------------------------------------------------------------------- #
def test_ee_publish_success_merges_parameters():
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
                "visit_id": "visit_abc",
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
            "entity_id": "99",
            "parameters": {
                "name": "John",
                "phone": "+9199",
                "location": "Baner",
                "visit_date": "2026-08-01T10:00:00Z",
            },
        })

    res = asyncio.run(run())
    assert res["status"] == "success"
    assert published
    etype, payload = published[0]
    assert etype == "site_visit.scheduled"
    assert payload["name"] == "John"
    assert payload["phone"] == "+9199"
    assert payload["visit_id"] == "visit_abc"
    assert payload["lead_id"] == 99
    assert payload["provider"] == "stub"


# --------------------------------------------------------------------------- #
# BA-4 — HITL deep-link paths
# --------------------------------------------------------------------------- #
def test_request_approval_payload_has_paths(monkeypatch):
    from app.automation_engine import hitl as hitl_mod
    from database import SessionLocal
    from models import ApprovalRequest

    published = []

    async def fake_pub(etype, tenant, entity, payload, source="hitl", correlation_id=None):
        published.append((etype, payload))
        return "eid"

    class Bus:
        _running = True

        async def publish(self, *a, **k):
            return await fake_pub(*a, **k)

    monkeypatch.setattr(hitl_mod, "event_bus", Bus())
    ensure_test_client(1)
    entity = f"e18_hitl_{uuid4().hex[:8]}"

    try:
        async def run():
            return await hitl_mod.request_approval(
                {
                    "action_type": "send_whatsapp",
                    "tenant_id": "Client_1",
                    "entity_id": entity,
                    "parameters": {"message": "offer"},
                },
                tenant_id="Client_1",
                entity_id=entity,
            )

        res = asyncio.run(run())
        assert res["status"] == "pending"
        assert published
        assert published[0][0] == "approval.requested"
        p = published[0][1]
        assert p["approve_path"] == f"/api/v1/approvals/{res['id']}/approve"
        assert p["reject_path"] == f"/api/v1/approvals/{res['id']}/reject"
        assert "parameters_summary" in p
    finally:
        with SessionLocal() as db:
            db.query(ApprovalRequest).filter(
                ApprovalRequest.entity_id == entity
            ).delete(synchronize_session=False)
            db.commit()


# --------------------------------------------------------------------------- #
# BA-5 — calendar API
# --------------------------------------------------------------------------- #
def test_calendar_availability_stub_labeled(monkeypatch):
    from config import settings
    from fastapi.testclient import TestClient

    monkeypatch.setattr(settings, "GOOGLE_CALENDAR_ID", "")
    monkeypatch.setattr(settings, "GOOGLE_CALENDAR_CREDENTIALS_JSON", "")

    # Import app routes without full lifespan if possible
    from app.api.calendar import router
    from fastapi import FastAPI
    from auth import get_client_by_api_key
    from models import Client

    app = FastAPI()
    app.include_router(router)

    fake = Client(id=1, company_name="T", email="t@t.com", api_key="k", is_active=True)

    async def _client():
        return fake

    app.dependency_overrides[get_client_by_api_key] = lambda: fake
    client = TestClient(app)
    r = client.get("/api/v1/calendar/availability?date=2026-08-01")
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "stub"
    assert body["available"] is True
    assert "slots" in body
    assert body.get("note")


def test_calendar_confirm_calls_ae(monkeypatch):
    from app.api import calendar as cal_mod
    from database import SessionLocal
    from models import Lead, Session
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from auth import get_client_by_api_key
    from models import Client

    cid = ensure_test_client(1)
    sid = f"e18_cal_{uuid4().hex[:8]}"
    ae_calls = []

    async def fake_submit(action):
        ae_calls.append(action)
        return {"status": "success", "visit_id": "visit_test"}

    monkeypatch.setattr("app.automation_engine.engine.submit", fake_submit)

    app = FastAPI()
    app.include_router(cal_mod.router)
    fake_client = Client(id=cid, company_name="T", email="t@t.com", api_key="k", is_active=True)
    app.dependency_overrides[get_client_by_api_key] = lambda: fake_client

    with SessionLocal() as db:
        db.add(Session(id=sid, client_id=cid, status="active"))
        lead = Lead(session_id=sid, client_id=cid, name="Cal", phone="+91", location="Baner")
        db.add(lead)
        db.commit()
        db.refresh(lead)
        lead_id = lead.id

    try:
        client = TestClient(app)
        r = client.post(
            "/api/v1/calendar/confirm",
            json={"lead_id": lead_id, "visit_date": "2026-08-05T11:00:00+05:30"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "success"
        assert body["lead_id"] == lead_id
        assert ae_calls
        assert ae_calls[0]["action_type"] == "schedule_visit"
        assert ae_calls[0]["parameters"]["visit_date"] == "2026-08-05T11:00:00+05:30"
    finally:
        with SessionLocal() as db:
            db.query(Lead).filter(Lead.id == lead_id).delete()
            db.query(Session).filter(Session.id == sid).delete()
            db.commit()


def test_calendar_router_mounted_in_main():
    import main as main_mod

    paths = list(main_mod.app.openapi().get("paths", {}).keys())
    assert "/api/v1/calendar/availability" in paths
    assert "/api/v1/calendar/confirm" in paths


def test_no_invented_event_types_in_closeout_modules():
    """Guard: closeout code must not introduce rejected event names."""
    from pathlib import Path

    roots = [
        Path("app/events/lead_hot.py"),
        Path("app/agents/lead_scoring_handler.py"),
        Path("app/api/calendar.py"),
    ]
    banned = ("human.requested", "lead.escalated", "session.completed")
    for path in roots:
        text = path.read_text(encoding="utf-8")
        for b in banned:
            assert b not in text, f"{b} found in {path}"
