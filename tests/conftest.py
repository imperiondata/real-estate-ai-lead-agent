"""Shared pytest fixtures for the IREIOS 3.0 expansion test suite (tests/test_e*.py).

Kept separate from the bug-fix suite (tests/test_p*.py) via the `e` filename prefix.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session")
def redis_url():
    """Redis connection string for the Event Bus (Phase 1)."""
    return os.getenv("REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture(scope="session")
def event_bus_stream():
    """Default Redis Stream name used by the bus client (Phase 1.2)."""
    return os.getenv("EVENT_BUS_STREAM", "ireios:events")


@pytest.fixture(scope="session")
def db_session():
    """Placeholder DB session fixture; wire to database.SessionLocal when needed."""
    yield None


def ensure_test_client(client_id: int = 1) -> int:
    """Idempotently ensure a ``clients`` row exists for FK-dependent tests.

    Many expansion tests hardcode ``client_id=1``. After a fresh Postgres volume
    (or soft wipe that keeps schema but drops clients), inserts into sessions/
    leads/approval_requests fail with ForeignKeyViolation. Call this before
    those inserts.

    Returns the ensured client id (may differ from requested if that id is free
    but we reuse an existing row — prefers matching primary key when possible).
    """
    from auth import get_password_hash
    from database import SessionLocal
    from models import Client

    email = f"wave-test-client-{client_id}@revenueos.local"
    with SessionLocal() as db:
        # Prefer exact PK match (tests use client_id=1).
        row = db.query(Client).filter(Client.id == client_id).first()
        if row is not None:
            if not row.is_active:
                row.is_active = True
                db.commit()
            return row.id

        # Fallback: any active client (cron tests only need >=1).
        any_active = db.query(Client).filter(Client.is_active.is_(True)).first()
        if any_active is not None and client_id != 1:
            return any_active.id

        # Create with preferred id when table empty / id free.
        row = Client(
            id=client_id,
            company_name=f"Wave Test Client {client_id}",
            email=email,
            hashed_password=get_password_hash("password123"),
            api_key=f"wave-test-key-{client_id}",
            is_active=True,
        )
        db.add(row)
        try:
            db.commit()
            return client_id
        except Exception:
            db.rollback()
            # Race or sequence conflict — take whatever exists now.
            row = db.query(Client).filter(Client.id == client_id).first()
            if row is not None:
                return row.id
            any_c = db.query(Client).first()
            if any_c is None:
                raise
            return any_c.id
