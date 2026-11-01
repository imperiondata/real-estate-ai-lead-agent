# V2 Migration Dry-Run Plan

**Date:** 30 October 2026, executed 1 November 2026
**Owner:** Aritro
**Audience:** Mayank, for the 2 November staging demo package
**Status:** Rules tested in memory, and executed once against throwaway local Postgres on 1 November 2026. No live DDL. No Render connection.

Piyush rejected the selected-field checksum (`v1_lead_id|name|phone|budget`) on 29 October 2026. That rule is withdrawn. Parity is full-table reconciliation. The rules live in `app/migration/dry_run.py`, which imports no database driver. The 1 November execution is `app/migration/isolated_drill.py` and `scripts/run_v2_isolated_drill.py`.

The execution used a throwaway database `v2_nov1_drill` on `127.0.0.1`. It did not open `realestate_db`, did not read `LIVE_DATABASE_URL`, and did not create schema `v2` in any shared database. Its raw output is `plans/evidence/NOV1_ISOLATED_DRILL.log`, reproduced in section 6.

This drill does not execute row-level security, agency boundaries, or foreign-key enforcement. Those are not claimed here.

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

The local INF-01 drill is not this rollback. The 1 November isolated run executed the reconciliation and the failure-injection half against throwaway local Postgres (section 6). It did not execute `rollback()` against Postgres. That step remains in-memory only.

---

## 5. Evidence

| Check | Command | Expected |
|---|---|---|
| Dry-run rules | `pytest tests/test_v2_migration_dry_run.py -q` | passed |
| Profile lock, separate owner | `pytest tests/test_v2_industry_profile_guard.py -q` | passed |
| Doc consistency | `pytest tests/test_v2_docs_consistency.py -q` | passed |
| Isolated drill (1 November) | `python scripts/run_v2_isolated_drill.py` | `NOV1_DRILL_PASS` |
| Isolation policy shape (1 November) | `pytest tests/test_v2_agency_isolation.py -q` | `ISOLATION_DRILL_PASS` |
| Isolation CI workflow | GitHub Actions `v2-isolation` at `bf456fe` | Passed: https://github.com/imperiondata/real-estate-ai-lead-agent/actions/runs/41316092168 |

No live database changes were made for this plan.

---

## 6. Executed isolated run, 1 November 2026

Command: `python scripts/run_v2_isolated_drill.py`. The script creates `v2_nov1_drill` on `127.0.0.1`, runs the drill, writes the log, and drops the database. Raw output is `plans/evidence/NOV1_ISOLATED_DRILL.log`.

```text
NOV1_DRILL_START
engine=postgres host=127.0.0.1 database=v2_nov1_drill
live_database_used=false
render_used=false
app_database_touched=false
RLS_STATUS v1_render=not_shipped isolated_execution=not_this_run production_claim=false
RECONCILE tenant=1 ok=true v1_count=2 v2_count=2 missing=[] extra=[] mismatches=[]
REJECTED_CHECKSUM_WOULD_MATCH tenant=1 true
RECONCILE tenant=2 ok=false v1_count=1 v2_count=1 missing=[] extra=[] mismatches=[{'pk': 3, 'column': 'funnel_stage', 'v1': 'New', 'v2': 'Lost'}]
REJECTED_CHECKSUM_WOULD_MATCH tenant=2 true
CRASH phase=before_v1 failure_id=1 visible_to_new_connection=true seen_phase=before_v1 seen_status=open v1_count=0 v2_count=0
RETRY phase=before_v1 status=resolved v1_count=1 v2_count=1 duplicate=false
CRASH phase=after_v1_before_v2 failure_id=2 visible_to_new_connection=true seen_phase=after_v1_before_v2 seen_status=open v1_count=1 v2_count=0
RETRY phase=after_v1_before_v2 status=resolved v1_count=1 v2_count=1 duplicate=false
CRASH phase=after_both failure_id=3 visible_to_new_connection=true seen_phase=after_both seen_status=open v1_count=1 v2_count=1
RETRY phase=after_both status=resolved v1_count=1 v2_count=1 duplicate=false
NOV1_DRILL_PASS
```

What each block shows:

| Line | Meaning |
|---|---|
| `RECONCILE tenant=1 ok=true` | Every digested Lead column matches for tenant 1. |
| `RECONCILE tenant=2 ok=false` | Tenant 2 differs on `funnel_stage` only, at `v1_lead_id` 3 (`New` against `Lost`). The read cut for tenant 2 is blocked. |
| `REJECTED_CHECKSUM_WOULD_MATCH tenant=2 true` | The checksum rejected on 29 October would have passed this tenant. Full-column reconciliation is what catches it. |
| `CRASH ... visible_to_new_connection=true` | The failure row was committed before the simulated crash and is visible on a second connection in all three phases. |
| `CRASH ... before_v1 ... v1_count=0 v2_count=0` | Crash before any write. Nothing but the failure record survived. |
| `CRASH ... after_v1_before_v2 ... v1_count=1 v2_count=0` | Crash between the V1 and V2 writes. The V1 row survived and the V2 row is missing. |
| `CRASH ... after_both ... v1_count=1 v2_count=1` | Crash after both writes but before resolve. Both rows survived and the failure stayed `open`. |
| `RETRY ... status=resolved ... v1_count=1 v2_count=1 duplicate=false` | Retry filled only what was missing, then a second retry wrote nothing. One V1 row and one V2 row in every phase. |

Not executed by this run: row-level security, agency scope, composite foreign keys, and the `rollback()` procedure. `RLS_STATUS` in the header records that V1 and Render have no RLS and that this drill did not execute it. No production claim is made.

A separate run, `python scripts/run_v2_isolation_drill.py`, executed the V2 policy shape on `v2_isolation_drill` and wrote `plans/evidence/ISOLATION_DRILL.log`. That run is not part of the reconciliation log above, and it does not change what this log proves.

