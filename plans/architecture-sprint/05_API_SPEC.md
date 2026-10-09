# API

Target routes. One process. No industry prefix. No service split.

Live routes stay until cutover. The compatibility table is at the bottom. Bodies here are the new contract.

---

## Conventions

- Base path `/api/v2`. V1 paths stay as listed in the compatibility table.
- Auth: `Authorization: Bearer` for user routes. `X-API-Key` for ingest and channel routes. `X-Admin-Token` for ops inject only.
- `agency_id` and `tenant_id` are not resource fields. They come from auth. See `03_TENANCY_AND_RBAC.md`. The only bodies that may carry `tenant_id` are `POST /api/v2/auth/switch` and membership create.
- Error shape:

```json
{ "error": "not_found", "message": "Lead not found" }
```

- List responses: `{ "data": [], "next": null }`.
- Write responses: the resource, plus `id`.
- Status codes that matter: 400 validation, 401 missing auth, 403 membership, 404 not in scope, 409 duplicate webhook or duplicate slug.

---

## Auth

### `POST /api/v2/auth/login`

Auth: none. Body `application/x-www-form-urlencoded`: `username`, `password`.

```json
{ "access_token": "<jwt>", "token_type": "bearer", "memberships": [ { "agency_id": 1, "tenant_id": 4, "role": "tenant_admin" } ] }
```

The token subject is the user id. It does not contain a tenant the server will trust without a membership check.

### `POST /api/v2/auth/switch`

Auth: Bearer. Body `{ "tenant_id": 4 }`. This is membership selection, not a resource scope. The id must already be one of the caller's memberships. Otherwise 403. The server still checks that membership on every later call. A `tenant_id` on any other resource body is ignored.

---

## Agencies

Auth: Bearer. `GET` and `PATCH` are `agency_admin` (own agency) or `platform_admin`. `POST` is `platform_admin` only. An agency admin cannot create another agency.

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/v2/agencies` | — | list in scope |
| POST | `/api/v2/agencies` | `{ "name", "billing_email", "logo_url?", "brand_color?", "custom_domain?" }` | agency |
| GET | `/api/v2/agencies/{id}` | — | agency |
| PATCH | `/api/v2/agencies/{id}` | same fields, partial | agency |

`platform_admin` may create an agency. A direct buyer is not created without an agency. `POST /api/v2/tenants` has no agency field. An `agency_admin` call attaches the caller's agency. A `platform_admin` call attaches Internal Platform Agency.

---

## Tenants

| Method | Path | Auth | Body | Response |
|---|---|---|---|---|
| GET | `/api/v2/tenants` | Bearer, agency scope | — | tenants in the agency |
| POST | `/api/v2/tenants` | Bearer, `agency_admin` or `platform_admin` | `{ "name", "industry_profile_key" }` | tenant, `api_key` once |
| GET | `/api/v2/tenants/{id}` | Bearer, in scope | — | tenant |
| PATCH | `/api/v2/tenants/{id}` | Bearer, `tenant_admin` | `{ "name?", "status?" }` | tenant |

`industry_profile_key` must name a published profile. The server writes one `tenant_configurations` row. It does not also store the profile id on `tenants`. The caller cannot send a raw profile document on this route.

Second industry: a second POST. Not a second key on the same tenant.

---

## Users

| Method | Path | Auth | Body |
|---|---|---|---|
| GET | `/api/v2/users` | Bearer, admin of the scope | — |
| POST | `/api/v2/users` | Bearer, admin | `{ "email", "password", "role", "tenant_id?" }` |
| PATCH | `/api/v2/users/{id}` | Bearer, admin | `{ "is_active?" }` |
| DELETE | `/api/v2/memberships/{id}` | Bearer, admin | — |

`role` is one of the four membership roles in `03_TENANCY_AND_RBAC.md`. `platform_admin` is not set on this route. A tenant role requires `tenant_id`, and that tenant must be inside the caller's scope. An agency role must not send `tenant_id`.

---

## Leads

Auth: Bearer, tenant scope, unless noted.

### `GET /api/v2/leads`

Query: `stage`, `temperature`, `q`, `cursor`. Response item:

```json
{
  "id": 10,
  "name": "A",
  "phone": "+91...",
  "email": null,
  "source": "whatsapp",
  "status": "open",
  "temperature": "warm",
  "score": 40,
  "stage": { "key": "new", "label": "New" },
  "attributes": { "location": "Wakad", "budget": "80 lakhs" },
  "requires_manual_review": false
}
```

`attributes` keys are the profile schema. Unknown keys are not returned and not accepted on write.

### `GET /api/v2/leads/{id}`

Same object, plus `owner` and `conversation_id`.

### `PATCH /api/v2/leads/{id}`

```json
{ "name": "A", "phone": "+91...", "attributes": { "budget": "75 lakhs" } }
```

Attribute keys not in the profile: 400. A successful patch emits `lead.updated`.

### `PATCH /api/v2/leads/{id}/stage`

```json
{ "stage_key": "contacted" }
```

Unknown key for this tenant's pipeline: 400. Emits `pipeline.stage_changed`.

### `POST /api/v2/leads/{id}/claim`

Body empty. Sets `status` to `claimed`.

### `GET /api/v2/leads/export`

Auth: `tenant_admin`, `agency_admin`, or `platform_admin`. File download. Same filter as the list. A platform-admin export is audited.

---

## Conversations

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/api/v2/conversations/{id}/messages` | Bearer | tenant scope |
| POST | `/api/v2/conversations` | API key | `{ "session_id", "message" }` → reply, optional `media_url` |
| POST | `/api/v2/channels/whatsapp` | API key + signature | provider form body. Reply is channel XML or an interim line |
| POST | `/api/v2/channels/sms` | API key | provider form body |

