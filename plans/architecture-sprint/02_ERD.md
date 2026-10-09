# Entity model

Target tables. Current tables stay until cutover. This file does not run SQL. Script order is `07_MIGRATION_LOGIC.md`.

Conventions:

- New tables live in schema `v2`. The live tables stay in `public`. Do not rename `public.leads` to free the name.
- Tenant-scoped row: `agency_id` NOT NULL, `tenant_id` NOT NULL, index `(agency_id, tenant_id)`.
- Exceptions, no `tenant_id`: `industry_profiles`, `plans`. Agency-scoped, no `tenant_id`: `subscriptions`, `invoices`. `audit_logs.tenant_id` is null only for a platform-admin action.
- Platform template: no `tenant_id`. `industry_profiles` and `plans` are templates.
- Ids are integers unless noted. Timestamps are timezone-aware.
- No industry branch in a check constraint. No `property_type` column on `leads`.

---

## Agency and tenant

### agencies

| Column | Notes |
|---|---|
| id | PK |
| name | NOT NULL |
| slug | unique |
| status | `active` \| `suspended` |
| logo_url | nullable |
| brand_color | nullable |
| custom_domain | nullable. No certificate flow |
| billing_email | NOT NULL |
| created_at | |

Seed row: slug `internal-platform`, name Internal Platform Agency. Direct buyers attach here. `agency_id` is never null on a tenant.

### tenants

Replaces `clients` as the isolation boundary. Does not replace the login.

| Column | Notes |
|---|---|
| id | PK |
| agency_id | FK agencies, NOT NULL |
| name | NOT NULL |
| status | `active` \| `suspended` |
| api_key_hash | unique. Plain key is shown once at create |
| settings | JSONB. Non-industry flags only |
| created_at | |

One profile per tenant lives on `tenant_configurations`, not on this row. A second industry is a second tenant under the same `agency_id`.

### users

| Column | Notes |
|---|---|
| id | PK |
| email | unique, NOT NULL |
| hashed_password | NOT NULL |
| is_active | |
| is_platform_admin | default false. Not a membership. The only cross-agency flag |
| created_at | |

No `agency_id` on the user. Agency and tenant scope live on the membership. `platform_admin` is this flag, not a role row with a null agency.

### memberships

| Column | Notes |
|---|---|
| id | PK |
| user_id | FK users, NOT NULL |
| agency_id | FK agencies, NOT NULL |
| tenant_id | FK tenants, nullable |
| role | see `03_TENANCY_AND_RBAC.md` |
| created_at | |

`tenant_id` null means the role is `agency_admin`. A tenant role requires `tenant_id`. `role` is never `platform_admin`. Two unique indexes, because a null `tenant_id` does not collide in one unique constraint: unique `(user_id, agency_id)` where `tenant_id` is null, and unique `(user_id, agency_id, tenant_id, role)` where `tenant_id` is not null.

### sales_contacts

Replaces `agents`. Not a login.

| Column | Notes |
|---|---|
| id | PK |
| agency_id, tenant_id | both NOT NULL |
| name, phone, email | |
| capabilities | JSONB. Escalation targets live here, not as a second user table |
| routing | JSONB. Locations, speciality, deal size. Profile-shaped, not core columns |
| active_lead_count | integer |

`is_manager` and `is_director` do not survive as columns. Escalation reads `capabilities`.

---

## Profile

### industry_profiles

Platform template. No `tenant_id`.

| Column | Notes |
|---|---|
| id | PK |
| key | unique, e.g. `real_estate` |
| version | integer. Published version is immutable |
| document | JSONB. Shape in `09_INDUSTRY_PROFILE.md` |
| status | `draft` \| `published` |

### tenant_configurations

| Column | Notes |
|---|---|
| id | PK |
| agency_id, tenant_id | both NOT NULL. Unique on `tenant_id` |
| industry_profile_id | FK, NOT NULL |
| profile_version | the published version bound at assign time |
| overrides | JSONB. Whitelist only. Cannot replace the runtime |

---

## Lead and conversation

### leads

Identity and status only.

