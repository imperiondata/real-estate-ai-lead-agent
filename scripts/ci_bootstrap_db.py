"""Create the throwaway CI schema and the tenant rows the suite expects.

This is not a migration of Render or realestate_db. The workflow points
DATABASE_URL at the GitHub Postgres service before calling it.

``ensure_test_client(1)`` inserts ``wave-test-key-1``. Tests that call the
API with the seed.py demo keys find that row by primary key and then 401.
Stamp those demo keys onto clients 1 and 2 after the row exists.
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import models  # noqa: E402
from auth import get_password_hash  # noqa: E402
from database import SessionLocal, engine  # noqa: E402
from tests.conftest import ensure_test_client  # noqa: E402

# Same plaintext keys as seed.py. Not hashed. Not a production secret.
DEMO_CLIENTS = (
    (1, "admin@revenueos.com", "Revenue OS HQ (Test Client A)", "secret-client-key-123"),
    (2, "client2@revenueos.com", "Apex Properties (Test Client B)", "secret-client-key-456"),
)


def stamp_demo_keys() -> None:
    with SessionLocal() as db:
        for client_id, email, company, api_key in DEMO_CLIENTS:
            row = db.query(models.Client).filter(models.Client.id == client_id).first()
            if row is None:
                row = models.Client(
                    id=client_id,
                    company_name=company,
                    email=email,
                    hashed_password=get_password_hash("password123"),
                    api_key=api_key,
                    is_api_key_hashed=False,
                    is_active=True,
                )
                db.add(row)
            else:
                row.api_key = api_key
                row.is_api_key_hashed = False
                row.is_active = True
            db.commit()


def main() -> None:
    models.Base.metadata.create_all(bind=engine)
    ensure_test_client(1)
    stamp_demo_keys()
    with engine.begin() as conn:
        conn.execute(
            text(
                "SELECT setval(pg_get_serial_sequence('clients', 'id'), "
                "(SELECT MAX(id) FROM clients))"
            )
        )
    print("CI_DB_BOOTSTRAP_OK client_ids=1,2 demo_keys=seed.py")


if __name__ == "__main__":
    main()
