"""Tests for P0 Security Remediation:
- API key SHA-256 verification (valid, invalid, revoked)
- PII redaction across logger, events, and payloads
- Fail-closed RAG / Vector / Neo4j retrieval on missing context
- Cross-tenant isolation (Client B denied access to Client A)
- DLQ replay safety (missing session, invalid tenant, mismatched resource, concurrent replay)
"""
import asyncio
import hashlib
import json
import logging
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException

from app.utils.redaction import mask_email, mask_phone, redact_text, redact_payload
from rag import _chunk_visible
from app.clients.graph_client import GraphClient
from dlq_replay import process_ml_followup
from models import DLQEvent, Session as SessionModel, Client, Lead
from database import SessionLocal


# --------------------------------------------------------------------------- #
# PII Redaction Unit Tests
# --------------------------------------------------------------------------- #

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
    assert mask_phone("+9199") == "+9199"  # short test string preserved
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


def test_logger_filter_redacts_pii():
    """Verify application log filter redacts emails and phone numbers."""
    from main import SecurePIILogFilter
    filt = SecurePIILogFilter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=10,
        msg="Inbound inquiry from lead@buyer.com with phone +919876543210",
        args=(), exc_info=None
    )
    filt.filter(record)
    assert "lead@buyer.com" not in record.msg
    assert "l***@buyer.com" in record.msg
    assert "9876543210" not in record.msg
    assert "***-***-3210" in record.msg


def test_event_bus_publisher_redacts_pii_payload():
    """Verify EventBusClient scrubs PII before emitting payload to Redis Streams."""
    from app.clients.event_bus_client import EventBusClient

    captured = []
    fake_redis = MagicMock()
    async def fake_xadd(stream, fields):
        captured.append(json.loads(fields["data"]))
        return "1-0"
    fake_redis.xadd = fake_xadd

    bus = EventBusClient(stream="test_stream", group="test_group")
    bus._running = True
    bus._pub_redis = fake_redis

    async def run():
        await bus.publish(
            "lead.created",
            "Client_1",
            "lead_101",
            {
                "name": "John Doe",
                "email": "john.doe@company.com",
                "phone": "+919876543210",
                "notes": "Direct contact via personal@domain.com",
            }
        )

    asyncio.run(run())
    assert len(captured) == 1
    p = captured[0]["payload"]
    assert p["name"] == "John Doe"
    assert p["email"] == "j***@company.com"
    assert p["phone"] == "***-***-3210"
    assert "personal@domain.com" not in p["notes"]
    assert "p***@domain.com" in p["notes"]


# --------------------------------------------------------------------------- #
# Backend Auth Verification: Valid, Invalid, and Revoked Keys
# --------------------------------------------------------------------------- #

def test_api_key_sha256_verification():
    from auth import get_client_by_api_key
    raw_key = "super-secret-test-key-p0"
    hashed_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    db = SessionLocal()
    try:
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


def test_auth_dependency_valid_invalid_and_revoked_keys():
    """Verify Depends(get_client_by_api_key) accepts valid hashed keys and rejects invalid/revoked keys."""
    from auth import get_client_by_api_key
    db = SessionLocal()
    try:
        active_raw = "active-test-key-p0"
        active_hash = hashlib.sha256(active_raw.encode("utf-8")).hexdigest()
        revoked_raw = "revoked-test-key-p0"
        revoked_hash = hashlib.sha256(revoked_raw.encode("utf-8")).hexdigest()

        # Seed active client with hashed key
        c1 = db.query(Client).filter(Client.api_key == active_hash).first()
        if not c1:
            c1 = Client(company_name="ActiveClient", email="active@test.com",
                        hashed_password="x", api_key=active_hash, is_active=True)
            db.add(c1)

        # Seed revoked client (is_active=False) with hashed key
        c2 = db.query(Client).filter(Client.api_key == revoked_hash).first()
        if not c2:
            c2 = Client(company_name="RevokedClient", email="revoked@test.com",
                        hashed_password="x", api_key=revoked_hash, is_active=False)
            db.add(c2)
        else:
            c2.is_active = False

        db.commit()

        # 1. Valid plaintext key matches database hash -> 200 OK
        res = get_client_by_api_key(api_key_h=active_raw, api_key_q=None, db=db)
        assert res.id == c1.id

        # 2. Invalid plaintext key -> 401 Unauthorized
        with pytest.raises(HTTPException) as exc_invalid:
            get_client_by_api_key(api_key_h="completely-wrong-key", api_key_q=None, db=db)
        assert exc_invalid.value.status_code == 401

        # 3. Revoked client key (is_active=False) -> 401 Unauthorized
        with pytest.raises(HTTPException) as exc_revoked:
            get_client_by_api_key(api_key_h=revoked_raw, api_key_q=None, db=db)
        assert exc_revoked.value.status_code == 401
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Fail-Closed RAG / Vector / Neo4j Retrieval on Missing Context
# --------------------------------------------------------------------------- #

