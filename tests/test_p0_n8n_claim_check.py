"""P0 n8n claim-check evidence.

The Redis stream stores exactly ``{"lead_id", "tenant_id"}``. The n8n bridge
rebuilds the webhook body from the tenant-owned Postgres row immediately
before POST. These tests are the evidence for the bridge hydration pass.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from unittest.mock import MagicMock

from sqlalchemy import text

from app.automation_engine import n8n_claim
from app.automation_engine.n8n_bridge import N8NBridge
from app.clients.event_bus_client import EventBusClient
from database import SessionLocal
from models import ApprovalRequest, Client, Lead, Session as SessionModel


def _bus_capture():
    captured = []
    fake_redis = MagicMock()

    async def fake_xadd(stream, fields):
        captured.append(json.loads(fields["data"]))
        return "1-0"

    fake_redis.xadd = fake_xadd
    bus = EventBusClient(stream="test_stream", group="test_group")
    bus._running = True
    bus._pub_redis = fake_redis
    return bus, captured


class _RecordingClient:
    configured = True

    def __init__(self):
        self.calls = []

    async def trigger_workflow(self, workflow_id, payload):
        self.calls.append((workflow_id, payload))
        return {"status": "success", "workflow_id": workflow_id}


def _ensure_client_columns() -> None:
    db = SessionLocal()
    try:
        db.execute(
            text(
                "ALTER TABLE clients ADD COLUMN IF NOT EXISTS "
                "is_api_key_hashed BOOLEAN DEFAULT FALSE"
            )
        )
        db.commit()
    finally:
        db.close()


def _seed_client(
    token: str,
    tag: str,
    *,
    name: str,
    phone: str,
    created_clients: list[int],
) -> tuple[int, int, str]:
    _ensure_client_columns()
    db = SessionLocal()
    try:
        client = Client(
            company_name=f"N8N Claim {tag} {token}",
            email=f"n8n-claim-{tag}-{token}@local.test",
            hashed_password="not-a-login",
            api_key=f"n8n-claim-{tag}-{token}",
            is_api_key_hashed=False,
            is_active=True,
        )
        db.add(client)
        db.commit()
        db.refresh(client)
        created_clients.append(client.id)

        session_id = f"{client.id}_n8n-claim-{tag}-{token}"
        db.add(SessionModel(id=session_id, client_id=client.id))
        lead = Lead(
            session_id=session_id,
            client_id=client.id,
            name=name,
            phone=phone,
            location=f"Claimcheck {tag} {token}",
            budget="75L",
            property_type="2BHK",
            intent="buy",
            source="n8n_claim_test",
            visit_date="2026-11-05T10:00:00+05:30",
            conversion_probability=91,
            assigned_agent="Agent A",
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)
        return client.id, lead.id, session_id
    finally:
        db.close()


def _cleanup(client_ids: list[int]) -> None:
    db = SessionLocal()
    try:
        for client_id in client_ids:
            db.execute(
                text("DELETE FROM n8n_claim_context WHERE client_id = :client_id"),
                {"client_id": client_id},
            )
            db.query(ApprovalRequest).filter(
                ApprovalRequest.client_id == client_id
            ).delete(synchronize_session=False)
            db.query(Lead).filter(Lead.client_id == client_id).delete(
                synchronize_session=False
            )
            db.query(SessionModel).filter(
                SessionModel.client_id == client_id
            ).delete(synchronize_session=False)
            db.query(Client).filter(Client.id == client_id).delete(
                synchronize_session=False
            )
        db.commit()
    finally:
        db.close()


def _lead_hot_envelope(client_id: int, lead_id: int, **payload) -> dict:
    base = {"lead_id": lead_id, "tenant_id": f"Client_{client_id}"}
    base.update(payload)
    return {
        "event_id": f"e-{uuid.uuid4().hex[:8]}",
        "event_type": "lead.hot",
        "tenant_id": f"Client_{client_id}",
        "entity_id": str(lead_id),
        "source": "test",
        "timestamp": "2026-10-20T10:00:00+00:00",
        "correlation_id": "corr-1",
        "payload": base,
    }


def test_bus_stores_identifiers_only():
    bus, captured = _bus_capture()
    token = uuid.uuid4().hex[:10]
    name = f"Claimcheck {token}"
    phone = f"+9198{token[:8]}"
    email = f"{token}@pii.test"

    async def run():
        await bus.publish(
            "lead.created",
            "Client_7",
            "101",
            {
                "lead_id": "101",
                "name": name,
                "phone": phone,
                "email": email,
                "to": phone,
                "body": f"Hi {name}",
                "chat_context": f"User: {name}",
                "location": "Baner",
                "assigned_agent": "Agent X",
                "trigger": "hot_threshold",
                "visit_id": "visit_1",
            },
        )

    asyncio.run(run())
    assert len(captured) == 1
    assert captured[0]["payload"] == {"lead_id": 101, "tenant_id": "Client_7"}
    blob = json.dumps(captured[0])
    for secret in (name, phone, email):
        assert secret not in blob


def test_hydration_is_tenant_scoped():
    token = uuid.uuid4().hex[:10]
    a_name = f"Claim A {token}"
    a_phone = f"+9191{token[:8]}"
    b_name = f"Claim B {token}"
    b_phone = f"+9192{token[:8]}"
    html_link = f"https://calendar.google.com/calendar/event?eid={token}"
    created: list[int] = []
    try:
        a_client, a_lead, _ = _seed_client(
            token, "a", name=a_name, phone=a_phone, created_clients=created
        )
        b_client, b_lead, _ = _seed_client(
            token, "b", name=b_name, phone=b_phone, created_clients=created
        )
        assert n8n_claim.upsert_claim(
            a_client,
            a_lead,
            "lead.hot",
            trigger="human_handoff",
            html_link=html_link,
        )

        client = _RecordingClient()
        bridge = N8NBridge(n8n_client=client)

        out_a = asyncio.run(bridge.forward_envelope(_lead_hot_envelope(a_client, a_lead)))
        assert out_a["status"] == "success"
        assert len(client.calls) == 1
        posted_a = client.calls[0][1]["payload"]
        assert posted_a["name"] == a_name
        assert posted_a["phone"] == a_phone
        assert posted_a["trigger"] == "human_handoff"
        assert b_phone not in json.dumps(posted_a)

        out_b = asyncio.run(bridge.forward_envelope(_lead_hot_envelope(b_client, a_lead)))
        assert out_b["error"] == "n8n_claim_denied"
        assert len(client.calls) == 1
        denied_blob = json.dumps(out_b)
        for secret in (a_name, a_phone, html_link):
            assert secret not in denied_blob

        row_phone = f"+9193{token[:8]}"
        db = SessionLocal()
        try:
            db.query(Lead).filter(Lead.id == a_lead).update({"phone": row_phone})
            db.commit()
        finally:
            db.close()

        out_injected = asyncio.run(
            bridge.forward_envelope(
                _lead_hot_envelope(
                    a_client,
                    a_lead,
                    phone=a_phone,
                    name="Injected Name",
                )
            )
        )
        assert out_injected["status"] == "success"
        posted_injected = client.calls[-1][1]["payload"]
        assert posted_injected["phone"] == row_phone
        assert posted_injected["name"] == a_name
        assert a_phone not in json.dumps(posted_injected)
    finally:
        _cleanup(created)


def test_approval_hydration_is_tenant_scoped():
    token = uuid.uuid4().hex[:10]
    a_name = f"Approval A {token}"
    created: list[int] = []
    try:
        a_client, a_lead, _ = _seed_client(
            token, "aa", name=a_name, phone=f"+9194{token[:8]}", created_clients=created
        )
        b_client, _, _ = _seed_client(
            token, "bb", name=f"Approval B {token}", phone=f"+9195{token[:8]}",
            created_clients=created,
        )

        db = SessionLocal()
        try:
            approval = ApprovalRequest(
                client_id=a_client,
                entity_id=str(a_lead),
                action_type="send_whatsapp",
                action_payload={"lead_id": a_lead},
                status="pending",
            )
            db.add(approval)
            db.commit()
            db.refresh(approval)
            approval_id = approval.id
        finally:
            db.close()

        client = _RecordingClient()
        bridge = N8NBridge(n8n_client=client)
        env_a = {
            "event_id": f"approval-{token}",
            "event_type": "approval.requested",
            "tenant_id": f"Client_{a_client}",
            "entity_id": str(a_lead),
            "payload": {"lead_id": None, "tenant_id": f"Client_{a_client}"},
        }
        out_a = asyncio.run(bridge.forward_envelope(env_a))
        assert out_a["status"] == "success"
        posted = client.calls[0][1]["payload"]
        assert posted["approval_id"] == approval_id
        assert posted["action_type"] == "send_whatsapp"
        assert posted["name"] == a_name

        env_b = dict(env_a)
        env_b["tenant_id"] = f"Client_{b_client}"
        env_b["payload"] = {"lead_id": None, "tenant_id": f"Client_{b_client}"}
        out_b = asyncio.run(bridge.forward_envelope(env_b))
        assert out_b["error"] == "n8n_claim_denied"
        denied_blob = json.dumps(out_b)
        assert str(approval_id) not in denied_blob
        assert a_name not in denied_blob
    finally:
        _cleanup(created)


def test_marketing_hydration_uses_resolved_tenant(monkeypatch):
    token = uuid.uuid4().hex[:10]
    created: list[int] = []
    try:
        a_client, _, _ = _seed_client(
            token, "mk", name=f"Marketing {token}", phone=f"+9196{token[:8]}",
            created_clients=created,
        )
        seen: list[int] = []

        def fake_segment(db, client_id):
            seen.append(client_id)
            return {
                "total_open": 3,
                "hot": [1, 2],
                "warm": [3],
                "cold": [],
                "counts": {"hot": 2, "warm": 1, "cold": 0},
            }

        monkeypatch.setattr(n8n_claim, "segment_leads", fake_segment)

        client = _RecordingClient()
        bridge = N8NBridge(n8n_client=client)
        env = {
            "event_id": f"marketing-{token}",
            "event_type": "marketing.report.generated",
            "tenant_id": f"Client_{a_client}",
            "entity_id": "marketing",
            "payload": {"lead_id": None, "tenant_id": f"Client_{a_client}"},
        }
        out = asyncio.run(bridge.forward_envelope(env))
        assert out["status"] == "success"
        assert seen == [a_client]

        posted = client.calls[0][1]["payload"]
        assert posted["segments"]["hot"]["count"] == 2
        assert posted["segments"]["warm"]["count"] == 1
        assert posted["segments"]["cold"]["count"] == 0
        assert not isinstance(posted["segments"]["hot"], list)
        assert isinstance(posted["suggestions"], list)
        assert posted["suggestions"][0]["segment"] == "hot"
        assert "channel" in posted["suggestions"][0]
        assert "message" in posted["suggestions"][0]
        blob = json.dumps(posted)
        assert "lead_id" not in blob
        assert "[1, 2]" not in blob
    finally:
        _cleanup(created)


def test_qualified_and_site_visit_hydration():
    token = uuid.uuid4().hex[:10]
    created: list[int] = []
    try:
        a_client, a_lead, _ = _seed_client(
            token, "sv", name=f"Visit {token}", phone=f"+9197{token[:8]}",
            created_clients=created,
        )
        client = _RecordingClient()
        bridge = N8NBridge(n8n_client=client)

        env_q = {
            "event_id": f"qualified-{token}",
            "event_type": "lead.qualified",
            "tenant_id": f"Client_{a_client}",
            "entity_id": str(a_lead),
            "payload": {"lead_id": a_lead, "tenant_id": f"Client_{a_client}"},
        }
        out_q = asyncio.run(bridge.forward_envelope(env_q))
        assert out_q["status"] == "success"
        posted_q = client.calls[-1][1]["payload"]
        assert posted_q["name"] == f"Visit {token}"
        assert posted_q["visit_date"] == "2026-11-05T10:00:00+05:30"

        assert n8n_claim.upsert_claim(
            a_client,
            a_lead,
            "site_visit.scheduled",
            visit_id="visit_x",
            html_link=f"https://calendar.google.com/calendar/event?eid={token}",
            provider="google_calendar",
        )
        env_v = {
            "event_id": f"visit-{token}",
            "event_type": "site_visit.scheduled",
            "tenant_id": f"Client_{a_client}",
            "entity_id": str(a_lead),
            "payload": {"lead_id": a_lead, "tenant_id": f"Client_{a_client}"},
        }
        out_v = asyncio.run(bridge.forward_envelope(env_v))
        assert out_v["status"] == "success"
        posted_v = client.calls[-1][1]["payload"]
        assert posted_v["visit_id"] == "visit_x"
        assert posted_v["provider"] == "google_calendar"
        assert posted_v["html_link"].startswith("https://calendar.google.com/")

        db = SessionLocal()
        try:
            db.execute(
                text(
                    "DELETE FROM n8n_claim_context "
                    "WHERE client_id = :client_id AND lead_id = :lead_id "
                    "AND event_type = 'site_visit.scheduled'"
                ),
                {"client_id": a_client, "lead_id": a_lead},
            )
            db.commit()
        finally:
            db.close()

        out_v2 = asyncio.run(bridge.forward_envelope(env_v))
        assert out_v2["status"] == "success"
        posted_v2 = client.calls[-1][1]["payload"]
        assert "visit_id" not in posted_v2
        assert posted_v2["name"] == f"Visit {token}"
    finally:
        _cleanup(created)


def test_claim_context_has_no_pii_columns():
    db = SessionLocal()
    try:
        n8n_claim.ensure_claim_table(db)
        rows = db.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'n8n_claim_context'"
            )
        ).fetchall()
    finally:
        db.close()

    columns = {row[0] for row in rows}
    for prohibited in ("name", "phone", "email", "message", "chat_context", "notes"):
        assert prohibited not in columns
    assert {
        "client_id",
        "lead_id",
        "event_type",
        "trigger",
        "visit_id",
        "html_link",
        "provider",
        "action_type",
        "approval_id",
    } <= columns
