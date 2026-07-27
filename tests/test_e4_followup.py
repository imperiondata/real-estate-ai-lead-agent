"""Expansion Phase 4 — Follow-up scheduler via AE->EE (Tasks 4.1–4.5).

Tracks Step 13 (Expansion Phase 4). Exercises the v3 follow-up workflow, the
FOLLOWUP_ENGINE selector, and the FollowUpState arming handler.

See plans/IREIOS_3.0_EXPANSION_CHANGELOG.md (Phase 4 status).
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.workflows.followup_arm import arm_followup_state, on_lead_created
from app.workflows.followup_scheduler import check_and_send_followups_v3, _backoff
from config import settings
from database import SessionLocal
from models import FollowUpState, Lead, Message, Session


def _clean(ids):
    with SessionLocal() as db:
        for sid in ids:
            db.query(Message).filter(Message.session_id == sid).delete()
            db.query(FollowUpState).filter(FollowUpState.session_id == sid).delete()
            db.query(Lead).filter(Lead.session_id == sid).delete()
            db.query(Session).filter(Session.id == sid).delete()
        db.commit()


def _make_lead(session_id="sess_fu_1", phone="+919999999999", source="whatsapp"):
    with SessionLocal() as db:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        db.execute(
            pg_insert(__import__("models").Client).values(
                id=1, company_name="A", email="phase4_test@a.com",
                hashed_password="x", api_key="phase4_test_k1", is_active=True,
                subscription_status="inactive",
            ).on_conflict_do_nothing(index_elements=["id"])
        )
        sess = Session(id=session_id, client_id=1, status="active")
        db.add(sess)
        lead = Lead(session_id=session_id, client_id=1, name="Fu", phone=phone,
                   source=source, whatsapp_opt_in=True, conversion_probability=70)
        db.add(lead)
        db.add(FollowUpState(session_id=session_id, client_id=1, follow_up_stage="Day 0",
                             follow_up_status="active",
                             next_follow_up_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
        db.commit()


def test_followup_v3_test_mode_sends_and_advances(monkeypatch):
    sid = "sess_v3_1"
    try:
        monkeypatch.setattr(settings, "TEST_MODE", True)
        monkeypatch.setattr(settings, "FOLLOW_UP_TEST_MODE", True)
        _make_lead(sid)
        check_and_send_followups_v3()
        with SessionLocal() as db:
            state = db.query(FollowUpState).filter(FollowUpState.session_id == sid).first()
            assert state.follow_up_stage == "Day 1"
            assert state.follow_up_status == "active"
            msgs = db.query(Message).filter(Message.session_id == sid).all()
            assert any("AUTO" in m.content for m in msgs)
    finally:
        _clean([sid])


def test_followup_v3_terminal_optout_stops(monkeypatch):
    sid = "sess_v3_opt"
    try:
        monkeypatch.setattr(settings, "TEST_MODE", True)
        monkeypatch.setattr(settings, "FOLLOW_UP_TEST_MODE", True)
        _make_lead(sid)
        with SessionLocal() as db:
            l = db.query(Lead).filter(Lead.session_id == sid).first()
            l.whatsapp_opt_in = False
            db.commit()
        check_and_send_followups_v3()
        with SessionLocal() as db:
            state = db.query(FollowUpState).filter(FollowUpState.session_id == sid).first()
            assert state.follow_up_status == "stopped"
    finally:
        _clean([sid])


def test_arm_followup_state_idempotent():
    sid = "sess_arm_1"
    try:
        with SessionLocal() as db:
            db.add(Session(id=sid, client_id=1, status="active"))
            db.commit()
        arm_followup_state(sid, 1, next_in=5)
        arm_followup_state(sid, 1, next_in=5)
        with SessionLocal() as db:
            rows = db.query(FollowUpState).filter(FollowUpState.session_id == sid).all()
            assert len(rows) == 1
    finally:
        _clean([sid])


def test_on_lead_created_arms_state():
    sid = "sess_evt_1"
    try:
        with SessionLocal() as db:
            db.add(Session(id=sid, client_id=1, status="active"))
            db.commit()
        async def run():
            await on_lead_created({"event_type": "lead.created", "tenant_id": "Client_1", "entity_id": sid})

        asyncio.run(run())
        with SessionLocal() as db:
            row = db.query(FollowUpState).filter(FollowUpState.session_id == sid).first()
            assert row is not None
            assert row.follow_up_status == "active"
    finally:
        _clean([sid])


def test_backoff_schedules_retry():
    sid = "sess_bo_1"
    try:
        with SessionLocal() as db:
            db.add(Session(id=sid, client_id=1, status="active"))
            state = FollowUpState(session_id=sid, client_id=1, follow_up_stage="Day 1",
                                  follow_up_status="active",
                                  next_follow_up_at=datetime.now(timezone.utc))
            db.add(state)
            db.commit()
        with SessionLocal() as db:
            s = db.query(FollowUpState).filter(FollowUpState.session_id == sid).first()
            _backoff(db, s, datetime.now(timezone.utc))
        with SessionLocal() as db:
            s = db.query(FollowUpState).filter(FollowUpState.session_id == sid).first()
            assert s.send_retry_count == 1
            assert s.next_follow_up_at is not None
    finally:
        _clean([sid])
