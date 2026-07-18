"""Production gap fill — inbound bus wiring + no double-send on brochure tools."""
from __future__ import annotations

import asyncio
import inspect

import main as main_mod
from app.agents.whatsapp_agent import WhatsAppAgent
from app.workflows.followup_arm import on_lead_created
from database import SessionLocal
from models import FollowUpState, Lead, Message, Session


def test_emit_turn_events_and_publish_helpers_exist():
    assert callable(main_mod._publish_bus_event)
    assert callable(main_mod._emit_turn_events)
    assert callable(main_mod._send_whatsapp_via_ee)
    assert callable(main_mod._is_lead_qualified)
    src = inspect.getsource(main_mod.process_unified_lead)
    assert "_emit_turn_events" in src
    bg = inspect.getsource(main_mod.background_process_and_push)
    assert "_send_whatsapp_via_ee" in bg
    assert "client.messages.create" not in bg


def test_is_lead_qualified_six_field_gate():
    class L:
        visit_date = "2026-08-01"
        phone = "+91"
        name = "A"
        location = "Wakad"
        budget = "80L"
        property_type = "2BHK"

    assert main_mod._is_lead_qualified(L()) is True
    L.visit_date = None
    assert main_mod._is_lead_qualified(L()) is False
    assert main_mod._is_lead_qualified(None) is False


def test_followup_arm_uses_payload_session_id():
    sid = "sess_arm_payload_1"
    try:
        with SessionLocal() as db:
            db.query(FollowUpState).filter(FollowUpState.session_id == sid).delete()
            db.query(Session).filter(Session.id == sid).delete()
            db.add(Session(id=sid, client_id=1, status="active"))
            db.commit()

        async def run():
            await on_lead_created(
                {
                    "event_type": "lead.created",
                    "tenant_id": "Client_1",
                    "entity_id": "999001",
                    "payload": {"session_id": sid, "lead_id": 999001},
                }
            )

        asyncio.run(run())
        with SessionLocal() as db:
            row = db.query(FollowUpState).filter(FollowUpState.session_id == sid).first()
            assert row is not None
            assert row.follow_up_status == "active"
    finally:
        with SessionLocal() as db:
            db.query(FollowUpState).filter(FollowUpState.session_id == sid).delete()
            db.query(Session).filter(Session.id == sid).delete()
            db.commit()


def test_brochure_default_path_does_not_ae_dispatch(monkeypatch):
    """TwiML/chat path must not AE-send brochure (avoids double delivery)."""
    called = {"ae": 0}

    async def boom(*a, **k):
        called["ae"] += 1
        raise AssertionError("AE should not be called on default brochure path")

    async def fake_legacy(session_id, user_message, db, client_id=1, is_background=False, extra_context=None):
        return "ok"

    import agent
    import app.agents.qualification as qual
    import app.agents.whatsapp_agent as wa

    monkeypatch.setattr(agent, "process_chat", fake_legacy)
    monkeypatch.setattr(qual, "process_chat", fake_legacy)
    monkeypatch.setattr(wa, "ae_submit", boom)

    sid = "sess_brochure_nodouble"
    with SessionLocal() as db:
        db.query(Message).filter(Message.session_id == sid).delete()
        db.query(Lead).filter(Lead.session_id == sid).delete()
        db.query(Session).filter(Session.id == sid).delete()
        db.add(Session(id=sid, client_id=1, status="active"))
        db.add(
            Lead(
                session_id=sid,
                client_id=1,
                name="Me",
                phone="+919999999999",
                whatsapp_opt_in=True,
                property_type="2BHK",
                location="Wakad",
                budget="80L",
            )
        )
        db.commit()
    try:
        async def run():
            with SessionLocal() as db:
                return await WhatsAppAgent().process_chat(
                    sid, "send me the brochure", db, client_id=1
                )

        reply = asyncio.run(run())
        assert "brochure" in reply.lower()
        assert called["ae"] == 0
    finally:
        with SessionLocal() as db:
            db.query(Message).filter(Message.session_id == sid).delete()
            db.query(Lead).filter(Lead.session_id == sid).delete()
            db.query(Session).filter(Session.id == sid).delete()
            db.commit()
