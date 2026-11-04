"""Application-process restart proofs for the 4 November package.

The drill terminates the worker PID and reads the committed failure row back
from a second process. Runs against throwaway Postgres on 127.0.0.1. Fails,
rather than skips, if local Postgres is down.
"""

from __future__ import annotations

import psycopg2

from app.migration.process_restart_drill import (
    ADMIN_DSN,
    DRILL_DB,
    REQUIRED_LINES,
    run_process_restart_drill,
)


def test_process_restart_drill_passes_and_cleans_up():
    lines = run_process_restart_drill()
    blob = "\n".join(lines)

    assert "PROCESS_RESTART_DRILL_START" in blob
    assert "database=v2_process_restart" in blob
    assert "live_database_used=false" in blob
    assert "render_used=false" in blob
    assert "app_database_touched=false" in blob
    assert "production_claim=false" in blob
    assert "code_path=app.migration.process_restart_worker" in blob
    assert "not_a_new_connection_in_the_same_process=true" in blob
    assert "live_dual_write_flag=false" in blob
    assert "chat_path_unchanged=true" in blob
    assert "pids_differ=true" in blob
    assert "process_killed=true" in blob
    assert "order=injected production_order=v1_then_v2" in blob
    assert "PROCESS_RESTART_DRILL_PASS" in blob
    for required in REQUIRED_LINES:
        assert required in blob, required

    conn = psycopg2.connect(ADMIN_DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DRILL_DB,))
            assert cur.fetchone() is None
    finally:
        conn.close()