| Column | Notes |
|---|---|
| id | PK |
| agency_id, tenant_id | both NOT NULL |
| session_id | unique, FK sessions |
| name, phone, email | email nullable |
| source | |
| opt_in | boolean. Channel-neutral |
| status | `open` \| `claimed` \| `closed` |
| owner_contact_id | FK sales_contacts, nullable |
| temperature | `hot` \| `warm` \| `cold` |
| score | integer 0–100. Replaces the string score |
| conversion_probability | integer |
| engagement_score | integer |
| urgency_level | string. Values come from the scorer, not a housing enum |
| budget_alignment_status | string |
| inactivity_penalty | integer |
| confidence_score | integer |
| requires_manual_review | boolean |
| is_negotiating | boolean |
| pipeline_stage_id | FK pipeline_stages, nullable |
| external_crm_id | |
| crm_sync_status | |
| crm_resync_pending | boolean |
| created_at, updated_at | |

Not columns: `property_type`, `budget`, `location`, `intent`, `visit_date`, `funnel_stage`.

### lead_attributes

| Column | Notes |
|---|---|
| id | PK |
| agency_id, tenant_id, lead_id | NOT NULL |
| data | JSONB. Keys must exist in the bound profile's `qualification_schema` |
| updated_at | |

Not an EAV table. One row per lead. Filterable keys from the profile get an expression index, declared in the migration, not a side table per field.

### sessions

| Column | Notes |
|---|---|
| id | PK string. Shape `{tenant_id}_{raw}` |
| agency_id, tenant_id | NOT NULL |
| status | `active` \| `closed` |
| last_activity_at | |

### messages

| Column | Notes |
|---|---|
| id | PK |
| agency_id, tenant_id | NOT NULL |
| session_id | FK |
| role | `user` \| `assistant` |
| content | text |
| created_at | |

### conversation_memory

Replaces `lead_memories`.

| Column | Notes |
|---|---|
| id | PK |
| agency_id, tenant_id, lead_id | NOT NULL |
| session_id | nullable |
| key, value | |
| memory_type | `fact` \| `preference` \| `objection` |

---

## Pipeline, appointments, work

### pipelines

One per tenant.

| Column | Notes |
|---|---|
| id | PK |
| agency_id, tenant_id | unique together |
| name | |

### pipeline_stages

| Column | Notes |
|---|---|
| id | PK |
| agency_id, tenant_id, pipeline_id | NOT NULL |
| key | stable id, e.g. `new` |
| label | display. From the profile |
| position | integer |

The current enum New, Contacted, Appointment Scheduled, Closed Won, Lost is the real-estate seed. It is not a check constraint on `leads`.

### appointments

Replaces site-visit as a core noun.

| Column | Notes |
|---|---|
| id | PK |
| agency_id, tenant_id, lead_id | NOT NULL |
| appointment_type | from the profile. Real-estate seed: `site_visit` |
| starts_at | |
| status | `scheduled` \| `completed` \| `cancelled` |
| external_ref | calendar id, nullable |

### tasks

Replaces `agent_tasks`.

| Column | Notes |
|---|---|
| id | PK |
| agency_id, tenant_id, lead_id | lead nullable |
| assignee_contact_id | FK sales_contacts, nullable |
| title, status, due_at | |

### notifications

Replaces `notification_logs`.

| Column | Notes |
|---|---|
| id | PK |
| agency_id, tenant_id | NOT NULL |
| lead_id | nullable |
| channel, reason, severity, status | |
| created_at | |

### approval_requests

| Column | Notes |
|---|---|
| id | PK |
| agency_id, tenant_id | both NOT NULL |
| entity_id | lead or session, nullable |
| action_type | NOT NULL |
| action_payload | JSONB |
| status | `pending` \| `approved` \| `rejected` \| `expired` |
| requested_by, resolved_by, reason | nullable |
| correlation_id | unique |
| created_at, resolved_at | |

### agent_learning

| Column | Notes |
|---|---|
| id | PK |
| agency_id, tenant_id | both NOT NULL |
| agent_name | NOT NULL |
| wins, losses | integer |

Not a profile. Unique `(tenant_id, agent_name)`.

### event_logs

| Column | Notes |
|---|---|
| id | PK |
| agency_id, tenant_id | both NOT NULL |
| session_id | |
| event_type, action_type | |
| latency_ms | nullable |
| agent_type | |
| created_at | |

V1 rows are copied here. A user action also writes `audit_logs`. This table is not a second bus.

