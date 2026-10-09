# Spine

Target platform. One process, one database, one runtime. Industry is data.

This file owns the decisions and the pathways. It does not own column lists (`02_ERD.md`), role matrices (`03_TENANCY_AND_RBAC.md`), threat controls (`04_SECURITY_MODEL.md`), request bodies (`05_API_SPEC.md`), the event catalog (`06_EVENTS.md`), or SQL (`07_MIGRATION_LOGIC.md`).

Design baseline is the production schema at the branch point of `architecture-sprint`. Live tables stay in place until cutover.

---

## Decisions

- Four tiers always: Platform, Agency, Tenant, User. A direct buyer is a tenant under a seeded agency, Internal Platform Agency. `agency_id` is never null.
- One tenant, one industry. A second industry is a second tenant under the same agency.
- `agency_id` is the partition key on every business row. `tenant_id` is the isolation key. Tenant reads filter both. No `platform_id` column. Exceptions are platform templates and platform-admin audit rows. See `02_ERD.md`.
- Auth context sets both ids. The browser and the model do not.
- Industry is data. The core has no industry branch.
- The runtime injects `agency_id` and `tenant_id` into every tool call.
- Same repo, same database. New tables sit beside the current ones. Live tables are not altered until cutover.
- One process. Modules, not separate services.
- Workflow runner is an interface. n8n is the first adapter.
- Billing tables exist in the schema now. Stripe stays the processor.
- Agency brand is name, logo, and a nullable domain. No certificate flow.

---

## ASCII spine

```text
Platform
  Agency                         (direct buy → Internal Platform Agency)
    Tenant                       (one industry profile)
      User                       (membership)
        |
  Resolve agency_id + tenant_id  (API key | JWT membership | webhook binding | job envelope)
        |
  Industry profile (data)        Core (code)
  fields, prompts, scoring       auth, lead identity, chat, pipeline, bus, audit, billing
  tools on/off, stages
        |
  One agent runtime
  memory + knowledge + tools
  both ids injected here, never chosen by the model
        |
  Event bus (neutral names)
        |
  Workflow runner → Automation → Execution
        |
  Agency dashboard | Tenant dashboard (labels from the profile)

Beside this, until cutover:
  V1 tables (clients, leads, …) still serve live routes
  V2 tables serve new routes
  No destructive alter on V1
```

---

## Layers

| Layer | Kind | Contains |
|---|---|---|
| Core | code | Auth, agency, tenant, user, lead identity, conversation, pipeline, tasks, appointments, notifications, audit, billing |
| AI | code | One runtime loop. See `08_AGENT_RUNTIME.md` |
| Profile | data | Terminology, fields, scoring, prompts, tool allowlist, stages, workflows, KPIs. See `09_INDUSTRY_PROFILE.md` |
| Surfaces | code | Agency dashboard, tenant dashboard. Labels from the profile |

Real-estate nouns (site visit, brochure, floor plan, BHK) are profile examples. They are not boxes in the core.

---

## Hierarchy

```text
Platform
  └── Agency
        ├── Tenant (industry = real_estate)
        │     └── Users via membership
        └── Tenant (industry = education)     ← second industry, second tenant, same agency
              └── Users via membership
```

Today's `clients` row becomes a tenant. Today's `clients.email` login becomes a user plus a membership. Today's `agents` row becomes a sales contact, not a login. See `02_ERD.md`.

---

## Tenant resolution

Four paths. No others. Detail in `03_TENANCY_AND_RBAC.md`.

```text
API key ──────────────► one tenant, then its agency
JWT ──────────────────► user, then a membership that owns the active tenant
Webhook binding ──────► external account (number, page, portal) → tenant; body tenant field ignored
Job envelope ─────────► agency_id + tenant_id on the event; missing either id → ack, do not run, do not dead-letter
```

`X-Admin-Token` is an ops credential. It is not a tenant and not a role.

---

## Inbound

Each path resolves a tenant before any lead write.

| Path | Auth | Target event |
|---|---|---|
| `POST /api/v1/whatsapp` | API key + Twilio signature | `message.received` channel `whatsapp` |
| `POST /api/v1/incoming_sms` | API key | `message.received` channel `sms` |
| `POST /api/v1/chat` | API key | `message.received` channel `web` |
| `POST /api/v1/ingest` | API key | `lead.created` source `import` |
| `POST /api/v1/webhook/meta` | API key | `lead.created` channel `meta` |
| `POST /api/v1/webhook/portals` | API key | `lead.created` channel `portal` |
| `PATCH /api/v1/leads/{id}/stage` | JWT | `pipeline.stage_changed` |
| `POST /api/v1/notifications/acknowledge` | JWT | claim. Not an industry event |
| `POST /api/v1/leads/{id}/sales-ai` | JWT | runtime tool `run_sales`, preview or execute |
| `POST /api/v1/calendar/confirm` | API key | `appointment.scheduled` |
| `POST /api/v1/lifecycle/events` | ops token | ops inject. Tenant taken from the lead row |

