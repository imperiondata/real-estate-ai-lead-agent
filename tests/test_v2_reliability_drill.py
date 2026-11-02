"""Reliability proofs for the 2 November package.

Update, delete, concurrent writes, new-connection read-back, retry
idempotency, and a SQL rollback. Runs against throwaway Postgres on
127.0.0.1. Fails, rather than skips, if local Postgres is down.
"""

from __future__ import annotations

import psycopg2

from app.migration.reliability_drill import (
    ADMIN_DSN,
    DRILL_DB,
    REQUIRED_LINES,
    run_reliability_drill,
)


def test_reliability_drill_passes_and_cleans_up():
    lines = run_reliability_drill()
    blob = "\n".join(lines)

    assert "RELIABILITY_DRILL_START" in blob
    assert "database=v2_nov2_reliability" in blob
    assert "live_database_used=false" in blob
    assert "render_used=false" in blob
    assert "app_database_touched=false" in blob
    assert "production_claim=false" in blob
    assert "process_restart=new_connection_after_commit" in blob
    assert "RELIABILITY_DRILL_PASS" in blob
    for required in REQUIRED_LINES:
        assert required in blob, required

    conn = psycopg2.connect(ADMIN_DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DRILL_DB,))
            assert cur.fetchone() is None
    finally:
        conn.close()