### follow_up_states

Keep the current columns. Add `agency_id`. `client_id` becomes `tenant_id`. Stage names come from the profile sequence, not from a hardcoded Day 0–7 check.

---

## Knowledge and integrations

### knowledge_bases, knowledge_documents, knowledge_chunks

All three carry `agency_id` and `tenant_id`. A chunk without both is invalid. The retriever drops a chunk whose tenant does not match the auth context.

### integrations

| Column | Notes |
|---|---|
| id | PK |
| agency_id, tenant_id | NOT NULL |
| kind | `twilio` \| `meta` \| `portal` \| `crm` \| `calendar` |
| status | |

### integration_credentials

Secrets. Not stored inside the profile document.

| Column | Notes |
|---|---|
| id | PK |
| integration_id | FK |
| agency_id, tenant_id | NOT NULL. Denormalized so a credential query cannot omit the filter |
| secret_ref | pointer to the secret store. Not the raw secret in this draft's JSON examples |

### webhook_bindings

| Column | Notes |
|---|---|
| id | PK |
| agency_id, tenant_id | NOT NULL |
| provider | |
| external_key | unique with `provider`. Phone number, page id, or portal account |
| integration_id | FK |

Unique `(provider, external_key)`. The inbound payload cannot name the tenant. Resolution reads this table. Stripe is not a row here. It lives on `subscriptions`.

---

## Billing

Enough to bill an agency. No metering engine.

### plans

Platform template. No `tenant_id`. `key`, `name`, `interval`, `amount_cents`, `currency`.

### subscriptions

| Column | Notes |
|---|---|
| id | PK |
| agency_id | NOT NULL. Billing is agency-scoped. Not unique. One agency may have several rows after the internal-agency migration |
| plan_id | FK |
| status | |
| stripe_customer_id | nullable |
| current_period_end | |

### invoices

`agency_id`, `subscription_id`, `amount_cents`, `status`, `issued_at`.

### usage_events

`agency_id`, `tenant_id`, `metric`, `quantity`, `occurred_at`. Written by the core. Not priced here.

---

## Audit and runs

### audit_logs

`agency_id`, `tenant_id` nullable only for platform-admin actions. `actor_user_id`, `action`, `entity`, `entity_id`, `created_at`.

### ai_runs

`agency_id`, `tenant_id`, `lead_id`, `profile_version`, `model`, `input_tokens`, `output_tokens`, `created_at`.

### ai_tool_calls

`ai_run_id`, `agency_id`, `tenant_id`, `tool_id`, `status`, `created_at`. No tenant argument in the stored request. The injected ids are columns, not model input.

### webhook_logs

PK `(tenant_id, message_sid)`. `agency_id` is a column, not part of the key. A duplicate of that pair returns an empty response. A provider id reused under another tenant is a different row.

### dlq_events

Add `agency_id`. `client_id` becomes `tenant_id`. `target_endpoint`, `payload`, `error_trace`, `status`.

---

## Migration only

`v2.migration_tenant_map (v1_client_id, tenant_id, agency_id)`. Not a product table. Steps that fill it are in `07_MIGRATION_LOGIC.md`. Drop it only after cutover sign-off.

---

## Not core tables

`inventory_units` and `pricing_rules` are not recreated as required tables. Their rows are copied into the real-estate profile's product data during migration. See `07_MIGRATION_LOGIC.md`.

---

## Current table map

| Current | Target |
|---|---|
| `clients` | `tenants` plus a `users` row plus a `tenant_admin` membership. `subscription_status` and `stripe_customer_id` move to `subscriptions` on the agency |
| `agents` | `sales_contacts` |
| `leads` | `leads` plus `lead_attributes` |
| `sessions`, `messages` | same names, both ids added |
| `lead_memories` | `conversation_memory` |
| `event_logs` | `event_logs`, both ids. User actions also write `audit_logs` |
| `follow_up_states` | same name, both ids |
| `webhook_logs`, `dlq_events` | both ids added |
| `approval_requests`, `notification_logs`, `agent_tasks` | `approval_requests`, `notifications`, `tasks` |
| `agent_learning` | `agent_learning`, both ids. Not a profile |
| `inventory_units`, `pricing_rules` | profile data, not core |
