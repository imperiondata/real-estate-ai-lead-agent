# V2 Migration and Security Boundaries

**Phase 1 deliverable: V1-to-V2 migration plan, backward compatibility, rollback, and security boundaries.**

Owner: Aritro. This document aligns to Mayank's tenancy note and to Maitri's Industry Profile. It does not redraw the ER diagram. It does not design the qualification schema.

No live schema change is proposed for execution. Piyush banned live database changes until he reviews this package. The SQL below is a proposal. It is not a migration to run.

Mayank accepted all four decisions on 25 October 2026. He is updating the ER diagram and the tenancy note to match this plan. Live schema changes stay banned until Piyush reviews the package.

---

## 1. Current V1

V1 is one Postgres database. The tenant is the `clients` row. Operational tables use an integer `client_id` foreign key. Primary keys on `clients` and `leads` are integers. Session ids are strings, often `{client_id}_{phone}`.

Tables that carry `client_id` today:

| Table | Notes |
|---|---|
| `sessions` | String primary key. `client_id` indexed |
| `messages` | Separate rows. Not a JSON history blob |
| `leads` | Integer primary key. Industry fields are columns |
| `event_logs` | |
| `follow_up_states` | |
| `dlq_events` | `client_id` is nullable |
| `agents` | Human directory, not the platform User |
| `approval_requests` | |
| `agent_learning` | |
| `notification_logs` | |
| `lead_memories` | |
| `inventory_units` | |
| `pricing_rules` | |
| `agent_tasks` | `lead_id` uses `ON DELETE SET NULL` |

`webhook_logs` has no `client_id`. That is a V1 gap. V2 gives it `tenant_id`. It is not fixed by a live alter in this package.

Almost every `client_id` foreign key is `ON DELETE CASCADE`. SQLAlchemy relationships also cascade deletes. This cut keeps that behavior on `v2` so dual-write does not break the app. The flip to `ON DELETE RESTRICT` is a later contract step. See section 8.

There is no Agency, no User separate from Client, no membership table, and no RLS. Auth is an API key, a dashboard JWT, or an admin key. Background jobs open `SessionLocal()` with no tenant session variable.

External contracts that embed the integer id:

- Redis lock `session_lock:{client_id}_{from}`
- Bus payload `tenant_id` of the form `Client_<int>`
- Session id prefix `{client_id}_`
- Twilio ingress resolved by tenant API key or Twilio number, not by a user login

---

## 2. Target, and what this cut will not do

Mayank's model is Platform, Agency, Tenant, User. Operational rows carry `tenant_id` UUID. Industry-specific lead fields live in `industry_dynamic_data` JSONB, validated against the Industry Profile. RLS uses `app.current_tenant_id`. This cut uses `ON DELETE CASCADE` on `v2` tenant foreign keys. `ON DELETE RESTRICT` waits for the contract step.

This cut does not:

- alter V1 tables in place
- change integer primary keys to UUID in place
- drop `client_id`
- stop writes to V1
- collapse `messages` into `conversation.message_history`
- rebuild Neo4j
- seed nine industries
- run any of the SQL in this document against Render or local production data

In-place integer-to-UUID primary keys are not a zero-downtime path. Child foreign keys, session ids, Redis keys, and `Client_<int>` bus values would all break in the same window.

---

## 3. Shadow schema

Leave V1 as the source of truth. Add a shadow schema `v2` in the same Postgres instance. Do not drop or rewrite V1.

Order:

1. Create `v2` tables. V1 is untouched, so this step is reversible by dropping the schema.
2. Backfill once from V1.
3. Turn on dual-write behind `V2_DUAL_WRITE`. New V1 writes also upsert the shadow row. Reads stay on V1.
4. Compare per-tenant row counts and a checksum of name, phone, and budget. Do not cut reads on a mismatch.
5. Flip reads to `v2` only after that check passes. Keep dual-write on through the soak.
6. Stopping V1 writes is a later contract step. It is not in Tuesday's package. It requires a fresh `live_dr.py` dump taken immediately before the stop, and Piyush's approval of that later change.

