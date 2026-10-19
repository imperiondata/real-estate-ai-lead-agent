"""Production gap fill — inbound bus wiring + no double-send on brochure tools."""
from __future__ import annotations

import asyncio
import inspect

import pytest

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


def test_followup_arm_uses_lead_row_session_id():
    """P0 claim-check: arm from the lead row, not the payload; foreign tenant no-op."""
    from tests.conftest import ensure_test_client

    cid = ensure_test_client(1)
    other_cid = ensure_test_client(2)
    if other_cid == cid:
        pytest.skip("needs a second distinct tenant")
    sid = "sess_arm_row_1"
    foreign_sid = "sess_arm_row_foreign"
    lead_id = None
    try:
        with SessionLocal() as db:
            db.query(FollowUpState).filter(FollowUpState.session_id.in_([sid, foreign_sid])).delete()
            db.query(Lead).filter(Lead.session_id == sid).delete()
            db.query(Session).filter(Session.id == sid).delete()
            db.add(Session(id=sid, client_id=cid, status="active"))
            lead = Lead(session_id=sid, client_id=cid, name="Arm Row", phone="+919000111222")
            db.add(lead)
            db.commit()
            db.refresh(lead)
            lead_id = lead.id

        async def run(event):
            await on_lead_created(event)

        # Two-key claim payload: the session id is NOT on the bus.
        asyncio.run(run({
            "event_type": "lead.created",
            "tenant_id": f"Client_{cid}",
            "entity_id": str(lead_id),
            "payload": {"lead_id": lead_id, "tenant_id": f"Client_{cid}"},
        }))
        with SessionLocal() as db:
            row = db.query(FollowUpState).filter(FollowUpState.session_id == sid).first()
            assert row is not None, "must arm using lead.session_id from the row"
            assert row.client_id == cid
            assert row.follow_up_status == "active"

        # Foreign tenant on A's lead id: must not arm.
        asyncio.run(run({
            "event_type": "lead.created",
            "tenant_id": f"Client_{other_cid}",
            "entity_id": str(lead_id),
            "payload": {"lead_id": lead_id, "tenant_id": f"Client_{other_cid}"},
        }))
        with SessionLocal() as db:
            foreign = db.query(FollowUpState).filter(FollowUpState.session_id == foreign_sid).first()
            assert foreign is None
            foreign_any = db.query(FollowUpState).filter(
                FollowUpState.client_id == other_cid,
                FollowUpState.session_id == sid,
            ).first()
            assert foreign_any is None, "foreign tenant must never arm A's lead"
    finally:
        with SessionLocal() as db:
            db.query(FollowUpState).filter(FollowUpState.session_id.in_([sid, foreign_sid])).delete()
            if lead_id is not None:
                db.query(Lead).filter(Lead.id == lead_id).delete()
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

    from tests.conftest import ensure_test_client

    cid = ensure_test_client(1)
    sid = "sess_brochure_nodouble"
    with SessionLocal() as db:
        db.query(Message).filter(Message.session_id == sid).delete()
        db.query(Lead).filter(Lead.session_id == sid).delete()
        db.query(Session).filter(Session.id == sid).delete()
        db.add(Session(id=sid, client_id=cid, status="active"))
        db.add(
            Lead(
                session_id=sid,
                client_id=cid,
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
                    sid, "send me the brochure", db, client_id=cid
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
