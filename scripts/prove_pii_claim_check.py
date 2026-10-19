"""P0 claim-check proof — the event bus stores exactly {lead_id, tenant_id}.

Local Postgres + Redis only (localhost/127.0.0.1/::1). Never Render.
No real WhatsApp send, no live HubSpot call (stubbed at the
``app.execution_engine.crm_executor._push_to_hubspot`` boundary), no Gemini call.

Prints ``PII_CLAIM_CHECK_PASS`` only when every assertion held. Exit 1 otherwise.
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from config import settings
from database import SessionLocal

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _fail(message: str) -> None:
    print(f"PII_PROOF_FAIL {message}")
    sys.exit(1)


def _host_of(url: str) -> str | None:
    try:
        return urlparse(url).hostname
    except Exception:
        return None


def _refuse_nonlocal() -> None:
    pg_url = settings.DATABASE_URL or ""
    if not pg_url.startswith("postgres"):
        print("Refusing proof: DATABASE_URL is not local postgres.")
        sys.exit(1)
    if _host_of(pg_url) not in _LOCAL_HOSTS:
        print("Refusing proof: DATABASE_URL host is not a local postgres host.")
        sys.exit(1)
    redis_host = _host_of(settings.REDIS_URL or "")
    if redis_host not in _LOCAL_HOSTS:
        print("Refusing proof: REDIS_URL host is not a local redis host.")
        sys.exit(1)


def _ensure_client_columns() -> None:
    db = SessionLocal()
    try:
        db.execute(text(
            "ALTER TABLE clients ADD COLUMN IF NOT EXISTS is_api_key_hashed BOOLEAN DEFAULT FALSE"
        ))
        db.execute(text(
            "ALTER TABLE clients ADD COLUMN IF NOT EXISTS twilio_phone_number VARCHAR"
        ))
        db.execute(text(
            "ALTER TABLE clients ADD COLUMN IF NOT EXISTS twilio_auth_token VARCHAR"
        ))
        db.execute(text(
            "ALTER TABLE clients ADD COLUMN IF NOT EXISTS twilio_account_sid VARCHAR"
        ))
        db.commit()
    finally:
        db.close()


def _pg_up() -> None:
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        print("local postgres is unreachable.")
        sys.exit(1)
    finally:
        db.close()


def _seed(tag: str, token: str, name: str, phone: str) -> tuple[int, int, str]:
    """New rows only: client + session + lead with a distinctive identity."""
    from models import Client, Lead, Session as SessionModel

    db = SessionLocal()
    try:
        client = Client(
            company_name=f"PII Proof {tag} {token}",
            email=f"pii-proof-{tag}-{token}@local.test",
            hashed_password="not-a-login",
            api_key=f"pii-proof-{tag}-{token}",
            is_api_key_hashed=False,
            is_active=True,
        )
        db.add(client)
        db.commit()
        db.refresh(client)
        session_id = f"{client.id}_pii-proof-{tag}-{token}"
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
            source="proof",
            visit_date="2026-11-05T10:00:00+05:30",
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)
        return client.id, lead.id, session_id
    finally:
        db.close()


async def _read_entries_async(r, stream: str) -> list[dict]:
    """Read raw envelopes using an existing connection + running loop."""
    entries = await r.xrange(stream, min="-", max="+")
    return [json.loads(fields["data"]) for _entry_id, fields in entries]


def _read_all_entries(stream: str) -> list[dict]:
    """Read every raw envelope straight from the Redis stream (no bus parsing)."""
    import redis.asyncio as aioredis

    async def run() -> list[dict]:
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            return await _read_entries_async(r, stream)
        finally:
            await r.aclose()

    return asyncio.run(run())


def main() -> None:
    _refuse_nonlocal()
    _pg_up()
    _ensure_client_columns()

    token = uuid.uuid4().hex[:12]
    proof_stream = f"ireios:proof:pii:{token}"
    name_a = f"Claimcheck A {token}"
    phone_a = f"+9191{token[:8]}"
    email_a = f"claimcheck-{token}@pii.test"
    name_b = f"Claimcheck B {token}"
    phone_b = f"+9192{token[:8]}"

    from app.clients.event_bus_client import event_bus
    from main import _emit_turn_events

    # Re-point the SHARED singleton at the proof stream so every path
    # (turn events, crm_automation, AE->EE publish) lands in one stream.
    event_bus.stream = proof_stream
    event_bus.group = f"ireios-proof-pii-{token}"

    client_a, lead_a, session_a = _seed("a", token, name_a, phone_a)
    client_b, lead_b, session_b = _seed("b", token, name_b, phone_b)
    tenant_a = f"Client_{client_a}"
    tenant_b = f"Client_{client_b}"
    print(f"seeded tenant_a={tenant_a} lead_a={lead_a} tenant_b={tenant_b} lead_b={lead_b}")
    print(f"proof_stream={proof_stream}")

    crm_calls: list[dict] = []

    async def drive() -> None:
        from models import Lead

        await event_bus.start()

        # ---- Case 1: the real turn publisher ----------------------------
        db = SessionLocal()
        try:
            lead_obj = db.query(Lead).filter(
                Lead.id == lead_a, Lead.client_id == client_a
            ).first()
            if lead_obj is None:
                _fail("case1: lead row missing")
            await _emit_turn_events(
                client_id=client_a,
                scoped_session_id=session_a,
                lead=lead_obj,
                source_channel="whatsapp",
                is_new_lead=True,
                message=f"Interested in {lead_obj.location} 3bhk",
                db=db,
            )
        finally:
            db.close()

        # ---- Case 2: fat payload straight into publish ------------------
        fat = {
            "lead_id": lead_a,
            "name": name_a,
            "phone": phone_a,
            "email": email_a,
            "to": phone_a,
            "body": f"Hi {name_a}, your visit is set",
            "location": f"Baner {token}",
            "assigned_agent": "Sneha Proof",
            "chat_context": f"User: buy {token}",
        }
        await event_bus.publish("lead.created", tenant_a, str(lead_a), fat, source="proof_fat")

        # ---- Case 3: ExecutionEngine success merge (to/body) ------------
        from app.execution_engine.execution_engine import ExecutionEngine

        class _StubExecutor:
            action_type = "send_whatsapp"

            async def execute(self, action_request: dict) -> dict:
                return {"status": "success", "to": phone_a, "body": f"Reply to {name_a}"}

        ee = ExecutionEngine(session_factory=SessionLocal, bus=event_bus)
        ee.register("send_whatsapp", _StubExecutor())
        ee.register_event("send_whatsapp", "whatsapp.sent")
        await ee._publish_success(
            {
                "action_type": "send_whatsapp",
                "tenant_id": tenant_a,
                "entity_id": str(lead_a),
                "parameters": {"to": phone_a, "body": f"Offer to {name_a}"},
            },
            {"status": "success", "to": phone_a, "body": f"Reply to {name_a}"},
        )

        # ---- Case 4: crm_automation on the stored lead.created envelope --
        # Register the real executors so AE->EE dispatch reaches CRMExecutor.
        from app.execution_engine.registry import register_executors

        register_executors()

        async def fake_push(payload: dict) -> dict:
            crm_calls.append(payload.get("properties") or {})
            return {"id": f"fake-crm-{token}"}

        import app.execution_engine.crm_executor as crm_executor_mod

        crm_executor_mod._push_to_hubspot = fake_push

        envelopes_now = await _read_entries_async(event_bus._pub_redis, proof_stream)
        created = next(
            (e for e in envelopes_now if e.get("event_type") == "lead.created"
             and (e.get("payload") or {}).get("lead_id") == lead_a),
            None,
        )
        if created is None:
            _fail("case4: stored lead.created envelope not found")

        from app.workflows.crm_automation import crm_automation_handler

        await crm_automation_handler(created)

        # ---- Case 5: followup_arm from the lead row ---------------------
        from app.workflows.followup_arm import on_lead_created

        await on_lead_created(created)

    try:
        asyncio.run(drive())

        # ---- Assertions over the raw stream -----------------------------
        envelopes = _read_all_entries(proof_stream)
        print(f"raw_entries={len(envelopes)}")
        if not envelopes:
            _fail("no raw entries on the proof stream")

        for i, env in enumerate(envelopes):
            payload = env.get("payload") or {}
            expected_tenant = env.get("tenant_id")
            if expected_tenant == tenant_a:
                _assert_two_keys(env, lead_a, tenant_a, f"entry#{i}:{env.get('event_type')}")
            elif expected_tenant == tenant_b:
                _assert_two_keys(env, lead_b, tenant_b, f"entry#{i}:{env.get('event_type')}")
            else:
                _fail(f"entry#{i}: unexpected tenant {expected_tenant!r}")
            blob = json.dumps(payload)
            for secret in (name_a, phone_a, email_a, name_b, phone_b):
                if secret in blob:
                    _fail(f"entry#{i} ({env.get('event_type')}): leaked {secret!r}")
        print(f"claim_check_entries_ok={len(envelopes)}")

        # ---- CRM boundary assertion -------------------------------------
        from models import Lead

        db = SessionLocal()
        try:
            row = db.query(Lead).filter(Lead.id == lead_a, Lead.client_id == client_a).first()
            expected_name = row.name
            expected_phone = row.phone
        finally:
            db.close()
        if not crm_calls:
            _fail("crm: _push_to_hubspot was never called")
        props = crm_calls[-1]
        if props.get("firstname") != expected_name or props.get("phone") != expected_phone:
            _fail(f"crm properties {props!r} do not match live row ({expected_name!r}, {expected_phone!r})")
        if props.get("firstname") == "Unknown":
            _fail("crm properties carried 'Unknown' instead of the row name")
        print(f"crm_properties_ok firstname={props.get('firstname')!r} phone={props.get('phone')!r}")

        # ---- Follow-up arm assertions ------------------------------------
        from models import FollowUpState

        db = SessionLocal()
        try:
            armed = db.query(FollowUpState).filter(FollowUpState.session_id == session_a).first()
            if armed is None:
                _fail("followup: no FollowUpState armed for A's session from the lead row")
            if armed.client_id != client_a:
                _fail(f"followup: armed client_id={armed.client_id}, expected {client_a}")
            print(f"followup_armed session={session_a} client={armed.client_id}")
            before_b = db.query(FollowUpState).filter(FollowUpState.client_id == client_b).count()
        finally:
            db.close()

        from app.workflows.followup_arm import on_lead_created

        foreign_event = {
            "event_type": "lead.created",
            "tenant_id": tenant_b,
            "entity_id": str(lead_a),
            "payload": {"lead_id": lead_a, "tenant_id": tenant_b},
        }
        asyncio.run(on_lead_created(foreign_event))
        db = SessionLocal()
        try:
            after_b = db.query(FollowUpState).filter(FollowUpState.client_id == client_b).count()
            if after_b != before_b:
                _fail(f"followup: foreign tenant armed (before={before_b}, after={after_b})")
            print(f"foreign_tenant_no_arm before={before_b} after={after_b}")
        finally:
            db.close()

        print("PII_CLAIM_CHECK_PASS")
    finally:
        _cleanup(client_a, client_b, session_a, session_b, proof_stream)


def _assert_two_keys(envelope: dict, expect_lead_id: int | None, expect_tenant: str, ctx: str) -> None:
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        _fail(f"{ctx}: payload is not a dict: {payload!r}")
    expected = {"lead_id": expect_lead_id, "tenant_id": expect_tenant}
    if payload != expected:
        _fail(f"{ctx}: payload {payload!r} != {expected!r}")


def _cleanup(client_a: int, client_b: int, session_a: str, session_b: str, proof_stream: str) -> None:
    import redis.asyncio as aioredis
    from models import (
        Client,
        DLQEvent,
        EventLog,
        FollowUpState,
        Lead,
        Message,
        Session as SessionModel,
    )

    db = SessionLocal()
    try:
        for cid in (client_a, client_b):
            db.query(FollowUpState).filter(FollowUpState.client_id == cid).delete(synchronize_session=False)
            db.query(DLQEvent).filter(DLQEvent.client_id == cid).delete(synchronize_session=False)
            db.query(EventLog).filter(EventLog.client_id == cid).delete(synchronize_session=False)
        db.query(Message).filter(Message.session_id.in_([session_a, session_b])).delete(synchronize_session=False)
        db.query(Lead).filter(Lead.client_id.in_([client_a, client_b])).delete(synchronize_session=False)
        db.query(SessionModel).filter(SessionModel.id.in_([session_a, session_b])).delete(synchronize_session=False)
        db.query(Client).filter(Client.id.in_([client_a, client_b])).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()

    async def drop_stream():
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            await r.delete(proof_stream)
        finally:
            await r.aclose()

    asyncio.run(drop_stream())
    print("cleanup_done")


if __name__ == "__main__":
    main()
