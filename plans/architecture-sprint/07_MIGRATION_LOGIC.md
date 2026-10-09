# Migration logic

Proposed SQL and copy order. Not applied. Live tables are not altered in this draft.

Reads and writes name tables from `02_ERD.md`. V1 names are the current tables: `clients`, `sessions`, `messages`, `leads`, `event_logs`, `follow_up_states`, `webhook_logs`, `dlq_events`, `agents`, `approval_requests`, `agent_learning`, `notification_logs`, `lead_memories`, `inventory_units`, `pricing_rules`, `agent_tasks`.

Each step says what it must not drop.

---

## 1. Create V2 tables

Create schema `v2` and every table in `02_ERD.md` inside it. Qualify every new-table statement with `v2.`. Do not `ALTER` `public.leads` or `public.clients`. Do not drop a column. Do not rename a V1 table.

Rollback of this step: drop only the new tables, and only if no V2 route has been enabled.

---

## 2. Seed the internal agency

```sql
INSERT INTO v2.agencies (name, slug, status, billing_email)
VALUES ('Internal Platform Agency', 'internal-platform', 'active', 'billing@internal')
ON CONFLICT (slug) DO NOTHING;
```

One row. Later direct buyers use this id. Do not leave `agency_id` null to mean "direct".

---

## 3. Seed the real-estate profile, then copy clients

Insert one `v2.industry_profiles` row before any tenant configuration. `key` = `real_estate`, `status` = `published`, `version` = `1`. `document` is the real-estate example in `09_INDUSTRY_PROFILE.md`, and the `key` and `version` inside that JSON must equal the columns. Do not invent a second copy.

Seed `v2.pipelines` and `v2.pipeline_stages` for each new tenant from that document's `pipeline_stages`, after the tenant row exists and before leads are copied.

For each `clients` row:

- Insert `tenants` with `agency_id` = the internal agency, `name` = `company_name`, `status` from `is_active`. Do not put a profile id on this row.
- Store `api_key_hash` from the existing `api_key`. Do not print the key.
- Insert `tenant_configurations` for that tenant, `industry_profile_id` = the published `real_estate` profile, `profile_version` = the published version, `overrides` = `{}`.
- Keep a map table `migration_tenant_map (v1_client_id, tenant_id, agency_id)` in the new schema. The map is how later steps set both ids. Drop the map only after cutover sign-off, not in this draft.

Do not delete `clients`.

---

## 4. Copy logins to users

For each `clients` row:

- Insert `users` with `email` and `hashed_password` copied. On email conflict, reuse the user. Do not reset the password.
- Insert `memberships` with `role` = `tenant_admin`, `agency_id` from the map, `tenant_id` from the map.

The V1 login still works against `clients` until cutover. This step does not switch it.

---

## 5. Copy agents to sales contacts

```sql
INSERT INTO v2.sales_contacts (
  agency_id, tenant_id, name, phone, email, capabilities, routing, active_lead_count
)
SELECT
  m.agency_id,
  m.tenant_id,
  a.name,
  a.phone,
  a.email,
  jsonb_build_object('escalate_10m', a.is_manager, 'escalate_30m', a.is_director),
  jsonb_build_object(
    'locations', a.locations,
    'speciality', a.speciality,
    'deal_size', a.deal_size,
    'lead_type', a.lead_type
  ),
  a.active_leads
FROM public.agents a
JOIN v2.migration_tenant_map m ON m.v1_client_id = a.client_id;
```

Do not insert `users` for these rows. A sales contact is not a login.

---

## 6. Copy sessions, then leads

Copy `public.sessions` into `v2.sessions` first. Set both ids from the map. Do not insert a lead until its session row exists. `v2.leads.session_id` is a foreign key.

Identity columns go to `v2.leads`. Industry columns go to `v2.lead_attributes.data`.

```sql
INSERT INTO v2.leads (
  agency_id, tenant_id, session_id, name, phone, source, opt_in, status,
  temperature, score, conversion_probability, engagement_score, urgency_level,
  budget_alignment_status, inactivity_penalty, confidence_score,
  requires_manual_review, is_negotiating, external_crm_id, crm_sync_status,
  crm_resync_pending
)
SELECT
  m.agency_id, m.tenant_id, l.session_id, l.name, l.phone, l.source,
  l.whatsapp_opt_in,
  l.conversion_status,
  l.lead_temperature,
  CASE l.score WHEN 'High' THEN 80 WHEN 'Medium' THEN 50 ELSE 20 END,
  l.conversion_probability, l.engagement_score, l.urgency_level,
  l.budget_alignment_status, l.inactivity_penalty, l.confidence_score,
  l.requires_manual_review, l.is_negotiating, l.external_crm_id,
  l.crm_sync_status, l.crm_resync_pending
FROM public.leads l
JOIN v2.migration_tenant_map m ON m.v1_client_id = l.client_id;
```

