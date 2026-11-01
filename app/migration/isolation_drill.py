"""Isolated V2 agency-isolation drill. Throwaway database on 127.0.0.1 only.

This module executes the V2 policy shape against a disposable PostgreSQL
database. It proves cross-agency isolation, the agency-administrator boundary,
and tenant-consistent composite foreign keys. It does not touch ``realestate_db``,
Render, or ``LIVE_DATABASE_URL``, and it does not change V1.

The fixture is synthetic and is not the section 4 backfill. The connecting
Docker user is a superuser, so every probe runs as a ``SET LOCAL ROLE`` inside a
transaction that is rolled back.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from urllib.parse import urlparse

import psycopg2
from psycopg2 import sql

from app.migration.dry_run import assert_isolated_dsn

ADMIN_DSN = "postgresql://realestate:localpass@127.0.0.1:5432/postgres"
DRILL_DB = "v2_isolation_drill"
DRILL_DSN = f"postgresql://realestate:localpass@127.0.0.1:5432/{DRILL_DB}"
ALLOWED_DATABASES = {"postgres", DRILL_DB}
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}

AGENCY_A = "11111111-1111-1111-1111-111111111111"
AGENCY_B = "22222222-2222-2222-2222-222222222222"
TENANT_A1 = "aaaaaaaa-0000-0000-0000-000000000001"
TENANT_A2 = "aaaaaaaa-0000-0000-0000-000000000002"
TENANT_B1 = "bbbbbbbb-0000-0000-0000-000000000001"
SESSION_A1 = "5a5a5a5a-0000-0000-0000-000000000001"
SESSION_A2 = "5a5a5a5a-0000-0000-0000-000000000002"
SESSION_B1 = "5b5b5b5b-0000-0000-0000-000000000001"
LEAD_A1_1 = "1e1e1e1e-0000-0000-0000-000000000001"
LEAD_A1_2 = "1e1e1e1e-0000-0000-0000-000000000002"
LEAD_A2_1 = "1e1e1e1e-0000-0000-0000-000000000003"
LEAD_B1_1 = "1e1e1e1e-0000-0000-0000-000000000004"
MESSAGE_A1 = "3e3e3e3e-0000-0000-0000-000000000001"
MESSAGE_B1 = "3e3e3e3e-0000-0000-0000-000000000002"


class DrillError(RuntimeError):
    """The drill refused to run, or an assertion failed."""


@dataclass(frozen=True)
class RoleNames:
    owner: str
    app: str
    agency: str
    agg: str
    fk: str

    def all(self) -> tuple[str, ...]:
        return (self.owner, self.app, self.agency, self.agg, self.fk)


def _refuse_nonlocal(dsn: str) -> None:
    """Loopback host only, and never the application database."""
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


def _fetchall(conn, statement, params=None):
    with conn.cursor() as cur:
        cur.execute(statement, params)
        return cur.fetchall()


def _create_roles(names: RoleNames) -> None:
    conn = _admin_conn()
    try:
        role_specs = (
            (names.owner, "NOBYPASSRLS"),
            (names.app, "NOBYPASSRLS"),
            (names.agency, "NOBYPASSRLS"),
            (names.agg, "BYPASSRLS"),
            (names.fk, "BYPASSRLS"),
        )
        with conn.cursor() as cur:
            for role, bypass in role_specs:
                cur.execute(
                    sql.SQL(
                        "CREATE ROLE {} NOLOGIN NOSUPERUSER {} "
                        "NOCREATEDB NOCREATEROLE"
                    ).format(sql.Identifier(role), sql.SQL(bypass))
                )
    finally:
        conn.close()


def _drop_roles(names: RoleNames) -> None:
    conn = _admin_conn()
    try:
        with conn.cursor() as cur:
            for role in names.all():
                cur.execute(
                    sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role))
                )
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


def _reset_database(names: RoleNames) -> None:
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
            cur.execute(
                sql.SQL("CREATE DATABASE {} OWNER {}").format(
                    sql.Identifier(DRILL_DB), sql.Identifier(names.owner)
                )
            )
    finally:
        conn.close()


SCHEMA_SQL = """
CREATE SCHEMA v2;

CREATE TABLE v2.agencies (
    id uuid PRIMARY KEY,
    name text NOT NULL
);

CREATE TABLE v2.tenants (
    id uuid PRIMARY KEY,
    agency_id uuid NOT NULL REFERENCES v2.agencies(id) ON DELETE CASCADE,
    name text NOT NULL
);

