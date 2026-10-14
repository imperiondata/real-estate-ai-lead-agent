import sys

import psycopg2

from config import settings

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
]


def run_migration(conn=None) -> int:
    own_conn = conn is None
    if own_conn:
        db_url = settings.DATABASE_URL
        if not db_url:
            print("DATABASE_URL is not configured.")
            return 1
        try:
            conn = psycopg2.connect(db_url)
        except Exception as exc:
            print("Migration failed.")
            print(type(exc).__name__)
            return 1
    conn.autocommit = False
    cursor = None
    try:
        cursor = conn.cursor()
        for query in MIGRATIONS:
            cursor.execute(query)
        conn.commit()
        print("Migration complete.")
        return 0
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        print("Migration failed.")
        print(type(exc).__name__)
        return 1
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if own_conn and conn is not None:
            try:
                conn.close()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(run_migration())
