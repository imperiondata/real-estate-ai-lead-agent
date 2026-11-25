"""Post-cutover rollback proofs.

One in-memory test proves ``switch_reads_to_v1`` is not ``rollback()``. One
Postgres test executes the drill against the throwaway local database. It fails
rather than skips when Postgres is unavailable, so a green run is evidence that
the procedure was actually executed.
"""

from __future__ import annotations

import psycopg2
import pytest

from app.migration import dry_run
from app.migration.dry_run import DryRunStore, apply_dual_write, switch_reads_to_v1
from app.migration.post_cutover_rollback_drill import (
    ADMIN_DSN,
    DRILL_DB,
    REQUIRED_LINES,
    run_post_cutover_rollback_drill,
)


def _aggregate(lead_id: int, name: str) -> dict:
    return {
        "tenant": "1",
        "tables": {
            "v1_leads": {lead_id: {"id": lead_id, "name": name}},
            "v2.leads": {lead_id: {"v1_lead_id": lead_id, "name": name}},
        },
    }


def test_switch_reads_to_v1_keeps_dual_write_and_the_shadow(monkeypatch):
    def _explode(_store):
        raise AssertionError("switch_reads_to_v1 must not call rollback()")

    monkeypatch.setattr(dry_run, "rollback", _explode)

    store = DryRunStore({"leads": []})
    store.dual_write = True
    assert apply_dual_write(store, _aggregate(1, "seed"))["status"] == "complete"
    store.read_source = "v2"
    shadow_before = {table: dict(rows) for table, rows in store.shadow.items()}

    outcome = switch_reads_to_v1(store)

    assert store.read_source == "v1"
    assert store.dual_write is True
    assert store.shadow == shadow_before
    assert outcome == {
        "read_source": "v1",
        "dual_write": True,
        "shadow_tables": len(shadow_before),
    }


@pytest.mark.integration
def test_post_cutover_rollback_drill_passes_and_cleans_up():
    lines = run_post_cutover_rollback_drill()
    blob = "\n".join(lines)

    assert "POST_CUTOVER_ROLLBACK_DRILL_START" in blob
    assert "database=v2_post_cutover_rollback" in blob
    assert "POST_CUTOVER_ROLLBACK_PASS" in blob

    for required in REQUIRED_LINES:
        assert required in blob, required

    assert "SIMULATED_CUT read_source=v2 dual_write=true" in blob
    assert "WRITE_ORDER v1_then_v2" in blob
    assert "new_v1_rows=1 new_shadow_rows=1" in blob
    assert "TABLE_CHECKSUM" in blob
    assert "table_checksum_equal=true" in blob

    conn = psycopg2.connect(ADMIN_DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DRILL_DB,))
            assert cur.fetchone() is None
    finally:
        conn.close()
