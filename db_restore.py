import logging
import os
import subprocess
import sys
from urllib.parse import urlparse

from config import settings

logger = logging.getLogger("db_restore")
logging.basicConfig(level=logging.INFO)

# Local restore requires an explicit confirmation flag: --confirm LOCAL
REQUIRED_CONFIRM = "LOCAL"

_ALLOWED_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _is_local_db_url(db_url: str) -> bool:
    """Return True only for local postgres URLs (INF01 host guard)."""
    if not db_url or not db_url.startswith("postgres"):
        return False
    try:
        host = urlparse(db_url).hostname
    except Exception:
        return False
    return host in _ALLOWED_LOCAL_HOSTS


def _require_local_db_url(db_url: str) -> None:
    if not _is_local_db_url(db_url):
        # Redacted: never print the URL itself.
        logger.error("Refusing restore: DATABASE_URL is not a local postgres host. Aborting.")
        sys.exit(1)


def _parse_confirm(argv) -> str | None:
    """Extract the --confirm value. Usage: db_restore.py <file> --confirm LOCAL."""
    for i, arg in enumerate(argv):
        if arg == "--confirm" and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--confirm="):
            return arg.split("=", 1)[1]
    return None


def restore_postgres(backup_file: str, confirm: str | None = None):
    """
    Safely restores a PostgreSQL database from a pg_dump .sql artifact.
    WARNING: This will overwrite data in the target database.
    Requires confirm == "LOCAL" (i.e. --confirm LOCAL) before running psql.
    """
    if confirm != REQUIRED_CONFIRM:
        logger.error("Refusing restore: missing required flag --confirm LOCAL. Aborting.")
        sys.exit(1)

    db_url = settings.DATABASE_URL
    if not db_url or not db_url.startswith("postgres"):
        logger.error("DATABASE_URL is not configured for PostgreSQL. Aborting restore.")
        sys.exit(1)
    _require_local_db_url(db_url)

    if not os.path.exists(backup_file):
        logger.error(f"Backup file not found: {backup_file}")
        sys.exit(1)

    try:
        logger.warning(f"Starting PostgreSQL restore from: {backup_file}")
        logger.warning("Target Database: local postgres host")  # Hide credentials/host in log

        # We pass the db_url directly to psql since pg_dump output is usually raw SQL.
        # If it was custom format (-Fc), we would use pg_restore. Our backup uses raw SQL.
        # ON_ERROR_STOP=1 makes psql abort on the first SQL error (non-zero exit).
        process = subprocess.run(
            ["psql", db_url, "-v", "ON_ERROR_STOP=1", "-f", backup_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if process.returncode != 0:
            logger.error(f"Restore failed: {process.stderr}")
            sys.exit(1)
        else:
            logger.info(f"Restore completed successfully from {backup_file}")

    except SystemExit:
        raise
    except Exception as e:
        logger.error(f"Failed to execute psql for restore: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python db_restore.py <path_to_backup_file.sql> --confirm LOCAL")
        sys.exit(1)

    backup_file_path = sys.argv[1]
    confirm_value = _parse_confirm(sys.argv[2:])
    restore_postgres(backup_file_path, confirm=confirm_value)