`V2_DUAL_WRITE` defaults off. Turning it on is an application flag, not a schema change, and it still waits for approval of this package. The flag writes the shadow schema only. It never points `DATABASE_URL` at Render and never copies `LIVE_DATABASE_URL` over `DATABASE_URL`.

### Rollback

| Moment | Action | Data loss |
|---|---|---|
| Before the read cut | Turn `V2_DUAL_WRITE` off. Drop schema `v2` if required | None. V1 was never rewritten |
| After the read cut, dual-write still on | Flip reads back to V1 | None. V1 is still receiving writes |
| After V1 writes have stopped | Not this package. Restore from the pre-stop `live_dr.py` dump | Only if the dump is missing |

The local INF-01 drill is not the rollback for a Render cut. Live rollback uses `live_dr.py` and `LIVE_DATABASE_URL` only.

---

## 4. Identity map

Create one Agency for the existing operator. Every current `clients` row becomes one Tenant under that Agency. Do not invent a many-tenants-per-agency split during this migration. Stripe fields on `clients` (`stripe_customer_id`, `subscription_status`) move to that Agency row, one-to-one with today's paying client, until a later billing design says otherwise.

Keep a compatibility table:

```text
v2.tenant_legacy_ids
  v1_client_id   integer  primary key
  tenant_id      uuid     not null unique
```

Session ids, Redis locks, and `Client_<int>` bus values keep working through this map. New bus values may use `Tenant_<uuid>`. The parser accepts both until the contract step. A payload that matches neither is rejected. It is not assigned to tenant 1.

Each current client email becomes a User with one `tenant_membership` owner role. The human `agents` directory stays tenant-scoped operational data. It is not the platform User table. Those people may later gain memberships. This cut does not merge the two.

---

## 5. Field split

**Accepted.** Name and phone stay standard relational columns on `leads`. Claim-check and CRM sync read them as columns. They do not move into `industry_dynamic_data`. They are nullable for this cut. Empty V1 values are stored as null, not as `""` and not as a placeholder. `NOT NULL` waits for the contract step, after unqualified leads have been backfilled.

Global lead columns in `v2`:

- `id` UUID
- `tenant_id` UUID, not null
- `v1_lead_id` integer, unique, nullable only during backfill
- `status`
- `name`
- `phone`
- `created_at`

Industry JSON, validated against Maitri's `real_estate` version `1` schema before write:

| V1 column | `industry_dynamic_data` key | Required to book |
|---|---|---|
| `location` | `location` | yes |
| `budget` | `budget` | yes |
| `property_type` | `property_type` | yes |
| `intent` | `intent` | no |
| `visit_date` | `visit_date` | yes |

Backfill omits empty strings. A row that fails the schema is counted and skipped, not inserted as valid. Name and phone are copied to columns, not into the JSON object.

Score outputs stay engine columns: `conversion_probability`, `lead_temperature`, `engagement_score`, `urgency_level`, `budget_alignment_status`, `confidence_score`, `requires_manual_review`. They are not industry JSON. Thresholds come from the Industry Profile. This cut does not retune them.

Channel and CRM columns that are not industry fields (`source`, `whatsapp_opt_in`, `external_crm_id`, `crm_sync_status`, `funnel_stage`, `assigned_agent`) stay relational. They are not dumped into JSONB to avoid a decision.

---

## 6. Credentials

**Accepted.** WhatsApp ingress is not a user login. One `v2.tenant_credentials` row per tenant, separate from `users`. This matches Mayank's one-to-one credential entity.

```text
v2.tenant_credentials
  id                  uuid primary key
  tenant_id           uuid not null unique references v2.tenants(id) on delete cascade
  api_key_hash        text
  twilio_phone_number text
  twilio_account_sid  text
  twilio_secret_ref   text
  created_at          timestamptz not null default now()
```

