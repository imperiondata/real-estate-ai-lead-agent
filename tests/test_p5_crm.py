"""P5 — CRM sync completeness (re-sync after changes, expanded map, no false success)."""

from types import SimpleNamespace

import pytest
import uuid

from crm_sync import (
    build_crm_properties,
    decide_crm_status_after_poll,
    crm_resync_job,
    sync_lead_to_crm,
)


def _lead(**kw):
    base = dict(
        name=None, phone=None, budget=None, location=None, property_type=None,
        intent=None, visit_date=None, assigned_agent=None,
        budget_alignment_status=None, urgency_level=None, engagement_score=0,
        lead_temperature="cold", external_crm_id=None, crm_sync_status="pending",
        crm_resync_pending=False, client_id=1,
    )
    base.update(kw)
    return SimpleNamespace(**base)


# --- P5.2: expanded property map ---


def test_base_properties_always_present():
    props = build_crm_properties(_lead(name="A", phone="+91"), include_extended=False)
    assert props["firstname"] == "A"
    assert props["phone"] == "+91"
    assert props["lifecyclestage"] == "lead"
    assert "location" not in props


def test_extended_properties_included_when_enabled():
    lead = _lead(name="A", phone="+91", location="Baner", property_type="2bhk",
                 intent="buy", visit_date="2026-08-01", assigned_agent="Raj",
                 budget_alignment_status="aligned", urgency_level="high",
                 engagement_score=42, lead_temperature="hot")
    props = build_crm_properties(lead, include_extended=True)
    assert props["location"] == "Baner"
    assert props["property_type"] == "2bhk"
    assert props["intent"] == "buy"
    assert props["visit_date"] == "2026-08-01"
    assert props["assignee"] == "Raj"
    assert props["budget_alignment_status"] == "aligned"
    assert props["urgency_level"] == "high"
    assert props["engagement_score"] == "42"
    assert props["lead_temperature"] == "hot"


def test_extended_properties_skipped_when_disabled():
    lead = _lead(name="A", phone="+91", location="Baner")
    props = build_crm_properties(lead, include_extended=False)
    assert "location" not in props


def test_boolean_values_normalized_to_string():
    props = build_crm_properties(_lead(include_extended=True, whatsapp_opt_in=True), include_extended=True)
    # ensure no truthy bool leaks; only the enumerated extended fields are added
    assert all(not isinstance(v, bool) for v in props.values())


# --- P5.3: no false success on empty identity ---


def test_status_pending_when_identity_missing():
    lead = _lead(name=None, phone=None)
    assert decide_crm_status_after_poll(lead) == "pending"


def test_status_success_when_phone_present():
    lead = _lead(name=None, phone="+91")
    assert decide_crm_status_after_poll(lead) == "success"


def test_status_success_when_name_present():
    lead = _lead(name="A", phone=None)
    assert decide_crm_status_after_poll(lead) == "success"


# --- P5.1: debounced re-sync job (DB-backed) ---


@pytest.mark.integration
def test_resync_job_clears_pending_after_sync():
    from database import SessionLocal
    from models import Lead, Client, Session

    db = SessionLocal()
    try:
        client = db.query(Client).first()
        assert client, "seed a client before running CRM resync test"
        sid = f"crmtest_{client.id}_{uuid.uuid4().hex}"
        db.add(Session(id=sid, client_id=client.id, status="active"))
        db.commit()
        lead = Lead(
            client_id=client.id,
            session_id=sid,
            name="Resync Tester",
            phone="+910000000000",
            external_crm_id="ext-123",
            crm_sync_status="success",
            crm_resync_pending=True,
        )
        db.add(lead)
        db.commit()
        lead_id = lead.id

        crm_resync_job()

        db.expire_all()
        refreshed = db.query(Lead).filter(Lead.id == lead_id).first()
        assert refreshed.crm_resync_pending is False
        assert refreshed.crm_sync_status == "success"

        db.delete(refreshed)
        db.delete(db.query(Session).filter(Session.id == sid).first())
        db.commit()
    finally:
        db.close()
