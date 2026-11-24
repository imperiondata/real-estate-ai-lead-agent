"""Canonical V2 tenant session variable.

The only GUC name is ``app.current_tenant_id``. A missing value is not
replaced with tenant 1, and an invalid value is not rewritten. The caller
passes the value through. Postgres then fails the policy cast closed.

This helper is for the isolated V2 drill and later V2 transactions. The V1
``SessionLocal`` path does not call it. V1 still filters by ``client_id``.
"""

from __future__ import annotations

TENANT_GUC = "app.current_tenant_id"


def set_current_tenant_id(cursor, tenant_id: str) -> None:
    """Set ``app.current_tenant_id`` for the current transaction only."""
    if tenant_id is None or str(tenant_id).strip() == "":
        raise ValueError("app.current_tenant_id is missing; not defaulted")
    cursor.execute(
        "SELECT set_config(%s, %s, true)",
        (TENANT_GUC, str(tenant_id)),
    )
