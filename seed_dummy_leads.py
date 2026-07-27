"""Seed N fully-populated dummy leads into Postgres and project to Neo4j.

Safe for local/dev only. Tags source=`dummy_seed` for easy cleanup.

  python seed_dummy_leads.py                  # 1000 leads, client 1
  python seed_dummy_leads.py --count 100
  python seed_dummy_leads.py --client-id 1 --purge-only
  python seed_dummy_leads.py --no-neo4j       # Postgres only
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone

from database import SessionLocal, engine
from models import Base, Client, Lead, Session

SOURCE = "dummy_seed"

LOCATIONS = [
    "Baner",
    "Wakad",
    "Hinjewadi",
    "Balewadi",
    "Kharadi",
    "Viman Nagar",
    "Hadapsar",
    "Kothrud",
    "Aundh",
    "Pimple Saudagar",
]
PROPERTY_TYPES = ["1BHK", "2BHK", "3BHK", "4BHK", "Villa", "Plot", "Office"]
INTENTS = ["buy", "rent", "invest"]
TEMPS = ["hot", "warm", "cold"]
URGENCY = ["high", "medium", "low"]
FUNNELS = ["New", "Contacted", "Appointment Scheduled", "Closed Won", "Lost"]
BUDGETS = [
    "40 lakhs",
    "55 lakhs",
    "75 lakhs",
    "90 lakhs",
    "1.2 cr",
    "1.5 cr",
    "2 cr",
    "25000 PERMONTH",
    "45000 PERMONTH",
]
AGENTS = ["Sneha Patil", "System Admin", "Rahul Deshmukh", "Priya Kulkarni", None]
FIRST = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Ayaan",
    "Krishna", "Ishaan", "Ananya", "Aadhya", "Diya", "Myra", "Sara", "Anika",
    "Pari", "Navya", "Kiara", "Ira", "Rohan", "Karan", "Neha", "Pooja", "Amit",
]
LAST = [
    "Sharma", "Patil", "Kulkarni", "Deshmukh", "Joshi", "Mehta", "Shah",
    "Reddy", "Nair", "Iyer", "Gupta", "Singh", "Khan", "Das", "Banerjee",
]


def _purge(db, client_id: int) -> int:
    leads = (
        db.query(Lead)
        .filter(Lead.client_id == client_id, Lead.source == SOURCE)
        .all()
    )
    session_ids = [l.session_id for l in leads]
    n = len(leads)
    for lead in leads:
        db.delete(lead)
    db.flush()
    if session_ids:
        db.query(Session).filter(
            Session.client_id == client_id,
            Session.id.in_(session_ids),
        ).delete(synchronize_session=False)
    db.commit()
    return n


def _make_lead(db, client_id: int, i: int, rng: random.Random) -> Lead:
    loc = LOCATIONS[i % len(LOCATIONS)]
    ptype = PROPERTY_TYPES[i % len(PROPERTY_TYPES)]
    temp = TEMPS[i % len(TEMPS)]
    eng = {"hot": 85, "warm": 55, "cold": 25}[temp]
    conv = min(95, eng + rng.randint(-10, 15))
    name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
    phone = f"+9198{rng.randint(10000000, 99999999)}"
    sid = f"{client_id}_dummy_{i:04d}"
    visit = None
    if temp == "hot" or i % 4 == 0:
        day = datetime.now(timezone.utc) + timedelta(days=rng.randint(1, 14))
        visit = day.strftime("%Y-%m-%d 11:00")

    sess = Session(
        id=sid,
        client_id=client_id,
        status="active",
        follow_up_count=rng.randint(0, 3),
    )
    db.add(sess)
    db.flush()

    agent = AGENTS[i % len(AGENTS)]
    lead = Lead(
        session_id=sid,
        client_id=client_id,
        name=name,
        phone=phone,
        budget=rng.choice(BUDGETS),
        location=loc,
        property_type=ptype,
        intent=rng.choice(INTENTS),
        score="High" if temp == "hot" else ("Medium" if temp == "warm" else "Low"),
        visit_date=visit,
        source=SOURCE,
        whatsapp_opt_in=True,
        conversion_probability=conv,
        expected_closure_days=rng.randint(7, 90),
        lead_temperature=temp,
        engagement_score=eng,
        budget_alignment_status=rng.choice(["aligned", "stretch", "unknown"]),
        inactivity_penalty=rng.randint(0, 20),
        response_speed_score=rng.randint(40, 100),
        urgency_level=URGENCY[i % len(URGENCY)],
        assigned_agent=agent,
        conversion_status="open" if FUNNELS[i % len(FUNNELS)] not in ("Closed Won", "Lost") else "closed",
        followup_stage=rng.choice(["new", "Day 0", "Day 1", "Day 3"]),
        best_performing_script="dummy seed script",
        funnel_stage=FUNNELS[i % len(FUNNELS)],
        external_crm_id=f"dummy-crm-{client_id}-{i:04d}",
        crm_sync_status=rng.choice(["pending", "success", "pending"]),
        crm_resync_pending=False,
        confidence_score=rng.randint(70, 100),
        requires_manual_review=conv < 50,
    )
    db.add(lead)
    return lead


def seed(
    count: int = 1000,
    client_id: int = 1,
    purge_first: bool = True,
    project_neo4j: bool = True,
    seed_value: int = 42,
) -> dict:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    rng = random.Random(seed_value)
    purged = 0
    try:
        client = db.query(Client).filter(Client.id == client_id).first()
        if not client:
            print(
                f"ERROR: client_id={client_id} not found. Run python seed.py first.",
                file=sys.stderr,
            )
            return {"ok": False, "created": 0}

        if purge_first:
            purged = _purge(db, client_id)
            print(f"Purged {purged} existing {SOURCE} leads (+ sessions)")

        created = 0
        batch = 100
        for i in range(count):
            _make_lead(db, client_id, i, rng)
            created += 1
            if created % batch == 0:
                db.commit()
                print(f"  Postgres … {created}/{count}")
        db.commit()
        print(f"Created {created} leads in Postgres (client_id={client_id}, source={SOURCE})")
    finally:
        db.close()

    neo = {"skipped": True}
    if project_neo4j:
        from project_leads_to_neo4j import project

        neo = project(client_id=client_id, source=SOURCE, limit=count)
        print(f"Neo4j projection: {neo}")

    return {
        "ok": True,
        "purged": purged,
        "created": created,
        "client_id": client_id,
        "source": SOURCE,
        "neo4j": neo,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Seed dummy leads + optional Neo4j project")
    p.add_argument("--count", type=int, default=1000)
    p.add_argument("--client-id", type=int, default=1)
    p.add_argument("--no-purge", action="store_true", help="Do not delete prior dummy_seed rows")
    p.add_argument("--purge-only", action="store_true", help="Only delete dummy_seed rows")
    p.add_argument("--no-neo4j", action="store_true")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    if args.purge_only:
        db = SessionLocal()
        try:
            n = _purge(db, args.client_id)
            print(f"Purged {n} dummy leads for client_id={args.client_id}")
        finally:
            db.close()
        return 0

    result = seed(
        count=args.count,
        client_id=args.client_id,
        purge_first=not args.no_purge,
        project_neo4j=not args.no_neo4j,
        seed_value=args.seed,
    )
    print(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
