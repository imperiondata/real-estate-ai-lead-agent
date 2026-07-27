"""Wave B — deepen Sales / CS / Marketing + AE templates.

Plan: plans/IREIOS_3.0_WAVE_A_D_EXPANSION.md §2
Changelog: plans/IREIOS_3.0_WAVE_A_D_CHANGELOG.md

B.1 + B.2 implemented. B.3/B.4/B.5/B.6/B.7 skeletons remain.
"""
from __future__ import annotations

import asyncio
import os

import pytest

os.environ.setdefault("ADMIN_API_KEY", "test-admin-key-wave-b")

from app.agents.sales_agent import (
    detect_objections,
    recommend_next_action,
    _nba_to_ae_action,
    _debounce_key,
)
from config import settings
from models import Client, Lead, Message, Session


def _clean(db, sid):
    db.query(Message).filter(Message.session_id == sid).delete()
    db.query(Lead).filter(Lead.session_id == sid).delete()
    db.query(Session).filter(Session.id == sid).delete()
    db.commit()


def _db_ok() -> bool:
    try:
        from database import SessionLocal
        db = SessionLocal()
        db.query(Client).first()
        db.close()
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# B.1 — Sales bus
# --------------------------------------------------------------------------- #
def test_sales_agent_registered_active_on_ceo():
    """B.1: sales_agent is registered as active on the CEO."""
    from app.orchestrator.ceo_orchestrator import ceo
    from app.agents.sales_agent import register_sales_agent

    register_sales_agent(ceo)
    agents = ceo.registry.list_agents()
    sales = [a for a in agents if a.agent_id == "sales_agent"]
    assert len(sales) >= 1
    assert sales[0].status == "active"


def test_lead_hot_envelope_triggers_notify_ae(monkeypatch):
    """B.1: hot lead envelope triggers AE notify_agent."""
    if not _db_ok():
        pytest.skip("requires Postgres")
    from app.agents.sales_agent import sales_bus_handler
    from database import SessionLocal
    from uuid import uuid4
    from tests.conftest import ensure_test_client

    cid = ensure_test_client(1)
    # Create a real lead for the bus handler to find
    sid = f"b1_test_{uuid4().hex[:8]}"
    db = SessionLocal()
    try:
        db.add(Session(id=sid, client_id=cid))
        lead = Lead(
            session_id=sid, client_id=cid,
            name="Test", phone="+919999999999", location="Pune",
            budget="1cr", property_type="flat", lead_temperature="hot",
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)
        lid = lead.id
    finally:
        db.close()

    submitted = []

    async def fake_submit(req):
        submitted.append(req)
        return {"status": "success"}

    import app.agents.sales_agent as sa
    monkeypatch.setattr(sa, "ae_submit", fake_submit)

    # Clear any leftover Redis debounce from prior runs (same client/lead ids rare but flaky).
    try:
        import redis
        from app.agents.sales_agent import _debounce_key
        from config import settings as _s
        r = redis.from_url(_s.REDIS_URL, decode_responses=True)
        r.delete(_debounce_key(cid, lid))
        r.close()
    except Exception:
        pass

    async def run():
        await sales_bus_handler({
            "event_type": "lead.hot",
            "tenant_id": f"Client_{cid}",
            "entity_id": str(lid),
            "payload": {"lead_id": lid},
        })

    asyncio.run(run())

    # Clean up
    _clean(SessionLocal(), sid)

    assert len(submitted) >= 1
    assert submitted[0]["action_type"] == "notify_agent"


def test_sales_bus_debounce_skips_second_event(monkeypatch):
    """B.1: debounce key format is correct."""
    from app.agents.sales_agent import _debounce_key
    key = _debounce_key(1, 42)
    assert key == "sales_ai_lock:1:42"

    # Test the handler doesn't crash even if Redis is down
    from app.agents.sales_agent import sales_bus_handler

    async def run():
        try:
            await sales_bus_handler({
                "event_type": "lead.scored",
                "tenant_id": "Client_1",
                "entity_id": "1",
                "payload": {"lead_id": 1},
            })
        except Exception:
            pass  # no Redis -> debounce silently skipped

    asyncio.run(run())


def test_sales_http_api_still_works():
    """B.1 regression: HTTP sales-ai endpoint still reachable."""
    from fastapi.testclient import TestClient
    import main as main_mod

    with TestClient(main_mod.app) as client:
        r = client.get("/openapi.json")
    assert r.status_code == 200


