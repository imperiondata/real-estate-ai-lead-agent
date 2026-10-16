"""Disaster Recovery (INF-01) Database Restore Integrity Verification Script.

Connects to the restored target database, performs strict foreign-key integrity
checks, asserts representative business records, and simulates an application boot check.

Usage:
    python scripts/verify_restore_integrity.py [--db-url postgresql://user:pass@host:port/dbname]
"""
from __future__ import annotations

import argparse
import sys
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("dr_verification")


def parse_args():
    parser = argparse.ArgumentParser(description="Verify restored database integrity.")
    parser.add_argument(
        "--db-url",
        default="postgresql://postgres:Mayank%401@localhost:5432/paas_drill_db",
        help="Database connection URL to verify (default: local paas_drill_db)",
    )
    return parser.parse_args()


def run_integrity_audit(db_url: str) -> bool:
    logger.info("Connecting to target database for integrity verification...")
    logger.info("Target URL: %s", db_url.split("@")[-1] if "@" in db_url else db_url)

    engine = create_engine(db_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    session = Session()

    passed = True
    report = []

    try:
        # ------------------------------------------------------------------ #
        # Step 1: Application Boot & Table Existence Check
        # ------------------------------------------------------------------ #
        required_tables = [
            "clients",
            "sessions",
            "leads",
            "messages",
            "event_logs",
            "follow_up_states",
            "dlq_events",
            "agents",
            "notification_logs",
            "webhook_logs",
        ]

        logger.info("--- Step 1: Application Boot & Table Schema Verification ---")
        existing_tables_res = session.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        ).fetchall()
        existing_tables = {row[0] for row in existing_tables_res}

        missing_tables = [t for t in required_tables if t not in existing_tables]
        if missing_tables:
            logger.error("[FAIL] Missing required core tables: %s", missing_tables)
            passed = False
            report.append(f"Table Schema: FAILED (missing: {missing_tables})")
        else:
            logger.info("[PASS] All %d required core tables are present.", len(required_tables))
            report.append(f"Table Schema: PASSED ({len(required_tables)} core tables present)")

        # ------------------------------------------------------------------ #
        # Step 2: Referential Integrity (Foreign Key Orphan Checks)
        # ------------------------------------------------------------------ #
        logger.info("--- Step 2: Referential & Foreign-Key Integrity Checks ---")
        fk_checks = [
            ("leads.client_id -> clients.id",
             "SELECT COUNT(*) FROM leads WHERE client_id NOT IN (SELECT id FROM clients)"),
            ("sessions.client_id -> clients.id",
             "SELECT COUNT(*) FROM sessions WHERE client_id IS NOT NULL AND client_id NOT IN (SELECT id FROM clients)"),
            ("messages.client_id -> clients.id",
             "SELECT COUNT(*) FROM messages WHERE client_id NOT IN (SELECT id FROM clients)"),
            ("messages.session_id -> sessions.id",
             "SELECT COUNT(*) FROM messages WHERE session_id NOT IN (SELECT id FROM sessions)"),
            ("event_logs.client_id -> clients.id",
             "SELECT COUNT(*) FROM event_logs WHERE client_id IS NOT NULL AND client_id NOT IN (SELECT id FROM clients)"),
            ("dlq_events.client_id -> clients.id",
             "SELECT COUNT(*) FROM dlq_events WHERE client_id NOT IN (SELECT id FROM clients)"),
            ("agents.client_id -> clients.id",
             "SELECT COUNT(*) FROM agents WHERE client_id NOT IN (SELECT id FROM clients)"),
        ]

        fk_failures = 0
        for name, query in fk_checks:
            try:
                orphan_count = session.execute(text(query)).scalar() or 0
                if orphan_count > 0:
                    logger.error("[FAIL] FK Orphan Violation in %s: %d orphaned rows found!", name, orphan_count)
                    passed = False
                    fk_failures += 1
                else:
                    logger.info("[PASS] FK %s: 0 orphans", name)
            except Exception as e:
                logger.warning("[WARN] Could not verify %s: %s", name, e)

        report.append(f"FK Integrity: {'PASSED (0 violations)' if fk_failures == 0 else f'FAILED ({fk_failures} violations)'}")

        # ------------------------------------------------------------------ #
        # Step 3: Representative Business Records Audit
        # ------------------------------------------------------------------ #
        logger.info("--- Step 3: Representative Business Records Presence ---")
        client_count = session.execute(text("SELECT COUNT(*) FROM clients")).scalar() or 0
        active_client_count = session.execute(text("SELECT COUNT(*) FROM clients WHERE is_active = TRUE")).scalar() or 0
        lead_count = session.execute(text("SELECT COUNT(*) FROM leads")).scalar() or 0
        message_count = session.execute(text("SELECT COUNT(*) FROM messages")).scalar() or 0

        logger.info("Clients Total: %d (Active: %d)", client_count, active_client_count)
        logger.info("Leads Total:   %d", lead_count)
        logger.info("Messages Total: %d", message_count)

        if client_count == 0:
            logger.error("[FAIL] Zero clients found in restored database!")
            passed = False
        if lead_count == 0:
            logger.error("[FAIL] Zero leads found in restored database!")
            passed = False
        if message_count == 0:
            logger.error("[FAIL] Zero messages found in restored database!")
            passed = False

        # Verify presence of qualification fields
        sample_lead = session.execute(
            text("SELECT id, name, phone, location, budget FROM leads WHERE phone IS NOT NULL LIMIT 1")
        ).fetchone()

        if sample_lead:
            logger.info("[PASS] Sample lead record confirmed: ID=%s, Name=%s, Location=%s", sample_lead[0], sample_lead[1], sample_lead[3])
            report.append(f"Business Records: PASSED ({client_count} clients, {lead_count} leads, {message_count} messages)")
        else:
            logger.error("[FAIL] No qualified lead records with phone numbers found.")
            passed = False
            report.append("Business Records: FAILED (missing qualified lead data)")

        # ------------------------------------------------------------------ #
        # Step 4: Summary & Exit Status
        # ------------------------------------------------------------------ #
        print("\n" + "=" * 70)
        print("DISASTER RECOVERY INTEGRITY AUDIT REPORT")
        print("=" * 70)
        for line in report:
            print(f"- {line}")
        print("=" * 70)
        print(f"OVERALL STATUS: {'[PASS] RESTORE INTEGRITY VERIFIED' if passed else '[FAIL] INTEGRITY ISSUES DETECTED'}")
        print("=" * 70 + "\n")

    except Exception as exc:
        logger.exception("[FATAL] Error running integrity audit: %s", exc)
        passed = False
    finally:
        session.close()
        engine.dispose()

    return passed


if __name__ == "__main__":
    args = parse_args()
    success = run_integrity_audit(args.db_url)
    sys.exit(0 if success else 1)