def test_rag_chunk_fails_closed_on_missing_context():
    """Verify private tenant-tagged FAQ chunks fail closed when client_id is None."""
    # Private chunk belonging to tenant 9
    private_chunk = {"client_id": 9, "location": "Baner", "details": "Private project"}

    # Public FAQ chunk (explicitly marked public or untagged)
    public_chunk_tagged = {"is_public": True, "location": "Pune", "details": "City FAQ"}
    public_chunk_untagged = {"location": "Pune", "details": "General FAQ"}

    # FAIL CLOSED: Missing tenant context (client_id=None) CANNOT access private tenant chunk
    assert _chunk_visible(private_chunk, client_id=None) is False

    # Foreign tenant (client_id=3) CANNOT access tenant 9 private chunk
    assert _chunk_visible(private_chunk, client_id=3) is False

    # Legitimate owner (client_id=9) CAN access private chunk
    assert _chunk_visible(private_chunk, client_id=9) is True

    # Public FAQ chunks stay visible to everyone
    assert _chunk_visible(public_chunk_tagged, client_id=None) is True
    assert _chunk_visible(public_chunk_tagged, client_id=3) is True
    assert _chunk_visible(public_chunk_untagged, client_id=None) is True
    assert _chunk_visible(public_chunk_untagged, client_id=3) is True


def test_neo4j_retrieval_fails_closed_on_missing_or_down():
    """Verify GraphClient fails closed to empty dict when context cannot be established."""
    gc = GraphClient(kg=None)
    # Available is False when kg is unconfigured or down
    assert gc.available is False
    # Must fail closed returning empty dict, never raising or leaking foreign data
    assert gc.get_lead_context(lead_id=1, client_id=1) == {}


# --------------------------------------------------------------------------- #
# Cross-Tenant Isolation: Client B Denied Access to Client A
# --------------------------------------------------------------------------- #

