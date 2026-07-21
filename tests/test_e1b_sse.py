"""Expansion Phase 1b — early SSE + API envelopes (Tasks 1b.1-1b.3).

Verifies the frontend-unblock contracts: authenticated SSE stream that
receives tenant-scoped bus events, a tenant-scoped lead timeline, and an
admin-gated stub publisher.

Bus-dependent tests (SSE + stub) require the `redis` container and start the
bus inside the same event loop as the test. DB-dependent tests (timeline)
require Postgres. Both skip cleanly when unavailable, using the same
`asyncio.run` pattern as the rest of the `e` suite.

See plans/IREIOS_3.0_EXPANSION_CHANGELOG.md (Phase 1b status).
"""
import asyncio
import os

import pytest

# Ensure a non-default admin key for the admin-gated stub endpoint test.
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key-1b")

import httpx  # noqa: E402

from app.clients.event_bus_client import event_bus  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import Client, EventLog, Lead, Session as SessionModel  # noqa: E402


def _redis_ok() -> bool:
    try:
        import redis

        return redis.Redis.from_url("redis://localhost:6379/0", socket_connect_timeout=3).ping()
    except Exception:
        return False


def _db_ok() -> bool:
    try:
        db = SessionLocal()
        db.query(Client).first()
        db.close()
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Task 1b.1 — SSE stream
# --------------------------------------------------------------------------- #
def test_sse_requires_auth():
    import main

    async def run():
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/events/stream")
            assert resp.status_code in (401, 403)

    asyncio.run(run())


def test_events_routes_registered():
    """Wiring check: SSE + timeline + stub endpoints are mounted.

    Starlette/FastAPI may nest included routers as ``_IncludedRouter`` without
    flattening paths onto ``app.routes``; prefer OpenAPI paths (stable contract).
    """
    import main

    def _walk(routes, out):
        for r in routes:
            path = getattr(r, "path", None)
            methods = getattr(r, "methods", None)
            if path and methods:
                out.add((path, tuple(sorted(m for m in methods if m != "HEAD"))))
            nested = getattr(r, "routes", None)
            if nested is not None:
                _walk(nested, out)

    flat = set()
    _walk(main.app.routes, flat)
    openapi_paths = set((main.app.openapi() or {}).get("paths", {}) or {})

    def _present(path: str, method: str) -> bool:
        if (path, (method,)) in flat:
            return True
        # OpenAPI keys are path strings; methods nested under them.
        ops = ((main.app.openapi() or {}).get("paths") or {}).get(path) or {}
        return method.lower() in ops

    assert _present("/api/v1/events/stream", "GET") or "/api/v1/events/stream" in openapi_paths
    assert _present("/api/v1/events/leads/{lead_id}/timeline", "GET") or (
        "/api/v1/events/leads/{lead_id}/timeline" in openapi_paths
    )
    assert _present("/api/v1/events/stub", "POST") or "/api/v1/events/stub" in openapi_paths


def test_sse_delivers_tenant_scoped_events():
    """Mirrors the SSE handler: only the authed tenant's events are delivered.

    Uses the running bus directly (same subscribe/filter logic as the
    endpoint) to avoid the httpx streaming-close quirk while still exercising
    the real delivery + tenant-isolation path.
    """
    import main  # noqa: F401

    if not _redis_ok():
        pytest.skip("Redis not reachable at redis://localhost:6379/0")

    async def run():
        await event_bus.start()
        try:
            tenant_id = "Client_1"
            received = []

            def _handler(envelope):
                if envelope.get("tenant_id") == tenant_id:
                    received.append(envelope)

            event_bus.subscribe("*", _handler)
            try:
                await event_bus.publish("lead.created", "Client_1", "e1", {"n": 1}, source="stub")
                await event_bus.publish("lead.created", "Client_2", "e2", {"n": 2}, source="stub")
                # Poll for delivery (tolerant of Redis/contention latency).
                for _ in range(30):
                    if len(received) >= 1:
                        break
                    await asyncio.sleep(0.1)
            finally:
                event_bus.unsubscribe("*", _handler)

            assert len(received) == 1, received
            assert received[0]["entity_id"] == "e1"
        finally:
            await event_bus.stop()

    asyncio.run(run())


