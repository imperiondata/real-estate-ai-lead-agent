"""INF-01 drill: local dump -> S3 upload -> S3 download -> isolated local restore.

Does not touch Render. Does not print credentials, database URLs, or row data.
Requires, when run for real:

  S3_BACKUP_BUCKET
  AWS_ACCESS_KEY_ID
  AWS_SECRET_ACCESS_KEY
  AWS_REGION                  (default us-east-1 if unset)
  DATABASE_URL                local postgres only

Optional:

  INF01_RESTORE_URL           local postgres URL of a different database.
                              Default: same host, database name inf01_drill.
  KMS_KEY_ARN                 if set, upload uses aws:kms. The ARN is not printed.

  python scripts/prove_inf01_s3_drill.py --check
  python scripts/prove_inf01_s3_drill.py
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_ISOLATED_DB = "inf01_drill"
_COUNT_SQL = """
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
ORDER BY 1;
"""

REPO = Path(__file__).resolve().parent.parent


def redact(text: str) -> str:
    """Strip credentials and contact data from tool output. Never print the raw string."""
    cleaned = text or ""
    cleaned = re.sub(r"postgres(?:ql)?(?:\+\w+)?://\S+", "[redacted-url]", cleaned, flags=re.I)
    cleaned = re.sub(
        r"(?i)(password|secret|token|aws_secret_access_key)\s*[=:]\s*\S+",
        r"\1=[redacted]",
        cleaned,
    )
    cleaned = re.sub(r"\bAKIA[0-9A-Z]{16}\b", "[redacted-key]", cleaned)
    cleaned = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[redacted-email]", cleaned)
    cleaned = re.sub(r"(?<!\d)(?:\+?\d[\d\-\s]{8,}\d)", "[redacted-phone]", cleaned)
    return cleaned


def _env_value(name: str) -> str:
    raw = os.getenv(name, "")
    if raw:
        return raw.strip().strip('"').strip("'")
    env_path = REPO / ".env"
    if not env_path.exists():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == name:
            return value.strip().strip('"').strip("'")
    return ""


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _db_name(url: str) -> str:
    path = (urlparse(url).path or "").lstrip("/")
    return path.split("/", 1)[0]


def assert_local_source(url: str) -> str:
    if not url or not url.startswith("postgres"):
        raise SystemExit("source database is not configured for postgres")
    if _host(url) not in _LOCAL_HOSTS:
        raise SystemExit("refusing source database: host is not local")
    if not _db_name(url):
        raise SystemExit("source database name is missing")
    return url


def isolated_restore_url(source_url: str, override: str = "") -> str:
    source_url = assert_local_source(source_url)
    if override:
        target = override
        if _host(target) not in _LOCAL_HOSTS:
            raise SystemExit("refusing restore database: host is not local")
    else:
        parts = urlparse(source_url)
        target = urlunparse(parts._replace(path=f"/{_ISOLATED_DB}"))
    if _db_name(target) == _db_name(source_url):
        raise SystemExit("refusing restore: target database is the source database")
    if not override and _db_name(target) != _ISOLATED_DB:
        raise SystemExit("refusing restore: isolated database name is not inf01_drill")
    return target


def _tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise SystemExit(f"{name} is not on PATH")
    return path


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.pop("PGPASSWORD", None)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _print_tool(prefix: str, proc: subprocess.CompletedProcess) -> None:
    err = redact(proc.stderr).strip()
    if err:
        print(f"{prefix}{err[:800]}")


def _admin_url(source_url: str) -> str:
    parts = urlparse(source_url)
    return urlunparse(parts._replace(path="/postgres"))


def _counts(url: str) -> dict[str, int]:
    proc = _run(
        [_tool("psql"), "--dbname", url, "-v", "ON_ERROR_STOP=1", "-A", "-t", "-c", _COUNT_SQL],
        120,
    )
    _print_tool("counts_err=", proc)
    if proc.returncode != 0:
        raise SystemExit("table list failed")
    names = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    counts: dict[str, int] = {}
    for name in names:
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", name):
            raise SystemExit("refusing unexpected table name")
        counted = _run(
            [
                _tool("psql"),
                "--dbname",
                url,
                "-v",
                "ON_ERROR_STOP=1",
                "-A",
                "-t",
                "-c",
                f"SELECT COUNT(*) FROM public.{name}",
            ],
            120,
        )
        _print_tool("count_err=", counted)
        if counted.returncode != 0:
            raise SystemExit("count query failed")
        counts[name] = int(counted.stdout.strip() or "0")
    return counts


def _print_counts(label: str, counts: dict[str, int]) -> None:
    print(f"{label}_tables={len(counts)}")
    for name in sorted(counts):
        print(f"{label} {name}={counts[name]}")


def _ensure_isolated(admin_url: str, restore_url: str) -> None:
    name = _db_name(restore_url)
    if name != _ISOLATED_DB:
        raise SystemExit("refusing to create a database that is not inf01_drill")
    exists = _run(
        [
            _tool("psql"),
            "--dbname",
            admin_url,
            "-v",
            "ON_ERROR_STOP=1",
            "-A",
            "-t",
            "-c",
            "SELECT 1 FROM pg_database WHERE datname = 'inf01_drill'",
        ],
        60,
    )
    _print_tool("db_exists_err=", exists)
    if exists.returncode != 0:
        raise SystemExit("could not check isolated database")
    if exists.stdout.strip() == "1":
        drop = _run(
            [
                _tool("psql"),
                "--dbname",
                admin_url,
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
                "DROP DATABASE inf01_drill WITH (FORCE)",
            ],
            60,
        )
        _print_tool("drop_err=", drop)
        if drop.returncode != 0:
            raise SystemExit("could not reset isolated database")
    created = _run(
        [
            _tool("psql"),
            "--dbname",
            admin_url,
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            "CREATE DATABASE inf01_drill",
        ],
        60,
    )
    _print_tool("create_err=", created)
    if created.returncode != 0:
        raise SystemExit("could not create isolated database")


def _s3_client(region: str):
    import boto3

    return boto3.client("s3", region_name=region)


def check_ready() -> int:
    source = assert_local_source(_env_value("DATABASE_URL"))
    restore = isolated_restore_url(source, _env_value("INF01_RESTORE_URL"))
    _tool("pg_dump")
    _tool("psql")
    bucket_set = bool(_env_value("S3_BACKUP_BUCKET"))
    key_set = bool(_env_value("AWS_ACCESS_KEY_ID")) and bool(_env_value("AWS_SECRET_ACCESS_KEY"))
    print("INF01_S3_CHECK")
    print("source_host=local")
    print(f"source_db={_db_name(source)}")
    print(f"restore_db={_db_name(restore)}")
    print(f"bucket_set={'yes' if bucket_set else 'no'}")
    print(f"aws_key_set={'yes' if key_set else 'no'}")
    print(f"region_set={'yes' if _env_value('AWS_REGION') else 'no'}")
    print(f"kms_set={'yes' if _env_value('KMS_KEY_ARN') else 'no'}")
    if bucket_set and key_set:
        print("INF01_S3_READY")
    else:
        print("INF01_S3_WAITING_FOR_KEYS")
    return 0


def drill() -> int:
    started = time.monotonic()
    started_at = _utc()
    source = assert_local_source(_env_value("DATABASE_URL"))
    restore = isolated_restore_url(source, _env_value("INF01_RESTORE_URL"))
    bucket = _env_value("S3_BACKUP_BUCKET")
    if not bucket:
        print("INF01_S3_DRILL_BLOCKED bucket_not_configured")
        return 1
    if not _env_value("AWS_ACCESS_KEY_ID") or not _env_value("AWS_SECRET_ACCESS_KEY"):
        print("INF01_S3_DRILL_BLOCKED aws_not_configured")
        return 1
    region = _env_value("AWS_REGION") or "us-east-1"
    kms = _env_value("KMS_KEY_ARN")
    stamp = _stamp()
    backup_id = f"inf01-drill/{stamp}/local_backup_{stamp}.sql"
    sha_id = f"{backup_id}.sha256"

    print("INF01_S3_DRILL_START")
    print(f"started_at={started_at}")
    print(f"backup_id={backup_id}")
    print(f"source_db={_db_name(source)}")
    print(f"restore_db={_db_name(restore)}")
    print(f"sse={'aws:kms' if kms else 'AES256'}")

    with tempfile.TemporaryDirectory(prefix="inf01-") as tmp:
        dump_path = Path(tmp) / "local_backup.sql"
        downloaded = Path(tmp) / "downloaded.sql"

        dump_started = _utc()
        dump = _run(
            [
                _tool("pg_dump"),
                "--dbname",
                source,
                "--no-owner",
                "--no-privileges",
                "--clean",
                "--if-exists",
                "-f",
                str(dump_path),
            ],
            600,
        )
        _print_tool("dump_err=", dump)
        if dump.returncode != 0 or not dump_path.is_file() or dump_path.stat().st_size == 0:
            print("INF01_S3_DRILL_FAIL dump_failed")
            return 1
        digest = _sha256(dump_path)
        print(f"dump_started_at={dump_started}")
        print(f"dump_finished_at={_utc()}")
        print(f"dump_bytes={dump_path.stat().st_size}")
        print(f"dump_sha256={digest}")

        upload_started = _utc()
        client = _s3_client(region)
        put_args = {
            "Bucket": bucket,
            "Key": backup_id,
            "Body": dump_path.read_bytes(),
        }
        if kms:
            put_args["ServerSideEncryption"] = "aws:kms"
            put_args["SSEKMSKeyId"] = kms
        else:
            put_args["ServerSideEncryption"] = "AES256"
        put = client.put_object(**put_args)
        client.put_object(
            Bucket=bucket,
            Key=sha_id,
            Body=f"{digest}  local_backup_{stamp}.sql\n".encode("utf-8"),
            ServerSideEncryption="AES256",
        )
        head = client.head_object(Bucket=bucket, Key=backup_id)
        print(f"upload_started_at={upload_started}")
        print(f"upload_finished_at={_utc()}")
        print(f"s3_etag_present={'yes' if put.get('ETag') else 'no'}")
        print(f"s3_sse={head.get('ServerSideEncryption', 'missing')}")
        print(f"s3_bytes={head.get('ContentLength')}")

        download_started = _utc()
        obj = client.get_object(Bucket=bucket, Key=backup_id)
        downloaded.write_bytes(obj["Body"].read())
        sidecar = client.get_object(Bucket=bucket, Key=sha_id)["Body"].read().decode("utf-8")
        downloaded_digest = _sha256(downloaded)
        sidecar_digest = sidecar.split()[0] if sidecar.split() else ""
        print(f"download_started_at={download_started}")
        print(f"download_finished_at={_utc()}")
        print(f"downloaded_bytes={downloaded.stat().st_size}")
        print(f"downloaded_sha256={downloaded_digest}")
        print(f"sidecar_match={'yes' if sidecar_digest == digest else 'no'}")
        if downloaded_digest != digest or sidecar_digest != digest:
            print("INF01_S3_DRILL_FAIL checksum_mismatch")
            return 1

        before = _counts(source)
        _print_counts("source", before)
        _ensure_isolated(_admin_url(source), restore)

        restore_started = _utc()
        restored = _run(
            [_tool("psql"), "--dbname", restore, "-v", "ON_ERROR_STOP=1", "-f", str(downloaded)],
            600,
        )
        _print_tool("restore_err=", restored)
        print(f"restore_started_at={restore_started}")
        print(f"restore_finished_at={_utc()}")
        print(f"restore_rc={restored.returncode}")
        if restored.returncode != 0:
            print("INF01_S3_DRILL_FAIL restore_failed")
            print("isolated_db_kept=inf01_drill")
            return 1

        after = _counts(restore)
        _print_counts("restored", after)
        mismatched = sorted(
            name for name in set(before) | set(after) if before.get(name) != after.get(name)
        )
        print(f"counts_match={'yes' if not mismatched else 'no'}")
        if mismatched:
            print(f"mismatched_tables={','.join(mismatched)}")
            print("INF01_S3_DRILL_FAIL counts_mismatch")
            print("isolated_db_kept=inf01_drill")
            return 1

    elapsed = time.monotonic() - started
    print(f"finished_at={_utc()}")
    print(f"recovery_seconds={elapsed:.3f}")
    print("local_artifacts_deleted=yes")
    print("INF01_S3_DRILL_PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="INF-01 local-to-S3-to-isolated restore drill")
    parser.add_argument("--check", action="store_true", help="Validate local guards. Do not dump or upload.")
    args = parser.parse_args()
    try:
        if args.check:
            return check_ready()
        return drill()
    except SystemExit as exc:
        message = str(exc)
        if message:
            print(redact(message))
        code = exc.code
        return code if isinstance(code, int) else 1
    except Exception as exc:
        print(f"INF01_S3_DRILL_FAIL {type(exc).__name__}")
        print(redact(str(exc))[:800])
        return 1


if __name__ == "__main__":
    sys.exit(main())
