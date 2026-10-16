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

This script is **fully idempotent** and relies on explicit migration state (`is_api_key_hashed`), safely handling all keys including 64-character hex strings:

```sql
-- ============================================================================
-- P0 REMEDIATION: API KEY SHA-256 HASH MIGRATION
-- Explicit Migration State (Zero Plaintext Backup Snapshots)
-- ============================================================================
BEGIN;

-- 1. Ensure schema column is_api_key_hashed exists
ALTER TABLE clients ADD COLUMN IF NOT EXISTS is_api_key_hashed BOOLEAN DEFAULT FALSE;

-- 2. Ensure pgcrypto extension is enabled for digest() calculation
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 3. Update non-hashed keys to SHA-256 hex string and mark as hashed
--    Only hashes keys where is_api_key_hashed IS FALSE (immune to 64-char hex collisions)
UPDATE clients
SET api_key = encode(digest(api_key::bytea, 'sha256'), 'hex'),
    is_api_key_hashed = TRUE
WHERE is_api_key_hashed IS FALSE;

-- 4. Verification Check: Assert no unhashed keys remain
DO $$
DECLARE
    unhashed_count INT;
BEGIN
    SELECT COUNT(*) INTO unhashed_count
    FROM clients
    WHERE is_api_key_hashed IS FALSE;

    IF unhashed_count > 0 THEN
        RAISE EXCEPTION 'MIGRATION FAILED: Found % rows with is_api_key_hashed = FALSE', unhashed_count;
    END IF;
    RAISE NOTICE 'SUCCESS: All % client keys verified as SHA-256 hex digests with is_api_key_hashed = TRUE.', (SELECT COUNT(*) FROM clients);
END $$;

COMMIT;
```

---

## 4. Key Rotation & Provisioning Runbook

When a client rotates their API key or when a new client is provisioned via `add_client.py`:

1. **Generation:** Generate 32 bytes of secure entropy:
   ```python
   import secrets, hashlib
   raw_key = secrets.token_hex(32)  # 64-char lowercase hex
   hashed_verifier = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
   ```
2. **Storage:** Insert `hashed_verifier` into `clients.api_key` and set `is_api_key_hashed = TRUE`.
3. **Display:** Display `raw_key` to the agency administrator **once**.
4. **Invalidation:** To revoke, set `clients.is_active = FALSE` or overwrite `clients.api_key` with a revoked hash placeholder.

---

## 5. Rollback & Disaster Recovery Plan

Storing plaintext keys in a rollback snapshot table violates the zero-plaintext security architecture and re-introduces credential exposure risks.

Instead, the system relies on **Forward-Compatible Auth and Dynamic Key Rotation**:

### 1. Forward-Compatible Dual-Read Auth
During rollout windows, the authentication layer verifies against `is_api_key_hashed`:
- If `is_api_key_hashed == True`, compares incoming key hash against stored hash.
- If `is_api_key_hashed == False` (legacy un-migrated row), compares incoming plaintext key directly.

### 2. Zero-Downtime Key Rotation Rollback
If an individual tenant or client encounters an authentication failure:
1. Generate a new high-entropy raw key via `secrets.token_hex(32)`.
2. Compute `hashlib.sha256(raw_key.encode("utf-8")).hexdigest()`.
3. Update `clients` record:
   ```sql
   UPDATE clients
   SET api_key = '<new_sha256_hash>',
       is_api_key_hashed = TRUE
   WHERE id = <client_id>;
   ```
4. Deliver `raw_key` out-of-band to tenant administrator.

### 3. Emergency Key Invalidation
If a key is compromised, immediately deactivate the client:
```sql
UPDATE clients SET is_active = FALSE WHERE id = <client_id>;
```
No plaintext snapshots are ever stored or restored.
