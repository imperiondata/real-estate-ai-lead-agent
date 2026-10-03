"""Live Render Postgres drill. Reads LIVE_* only. Never prints the URL.

Local backups stay on db_backup.py / db_restore.py. Do not point DATABASE_URL
at Render.

  python live_dr.py counts
  python live_dr.py dump
  python live_dr.py probe-down
  python live_dr.py restore --dump ..\\dr_dumps\\backup_YYYYMMDD_HHMMSS_a.sql --confirm LIVE
  python live_dr.py probe-up
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parent
DEMO_KEY = "secret-client-key-123"
COUNT_SQL = """
SELECT 'clients' AS tbl, COUNT(*)::text FROM clients
UNION ALL SELECT 'sessions', COUNT(*)::text FROM sessions
UNION ALL SELECT 'leads', COUNT(*)::text FROM leads
UNION ALL SELECT 'messages', COUNT(*)::text FROM messages
UNION ALL SELECT 'event_logs', COUNT(*)::text FROM event_logs
UNION ALL SELECT 'follow_up_states', COUNT(*)::text FROM follow_up_states
UNION ALL SELECT 'dlq_events', COUNT(*)::text FROM dlq_events
ORDER BY 1;
"""


def redact(text: str) -> str:
    text = re.sub(r"postgres(?:ql)?://\S+", "[redacted-url]", text or "")
    text = re.sub(r"password=\S+", "password=[redacted]", text, flags=re.I)
    return text


def _env_value(name: str) -> str:
    raw = os.getenv(name, "")
    if raw:
        return raw.strip().strip('"').strip("'")
    env_path = REPO / ".env"
    if not env_path.exists():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def assert_live_url(url: str) -> str:
    if not url or not url.startswith("postgres"):
        raise SystemExit("LIVE_DATABASE_URL missing or not postgres")
    host = (urlparse(url).hostname or "").lower()
    if host in ("", "localhost", "127.0.0.1", "::1"):
        raise SystemExit("refusing local database host")
    return url


def dump_dir() -> Path:
    raw = os.getenv("DR_DUMP_DIR", "").strip()
    path = Path(raw) if raw else REPO.parent / "dr_dumps"
    path = path.resolve()
    repo = REPO.resolve()
    if path == repo or repo in path.parents:
        raise SystemExit("refusing dump dir inside the repo")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _child_env() -> dict:
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)
    env.pop("PGPASSWORD", None)
    return env


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_child_env(),
    )


def _psql() -> str:
    path = shutil.which("psql")
    if not path:
        raise SystemExit("psql not on PATH")
    return path


def _pg_dump() -> str:
    path = shutil.which("pg_dump")
    if not path:
        raise SystemExit("pg_dump not on PATH")
    return path


def _print_proc(prefix: str, proc: subprocess.CompletedProcess) -> None:
    err = redact(proc.stderr).strip()
    if err:
        print(prefix + err[:800])


def print_counts(url: str) -> None:
    proc = _run(
        [_psql(), "--dbname", url, "-v", "ON_ERROR_STOP=1", "-A", "-F", "|", "-c", COUNT_SQL],
        120,
    )
    print(f"counts_rc={proc.returncode}")
    print(redact(proc.stdout).strip())
    _print_proc("counts_err=", proc)
    if proc.returncode != 0:
        raise SystemExit("counts failed")
    proc = _run(
        [_psql(), "--dbname", url, "-v", "ON_ERROR_STOP=1", "-A", "-t", "-c", "SELECT id FROM clients ORDER BY id;"],
        60,
    )
    ids = redact(proc.stdout).strip().replace("\n", ",")
    print(f"clients_rc={proc.returncode} client_ids={ids}")
    _print_proc("clients_err=", proc)
    if proc.returncode != 0:
        raise SystemExit("client id query failed")


def _has_clients_table(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace")
    return re.search(r"CREATE TABLE\s+(public\.)?clients\b", text) is not None


def cmd_dump(url: str) -> None:
    out = dump_dir()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    print(f"stamp={stamp}")
    print(f"dump_dir={out}")
    for tag in ("a", "b"):
        path = out / f"backup_{stamp}_{tag}.sql"
        proc = _run(
            [
                _pg_dump(),
                "--dbname",
                url,
                "-f",
                str(path),
                "--no-owner",
                "--no-privileges",
                "--clean",
            ],
            600,
        )
        size = path.stat().st_size if path.exists() else 0
        print(f"dump_{tag}_rc={proc.returncode} bytes={size} name={path.name}")
        _print_proc(f"dump_{tag}_err=", proc)
        if proc.returncode != 0 or size == 0 or not _has_clients_table(path):
            raise SystemExit(f"dump {tag} failed")
    print("PASS")


def _http(base: str, path: str, method: str = "GET", data: bytes | None = None, headers: dict | None = None, timeout: int = 30):
    req = urllib.request.Request(base + path, data=data, method=method, headers=headers or {})
    t0 = time.monotonic()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(4000)
            return stamp, resp.status, time.monotonic() - t0, body
    except urllib.error.HTTPError as exc:
        return stamp, exc.code, time.monotonic() - t0, exc.read(4000)
    except Exception as exc:
        print(stamp, method, path, type(exc).__name__, f"{time.monotonic() - t0:.1f}s")
        return stamp, 0, time.monotonic() - t0, b""


def _base_url() -> str:
    base = _env_value("LIVE_API_BASE_URL").rstrip("/")
    if not base.startswith("https://"):
        raise SystemExit("LIVE_API_BASE_URL missing or not https")
    return base


def cmd_probe_down() -> None:
    base = _base_url()
    for method, path, data in (
        ("GET", "/health", None),
        ("POST", "/api/v1/chat?session_id=dr-suspend-probe&message=ping", b""),
    ):
        stamp, status, elapsed, _body = _http(base, path, method, data)
        print(stamp, method, path, status, f"{elapsed:.1f}s")


def cmd_probe_up() -> None:
    key = _env_value("LIVE_CLIENT_B_KEY")
    if not key or key == DEMO_KEY:
        raise SystemExit("refusing empty or demo client key")
    base = _base_url()
    status = 0
    for _ in range(8):
        stamp, status, elapsed, _body = _http(base, "/health")
        print(stamp, "GET", "/health", status, f"{elapsed:.1f}s")
        if status == 200:
            break
        time.sleep(8)
    if status != 200:
        raise SystemExit("health not 200; no chat")
    session = "dr-restore-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    path = f"/api/v1/chat?session_id={session}&message=Hi"
    stamp, status, elapsed, body = _http(
        base,
        path,
        "POST",
        b"",
        {"X-API-Key": key},
        timeout=90,
    )
    client_id = ""
    try:
        client_id = str(json.loads(body.decode("utf-8", "replace")).get("client_id", ""))
    except (json.JSONDecodeError, UnicodeError):
        client_id = ""
    print(stamp, "POST", "/api/v1/chat", status, f"{elapsed:.1f}s", f"client_id={client_id}")


def cmd_restore(url: str, dump: str, confirm: str) -> None:
    if confirm != "LIVE":
        raise SystemExit("restore refused: pass --confirm LIVE")
    path = Path(dump)
    if not path.is_file():
        raise SystemExit("dump file not found")
    if path.stat().st_size == 0 or not _has_clients_table(path):
        raise SystemExit("dump failed the clients-table check")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"restore_start={stamp} file={path.name} bytes={path.stat().st_size}")
    proc = _run(
        [_psql(), "--dbname", url, "-v", "ON_ERROR_STOP=1", "-f", str(path)],
        600,
    )
    print(f"restore_rc={proc.returncode}")
    tail = "\n".join(redact(proc.stderr).splitlines()[-8:])
    if tail.strip():
        print("restore_err_tail=" + tail[:800])
    if proc.returncode != 0:
        raise SystemExit("restore failed")
    print_counts(url)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Live DR helper. Reads LIVE_* only.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("counts")
    sub.add_parser("dump")
    sub.add_parser("probe-down")
    sub.add_parser("probe-up")
    restore = sub.add_parser("restore")
    restore.add_argument("--dump", required=True)
    restore.add_argument("--confirm", default="")
    args = parser.parse_args(argv)
    if args.cmd == "restore" and args.confirm != "LIVE":
        raise SystemExit("restore refused: pass --confirm LIVE")
    if args.cmd == "probe-down":
        cmd_probe_down()
        return
    if args.cmd == "probe-up":
        cmd_probe_up()
        return
    url = assert_live_url(_env_value("LIVE_DATABASE_URL"))
    if args.cmd == "counts":
        print_counts(url)
    elif args.cmd == "dump":
        print_counts(url)
        cmd_dump(url)
    elif args.cmd == "restore":
        cmd_restore(url, args.dump, args.confirm)


if __name__ == "__main__":
    try:
        main()
    except SystemExit as exc:
        if exc.code not in (0, None):
            print(redact(str(exc.code)) if not isinstance(exc.code, int) else "")
        raise
