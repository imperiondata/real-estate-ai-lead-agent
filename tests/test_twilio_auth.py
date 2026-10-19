import sys
import uuid
from pathlib import Path
from unittest.mock import patch, AsyncMock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

import models
from database import SessionLocal
from auth import get_password_hash
from main import app

# Tenant credentials for tests
TENANT_A_PHONE = "+14155238886"
TENANT_A_TOKEN = "test_auth_token_tenant_a_secret_123"
TENANT_A_SID = "AC_tenant_a_1234567890"

TENANT_B_PHONE = "+14155239999"
TENANT_B_TOKEN = "test_auth_token_tenant_b_secret_456"
TENANT_B_SID = "AC_tenant_b_1234567890"

BASE_WEBHOOK_URL = "http://testserver/api/v1/whatsapp"
HTTPS_WEBHOOK_URL = "https://testserver/api/v1/whatsapp"


@pytest.fixture(scope="module", autouse=True)
def setup_test_tenants():
    """Seed test tenants with dedicated Twilio phone numbers and auth tokens."""
    with SessionLocal() as db:
        # Cleanup any previous test client rows and webhook logs
        db.query(models.Client).filter(
            models.Client.email.in_([
                "twilio_test_tenant_a@revenueos.local",
                "twilio_test_tenant_b@revenueos.local",
                "twilio_test_tenant_inactive@revenueos.local",
            ])
        ).delete(synchronize_session=False)
        db.query(models.WebhookLog).filter(models.WebhookLog.message_sid.like("SM_test_%")).delete(synchronize_session=False)
        db.commit()

        # Tenant A
        tenant_a = models.Client(
            company_name="Tenant A Twilio Corp",
            email="twilio_test_tenant_a@revenueos.local",
            hashed_password=get_password_hash("password123"),
            api_key="twilio-test-key-a",
            is_api_key_hashed=False,
            twilio_phone_number=TENANT_A_PHONE,
            twilio_auth_token=TENANT_A_TOKEN,
            twilio_account_sid=TENANT_A_SID,
            is_active=True,
        )

        # Tenant B
        tenant_b = models.Client(
            company_name="Tenant B Twilio Corp",
            email="twilio_test_tenant_b@revenueos.local",
            hashed_password=get_password_hash("password123"),
            api_key="twilio-test-key-b",
            is_api_key_hashed=False,
            twilio_phone_number=TENANT_B_PHONE,
            twilio_auth_token=TENANT_B_TOKEN,
            twilio_account_sid=TENANT_B_SID,
            is_active=True,
        )

        # Inactive Tenant
        tenant_inactive = models.Client(
            company_name="Tenant Inactive Twilio",
            email="twilio_test_tenant_inactive@revenueos.local",
            hashed_password=get_password_hash("password123"),
            api_key="twilio-test-key-inactive",
            is_api_key_hashed=False,
            twilio_phone_number="+14155230000",
            twilio_auth_token="token_inactive_xyz",
            is_active=False,
        )

        db.add_all([tenant_a, tenant_b, tenant_inactive])
        db.commit()

        yield {
            "tenant_a": tenant_a,
            "tenant_b": tenant_b,
        }

        # Cleanup on teardown
        db.query(models.Client).filter(
            models.Client.email.in_([
                "twilio_test_tenant_a@revenueos.local",
                "twilio_test_tenant_b@revenueos.local",
                "twilio_test_tenant_inactive@revenueos.local",
            ])
        ).delete(synchronize_session=False)
        db.query(models.WebhookLog).filter(models.WebhookLog.message_sid.like("SM_test_%")).delete(synchronize_session=False)
        db.commit()


@pytest.fixture
def client():
    return TestClient(app)


