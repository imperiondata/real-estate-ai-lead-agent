import os
import sys
import logging
import psycopg2
from psycopg2 import Error as Psycopg2Error

try:
    from sqlalchemy.exc import SQLAlchemyError
except ImportError:
    class SQLAlchemyError(Exception):
        pass

from config import settings

logger = logging.getLogger("migration_runner")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

MIGRATIONS = [
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS confidence_score INTEGER DEFAULT 100;",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS requires_manual_review BOOLEAN DEFAULT FALSE;",
    
    "ALTER TABLE agents ADD COLUMN IF NOT EXISTS locations TEXT;",
    "ALTER TABLE agents ADD COLUMN IF NOT EXISTS speciality VARCHAR;",
    "ALTER TABLE agents ADD COLUMN IF NOT EXISTS deal_size VARCHAR;",
    "ALTER TABLE agents ADD COLUMN IF NOT EXISTS lead_type VARCHAR;",
    "ALTER TABLE agents ADD COLUMN IF NOT EXISTS conversion_rate INTEGER DEFAULT 30;",
    "ALTER TABLE agents ADD COLUMN IF NOT EXISTS response_speed_score INTEGER DEFAULT 50;",
    "ALTER TABLE agents ADD COLUMN IF NOT EXISTS active_leads INTEGER DEFAULT 0;",
    "ALTER TABLE agents ADD COLUMN IF NOT EXISTS is_director BOOLEAN DEFAULT FALSE;",
    
    "ALTER TABLE notification_logs ADD COLUMN IF NOT EXISTS twilio_message_sid VARCHAR;",
    "ALTER TABLE notification_logs ADD COLUMN IF NOT EXISTS twilio_delivery_status VARCHAR;",
    "ALTER TABLE notification_logs ADD COLUMN IF NOT EXISTS reason VARCHAR;",
    "ALTER TABLE notification_logs ADD COLUMN IF NOT EXISTS severity INTEGER DEFAULT 1;",
    "ALTER TABLE follow_up_states ADD COLUMN IF NOT EXISTS send_retry_count INTEGER DEFAULT 0;",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS crm_resync_pending BOOLEAN DEFAULT FALSE;",
    "CREATE TABLE IF NOT EXISTS agent_learning (id SERIAL PRIMARY KEY, client_id INTEGER REFERENCES clients(id) ON DELETE CASCADE, agent_name VARCHAR, wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0);",
    "CREATE INDEX IF NOT EXISTS ix_agent_learning_client_agent ON agent_learning (client_id, agent_name);",
    "CREATE TABLE IF NOT EXISTS approval_requests (id SERIAL PRIMARY KEY, client_id INTEGER REFERENCES clients(id) ON DELETE CASCADE, entity_id VARCHAR, action_type VARCHAR, action_payload JSONB, status VARCHAR DEFAULT 'pending', requested_by VARCHAR, resolved_by VARCHAR, reason VARCHAR, correlation_id VARCHAR UNIQUE, created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), resolved_at TIMESTAMP WITH TIME ZONE);",
    "CREATE INDEX IF NOT EXISTS ix_approval_requests_client_status ON approval_requests (client_id, status);",
    "CREATE TABLE IF NOT EXISTS lead_memories (id SERIAL PRIMARY KEY, client_id INTEGER REFERENCES clients(id) ON DELETE CASCADE, lead_id INTEGER REFERENCES leads(id) ON DELETE CASCADE, session_id VARCHAR, key VARCHAR, value TEXT, memory_type VARCHAR DEFAULT 'fact', created_at TIMESTAMP WITH TIME ZONE DEFAULT now());",
    "CREATE INDEX IF NOT EXISTS ix_lead_memories_lead ON lead_memories (lead_id);",
    "CREATE INDEX IF NOT EXISTS ix_lead_memories_client ON lead_memories (client_id);",
    "CREATE TABLE IF NOT EXISTS inventory_units (id SERIAL PRIMARY KEY, client_id INTEGER REFERENCES clients(id) ON DELETE CASCADE, project_name VARCHAR NOT NULL, tower VARCHAR, unit_code VARCHAR NOT NULL, bhk VARCHAR, location VARCHAR, list_price INTEGER, status VARCHAR DEFAULT 'available', carpet_sqft INTEGER, meta_json JSONB, created_at TIMESTAMP WITH TIME ZONE DEFAULT now());",
    "CREATE INDEX IF NOT EXISTS ix_inventory_units_client ON inventory_units (client_id);",
    "CREATE TABLE IF NOT EXISTS pricing_rules (id SERIAL PRIMARY KEY, client_id INTEGER REFERENCES clients(id) ON DELETE CASCADE, location VARCHAR, bhk VARCHAR, min_budget INTEGER, max_budget INTEGER, list_price INTEGER, notes TEXT, created_at TIMESTAMP WITH TIME ZONE DEFAULT now());",
    "CREATE INDEX IF NOT EXISTS ix_pricing_rules_client ON pricing_rules (client_id);",
    "CREATE TABLE IF NOT EXISTS agent_tasks (id SERIAL PRIMARY KEY, client_id INTEGER REFERENCES clients(id) ON DELETE CASCADE, lead_id INTEGER REFERENCES leads(id) ON DELETE SET NULL, title VARCHAR NOT NULL, description TEXT, status VARCHAR DEFAULT 'open', assignee VARCHAR, source VARCHAR, meta_json JSONB, created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), updated_at TIMESTAMP WITH TIME ZONE DEFAULT now());",
    "CREATE INDEX IF NOT EXISTS ix_agent_tasks_client ON agent_tasks (client_id);",
    "CREATE INDEX IF NOT EXISTS ix_agent_tasks_lead ON agent_tasks (lead_id);",
    "CREATE INDEX IF NOT EXISTS ix_agent_tasks_status ON agent_tasks (client_id, status);",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS is_negotiating BOOLEAN DEFAULT FALSE;",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS is_api_key_hashed BOOLEAN DEFAULT FALSE;",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS twilio_phone_number VARCHAR;",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS twilio_auth_token VARCHAR;",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS twilio_account_sid VARCHAR;",
    "CREATE INDEX IF NOT EXISTS ix_clients_twilio_phone ON clients (twilio_phone_number);",
    "CREATE INDEX IF NOT EXISTS ix_clients_twilio_account_sid ON clients (twilio_account_sid);",
    "CREATE EXTENSION IF NOT EXISTS pgcrypto;",
    "UPDATE clients SET api_key = encode(digest(api_key::bytea, 'sha256'), 'hex'), is_api_key_hashed = TRUE WHERE is_api_key_hashed IS FALSE;",
]


