"""Project Postgres leads into Neo4j (batch backfill).

Use after Neo4j wipe, schema migrate, or bulk seed when bus events did not run.
Postgres remains source of truth; this is a best-effort projection.

  python project_leads_to_neo4j.py
  python project_leads_to_neo4j.py --client-id 1
  python project_leads_to_neo4j.py --source dummy_seed --limit 1000
  python project_leads_to_neo4j.py --dry-run
"""
from __future__ import annotations

import argparse
import sys

from database import SessionLocal
from models import Lead


LEAD_PROP_FIELDS = (
    "name",
    "location",
    "property_type",
    "lead_temperature",
    "conversion_probability",
    "intent",
    "visit_date",
    "funnel_stage",
    "budget",
    "urgency_level",
    "source",
)


def _props(lead: Lead) -> dict:
    out = {}
    for k in LEAD_PROP_FIELDS:
        v = getattr(lead, k, None)
        if v is not None:
            out[k] = v
    return out


def project(
    client_id: int | None = None,
    source: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    batch_size: int = 200,
) -> dict:
    from app.knowledge_graph.neo4j_client import neo4j_client
    from app.knowledge_graph.neo4j_kg import knowledge_graph

    if not dry_run:
        if not neo4j_client.available:
            print("ERROR: Neo4j unavailable (check NEO4J_URI / docker neo4j).", file=sys.stderr)
            return {"ok": False, "projected": 0, "linked": 0}
        neo4j_client.migrate_schema()

    db = SessionLocal()
    try:
        q = db.query(Lead).order_by(Lead.id.asc())
        if client_id is not None:
            q = q.filter(Lead.client_id == client_id)
        if source:
            q = q.filter(Lead.source == source)
        if limit is not None:
            q = q.limit(limit)
        leads = q.all()
    finally:
        db.close()

    projected = 0
    linked = 0
    for i, lead in enumerate(leads, 1):
        props = _props(lead)
        if dry_run:
            projected += 1
            if lead.assigned_agent:
                linked += 1
        else:
            knowledge_graph.upsert_lead(lead.id, lead.client_id, props)
            projected += 1
            if lead.assigned_agent:
                knowledge_graph.link_lead_agent(
                    lead.id, str(lead.assigned_agent), lead.client_id
                )
                linked += 1
        if i % batch_size == 0:
            print(f"  … {i}/{len(leads)}")

    return {
        "ok": True,
        "total": len(leads),
        "projected": projected,
        "linked": linked,
        "dry_run": dry_run,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Project Postgres leads → Neo4j")
    p.add_argument("--client-id", type=int, default=None)
    p.add_argument("--source", type=str, default=None, help="Filter Lead.source")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--batch-size", type=int, default=200)
    args = p.parse_args()

    result = project(
        client_id=args.client_id,
        source=args.source,
        limit=args.limit,
        dry_run=args.dry_run,
        batch_size=args.batch_size,
    )
    print(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
