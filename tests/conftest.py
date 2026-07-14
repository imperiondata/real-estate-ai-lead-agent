"""Shared pytest fixtures for the IREIOS 3.0 expansion test suite (tests/test_e*.py).

Skeleton only — concrete fixtures are filled in as each expansion phase lands.
Kept separate from the bug-fix suite (tests/test_p*.py) via the `e` filename prefix.
"""

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
    """Placeholder DB session fixture; wire to database.SessionLocal when needed.

    Intentionally not importing the app DB module yet so this skeleton collects
    without the implementation existing.
    """
    yield None
