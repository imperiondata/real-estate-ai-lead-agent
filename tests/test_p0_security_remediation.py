"""Tests for P0 Security Remediation:
- API key migration & verification with explicit is_api_key_hashed state & 64-char hex legacy key regression
- URL query-string API key rejection (400 Bad Request)
- PII redaction across logger, events, payloads, names, and companies
- Fail-closed RAG / Vector / Neo4j retrieval on missing context / unknown metadata
- Deep cross-tenant negative-access isolation (read, update, delete, export, webhook)
- DLQ fail-closed on a missing session or a tenant mismatch
- INF-01 S3 backup pipeline verification with moto (KMS encryption, SHA-256 checksum, 30-day lifecycle)

Live DLQ concurrency is not in this file. Run scripts/prove_dlq_concurrency.py
against local Postgres.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import secrets
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from moto import mock_aws
import boto3

from app.utils.redaction import mask_email, mask_phone, mask_name, redact_text, redact_payload
from rag import _chunk_visible
from app.clients.graph_client import GraphClient
from dlq_replay import process_ml_followup
from models import Session as SessionModel, Client, Lead
from database import SessionLocal
from scripts.backup_to_s3 import run_s3_backup
from auth import get_client_by_api_key, create_access_token
from main import app


# --------------------------------------------------------------------------- #
# 1. PII Redaction Unit Tests (Email, Phone, Name, Company)
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
    assert mask_phone("+9199") == "+9199"  # short string preserved
    assert mask_phone("") == ""


def test_mask_name():
    assert mask_name("Mayank Jindal") == "M*** J***"
    assert mask_name("Acme Real Estate") == "A*** R*** E***"
    assert mask_name("Alice") == "A***"
    assert mask_name("") == ""
    assert mask_name(None) is None


def test_redact_text():
    raw = "User email is mayank@gmail.com and phone is +919876541234."
    redacted = redact_text(raw)
    assert "mayank@gmail.com" not in redacted
    assert "m***@gmail.com" in redacted
    assert "9876541234" not in redacted
    assert "***-***-1234" in redacted


def test_redact_payload_nested():
    """Verify nested payload redacts emails, phones, names, and companies."""
    payload = {
        "user": {
            "email": "mayank@gmail.com",
            "phone_number": "+919876541234",
            "name": "Mayank Jindal",
            "company": "Acme Realty",
        },
        "notes": [
            "Customer contacted from +1-555-123-4567 about listing.",
            "Send info to contact@realestate.com",
        ],
        "safe_int": 42,
    }
    redacted = redact_payload(payload)
    assert redacted["user"]["email"] == "m***@gmail.com"
    assert redacted["user"]["phone_number"] == "***-***-1234"
    assert redacted["user"]["name"] == "M*** J***"
    assert redacted["user"]["company"] == "A*** R***"
    assert "Mayank Jindal" not in str(redacted)
    assert "Acme Realty" not in str(redacted)
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


def test_event_bus_publisher_stores_claim_check_payload_only():
    """P0 claim-check: a fat payload is stored as exactly {lead_id, tenant_id}.

    Not the evidence — the live proof is scripts/prove_pii_claim_check.py.
    """
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
            "Client_7",
            "lead_101",
            {
                "lead_id": "101",
                "name": "John Doe",
                "email": "john.doe@company.com",
                "phone": "+919876543210",
                "notes": "Direct contact via personal@domain.com",
            }
        )

    asyncio.run(run())
    assert len(captured) == 1
    p = captured[0]["payload"]
    assert p == {"lead_id": 101, "tenant_id": "Client_7"}
    blob = json.dumps(p)
    assert "John Doe" not in blob
    assert "john.doe@company.com" not in blob
    assert "+919876543210" not in blob


# --------------------------------------------------------------------------- #
# 2. API Key Migration & Verification: Explicit State & 64-Char Hex Regression
# --------------------------------------------------------------------------- #

def test_legacy_token_hex_api_key_migration():
    """Regression Test: Prove a 64-char lowercase hex key from secrets.token_hex(32)

    migrates via explicit is_api_key_hashed state, authenticates, and raw unhashed
    value is rejected.
    """
    db = SessionLocal()
    try:
        # 1. Generate 64-character hex legacy key (simulating old add_client.py)
        legacy_raw = secrets.token_hex(32)
        assert len(legacy_raw) == 64
        assert legacy_raw.lower() == legacy_raw

        # Seed un-migrated legacy client
        client = Client(
            company_name="Legacy Hex Tenant",
            email=f"legacy_hex_{secrets.token_hex(4)}@example.com",
            hashed_password="dummy_pw",
            api_key=legacy_raw,
            is_api_key_hashed=False,
            is_active=True,
        )
        db.add(client)
        db.commit()
        db.refresh(client)
        cid = client.id

        # 2. Before migration: Forward-compatible dual-read authenticates raw key
        resolved_before = get_client_by_api_key(api_key_h=legacy_raw, api_key_q=None, db=db)
        assert resolved_before.id == cid

        # 3. Execute Migration Logic: hash only where is_api_key_hashed IS FALSE
        expected_hash = hashlib.sha256(legacy_raw.encode("utf-8")).hexdigest()
        assert expected_hash != legacy_raw  # SHA-256 of a 64-char hex is a different 64-char hex

        updated_count = db.query(Client).filter(
            Client.id == cid,
            Client.is_api_key_hashed.is_(False)
        ).update({
            "api_key": expected_hash,
            "is_api_key_hashed": True
        })
        db.commit()
        assert updated_count == 1

        # 4. Refresh and assert explicit state
        client_refreshed = db.query(Client).filter(Client.id == cid).first()
        assert client_refreshed.is_api_key_hashed is True
        assert client_refreshed.api_key == expected_hash

        # 5. Authenticate with original raw key (via header X-API-Key)
        resolved_after = get_client_by_api_key(api_key_h=legacy_raw, api_key_q=None, db=db)
        assert resolved_after.id == cid
        assert resolved_after.api_key == expected_hash

        # 6. Prove raw unhashed value in database is rejected (no plaintext remains in DB)
        raw_db_match = db.query(Client).filter(Client.api_key == legacy_raw).first()
        assert raw_db_match is None

        # 7. Prove attacker passing the raw database hash as an API key is rejected
        with pytest.raises(HTTPException) as exc_hash_as_key:
            get_client_by_api_key(api_key_h=expected_hash, api_key_q=None, db=db)
        assert exc_hash_as_key.value.status_code == 401

        # Clean up
        db.delete(client_refreshed)
        db.commit()
    finally:
        db.close()


def test_auth_dependency_rejects_query_string_keys():
    """Verify API keys passed via URL query parameter are strictly rejected with 400 Bad Request."""
    db = SessionLocal()
    try:
        raw_key = secrets.token_hex(32)
        hashed_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        client = Client(
            company_name="Query Test Tenant",
            email=f"query_test_{secrets.token_hex(4)}@example.com",
            hashed_password="pw",
            api_key=hashed_key,
            is_api_key_hashed=True,
            is_active=True,
        )
        db.add(client)
        db.commit()
        cid = client.id

        # 1. Query-string only -> 400 Bad Request
        with pytest.raises(HTTPException) as exc_query:
            get_client_by_api_key(api_key_h=None, api_key_q=raw_key, db=db)
        assert exc_query.value.status_code == 400
        assert "forbidden" in exc_query.value.detail.lower()

        # 2. Both header and query string provided -> 400 Bad Request (query string strictly disallowed)
        with pytest.raises(HTTPException) as exc_both:
            get_client_by_api_key(api_key_h=raw_key, api_key_q=raw_key, db=db)
        assert exc_both.value.status_code == 400

        # Clean up
        db.delete(client)
        db.commit()
    finally:
        db.close()


def test_auth_dependency_valid_invalid_and_revoked_keys():
    """Verify Depends(get_client_by_api_key) accepts valid hashed keys and rejects invalid/revoked keys."""
    db = SessionLocal()
    try:
        active_raw = "active-test-key-p0"
        active_hash = hashlib.sha256(active_raw.encode("utf-8")).hexdigest()
        revoked_raw = "revoked-test-key-p0"
        revoked_hash = hashlib.sha256(revoked_raw.encode("utf-8")).hexdigest()

        # Seed active client with hashed key
        c1 = db.query(Client).filter((Client.email == "active@test.com") | (Client.api_key == active_hash)).first()
        if not c1:
            c1 = Client(company_name="ActiveClient", email="active@test.com",
                        hashed_password="x", api_key=active_hash, is_api_key_hashed=True, is_active=True)
            db.add(c1)
        else:
            c1.api_key = active_hash
            c1.is_api_key_hashed = True
            c1.is_active = True

        # Seed revoked client (is_active=False) with hashed key
        c2 = db.query(Client).filter((Client.email == "revoked@test.com") | (Client.api_key == revoked_hash)).first()
        if not c2:
            c2 = Client(company_name="RevokedClient", email="revoked@test.com",
                        hashed_password="x", api_key=revoked_hash, is_api_key_hashed=True, is_active=False)
            db.add(c2)
        else:
            c2.api_key = revoked_hash
            c2.is_api_key_hashed = True
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
# 3. Fail-Closed RAG / Vector / Neo4j Retrieval on Missing Context & Unknown Metadata
# --------------------------------------------------------------------------- #

def test_rag_chunk_fails_closed_on_missing_context():
    """Verify private tenant chunks and unknown metadata fail closed."""
    # Private chunk belonging to tenant 9
    private_chunk = {"client_id": 9, "location": "Baner", "details": "Private project"}

    # Public FAQ chunk explicitly marked public
    public_chunk_tagged = {"is_public": True, "location": "Pune", "details": "City FAQ"}

    # Untagged chunk with missing tenant ID and missing is_public flag (unknown metadata)
    untagged_chunk = {"location": "Pune", "details": "General FAQ"}

    # 1. Private chunk with missing tenant context (client_id=None) -> MUST FAIL CLOSED
    assert _chunk_visible(private_chunk, client_id=None) is False

    # 2. Private chunk accessed by foreign tenant (client_id=3) -> MUST FAIL CLOSED
    assert _chunk_visible(private_chunk, client_id=3) is False

    # 3. Private chunk accessed by legitimate owner (client_id=9) -> ALLOWED
    assert _chunk_visible(private_chunk, client_id=9) is True

    # 4. Explicit public chunk is visible to all
    assert _chunk_visible(public_chunk_tagged, client_id=None) is True
    assert _chunk_visible(public_chunk_tagged, client_id=3) is True

    # 5. UNKNOWN METADATA FAILS CLOSED: untagged chunk MUST NOT be treated as public
    assert _chunk_visible(untagged_chunk, client_id=None) is False
    assert _chunk_visible(untagged_chunk, client_id=3) is False

    # 6. Malformed items fail closed
    assert _chunk_visible("not_a_dict", client_id=9) is False
    assert _chunk_visible(None, client_id=9) is False


def test_neo4j_retrieval_fails_closed_on_missing_or_down():
    """Verify GraphClient fails closed to empty dict when context cannot be established.

    Note: ``kg=None`` falls back to the global ``knowledge_graph`` singleton, so
    availability here is environment-dependent (Local Neo4j may be up). Use an
    explicitly unavailable stub and a degraded stub for deterministic fail-closed
    checks.
    """

    class _Down:
        available = False

    class _Degraded:
        available = True

        def get_similar_leads(self, *args, **kwargs):
            raise RuntimeError("neo4j down")

    gc_down = GraphClient(kg=_Down())
    assert gc_down.available is False
    assert gc_down.get_lead_context(lead_id=1, client_id=1) == {}

    gc_degraded = GraphClient(kg=_Degraded())
    assert gc_degraded.available is True
    assert gc_degraded.get_lead_context(lead_id=1, client_id=1) == {}


def test_dlq_fails_closed_on_missing_session():
    """Verify DLQ replay returns False when session does not exist."""
    db = SessionLocal()
    try:
        payload = {
            "session_id": "nonexistent_session_999999",
            "stage": "Day 0",
            "lead_data": {"name": "Test"},
        }
        success = process_ml_followup(payload, db, event_client_id=1)
        assert success is False
    finally:
        db.close()


def test_dlq_fails_closed_on_tenant_mismatch():
    """Verify DLQ replay returns False when session client_id does not match event client_id."""
    db = SessionLocal()
    try:
        sess = db.query(SessionModel).filter(SessionModel.id == "dlq_tenant_mismatch_sess").first()
        if not sess:
            sess = SessionModel(id="dlq_tenant_mismatch_sess", client_id=1)
            db.add(sess)
            db.commit()

        payload = {
            "session_id": "dlq_tenant_mismatch_sess",
            "stage": "Day 0",
            "lead_data": {"name": "Test"},
        }
        success = process_ml_followup(payload, db, event_client_id=2)
        assert success is False
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# 5. Deep Cross-Tenant Negative-Access Isolation Tests (Read, Update, Delete, Export, Webhook)
# --------------------------------------------------------------------------- #

def test_cross_tenant_negative_access_deep():
    """Exhaustive Negative-Access Test Suite:

    Proves Client B receives 403/404 when targeting Client A's resources across:
    - READ: Lead score, timeline, memory, prediction
    - UPDATE: PATCH lead stage
    - DELETE: DELETE lead
    - POST: Sales-AI trigger, store memory
    - EXPORT: Client B export excludes Client A records
    - WEBHOOK / QUERY STRING: Query-string key rejection (400)
    """
    db = SessionLocal()
    try:
        # 1. Setup Tenant A
        raw_key_a = "secret-client-a-key-p0"
        hash_a = hashlib.sha256(raw_key_a.encode("utf-8")).hexdigest()
        ca = db.query(Client).filter((Client.email == "tenant_a_deep@test.com") | (Client.api_key == hash_a)).first()
        if not ca:
            ca = Client(company_name="Tenant A Corp", email="tenant_a_deep@test.com",
                        hashed_password="pw", api_key=hash_a, is_api_key_hashed=True, is_active=True)
            db.add(ca)
            db.commit()
            db.refresh(ca)
        else:
            ca.api_key = hash_a
            ca.is_api_key_hashed = True
            ca.is_active = True
            db.commit()

        # 2. Setup Tenant B
        raw_key_b = "secret-client-b-key-p0"
        hash_b = hashlib.sha256(raw_key_b.encode("utf-8")).hexdigest()
        cb = db.query(Client).filter((Client.email == "tenant_b_deep@test.com") | (Client.api_key == hash_b)).first()
        if not cb:
            cb = Client(company_name="Tenant B Corp", email="tenant_b_deep@test.com",
                        hashed_password="pw", api_key=hash_b, is_api_key_hashed=True, is_active=True)
            db.add(cb)
            db.commit()
            db.refresh(cb)
        else:
            cb.api_key = hash_b
            cb.is_api_key_hashed = True
            cb.is_active = True
            db.commit()

        # Generate JWT Bearer tokens for Dashboard operations
        jwt_b = create_access_token(data={"sub": str(cb.id)})

        # Ensure session and private lead for Tenant A
        session_a = db.query(SessionModel).filter(SessionModel.id == "deep_session_a").first()
        if not session_a:
            session_a = SessionModel(id="deep_session_a", client_id=ca.id)
            db.add(session_a)
            db.commit()

        lead_a = db.query(Lead).filter(Lead.client_id == ca.id, Lead.phone == "+919999900099").first()
        if not lead_a:
            lead_a = Lead(
                client_id=ca.id,
                session_id="deep_session_a",
                name="Tenant A Confidential Lead",
                phone="+919999900099",
                location="Koregaon Park",
                budget="5Cr",
                property_type="Villa",
                funnel_stage="New",
            )
            db.add(lead_a)
            db.commit()
            db.refresh(lead_a)
        lead_a_id = lead_a.id

        with TestClient(app) as client:
            headers_b_jwt = {"Authorization": f"Bearer {jwt_b}"}
            headers_b_api = {"X-API-Key": raw_key_b}

            # --- NEGATIVE READ PATHS ---
            # 1. Timeline (API Key auth)
            r = client.get(f"/api/v1/events/leads/{lead_a_id}/timeline", headers=headers_b_api)
            assert r.status_code == 404

            # 2. Score endpoint (JWT auth)
            r = client.get(f"/api/v1/leads/{lead_a_id}/score", headers=headers_b_jwt)
            assert r.status_code == 404

            # 3. Memory recall (JWT auth)
            r = client.get(f"/api/v1/leads/{lead_a_id}/memory", headers=headers_b_jwt)
            assert r.status_code == 404

            # 4. Prediction endpoint (JWT auth)
            r = client.get(f"/api/v1/leads/{lead_a_id}/prediction", headers=headers_b_jwt)
            assert r.status_code == 404

            # --- NEGATIVE UPDATE PATH ---
            # 5. PATCH lead stage
            r = client.patch(
                f"/api/v1/leads/{lead_a_id}/stage",
                json={"stage": "Contacted"},
                headers=headers_b_jwt,
            )
            assert r.status_code == 404

            # --- NEGATIVE POST PATHS ---
            # 6. Sales-AI trigger
            r = client.post(f"/api/v1/leads/{lead_a_id}/sales-ai", headers=headers_b_jwt)
            assert r.status_code == 404

            # 7. Store memory
            r = client.post(
                f"/api/v1/leads/{lead_a_id}/memory",
                json={"key": "budget_flexibility", "value": "strict"},
                headers=headers_b_jwt,
            )
            assert r.status_code == 404

            # --- NEGATIVE DELETE PATH ---
            # 8. DELETE lead
            r = client.delete(f"/api/v1/leads/{lead_a_id}", headers=headers_b_jwt)
            assert r.status_code == 404
            # Verify Lead A still exists untouched
            assert db.query(Lead).filter(Lead.id == lead_a_id).first() is not None

            # --- EXPORT ISOLATION PATH ---
            # 9. Client B exporting leads must NEVER leak Client A's data
            r = client.get("/api/v1/leads/export", headers=headers_b_jwt)
            assert r.status_code == 200
            assert "+919999900099" not in r.text
            assert "Tenant A Confidential Lead" not in r.text

            # --- URL QUERY-STRING API KEY REJECTION ---
            # 10. Attempting query-string authentication MUST fail with 400
            r = client.post(f"/api/v1/chat?api_key={raw_key_a}&session_id=test&message=hello")
            assert r.status_code == 400
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# 6. INF-01 S3 Backup Mock Execution (Moto): KMS, Checksum, and Lifecycle
# --------------------------------------------------------------------------- #

@mock_aws
def test_s3_backup_mock_execution_moto():
    """INF-01 Verification: Execute and verify full backup-to-S3 path using Moto.

    Asserts:
    1. Backup dump uploaded to S3 bucket
    2. Server-side encryption uses AWS KMS (aws:kms) with specified KMS Key ARN
    3. Cryptographic SHA-256 checksum file uploaded and matches local dump bytes
    4. 30-day lifecycle retention policy is properly configured on S3 bucket
    """
    region = "us-east-1"
    bucket_name = "real-estate-ai-lead-agent-backups"
    timestamp = "20261016_220000Z"

    # 1. Initialize AWS mock clients
    kms_client = boto3.client("kms", region_name=region)
    s3_client = boto3.client("s3", region_name=region)

    # 2. Provision mock KMS Key
    kms_res = kms_client.create_key(Description="DR Backup Encryption Key")
    kms_key_arn = kms_res["KeyMetadata"]["Arn"]

    # 3. Provision S3 Bucket
    s3_client.create_bucket(Bucket=bucket_name)

    # 4. Generate mock database snapshot payload
    raw_dump_bytes = b"PG_DUMP_FORMAT_C_BINARY_REVENUE_OS_BACKUP_DRILL_DATA"
    expected_sha256 = hashlib.sha256(raw_dump_bytes).hexdigest()

    # 5. Execute S3 Backup Pipeline
    result = run_s3_backup(
        dump_bytes=raw_dump_bytes,
        bucket_name=bucket_name,
        timestamp=timestamp,
        kms_key_arn=kms_key_arn,
        retention_days=30,
        region_name=region,
        s3_client=s3_client,
    )

    assert result["status"] == "success"
    assert result["sha256"] == expected_sha256

    dump_key = result["dump_key"]
    sha_key = result["sha_key"]

    # 6. Verify Dump Object & KMS Encryption in S3
    head_dump = s3_client.head_object(Bucket=bucket_name, Key=dump_key)
    assert head_dump["ServerSideEncryption"] == "aws:kms"
    assert head_dump["SSEKMSKeyId"] == kms_key_arn

    # 7. Verify SHA-256 Checksum in S3
    sha_obj = s3_client.get_object(Bucket=bucket_name, Key=sha_key)
    sha_body = sha_obj["Body"].read().decode("utf-8")
    assert expected_sha256 in sha_body

    # 8. Verify 30-Day Lifecycle Configuration in S3
    lifecycle = s3_client.get_bucket_lifecycle_configuration(Bucket=bucket_name)
    rules = lifecycle["Rules"]
    assert len(rules) == 1
    rule = rules[0]
    assert rule["ID"] == "DR-30-Day-Expiration-Policy"
    assert rule["Status"] == "Enabled"
    assert rule["Filter"]["Prefix"] == "postgres/automated/"
    assert rule["Expiration"]["Days"] == 30
    assert rule["NoncurrentVersionExpiration"]["NoncurrentDays"] == 7