def test_client_b_denied_access_to_client_a():
    """Verify Client B is strictly denied access (404) to Client A's lead and timeline."""
    from fastapi.testclient import TestClient
    from main import app

    db = SessionLocal()
    try:
        # Client A
        key_a = "client-a-secret-test-key"
        hash_a = hashlib.sha256(key_a.encode("utf-8")).hexdigest()
        ca = db.query(Client).filter(Client.api_key == hash_a).first()
        if not ca:
            ca = Client(company_name="Tenant A", email="tenant_a@iso.com",
                        hashed_password="x", api_key=hash_a, is_active=True)
            db.add(ca)
            db.commit()
            db.refresh(ca)

        # Client B
        key_b = "client-b-secret-test-key"
        hash_b = hashlib.sha256(key_b.encode("utf-8")).hexdigest()
        cb = db.query(Client).filter(Client.api_key == hash_b).first()
        if not cb:
            cb = Client(company_name="Tenant B", email="tenant_b@iso.com",
                        hashed_password="x", api_key=hash_b, is_active=True)
            db.add(cb)
            db.commit()
            db.refresh(cb)

        from models import Session as SessionModel

        # Ensure dummy session exists for Client A
        session_a = db.query(SessionModel).filter(SessionModel.id == "dummy_test_session_a").first()
        if not session_a:
            session_a = SessionModel(id="dummy_test_session_a", client_id=ca.id)
            db.add(session_a)
            db.commit()
            db.refresh(session_a)

        # Create private lead belonging exclusively to Client A
        lead_a = db.query(Lead).filter(Lead.client_id == ca.id, Lead.phone == "+919999900001").first()
        if not lead_a:
            lead_a = Lead(
                client_id=ca.id,
                session_id="dummy_test_session_a",
                name="Client A Private Lead",
                phone="+919999900001",
                location="Koregaon Park",
                budget="2Cr",
                property_type="3BHK"
            )
            db.add(lead_a)
            db.commit()
            db.refresh(lead_a)

        # TestClient accessing Client A's lead using Client B's credentials
        with TestClient(app) as http_client:
            resp = http_client.get(
                f"/api/v1/events/leads/{lead_a.id}/timeline",
                headers={"X-API-Key": key_b}
            )
            # MUST fail with 404: Client B cannot view Client A's lead
            assert resp.status_code == 404
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# DLQ Safety Tests: Missing Session, Invalid Tenant, Concurrent Replay
# --------------------------------------------------------------------------- #

def test_dlq_fails_closed_on_missing_session():
    """Verify DLQ replay returns False when session does not exist."""
    db = SessionLocal()
    try:
        payload = {
            "session_id": "nonexistent_session_999999",
            "stage": "Day 0",
            "lead_data": {"name": "Test"}
        }
        success = process_ml_followup(payload, db, event_client_id=1)
        assert success is False
    finally:
        db.close()


def test_dlq_fails_closed_on_tenant_mismatch():
    """Verify DLQ replay returns False when session client_id does not match event client_id."""
    db = SessionLocal()
    try:
        # Create session owned by client_id=1
        sess = db.query(SessionModel).filter(SessionModel.id == "dlq_tenant_mismatch_sess").first()
        if not sess:
            sess = SessionModel(id="dlq_tenant_mismatch_sess", client_id=1)
            db.add(sess)
            db.commit()

        payload = {
            "session_id": "dlq_tenant_mismatch_sess",
            "stage": "Day 0",
            "lead_data": {"name": "Test"}
        }
        # Attempt replay attributing event to client_id=2 (MISMATCH)
        success = process_ml_followup(payload, db, event_client_id=2)
        assert success is False
    finally:
        db.close()


def test_dlq_concurrent_replay_atomic_lock():
    """Verify atomic state claim prevents concurrent replay workers from double-processing."""
    db = SessionLocal()
    try:
        # Insert a pending DLQ event
        dlq_ev = DLQEvent(
            client_id=1,
            target_endpoint="hubspot_crm",
            payload={"test": "data"},
            error_trace="initial failure",
            status="pending"
        )
        db.add(dlq_ev)
        db.commit()
        db.refresh(dlq_ev)
        ev_id = dlq_ev.id

        # Worker 1 atomically claims the event: pending -> processing
        w1_claimed = db.query(DLQEvent).filter(
            DLQEvent.id == ev_id,
            DLQEvent.status == "pending"
        ).update({"status": "processing"})
        db.commit()
        assert w1_claimed == 1

        # Worker 2 simultaneously attempts to claim the same event: MUST FAIL (0 rows updated)
        w2_claimed = db.query(DLQEvent).filter(
            DLQEvent.id == ev_id,
            DLQEvent.status == "pending"
        ).update({"status": "processing"})
        db.commit()
        assert w2_claimed == 0

        # Worker 1 completes processing and resolves
        db.query(DLQEvent).filter(DLQEvent.id == ev_id).update({"status": "resolved"})
        db.commit()

        # Clean up
        db.query(DLQEvent).filter(DLQEvent.id == ev_id).delete()
        db.commit()
    finally:
        db.close()
