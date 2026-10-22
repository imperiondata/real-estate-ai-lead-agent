"""P0 INF01 — local backup/restore guards. No live DB, no Render."""
from pathlib import Path

import pytest

import db_backup
import db_restore

REPO = Path(__file__).resolve().parent.parent
RESTORE_SRC = (REPO / "db_restore.py").read_text(encoding="utf-8")
BACKUP_SRC = (REPO / "db_backup.py").read_text(encoding="utf-8")

RENDER_URL = "postgresql://u:p@dpg-example.oregon-postgres.render.com:5432/db"
LOCAL_URL = "postgresql://realestate:localpass@127.0.0.1:5432/realestate_db"


def test_host_check_rejects_render_accepts_local():
    assert db_backup._is_local_db_url(RENDER_URL) is False
    assert db_restore._is_local_db_url(RENDER_URL) is False
    assert db_backup._is_local_db_url(LOCAL_URL) is True
    assert db_restore._is_local_db_url(LOCAL_URL) is True
    assert db_backup._is_local_db_url("postgresql://u:p@localhost:5432/db") is True


def test_restore_source_has_on_error_stop_and_confirm():
    assert "ON_ERROR_STOP=1" in RESTORE_SRC
    assert "--confirm LOCAL" in RESTORE_SRC


def test_backup_source_has_create_table_check():
    assert "CREATE TABLE" in BACKUP_SRC
    assert "clients" in BACKUP_SRC


def test_local_scripts_do_not_import_live_dr():
    assert "live_dr" not in BACKUP_SRC
    assert "live_dr" not in RESTORE_SRC


def test_restore_without_confirm_exits():
    with pytest.raises(SystemExit):
        db_restore.restore_postgres("some_file.sql", confirm=None)
    with pytest.raises(SystemExit):
        db_restore.restore_postgres("some_file.sql", confirm="WRONG")