CREATE TABLE v2.sessions (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL REFERENCES v2.tenants(id) ON DELETE CASCADE,
    PRIMARY KEY (tenant_id, id)
);

CREATE TABLE v2.leads (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES v2.tenants(id) ON DELETE CASCADE,
    session_id uuid NOT NULL,
    name text,
    phone text,
    FOREIGN KEY (tenant_id, session_id)
        REFERENCES v2.sessions(tenant_id, id) ON DELETE CASCADE
);

CREATE TABLE v2.messages (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES v2.tenants(id) ON DELETE CASCADE,
    session_id uuid NOT NULL,
    content text,
    FOREIGN KEY (tenant_id, session_id)
        REFERENCES v2.sessions(tenant_id, id) ON DELETE CASCADE
);

ALTER TABLE v2.leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE v2.leads FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON v2.leads
    USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

ALTER TABLE v2.sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE v2.sessions FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON v2.sessions
    USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

ALTER TABLE v2.messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE v2.messages FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON v2.messages
    USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

ALTER TABLE v2.tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE v2.tenants FORCE ROW LEVEL SECURITY;
CREATE POLICY agency_isolation ON v2.tenants
    USING (agency_id = current_setting('app.current_agency_id', true)::uuid)
    WITH CHECK (agency_id = current_setting('app.current_agency_id', true)::uuid);

CREATE FUNCTION v2.resolve_agency_id(requested uuid) RETURNS uuid
LANGUAGE sql STABLE AS $$
    SELECT agency_id FROM v2.tenants WHERE id = requested
$$;

CREATE FUNCTION v2.agency_lead_count() RETURNS bigint
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, v2 AS $$
    SELECT count(*)
    FROM v2.leads
    WHERE tenant_id IN (
        SELECT id
        FROM v2.tenants
        WHERE agency_id =
            nullif(current_setting('app.current_agency_id', true), '')::uuid
    )
