# Tenancy and RBAC

How a request gets `agency_id` and `tenant_id`, and who may read what. Column shapes are in `02_ERD.md`. Threat tests are in `04_SECURITY_MODEL.md`.

---

## Rules

- `agency_id` is never null on a tenant or on a business row.
- A direct buyer is a tenant under the seeded agency Internal Platform Agency.
- One tenant, one industry profile. A second industry is a second tenant under the same agency.
- Auth context sets both ids. A resource body, the query string, and the model do not. Switch and membership create are the only body exceptions, and both still require a membership check.
- A tenant query filters `agency_id` and `tenant_id`.
- An agency query filters `agency_id` only, and only for roles that are agency-scoped.
- Session id shape is `{tenant_id}_{raw}`.
- A sales contact is not a user and not a membership.

---

## Resolution

### API key

Used by WhatsApp, SMS, chat, ingest, Meta, portals, and calendar confirm.

1. Read `X-API-Key` or `?api_key=`.
2. Hash and match `tenants.api_key_hash`.
3. Load that tenant. Reject if `status` is not `active`.
4. Set `tenant_id` and `agency_id` from the row.
5. Ignore any tenant or agency field in the body.

One key, one tenant. An agency does not hold a key that can see every tenant.

### JWT

1. Read `Authorization: Bearer`. The cookie `jwt` is the same token, kept so a browser stream can send it. It is not a second login. Only `GET /api/v2/events/stream` may read the cookie. Every other route requires the header.
2. Resolve the user from the token subject.
3. Load memberships for that user.
4. The active tenant is the one selected for this request. It must be one of those memberships.
5. Set `agency_id` and `tenant_id` from that membership.
6. A resource body that names a tenant does not change the query scope. Ignore it. Two calls may carry `tenant_id` and must still pass a membership check: `POST /api/v2/auth/switch`, and membership create. Any other body tenant id is not authority.

A user who is not `platform_admin` and has no membership is rejected. A token is not a tenant. `platform_admin` with no membership has platform scope and no active tenant until a switch. That switch still requires a membership on the target tenant.

### Webhook binding

1. Read the provider account from the signature-verified payload (Twilio number, page id, portal account).
2. Look up `webhook_bindings.external_key`.
3. Set both ids from that row.
4. Drop any tenant field in the body.

No binding, no write.

### Job envelope

1. Read `agency_id` and `tenant_id` from the event envelope. See `06_EVENTS.md`.
2. If either is missing, ack the message, do not run, do not write, and do not dead-letter. A missing id is poison, not a retry. Do not fall back to a default tenant.
3. Set context, then query.

Ops jobs that are not tenant-scoped (backup, aged-log cleanup) set an ops context. They do not read lead rows without a tenant filter.

### Ops token

`X-Admin-Token` matches the platform ops secret. It is not a role and not a tenant. It may inject an ops event only after the lead row supplies the tenant. It may not list another tenant's leads.

---

## Roles

`platform_admin` is `users.is_platform_admin`. The other four roles are stored on `memberships.role`.

| Role | Scope |
|---|---|
| `platform_admin` | Cross-agency. Column on `users`, not a membership |
| `agency_admin` | One agency, all of its tenants |
| `tenant_admin` | One tenant |
| `tenant_member` | One tenant. Work the queue. No billing, no exports of other users |
| `tenant_viewer` | One tenant. Read only |

`platform_admin` is the only role that crosses agencies.

---

## Matrix

| Action | platform_admin | agency_admin | tenant_admin | tenant_member | tenant_viewer |
|---|---|---|---|---|---|
| List agencies | yes | own agency | no | no | no |
| List tenants | yes | own agency | own tenant | no | no |
| Leads, conversations | any, audited | own agency | own tenant | own tenant | read own tenant |
| Knowledge | any, audited | own agency | own tenant | own tenant | read own tenant |
| Billing | yes | own agency | no | no | no |
| Exports | yes | own agency | own tenant | no | no |
| Ops inject | yes | no | no | no | no |
| Manage memberships | yes | own agency | own tenant | no | no |

A denial writes an `audit_logs` row.

---

## Escalation

The 10-minute and 30-minute hot-lead targets are `sales_contacts.capabilities`. They are not columns named `is_manager` and `is_director`, and they are not membership roles.

Selection stays inside the tenant. If no contact holds the higher capability, fall back to the lower one and log the fallback. Do not cross tenants to find a recipient.

---

## What does not resolve a tenant

- A `tenant_id` field on a resource body. It does not select the row. Switch and membership create are the only exceptions, and both require a membership check. See `05_API_SPEC.md`.
- A model tool argument.
- A Twilio `From` number alone. The binding table maps the destination account, not the sender.
- The string `Client_{id}` from the current bus. The new envelope carries integer `agency_id` and `tenant_id`. See `06_EVENTS.md`.