Off the spine: Stripe subscription updates, Twilio status callbacks, `/health`, `/metrics`. They do not create leads.

Live WhatsApp URL stays on the old path until cutover. See `05_API_SPEC.md`.

---

## Reply path

WhatsApp is the channel with a race window. Other channels use the same runtime without it.

```text
Webhook
  → insert webhook_logs (duplicate → empty response)
  → lock agency:{agency_id}:tenant:{tenant_id}:session_lock:{raw}
  → private DB session
  → load profile + memory + knowledge
  → model (one call)
  → tools (ids injected)
  → reply
       fast: TwiML
       slow: one interim, then the same task's reply via the runner
  → events off the reply path
```

The interim line is a channel detail. It is not a second runtime and not a second model call. A down knowledge adapter returns empty context. It does not fail the turn.

---

## Runtime

```text
context already set
  → load profile
  → last 6 turns + memory + knowledge + optional graph
  → prompt = stable shell + profile fragments
  → model
  → tool allowlist only
  → inject agency_id, tenant_id
  → write identity, attributes, reply
  → emit neutral events
```

Full loop: `08_AGENT_RUNTIME.md`.

---

## Events and execution

```text
message.received | lead.created | lead.qualified | lead.scored | lead.hot
        |
  core workflows (follow-up, score, CRM, notify, task)
        |
  WorkflowRunner.submit(envelope)
        |
  n8n adapter (first implementation; core does not import it)
        |
  Automation → Execution
        |
  send_message | update_crm | schedule_appointment | notify_sales | create_task
        |
  failure → DLQ
```

Catalog and rename map: `06_EVENTS.md`.

Pricing, inventory, brochure, and floor plan are a real-estate tool pack inside the profile. They are not core workflows. See `10_MEMORY_KNOWLEDGE_TOOLS.md`.

---

## Scheduler

Industry-blind jobs. Gaps and quiet hours come from the profile.

| Job | When | Effect |
|---|---|---|
| Follow-up tick | 1 min | Send the next step from the profile sequence |
| Backup | 02:00 | Dump. Does not cross tenants in the restore story |
| Cleanup | 03:00 | Drop aged logs. Ops context, not a tenant |
| Escalation | 1 min | Unacked hot alerts to the sales contact whose capabilities match. Not a membership |
| CRM resync | 5 min | Re-push rows flagged pending |
| Competitor scan | 01:00 | No-op when the profile keyword list is empty |
| Weekly report | Mon 08:00 | One report event per active tenant |
| Expire approvals | 15 min | Close stale approval rows |

---

## Stores

| Store | Rule |
|---|---|
| Postgres | System of record. Both ids on every tenant-scoped row. Exceptions are in `02_ERD.md` |
| Redis | Locks, dedupe, stream. Key prefix `agency:{id}:tenant:{id}:` |
| Vector index | Optional. Foreign tenant chunk is dropped |
| Graph | Optional. Same filter. Down means no graph block |
| Workflow runner | Optional. Unconfigured means the core still completes the turn |

---

## Failure

- Duplicate webhook: insert `webhook_logs` first. Conflict on `(tenant_id, message_sid)` returns an empty response.
- Interim: at most one per message id.
- DLQ: outbound send, CRM, follow-up scheduler, unknown execution action.
- Replay is an ops script, not a product path.

---

## Dashboards

Agency view lists that agency's tenants only: industries, leads today, qualified, appointments, hot.

Tenant view lists that tenant only. Stage labels, appointment labels, and field labels come from the profile.

Command-center pages (copilot, graph, twin) are tenant tools. They are not a third product. Public marketing pages are out of this spine.

---

## V1 beside V2

```text
Live routes  → public schema (clients, leads, …)
New routes   → schema v2 (agencies, tenants, leads, lead_attributes, …)
Cutover      → switch reads, freeze, final copy, then (later) drop old columns
Rollback     → point reads back at the public schema
```

New tables are created in schema `v2` so the name `leads` does not collide with the live table. See `07_MIGRATION_LOGIC.md`.

Detail: `07_MIGRATION_LOGIC.md`.

---

## Acceptance

Adding Travel is a profile, a qualification schema, a knowledge namespace, a pipeline, and KPIs. It does not add an agent class, a lead table, or an `/api/v1/travel` prefix. If it does, this spine is wrong.
