import os
import sys
import hashlib
import secrets
import subprocess
from pathlib import Path
from urllib.parse import urlparse, urlunparse

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest
import psycopg2
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
from models import Client
from auth import get_client_by_api_key, get_password_hash
from config import settings

ISOLATED_DB_NAME = "test_live_migration_isolated"


def get_base_db_url() -> str:
    raw = os.environ.get("DATABASE_URL") or getattr(settings, "DATABASE_URL", None) or "postgresql://realestate:localpass@localhost:5432/realestate_db"
    if raw.startswith("postgresql+psycopg2://"):
        raw = raw.replace("postgresql+psycopg2://", "postgresql://", 1)
    return raw


def get_admin_url(base_url: str) -> str:
    # Use base_url as the administrative connection to manage test databases
    return base_url


def get_isolated_url(base_url: str, db_name: str = ISOLATED_DB_NAME) -> str:
    parsed = urlparse(base_url)
    return urlunparse(parsed._replace(path=f"/{db_name}"))


def force_drop_database(admin_url: str, db_name: str):
    conn = None
    try:
        conn = psycopg2.connect(admin_url)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(f"""
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = '{db_name}' AND pid != pg_backend_pid();
        """)
        cur.execute(f"DROP DATABASE IF EXISTS {db_name};")
        cur.close()
    except Exception as exc:
        print(f"Notice: force_drop_database ({db_name}): {exc}")
    finally:
        if conn:
            conn.close()


def create_isolated_database(admin_url: str, db_name: str):
    force_drop_database(admin_url, db_name)
    conn = psycopg2.connect(admin_url)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"CREATE DATABASE {db_name};")
    cur.close()
    conn.close()


@pytest.fixture(scope="module")
def isolated_pg_database():
    """Provisions a completely isolated, clean PostgreSQL database instance for live migration testing."""
    base_url = get_base_db_url()
    admin_url = get_admin_url(base_url)
    create_isolated_database(admin_url, ISOLATED_DB_NAME)
    isolated_url = get_isolated_url(base_url, ISOLATED_DB_NAME)

    # Initialize base schema
    engine = create_engine(isolated_url)
    models.Base.metadata.create_all(bind=engine)
    engine.dispose()

    yield isolated_url

    # Teardown: terminate active connections and drop the isolated database
    force_drop_database(admin_url, ISOLATED_DB_NAME)


# Test keys and tenant identities
RAW_64_HEX_KEY = secrets.token_hex(32)  # Exactly 64 hex characters (token_hex standard)
RAW_ORDINARY_KEY = "legacy-plain-api-key-test-abc123xyz"
RAW_ALREADY_MIGRATED_KEY = "already-migrated-secret-key-456789"
HASHED_ALREADY_MIGRATED_KEY = hashlib.sha256(RAW_ALREADY_MIGRATED_KEY.encode("utf-8")).hexdigest()


