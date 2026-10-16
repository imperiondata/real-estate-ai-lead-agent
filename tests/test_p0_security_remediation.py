"""Tests for P0 Security Remediation: API key hashing and PII redaction."""
import hashlib
import pytest
from app.utils.redaction import mask_email, mask_phone, redact_text, redact_payload


def test_mask_email():
    assert mask_email("mayank@gmail.com") == "m***@gmail.com"
    assert mask_email("john.doe@example.org") == "j***@example.org"
    assert mask_email("a@b.com") == "a***@b.com"
    assert mask_email("invalid-email") == "invalid-email"
    assert mask_email("") == ""


def test_mask_phone():
    assert mask_phone("+919876541234") == "***-***-1234"
    assert mask_phone("987-654-1234") == "***-***-1234"
    assert mask_phone("+1 (555) 123-1234") == "***-***-1234"
    assert mask_phone("1234") == "***-***-1234"
    assert mask_phone("") == ""


def test_redact_text():
    raw = "User email is mayank@gmail.com and phone is +919876541234."
    redacted = redact_text(raw)
    assert "mayank@gmail.com" not in redacted
    assert "m***@gmail.com" in redacted
    assert "9876541234" not in redacted
    assert "***-***-1234" in redacted


def test_redact_payload_nested():
    payload = {
        "user": {
            "email": "mayank@gmail.com",
            "phone_number": "+919876541234",
            "name": "Mayank Jindal",
        },
        "notes": [
            "Customer contacted from +1-555-123-4567 about listing.",
            "Send info to contact@realestate.com"
        ],
        "safe_int": 42,
    }
    redacted = redact_payload(payload)
    assert redacted["user"]["email"] == "m***@gmail.com"
    assert redacted["user"]["phone_number"] == "***-***-1234"
    assert redacted["user"]["name"] == "Mayank Jindal"
    assert "contact@realestate.com" not in redacted["notes"][1]
    assert "c***@realestate.com" in redacted["notes"][1]
    assert "4567" in redacted["notes"][0]
    assert redacted["safe_int"] == 42


def test_api_key_sha256_verification():
    from auth import get_client_by_api_key
    from database import SessionLocal
    from models import Client

    raw_key = "super-secret-test-key-p0"
    hashed_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    db = SessionLocal()
    try:
        # Create client with HASHED key in database
        client = db.query(Client).filter(Client.api_key == hashed_key).first()
        if not client:
            client = Client(
                company_name="P0 Hash Test Client",
                email="p0_hash_test@example.com",
                hashed_password="dummy_password",
                api_key=hashed_key,
                is_active=True,
            )
            db.add(client)
            db.commit()
            db.refresh(client)

        # Call get_client_by_api_key using PLAINTEXT key
        resolved = get_client_by_api_key(api_key_h=raw_key, api_key_q=None, db=db)
        assert resolved.id == client.id
        assert resolved.api_key == hashed_key
    finally:
        db.close()