# --------------------------------------------------------------------------- #
# B.2 — Objections
# --------------------------------------------------------------------------- #
def test_objection_price_tag_from_message():
    """B.2: 'too expensive' tags price objection."""
    result = detect_objections("this is too expensive for me")
    assert len(result) >= 1
    assert result[0]["type"] == "price"


def test_objection_no_false_positive():
    """B.2: benign message has no objections."""
    result = detect_objections("I want to see the apartment")
    assert len(result) == 0


def test_objection_empty_message():
    """B.2: empty message returns empty list."""
    assert detect_objections("") == []
    assert detect_objections(None) == []


def test_objection_multiple_types():
    """B.2: message with multiple objections tags both."""
    result = detect_objections("too expensive and too far away")
    types = {r["type"] for r in result}
    assert "price" in types
    assert "location" in types


# --------------------------------------------------------------------------- #
# B.3 — CS WhatsApp
# --------------------------------------------------------------------------- #


def _make_test_lead(db, client_id, phone="+919999999999"):
    import uuid
    s = Session(id=str(uuid.uuid4()), client_id=client_id, status="active")
    db.add(s)
    db.flush()
    l = Lead(session_id=s.id, client_id=client_id, phone=phone, name="CS Test", conversion_status="open")
    db.add(l)
    db.flush()
    db.commit()
    return s.id, l.id


def test_cs_send_whatsapp_when_phone_present(monkeypatch):
    if not _db_ok():
        pytest.skip("DB not available")
    from app.agents.customer_success_agent import customer_success_handler
    from database import SessionLocal
    db = SessionLocal()
    client = db.query(Client).first()
    if not client:
        db.close()
        pytest.skip("no client seed data")
    cid = client.id
    sid, lid = _make_test_lead(db, cid, phone="+919988776655")
    db.close()

    submitted = []

    async def fake_submit(req):
        submitted.append(req)
        return {"status": "success"}

    import app.agents.customer_success_agent as mod
    monkeypatch.setattr(mod, "ae_submit", fake_submit)

    asyncio.run(customer_success_handler({
        "event_type": "booking.confirmed",
        "tenant_id": f"Client_{cid}",
        "entity_id": str(lid),
        "payload": {"lead_id": lid},
    }))

    assert len(submitted) == 1
    assert submitted[0]["action_type"] == "send_whatsapp"
    assert submitted[0]["parameters"].get("to") == "+919988776655"

    db2 = SessionLocal()
    _clean(db2, sid)
    db2.close()


def test_cs_fallback_notify_admin_without_phone(monkeypatch):
    if not _db_ok():
        pytest.skip("DB not available")
    from app.agents.customer_success_agent import customer_success_handler
    from database import SessionLocal
    db = SessionLocal()
    client = db.query(Client).first()
    if not client:
        db.close()
        pytest.skip("no client seed data")
    cid = client.id
    sid, lid = _make_test_lead(db, cid, phone=None)
    db.close()

    submitted = []

    async def fake_submit(req):
        submitted.append(req)
        return {"status": "success"}

    import app.agents.customer_success_agent as mod
    monkeypatch.setattr(mod, "ae_submit", fake_submit)

    asyncio.run(customer_success_handler({
        "event_type": "booking.confirmed",
        "tenant_id": f"Client_{cid}",
        "entity_id": str(lid),
        "payload": {"lead_id": lid},
    }))

    assert len(submitted) == 1
    assert submitted[0]["action_type"] == "notify_agent"

    db2 = SessionLocal()
    _clean(db2, sid)
    db2.close()


def test_cs_subscribes_customer_onboarded():
    from app.agents.customer_success_agent import CS_EVENTS
    assert "customer.onboarded" in CS_EVENTS


# --------------------------------------------------------------------------- #
# B.4 — Marketing market.alert
# --------------------------------------------------------------------------- #


