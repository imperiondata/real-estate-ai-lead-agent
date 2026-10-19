"""P0 proof — active Neo4j tenant isolation (not the graph-down test).

Local Postgres + Neo4j only (localhost/127.0.0.1/::1). Never Render.
Requires ``GET /api/v1/graph/health`` to report ``available: true`` before any
isolation assertion — a 404 against a down graph is NOT isolation.

Prints ``GRAPH_ISOLATION_PASS`` only when every assertion held. Exit 1 otherwise.
"""
from __future__ import annotations

import hashlib
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
    print(f"GRAPH_PROOF_FAIL {message}")
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
    neo_uri = settings.NEO4J_URI or ""
    if not neo_uri:
        print("Refusing proof: NEO4J_URI is empty — graph is a no-op. Start local Neo4j.")
        sys.exit(1)
    if _host_of(neo_uri) not in _LOCAL_HOSTS:
        print("Refusing proof: NEO4J_URI host is not local.")
        sys.exit(1)


def _pg_up() -> None:
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        print("local postgres is unreachable.")
        sys.exit(1)
    finally:
        db.close()


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


def _seed_tenant(tag: str, token: str, marker: str) -> tuple[int, str, int, int, list[str]]:
    """Fresh client + two sessions + target lead + similar lead (marker in location)."""
    from models import Client, Lead, Session as SessionModel

    db = SessionLocal()
    try:
        raw_key = f"graph-proof-{tag}-{token}"
        client = Client(
            company_name=f"Graph Isolation Proof {tag} {token}",
            email=f"graph-proof-{tag}-{token}@local.test",
            hashed_password="not-a-login",
            api_key=raw_key,
            is_api_key_hashed=False,
            is_active=True,
        )
        db.add(client)
        db.commit()
        db.refresh(client)
        # Lead.session_id is UNIQUE — the similar lead gets its own session row.
        sids = [
            f"{client.id}_graph-proof-{tag}-{token}",
            f"{client.id}_graph-proof-{tag}-{token}-sim",
        ]
        for sid in sids:
            db.add(SessionModel(id=sid, client_id=client.id))
        target = Lead(
            session_id=sids[0],
            client_id=client.id,
            name=f"Iso Proof {tag} {token}",
            phone=f"+919{tag == 'a' and 51 or 52}{token[:6]}",
            location=marker,
            budget="85L",
            property_type="3BHK",
            intent="buy",
            source="proof",
        )
        db.add(target)
        similar = Lead(
            session_id=sids[1],
            client_id=client.id,
            name=f"Iso Similar {tag} {token}",
            phone=f"+919{tag == 'a' and 61 or 62}{token[:6]}",
            location=marker,
            budget="60L",
            property_type="2BHK",
            intent="buy",
            source="proof",
        )
        db.add(similar)
        db.commit()
        db.refresh(target)
        db.refresh(similar)
        return client.id, raw_key, target.id, similar.id, sids
    finally:
        db.close()


