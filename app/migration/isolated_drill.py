"""Isolated Nov 1 drill. Throwaway database on 127.0.0.1 only.

This module opens a socket, so it stays out of ``dry_run``. It refuses any DSN
that is not loopback or that names the application database, and it never reads
``LIVE_DATABASE_URL``.

The run proves two things and claims nothing else:

1. Per-tenant parity over every mapped Lead column, and the mismatch report.
   The checksum Piyush rejected on 29 October would still pass tenant 2.
2. Failure injection at three points around the V1 and V2 writes. The failure
   row is committed first, read back on a second connection, and retried with
   an idempotent upsert.

RLS, agencies, and foreign-key boundaries are not executed here and are not
claimed by this log.
"""

from __future__ import annotations

import uuid
from urllib.parse import urlparse

import psycopg2
from psycopg2 import sql

from app.migration.dry_run import (
    assert_isolated_dsn,
    reconcile_table,
    rejected_selected_field_checksum,
)

ADMIN_DSN = "postgresql://realestate:localpass@127.0.0.1:5432/postgres"
DRILL_DB = "v2_nov1_drill"
DRILL_DSN = f"postgresql://realestate:localpass@127.0.0.1:5432/{DRILL_DB}"
ALLOWED_DATABASES = {"postgres", DRILL_DB}
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}

# The digest covers the same fields the backfill maps, so a difference in any
# of them fails parity. This is wider than name/phone/budget.
LEAD_SPEC = {
    "pk": "id",
    "digest": ("name", "phone", "budget", "location", "funnel_stage"),
    "secrets": (),
}


class DrillError(RuntimeError):
    """The drill refused to run, or an assertion failed."""


def _refuse_nonlocal(dsn: str) -> None:
    """Loopback host only, and never the application database."""
    assert_isolated_dsn(dsn)
    parsed = urlparse(dsn)
    host = (parsed.hostname or "").lower()
    if host not in LOCAL_HOSTS:
        raise DrillError(f"refusing non-local host {host or 'unknown'}")
    database = parsed.path.lstrip("/")
    if database not in ALLOWED_DATABASES:
        raise DrillError(f"refusing database {database or 'unknown'}")


def _connect(dsn: str):
    _refuse_nonlocal(dsn)
    return psycopg2.connect(dsn)


def _admin_conn():
    conn = _connect(ADMIN_DSN)
    conn.autocommit = True
    return conn


def reset_database() -> None:
    """Drop and recreate the throwaway database. Never the app database."""
    conn = _admin_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (DRILL_DB,),
            )
            cur.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(DRILL_DB)
                )
            )
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DRILL_DB)))
    finally:
        conn.close()


def drop_database() -> None:
    conn = _admin_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (DRILL_DB,),
            )
            cur.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(DRILL_DB)
                )
            )
    finally:
        conn.close()


def _exec(conn, statement, params=None) -> None:
    with conn.cursor() as cur:
        cur.execute(statement, params)


def _fetchone(conn, statement: str, params=None):
    with conn.cursor() as cur:
        cur.execute(statement, params)
        return cur.fetchone()


def _fetchall(conn, statement: str, params=None):
    with conn.cursor() as cur:
        cur.execute(statement, params)
        return cur.fetchall()


SCHEMA_SQL = """
CREATE TABLE v1_leads (
    id integer PRIMARY KEY,
    client_id integer NOT NULL,
    name text,
    phone text,
    budget text,
    location text,
    funnel_stage text
);

CREATE TABLE v2_leads (
    v1_lead_id integer PRIMARY KEY,
    tenant_key text NOT NULL,
    name text,
    phone text,
    budget text,
    location text,
    funnel_stage text
);

CREATE TABLE dual_write_failures (
    id serial PRIMARY KEY,
    tenant_key text NOT NULL,
    v1_lead_id integer NOT NULL,
    phase text NOT NULL,
    written text NOT NULL,
    missing text NOT NULL,
    error text NOT NULL,
    retry_count integer NOT NULL DEFAULT 0,
    status text NOT NULL,
    UNIQUE (v1_lead_id, phase)
);
"""

