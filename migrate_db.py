import psycopg2
from config import settings

def run_migration():
    print("Connecting to DB:", settings.DATABASE_URL)
    conn = psycopg2.connect(settings.DATABASE_URL)
    conn.autocommit = True
    cursor = conn.cursor()

    migrations = [
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
        "CREATE INDEX IF NOT EXISTS ix_agent_learning_client_agent ON agent_learning (client_id, agent_name);"
    ]

    for query in migrations:
        try:
            print("Running:", query)
            cursor.execute(query)
            print("Success")
        except Exception as e:
            print("Failed:", e)

    cursor.close()
    conn.close()
    print("Migration complete.")

if __name__ == "__main__":
    run_migration()
