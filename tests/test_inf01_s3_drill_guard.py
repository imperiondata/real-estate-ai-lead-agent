"""INF-01 drill guards. No AWS, no live dump, no credentials printed."""
from pathlib import Path

import scripts.prove_inf01_s3_drill as drill


def test_redact_strips_url_key_email_and_phone():
    raw = (
        "failed postgres://realestate:localpass@localhost:5432/realestate_db "
        "AKIAIOSFODNN7EXAMPLE password=hunter2 "
        "lead@buyer.com +919876543210"
    )
    cleaned = drill.redact(raw)
    assert "postgres://" not in cleaned
    assert "localpass" not in cleaned
    assert "AKIA" not in cleaned
    assert "hunter2" not in cleaned
    assert "lead@buyer.com" not in cleaned
    assert "9876543210" not in cleaned
    assert "[redacted-url]" in cleaned
    assert "[redacted-key]" in cleaned
    assert "[redacted-email]" in cleaned


def test_source_must_be_local():
    try:
        drill.assert_local_source("postgresql://u:p@dpg-render.internal:5432/app")
    except SystemExit as exc:
        assert "not local" in str(exc)
    else:
        raise AssertionError("remote source was accepted")


def test_restore_cannot_be_the_source_database():
    source = "postgresql://realestate:localpass@127.0.0.1:5432/realestate_db"
    target = drill.isolated_restore_url(source)
    assert drill._db_name(target) == "inf01_drill"
    assert drill._host(target) == "127.0.0.1"
    try:
        drill.isolated_restore_url(source, source)
    except SystemExit as exc:
        assert "source database" in str(exc)
    else:
        raise AssertionError("source database was accepted as the restore target")


def test_restore_refuses_remote_override():
    source = "postgresql://realestate:localpass@localhost:5432/realestate_db"
    try:
        drill.isolated_restore_url(source, "postgresql://u:p@example.com:5432/inf01_drill")
    except SystemExit as exc:
        assert "not local" in str(exc)
    else:
        raise AssertionError("remote restore target was accepted")


def test_script_does_not_read_live_database_url():
    src = Path(drill.__file__).read_text(encoding="utf-8")
    assert "LIVE_DATABASE_URL" not in src
    assert "put_bucket_lifecycle_configuration" not in src