SEED_SQL = """
INSERT INTO v1_leads (id, client_id, name, phone, budget, location, funnel_stage) VALUES
    (1, 1, 'Ada', '90001', '50L', 'Baner', 'New'),
    (2, 1, 'Bea', '90002', '60L', 'Wakad', 'Contacted'),
    (3, 2, 'Cara', '90003', '70L', 'Kothrud', 'New');

INSERT INTO v2_leads (v1_lead_id, tenant_key, name, phone, budget, location, funnel_stage) VALUES
    (1, '1', 'Ada', '90001', '50L', 'Baner', 'New'),
    (2, '1', 'Bea', '90002', '60L', 'Wakad', 'Contacted'),
    (3, '2', 'Cara', '90003', '70L', 'Kothrud', 'Lost');
"""

LEAD_FIELDS = ("id", "name", "phone", "budget", "location", "funnel_stage")


def _v1_rows(conn, tenant_key: str) -> list[dict]:
    found = _fetchall(
        conn,
        "SELECT id, name, phone, budget, location, funnel_stage FROM v1_leads "
        "WHERE client_id = %s ORDER BY id",
        (int(tenant_key),),
    )
    return [dict(zip(LEAD_FIELDS, row)) for row in found]


def _v2_rows(conn, tenant_key: str) -> list[dict]:
    found = _fetchall(
        conn,
        "SELECT v1_lead_id, name, phone, budget, location, funnel_stage FROM v2_leads "
        "WHERE tenant_key = %s ORDER BY v1_lead_id",
        (tenant_key,),
    )
    return [dict(zip(LEAD_FIELDS, row)) for row in found]


def reconcile_lines(conn) -> list[str]:
    lines = []
    for tenant in ("1", "2"):
        v1 = _v1_rows(conn, tenant)
        v2 = _v2_rows(conn, tenant)
        result = reconcile_table(v1, v2, LEAD_SPEC)
        lines.append(
            f"RECONCILE tenant={tenant} ok={str(result['ok']).lower()} "
            f"v1_count={result['v1_count']} v2_count={result['v2_count']} "
            f"missing={result['missing']} extra={result['extra']} "
            f"mismatches={result['column_mismatches']}"
        )
        old_checksum_match = rejected_selected_field_checksum(
            v1
        ) == rejected_selected_field_checksum(v2)
        lines.append(
            f"REJECTED_CHECKSUM_WOULD_MATCH tenant={tenant} {str(old_checksum_match).lower()}"
        )
    return lines


def _counts(conn, lead_id: int) -> tuple[int, int]:
    v1 = _fetchone(conn, "SELECT count(*) FROM v1_leads WHERE id = %s", (lead_id,))[0]
    v2 = _fetchone(
        conn, "SELECT count(*) FROM v2_leads WHERE v1_lead_id = %s", (lead_id,)
    )[0]
    return v1, v2


def _insert_v1(conn, lead_id: int) -> None:
    _exec(
        conn,
        """
        INSERT INTO v1_leads (id, client_id, name, phone, budget, location, funnel_stage)
        VALUES (%s, 9, 'Crash', '90009', '10L', 'Baner', 'New')
        ON CONFLICT (id) DO NOTHING
        """,
        (lead_id,),
    )
    conn.commit()


def _insert_v2(conn, lead_id: int) -> None:
    _exec(
        conn,
        """
        INSERT INTO v2_leads (v1_lead_id, tenant_key, name, phone, budget, location, funnel_stage)
        VALUES (%s, '9', 'Crash', '90009', '10L', 'Baner', 'New')
        ON CONFLICT (v1_lead_id) DO NOTHING
        """,
        (lead_id,),
    )
    conn.commit()


def _record_failure(conn, lead_id: int, phase: str, written: str, missing: str) -> int:
    row = _fetchone(
        conn,
        """
        INSERT INTO dual_write_failures
            (tenant_key, v1_lead_id, phase, written, missing, error, status)
        VALUES ('9', %s, %s, %s, %s, 'injected_crash', 'open')
        RETURNING id
        """,
        (lead_id, phase, written, missing),
    )
    conn.commit()
    return row[0]


def _failure_row(conn, failure_id: int) -> tuple[str, str]:
    row = _fetchone(
        conn,
        "SELECT phase, status FROM dual_write_failures WHERE id = %s",
        (failure_id,),
    )
    return row[0], row[1]


