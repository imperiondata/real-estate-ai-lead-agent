"""IREIOS 3.0 — Phase 7.2: Neo4j session helper + schema migrate.

`Neo4jClient` is a thin, fail-safe wrapper over the Neo4j Python driver:

- Lazy driver import (module imports even when `neo4j` is not installed).
- `available` is `False` when `NEO4J_URI` is empty (repo default) or the
  server is unreachable — every query becomes a safe no-op returning `[]`.
- `migrate_schema()` applies constraints/indexes idempotently and stamps a
  `(:SchemaVersion {version:1})` marker so it can run repeatedly.

Postgres remains the transactional source of truth; Neo4j is the relationship
/ traversal layer only.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from config import settings

logger = logging.getLogger("neo4j_client")

SCHEMA_VERSION = 1

# Idempotent DDL (Neo4j 5 syntax). Each statement is IF NOT EXISTS.
SCHEMA_STATEMENTS = [
    "CREATE CONSTRAINT lead_key IF NOT EXISTS "
    "FOR (l:Lead) REQUIRE (l.lead_id, l.client_id) IS UNIQUE",
    "CREATE CONSTRAINT agent_key IF NOT EXISTS "
    "FOR (a:Agent) REQUIRE (a.name, a.client_id) IS UNIQUE",
    "CREATE INDEX lead_client IF NOT EXISTS FOR (l:Lead) ON (l.client_id)",
    "CREATE INDEX lead_location IF NOT EXISTS FOR (l:Lead) ON (l.location)",
    "CREATE INDEX property_key IF NOT EXISTS FOR (p:Property) ON (p.name)",
]


class Neo4jClient:
    """Fail-safe Neo4j driver wrapper with schema migration."""

    def __init__(self) -> None:
        self._driver = None
        self.available = bool(getattr(settings, "NEO4J_URI", ""))
        if self.available:
            try:
                self._connect()
            except Exception as e:  # pragma: no cover - requires live Neo4j
                logger.warning("Neo4j configured but unreachable; disabled: %s", e)
                self.available = False

    def _connect(self):  # pragma: no cover - requires live Neo4j + driver
        from neo4j import GraphDatabase

        self._driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
        # Fail fast if the server is not actually reachable.
        self._driver.verify_connectivity()

    def run(self, cypher: str, **params) -> list:
        """Run a Cypher query, returning a list of dicts. No-op when down."""
        if not self.available or self._driver is None:
            return []
        try:
            with self._driver.session() as session:
                return [dict(r) for r in session.run(cypher, **params)]
        except Exception as e:  # pragma: no cover - depends on live Neo4j
            logger.warning("Neo4j query failed (degraded): %s", e)
            return []

    def health(self) -> dict:
        """Return connectivity + schema version (never raises)."""
        if not self.available or self._driver is None:
            return {"available": False, "schema_version": None}
        rows = self.run(
            "MATCH (s:SchemaVersion) RETURN s.version AS version "
            "ORDER BY s.version DESC LIMIT 1"
        )
        version = rows[0]["version"] if rows else None
        return {"available": True, "schema_version": version}

    def migrate_schema(self) -> dict:
        """Apply constraints/indexes + version marker. Idempotent."""
        if not self.available or self._driver is None:
            logger.info("Neo4j not available; schema migrate skipped")
            return {"migrated": False, "reason": "unavailable"}
        try:  # pragma: no cover - requires live Neo4j
            with self._driver.session() as session:
                for stmt in SCHEMA_STATEMENTS:
                    session.run(stmt)
                session.run(
                    "MERGE (s:SchemaVersion {version:$v}) "
                    "SET s.applied_at = datetime()",
                    v=SCHEMA_VERSION,
                )
            logger.info("Neo4j schema v%s applied", SCHEMA_VERSION)
            return {"migrated": True, "schema_version": SCHEMA_VERSION}
        except Exception as e:  # pragma: no cover
            logger.warning("Neo4j schema migrate failed: %s", e)
            return {"migrated": False, "reason": str(e)}

    def close(self) -> None:  # pragma: no cover
        if self._driver is not None:
            self._driver.close()
            self._driver = None


neo4j_client = Neo4jClient()
