import logging
import os
import subprocess
import sys
from datetime import datetime
from urllib.parse import urlparse

from config import settings, use_tenant

logger = logging.getLogger("db_backup")
logging.basicConfig(level=logging.INFO)

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
        logger.error("Refusing backup: DATABASE_URL is not a local postgres host. Aborting.")
        sys.exit(1)


def backup_postgres():
    """
    Executes a pg_dump against the configured DATABASE_URL and securely
    stores the backup artifact in the backups/ directory.
    """
    with use_tenant("ops"):
        return _backup_postgres()


def _backup_postgres():
    db_url = settings.DATABASE_URL
    if not db_url or not db_url.startswith("postgres"):
        logger.error("DATABASE_URL is not configured for PostgreSQL. Aborting backup.")
        sys.exit(1)
    _require_local_db_url(db_url)

    # Ensure backups directory exists
    backup_dir = os.path.join(os.getcwd(), "backups")
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(backup_dir, f"backup_{timestamp}.sql")

    # Run pg_dump
    # Note: On Render or in Docker, the pg_dump binary must be available.
    try:
        logger.info(f"Starting PostgreSQL backup: {backup_file}")

        # We pass the db_url directly to pg_dump.
        # Using subprocess.run with check=True to raise an error if it fails.
        process = subprocess.run(
            ["pg_dump", db_url, "-f", backup_file, "--no-owner", "--no-privileges", "--clean"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if process.returncode != 0:
            logger.error(f"Backup failed: {process.stderr}")
            try:
                if os.path.exists(backup_file):
                    os.remove(backup_file)
            except Exception:
                pass
            sys.exit(1)

        # Verify the artifact: must exist, be non-empty, and contain
        # CREATE TABLE for clients (otherwise pg_dump wrote nothing useful).
        try:
            if not os.path.exists(backup_file) or os.path.getsize(backup_file) == 0:
                raise ValueError("Backup file missing or empty.")
            with open(backup_file, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
            if "CREATE TABLE" not in content or "clients" not in content:
                raise ValueError("Backup file missing CREATE TABLE for clients.")
        except Exception as e:
            logger.error(f"Backup verification failed: {e}")
            try:
                if os.path.exists(backup_file):
                    os.remove(backup_file)
            except Exception:
                pass
            sys.exit(1)

        logger.info(f"Backup completed successfully. Saved to {backup_file}")
        return backup_file

    except SystemExit:
        raise
    except Exception as e:
        logger.error(f"Failed to execute pg_dump: {e}")
        try:
            if os.path.exists(backup_file):
                os.remove(backup_file)
        except Exception:
            pass
        sys.exit(1)

if __name__ == "__main__":
    backup_postgres()