`twilio_secret_ref` is a secret-store reference. The raw auth token is not a column, not JSONB, and not in this document. Phone number and account SID stay because webhook routing needs them. They are not the token. The API key is stored only as a hash. The foreign key uses `ON DELETE CASCADE` for this cut, same as the other `v2` tenant keys. The token does not live on the User row.

`X-API-Key` resolves through `tenant_credentials` to `tenant_id`, then through the same request context as a JWT. The handler never trusts a `tenant_id` in the body.

---

## 7. Messages stay rows

**Accepted.** Keep a separate `messages` table with a `tenant_id` foreign key. This migration does not collapse messages into `conversation.message_history`.

Webhook idempotency is `webhook_logs.message_sid`. The history window reads message rows. A single JSON document cannot do either without a rewrite that is outside this cut.

`v2.messages` keeps one row per message, with `tenant_id` not null and a foreign key to the lead or session. `v2.conversations` may exist as a parent. `message_history` JSONB is a later projection, built from rows, not the source of truth.

`v2.webhook_logs` gains `tenant_id`. The current table has none. Dedup remains on `message_sid`.

---

## 8. CASCADE now, RESTRICT later

Mayank confirmed this on 26 October 2026. This cut uses `ON DELETE CASCADE` on `v2` tenant foreign keys so the shadow schema matches the ER and dual-write does not break app deletes that expect child rows to disappear. A tenant delete in this cut still drops child rows.

`ON DELETE RESTRICT` is the later contract step, after the app no longer deletes a client and expects children to vanish. That step also replaces tenant delete with a background job: soft delete, archive, then purge. It is not part of Tuesday's package, and it is not applied to V1 in this cut.

---

## 9. Security boundaries

Fail closed. A missing tenant context returns no operational rows. It does not mean "all tenants."

### 9.1 Row-level security

**Accepted.** `FORCE ROW LEVEL SECURITY` and a non-owner app role are required. The sample policy is bypassed by the table owner. Render's application role often owns the tables. Without the two rules below, RLS does not meet the P0 isolation bar.

- `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` on every operational table.
- The application role is not the owner and is not a superuser. It has `SELECT`, `INSERT`, `UPDATE` on the operational tables and nothing else.
- A migration role owns the tables. The app never connects as that role.
- The policy is `tenant_id = current_setting('app.current_tenant_id', true)::uuid` for both `USING` and `WITH CHECK`.
- `current_setting(..., true)` returns null when the setting is missing. The comparison then fails. The query returns no rows. It does not throw open.
- An empty string or a non-UUID fails the cast inside a transaction that has already set the role. The request errors. It does not fall back to tenant 1.

`SET LOCAL app.current_tenant_id` runs inside the transaction, after the request context is known, before any operational query. `SET LOCAL` ends at commit or rollback. The pool resets the connection on check-in anyway, so a leaked session variable cannot ride to the next request. Do not use `SET` without `LOCAL`.

Proposed shape, not to be executed now:

```sql
ALTER TABLE v2.leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE v2.leads FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON v2.leads
  USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
  WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
```

The same policy is repeated for every operational table that has `tenant_id`. A table without `tenant_id` is not readable by the app role.

### 9.2 API auth

One request context object is built before any query:

- Dashboard JWT: `active_tenant_id` and `permissions` come from the token. A `tenant_id` in the body, query string, or JSON payload is overwritten with the token value. The client value is ignored, not merged.
- `X-API-Key`: hash the key, resolve `tenant_credentials`, set `active_tenant_id` from that row. Same overwrite rule.
- Admin key: does not become a tenant. It selects the platform role in section 9.3. It does not set `app.current_tenant_id` to a client id.

A key or token for tenant B, plus a lead id that belongs to tenant A, returns no row even if the query forgets the `tenant_id` filter. That is the RLS test. Application filters stay. They are not a substitute for the policy.

Impersonation check to include in the later implementation, not run now: call the lead read with tenant B's credential and tenant A's id. Require zero rows and no name or phone from A in the response.

### 9.3 Jobs and admin routes

Three classes. A job does not get `BYPASSRLS` because it is convenient.

