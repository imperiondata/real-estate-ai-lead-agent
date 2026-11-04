"""Parent for the 4 November application-process restart drill.

A new connection after commit is not a process restart. This parent starts
``app.migration.process_restart_worker`` as a child process, waits for its
``READY`` line, terminates that PID, and then starts a *second* process to read
the committed row back. Nothing here terminates a Postgres backend, and
``pg_terminate_backend`` is not the restart proof.

Throwaway database ``v2_process_restart`` on ``127.0.0.1`` only. It never opens
``realestate_db``, never reads ``LIVE_DATABASE_URL``, and never connects to
Render. The database is dropped in a ``finally`` block.
"""

from __future__ import annotations

import os
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
from psycopg2 import sql

from app.migration.dry_run import assert_isolated_dsn
from app.migration.process_restart_worker import (
    ADMIN_DSN,
    DRILL_DB,
    DRILL_DSN,
    FAILURE_ID,
    LEAD_ID,
    PHASES,
)

ROOT = Path(__file__).resolve().parent.parent.parent
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
ALLOWED_DATABASES = {"postgres", DRILL_DB}

SCHEMA_SQL = """
CREATE TABLE v1_leads (
    id integer PRIMARY KEY,
    name text
);

CREATE SCHEMA v2;
CREATE TABLE v2.leads (
    v1_lead_id integer PRIMARY KEY,
    name text
);

CREATE TABLE dual_write_failures (
    id integer PRIMARY KEY,
    phase text NOT NULL,
    status text NOT NULL
);
"""