$$;
"""


def _create_schema(conn, names: RoleNames) -> None:
    with conn.cursor() as cur:
        cur.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(names.owner)))
        cur.execute(SCHEMA_SQL)
    conn.commit()

    with conn.cursor() as cur:
        cur.execute("RESET ROLE")
        cur.execute(
            sql.SQL("ALTER FUNCTION v2.agency_lead_count() OWNER TO {}").format(
                sql.Identifier(names.agg)
            )
        )
        cur.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(DRILL_DB),
                sql.SQL(", ").join(
                    sql.Identifier(role)
                    for role in (names.app, names.agency, names.agg, names.fk)
                ),
            )
        )
        cur.execute(
            sql.SQL("GRANT USAGE ON SCHEMA v2 TO {}").format(
                sql.SQL(", ").join(
                    sql.Identifier(role)
                    for role in (names.app, names.agency, names.agg, names.fk)
                )
            )
        )
        cur.execute(
            sql.SQL("GRANT SELECT, INSERT, UPDATE ON {}, {}, {} TO {}").format(
                sql.Identifier("v2", "leads"),
                sql.Identifier("v2", "messages"),
                sql.Identifier("v2", "sessions"),
                sql.Identifier(names.app),
            )
        )
        cur.execute(
            sql.SQL(
                "GRANT SELECT (id, agency_id, name) ON {} TO {}"
            ).format(
                sql.Identifier("v2", "tenants"),
                sql.Identifier(names.agency),
            )
        )
        cur.execute(
            sql.SQL("GRANT EXECUTE ON FUNCTION v2.resolve_agency_id(uuid) TO {}").format(
                sql.Identifier(names.agency)
            )
        )
        cur.execute(
            sql.SQL("GRANT EXECUTE ON FUNCTION v2.agency_lead_count() TO {}").format(
                sql.Identifier(names.agency)
            )
        )
        cur.execute(
            sql.SQL("GRANT SELECT ON {}, {} TO {}").format(
                sql.Identifier("v2", "tenants"),
                sql.Identifier("v2", "leads"),
                sql.Identifier(names.agg),
            )
        )
        cur.execute(
            sql.SQL("GRANT SELECT, REFERENCES ON {}, {} TO {}").format(
                sql.Identifier("v2", "sessions"),
                sql.Identifier("v2", "tenants"),
                sql.Identifier(names.fk),
            )
        )
        cur.execute(
            sql.SQL("GRANT INSERT ON {}, {} TO {}").format(
                sql.Identifier("v2", "leads"),
                sql.Identifier("v2", "messages"),
                sql.Identifier(names.fk),
            )
        )
    conn.commit()


def _seed(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO v2.agencies (id, name) VALUES (%s, 'Agency A'), (%s, 'Agency B')",
            (AGENCY_A, AGENCY_B),
        )
        cur.execute(
            "INSERT INTO v2.tenants (id, agency_id, name) VALUES "
            "(%s, %s, 'A1'), (%s, %s, 'A2'), (%s, %s, 'B1')",
            (TENANT_A1, AGENCY_A, TENANT_A2, AGENCY_A, TENANT_B1, AGENCY_B),
        )
        cur.execute(
            "INSERT INTO v2.sessions (id, tenant_id) VALUES "
            "(%s, %s), (%s, %s), (%s, %s)",
            (SESSION_A1, TENANT_A1, SESSION_A2, TENANT_A2, SESSION_B1, TENANT_B1),
        )
        cur.execute(
            "INSERT INTO v2.leads (id, tenant_id, session_id, name, phone) VALUES "
            "(%s, %s, %s, 'A1 Lead One', '90001'), "
            "(%s, %s, %s, 'A1 Lead Two', '90002'), "
            "(%s, %s, %s, 'A2 Lead', '90003'), "
            "(%s, %s, %s, 'B1 Lead', '90004')",
            (
                LEAD_A1_1,
                TENANT_A1,
                SESSION_A1,
                LEAD_A1_2,
                TENANT_A1,
                SESSION_A1,
                LEAD_A2_1,
                TENANT_A2,
                SESSION_A2,
                LEAD_B1_1,
                TENANT_B1,
                SESSION_B1,
            ),
        )
        cur.execute(
            "INSERT INTO v2.messages (id, tenant_id, session_id, content) VALUES "
            "(%s, %s, %s, 'A1 message'), (%s, %s, %s, 'B1 message')",
            (MESSAGE_A1, TENANT_A1, SESSION_A1, MESSAGE_B1, TENANT_B1, SESSION_B1),
        )
    conn.commit()


def _apply_context(cur, role: str, settings: dict | None) -> None:
    cur.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
    for key, value in (settings or {}).items():
        cur.execute("SELECT set_config(%s, %s, true)", (key, value))


def _run(role: str, settings: dict | None, query: str, params=None, *, fetch: bool):
    conn = _connect(DRILL_DSN)
    try:
        with conn.cursor() as cur:
            _apply_context(cur, role, settings)
            cur.execute(query, params)
            rows = cur.fetchall() if fetch else []
        return rows, None
    except psycopg2.Error as exc:
        return [], exc.pgcode
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()


def _plain_fetch(query: str, params=None):
    conn = _connect(DRILL_DSN)
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()
    finally:
        conn.rollback()
        conn.close()


def _scalar(rows, code):
    if code is not None:
        return f"error:{code}"
    return rows[0][0] if rows else "no_rows"


def _tenant_names(names: RoleNames, agency_id: str):
    rows, code = _run(
        names.agency,
        {"app.current_agency_id": agency_id},
        "SELECT name FROM v2.tenants ORDER BY name",
        fetch=True,
    )
    return [row[0] for row in rows] if code is None else f"error:{code}"


def _insert_outcome(names: RoleNames, query: str, params):
    _rows, code = _run(names.fk, None, query, params, fetch=False)
    return code


def _proof_lines(names: RoleNames) -> list[str]:
    lines: list[str] = []

    flags = _plain_fetch(
        """
        SELECT c.relrowsecurity, c.relforcerowsecurity,
               pg_get_userbyid(c.relowner)
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'v2' AND c.relname = 'leads'
        """
    )
    if not flags:
        raise DrillError("could not read RLS flags for v2.leads")
    enabled, forced, table_owner = flags[0]
    app_attrs = _plain_fetch(
        "SELECT rolbypassrls FROM pg_roles WHERE rolname = %s", (names.app,)
    )
    app_bypass = app_attrs[0][0] if app_attrs else None
    app_is_owner = table_owner == names.app
    lines.append(
        "RLS_FLAGS leads_enabled={} leads_forced={} app_bypassrls={} "
        "app_is_owner={}".format(
            enabled,
            forced,
            str(app_bypass).lower(),
            str(app_is_owner).lower(),
        )
    )

    owner_rows, owner_code = _run(
        names.owner, None, "SELECT count(*) FROM v2.leads", fetch=True
    )
    lines.append(f"OWNER_FORCE rows_without_setting={_scalar(owner_rows, owner_code)}")

    a1_rows, a1_code = _run(
        names.app,
        {"app.current_tenant_id": TENANT_A1},
        "SELECT count(*) FROM v2.leads",
        fetch=True,
    )
    a2_rows, a2_code = _run(
        names.app,
        {"app.current_tenant_id": TENANT_A2},
        "SELECT count(*) FROM v2.leads",
        fetch=True,
    )
    b1_rows, b1_code = _run(
        names.app,
        {"app.current_tenant_id": TENANT_B1},
        "SELECT count(*) FROM v2.leads",
        fetch=True,
    )
    missing_rows, missing_code = _run(
        names.app, None, "SELECT count(*) FROM v2.leads", fetch=True
    )
    lines.append(
        "TENANT_RLS a1_rows={} a2_rows={} b1_rows={} "
        "missing_setting_rows={}".format(
            _scalar(a1_rows, a1_code),
            _scalar(a2_rows, a2_code),
            _scalar(b1_rows, b1_code),
            _scalar(missing_rows, missing_code),
        )
    )

    _bad_rows, bad_code = _run(
        names.app,
        {"app.current_tenant_id": "not-a-uuid"},
        "SELECT count(*) FROM v2.leads",
        fetch=True,
    )
    lines.append(f"RLS_BAD_SETTING error={bad_code or 'none'} rows_returned=0")

    lines.append(
        "CROSS_AGENCY agency_a_tenants={} agency_b_tenants={}".format(
            _tenant_names(names, AGENCY_A),
            _tenant_names(names, AGENCY_B),
        )
    )

    own_resolved, own_code = _run(
        names.agency,
        {"app.current_agency_id": AGENCY_A},
        "SELECT v2.resolve_agency_id(%s)::text",
        (TENANT_A1,),
        fetch=True,
    )
    other_resolved, other_code = _run(
        names.agency,
        {"app.current_agency_id": AGENCY_A},
        "SELECT v2.resolve_agency_id(%s)::text",
        (TENANT_B1,),
        fetch=True,
    )
    if own_code is not None or not own_resolved or own_resolved[0][0] != AGENCY_A:
        resolved_label = "own_resolution_failed"
    elif other_code is not None:
        resolved_label = f"error:{other_code}"
    else:
        resolved_label = other_resolved[0][0] if other_resolved else None
    lines.append(
        f"AGENCY_ADMIN_IMPERSONATION requested_other_agency resolved={resolved_label}"
    )

    _pii_rows, pii_code = _run(
        names.agency,
        {"app.current_agency_id": AGENCY_A},
        "SELECT name, phone FROM v2.leads",
        fetch=True,
    )
    lines.append(
        "AGENCY_ADMIN_PII select={} sqlstate={}".format(
            "denied" if pii_code == "42501" else "allowed",
            pii_code or "none",
        )
    )

    own_count, own_count_code = _run(
        names.agency,
        {"app.current_agency_id": AGENCY_A},
        "SELECT v2.agency_lead_count()",
        fetch=True,
    )
    other_count, other_count_code = _run(
        names.agency,
        {"app.current_agency_id": AGENCY_B},
        "SELECT v2.agency_lead_count()",
        fetch=True,
    )
    missing_count, missing_count_code = _run(
        names.agency,
        None,
        "SELECT v2.agency_lead_count()",
        fetch=True,
    )
    lines.append(
        "AGENCY_ADMIN_AGGREGATE own={} other_when_setting_switched={} "
        "missing_setting={}".format(
            _scalar(own_count, own_count_code),
            _scalar(other_count, other_count_code),
            _scalar(missing_count, missing_count_code),
        )
    )

    privilege_rows = _plain_fetch(
        "SELECT has_table_privilege(%s, 'v2.leads', 'SELECT'), "
        "has_table_privilege(%s, 'v2.leads', 'INSERT')",
        (names.agency, names.agency),
    )
    select_priv, insert_priv = privilege_rows[0]
    columns = {
        row[0]
        for row in _plain_fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'v2' AND table_name = 'leads'"
        )
    }
    lines.append(
        "AGENCY_ADMIN_RESTRICTION pii={} insert_leads={} operational_owner={}".format(
            "denied" if not select_priv else "allowed",
            "not_granted" if not insert_priv else "granted",
            "tenant" if "tenant_id" in columns and "agency_id" not in columns else "unknown",
        )
    )

    same_code = _insert_outcome(
        names,
        "INSERT INTO v2.leads (id, tenant_id, session_id, name, phone) "
        "VALUES (%s, %s, %s, 'Same Tenant', '90009')",
        (str(uuid.uuid4()), TENANT_A1, SESSION_A1),
    )
    lines.append(
        "FK_SAME_TENANT insert={}".format(
            "accepted" if same_code is None else f"rejected sqlstate={same_code}"
        )
    )

    cross_code = _insert_outcome(
        names,
        "INSERT INTO v2.messages (id, tenant_id, session_id, content) "
        "VALUES (%s, %s, %s, 'Cross Tenant')",
        (str(uuid.uuid4()), TENANT_B1, SESSION_A1),
    )
    lines.append(
        "FK_CROSS_TENANT insert={}".format(
            f"rejected sqlstate={cross_code}" if cross_code else "accepted"
        )
    )

    lead_session_code = _insert_outcome(
        names,
        "INSERT INTO v2.leads (id, tenant_id, session_id, name, phone) "
        "VALUES (%s, %s, %s, 'Wrong Session', '90010')",
        (str(uuid.uuid4()), TENANT_A1, SESSION_B1),
    )
    lines.append(
        "FK_LEAD_SESSION insert={}".format(
            f"rejected sqlstate={lead_session_code}"
            if lead_session_code
            else "accepted"
        )
    )

    return lines


REQUIRED_LINES = (
    "RLS_FLAGS leads_enabled=True leads_forced=True app_bypassrls=false "
    "app_is_owner=false",
    "OWNER_FORCE rows_without_setting=0",
    "TENANT_RLS a1_rows=2 a2_rows=1 b1_rows=1 missing_setting_rows=0",
    "RLS_BAD_SETTING error=22P02 rows_returned=0",
    "CROSS_AGENCY agency_a_tenants=['A1', 'A2'] agency_b_tenants=['B1']",
    "AGENCY_ADMIN_IMPERSONATION requested_other_agency resolved=None",
    "AGENCY_ADMIN_PII select=denied sqlstate=42501",
    "AGENCY_ADMIN_AGGREGATE own=3 other_when_setting_switched=1 missing_setting=0",
    "AGENCY_ADMIN_RESTRICTION pii=denied insert_leads=not_granted "
    "operational_owner=tenant",
    "FK_SAME_TENANT insert=accepted",
    "FK_CROSS_TENANT insert=rejected sqlstate=23503",
    "FK_LEAD_SESSION insert=rejected sqlstate=23503",
)


def run_isolation_drill() -> list[str]:
    """Create the throwaway database, run the proofs, clean up, return lines."""
    _refuse_nonlocal(ADMIN_DSN)
    _refuse_nonlocal(DRILL_DSN)

    suffix = uuid.uuid4().hex[:8]
    names = RoleNames(
        owner=f"iso_owner_{suffix}",
        app=f"iso_app_{suffix}",
        agency=f"iso_agency_{suffix}",
        agg=f"iso_agg_{suffix}",
        fk=f"iso_fk_{suffix}",
    )
    lines = [
        "ISOLATION_DRILL_START",
        "engine=postgres host=127.0.0.1 database=v2_isolation_drill",
        "live_database_used=false",
        "render_used=false",
        "app_database_touched=false",
        "production_claim=false",
        "v1_render_rls=not_shipped",
    ]

    try:
        _create_roles(names)
        _reset_database(names)
        conn = _connect(DRILL_DSN)
        try:
            _create_schema(conn, names)
            _seed(conn)
        finally:
            conn.close()
        lines.extend(_proof_lines(names))
    finally:
        _drop_database()
        _drop_roles(names)

    blob = "\n".join(lines)
    missing = [item for item in REQUIRED_LINES if item not in blob]
    if missing:
        lines.append("ISOLATION_DRILL_FAIL " + ",".join(missing))
        raise DrillError("isolation assertions failed: " + ",".join(missing))
    lines.append("ISOLATION_DRILL_PASS")
    return lines


if __name__ == "__main__":
    for line in run_isolation_drill():
        print(line)