def run_migration(db_url: str = None) -> None:
    target_db_url = db_url or os.environ.get("DATABASE_URL") or getattr(settings, "DATABASE_URL", None)
    if not target_db_url:
        logger.error("FATAL: DATABASE_URL is not set.")
        sys.exit(1)

    # Normalize SQLAlchemy connection string prefix for psycopg2 if needed
    if target_db_url.startswith("postgresql+psycopg2://"):
        target_db_url = target_db_url.replace("postgresql+psycopg2://", "postgresql://", 1)

    masked_url = target_db_url.split("@")[-1] if "@" in target_db_url else target_db_url
    logger.info("Connecting to DB: %s", masked_url)

    conn = None
    cursor = None
    try:
        conn = psycopg2.connect(target_db_url)
        conn.autocommit = False
        cursor = conn.cursor()

        # Explicitly begin strict database transaction
        #cursor.execute("BEGIN;")

        statements = list(MIGRATIONS)

        # Support failure injection for chaos/integration testing
        inject_fail = os.environ.get("MIGRATE_INJECT_FAIL_SQL")
        if not inject_fail and "--inject-fail-sql" in sys.argv:
            idx = sys.argv.index("--inject-fail-sql")
            if idx + 1 < len(sys.argv):
                inject_fail = sys.argv[idx + 1]

        if inject_fail:
            logger.warning("FAILURE INJECTION: Appending failure SQL statement: %s", inject_fail)
            statements.append(inject_fail)

        for query in statements:
            logger.info("Running: %s", query.strip()[:80] + ("..." if len(query.strip()) > 80 else ""))
            cursor.execute(query)

        # Commit strictly after all statements succeed
        conn.commit()
        logger.info("Migration transaction committed successfully.")
    except (Psycopg2Error, SQLAlchemyError) as exc:
        logger.error("Migration failed due to database exception: %s", exc)
        if conn:
            try:
                conn.rollback()
                logger.info("Transaction rolled back successfully.")
            except Exception as rb_exc:
                logger.error("Failed to rollback transaction: %s", rb_exc)
        sys.exit(1)
    except Exception as exc:
        logger.error("Migration failed due to unexpected error: %s", exc)
        if conn:
            try:
                conn.rollback()
                logger.info("Transaction rolled back successfully.")
            except Exception as rb_exc:
                logger.error("Failed to rollback transaction: %s", rb_exc)
        sys.exit(1)
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    print("Migration complete.")


if __name__ == "__main__":
    run_migration()