def test_live_migration_execution_and_authentication(isolated_pg_database):
    """Test authentic execution of migrate_db.py via subprocess.run,

    verifying API-key hashing and subsequent authentication against isolated PostgreSQL.
    """
    engine = create_engine(isolated_pg_database)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()

    try:
        # 1. Seeding the three mandatory authentic test records:
        # a) 64-character legacy hexadecimal key (must NOT be skipped as 'already hashed')
        client_64hex = Client(
            company_name="64Hex Legacy Tenant",
            email="tenant_64hex@test.local",
            hashed_password=get_password_hash("password123"),
            api_key=RAW_64_HEX_KEY,
            is_api_key_hashed=False,
            is_active=True,
        )
        # b) Ordinary legacy key
        client_ordinary = Client(
            company_name="Ordinary Legacy Tenant",
            email="tenant_ordinary@test.local",
            hashed_password=get_password_hash("password123"),
            api_key=RAW_ORDINARY_KEY,
            is_api_key_hashed=False,
            is_active=True,
        )
        # c) An already-migrated record
        client_migrated = Client(
            company_name="Already Migrated Tenant",
            email="tenant_migrated@test.local",
            hashed_password=get_password_hash("password123"),
            api_key=HASHED_ALREADY_MIGRATED_KEY,
            is_api_key_hashed=True,
            is_active=True,
        )
        db.add_all([client_64hex, client_ordinary, client_migrated])
        db.commit()
    finally:
        db.close()
        engine.dispose()

    # 2. Execution: Run the actual migrate_db.py deployment script via subprocess.run
    sub_env = os.environ.copy()
    sub_env["DATABASE_URL"] = isolated_pg_database
    res = subprocess.run(
        [sys.executable, "migrate_db.py"],
        cwd=str(REPO_ROOT),
        env=sub_env,
        capture_output=True,
        text=True,
    )

    assert res.returncode == 0, f"migrate_db.py failed with return code {res.returncode}. Stderr: {res.stderr}\nStdout: {res.stdout}"
    assert "Migration complete." in res.stdout, f"Expected successful migration completion message. Stdout: {res.stdout}"

    # 3. Assertions: Inspect live database state
    engine = create_engine(isolated_pg_database)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()

    try:
        c_hex = db.query(Client).filter_by(email="tenant_64hex@test.local").one()
        c_ord = db.query(Client).filter_by(email="tenant_ordinary@test.local").one()
        c_mig = db.query(Client).filter_by(email="tenant_migrated@test.local").one()

        # Verify plaintext keys are strictly eliminated
        assert c_hex.is_api_key_hashed is True
        assert c_hex.api_key == hashlib.sha256(RAW_64_HEX_KEY.encode("utf-8")).hexdigest()
        assert c_hex.api_key != RAW_64_HEX_KEY, "Plaintext 64-hex key was not migrated!"

        assert c_ord.is_api_key_hashed is True
        assert c_ord.api_key == hashlib.sha256(RAW_ORDINARY_KEY.encode("utf-8")).hexdigest()
        assert c_ord.api_key != RAW_ORDINARY_KEY, "Plaintext ordinary key was not migrated!"

        # Verify already-migrated key was NOT re-hashed / double-hashed
        assert c_mig.is_api_key_hashed is True
        assert c_mig.api_key == HASHED_ALREADY_MIGRATED_KEY

        # 4. Assertions: Verify authentic live authentication using auth.get_client_by_api_key
        auth_c_hex = get_client_by_api_key(api_key_h=RAW_64_HEX_KEY, api_key_q=None, db=db)
        assert auth_c_hex.id == c_hex.id
        assert auth_c_hex.company_name == "64Hex Legacy Tenant"

        auth_c_ord = get_client_by_api_key(api_key_h=RAW_ORDINARY_KEY, api_key_q=None, db=db)
        assert auth_c_ord.id == c_ord.id
        assert auth_c_ord.company_name == "Ordinary Legacy Tenant"

        auth_c_mig = get_client_by_api_key(api_key_h=RAW_ALREADY_MIGRATED_KEY, api_key_q=None, db=db)
        assert auth_c_mig.id == c_mig.id
        assert auth_c_mig.company_name == "Already Migrated Tenant"

        # Negative authentication: invalid key must be rejected with 401
        with pytest.raises(HTTPException) as exc_info:
            get_client_by_api_key(api_key_h="completely-invalid-key-9999", api_key_q=None, db=db)
        assert exc_info.value.status_code == 401

        # Negative authentication: query parameter key must be rejected with 400
        with pytest.raises(HTTPException) as exc_info_q:
            get_client_by_api_key(api_key_h=None, api_key_q=RAW_ORDINARY_KEY, db=db)
        assert exc_info_q.value.status_code == 400

    finally:
        db.close()
        engine.dispose()


