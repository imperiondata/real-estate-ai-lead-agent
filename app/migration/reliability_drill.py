"""Isolated 2 November reliability drill. Throwaway database on 127.0.0.1 only.

Proves update, delete, concurrent writes, a new-connection read-back, retry
idempotency, and a SQL rollback that drops schema ``v2`` without rewriting V1.

Does not read ``LIVE_DATABASE_URL``. Does not open ``realestate_db``. Does not
connect to Render. Does not restart the local Postgres process, because that
process also serves the application database. A new connection after commit is
the process-restart proof.
"""

from __future__ import annotations

import hashlib
import os
import threading
from urllib.parse import urlparse

import psycopg2
from psycopg2 import sql

from app.migration.dry_run import assert_isolated_dsn, reconcile_table

ADMIN_DSN = "postgresql://realestate:localpass@127.0.0.1:5432/postgres"
DRILL_DB = "v2_nov2_reliability"
DRILL_DSN = f"postgresql://realestate:localpass@127.0.0.1:5432/{DRILL_DB}"
ALLOWED_DATABASES = {"postgres", DRILL_DB}
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}

LEAD_SPEC = {
    "pk": "id",
    "digest": ("name", "phone", "budget", "location", "funnel_stage"),
    "secrets": (),
}

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

CREATE SCHEMA v2;
CREATE TABLE v2.leads (
    v1_lead_id integer PRIMARY KEY,
    tenant_key text NOT NULL,
    name text,
    phone text,
    budget text,
    location text,
    funnel_stage text
);
"""


class DrillError(RuntimeError):
    """The drill refused to run, or an assertion failed."""


def _refuse_nonlocal(dsn: str) -> None:
    assert_isolated_dsn(dsn, live_database_url=os.getenv("LIVE_DATABASE_URL"))
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


def _exec(conn, statement, params=None) -> None:
    with conn.cursor() as cur:
        cur.execute(statement, params)


def _fetchone(conn, statement, params=None):
    with conn.cursor() as cur:
        cur.execute(statement, params)
        return cur.fetchone()


def _fetchall(conn, statement, params=None):
    with conn.cursor() as cur:
        cur.execute(statement, params)
        return cur.fetchall()


def _reset_database() -> None:
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


def _drop_database() -> None:
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


def _insert_pair(conn, lead_id: int, stage: str = "New") -> None:
    _exec(
        conn,
        """
        INSERT INTO v1_leads (id, client_id, name, phone, budget, location, funnel_stage)
        VALUES (%s, 1, 'Ada', '90001', '50L', 'Baner', %s)
        ON CONFLICT (id) DO NOTHING
        """,
        (lead_id, stage),
    )
    _exec(
        conn,
        """
        INSERT INTO v2.leads (v1_lead_id, tenant_key, name, phone, budget, location, funnel_stage)
        VALUES (%s, '1', 'Ada', '90001', '50L', 'Baner', %s)
        ON CONFLICT (v1_lead_id) DO NOTHING
        """,
        (lead_id, stage),
    )
    conn.commit()


def _rows(conn, table: str) -> list[dict]:
    if table == "v1_leads":
        found = _fetchall(
            conn,
            "SELECT id, name, phone, budget, location, funnel_stage "
            "FROM v1_leads ORDER BY id",
        )
    else:
        found = _fetchall(
            conn,
            "SELECT v1_lead_id, name, phone, budget, location, funnel_stage "
            "FROM v2.leads ORDER BY v1_lead_id",
        )
    columns = ("id", "name", "phone", "budget", "location", "funnel_stage")
    return [dict(zip(columns, row)) for row in found]


def _reconcile(conn) -> dict:
    return reconcile_table(_rows(conn, "v1_leads"), _rows(conn, "v2.leads"), LEAD_SPEC)


def _count(conn, lead_id: int) -> tuple[int, int]:
    v1 = _fetchone(conn, "SELECT count(*) FROM v1_leads WHERE id = %s", (lead_id,))[0]
    v2 = _fetchone(
        conn, "SELECT count(*) FROM v2.leads WHERE v1_lead_id = %s", (lead_id,)
    )[0]
    return v1, v2


def _v1_checksum(conn) -> str:
    found = _fetchall(
        conn,
        "SELECT id, name, phone, budget, location, funnel_stage "
        "FROM v1_leads ORDER BY id",
    )
    payload = "\n".join("|".join("" if cell is None else str(cell) for cell in row) for row in found)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _schema_exists(conn) -> bool:
    row = _fetchone(
        conn,
        "SELECT 1 FROM information_schema.schemata WHERE schema_name = 'v2'",
    )
    return row is not None


def _update_lines(conn) -> list[str]:
    _insert_pair(conn, 1, "New")
    _exec(
        conn,
        "UPDATE v1_leads SET funnel_stage = 'Contacted' WHERE id = 1",
    )
    _exec(
        conn,
        "UPDATE v2.leads SET funnel_stage = 'Contacted' WHERE v1_lead_id = 1",
    )
    conn.commit()
    both = _reconcile(conn)
    lines = [f"UPDATE_BOTH ok={str(both['ok']).lower()}"]

    _exec(
        conn,
        "UPDATE v2.leads SET funnel_stage = 'Lost' WHERE v1_lead_id = 1",
    )
    conn.commit()
    only_v2 = _reconcile(conn)
    columns = sorted({item["column"] for item in only_v2["column_mismatches"]})
    column = columns[0] if columns else "none"
    lines.append(f"UPDATE_V2_ONLY ok={str(only_v2['ok']).lower()} column={column}")
    return lines


def _delete_lines(conn) -> list[str]:
    _insert_pair(conn, 10, "New")
    _exec(conn, "DELETE FROM v1_leads WHERE id = 10")
    _exec(conn, "DELETE FROM v2.leads WHERE v1_lead_id = 10")
    conn.commit()
    v1_count, v2_count = _count(conn, 10)
    lines = [f"DELETE_BOTH v1_count={v1_count} v2_count={v2_count}"]

    _insert_pair(conn, 4, "New")
    _exec(conn, "DELETE FROM v2.leads WHERE v1_lead_id = 4")
    conn.commit()
    missing = _reconcile(conn)["missing"]
    lines.append(f"DELETE_V2_ONLY missing={missing}")
    return lines


def _insert_from_new_connection(lead_id: int, barrier: threading.Barrier) -> None:
    barrier.wait(timeout=10)
    conn = _connect(DRILL_DSN)
    try:
        _insert_pair(conn, lead_id, "New")
    finally:
        conn.close()


def _concurrent_lines() -> list[str]:
    distinct = threading.Barrier(2)
    threads = [
        threading.Thread(target=_insert_from_new_connection, args=(20, distinct)),
        threading.Thread(target=_insert_from_new_connection, args=(21, distinct)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    if any(thread.is_alive() for thread in threads):
        raise DrillError("concurrent distinct inserts did not finish")

    same = threading.Barrier(2)
    same_threads = [
        threading.Thread(target=_insert_from_new_connection, args=(30, same)),
        threading.Thread(target=_insert_from_new_connection, args=(30, same)),
    ]
    for thread in same_threads:
        thread.start()
    for thread in same_threads:
        thread.join(timeout=20)
    if any(thread.is_alive() for thread in same_threads):
        raise DrillError("concurrent same-id inserts did not finish")

    conn = _connect(DRILL_DSN)
    try:
        distinct_rows = _fetchone(
            conn, "SELECT count(*) FROM v1_leads WHERE id IN (20, 21)"
        )[0]
        same_rows = _fetchone(conn, "SELECT count(*) FROM v1_leads WHERE id = 30")[0]
    finally:
        conn.close()
    return [
        f"CONCURRENT_DISTINCT ids=2 rows={distinct_rows}",
        f"CONCURRENT_SAME_ID rows={same_rows}",
    ]


def _restart_lines() -> list[str]:
    writer = _connect(DRILL_DSN)
    try:
        _insert_pair(writer, 40, "New")
        _exec(writer, "UPDATE v1_leads SET funnel_stage = 'Contacted' WHERE id = 40")
        _exec(
            writer,
            "UPDATE v2.leads SET funnel_stage = 'Contacted' WHERE v1_lead_id = 40",
        )
        writer.commit()
    finally:
        writer.close()

    reader = _connect(DRILL_DSN)
    try:
        stage = _fetchone(
            reader, "SELECT funnel_stage FROM v1_leads WHERE id = 40"
        )[0]
        update_visible = stage == "Contacted"
    finally:
        reader.close()

    deleter = _connect(DRILL_DSN)
    try:
        _exec(deleter, "DELETE FROM v2.leads WHERE v1_lead_id = 40")
        _exec(deleter, "DELETE FROM v1_leads WHERE id = 40")
        deleter.commit()
    finally:
        deleter.close()

    after = _connect(DRILL_DSN)
    try:
        delete_visible = _count(after, 40) == (0, 0)
    finally:
        after.close()
    return [
        "RESTART update_visible_to_new_connection="
        f"{str(update_visible).lower()} "
        f"delete_visible_to_new_connection={str(delete_visible).lower()}"
    ]


def _retry_lines(conn) -> list[str]:
    _insert_pair(conn, 50, "New")
    _insert_pair(conn, 50, "New")
    v1_count, v2_count = _count(conn, 50)
    lines = [
        f"RETRY_INSERT duplicate=false v1_count={v1_count} v2_count={v2_count}"
    ]

    _insert_pair(conn, 51, "New")
    for _ in range(2):
        _exec(conn, "UPDATE v1_leads SET funnel_stage = 'Contacted' WHERE id = 51")
        _exec(
            conn,
            "UPDATE v2.leads SET funnel_stage = 'Contacted' WHERE v1_lead_id = 51",
        )
        conn.commit()
    stage = _fetchone(conn, "SELECT funnel_stage FROM v1_leads WHERE id = 51")[0]
    rows = _count(conn, 51)[0]
    lines.append(f"RETRY_UPDATE value_stable={str(stage == 'Contacted').lower()} rows={rows}")

    _insert_pair(conn, 52, "New")
    for _ in range(2):
        _exec(conn, "DELETE FROM v2.leads WHERE v1_lead_id = 52")
        _exec(conn, "DELETE FROM v1_leads WHERE id = 52")
        conn.commit()
    v1_after, v2_after = _count(conn, 52)
    lines.append(
        f"RETRY_DELETE resurrected=false v1_count={v1_after} v2_count={v2_after}"
    )
    return lines


def _rollback_lines(conn) -> list[str]:
    before = _v1_checksum(conn)
    if not _schema_exists(conn):
        raise DrillError("schema v2 missing before rollback")
    _exec(conn, "DROP SCHEMA v2 CASCADE")
    conn.commit()
    after = _v1_checksum(conn)
    absent = not _schema_exists(conn)
    return [
        "ROLLBACK schema_v2="
        f"{'absent' if absent else 'present'} "
        f"v1_checksum_unchanged={str(before == after).lower()}"
    ]


REQUIRED_LINES = (
    "UPDATE_BOTH ok=true",
    "UPDATE_V2_ONLY ok=false column=funnel_stage",
    "DELETE_BOTH v1_count=0 v2_count=0",
    "DELETE_V2_ONLY missing=[4]",
    "CONCURRENT_DISTINCT ids=2 rows=2",
    "CONCURRENT_SAME_ID rows=1",
    "RESTART update_visible_to_new_connection=true delete_visible_to_new_connection=true",
    "RETRY_INSERT duplicate=false v1_count=1 v2_count=1",
    "RETRY_UPDATE value_stable=true rows=1",
    "RETRY_DELETE resurrected=false v1_count=0 v2_count=0",
    "ROLLBACK schema_v2=absent v1_checksum_unchanged=true",
)


def run_reliability_drill() -> list[str]:
    """Create the throwaway database, run the proofs, drop it, return raw lines."""
    _refuse_nonlocal(ADMIN_DSN)
    _refuse_nonlocal(DRILL_DSN)
    lines = [
        "RELIABILITY_DRILL_START",
        "engine=postgres host=127.0.0.1 database=v2_nov2_reliability",
        "live_database_used=false",
        "render_used=false",
        "app_database_touched=false",
        "production_claim=false",
        "process_restart=new_connection_after_commit",
    ]
    _reset_database()
    conn = _connect(DRILL_DSN)
    try:
        _exec(conn, SCHEMA_SQL)
        conn.commit()
        lines.extend(_update_lines(conn))
        lines.extend(_delete_lines(conn))
        lines.extend(_concurrent_lines())
        lines.extend(_restart_lines())
        lines.extend(_retry_lines(conn))
        lines.extend(_rollback_lines(conn))
    finally:
        conn.close()
        _drop_database()

    blob = "\n".join(lines)
    missing = [item for item in REQUIRED_LINES if item not in blob]
    if missing:
        lines.append("RELIABILITY_DRILL_FAIL " + ",".join(missing))
        raise DrillError("reliability assertions failed: " + ",".join(missing))
    lines.append("RELIABILITY_DRILL_PASS")
    return lines


if __name__ == "__main__":
    for line in run_reliability_drill():
        print(line)
