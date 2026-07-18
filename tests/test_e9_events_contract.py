"""Expansion Phase 9 — Frontend cutover backend contract (Tasks 9.1–9.2).

The FE half (9.3–9.7) is Mayank-owned. This backend test locks the contract
the FE consumes from Phase 1b: the events SSE router is mounted and the lead
timeline returns the frozen envelope schema, tenant-scoped and 401 without a
key. This is the backend half of Step 18.

See plans/IREIOS_3.0_STEP_BY_STEP_EXPANSION.md (Phase 9) and
plans/IREIOS_3.0_EXPANSION_CHANGELOG.md.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.events import router as events_router
from database import engine, Base
from models import Client, EventLog, Lead, Session


def _make_app():
    app = FastAPI()
    app.include_router(events_router)
    return app


def _seed():
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        client = db.query(Client).filter(Client.api_key == "e9_test_key").first()
        if not client:
            client = Client(company_name="E9Test", email="e9@test.com",
                            hashed_password="x", api_key="e9_test_key",
                            is_active=True, subscription_status="inactive")
            db.add(client)
            db.commit()
        cid = client.id
        sid = "e9_sess_1"
        db.query(Lead).filter(Lead.session_id == sid).delete()
        db.query(Session).filter(Session.id == sid).delete()
        db.query(EventLog).filter(EventLog.session_id == sid).delete()
        db.add(Session(id=sid, client_id=cid, status="active"))
        lead = Lead(session_id=sid, client_id=cid, name="E9", location="Wakad")
        db.add(lead)
        db.commit()
        lid = lead.id
        db.add(EventLog(session_id=sid, client_id=cid, event_type="tracking",
                        action_type="lead_created", agent_type="AI"))
        db.commit()
        return cid, lid
    finally:
        db.close()


def test_timeline_envelope_contract():
    cid, lid = _seed()
    app = _make_app()
    with TestClient(app) as client:
        # 401 without a key
        r = client.get(f"/api/v1/events/leads/{lid}/timeline")
        assert r.status_code == 401
        # envelope shape with api key
        r = client.get(f"/api/v1/events/leads/{lid}/timeline?api_key=e9_test_key")
        assert r.status_code == 200
        body = r.json()
        assert body["lead_id"] == lid
        assert isinstance(body["events"], list)
        assert body["events"]
        evt = body["events"][0]
        for field in ("event_id", "event_type", "tenant_id", "entity_id", "source", "timestamp", "payload"):
            assert field in evt
        assert evt["tenant_id"] == f"Client_{cid}"


def test_timeline_isolation():
    cid, lid = _seed()
    app = _make_app()
    # Create a second client that must NOT see client 1's lead.
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        other = db.query(Client).filter(Client.api_key == "e9_test_key2").first()
        if not other:
            other = Client(company_name="E9Other", email="e9o@test.com",
                           hashed_password="x", api_key="e9_test_key2",
                           is_active=True, subscription_status="inactive")
            db.add(other)
            db.commit()
    finally:
        db.close()
    with TestClient(app) as client:
        r = client.get(f"/api/v1/events/leads/{lid}/timeline?api_key=e9_test_key2")
        assert r.status_code == 404  # lead belongs to client 1, not client 2