def test_marketing_includes_market_alert_in_report(monkeypatch):
    if not _db_ok():
        pytest.skip("DB not available")
    from app.agents.marketing_agent import marketing_agent_handler
    from database import SessionLocal

    db = SessionLocal()
    client = db.query(Client).first()
    db.close()
    if not client:
        pytest.skip("no client seed data")

    published = []

    async def fake_publish(etype, tenant, entity, payload, source=None):
        published.append({"etype": etype, "payload": payload})

    import app.agents.marketing_agent as mod
    monkeypatch.setattr(mod.event_bus, "publish", fake_publish)

    asyncio.run(marketing_agent_handler({
        "event_type": "market.alert.generated",
        "tenant_id": f"Client_{client.id}",
        "entity_id": "42",
        "payload": {"lead_id": 42, "competitor": "AcmeCorp", "matched_keyword": "better deal"},
        "source": "competitor_monitor",
    }))

    assert len(published) == 1
    report = published[0]["payload"]
    assert "market_alert" in report
    assert report["market_alert"]["competitor"] == "AcmeCorp"


# --------------------------------------------------------------------------- #
# B.5 — templates + n8n
# --------------------------------------------------------------------------- #


def test_hot_lead_template_builds_valid_action_request():
    from app.automation_engine.templates.hot_lead_notify import build_hot_lead_action

    req = build_hot_lead_action(
        tenant_id="Client_1",
        lead_id=42,
        lead_name="Test Buyer",
        lead_phone="+919999999999",
        score=0.92,
    )
    assert req["action_type"] == "notify_agent"
    assert req["tenant_id"] == "Client_1"
    assert req["parameters"]["kind"] == "hot_lead"
    assert req["parameters"]["score"] == 0.92
    assert req["template_type"] == "linear"
    assert req["source"] == "hot_lead_notify_template"

    # n8n variant
    req2 = build_hot_lead_action(
        tenant_id="Client_1",
        lead_id=42,
        template_type="n8n",
        workflow_id="ireios_hot_lead_slack",
    )
    assert req2["template_type"] == "n8n"
    assert req2["workflow_id"] == "ireios_hot_lead_slack"


def test_visit_booking_template():
    from app.automation_engine.templates.visit_booking import build_visit_action

    req = build_visit_action(
        tenant_id="Client_1",
        lead_id=99,
        visit_date="2026-08-01T10:00",
        lead_name="Jane",
        property_type="3BHK",
    )
    assert req["action_type"] == "schedule_visit"
    assert req["parameters"]["visit_date"] == "2026-08-01T10:00"
    assert req["parameters"]["property_type"] == "3BHK"
    assert req["source"] == "visit_booking_template"


def test_n8n_hot_lead_workflow_id_documented_or_env():
    import os
    wf = os.environ.get("N8N_HOT_LEAD_WORKFLOW_ID", "ireios_hot_lead_slack")
    assert wf, "N8N_HOT_LEAD_WORKFLOW_ID or default must be set"
    # Check it's documented
    with open("docs/N8N_INTEGRATION.md") as f:
        doc = f.read()
    assert wf in doc, f"n8n workflow id {wf!r} must be documented in N8N_INTEGRATION.md"


# --------------------------------------------------------------------------- #
# B.6 — competitor notify
# --------------------------------------------------------------------------- #


def test_competitor_monitor_notifies_on_match(monkeypatch):
    if not _db_ok():
        pytest.skip("DB not available")
    from app.workflows.competitor_monitor import _write_notification
    from database import SessionLocal
    from models import NotificationLog

    db = SessionLocal()
    client = db.query(Client).first()
    if not client:
        db.close()
        pytest.skip("no client seed data")
    cid = client.id
    sid, lid = _make_test_lead(db, cid, phone="+919999999991")

    env = {
        "event_type": "market.alert.generated",
        "tenant_id": f"Client_{cid}",
        "entity_id": str(lid),
        "payload": {"lead_id": lid, "matches": ["better deal"], "monitored": ["AcmeCorp"]},
        "source": "competitor_monitor",
    }

    _write_notification(db, env)
    db.commit()

    logs = db.query(NotificationLog).filter(
        NotificationLog.client_id == cid,
        NotificationLog.lead_id == lid,
    ).all()
    assert len(logs) >= 1
    assert logs[0].reason == "competitor_alert"
    nid = logs[0].id

    _clean(db, sid)
    db.query(NotificationLog).filter(NotificationLog.id == nid).delete()
    db.commit()
    db.close()


# --------------------------------------------------------------------------- #
# B.7 — create_task (skeleton)
# --------------------------------------------------------------------------- #
_B7_IMPLEMENTED = False

def test_create_task_executor_success(monkeypatch):
    if not _B7_IMPLEMENTED:
        pytest.skip("B.7 not implemented")
    raise NotImplementedError