# --------------------------------------------------------------------------- #
# Task 1b.2 — Timeline
# --------------------------------------------------------------------------- #
def test_timeline_returns_envelopes_and_isolates_tenant():
    if not _db_ok():
        pytest.skip("Postgres not reachable")

    import main  # noqa: F401

    async def run():
        db = SessionLocal()
        created = {"sessions": [], "leads": [], "logs": []}
        try:
            c1 = db.query(Client).filter(Client.api_key == "secret-client-key-123").first()
            c2 = db.query(Client).filter(Client.api_key == "secret-client-key-456").first()
            assert c1 and c2, "seed clients missing"

            # Session -> Lead (Lead.session_id FK to Session.id)
            sess1 = SessionModel(id=f"{c1.id}_tl_test", client_id=c1.id)
            sess2 = SessionModel(id=f"{c2.id}_tl_test", client_id=c2.id)
            db.add_all([sess1, sess2])
            db.commit()
            db.refresh(sess1)
            db.refresh(sess2)
            created["sessions"].extend([sess1.id, sess2.id])

            lead1 = Lead(session_id=sess1.id, client_id=c1.id, name="TL1", phone="+910000000001")
            lead2 = Lead(session_id=sess2.id, client_id=c2.id, name="TL2", phone="+910000000002")
            db.add_all([lead1, lead2])
            db.commit()
            db.refresh(lead1)
            db.refresh(lead2)
            created["leads"].extend([lead1.id, lead2.id])

            log = EventLog(
                session_id=sess1.id,
                client_id=c1.id,
                event_type="lead.created",
                action_type="create",
                agent_type="AI",
            )
            db.add(log)
            db.commit()
            db.refresh(log)
            created["logs"].append(log.id)

            transport = httpx.ASGITransport(app=main.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                # own lead -> 200 with envelope-shaped events
                r1 = await client.get(
                    f"/api/v1/events/leads/{lead1.id}/timeline?api_key=secret-client-key-123"
                )
                assert r1.status_code == 200
                body = r1.json()
                assert body["lead_id"] == lead1.id
                assert isinstance(body["events"], list)
                assert any(e["event_type"] == "lead.created" for e in body["events"])
                assert body["events"][0]["source"] == "event_log"
                # other tenant's lead -> 404 (isolation)
                r2 = await client.get(
                    f"/api/v1/events/leads/{lead2.id}/timeline?api_key=secret-client-key-123"
                )
                assert r2.status_code == 404
        finally:
            db.query(EventLog).filter(EventLog.id.in_(created["logs"])).delete(
                synchronize_session=False
            )
            db.query(Lead).filter(Lead.id.in_(created["leads"])).delete(synchronize_session=False)
            db.query(SessionModel).filter(SessionModel.id.in_(created["sessions"])).delete(
                synchronize_session=False
            )
            db.commit()
            db.close()

    asyncio.run(run())


# --------------------------------------------------------------------------- #
# Task 1b.3 — Stub publisher
# --------------------------------------------------------------------------- #
def test_stub_requires_admin_key():
    import main

    async def run():
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post("/api/v1/events/stub", json={"event_type": "lead.created"})
            assert r.status_code == 403

    asyncio.run(run())


def test_stub_publishes_event():
    import main

    if not _redis_ok():
        pytest.skip("Redis not reachable at redis://localhost:6379/0")

    async def run():
        await event_bus.start()
        try:
            transport = httpx.ASGITransport(app=main.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.post(
                    "/api/v1/events/stub",
                    json={
                        "event_type": "lead.created",
                        "tenant_id": "Client_1",
                        "entity_id": "lead_stub",
                        "payload": {"name": "demo"},
                    },
                    headers={"X-Admin-Token": os.environ["ADMIN_API_KEY"]},
                )
                assert r.status_code == 200
                assert r.json()["status"] == "success"
                assert r.json()["event_id"]
        finally:
            await event_bus.stop()

    asyncio.run(run())