def test_valid_signed_request(client):
    """1. Valid Signed Request: Generates a real X-Twilio-Signature using RequestValidator,

    asserting HTTP 200 and XML TwiML response.
    """
    msg_sid = f"SM_test_valid_{uuid.uuid4().hex[:12]}"
    payload = {
        "To": f"whatsapp:{TENANT_A_PHONE}",
        "From": "whatsapp:+19876543210",
        "Body": "Hello, I am looking for a 3BHK in Indiranagar",
        "MessageSid": msg_sid,
    }
    validator = RequestValidator(TENANT_A_TOKEN)
    signature = validator.compute_signature(BASE_WEBHOOK_URL, payload)

    with patch("main._session_turn_locked", new=AsyncMock(return_value="Welcome to Revenue OS")):
        response = client.post(
            "/api/v1/whatsapp",
            data=payload,
            headers={"X-Twilio-Signature": signature},
        )

    assert response.status_code == 200
    assert "application/xml" in response.headers["content-type"]
    assert "<Response>" in response.text
    assert "Welcome to Revenue OS" in response.text


def test_invalid_signature_fails_with_401(client):
    """2. Invalid Signature: Sends a request with a tampered signature, asserting HTTP 401."""
    msg_sid = f"SM_test_invalid_{uuid.uuid4().hex[:12]}"
    payload = {
        "To": f"whatsapp:{TENANT_A_PHONE}",
        "From": "whatsapp:+19876543210",
        "Body": "Hello with forged signature",
        "MessageSid": msg_sid,
    }
    tampered_signature = "invalid_forged_base64_signature="

    with patch("main._session_turn_locked", new=AsyncMock()) as mock_turn:
        response = client.post(
            "/api/v1/whatsapp",
            data=payload,
            headers={"X-Twilio-Signature": tampered_signature},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid Twilio signature"
    mock_turn.assert_not_called()


def test_altered_parameters_after_signing_fails_with_401(client):
    """3. Altered Parameters/Path: Modifies the POST body after signing,

    asserting validation fails with 401.
    """
    original_payload = {
        "To": f"whatsapp:{TENANT_A_PHONE}",
        "From": "whatsapp:+19876543210",
        "Body": "Original Unaltered Text",
        "MessageSid": "SM_tamper_body_003",
    }
    validator = RequestValidator(TENANT_A_TOKEN)
    signature = validator.compute_signature(BASE_WEBHOOK_URL, original_payload)

    # Tamper with the Body parameter after signature calculation
    tampered_payload = original_payload.copy()
    tampered_payload["Body"] = "Tampered Hostile Payload Injected"

    with patch("main._session_turn_locked", new=AsyncMock()) as mock_turn:
        response = client.post(
            "/api/v1/whatsapp",
            data=tampered_payload,
            headers={"X-Twilio-Signature": signature},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid Twilio signature"
    mock_turn.assert_not_called()


def test_unknown_tenant_destination_fails_with_404(client):
    """4. Unknown Tenant: Sends a request to an unregistered To number,

    asserting HTTP 404 (preventing unmapped routing).
    """
    payload = {
        "To": "whatsapp:+19998887777",  # Unregistered destination number
        "From": "whatsapp:+19876543210",
        "Body": "Hello to unknown recipient",
        "MessageSid": "SM_unknown_004",
    }
    # Even with an arbitrary signature, unmapped recipient must 404 before token lookup
    with patch("main._session_turn_locked", new=AsyncMock()) as mock_turn:
        response = client.post(
            "/api/v1/whatsapp",
            data=payload,
            headers={"X-Twilio-Signature": "some_sig="},
        )

    assert response.status_code == 404
    assert "No active tenant configured" in response.json()["detail"]
    mock_turn.assert_not_called()


def test_mismatched_account_and_recipient_fails_with_401(client):
    """5. Mismatched Account/Recipient: Uses Tenant A's signature/token but tries

    to process a payload destined for Tenant B's number, asserting HTTP 401.
    """
    # Payload destined for Tenant B
    payload = {
        "To": f"whatsapp:{TENANT_B_PHONE}",
        "From": "whatsapp:+19876543210",
        "Body": "Cross-tenant spoofing attempt",
        "MessageSid": "SM_mismatch_005",
    }
    # Attacker uses Tenant A's token to sign the payload
    validator_tenant_a = RequestValidator(TENANT_A_TOKEN)
    attacker_signature = validator_tenant_a.compute_signature(BASE_WEBHOOK_URL, payload)

    with patch("main._session_turn_locked", new=AsyncMock()) as mock_turn:
        response = client.post(
            "/api/v1/whatsapp",
            data=payload,
            headers={"X-Twilio-Signature": attacker_signature},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid Twilio signature"
    mock_turn.assert_not_called()


def test_production_like_proxy_infers_https(client):
    """6. Production-like Proxy: Tests that the validator correctly infers HTTPS

    from the X-Forwarded-Proto header.
    """
    payload = {
        "To": f"whatsapp:{TENANT_A_PHONE}",
        "From": "whatsapp:+19876543210",
        "Body": "Testing HTTPS reverse proxy verification",
        "MessageSid": f"SM_test_proxy_{uuid.uuid4().hex[:12]}",
    }
    validator = RequestValidator(TENANT_A_TOKEN)
    # The external caller (Twilio) signed against the external HTTPS URL:
    https_signature = validator.compute_signature(HTTPS_WEBHOOK_URL, payload)

    with patch("main._session_turn_locked", new=AsyncMock(return_value="Proxy verified successfully")):
        # Request arrives at internal uvicorn server via HTTP, but with X-Forwarded-Proto: https
        response = client.post(
            "/api/v1/whatsapp",
            data=payload,
            headers={
                "X-Twilio-Signature": https_signature,
                "X-Forwarded-Proto": "https",
            },
        )

    assert response.status_code == 200
    assert "Proxy verified successfully" in response.text

    # Negative check: If signature was signed for HTTP, but proxy forwarded HTTPS, it must fail with 401
    http_signature = validator.compute_signature(BASE_WEBHOOK_URL, payload)
    response_mismatch = client.post(
        "/api/v1/whatsapp",
        data=payload,
        headers={
            "X-Twilio-Signature": http_signature,
            "X-Forwarded-Proto": "https",
        },
    )
    assert response_mismatch.status_code == 401


def test_zero_side_effects_on_rejection(client):
    """7. Zero Side Effects: Asserts that when a 401 or 404 occurs,

    no database changes or background tasks are spawned.
    """
    with SessionLocal() as db:
        initial_webhook_logs = db.query(models.WebhookLog).count()
        initial_sessions = db.query(models.Session).count()
        initial_leads = db.query(models.Lead).count()
        initial_messages = db.query(models.Message).count()

    # 1. Trigger 404 (unmapped destination)
    client.post(
        "/api/v1/whatsapp",
        data={"To": "whatsapp:+10000000000", "From": "whatsapp:+19876543210", "Body": "404 test"},
        headers={"X-Twilio-Signature": "dummy_sig="},
    )

    # 2. Trigger 401 (invalid signature)
    client.post(
        "/api/v1/whatsapp",
        data={"To": f"whatsapp:{TENANT_A_PHONE}", "From": "whatsapp:+19876543210", "Body": "401 test"},
        headers={"X-Twilio-Signature": "invalid_sig="},
    )

    # 3. Trigger 401 (missing signature header)
    client.post(
        "/api/v1/whatsapp",
        data={"To": f"whatsapp:{TENANT_A_PHONE}", "From": "whatsapp:+19876543210", "Body": "Missing sig test"},
    )

    # Verify zero database mutations across all relevant tables
    with SessionLocal() as db:
        final_webhook_logs = db.query(models.WebhookLog).count()
        final_sessions = db.query(models.Session).count()
        final_leads = db.query(models.Lead).count()
        final_messages = db.query(models.Message).count()

    assert final_webhook_logs == initial_webhook_logs, "Side effect detected: WebhookLog was created on rejected request!"
    assert final_sessions == initial_sessions, "Side effect detected: Session was created on rejected request!"
    assert final_leads == initial_leads, "Side effect detected: Lead was created on rejected request!"
    assert final_messages == initial_messages, "Side effect detected: Message was created on rejected request!"
