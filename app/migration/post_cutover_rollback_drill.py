"""Post-cutover rollback drill. Throwaway database only.

The 4 November log proved the pre-cutover procedure: ``rollback()`` turns
dual-write off and drops the shadow. That is not the post-cutover rollback.
After the read cut the application must move reads back to V1 while dual-write
stays on, so V1 keeps receiving writes and the shadow still matches it.

This drill starts in simulated post-cutover mode (``read_source=v2``,
dual-write on inside the harness), switches reads to V1 with
``switch_reads_to_v1``, then writes one new record in production order: V1
commits first, then the shadow upsert. It reads the new row back through
``serialize_lead`` and compares counts and SHA-256 checksums.

Throwaway database ``v2_post_cutover_rollback`` on ``127.0.0.1`` only. It never
opens ``realestate_db``, never reads ``LIVE_DATABASE_URL``, and never connects
to Render. Global ``V2_DUAL_WRITE`` stays false; the harness sets
``store.dual_write`` for this drill only. The database is dropped in a
``finally`` block.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

import psycopg2
from psycopg2 import sql
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.migration.dry_run import (
    DryRunStore,
    apply_dual_write,
    assert_isolated_dsn,
    row_digest,
    switch_reads_to_v1,
)
from app.migration.process_restart_worker import production_upsert_order

ADMIN_DSN = "postgresql://realestate:localpass@127.0.0.1:5432/postgres"
DRILL_DB = "v2_post_cutover_rollback"
DRILL_DSN = f"postgresql://realestate:localpass@127.0.0.1:5432/{DRILL_DB}"
ALLOWED_DATABASES = {"postgres", DRILL_DB}
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def sqlalchemy_dsn(dsn: str = DRILL_DSN) -> str:
    """Name the psycopg2 driver explicitly for SQLAlchemy.

    SQLAlchemy 2.1 resolves a plain ``postgresql://`` URL to psycopg v3, which
    this repo does not install; ``requirements.txt`` leaves SQLAlchemy unpinned,
    so CI gets 2.1 while ``requirements.lock`` pins 2.0. ``database.py``
    rewrites the app engine the same way. ``psycopg2.connect`` keeps the plain
    URL.
    """
    if dsn.startswith("postgresql://"):
        return dsn.replace("postgresql://", "postgresql+psycopg2://", 1)
    return dsn


TENANT_ID = 1
SEED_LEAD_ID = 1
NEW_LEAD_ID = 2
SEED_SESSION_ID = "1_post_cutover_seed"
NEW_SESSION_ID = "1_post_cutover_new"
SEED_NAME = "post-cutover-seed"
NEW_NAME = "post-cutover-new"

PHONE = "+919999999999"
LOCATION = "Baner"
BUDGET = "80L"
VISIT_DATE = "2026-12-01"
TEMPERATURE = "hot"
SCORE = "High"

# The original row must be byte-identical before and after the new write.
DIGEST_COLUMNS = (
    "name",
    "phone",
    "location",
    "budget",
    "visit_date",
    "lead_temperature",
)

V2_SCHEMA_SQL = """
CREATE SCHEMA v2;
CREATE TABLE v2.leads (
    v1_lead_id integer PRIMARY KEY,
    name text,
    phone text,
    location text,
    budget text,
    visit_date text,
    lead_temperature text
);
"""

V1_UPSERT = (
    "INSERT INTO leads "
    "(id, session_id, client_id, name, phone, location, budget, visit_date, "
    "lead_temperature, score) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
    "ON CONFLICT (id) DO NOTHING"
)
V2_UPSERT = (
    "INSERT INTO v2.leads "
    "(v1_lead_id, name, phone, location, budget, visit_date, lead_temperature) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s) "
    "ON CONFLICT (v1_lead_id) DO NOTHING"
)

REQUIRED_LINES = (
    "engine=postgres host=127.0.0.1 database=v2_post_cutover_rollback",
    "live_database_used=false",
    "render_used=false",
    "app_database_touched=false",
    "staging_claim=false",
    "live_dual_write_flag=false",
    "dual_write_source=drill_harness",
    "dual_write_still_on=true",
    "shadow_retained=true",
    "v1_latest=true",
    "duplicate=false",
    "lost=false",
    "v1_checksum_unchanged=true",
    "table_checksum_equal=true",
    "app_read=serialize_lead",
)


class DrillError(RuntimeError):
    """The drill refused to run, or an assertion failed."""


def _bool(value) -> str:
    return str(bool(value)).lower()


def _observed_dual_write_flag() -> str:
    """The live env flag, not a hardcoded proof line."""
    raw = os.environ.get("V2_DUAL_WRITE", "false")
    return (raw if raw is not None else "false").strip().lower() or "false"


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


def _connect(dsn: str = DRILL_DSN):
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


def _create_schema() -> None:
    """Create the V1 ORM tables the app reads, plus the V2 shadow."""
    from database import Base
    from models import Client, Lead
    from models import Session as SessionModel

    engine = create_engine(sqlalchemy_dsn())
    try:
        Base.metadata.create_all(
            engine,
            tables=[
                Client.__table__,
                SessionModel.__table__,
                Lead.__table__,
            ],
        )
    finally:
        engine.dispose()

    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(V2_SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


def _aggregate(lead_id: int, name: str) -> dict:
    """The same aggregate the production dual-write path receives."""
    return {
        "tenant": str(TENANT_ID),
        "tables": {
            "v1_leads": {lead_id: {"id": lead_id, "name": name}},
            "v2.leads": {lead_id: {"v1_lead_id": lead_id, "name": name}},
        },
    }


def _session_for(lead_id: int) -> str:
    return SEED_SESSION_ID if lead_id == SEED_LEAD_ID else NEW_SESSION_ID


def _seed(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO clients "
            "(id, company_name, email, hashed_password, api_key, "
            "is_api_key_hashed, is_active) "
            "VALUES (%s, %s, %s, %s, %s, true, true)",
            (
                TENANT_ID,
                "Post Cutover Tenant",
                "post-cutover@drill.local",
                "drill-not-a-password",
                "post-cutover-drill-key",
            ),
        )
        for session_id in (SEED_SESSION_ID, NEW_SESSION_ID):
            cur.execute(
                "INSERT INTO sessions (id, client_id) VALUES (%s, %s)",
                (session_id, TENANT_ID),
            )
        cur.execute(
            V1_UPSERT,
            (
                SEED_LEAD_ID,
                SEED_SESSION_ID,
                TENANT_ID,
                SEED_NAME,
                PHONE,
                LOCATION,
                BUDGET,
                VISIT_DATE,
                TEMPERATURE,
                SCORE,
            ),
        )
        cur.execute(
            V2_UPSERT,
            (SEED_LEAD_ID, SEED_NAME, PHONE, LOCATION, BUDGET, VISIT_DATE, TEMPERATURE),
        )
    conn.commit()


def _write_side(conn, table: str, lead_id: int, name: str) -> None:
    """Commit one side. The caller passes V1 first, as production does."""
    with conn.cursor() as cur:
        if table == "v1_leads":
            cur.execute(
                V1_UPSERT,
                (
                    lead_id,
                    _session_for(lead_id),
                    TENANT_ID,
                    name,
                    PHONE,
                    LOCATION,
                    BUDGET,
                    VISIT_DATE,
                    TEMPERATURE,
                    SCORE,
                ),
            )
        elif table == "v2.leads":
            cur.execute(
                V2_UPSERT,
                (lead_id, name, PHONE, LOCATION, BUDGET, VISIT_DATE, TEMPERATURE),
            )
        else:
            raise DrillError(f"unknown table {table}")
    conn.commit()


def _v1_row(conn, lead_id: int):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, name, phone, location, budget, visit_date, "
            "lead_temperature FROM leads WHERE id = %s",
            (lead_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    columns = ("id",) + DIGEST_COLUMNS
    return dict(zip(columns, row))


def _shadow_row(conn, lead_id: int):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT v1_lead_id, name, phone, location, budget, visit_date, "
            "lead_temperature FROM v2.leads WHERE v1_lead_id = %s",
            (lead_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    columns = ("id",) + DIGEST_COLUMNS
    return dict(zip(columns, row))


def _schema_exists(conn, name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
            (name,),
        )
        return cur.fetchone() is not None


def _latest_v1_id(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM leads ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
    return None if row is None else row[0]


def _latest_shadow_id(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT v1_lead_id FROM v2.leads ORDER BY v1_lead_id DESC LIMIT 1")
        row = cur.fetchone()
    return None if row is None else row[0]


def _count(conn, relation: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {relation}")
        return cur.fetchone()[0]


def _count_where(conn, relation: str, column: str, value) -> int:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT count(*) FROM {relation} WHERE {column} = %s", (value,)
        )
        return cur.fetchone()[0]


def _all_rows(conn, relation: str, id_column: str) -> list[dict]:
    """Every row on one side, in a stable order, with ``id`` as the digest key."""
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {id_column}, name, phone, location, budget, visit_date, "
            f"lead_temperature FROM {relation} ORDER BY {id_column}"
        )
        rows = cur.fetchall()
    columns = ("id",) + DIGEST_COLUMNS
    return [dict(zip(columns, row)) for row in rows]


def _app_read_latest() -> dict:
    """Read the newest V1 row through the application serializer. No HTTP."""
    from main import serialize_lead
    from models import Lead

    engine = create_engine(sqlalchemy_dsn())
    try:
        SessionFactory = sessionmaker(bind=engine)
        with SessionFactory() as session:
            lead = session.query(Lead).order_by(Lead.id.desc()).first()
            if lead is None:
                raise DrillError("no lead row on the V1 read path")
            return serialize_lead(lead)
    finally:
        engine.dispose()


def run_post_cutover_rollback_drill() -> list[str]:
    """Run the drill, drop the throwaway database, and return the log lines."""
    _refuse_nonlocal(ADMIN_DSN)
    _refuse_nonlocal(DRILL_DSN)

    flag = _observed_dual_write_flag()
    if flag != "false":
        raise DrillError(f"refusing V2_DUAL_WRITE={flag}; the global flag stays false")

    lines = [
        "POST_CUTOVER_ROLLBACK_DRILL_START",
        "engine=postgres host=127.0.0.1 database=v2_post_cutover_rollback",
        "live_database_used=false",
        "render_used=false",
        "app_database_touched=false",
        "staging_claim=false",
        f"live_dual_write_flag={flag}",
        "dual_write_source=drill_harness",
    ]

    try:
        reset_database()
        _create_schema()

        conn = _connect()
        try:
            _seed(conn)
            seed_row = _v1_row(conn, SEED_LEAD_ID)
            if seed_row is None:
                raise DrillError("seed row missing before the read cut")
            checksum_before = row_digest([seed_row], "id", DIGEST_COLUMNS)

            store = DryRunStore({"leads": []})
            store.dual_write = True
            apply_dual_write(store, _aggregate(SEED_LEAD_ID, SEED_NAME))
            store.read_source = "v2"
            lines.append(
                f"SIMULATED_CUT read_source={store.read_source} "
                f"dual_write={_bool(store.dual_write)}"
            )

            outcome = switch_reads_to_v1(store)
            shadow_schema = _schema_exists(conn, "v2")
            shadow_row = _shadow_row(conn, SEED_LEAD_ID)
            shadow_retained = bool(shadow_schema and shadow_row is not None)
            lines.append(
                f"SWITCH read_source={outcome['read_source']} "
                f"dual_write_still_on={_bool(store.dual_write)} "
                f"shadow_retained={_bool(shadow_retained)}"
            )
            if not store.dual_write or not shadow_retained:
                raise DrillError(
                    "switch_reads_to_v1 turned dual-write off or dropped the shadow"
                )

            decision = apply_dual_write(store, _aggregate(NEW_LEAD_ID, NEW_NAME))
            order = production_upsert_order(decision["written"])
            if order != ["v1_leads", "v2.leads"]:
                raise DrillError(f"unexpected production write order {order}")
            for table in order:
                _write_side(conn, table, NEW_LEAD_ID, NEW_NAME)
            lines.append("WRITE_ORDER v1_then_v2")

            v1_latest = _latest_v1_id(conn)
            shadow_latest = _latest_shadow_id(conn)
            v1_latest_ok = v1_latest == NEW_LEAD_ID and shadow_latest == NEW_LEAD_ID
            lines.append(
                f"V1_LATEST v1_latest={_bool(v1_latest_ok)} "
                f"v1_id={v1_latest} shadow_id={shadow_latest}"
            )
            if not v1_latest_ok:
                raise DrillError("the new row is not the latest on both sides")

            app_row = _app_read_latest()
            if app_row.get("id") != NEW_LEAD_ID:
                raise DrillError(
                    f"serialize_lead returned id {app_row.get('id')}, "
                    f"expected {NEW_LEAD_ID}"
                )
            lines.append(
                f"APP_READ app_read=serialize_lead lead_id={app_row['id']} "
                f"lead_temperature={app_row.get('lead_temperature')}"
            )

            v1_total = _count(conn, "leads")
            shadow_total = _count(conn, "v2.leads")
            new_v1 = _count_where(conn, "leads", "id", NEW_LEAD_ID)
            new_shadow = _count_where(conn, "v2.leads", "v1_lead_id", NEW_LEAD_ID)
            duplicate = not (
                v1_total == 2
                and shadow_total == 2
                and new_v1 == 1
                and new_shadow == 1
            )
            lines.append(
                f"COUNTS v1_total={v1_total} shadow_total={shadow_total} "
                f"new_v1_rows={new_v1} new_shadow_rows={new_shadow} "
                f"duplicate={_bool(duplicate)}"
            )

            after_row = _v1_row(conn, SEED_LEAD_ID)
            checksum_after = (
                row_digest([after_row], "id", DIGEST_COLUMNS)
                if after_row is not None
                else None
            )
            unchanged = checksum_after == checksum_before
            shadow_after = _shadow_row(conn, SEED_LEAD_ID)
            lost = (
                after_row is None
                or not unchanged
                or shadow_after is None
                or shadow_after != after_row
            )
            lines.append(
                f"CHECKSUM v1_checksum_unchanged={_bool(unchanged)} "
                f"before={checksum_before} after={checksum_after}"
            )

            v1_digest = row_digest(
                _all_rows(conn, "leads", "id"), "id", DIGEST_COLUMNS
            )
            shadow_digest = row_digest(
                _all_rows(conn, "v2.leads", "v1_lead_id"), "id", DIGEST_COLUMNS
            )
            table_parity = v1_digest == shadow_digest
            lines.append(
                f"TABLE_CHECKSUM v1={v1_digest} shadow={shadow_digest} "
                f"table_checksum_equal={_bool(table_parity)}"
            )
            lines.append(f"INTEGRITY lost={_bool(lost)}")
        finally:
            conn.close()
    finally:
        drop_database()

    if duplicate or lost or not table_parity:
        lines.append(
            f"POST_CUTOVER_ROLLBACK_FAIL duplicate={_bool(duplicate)} "
            f"lost={_bool(lost)} table_checksum_equal={_bool(table_parity)}"
        )
        raise DrillError("post-cutover rollback lost or duplicated a committed row")

    lines.append("POST_CUTOVER_ROLLBACK_PASS")
    return lines