def test_live_migration_idempotency(isolated_pg_database):
    """Test safe repeat execution (idempotency): re-running migrate_db.py

    must not re-hash or alter existing records, and all tenants must continue to authenticate.
    """
    sub_env = os.environ.copy()
    sub_env["DATABASE_URL"] = isolated_pg_database

    # Execute second time
    res = subprocess.run(
        [sys.executable, "migrate_db.py"],
        cwd=str(REPO_ROOT),
        env=sub_env,
        capture_output=True,
        text=True,
    )

    assert res.returncode == 0, f"Repeat migrate_db.py run failed. Stderr: {res.stderr}"
    assert "Migration complete." in res.stdout

    # Verify hashes remained identical and were not double-hashed
    engine = create_engine(isolated_pg_database)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()

    try:
        c_hex = db.query(Client).filter_by(email="tenant_64hex@test.local").one()
        c_ord = db.query(Client).filter_by(email="tenant_ordinary@test.local").one()
        c_mig = db.query(Client).filter_by(email="tenant_migrated@test.local").one()

        assert c_hex.api_key == hashlib.sha256(RAW_64_HEX_KEY.encode("utf-8")).hexdigest()
        assert c_ord.api_key == hashlib.sha256(RAW_ORDINARY_KEY.encode("utf-8")).hexdigest()
        assert c_mig.api_key == HASHED_ALREADY_MIGRATED_KEY

        # Verify authentication still works after re-running
        assert get_client_by_api_key(api_key_h=RAW_64_HEX_KEY, api_key_q=None, db=db).id == c_hex.id
        assert get_client_by_api_key(api_key_h=RAW_ORDINARY_KEY, api_key_q=None, db=db).id == c_ord.id
        assert get_client_by_api_key(api_key_h=RAW_ALREADY_MIGRATED_KEY, api_key_q=None, db=db).id == c_mig.id
    finally:
        db.close()
        engine.dispose()


def test_live_migration_failure_injection_and_rollback(isolated_pg_database):
    """Test failure injection: proving that when a statement errors,

    migrate_db.py fails immediately, calls conn.rollback(), exits with code 1,
    and leaves no partial mutations committed to the database.
    """
    engine = create_engine(isolated_pg_database)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()

    raw_chaos_key = "unmigrated-plaintext-chaos-key-888"
    try:
        # Seed an unmigrated tenant right before failure injection
        client_chaos = Client(
            company_name="Failure Injection Tenant",
            email="tenant_chaos@test.local",
            hashed_password=get_password_hash("password123"),
            api_key=raw_chaos_key,
            is_api_key_hashed=False,
            is_active=True,
        )
        db.add(client_chaos)
        db.commit()
    finally:
        db.close()
        engine.dispose()

    # Execute migrate_db.py with injected failure statement
    chaos_env = os.environ.copy()
    chaos_env["DATABASE_URL"] = isolated_pg_database
    chaos_env["MIGRATE_INJECT_FAIL_SQL"] = "INSERT INTO non_existent_table_for_rollback_proof (id) VALUES (999);"

    res = subprocess.run(
        [sys.executable, "migrate_db.py"],
        cwd=str(REPO_ROOT),
        env=chaos_env,
        capture_output=True,
        text=True,
    )

    # Must exit with non-zero code 1
    assert res.returncode == 1, f"Expected migrate_db.py to fail with code 1 on injected error, got {res.returncode}. Output: {res.stdout}\n{res.stderr}"
    assert "Migration complete." not in res.stdout, "Failed migration must NEVER report 'Migration complete.'"
    assert "Migration failed due to database exception" in res.stderr or "Migration failed due to database exception" in res.stdout

    # Assert database state: verify strict transaction rollback
    engine = create_engine(isolated_pg_database)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()

    try:
        c_chaos = db.query(Client).filter_by(email="tenant_chaos@test.local").one()
        # Because transaction rolled back, the UPDATE clients statement was rolled back:
        assert c_chaos.is_api_key_hashed is False, "Transaction was not rolled back: is_api_key_hashed was committed as True!"
        assert c_chaos.api_key == raw_chaos_key, "Transaction was not rolled back: api_key was mutated!"

        # Plaintext key should still authenticate via backward-compatible auth because it wasn't committed as hashed
        auth_c_chaos = get_client_by_api_key(api_key_h=raw_chaos_key, api_key_q=None, db=db)
        assert auth_c_chaos.id == c_chaos.id
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    pytest.main(["-v", __file__])
