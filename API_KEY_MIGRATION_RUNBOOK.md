# API Key SHA-256 Migration & One-Way Verifier Runbook

**Document Version:** 1.0.0  
**Security Classification:** Confidential / P0 Release Gate  
**Target Environments:** Staging (`paas_drill_db`), Production (`LIVE_DATABASE_URL`)  
**Scope:** Migration of plaintext `clients.api_key` to irreversible one-way SHA-256 digest verifiers.

---

## 1. Executive Summary & Architecture

Prior to this remediation, `clients.api_key` values were stored in reversible/plaintext formats, presenting credential exposure risks in database backups, dumps, or unauthorized query access.

Under the new security contract:
- API keys are generated as secure, high-entropy tokens and provided to the client **once** upon generation.
- The backend computes `hashlib.sha256(api_key.encode("utf-8")).hexdigest()`.
- The database stores **only** the 64-character hexadecimal digest.
- On authentication, incoming keys from `X-API-Key` or query parameters are hashed immediately in memory and compared against `clients.api_key`.

---

## 2. Zero-Downtime Migration Sequence

The migration is structured into four distinct phases to ensure continuous availability with zero dropped requests:

```
[Phase 1: Dual-Read Compatibility Code Deploy]
                   ↓
[Phase 2: Database Migration on Safe Copy & Validation]
                   ↓
[Phase 3: Production Database SQL Migration Execution]
                   ↓
[Phase 4: Strict Hash Verification Enforcement]
```

### Phase 1: Dual-Read Compatibility (Already Deployed)
The authentication dependency (`auth.py:get_client_by_api_key` and `app/api/events.py:get_events_client`) supports both hashed and un-migrated keys:
```python
incoming_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
client = db.query(Client).filter(
    (Client.api_key == incoming_hash) | (Client.api_key == api_key)
).first()
```
*Effect:* Any client authenticating with an existing key succeeds whether their database row contains the plaintext key or the migrated SHA-256 hash.

### Phase 2: Safe Copy Execution & Verification (INF-01 Drill)
Before running against production, execute the migration against `paas_drill_db` (restored from `production_backup.dump`):
1. Run pre-migration verification queries.
2. Execute migration script inside a transaction.
3. Assert that all keys are exactly 64-character hex strings.
4. Run integration tests to prove active clients authenticate successfully.

### Phase 3: Production Database SQL Execution
Execute the idempotent SQL script during a standard maintenance window.

### Phase 4: Strict Verification Cutover
Remove the plaintext fallback `| (Client.api_key == api_key)` from `auth.py`, ensuring only cryptographically hashed verifiers are accepted.

---

## 3. Production SQL Migration Script

This script is **fully idempotent** and will skip keys that are already SHA-256 hashed (64 hex characters):

```sql
-- ============================================================================
-- P0 REMEDIATION: API KEY SHA-256 HASH MIGRATION
-- ============================================================================
BEGIN;

-- 1. Create audit backup table for immediate rollback safety
CREATE TABLE IF NOT EXISTS _clients_api_key_backup_p0 AS
SELECT id, api_key, updated_at, NOW() AS migrated_at
FROM clients;

-- 2. Ensure pgcrypto extension is enabled for digest() calculation
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 3. Update non-hashed keys to SHA-256 hex string
UPDATE clients
SET api_key = encode(digest(api_key::bytea, 'sha256'), 'hex')
WHERE length(api_key) != 64 
   OR api_key !~ '^[0-9a-f]{64}$';

-- 4. Verification Check: Assert no plaintext keys remain
DO $$
DECLARE
    unhashed_count INT;
BEGIN
    SELECT COUNT(*) INTO unhashed_count
    FROM clients
    WHERE length(api_key) != 64 
       OR api_key !~ '^[0-9a-f]{64}$';

    IF unhashed_count > 0 THEN
        RAISE EXCEPTION 'MIGRATION FAILED: Found % rows with unhashed api_key values', unhashed_count;
    END IF;
    RAISE NOTICE 'SUCCESS: All % client keys verified as SHA-256 hex digests.', (SELECT COUNT(*) FROM clients);
END $$;

COMMIT;
```

---

## 4. Key Rotation & Provisioning Runbook

When a client rotates their API key or when a new client is provisioned via `add_client.py`:

1. **Generation:** Generate 32 bytes of secure entropy:
   ```python
   import secrets, hashlib
   raw_key = secrets.token_urlsafe(32)  # e.g. 'c3VwZXJzZWNyZXRrZXkxMjM0NTY3ODkwMTI'
   hashed_verifier = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
   ```
2. **Storage:** Insert `hashed_verifier` into `clients.api_key`.
3. **Display:** Display `raw_key` to the agency administrator **once**.
4. **Invalidation:** To revoke, set `clients.is_active = FALSE` or overwrite `clients.api_key` with a revoked hash placeholder.

---

## 5. Rollback Plan

If any authentication anomaly occurs post-migration:

### Fast Rollback (SQL)
Restore the plaintext keys from the atomic snapshot table:
```sql
BEGIN;

UPDATE clients c
SET api_key = b.api_key
FROM _clients_api_key_backup_p0 b
WHERE c.id = b.id;

COMMIT;
```

### Safety Valve
Because Phase 1 dual-read code accepts both `api_key == incoming_hash` and `api_key == plaintext`, rolling back the database rows requires **zero backend downtime** and **no code redeployment**.
