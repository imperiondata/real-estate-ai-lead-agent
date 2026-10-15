# PaaS Engineering Requirements & Execution Plan

## Section 1: P0 & P1 Remediation Tracker

| ID | Severity | Issue / Affected Area | Confirmed Defect | Root Cause & Business Impact | Proposed Correction | Owner | Target Date | Status / Evidence |
|---|---|---|---|---|---|---|---|---|
| SEC01 | P0 | Tenant Isolation (RAG / Data Layer) | RAG implementation fails open when `client_id` or context is missing. | Unenforced isolation; high risk of cross-tenant data leakage if context drops. | Enforce hard database RLS. Implement negative-access automated tests verifying Client B is denied access to Client A's records. | Mayank | Oct 15 | `553ad8f` on `remediation/p0-sec02-inf01`. Fail-closed RAG and graph. No RLS, no `agency_id`. Pytest 458 passed. Not production-proven. |
| SEC02 | P0 | DLQ Replay & Tenant Attribution | DLQ replay executes external actions before resolving tenant, falling back to tenant ID `'1'`. | Severe security risk; unauthorized actions executed under wrong tenant. | Remove arbitrary fallback. Validate tenant ownership before action. Add idempotency and concurrency locks. | Aritro | Oct 15 | `f8f7bf3`. Local tests passed. Replay on Render waits until this branch is deployed. |
| SEC03 | P0 | Knowledge Base & Vector Isolation | Shared FAISS index and Neo4j graph lack strict retrieval enforcement. | Ingestion metadata is insufficient; missing filters during retrieval expose private chunks to foreign tenants. | Enforce compound `(agency_id, tenant_id)` filters on all vector/graph retrievals. Reject queries missing context. | Maitri | Oct 15 | `553ad8f`. Fail-closed RAG and graph. No RLS, no `agency_id`. Pytest 458 passed. Not production-proven. |
| SEC04 | P0 | Secrets & PII Exposure | API keys passed in query strings; plaintext storage; PII leaked in logs/event streams. | Credentials exposed in proxy logs; PII compliance violation (GDPR/HIPAA risk). | Migrate to authenticated headers. Implement one-way secret hashing. Redact PII from event streams. | Mayank | Oct 16 | `553ad8f`. Header only. New keys hashed. Dual-read. Phone dropped from bus payloads. Render plaintext backfill waits for the window. Frontend `EventSource` still 401. |
| INF01 | P0 | Disaster Recovery & Backups | Restore utility ignores errors. Lacks encrypted off-site retention. | Silent failure during restoration leading to unrecoverable data loss. | Implement `ON_ERROR_STOP` in Postgres restores. Execute/log an isolated restore drill with verified record counts. | Aritro | Oct 15 | `f8f7bf3`. Local restore exit 0. Live drill not run. Off-site encryption open. |
| REL01 | P1 | Event Publishing Reliability | Event helper catches publication errors silently and continues. | Silent loss of critical business events (CRM sync, follow-ups). | Implement a transactional outbox pattern for durable delivery, retries, and dead-letter handling. | Maitri | Oct 16 | `553ad8f`. Failed publish writes `event_bus` DLQ. Not an outbox. Replay does not republish. |
| REL02 | P1 | Background Scheduler Scaling | API process starts jobs; multiple replicas cause duplicate executions. | Clients receive duplicate messages/updates when service scales horizontally. | Move jobs to a dedicated worker or implement a distributed lock/lease mechanism (e.g., Redis locks). | Aritro | Oct 16 | `553ad8f`. Redis lease on 8 jobs. Dedicated worker later. |
| MIG01 | P1 | V1-to-V2 Database Migration | Script uses autocommit, catches SQL errors silently, reports false success. | Corrupt database state during cutover with no safe rollback. | Use versioned, transactional migrations. Define exact backfill and rollback procedures. | Mayank | Oct 16 | `553ad8f`. One transaction, exit 1, URL not printed. Local run exit 0. Not a version table. |
| TST01 | P1 | Regression Test Failures | 24 out of 115 test scenarios are currently failing on stale code. | Codebase health is unknown; prevents safe deployment. | Re-run full suite. Fix broken assertions. Map tests to business outcomes (qualification, routing). | Team | Oct 16 | `553ad8f`. Pytest 458 passed, 4 skipped. `task3_runner.py` not run. |

---