def main() -> None:
    _refuse_nonlocal()
    _pg_up()
    _ensure_client_columns()

    token = uuid.uuid4().hex[:12]
    marker_a = f"graph-proof-A-{token}"
    marker_b = f"graph-proof-B-{token}"

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.events import router as events_router
    from app.knowledge_graph.graph_api import router as graph_router
    from app.knowledge_graph.neo4j_client import neo4j_client
    from app.knowledge_graph.neo4j_kg import knowledge_graph
    from app.clients.graph_client import graph_client

    # Wait for the live graph before any assertion.
    h = neo4j_client.health()
    print(f"neo4j_health={h}")
    if not h.get("available"):
        _fail("postgres is up but Neo4j is not available — start local Neo4j and retry")

    client_a, raw_key_a, target_a, similar_a, sids_a = _seed_tenant("a", token, marker_a)
    client_b, raw_key_b, target_b, similar_b, sids_b = _seed_tenant("b", token, marker_b)
    print(f"seeded A client={client_a} target_lead={target_a} similar={similar_a}")
    print(f"seeded B client={client_b} target_lead={target_b} similar={similar_b}")

    try:
        # Upsert the four Lead nodes into the LIVE graph (private nodes per tenant).
        knowledge_graph.upsert_lead(target_a, client_a, {
            "name": f"Iso Proof a {token}", "location": marker_a,
            "property_type": "3BHK", "lead_temperature": "hot",
        })
        knowledge_graph.upsert_lead(similar_a, client_a, {
            "name": f"Iso Similar a {token}", "location": marker_a,
            "property_type": "2BHK", "lead_temperature": "warm",
        })
        knowledge_graph.upsert_lead(target_b, client_b, {
            "name": f"Iso Proof b {token}", "location": marker_b,
            "property_type": "3BHK", "lead_temperature": "hot",
        })
        knowledge_graph.upsert_lead(similar_b, client_b, {
            "name": f"Iso Similar b {token}", "location": marker_b,
            "property_type": "2BHK", "lead_temperature": "warm",
        })
        print("graph_upserts_done count=4")

        app = FastAPI()
        app.include_router(events_router)
        app.include_router(graph_router)

        with TestClient(app) as tc:
            # Positive control on availability BEFORE isolation assertions.
            h_route = tc.get("/api/v1/graph/health")
            if h_route.status_code != 200:
                _fail(f"/graph/health returned {h_route.status_code}")
            body = h_route.json()
            if not body.get("available"):
                _fail("graph health reports available: false — down-graph 404s are not isolation")
            print(f"health_available true schema_version={body.get('schema_version')}")

            # 1. Tenant B's key on Tenant A's lead → 404, no A marker in body.
            r = tc.get(
                f"/api/v1/graph/leads/{target_a}/context",
                headers={"X-API-Key": raw_key_b},
            )
            if r.status_code != 404:
                _fail(f"B-on-A expected 404, got {r.status_code}: {r.text[:200]}")
            if marker_a in r.text:
                _fail("B-on-A 404 body leaked A's marker")
            print(f"b_on_a_404 status=404 marker_absent=true")

            # 2. Tenant A's key on A's lead → 200 WITH the marker (not an empty graph).
            r = tc.get(
                f"/api/v1/graph/leads/{target_a}/context",
                headers={"X-API-Key": raw_key_a},
            )
            if r.status_code != 200:
                _fail(f"A-on-A expected 200, got {r.status_code}: {r.text[:200]}")
            if marker_a not in r.text:
                _fail(f"A-on-A 200 body missing A's marker: {r.text[:400]}")
            print(f"a_on_a_200 status=200 marker_present=true")

            # 3. Tenant B's key on B's lead → 200 WITH B's marker.
            r = tc.get(
                f"/api/v1/graph/leads/{target_b}/context",
                headers={"X-API-Key": raw_key_b},
            )
            if r.status_code != 200:
                _fail(f"B-on-B expected 200, got {r.status_code}: {r.text[:200]}")
            if marker_b not in r.text:
                _fail(f"B-on-B 200 body missing B's marker: {r.text[:400]}")
            if marker_a in r.text:
                _fail("B-on-B body leaked A's marker")
            print(f"b_on_b_200 status=200 marker_present=true marker_b_absent_a=true")

            # 4. Direct GraphClient read with B's client_id on A's lead id.
            ctx = graph_client.get_lead_context(target_a, client_b)
            ctx_blob = str(ctx)
            if marker_a in ctx_blob:
                _fail(f"get_lead_context(A_lead, B_id) leaked A's marker: {ctx[:200]}")
            print(f"direct_read_b_on_a marker_absent=true ctx_keys={sorted(ctx.keys())}")

            # 5. Direct GraphClient read with A's client_id on A's lead → marker present.
            ctx_a = graph_client.get_lead_context(target_a, client_a)
            if marker_a not in str(ctx_a):
                _fail(f"get_lead_context(A_lead, A_id) missing A's marker")
            print(f"direct_read_a_on_a marker_present=true")

        print("GRAPH_ISOLATION_PASS")
    finally:
        _cleanup(client_a, client_b, token, [sids_a, sids_b])


def _cleanup(client_a: int, client_b: int, token: str, sids: list[list[str]]) -> None:
    from models import Client, EventLog, Lead, Message, Session as SessionModel

    # Neo4j: delete ONLY this run's per-tenant nodes (never ids 1 or 2).
    from app.knowledge_graph.neo4j_client import neo4j_client

    if neo4j_client.available:
        try:
            neo4j_client.run(
                "MATCH (l:Lead) WHERE l.client_id IN [$a, $b] DETACH DELETE l",
                a=client_a,
                b=client_b,
            )
            print("neo4j_cleanup_done")
        except Exception as exc:  # noqa: BLE001
            print(f"neo4j_cleanup_warn: {exc}")

    db = SessionLocal()
    try:
        all_sids = [sid for group in sids for sid in group]
        db.query(Message).filter(Message.session_id.in_(all_sids)).delete(synchronize_session=False)
        db.query(EventLog).filter(EventLog.session_id.in_(all_sids)).delete(synchronize_session=False)
        db.query(Lead).filter(Lead.client_id.in_([client_a, client_b])).delete(synchronize_session=False)
        db.query(SessionModel).filter(SessionModel.id.in_(all_sids)).delete(synchronize_session=False)
        db.query(Client).filter(Client.id.in_([client_a, client_b])).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()
    print("pg_cleanup_done")


if __name__ == "__main__":
    main()
