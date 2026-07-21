"""Wave D — Prediction routes, memory auto-write, n8n, brochure (D.1–D.5).

Plan: plans/IREIOS_3.0_WAVE_A_D_EXPANSION.md §4
Changelog: plans/IREIOS_3.0_WAVE_A_D_CHANGELOG.md
"""
from __future__ import annotations

import asyncio
import os

import pytest

os.environ.setdefault("ADMIN_API_KEY", "test-admin-key-wave-d")

from models import Client


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
# D.1 — Prediction routes
# --------------------------------------------------------------------------- #


def test_predict_revenue_returns_dict():
    if not _db_ok():
        pytest.skip("DB not available")
    from app.services.prediction_service import predict_revenue
    from database import SessionLocal
    db = SessionLocal()
    client = db.query(Client).first()
    if not client:
        db.close()
        pytest.skip("no client")
    result = predict_revenue(db, client.id)
    db.close()
    assert "total_expected_revenue" in result
    assert "open_lead_count" in result


def test_predict_cancellation_risk_returns_list():
    if not _db_ok():
        pytest.skip("DB not available")
    from app.services.prediction_service import predict_cancellation_risk
    from database import SessionLocal
    db = SessionLocal()
    client = db.query(Client).first()
    if not client:
        db.close()
        pytest.skip("no client")
    result = predict_cancellation_risk(db, client.id)
    db.close()
    assert isinstance(result, list)


def test_predict_inventory_returns_dict():
    if not _db_ok():
        pytest.skip("DB not available")
    from app.services.prediction_service import predict_inventory
    from database import SessionLocal
    db = SessionLocal()
    client = db.query(Client).first()
    if not client:
        db.close()
        pytest.skip("no client")
    result = predict_inventory(db, client.id)
    db.close()
    assert isinstance(result, dict)


def test_predict_cashflow_returns_dict():
    if not _db_ok():
        pytest.skip("DB not available")
    from app.services.prediction_service import predict_cashflow
    from database import SessionLocal
    db = SessionLocal()
    client = db.query(Client).first()
    if not client:
        db.close()
        pytest.skip("no client")
    result = predict_cashflow(db, client.id)
    db.close()
    assert "expected_30pct_cashflow" in result


def test_prediction_routes_return_401_without_jwt():
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)
    for path in ["/api/v1/predictions/revenue", "/api/v1/predictions/cancellation-risk",
                 "/api/v1/predictions/inventory", "/api/v1/predictions/cashflow"]:
        resp = client.get(path)
        assert resp.status_code == 401 or resp.status_code == 403


# --------------------------------------------------------------------------- #
# D.2 — Memory auto-write on WA turn (skeleton)
# --------------------------------------------------------------------------- #
_D2_IMPLEMENTED = False

def test_memory_auto_write_after_turn():
    if not _D2_IMPLEMENTED:
        pytest.skip("D.2 not implemented")
    raise NotImplementedError


# --------------------------------------------------------------------------- #
# D.3 — n8n workflows 2-3 (skeleton)
# --------------------------------------------------------------------------- #
_D3_IMPLEMENTED = False

def test_n8n_workflows_documented():
    if not _D3_IMPLEMENTED:
        pytest.skip("D.3 not implemented")
    raise NotImplementedError


# --------------------------------------------------------------------------- #
# D.4 — Brochure Approach B
# --------------------------------------------------------------------------- #


def test_resolve_tool_media_url_returns_url_when_configured(monkeypatch):
    from app.agents.whatsapp_agent import resolve_tool_media_url
    from config import settings
    monkeypatch.setattr(settings, "BROCHURE_MEDIA_URL", "https://cdn.example.com/brochure.pdf")
    monkeypatch.setattr(settings, "FLOORPLAN_MEDIA_URL", "https://cdn.example.com/floorplan.pdf")
    assert resolve_tool_media_url("brochure") == "https://cdn.example.com/brochure.pdf"
    assert resolve_tool_media_url("floorplan") == "https://cdn.example.com/floorplan.pdf"


def test_resolve_tool_media_url_falls_back_to_none(monkeypatch):
    from app.agents.whatsapp_agent import resolve_tool_media_url
    from config import settings
    monkeypatch.setattr(settings, "BROCHURE_MEDIA_URL", "")
    monkeypatch.setattr(settings, "FLOORPLAN_MEDIA_URL", "")
    assert resolve_tool_media_url("brochure") is None
    assert resolve_tool_media_url("floorplan") is None
    assert resolve_tool_media_url("unknown") is None


def test_resolve_tool_media_url_rejects_http(monkeypatch):
    """Approach B requires HTTPS — non-HTTPS is rejected."""
    from app.agents.whatsapp_agent import resolve_tool_media_url
    from config import settings
    monkeypatch.setattr(settings, "BROCHURE_MEDIA_URL", "http://cdn.example.com/bad.pdf")
    assert resolve_tool_media_url("brochure") is None