The WhatsApp path keeps the race window and the single interim. See `01_SPINE.md`.

---

## AI

### `POST /api/v2/leads/{id}/sales`

Auth: Bearer.

```json
{ "mode": "preview" }
```

`mode` is `preview` or `execute`. Default `preview`. The route is the `run_sales` tool. If that id is not on the tenant allowlist, return 403 and do not run. Preview writes nothing. Execute runs the same runtime tools and may emit events.

```json
{
  "mode": "preview",
  "applied": false,
  "temperature": "warm",
  "score": 40,
  "stage_before": "new",
  "stage_after": "contacted",
  "actions": []
}
```

---

## Knowledge

| Method | Path | Auth | Body |
|---|---|---|---|
| GET | `/api/v2/knowledge` | Bearer | — |
| POST | `/api/v2/knowledge/documents` | Bearer, `tenant_admin` | `{ "title", "body" }` |
| DELETE | `/api/v2/knowledge/documents/{id}` | Bearer, `tenant_admin` | — |

Documents are stored under the caller's tenant. There is no `tenant_id` in the body.

---

## Workflows, pipelines, appointments

Auth: Bearer, tenant scope.

| Method | Path | Body |
|---|---|---|
| GET | `/api/v2/pipelines` | — |
| GET | `/api/v2/workflows` | — |
| GET | `/api/v2/appointments` | — |
| POST | `/api/v2/appointments` | `{ "lead_id", "appointment_type", "starts_at" }` |
| POST | `/api/v2/appointments/{id}/complete` | — |

`appointment_type` must be in `conversation.tool_params.schedule_appointment.allowed_types`. Real-estate seed allows `site_visit`. Education seed allows `counselling`. `POST` submits `schedule_appointment`. It does not emit `appointment.scheduled` itself. The execution engine does. Complete emits `appointment.completed`.

Workflow definitions are profile data, not a free-form editor in this draft. `GET /api/v2/workflows` returns the bound profile's `workflows` block, read only.

---

## Integrations

| Method | Path | Auth | Body |
|---|---|---|---|
| GET | `/api/v2/integrations` | Bearer, `tenant_admin` | — |
| POST | `/api/v2/integrations` | Bearer, `tenant_admin` | `{ "kind", "external_key" }` |
| POST | `/api/v2/integrations/{id}/credentials` | Bearer, `tenant_admin` | `{ "secret_ref" }` |

`external_key` creates the webhook binding. Response does not echo secrets.

---

## Billing

Auth: `agency_admin` or `platform_admin`.

| Method | Path | Body |
|---|---|---|
| GET | `/api/v2/billing/subscription` | — |
| POST | `/api/v2/billing/subscription` | `{ "plan_key" }` |
| GET | `/api/v2/billing/invoices` | — |
| GET | `/api/v2/billing/usage` | — |

`GET /api/v2/billing/subscription` returns the agency's rows. It does not assume there is one. Stripe remains the processor. This API records the subscription. It does not implement card collection.

---

