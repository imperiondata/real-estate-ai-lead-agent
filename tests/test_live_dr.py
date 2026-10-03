"""live_dr.py must not be able to follow DATABASE_URL onto a local database."""
import subprocess
import sys
from pathlib import Path

import pytest

import live_dr

REPO = Path(__file__).resolve().parent.parent
SRC = (REPO / "live_dr.py").read_text(encoding="utf-8")


def test_source_does_not_read_settings_database_url():
    assert "settings.DATABASE_URL" not in SRC
    assert "import db_backup" not in SRC
    assert "import db_restore" not in SRC


def test_refuses_local_host():
    with pytest.raises(SystemExit):
        live_dr.assert_live_url("postgresql://u:p@localhost:5432/db")
    with pytest.raises(SystemExit):
        live_dr.assert_live_url("postgresql://u:p@127.0.0.1:5432/db")
    with pytest.raises(SystemExit):
        live_dr.assert_live_url("")


def test_accepts_remote_host():
    url = "postgresql://u:p@dpg-example.oregon-postgres.render.com/db"
    assert live_dr.assert_live_url(url) == url


def test_redact_strips_url():
    raw = "failed postgres://user:secret@host/db password=secret"
    cleaned = live_dr.redact(raw)
    assert "secret" not in cleaned
    assert "postgres://" not in cleaned


def test_restore_without_confirm_exits():
    proc = subprocess.run(
        [sys.executable, str(REPO / "live_dr.py"), "restore", "--dump", "missing.sql"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode != 0
    blob = proc.stdout + proc.stderr
    assert "postgres://" not in blob
    assert "password=" not in blob.lower() or "password=[redacted]" in blob.lower()
