"""Process-restart worker for the 4 November drill. Throwaway database only.

This module is the process that gets killed. ``app.migration.process_restart_drill``
launches it as ``python -m app.migration.process_restart_worker --case <case>``,
then again as a different operating-system process with ``--readback`` or
``--recover``.

The dual-write decision is made by ``apply_dual_write`` from
``app.migration.dry_run`` and persisted to Postgres. ``DryRunStore`` is
in-memory and dies with this process, so it cannot be the durability proof. The
proof is the committed ``dual_write_failures`` row and the committed lead row,
read back by a second process.

Refuses any DSN that is not loopback, and any database other than ``postgres``
and the throwaway ``v2_process_restart``. Never opens ``realestate_db``, never
reads ``LIVE_DATABASE_URL``, and never connects to Render.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from urllib.parse import urlparse

import psycopg2

from app.migration.dry_run import (
    DryRunStore,
    apply_dual_write,
    assert_isolated_dsn,
    retry_missing,
)

ADMIN_DSN = "postgresql://realestate:localpass@127.0.0.1:5432/postgres"
DRILL_DB = "v2_process_restart"
DRILL_DSN = f"postgresql://realestate:localpass@127.0.0.1:5432/{DRILL_DB}"
ALLOWED_DATABASES = {"postgres", DRILL_DB}
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}

LEAD_ID = 1
LEAD_NAME = "restart-lead"
FAILURE_ID = 1

# Case name -> persisted phase. The phase is what the recovery process reads.
PHASES = {
    "v1_success_v2_failure": "after_v1_before_v2",
    "v2_success_v1_failure": "after_v2_before_v1",
    "partial_commit": "after_v1_v2_rolled_back",
}

# What each phase already committed, and what is still missing. The recovery
# process derives the missing side from the committed row, not from the store.
PHASE_WRITTEN = {
    "after_v1_before_v2": ("v1_leads",),
    "after_v2_before_v1": ("v2.leads",),
    "after_v1_v2_rolled_back": ("v1_leads",),
}
PHASE_MISSING = {
    "after_v1_before_v2": ("v2.leads",),
    "after_v2_before_v1": ("v1_leads",),
    "after_v1_v2_rolled_back": ("v2.leads",),
}

UPSERTS = {
    "v1_leads": (
        "INSERT INTO v1_leads (id, name) VALUES (%s, %s) "
        "ON CONFLICT (id) DO NOTHING"
    ),
    "v2.leads": (
        "INSERT INTO v2.leads (v1_lead_id, name) VALUES (%s, %s) "
        "ON CONFLICT (v1_lead_id) DO NOTHING"
    ),
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


def _connect(dsn: str = DRILL_DSN):
    _refuse_nonlocal(dsn)
    return psycopg2.connect(dsn)


def _aggregate() -> dict:
    """One lead, both sides. The same id and name for every case."""
    return {
        "tenant": "1",
        "tables": {
            "v1_leads": {LEAD_ID: {"id": LEAD_ID, "name": LEAD_NAME}},
            "v2.leads": {LEAD_ID: {"v1_lead_id": LEAD_ID, "name": LEAD_NAME}},
        },
    }


def _store() -> DryRunStore:
    store = DryRunStore({"leads": []})
    store.dual_write = True
    return store


def _upsert(conn, table: str) -> int:
    with conn.cursor() as cur:
        cur.execute(UPSERTS[table], (LEAD_ID, LEAD_NAME))
        inserted = cur.rowcount
    conn.commit()
    return inserted


def _counts(conn) -> tuple[int, int]:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM v1_leads WHERE id = %s", (LEAD_ID,))
        v1 = cur.fetchone()[0]
        cur.execute(
            "SELECT count(*) FROM v2.leads WHERE v1_lead_id = %s", (LEAD_ID,)
        )
        v2 = cur.fetchone()[0]
    return v1, v2


def _record_failure(conn, phase: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO dual_write_failures (id, phase, status) "
            "VALUES (%s, %s, 'open') "
            "ON CONFLICT (id) DO UPDATE "
            "SET phase = EXCLUDED.phase, status = EXCLUDED.status",
            (FAILURE_ID, phase),
        )
    conn.commit()


def _failure_row(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT phase, status FROM dual_write_failures WHERE id = %s",
            (FAILURE_ID,),
        )
        return cur.fetchone()


def _write_case(conn, case: str) -> None:
    """Take the real dual-write decision, then persist it to Postgres."""
    phase = PHASES[case]
    aggregate = _aggregate()
    store = _store()

    if case == "v1_success_v2_failure":
        fail_tables = ["v2.leads"]
    elif case == "v2_success_v1_failure":
        fail_tables = ["v1_leads"]
    else:
        # The decision is complete. V2 is then rolled back by the injected
        # transaction below, which is the partial-commit case.
        fail_tables = None

    decision = apply_dual_write(
        store, aggregate, fail_tables=fail_tables, error="injected_crash"
    )

    if case == "partial_commit":
        # V1 commits. The V2 row is inserted inside its own transaction and that
        # transaction is rolled back. The failure row commits separately.
        _upsert(conn, "v1_leads")
        with conn.cursor() as cur:
            cur.execute(UPSERTS["v2.leads"], (LEAD_ID, LEAD_NAME))
        conn.rollback()
        _record_failure(conn, phase)
        return

    # V1 is authoritative and is committed first in production. The injected
    # V2-before-V1 case only skips the V1 write; it does not reorder a commit.
    for table in decision["written"]:
        _upsert(conn, table)
    _record_failure(conn, phase)


def _run_write_case(case: str) -> int:
    conn = _connect()
    try:
        _write_case(conn, case)
    finally:
        conn.close()

    print(f"READY phase={PHASES[case]} pid={os.getpid()}", flush=True)
    if case == "partial_commit":
        return 0

    # The parent terminates this process here. No signal handler, no atexit
    # hook, and no open transaction: the missing side is never written on the
    # way out, and no other side is committed after the READY line.
    time.sleep(30)
    return 0


def _run_readback(case: str) -> int:
    """A different process reads the committed state with its own connection."""
    phase = PHASES[case]
    conn = _connect()
    try:
        v1, v2 = _counts(conn)
        row = _failure_row(conn)
    finally:
        conn.close()

    visible = row is not None and row[0] == phase
    status = row[1] if row is not None else "none"
    print(
        f"READBACK pid={os.getpid()} phase={phase} status={status} "
        f"failure_visible={str(visible).lower()} v1_count={v1} v2_count={v2}",
        flush=True,
    )
    return 0


def _run_recover(case: str) -> int:
    """Read the failure row, retry the missing side once, then report."""
    conn = _connect()
    try:
        row = _failure_row(conn)
        if row is None:
            raise DrillError(f"no failure row to recover for {case}")
        stored_phase, status = row
        if stored_phase not in PHASE_MISSING:
            raise DrillError(f"unknown phase {stored_phase}")

        missing_tables = list(PHASE_MISSING[stored_phase])
        v1_before, v2_before = _counts(conn)
        print(
            f"READBACK pid={os.getpid()} phase={stored_phase} status={status} "
            f"failure_visible=true v1_count={v1_before} v2_count={v2_before}",
            flush=True,
        )

        # A resolved row has nothing missing. retry_missing is still called so
        # the second pass goes through the same idempotent decision.
        if status == "resolved":
            missing_tables = []

        aggregate = _aggregate()
        store = _store()
        failure = {
            "tenant": "1",
            "status": status,
            "written": list(PHASE_WRITTEN[stored_phase]),
            "missing": missing_tables,
            "error": "injected_crash",
            "kind": "transient",
            "retry_count": 0,
        }
        decision = retry_missing(store, aggregate, failure)

        for table in missing_tables:
            _upsert(conn, table)

        with conn.cursor() as cur:
            cur.execute(
                "UPDATE dual_write_failures SET status = 'resolved' WHERE id = %s",
                (FAILURE_ID,),
            )
        conn.commit()
        v1_after, v2_after = _counts(conn)
    finally:
        conn.close()

    duplicate = v1_after > 1 or v2_after > 1
    print(
        f"RECOVERED pid={os.getpid()} phase={stored_phase} status=resolved "
        f"retry={decision['status']} duplicate={str(duplicate).lower()} "
        f"v1_count={v1_after} v2_count={v2_after}",
        flush=True,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=sorted(PHASES), required=True)
    parser.add_argument("--readback", action="store_true")
    parser.add_argument("--recover", action="store_true")
    args = parser.parse_args(argv)

    if args.readback:
        return _run_readback(args.case)
    if args.recover:
        return _run_recover(args.case)
    return _run_write_case(args.case)


if __name__ == "__main__":
    sys.exit(main())
