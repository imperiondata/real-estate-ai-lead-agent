"""Expansion Phase 8 — Prediction APIs + Marketing/CS/Competitor (Tasks 8.1–8.5).

Tracks Step 17 (Expansion Phase 8). Exercises the prediction service and the
new client-scoped endpoints.

See plans/IREIOS_3.0_EXPANSION_CHANGELOG.md (Phase 8 status).
"""
from app.services.prediction_service import (
    competitor_signals,
    detect_at_risk,
    marketing_campaign_suggestion,
    predict_closure_days,
    predict_conversion,
    segment_leads,
)
from models import Lead, Session


def _clean(db, sid):
    db.query(Lead).filter(Lead.session_id == sid).delete()
    db.query(Session).filter(Session.id == sid).delete()
    db.commit()


def test_predict_conversion():
    lead = Lead(id=1, conversion_probability=80, lead_temperature="hot")
    p = predict_conversion(lead)
    assert p["conversion_probability"] == 80
    assert p["confidence"] == "high"
    # prob=80 -> round((100-80)/8)=round(2.5)=2 (banker's rounding)
    assert predict_closure_days(lead) == 2


def test_predict_conversion_low():
    lead = Lead(id=2, conversion_probability=20, lead_temperature="cold")
    p = predict_conversion(lead)
    assert p["confidence"] == "low"
    assert predict_closure_days(lead) > 1


def test_segment_leads():
    with __import__("database").SessionLocal() as db:
        for sid in ("seg_h", "seg_w", "seg_c"):
            _clean(db, sid)
        for sid, temp in (("seg_h", "hot"), ("seg_w", "warm"), ("seg_c", "cold")):
            db.add(Session(id=sid, client_id=1, status="active"))
            db.add(Lead(session_id=sid, client_id=1, lead_temperature=temp, conversion_status="open"))
        db.commit()
        segs = segment_leads(db, 1)
        # membership check (other client-1 open leads may exist from earlier tests)
        assert "seg_h" not in segs  # session_id not stored; check lead ids instead
        # locate by querying the leads we created
        from models import Lead as L
        hid = db.query(L).filter(L.session_id == "seg_h").first().id
        wid = db.query(L).filter(L.session_id == "seg_w").first().id
        cid = db.query(L).filter(L.session_id == "seg_c").first().id
        assert hid in segs["hot"] and wid in segs["warm"] and cid in segs["cold"]
        for sid in ("seg_h", "seg_w", "seg_c"):
            _clean(db, sid)


def test_marketing_campaign_suggestion():
    assert "WhatsApp" in marketing_campaign_suggestion("hot")["recommended_channel"]
    assert "email" in marketing_campaign_suggestion("cold")["recommended_channel"]


def test_detect_at_risk():
    with __import__("database").SessionLocal() as db:
        _clean(db, "risk_1")
        db.add(Session(id="risk_1", client_id=1, status="active"))
        lead = Lead(session_id="risk_1", client_id=1, lead_temperature="cold", conversion_status="open")
        db.add(lead)
        db.commit()
        risks = detect_at_risk(db, 1)
        assert any(r["lead_id"] == lead.id for r in risks)
        _clean(db, "risk_1")


def test_competitor_signals(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "COMPETITOR_KEYWORDS", "xyz builders,abc realty")
    sig = competitor_signals("i also spoke to xyz builders")
    assert sig["alert"] is True
    assert "xyz builders" in sig["matches"]
    sig2 = competitor_signals("nothing relevant")
    assert sig2["alert"] is False
