# V2 Migration Dry-Run Plan

**Date:** 30 October 2026
**Owner:** Aritro
**Audience:** Mayank, for the Oct 30 evidence package
**Status:** Documented procedure. Tested in memory. No live DDL. No Render connection.

Piyush rejected the selected-field checksum (`v1_lead_id|name|phone|budget`) on 29 October 2026. That rule is withdrawn. Parity is full-table reconciliation. The tested procedure is `app/migration/dry_run.py`, proved by `tests/test_v2_migration_dry_run.py`. The module imports no database driver.

This is not the Nov 1 isolated Postgres drill. It does not create schema `v2`, does not set `V2_DUAL_WRITE`, and does not read `LIVE_DATABASE_URL`.

---

## 1. Isolation gate

A later runner that wants a database must call `assert_isolated_dsn` before it connects, and must still refuse any host that is not local. The function refuses:

- an empty DSN
- a DSN equal to `LIVE_DATABASE_URL`
- any host ending in `render.com` or starting with `dpg-`

Passing the gate is not permission to run this package against Render. Live database changes remain banned.

---

## 2. What is reconciled

Every V1 table in `V2_Migration_and_Security.md` section 1, plus `clients` and `webhook_logs`.

| Table | Tenant key | Parity |
|---|---|---|
| `clients` | `id` | Digested business columns. `hashed_password`, `api_key`, and `twilio_auth_token` are compared as SHA-256 only. The report never prints them. `created_at` and `settings` are reported, not digested. |
| `sessions` | `client_id` | `follow_up_count`, `status`. Timestamps reported only. |
| `messages` | `client_id` | `session_id`, `role`, `content`. Content is digested and redacted from the sample. Orphan if `session_id` is missing. |
| `leads` | `client_id` | Every mapped column below. Orphan if `session_id` is missing. |
| `event_logs` | `client_id` | `session_id`, `event_type`, `action_type`, `latency_ms`, `agent_type`. |
| `follow_up_states` | `client_id` | Stage, status, inactivity score, send retry count. Timestamps reported only. |
| `dlq_events` | `client_id`, nullable | `target_endpoint`, `status`. A null `client_id` is reported. It is not assigned to tenant 1. Payload is not printed. |
| `agents` | `client_id` | Directory and routing columns. |
| `approval_requests` | `client_id` | Status and reason. `action_payload` is not printed. |
| `agent_learning` | `client_id` | `agent_name`, `wins`, `losses`. |
| `notification_logs` | `client_id` | Status, reason, severity, Twilio sid. Orphan if `lead_id` is missing. |
| `lead_memories` | `client_id` | Key, type, and value. Value is digested and redacted from the sample. |
| `inventory_units` | `client_id` | Unit columns. `meta_json` reported only. |
| `pricing_rules` | `client_id` | Location, bhk, budgets, list price, notes. |
| `agent_tasks` | `client_id` | Title, status, assignee. A null `lead_id` is allowed. |
| `webhook_logs` | none | Global `message_sid` set equality. No tenant is invented. |

For each tenant and each tenant-scoped table, `reconcile_all` records:

- V1 count and shadow count
- primary keys missing on the shadow
- primary keys extra on the shadow
- SHA-256 over every digested column, sorted by primary key, null encoded as an empty segment
- the first column mismatches, with secrets and free-text values omitted from the sample

A mismatch on any digested column blocks that tenant's read cut. Matching name, phone, and budget is not sufficient. `rejected_selected_field_checksum` still exists so the test can show the old checksum would pass while `reconcile_all` fails. The read-cut gate does not call it.

### 2.1 Lead column map

| Column | Disposition |
|---|---|
| `id` | Identity. Sort key `v1_lead_id`. The v2 UUID is not digested. |
| `client_id` | Identity map through `v2.tenant_legacy_ids`. Not digested as a raw integer. |
| `session_id`, `name`, `phone`, `score`, `source`, `whatsapp_opt_in`, score outputs, `funnel_stage`, CRM columns, `is_negotiating` | Relational shadow columns. Digested. |
| `budget`, `location`, `property_type`, `intent`, `visit_date` | `industry_dynamic_data`. Digested after the section 5.1 normalization. |
| `updated_at` | Reported, not digested. |

A missing `visit_date` is a partial lead. It is valid. It is not a parity failure. An unparsable date, a wrong type, or an unknown industry key is invalid.

---

## 3. Partial dual-write

V1 is authoritative during the soak. A shadow failure never rolls back the V1 commit and never blocks it.

One attempt is one aggregate: the parent row plus the child rows that belong to that write. Partial means at least one of those tables was written and at least one was not.

Detection writes a `v2.dual_write_failures` record with:

- tenant
- tables written
- tables missing
- error
- `kind`: `transient` or `schema_invalid`
- `retry_count`

Rules:

| Failure | Shadow write | Retry |
|---|---|---|
| Transient database error, including a partial child write | Keep the tables that committed. Do not delete them. | Idempotent upsert of the missing tables only, on the V1 primary key. Does not insert a second parent. |
| Schema-invalid industry JSON | Write nothing for that aggregate. No partial JSON insert. | Do not retry. Record a parity failure. Block that tenant's read cut. |
| Missing `visit_date` or any other empty optional key | Normal upsert. | Not a failure. |
| Five failed transient attempts | Leave V1 untouched. | Stop. Block that tenant's read cut. |

Transient delays are 1, 2, 4, 8, then 16 minutes. The cap is 5. This is the shadow upsert policy, not the follow-up send backoff.

`V2_DUAL_WRITE` still defaults off. It writes schema-qualified `v2` tables in the same database. It does not open a second DSN and it does not point `DATABASE_URL` at Render.

---

## 4. Tested rollback

`rollback()` was executed by `tests/test_v2_migration_dry_run.py` against an in-memory fixture. No socket was opened.

| Step | Result the test asserts |
|---|---|
| Copy a V1 fixture into the shadow while dual-write is on | Shadow has the row. V1 bytes are unchanged. |
| Inject a partial write of `leads` without `messages` | Failure record is `partial`. V1 is unchanged. |
| Retry the missing table | One parent row, not two. The missing child appears. V1 is unchanged. |
| Inject schema-invalid JSON | Shadow stays empty for that aggregate. Retry is `reject`. |
| Roll back | `dual_write` is false, `read_source` is `v1`, the shadow namespace is empty, the V1 fixture is byte-identical. |

The same function covers the two moments in this package:

| Moment | Action | Data loss |
|---|---|---|
| Before the read cut | `rollback()`: dual-write off, drop the shadow namespace | None. V1 was never rewritten. |
| After the read cut, dual-write still on | `rollback()`: reads flip back to V1, then drop the shadow namespace | None. V1 is still receiving writes. |
| After V1 writes have stopped | Not this package. Restore from the pre-stop `live_dr.py` dump using `LIVE_DATABASE_URL` only | Only if that dump is missing. |

The local INF-01 drill is not this rollback. A throwaway local Postgres execution of the same procedure is the Nov 1 isolated run. It is not claimed today.

---

## 5. Evidence

| Check | Command | Expected |
|---|---|---|
| Dry-run rules | `pytest tests/test_v2_migration_dry_run.py -q` | passed |
| Profile lock, separate owner | `pytest tests/test_v2_industry_profile_guard.py -q` | passed |
| Doc consistency | `pytest tests/test_v2_docs_consistency.py -q` | passed |

No live database changes were made for this plan.
