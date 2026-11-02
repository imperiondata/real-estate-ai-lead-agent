"""Create the throwaway CI schema and the tenant row the suite expects.

This is not a migration of Render or realestate_db. The workflow points
DATABASE_URL at the GitHub Postgres service before calling it.
"""

from __future__ import annotations

from sqlalchemy import text

import models
from database import engine
from tests.conftest import ensure_test_client


def main() -> None:
    models.Base.metadata.create_all(bind=engine)
    ensured = ensure_test_client(1)
    with engine.begin() as conn:
        conn.execute(
            text(
                "SELECT setval(pg_get_serial_sequence('clients', 'id'), "
                "(SELECT MAX(id) FROM clients))"
            )
        )
    print(f"CI_DB_BOOTSTRAP_OK client_id={ensured}")


if __name__ == "__main__":
    main()