## Analytics and notifications

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/api/v2/analytics/pipeline` | Bearer | tenant-scoped. Not an admin-global report |
| GET | `/api/v2/analytics/funnel` | Bearer | tenant-scoped |
| GET | `/api/v2/notifications` | Bearer | tenant-scoped |
| POST | `/api/v2/notifications/{id}/acknowledge` | Bearer | claim path |

`/api/v2/analytics/pipeline` and funnel replace the current ROI routes. Those current routes are already tenant-scoped JWT reads. The new routes keep that. They do not become admin-global.

---

## Ops

### `POST /api/v2/ops/events`

Auth: `X-Admin-Token`.

```json
{ "event_type": "customer.onboarded", "lead_id": 10, "payload": {} }
```

Allowed `event_type` values, and no others: `customer.onboarded`, `payment.received`, `payment.due`, `renewal.due`, `document.pending`. Unknown type: 400. These are ops events. They are not industry routes.

The server loads the lead, checks it exists, and sets both ids from the row. A `tenant_id` in the body is ignored. Unknown lead: 404.

### `GET /api/v2/events/stream`

Auth: Bearer or the `jwt` cookie. Stream is filtered to the caller's tenant. Heartbeat comment every 15 seconds. 503 if the bus is down.

---

## Compatibility

Stay until cutover means the live path keeps its current contract. Retire means the new route replaces it after cutover. Nothing in this table is deleted by this document.

| Current | Target | Until cutover |
|---|---|---|
| `POST /api/v1/whatsapp` | `POST /api/v2/channels/whatsapp` | stay |
| `POST /api/v1/incoming_sms` | `POST /api/v2/channels/sms` | stay |
| `POST /api/v1/chat` | `POST /api/v2/conversations` | stay |
| `POST /api/v1/ingest` | `POST /api/v2/leads` import | stay |
| `POST /api/v1/webhook/meta` | binding + `lead.created` | stay |
| `POST /api/v1/webhook/portals` | binding + `lead.created` | stay |
| `POST /api/v1/calendar/confirm` | `POST /api/v2/appointments` | stay |
| `PATCH /api/v1/leads/{id}/stage` | `PATCH /api/v2/leads/{id}/stage` | stay |
| `POST /api/v1/leads/{id}/sales-ai` | `POST /api/v2/leads/{id}/sales` | stay |
| `POST /api/v1/notifications/acknowledge` | `POST /api/v2/notifications/{id}/acknowledge` | stay |
| `GET /api/v1/events/stream` | `GET /api/v2/events/stream` | stay |
| `POST /api/v1/lifecycle/events` | `POST /api/v2/ops/events` | stay |
| `GET /api/v1/roi/*`, `GET /api/v1/reports/pipeline` | `GET /api/v2/analytics/*` | stay, already tenant-scoped |
| `POST /api/v1/auth/login` | `POST /api/v2/auth/login` | stay |

No `/api/v2/real-estate`, `/api/v2/education`, or `/api/v2/travel`.

Live routes not in the table above stay as they are until a later cutover note. They are not dropped by silence.

| Current | Why it is not in the table |
|---|---|
| `GET /health`, `GET /metrics` | Not product routes |
| `POST /api/v1/webhook/twilio-status`, `POST /api/v1/webhook/stripe`, `POST /api/v1/contact` | Off the spine. No lead create |
| `GET /api/v1/calendar/availability` | Becomes `get_availability`. No new public contract in this draft |
| `GET` and `POST /api/v1/agents` | Become sales contacts. No v2 route in this draft |
| `GET` and `PATCH /api/v1/settings` | Tenant settings. No v2 route in this draft |
| Approvals list, approve, reject | Stay. Runner adapter still consumes `approval.requested` |
| `GET /api/v1/leads/{id}/score`, memory, prediction | Read models of the lead. Fold into `GET /api/v2/leads/{id}` after cutover |
| `GET /api/v1/leads/export` | `GET /api/v2/leads/export` |
| `GET /api/v1/marketing/segments`, `GET /api/v1/cs/at-risk`, `POST /api/v1/competitor/signals` | Profile-driven reads. No new route in this draft |
| `GET /api/v1/kg/status`, `GET /api/v1/graph/*` | Optional graph adapter. Not a core route |
| `GET /api/v1/events/leads/{id}/timeline`, `POST /api/v1/events/stub` | Timeline stays a tenant read. Stub stays ops-only |
| `GET /api/v1/predictions/*` | Read models. Not a new domain in this draft |