```sql
INSERT INTO v2.lead_attributes (agency_id, tenant_id, lead_id, data)
SELECT
  v.agency_id, v.tenant_id, v.id,
  jsonb_strip_nulls(jsonb_build_object(
    'budget', l.budget,
    'location', l.location,
    'property_type', l.property_type,
    'intent', l.intent,
    'visit_date', l.visit_date
  ))
FROM public.leads l
JOIN v2.migration_tenant_map m ON m.v1_client_id = l.client_id
JOIN v2.leads v ON v.session_id = l.session_id AND v.tenant_id = m.tenant_id;
```

The second `leads` is `v2.leads`. The first is `public.leads`. Do not rename the live table to free the name.

Do not drop `budget`, `location`, `property_type`, `intent`, or `visit_date` from the live table.

String `score` High/Medium/Low is mapped to an integer so the new column type holds. The profile scorer overwrites it on the next V2 turn. V1 keeps the string.

After the lead row exists, set `pipeline_stage_id` from `public.leads.funnel_stage`:

| V1 `funnel_stage` | Stage key |
|---|---|
| New | `new` |
| Contacted | `contacted` |
| Appointment Scheduled | `appointment_scheduled` |
| Closed Won | `closed_won` |
| Lost | `lost` |

Any other value leaves `pipeline_stage_id` null and is listed. Do not invent a stage.

Set `owner_contact_id` by matching `public.leads.assigned_agent` to `v2.sales_contacts.name` in the same tenant. No match leaves the owner null and is listed. Do not create a contact to force a match.

---

## 7. Copy conversation and ops rows

Sessions were copied in step 6. This step copies `messages`, `lead_memories`, `follow_up_states`, `dlq_events`, `approval_requests`, `notification_logs`, `agent_tasks`, `agent_learning`, `event_logs`.

- Insert into the V2 table named in `02_ERD.md`.
- Set `agency_id` and `tenant_id` from `migration_tenant_map` via `client_id`.
- `lead_memories` copy into `conversation_memory` with `memory_type` kept.
- Do not copy `webhook_logs` by guessing. `message_sid` has no tenant prefix and the table has no `client_id`. Leave those rows in `public`. List the count. V2 writes new dedupe rows. Do not attach an old sid to a tenant by inference.

Do not delete the source rows.

---

## 8. Profile data that is not a core table

Copy `inventory_units` and `pricing_rules` into the real-estate profile document's product block for that tenant's `tenant_configurations.overrides`, under the whitelist key `product_data`. Do not create `inventory_units` in the V2 core.

If the overrides whitelist does not include `product_data`, extend the whitelist in `09_INDUSTRY_PROFILE.md` before this step. Do not stuff the rows into `leads`.

---

## 9. Dual-read window

- Live routes keep reading V1 tables.
- New routes read V2 tables.
- No dual-write in this draft. A live WhatsApp turn must not write both, or the two rows will diverge without a merge rule.
- Billing: insert one `v2.subscriptions` row per distinct `clients.stripe_customer_id`, all with the internal `agency_id`. Do not collapse several Stripe ids into one row. `subscriptions.agency_id` is not unique. Stripe webhooks keep updating V1 until cutover. Do not point Stripe at V2 in this step.

---

## 10. Cutover

Not part of the first apply. Order when it is scheduled:

1. Freeze V1 writes.
2. Repeat steps 6 and 7 for rows changed since the first copy. Match on `session_id` and the map.
3. Switch reads to V2.
4. Keep V1 tables.
5. Rollback is: point reads back at V1. V1 was not altered, so the freeze window's uncopied V2 writes are discarded, not merged, unless a later note says otherwise.

Dropping V1 columns is a separate step after sign-off. This document does not include that `ALTER`.

---

## Must not

- Must not run against the live database as part of writing this file.
- Must not set `DATABASE_URL` to the live host.
- Must not drop `clients`, `leads`, or `agents`.
- Must not null `agency_id`.
- Must not put two industries on one tenant to save a copy.
