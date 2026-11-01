"""Isolation proofs for the V2 policy shape.

These tests execute ``app.migration.isolation_drill`` against a throwaway local
PostgreSQL database. They fail rather than skip when Postgres is unavailable, so
a green run is evidence that the policy shape was actually executed.
"""

from __future__ import annotations

import psycopg2
import pytest

from app.migration.isolation_drill import (
    ADMIN_DSN,
    DRILL_DB,
    REQUIRED_LINES,
    run_isolation_drill,
)


@pytest.mark.integration
def test_agency_isolation_drill_passes_and_cleans_up():
    lines = run_isolation_drill()
    blob = "\n".join(lines)

    assert "ISOLATION_DRILL_START" in blob
    assert "database=v2_isolation_drill" in blob
    assert "live_database_used=false" in blob
    assert "render_used=false" in blob
    assert "app_database_touched=false" in blob
    assert "production_claim=false" in blob
    assert "ISOLATION_DRILL_PASS" in blob

    for required in REQUIRED_LINES:
        assert required in blob, required

    conn = psycopg2.connect(ADMIN_DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DRILL_DB,))
            assert cur.fetchone() is None
            cur.execute("SELECT rolname FROM pg_roles WHERE rolname LIKE 'iso_%'")
            assert cur.fetchall() == []
    finally:
        conn.close()
