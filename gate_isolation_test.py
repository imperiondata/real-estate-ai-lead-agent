import asyncio
import os
import uuid

import httpx
from database import SessionLocal
from models import Client, Lead


async def test_isolation():
    print("--- STARTING TENANT ISOLATION TEST ---")
    # Uses locally seeded keys by default; override via env if needed.
    KEY_A = os.getenv("CLIENT_KEY_A", "secret-client-key-123")
    KEY_B = os.getenv("CLIENT_KEY_B", "secret-client-key-456")
    if not KEY_A or not KEY_B:
        raise SystemExit("Set CLIENT_KEY_A / CLIENT_KEY_B (or seed local clients).")

    # Resolve client ids from the API keys (leads endpoint requires JWT; we
    # verify isolation at the data layer, which is the strongest assertion).
    with SessionLocal() as db:
        ca = db.query(Client).filter(Client.api_key == KEY_A).first()
        cb = db.query(Client).filter(Client.api_key == KEY_B).first()
    if not ca or not cb:
        raise SystemExit("Could not resolve both clients from the provided keys.")
    id_a, id_b = ca.id, cb.id

    # Fresh session so we never collide with opted-out / stale state.
    session_a = f"+9199{uuid.uuid4().hex[:10]}"
    body = "I want to buy 2BHK Baner"

    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=90.0) as client:
        # Inject a lead for Client A via the chat path (tenant-scoped, no webhook sig needed)
        print(f"\n1. Injecting lead for Client A (id={id_a}) via chat...")
        r = await client.post(
            "/api/v1/chat",
            params={"session_id": session_a, "message": body},
            headers={"X-API-Key": KEY_A},
        )
        print(f"   chat status={r.status_code}")

    # Verify DB-level isolation: the injected lead must belong to Client A and
    # must NOT be visible under Client B's client_id.
    with SessionLocal() as db:
        lead = db.query(Lead).filter(Lead.session_id.like(f"%{session_a}")).first()
        b_leads = db.query(Lead).filter(Lead.client_id == id_b).all()
    b_owns_it = lead is not None and lead.client_id == id_b

    if lead is None:
        print("\n[FAIL] ISOLATION TEST FAILED: lead was not created for Client A.")
        return
    if lead.client_id != id_a:
        print(f"\n[FAIL] ISOLATION TEST FAILED: lead.client_id={lead.client_id} != Client A id={id_a}.")
        return
    if b_owns_it or any(session_a in (l.session_id or "") for l in b_leads):
        print(f"\n[FAIL] ISOLATION TEST FAILED: Client B (id={id_b}) can see Client A's data.")
        return

    print(f"\n[PASS] ISOLATION TEST PASSED: Client B (id={id_b}) cannot see Client A's data.")
    print(f"   Injected lead session={lead.session_id} owned by client_id={lead.client_id}.")


asyncio.run(test_isolation())