## Section 2: Architecture Implementation Plan (The 10 PaaS Pillars)

**Current Status Key:** `[E]` Exists in Code, `[P]` Partially Implemented, `[A]` Proposed in Architecture Only, `[M]` Missing.

### 1. Multi-Tenancy `[A]`

- **Requirement:** Enforce the Platform → Agency → Tenant → User hierarchy and RLS resource ownership.
- **Implementation Step:** Scaffold the Postgres v2 schema with compound `(agency_id, tenant_id)` indexing. Implement Row-Level Security (RLS) policies directly on the Postgres application role.

### 2. Industry Configuration `[A]`

- **Requirement:** Versioned Industry Profiles driving schemas, scoring, workflows, and prompts.
- **Implementation Step:** Implement `tenant_configurations` bindings. Build the dynamic JSON schema validator for `lead_attributes.data` to replace hardcoded vertical columns.

### 3. Core Platform vs Industry Modules `[A]`

- **Requirement:** Define shared capabilities vs. industry-specific configurable logic.
- **Implementation Step:** Strip all Real Estate logic (`property_type`, `visit_date`) from Layer 1 core code. Move all vertical variations into the JSON profile schemas injected at runtime.

### 4. Data Migration `[A]`

- **Requirement:** V1-to-V2 mapping, backfill strategy, rollback plan, and cutover criteria.
- **Implementation Step:** Write the expand-and-contract migration scripts using versioned, transactional SQL. Build the rollback utility mapping `v2.tenants` back to `public.clients`.

### 5. Security & Isolation `[P]`

- **Requirement:** Tenant-aware authorization, secret handling, encryption, and audit trails.
- **Implementation Step:** Implement envelope encryption (KMS) for integration secrets. Deploy the immutable `audit_logs` table for all cross-boundary actions.

### 6. AI and Retrieval `[P]`

- **Requirement:** Tenant-aware memory, vector/graph storage isolation, and safe retrieval.
- **Implementation Step:** Enforce hard `(agency_id, tenant_id)` filters on all FAISS and Neo4j queries. Configure the LLM execution environment to strictly reject prompt-injected tenant context.

### 7. Workflow Execution `[A]`

- **Requirement:** Separate core platform logic from the n8n implementation via a defined interface.
- **Implementation Step:** Implement the `IWorkflowRunner` interface and the Redis Event Stream bus to handle asynchronous automation triggers.

### 8. Operations `[M]`

- **Requirement:** Horizontal scaling, dedicated workers, monitoring, and backups.
- **Implementation Step:** Extract the scheduled tick jobs from the API process into a dedicated worker. Implement connection pooling limits.

### 9. Testing `[P]`

- **Requirement:** Unit, integration, negative-access security, and failure-injection testing.
- **Implementation Step:** Write automated tests where Client B authenticates and explicitly attempts to read Client A's data via APIs and background jobs.

### 10. Rollout `[A]`

- **Requirement:** Phased deployment protecting the V1 service while V2 is validated.
- **Implementation Step:** Deploy v2 schema alongside `public`. Route pilot agencies to V2 while live legacy traffic remains untouched on V1.

---

## Section 3: Priority & Working Sequence

To ensure safety and reliability, development will strictly adhere to the following sequence:

### Phase 1: Remediation (Immediate)

Address all P0 risks (Tenant Isolation, RAG Fail-Open, DLQ Replay, Disaster Recovery). No architectural expansion will occur until these vulnerabilities in the current codebase are secured.

### Phase 2: Reliability & Test Coverage

Resolve P1 functional failures via a complete regression rerun. Implement durable event delivery (Outbox pattern) and stabilize the background scheduler for horizontal scaling.

### Phase 3: Finalize V2 Architecture

Obtain formal approval for the V2 schema, strict tenancy model, migration logic, and security boundaries.

### Phase 4: Phased Core Implementation

Execute the PaaS architecture in small, reviewable milestones. Each milestone will require passing automated tests and documented evidence before progression.

---

## Section 4: Acceptance Criteria & Required Evidence

For every task in the Remediation Tracker and Implementation Plan, completion will strictly require:

1. **Code/PR Link:** The specific commit reference.
2. **Test Output:** Automated test logs (e.g., negative-access isolation reports).
3. **Operational Proof:** Logs and verification results from reproducible drills (e.g., Backup/Restore drill output).
4. **No item will be marked "fixed" without verifiable production evidence.**
