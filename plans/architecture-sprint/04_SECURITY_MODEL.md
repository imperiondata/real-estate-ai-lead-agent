# Security model

The failure this model exists to prevent: one tenant's runtime reads another tenant's leads or knowledge.

Controls are structural. A prompt instruction is not a control.

---

## Identity

Both ids come from `03_TENANCY_AND_RBAC.md`. A query that uses an id taken from the body, the query string, or a tool argument is a defect.

`X-Admin-Token` does not widen a tenant query. `X-Admin-Key` is not a header in this design.

---

## Stores

### Postgres

Every tenant-scoped query includes `agency_id` and `tenant_id` from the auth context. Agency-scoped roles may omit `tenant_id` only on `subscriptions`, `invoices`, and the agency tenant list. `plans` and `industry_profiles` have no `tenant_id`. Lead, message, memory, and knowledge queries never omit `tenant_id`.

### Redis

Key prefix: `agency:{agency_id}:tenant:{tenant_id}:`.

Applies to session locks, interim dedupe, negotiation debounce, hot-lead debounce, and sales locks. The stream envelope carries both ids. A consumer that cannot read both acks, does not run, does not write, and does not dead-letter.

### Vector index

Filter is both ids, applied in the query. A chunk with a foreign tenant is dropped even if the embedding matches. A missing filter is a failed query, not an unfiltered query.

### Graph

Same filter. If the graph is down, the prompt gets no graph block. It does not fall back to a shared graph.

### Tools

The runtime injects `agency_id` and `tenant_id` before the call. The tool schema has no argument for either. A call that includes either field is rejected. See `08_AGENT_RUNTIME.md` and `10_MEMORY_KNOWLEDGE_TOOLS.md`.

### Workflow runner

The runner receives the envelope. It cannot substitute a different tenant. The core does not import a vendor client. See `06_EVENTS.md`.

### Exports, analytics, dashboards

Same filter as the lead query. An agency export is the union of that agency's tenants, not the platform. A tenant export is one tenant.

---

## Secrets

Integration secrets live in `integration_credentials`, as a reference, not inside the profile JSON and not inside a prompt. Logs do not print keys, database URLs, or webhook signatures.

---

## Webhooks and jobs

- Signature first, then binding lookup, then write. See `03_TENANCY_AND_RBAC.md`.
- Duplicate `(tenant_id, message_sid)` returns an empty response. The dedupe key is that pair. See `02_ERD.md`. A replay cannot attach to a different tenant by reusing the provider id.
- Interim send is at most one per message id, same prefix rule.
- A job with a missing envelope id is acked and does not run. It does not write, does not dead-letter, and does not use the last tenant in process memory. See `06_EVENTS.md`.

---

## Audit

Write an `audit_logs` row on:

- cross-tenant denial
- membership change
- export
- ops inject
- credential read

Platform-admin reads of another agency are audited. They are not silent.

---

## PII

Lead phone, email, and message body are tenant data. They are not copied into platform-level logs. AI run rows store token counts and profile version, not the full prompt, unless a later decision says otherwise. This draft does not store the full prompt.

---

## Rate limit and backup

Rate limits are per tenant on inbound messaging and per user on dashboard reads. A noisy tenant must not exhaust the platform lock table; the session lock is already per session id, which is tenant-prefixed.

Backup and restore copy all tenants. Restore of one tenant is a filtered copy, not a second database. Live restore does not point the application database URL at the backup target. That split stays.

---

## Paper tests

Not code. Each test must fail closed.

| Test | Expected |
|---|---|
| API key of tenant A, lead id of tenant B | 404, no row in the body |
| JWT of tenant A, resource body `tenant_id` of tenant B | ignored. Query stays on A. Not a switch |
| Switch or membership create for a tenant the caller does not hold | 403, audit row |
| Webhook with a valid signature and a forged tenant field | tenant comes from the binding, forged field ignored |
| Job envelope missing `agency_id` or `tenant_id` | ack, no run, no write, no dead-letter |
| Vector query for tenant A | no chunk whose `tenant_id` is B |
| Tool call that includes `tenant_id` | rejected before execution |
| Agency admin export | rows of that agency only |
| Ops token on a lead list | rejected |
| Runner adapter asked to swap tenant | core envelope unchanged |

If any test can pass by editing a prompt, the control is in the wrong layer.