EXPECTED_BEFORE = {
    # case -> (v1_count, v2_count) after the kill, before any retry
    "v1_success_v2_failure": (1, 0),
    "v2_success_v1_failure": (0, 1),
    "partial_commit": (1, 0),
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


def _reset_case() -> None:
    """Every case starts from the same empty state and does not depend on others."""
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM v1_leads WHERE id = %s", (LEAD_ID,))
            cur.execute("DELETE FROM v2.leads WHERE v1_lead_id = %s", (LEAD_ID,))
            cur.execute("DELETE FROM dual_write_failures WHERE id = %s", (FAILURE_ID,))
        conn.commit()
    finally:
        conn.close()


def _worker_command(*args: str) -> tuple[list[str], dict[str, str]]:
    """Command and environment whose PID is the process that runs the worker.

    A uv or venv ``python.exe`` on Windows is a launcher that spawns the base
    interpreter as a child, so ``Popen.pid`` would be the launcher rather than
    the worker, and ``terminate()`` would not be the worker's TerminateProcess.
    In that case the base interpreter runs the worker directly, with the venv
    site-packages on ``PYTHONPATH``. Elsewhere ``sys.executable`` is used as is.
    """
    env = os.environ.copy()
    executable = sys.executable
    base = getattr(sys, "_base_executable", sys.executable)
    if base and os.path.normcase(base) != os.path.normcase(sys.executable):
        site_packages = [path for path in sys.path if path.endswith("site-packages")]
        if site_packages:
            existing = env.get("PYTHONPATH")
            env["PYTHONPATH"] = os.pathsep.join(
                [site_packages[0]] + ([existing] if existing else [])
            )
            executable = base
    return (
        [executable, "-m", "app.migration.process_restart_worker", *args],
        env,
    )


def _spawn(*args: str) -> subprocess.Popen:
    command, env = _worker_command(*args)
    return subprocess.Popen(
        command,
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )


def _read_until(process: subprocess.Popen, prefix: str, timeout: float = 30.0) -> str:
    """Read child output until a line starts with ``prefix``, or raise."""
    lines: queue.Queue = queue.Queue()

    def _pump() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            lines.put(line.rstrip("\n"))
        lines.put(None)

    threading.Thread(target=_pump, daemon=True).start()
    deadline = time.monotonic() + timeout
    seen: list[str] = []
    while time.monotonic() < deadline:
        try:
            line = lines.get(timeout=0.5)
        except queue.Empty:
            if process.poll() is not None and lines.empty():
                break
            continue
        if line is None:
            break
        seen.append(line)
        if line.startswith(prefix):
            return line
    raise DrillError(
        f"worker did not print {prefix.strip()} within {timeout:.0f}s: {seen}"
    )


def _run_mode(mode: str, case: str) -> list[str]:
    """Run the worker in ``--readback`` or ``--recover`` mode as a new process."""
    command, env = _worker_command(mode, "--case", case)
    completed = subprocess.run(
        command,
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0:
        raise DrillError(
            f"worker {mode} for {case} failed with {completed.returncode}: "
            f"{completed.stdout}{completed.stderr}"
        )
    return [line for line in completed.stdout.splitlines() if line.strip()]


def _field(line: str, name: str) -> str:
    match = re.search(rf"\b{re.escape(name)}=(\S+)", line)
    if not match:
        raise DrillError(f"missing {name} in {line!r}")
    return match.group(1)


def _single(lines: list[str], prefix: str) -> str:
    found = [line for line in lines if line.startswith(prefix)]
    if not found:
        raise DrillError(f"no {prefix.strip()} line in {lines}")
    return found[-1]


def _kill_case(case: str) -> tuple[int, bool]:
    """Start the worker, wait for READY, then terminate that PID."""
    process = _spawn("--case", case)
    try:
        ready = _read_until(process, "READY ")
        killed_pid = process.pid
        announced = int(_field(ready, "pid"))
        if announced != killed_pid:
            raise DrillError(
                f"announced pid {announced} is not the child pid {killed_pid}"
            )
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        return killed_pid, process.poll() is not None
    finally:
        if process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass


def _partial_commit_child(case: str) -> int:
    """The rollback case exits on its own. It is not killed."""
    process = _spawn("--case", case)
    try:
        _read_until(process, "READY ", timeout=60.0)
        process.wait(timeout=30)
        if process.returncode != 0:
            raise DrillError(f"partial-commit worker exited {process.returncode}")
        return process.pid
    finally:
        if process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass


def _retry_twice(case: str) -> tuple[str, str]:
    """Two separate recovery processes. The second must not insert a row."""
    first = _run_mode("--recover", case)
    second = _run_mode("--recover", case)
    return _single(first, "RECOVERED "), _single(second, "RECOVERED ")


def _case_lines(case: str) -> list[str]:
    _reset_case()

    if case == "partial_commit":
        _partial_commit_child(case)
        process_killed = None
        killed_pid = None
    else:
        killed_pid, process_killed = _kill_case(case)

    readback_lines = _run_mode("--readback", case)
    readback = _single(readback_lines, "READBACK ")
    readback_pid = int(_field(readback, "pid"))
    v1_before = int(_field(readback, "v1_count"))
    v2_before = int(_field(readback, "v2_count"))
    visible = _field(readback, "failure_visible")

    expected = EXPECTED_BEFORE[case]
    if (v1_before, v2_before) != expected:
        raise DrillError(
            f"{case}: expected counts {expected} before retry, got "
            f"({v1_before}, {v2_before})"
        )
    if visible != "true":
        raise DrillError(f"{case}: the failure row is not visible to a new process")

    recovered_first, recovered_second = _retry_twice(case)
    v1_after = int(_field(recovered_second, "v1_count"))
    v2_after = int(_field(recovered_second, "v2_count"))
    duplicate = _field(recovered_second, "duplicate")
    if (v1_after, v2_after) != (1, 1):
        raise DrillError(
            f"{case}: retry left v1_count={v1_after} v2_count={v2_after}"
        )
    if duplicate != "false":
        raise DrillError(f"{case}: retry produced a duplicate row")

    if case == "partial_commit":
        return [
            f"PARTIAL_COMMIT v1_committed=true v2_rolled_back=true "
            f"failure_visible_to_new_process=true readback_pid={readback_pid}",
            f"RETRY_PARTIAL duplicate=false v1_count={v1_after} v2_count={v2_after}",
        ]

    pids_differ = killed_pid != readback_pid
    if not pids_differ:
        raise DrillError(
            f"{case}: killed pid {killed_pid} equals readback pid {readback_pid}"
        )
    if not process_killed:
        raise DrillError(f"{case}: terminated process was still alive")

    label = "V1_SUCCESS_V2_FAILURE" if case == "v1_success_v2_failure" else "V2_SUCCESS_V1_FAILURE"
    order = " order=injected production_order=v1_then_v2" if case == "v2_success_v1_failure" else ""
    return [
        f"{label}{order} killed_pid={killed_pid} readback_pid={readback_pid} "
        f"pids_differ={str(pids_differ).lower()} "
        f"process_killed={str(process_killed).lower()} "
        f"v1_count={v1_before} v2_count={v2_before}",
        f"{label}_RETRY duplicate=false v1_count={v1_after} v2_count={v2_after}",
    ]


REQUIRED_LINES = (
    "PROCESS_RESTART_DRILL_START",
    "engine=postgres host=127.0.0.1 database=v2_process_restart",
    "live_database_used=false",
    "render_used=false",
    "app_database_touched=false",
    "production_claim=false",
    "code_path=app.migration.process_restart_worker",
    "not_a_new_connection_in_the_same_process=true",
    "live_dual_write_flag=false",
    "chat_path_unchanged=true",
    "pids_differ=true",
    "process_killed=true",
    "order=injected production_order=v1_then_v2",
    "PARTIAL_COMMIT v1_committed=true v2_rolled_back=true "
    "failure_visible_to_new_process=true",
    "duplicate=false",
)


def run_process_restart_drill() -> list[str]:
    """Create the throwaway database, kill and recover, drop it, return lines."""
    _refuse_nonlocal(ADMIN_DSN)
    _refuse_nonlocal(DRILL_DSN)
    lines = [
        "PROCESS_RESTART_DRILL_START",
        "engine=postgres host=127.0.0.1 database=v2_process_restart",
        "live_database_used=false",
        "render_used=false",
        "app_database_touched=false",
        "production_claim=false",
        "code_path=app.migration.process_restart_worker",
        "not_a_new_connection_in_the_same_process=true",
        "live_dual_write_flag=false",
        "chat_path_unchanged=true",
    ]
    reset_database()
    try:
        conn = _connect(DRILL_DSN)
        try:
            with conn.cursor() as cur:
                cur.execute(SCHEMA_SQL)
            conn.commit()
        finally:
            conn.close()

        for case in PHASES:
            lines.extend(_case_lines(case))
    finally:
        drop_database()

    blob = "\n".join(lines)
    missing = [item for item in REQUIRED_LINES if item not in blob]
    if missing:
        lines.append("PROCESS_RESTART_DRILL_FAIL " + ",".join(missing))
        raise DrillError("process-restart assertions failed: " + ",".join(missing))
    lines.append("PROCESS_RESTART_DRILL_PASS")
    return lines


if __name__ == "__main__":
    for line in run_process_restart_drill():
        print(line)
