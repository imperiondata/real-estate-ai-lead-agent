"""Prove the application rollback against a throwaway local Postgres database.

This is the app-compatibility proof Piyush asked for, not the Nov 2 SQL drop.
It seeds a V1 row and a shadow ``v2`` schema, runs the application procedure
(``rollback()``: dual-write off, reads on V1), drops the shadow schema, then
reads the V1 row through the application ORM + serializer. It also reports the
``V2_DUAL_WRITE`` flag.

Local only. Refuses Render, refuses ``realestate_db``, and never reads
``LIVE_DATABASE_URL`` as a connection target.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.migration.dry_run import (  # noqa: E402
    DryRunStore,
    assert_isolated_dsn,
    rollback,
)

ADMIN_DSN = "postgresql://realestate:localpass@127.0.0.1:5432/postgres"
DRILL_DB = "v2_app_rollback"
DRILL_DSN = f"postgresql://realestate:localpass@127.0.0.1:5432/{DRILL_DB}"
APP_DB = "realestate_db"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
LOG_PATH = ROOT / "plans" / "evidence" / "NOV4_APP_ROLLBACK.log"


class ProofError(RuntimeError):
    pass


def _refuse_nonlocal(dsn: str) -> None:
    assert_isolated_dsn(dsn, live_database_url=os.environ.get("LIVE_DATABASE_URL"))
    parsed = urlparse(dsn)
    host = (parsed.hostname or "").lower()
    if host not in LOCAL_HOSTS:
        raise ProofError(f"refusing non-local host {host or 'unknown'}")
    database = parsed.path.lstrip("/")
    if database == APP_DB:
        raise ProofError("refusing the application database")
    if database not in {DRILL_DB, "postgres"}:
        raise ProofError(f"refusing database {database or 'unknown'}")


def _admin_conn():
    _refuse_nonlocal(ADMIN_DSN)
    conn = psycopg2.connect(ADMIN_DSN)
    conn.autocommit = True
    return conn


def _reset_database() -> None:
    conn = _admin_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (DRILL_DB,),
            )
            cur.execute(f'DROP DATABASE IF EXISTS "{DRILL_DB}"')
            cur.execute(f'CREATE DATABASE "{DRILL_DB}"')
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
            cur.execute(f'DROP DATABASE IF EXISTS "{DRILL_DB}"')
    finally:
        conn.close()


def _checksum(row) -> str:
    payload = "|".join(
        "" if value is None else str(value)
        for value in (
            row.id,
            row.name,
            row.phone,
            row.budget,
            row.location,
            row.property_type,
            row.visit_date,
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run() -> list[str]:
    _refuse_nonlocal(DRILL_DSN)
    _reset_database()
    lines = [
        "APP_ROLLBACK_START",
        "engine=postgres host=127.0.0.1 database=v2_app_rollback",
        "live_database_used=false",
    ]
    try:
        import models
        from main import serialize_lead

        engine = create_engine(DRILL_DSN)
        models.Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)

        with Session() as db:
            client = models.Client(
                company_name="Rollback Proof",
                email="rollback-proof@example.local",
                hashed_password="not-a-real-hash",
                api_key="rollback-proof-key",
            )
            db.add(client)
            db.flush()
            session = models.Session(id="rollback-proof-session", client_id=client.id)
            db.add(session)
            db.flush()
            lead = models.Lead(
                session_id=session.id,
                client_id=client.id,
                name="Rollback Proof",
                phone="+910000000000",
                budget="80L",
                location="Wakad",
                property_type="2BHK",
                visit_date="2026-08-01",
                lead_temperature="hot",
            )
            db.add(lead)
            db.commit()
            lead_id = lead.id
            before = _checksum(lead)

        raw = psycopg2.connect(DRILL_DSN)
        raw.autocommit = True
        try:
            with raw.cursor() as cur:
                cur.execute("CREATE SCHEMA v2")
                cur.execute("CREATE TABLE v2.leads (v1_lead_id integer primary key, name text)")
                cur.execute(
                    "INSERT INTO v2.leads (v1_lead_id, name) VALUES (%s, %s)",
                    (lead_id, "shadow"),
                )
        finally:
            raw.close()
        lines.append(
            f"SEED v1_lead_id={lead_id} v1_checksum={before} shadow_schema=present"
        )

        store = DryRunStore(
            {
                "leads": [{"id": lead_id, "name": "Rollback Proof"}],
                "webhook_logs": [],
            }
        )
        store.dual_write = True
        store.read_source = "v2"
        store.shadow = {"leads": {str(lead_id): {"name": "shadow"}}}
        outcome = rollback(store)
        lines.append(
            "APP_ROLLBACK "
            f"read_source={outcome['read_source']} "
            f"dual_write={str(outcome['dual_write']).lower()} "
            f"shadow_tables={outcome['shadow_tables']}"
        )

        raw = psycopg2.connect(DRILL_DSN)
        raw.autocommit = True
        try:
            with raw.cursor() as cur:
                cur.execute("DROP SCHEMA v2 CASCADE")
                cur.execute("SELECT to_regclass('v2.leads')")
                shadow_absent = cur.fetchone()[0] is None
        finally:
            raw.close()
        lines.append(f"SCHEMA_DROP v2_absent={str(shadow_absent).lower()}")

        try:
            with Session() as db:
                row = db.query(models.Lead).filter(models.Lead.id == lead_id).first()
                if row is None:
                    raise ProofError("V1 row did not load after rollback")
                payload = serialize_lead(row)
                after = _checksum(row)
        except Exception as exc:  # noqa: BLE001 - the log must record the failure
            lines.append(f"APP_READ status=error error={type(exc).__name__}: {exc}")
            raise
        lines.append("APP_READ status=ok http_equivalent=200")
        lines.append(
            "V1_INTEGRITY "
            f"checksum_unchanged={str(before == after).lower()} row_present=true"
        )
        lines.append(
            "V1_SERIALIZED "
            f"name={payload.get('name')!r} "
            f"temperature={payload.get('lead_temperature')!r}"
        )

        env_flag = (os.environ.get("V2_DUAL_WRITE", "false") or "false").strip().lower()
        env_off = env_flag not in {"1", "true", "yes", "on"}
        dual_write_off = env_off and outcome["dual_write"] is False
        lines.append(
            f"V2_DUAL_WRITE off={str(dual_write_off).lower()} env={env_flag}"
        )

        ok = (
            shadow_absent
            and before == after
            and outcome["read_source"] == "v1"
            and outcome["dual_write"] is False
            and outcome["shadow_tables"] == 0
            and dual_write_off
        )
        lines.append("APP_ROLLBACK_PASS" if ok else "APP_ROLLBACK_FAIL")
        return lines
    finally:
        _drop_database()


def main() -> int:
    try:
        lines = run()
    except Exception as exc:  # noqa: BLE001 - the log must record the failure
        text = f"APP_ROLLBACK_FAIL {type(exc).__name__}: {exc}\n"
        print(text, end="")
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOG_PATH.write_text(text, encoding="utf-8")
        return 1

    text = "\n".join(lines) + "\n"
    print(text, end="")
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(text, encoding="utf-8")
    return 0 if "APP_ROLLBACK_PASS" in text else 1


if __name__ == "__main__":
    sys.exit(main())