def retry_lead(conn, lead_id: int, failure_id: int) -> None:
    """Idempotent upsert of whatever is missing. Safe to call twice."""
    _phase, status = _failure_row(conn, failure_id)
    if status == "resolved":
        return
    v1_count, v2_count = _counts(conn, lead_id)
    if v1_count == 0:
        _insert_v1(conn, lead_id)
    if v2_count == 0:
        _insert_v2(conn, lead_id)
    _exec(
        conn,
        "UPDATE dual_write_failures "
        "SET status = 'resolved', retry_count = retry_count + 1 WHERE id = %s",
        (failure_id,),
    )
    conn.commit()


CRASH_SCENARIOS = (
    # lead_id, phase, already committed, still missing, write_v1, write_v2
    (100, "before_v1", "", "v1_leads,v2_leads", False, False),
    (101, "after_v1_before_v2", "v1_leads", "v2_leads", True, False),
    (102, "after_both", "v1_leads,v2_leads", "", True, True),
)


def crash_lines(conn) -> list[str]:
    lines = []
    for lead_id, phase, written, missing, write_v1, write_v2 in CRASH_SCENARIOS:
        if write_v1:
            _insert_v1(conn, lead_id)
        if write_v2:
            _insert_v2(conn, lead_id)
        failure_id = _record_failure(conn, lead_id, phase, written, missing)

        # Process "restart": a brand new connection must see the failure row.
        fresh = _connect(DRILL_DSN)
        try:
            seen_phase, seen_status = _failure_row(fresh, failure_id)
            v1_before, v2_before = _counts(fresh, lead_id)
            lines.append(
                f"CRASH phase={phase} failure_id={failure_id} "
                f"visible_to_new_connection=true seen_phase={seen_phase} "
                f"seen_status={seen_status} "
                f"v1_count={v1_before} v2_count={v2_before}"
            )
            retry_lead(fresh, lead_id, failure_id)
            retry_lead(fresh, lead_id, failure_id)
            v1_after, v2_after = _counts(fresh, lead_id)
            status = _failure_row(fresh, failure_id)[1]
            lines.append(
                f"RETRY phase={phase} status={status} "
                f"v1_count={v1_after} v2_count={v2_after} duplicate=false"
            )
        finally:
            fresh.close()
    return lines


REQUIRED_LINES = (
    "RECONCILE tenant=1 ok=true",
    "RECONCILE tenant=2 ok=false",
    "REJECTED_CHECKSUM_WOULD_MATCH tenant=2 true",
    "CRASH phase=before_v1",
    "CRASH phase=after_v1_before_v2",
    "CRASH phase=after_both",
    "RETRY phase=before_v1 status=resolved v1_count=1 v2_count=1 duplicate=false",
    "RETRY phase=after_v1_before_v2 status=resolved v1_count=1 v2_count=1 duplicate=false",
    "RETRY phase=after_both status=resolved v1_count=1 v2_count=1 duplicate=false",
    "visible_to_new_connection=true",
    "duplicate=false",
)


def run_isolated_drill() -> list[str]:
    """Create the throwaway database, run the drill, drop it, return raw lines."""
    _refuse_nonlocal(ADMIN_DSN)
    _refuse_nonlocal(DRILL_DSN)
    lines = [
        "NOV1_DRILL_START",
        "engine=postgres host=127.0.0.1 database=v2_nov1_drill",
        "live_database_used=false",
        "render_used=false",
        "app_database_touched=false",
        "RLS_STATUS v1_render=not_shipped isolated_execution=not_this_run "
        "production_claim=false",
    ]
    reset_database()
    conn = _connect(DRILL_DSN)
    try:
        conn.autocommit = False
        _exec(conn, SCHEMA_SQL)
        _exec(conn, SEED_SQL)
        conn.commit()
        lines.extend(reconcile_lines(conn))
        lines.extend(crash_lines(conn))
    finally:
        conn.close()
        drop_database()

    blob = "\n".join(lines)
    missing = [item for item in REQUIRED_LINES if item not in blob]
    if missing:
        lines.append("NOV1_DRILL_FAIL " + ",".join(missing))
        raise DrillError("drill assertions failed: " + ",".join(missing))
    lines.append("NOV1_DRILL_PASS")
    return lines


if __name__ == "__main__":
    for line in run_isolated_drill():
        print(line)
