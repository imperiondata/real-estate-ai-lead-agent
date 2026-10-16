# P0 Remediation Evidence Package
**Branch:** remediation/p0-security-fixes
**Status:** Ready for Merge Review
**Scope Definition:** This package exclusively covers P0 (Phase 1) remediation. P1 items (Outbox, Scheduler, V2 RLS, V1-to-V2 Migration) remain in the "Proposed/In Progress" state and are strictly isolated to Phase 2.

### 1. PR Links, Commits, and Code Diffs
* **553ad8f** (Backend): Patches RAG fail-open (SEC-01) and DLQ tenant attribution/concurrency locks (SEC-02). Enforces (agency_id, tenant_id) isolation at the data layer.
* **7e81b1d** (Frontend): Secures EventSource by replacing URL query params with HttpOnly JWT cookies.
* **1c2a7ab** (Frontend): Secures fetch in sales-copilot via HttpOnly JWT cookies.

### 2. Complete 458/458 Test Output
The complete pytest standard output is attached as pytest_evidence.log. The suite was executed against the exact HEAD of the remediation branch (1c2a7ab), confirming 458 passes and 0 failures.

### 3. Automated Negative-Access Test Results
As detailed in pytest_evidence.log, tests assert that RAG retrieval throws an immediate 403/closed-failure when tenant_id context is stripped. Cross-tenant API tests assert HTTP 403/404 when attempting to query foreign records.

### 4. Database Restore-Drill Evidence
Isolated DR drill performed Oct 15.
> pg_restore -d paas_drill_db --exit-on-error --clean --no-owner production_backup.dump
> The command exited with code 0.
Querying \dt confirmed all 16 legacy V1 tables cleanly restored.

### 5. API-Key Hashing & Integration Secret Protection
Frontend commits completely remove api_key= from URLs. Existing keys hashed via pgcrypto (sha256).
> CREATE EXTENSION IF NOT EXISTS pgcrypto; UPDATE clients SET api_key = encode(digest(api_key, 'sha256'), 'hex') WHERE api_key NOT SIMILAR TO '[0-9a-f]{64}';
> UPDATE 2

**Post-Hashing Integrity Verification:**
id | company_name | api_key | key_len
---|---|---|---
3 | Client B Holdings | c9c3644e2bb97bf51e8ee44905802939d2142c719935a38cd4dae7cd6340aa09 | 64 (Preserved)
1 | Revenue OS HQ (Test Client A) | da1126170b30bab106add678f73b6412998aff1ed17cd668720883fd0809838c | 64 (Hashed)
2 | Apex Properties (Test Client B) | ba9845f59a25849b483e918d5a59acb11b2990293810e4b08154ee440ef60571 | 64 (Hashed)

Live database execution will occur seamlessly during the approved maintenance window.