| Class | Examples | Context |
|---|---|---|
| Tenant-scoped | follow-up send, CRM resync of one lead, n8n claim hydration, escalation, KG upsert of one lead | Read `tenant_id` from the event or the legacy map. `SET LOCAL` before any lead or message read. If the id does not resolve, skip. Do not guess tenant 1 |
| Platform | `/api/v1/roi/*`, pipeline report, competitor monitor across tenants | Explicit platform role, audited, named in the route. Not the app role. No PII export beyond the aggregate the route already returns |
| Maintenance | `db_backup.py`, `db_restore.py`, nightly cleanup of expired tokens | A role that can dump or delete expired non-PII rows and cannot `SELECT` from `v2.leads` or `v2.messages` |

The event bus already carries `{lead_id, tenant_id}` and not the lead body. Workers keep that claim-check. They load the row only after `SET LOCAL` for that tenant. A fat payload on the bus is still ignored.

Scheduler jobs that scan every tenant do not run as the app role with the setting unset. Unset means zero rows. A scan uses the platform role and writes an audit row per run.

### 9.4 What still fails closed

- Unknown `tenant_id` format: reject.
- API key hash miss: 401. No query.
- JWT for tenant A and path id for tenant B: 404 or empty, and no PII in the body.
- Dual-write to `v2` when the Industry Profile schema rejects the JSON: V1 write may still commit, because V1 is the source of truth during the soak. The `v2` upsert is recorded as a parity failure. It does not partially insert an invalid JSON lead.
- `dlq_events.client_id` null: the replay job does not send and does not invent a tenant. That rule already exists for the SEC02 path. V2 keeps it.

---

## 10. Backward compatibility

Until the contract step:

- `X-API-Key` keeps working through `tenant_credentials` and the legacy map.
- Session ids stay `{v1_client_id}_{phone}`.
- Redis locks stay on the same key shape.
- Bus `Client_<int>` still resolves. `Tenant_<uuid>` also resolves.
- HubSpot `external_crm_id` is unchanged.
- Twilio webhook routing stays on the tenant credential, not on a user id.
- Dashboard JWT gains `active_tenant_id` when the auth cut is approved. Until then the existing JWT still maps through `v1_client_id`.

Neo4j is not migrated in place. After the read cut is approved, graph nodes are rebuilt from Postgres for the new tenant ids. The graph is not a source of truth and is not part of rollback.

---

## 11. Not in this package

- Executing the shadow schema.
- Dropping V1 columns or turning off V1 writes.
- Rebuilding Neo4j.
- Designing industries other than the `real_estate` keys Maitri already fixed.
- Changing Render `DATABASE_URL`.
- Storing API keys, Twilio tokens, or database URLs in this document.

---

## 12. Accepted by Mayank

Accepted 25 October 2026. Clarified 26 October 2026. He is updating the ER diagram for nullable name and phone, and for `twilio_secret_ref`.

| # | Decision | Status |
|---|---|---|
| 1 | Name and phone stay relational columns on `leads`, nullable for this cut | Accepted 26 October 2026. Section 5. `NOT NULL` waits for the contract step |
| 2 | One `v2.tenant_credentials` row per tenant. `api_key_hash` and `twilio_secret_ref`. No raw token | Accepted 26 October 2026. Section 6. Not a User row |
| 3 | Separate `messages` table with `tenant_id`. Do not collapse into JSONB | Accepted. Section 7 |
| 4 | `FORCE ROW LEVEL SECURITY`, non-owner app role, shadow `v2` schema, dual-write, `v1_client_id` map. V1 left intact for rollback | Accepted. Sections 3 and 9.1 |
| 5 | `ON DELETE CASCADE` on `v2` tenant foreign keys for this cut. `RESTRICT` at the later contract step, after the app stops expecting cascade deletes | Accepted 26 October 2026. Section 8 |

Industry JSON key names are `location`, `budget`, `property_type`, `intent`, and `visit_date`, from `V2_Industry_Profile.md`, profile `real_estate` version `1`.