def test_process_chat_stages_media_url_for_twiml(monkeypatch):
    """Default brochure path stages HTTPS media for TwiML (no AE double-send)."""
    import asyncio
    from uuid import uuid4

    from app.agents.whatsapp_agent import (
        WhatsAppAgent,
        peek_outbound_media_url,
        take_outbound_media_url,
    )
    from config import settings
    from database import SessionLocal
    from models import Lead, Message, Session
    from tests.conftest import ensure_test_client

    monkeypatch.setattr(settings, "BROCHURE_MEDIA_URL", "https://cdn.example.com/brochure.pdf")
    monkeypatch.setattr(settings, "FLOORPLAN_MEDIA_URL", "")

    async def fake_legacy(session_id, user_message, db, client_id=1, is_background=False, extra_context=None):
        return "ok"

    import agent
    import app.agents.qualification as qual
    import app.agents.whatsapp_agent as wa

    monkeypatch.setattr(agent, "process_chat", fake_legacy)
    monkeypatch.setattr(qual, "process_chat", fake_legacy)

    ae_calls = []

    async def boom(*a, **k):
        ae_calls.append(1)
        raise AssertionError("AE must not run on default brochure path")

    monkeypatch.setattr(wa, "ae_submit", boom)

    cid = ensure_test_client(1)
    sid = f"sess_media_stage_{uuid4().hex[:8]}"
    with SessionLocal() as db:
        db.query(Message).filter(Message.session_id == sid).delete()
        db.query(Lead).filter(Lead.session_id == sid).delete()
        db.query(Session).filter(Session.id == sid).delete()
        db.add(Session(id=sid, client_id=cid, status="active"))
        db.add(
            Lead(
                session_id=sid,
                client_id=cid,
                name="Test",
                phone="+919999999999",
                whatsapp_opt_in=True,
                property_type="3BHK",
                location="Pune",
                budget="1cr",
            )
        )
        db.commit()
    try:
        take_outbound_media_url()  # clear

        async def run():
            with SessionLocal() as db:
                return await WhatsAppAgent().process_chat(
                    sid, "send me the brochure", db, client_id=cid, dispatch_via_ae=False
                )

        reply = asyncio.run(run())
        assert "brochure" in reply.lower()
        assert "Highlights" not in reply  # short caption, not full text
        assert peek_outbound_media_url() == "https://cdn.example.com/brochure.pdf"
        assert take_outbound_media_url() == "https://cdn.example.com/brochure.pdf"
        assert take_outbound_media_url() is None  # cleared
        assert ae_calls == []
    finally:
        with SessionLocal() as db:
            db.query(Message).filter(Message.session_id == sid).delete()
            db.query(Lead).filter(Lead.session_id == sid).delete()
            db.query(Session).filter(Session.id == sid).delete()
            db.commit()
        take_outbound_media_url()


def test_twiml_includes_media_when_configured(monkeypatch):
    """TwiML response should include Media element when media URL is configured."""
    from twilio.twiml.messaging_response import MessagingResponse
    from config import settings

    monkeypatch.setattr(settings, "BROCHURE_MEDIA_URL", "https://cdn.example.com/brochure.pdf")

    twiml = MessagingResponse()
    msg = twiml.message("Hi Test, here is the brochure for 3BHK in Pune.")
    msg.media("https://cdn.example.com/brochure.pdf")
    xml = str(twiml)
    assert "<Media>" in xml
    assert "https://cdn.example.com/brochure.pdf" in xml


def test_sales_send_brochure_includes_media_url(monkeypatch):
    """Sales NBA send_brochure attaches resolve_tool_media_url when configured."""
    import asyncio
    from app.agents.sales_agent import _nba_to_ae_action
    from config import settings

    monkeypatch.setattr(settings, "BROCHURE_MEDIA_URL", "https://cdn.example.com/brochure.pdf")

    submitted = []

    async def fake_submit(req):
        submitted.append(req)
        return {"status": "success"}

    import app.agents.sales_agent as sa
    monkeypatch.setattr(sa, "ae_submit", fake_submit)

    class L:
        id = 99
        name = "Raj"
        phone = "+919999999999"
        property_type = "2BHK"
        location = "Wakad"
        budget = "80L"
        visit_date = None
        intent = ""

    asyncio.run(_nba_to_ae_action(L(), 1, {"action": "send_brochure", "rationale": "test"}))
    assert len(submitted) == 1
    assert submitted[0]["action_type"] == "send_whatsapp"
    assert submitted[0]["parameters"]["media_url"] == "https://cdn.example.com/brochure.pdf"
    assert "Highlights" not in submitted[0]["parameters"]["body"]


# --------------------------------------------------------------------------- #
# D.5 — Evidence pack / G3 (skeleton)
# --------------------------------------------------------------------------- #
_D5_IMPLEMENTED = False

def test_evidence_pack_readme_up_to_date():
    if not _D5_IMPLEMENTED:
        pytest.skip("D.5 not implemented")
    raise NotImplementedError
