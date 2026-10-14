"""P0 SEC04 — header-only API keys, hashed lookup, phone redaction. No Render."""
from types import SimpleNamespace

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from auth import find_client_by_api_key, get_client_by_api_key, hash_api_key
from app.events.lead_hot import build_lead_hot_payload
from app.events.redact import mask_phones
from database import SessionLocal
from models import Client


def test_hash_matches_and_plaintext_still_matches():
    raw = "sec04-raw-key"
    digest = hash_api_key(raw)
    emails = ("sec04-hash@test.com", "sec04-plain@test.com")
    db = SessionLocal()
    try:
        db.query(Client).filter(Client.email.in_(emails)).delete(synchronize_session=False)
        db.add(Client(
            company_name="SEC04Hash", email=emails[0], hashed_password="x",
            api_key=digest, is_active=True, subscription_status="inactive",
        ))
        db.add(Client(
            company_name="SEC04Plain", email=emails[1], hashed_password="x",
            api_key="sec04-plain", is_active=True, subscription_status="inactive",
        ))
        db.commit()
        assert find_client_by_api_key(db, raw).email == emails[0]
        assert find_client_by_api_key(db, "sec04-plain").email == emails[1]
        assert find_client_by_api_key(db, "missing") is None
        assert find_client_by_api_key(db, "") is None
        stored = db.query(Client).filter(Client.email == emails[1]).one()
        assert stored.api_key == "sec04-plain"
    finally:
        db.rollback()
        db.query(Client).filter(Client.email.in_(emails)).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_query_api_key_is_rejected():
    app = FastAPI()

    @app.get("/ping")
    def ping(client=Depends(get_client_by_api_key)):
        return {"id": client.id}

    with TestClient(app) as client:
        denied = client.get("/ping?api_key=secret-client-key-123")
        assert denied.status_code == 401
        missing = client.get("/ping")
        assert missing.status_code == 401


def test_lead_hot_drops_phone_and_masks_context():
    lead = SimpleNamespace(
        id=7,
        session_id="1_+919876543210",
        name="Ada",
        phone="+919876543210",
        location="Baner",
        budget="80L",
        property_type="2BHK",
        intent="buy",
        lead_temperature="hot",
        conversion_probability=90,
        assigned_agent="Sneha",
    )
    payload = build_lead_hot_payload(
        lead,
        trigger="hot_threshold",
        reason="crossed",
        chat_context="call me at +919876543210",
    )
    assert "phone" not in payload
    assert payload["name"] == "Ada"
    assert "+919876543210" not in payload["chat_context"]
    assert mask_phones("msg +91 98765 43210") == "msg [redacted-phone]"
