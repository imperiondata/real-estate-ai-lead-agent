# HubSpot CRM Integration

End-to-end documentation for the HubSpot contact sync in the Real Estate Revenue OS.
Covers auth (Private App Token + scopes), endpoints (POST create / PATCH update),
the property map, error handling / retries, DLQ, portal setup, and troubleshooting.

---

## 1. Overview

```
WhatsApp webhook → process_unified_lead → lead created / fields updated
      │
      ▼
Event Bus (Redis Streams)
      │  lead.created / lead.qualified / conversation.updated
      ▼
crm_automation workflow → Automation Engine → Execution Engine
      │  action_type = "update_crm"
      ▼
CRMExecutor._sync_lead → crm_sync._push_to_hubspot
      │
      ├─ first sync (no external_crm_id)  → POST  /crm/v3/objects/contacts   → 201
      └─ re-sync   (external_crm_id set)  → PATCH /crm/v3/objects/contacts/{id} → 200
```

- **Create-time CRM is bus-owned** (`lead.created` → `crm_automation` → AE → EE → `CRMExecutor`).
  Do not call `sync_lead_to_crm` from chat/webhook paths (`AGENTS.md` § CRM Sync).
- **Field updates** are debounced: `agent.py` sets `Lead.crm_resync_pending = True`,
  and `crm_resync_job` (APScheduler, every 5 min) re-pushes and clears the flag (P5.1).
- **No duplicates:** re-syncs PATCH the existing contact (stored in
  `Lead.external_crm_id`) instead of creating a new one.

---

## 2. Auth — Private App Token (PAT)

HubSpot authentication uses a **Private App access token** — not OAuth, not the
legacy HAPI key.

| Item | Value |
|------|-------|
| Header | `Authorization: Bearer <CRM_API_KEY>` |
| Content-Type | `application/json` |
| Env var | `CRM_API_KEY` (read via `os.getenv` in `crm_sync.py`, not pydantic Settings) |
| Portal URL | `CRM_API_URL` — default `https://api.hubapi.com/crm/v3/objects/contacts` |

### Scopes required (this project)

Create a Private App (Settings → Integrations → Private Apps) with these scopes:

| Scope | Needed for |
|-------|------------|
| `crm.objects.contacts.read` | Contact lookups / verification |
| `crm.objects.contacts.write` | **Create + update contacts (POST / PATCH)** |
| `crm.objects.companies.read` | Optional — company lookups (reserved) |
| `crm.objects.companies.write` | Optional — company writes (reserved) |

Contacts read/write are the minimum for the shipped path. Companies scopes are
harmless and reserved for future company sync.

> **401 vs 403:** a token without the required scope returns `403` (`OAuth` /
> scope error). A missing / malformed token returns `401`. See § 8.

### Creating the Private App access token (step-by-step)

HubSpot **deprecated legacy API keys on 2022-11-30** — there is no API-key
setting anymore. Private App access tokens are the only static-token option.
You need **Super Admin** permissions in a regular HubSpot portal (Private Apps
are **not** available in developer-portal accounts; most paid plans and some
free tiers include them).

1. Log in at `app.hubspot.com` and click the **gear icon** (Settings) in the
   top navigation bar.
2. In the left sidebar, go to **Integrations → Private Apps**.
3. Click **Create a private app** (top right).
4. On the **Basic Info** tab enter a descriptive **name** (e.g.
   `ireios-crm-sync`), an optional **description** and **logo**.
5. Open the **Scopes** tab and click **Add new scope**. Search and check the
   scopes from the table above (`crm.objects.contacts.read`,
   `crm.objects.contacts.write`, and optionally the two companies scopes),
   then click **Update**. Grant only the minimum scopes — you can add more
   later by editing the app (the token picks up new scopes automatically).
6. Click **Create app** (top right). Review the permissions summary in the
   dialog and click **Continue creating**.
7. HubSpot displays a **Token dialog** with the access token. **Copy it
   immediately — the full token is shown only once.** If you lose it, open the
   app and click **Auth → Show token** to reveal it again.
8. Store it as `CRM_API_KEY` in `.env` (which is gitignored — never commit the
   token). Optionally verify with:
   ```bash
   curl -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
     "https://api.hubapi.com/crm/v3/objects/contacts?limit=1"
   ```
   A JSON contact list = token + scopes are correct. `401` = bad/copied-wrong
   token; `403` = token works but a scope is missing.

**Token rotation:** HubSpot recommends rotating every **6 months** and emails
Super Admins about rotation status. On the app details page (**Auth** tab):
**Rotate and expire now** revokes the old token immediately (use when
compromised); **Rotate and expire later** expires it in **7 days** (grace for a
regular rotation). Rotating instantly invalidates the old token — update
`CRM_API_KEY` after rotating. Deleting the app permanently revokes its token.

---

## 3. Endpoints used

| Operation | Method + URL | When | Success |
|-----------|--------------|------|---------|
| Create contact | `POST /crm/v3/objects/contacts` | First push (no `external_crm_id`) | `201` + body with `id` |
| Update contact | `PATCH /crm/v3/objects/contacts/{contactId}` | Re-sync (`external_crm_id` exists) | `200` |

Implemented in `_push_to_hubspot(payload, external_id=None)` (`crm_sync.py`):

```python
if external_id:
    url = f"{CRM_API_URL}/{external_id}"
    method = client.patch
else:
    url = CRM_API_URL
    method = client.post
```

Both callers pass the stored id when present:

- `crm_sync._sync_lead_to_crm_async` → `_push_to_hubspot(payload, external_id=lead.external_crm_id)`
- `app/execution_engine/crm_executor.py` `CRMExecutor._sync_lead` → same

---

## 4. Property map

Built by `build_crm_properties(lead, include_extended)`.

### Base properties (always sent)

| HubSpot property | Source | Notes |
|------------------|--------|-------|
| `firstname` | `lead.name` | `"Unknown"` fallback when empty |
| `phone` | `lead.phone` | Identity field (P5.3) |
| `budget` | `lead.budget` | **Custom** — must exist in portal |
| `lifecyclestage` | hardcoded | `"lead"` |

### Extended properties (gated by `CRM_SYNC_EXTENDED_PROPERTIES`, default `true`)

Defined in `crm_sync._EXTENDED_CRM_PROPERTIES`:

| HubSpot property (internal name) | Lead attribute | HubSpot type |
|----------------------------------|----------------|--------------|
| `location` | `lead.location` | Single-line text |
| `intent` | `lead.intent` | Single-line text |
| `property_type` | `lead.property_type` | Single-line text |
| `visit_date` | `lead.visit_date` | Single-line text |
| `assignee` | `lead.assigned_agent` | Single-line text |
| `budget_alignment_status` | `lead.budget_alignment_status` | Single-line text |
| `urgency_level` | `lead.urgency_level` | Single-line text |
| `engagement_score` | `lead.engagement_score` | Number |
| `lead_temperature` | `lead.lead_temperature` | Single-line text |

- `None` values are skipped (property not included in the payload).
- Booleans are stringified (`"true"` / `"false"`).
- **All custom properties must exist in the portal with the exact internal
  (snake_case) name** or HubSpot rejects the request — see § 7.

---

## 5. Lifecycle & sync status

### Create-time poll (P5.3)

On first sync (not re-sync), `_sync_lead_to_crm_async` polls up to **10 × 0.5 s**
for `lead.phone` and `lead.name` before pushing, so the contact is never created
blank. If identity is still missing after the poll:

```python
decide_crm_status_after_poll(lead)  # -> "pending" (never "success")
```

`crm_sync_status = "pending"` means the next field update re-syncs instead of
marking the lead synced with empty identity.

### Status values

| `crm_sync_status` | Meaning |
|-------------------|---------|
| `success` | Contact created/updated; `external_crm_id` set |
| `pending` | Push OK but phone+name still empty → will re-sync on next field change |
| `failed` | Push permanently failed (after Tenacity) → DLQ row written |

### Resync job

`crm_resync_job` (every 5 min) selects leads where:

```
external_crm_id IS NOT NULL AND crm_sync_status == "success" AND crm_resync_pending == true
```

and re-pushes via **PATCH**. Failed re-syncs keep `crm_resync_pending = True`.

---

## 6. Error handling & retries

### Transient errors (retried by Tenacity)

`_push_to_hubspot` is decorated with:

```python
@retry(stop=stop_after_attempt(5),
       wait=wait_exponential(multiplier=1, min=2, max=30),
       retry=retry_if_exception_type((httpx.RequestError, CRMAPIError)),
       reraise=True)
```

Retry triggers: network errors, timeouts, and HTTP **429 / 5xx** (via
`CRMAPIError`). 4xx is **not** retried by Tenacity.

### 4xx unknown-property recovery (P5.2)

HubSpot returns `400` with `PROPERTY_DOESNT_EXIST` when a payload references a
property that does not exist in the portal:

```json
{"status":"error","message":"Property values were not valid",
 "errors":[{"message":"Property \"visit_date\" does not exist",
   "code":"PROPERTY_DOESNT_EXIST",
   "context":{"propertyName":["visit_date"]}}],
 "category":"VALIDATION_ERROR"}
```

`_push_to_hubspot` handles this with a **loop (up to 10 iterations)**:

1. Log the raw 400 body (`CRM 400 response body: ...`).
2. `_rejected_property_from_4xx` extracts the property name — first from
   `errors[0]["context"]["propertyName"][0]`, then regex fallbacks
   (`Property "X" does not exist`, `unknown property: X`, etc.).
3. Strip that property from the payload and retry **once per loop iteration**
   (same POST or PATCH method).
4. Stop when the request succeeds or no more properties are parseable.

The old behavior (strip one property, single retry, then raise) was replaced by
this loop in the 2026-08-18 change set.

### Permanent failure → DLQ

On permanent failure the lead is marked `crm_sync_status = "failed"` and a
`DLQEvent` is written:

```python
DLQEvent(target_endpoint="hubspot_crm", payload=payload,
         error_trace=str(e), status="pending", client_id=lead.client_id)
```

Replay: `python dlq_replay.py` (see `docs/DLQ_REPLAY_PROCESS.md`). Replay calls
`_push_to_hubspot(payload)` with the **stored payload** — if the lead already has
an `external_crm_id`, the re-push PATCHes that contact (idempotent); a replay
without a stored id may still create a new contact, so check by `phone` after
replay.

---

## 7. HubSpot portal setup checklist

1. **Create the contact properties** (Settings → Properties → Contact Properties),
   with internal names exactly matching the snake_case names in § 4:

   | Property | Type |
   |----------|------|
   | `budget` | Single-line text |
   | `location` | Single-line text |
   | `intent` | Single-line text |
   | `property_type` | Single-line text |
   | `visit_date` | Single-line text |
   | `assignee` | Single-line text |
   | `budget_alignment_status` | Single-line text |
   | `urgency_level` | Single-line text |
   | `engagement_score` | Number |
   | `lead_temperature` | Single-line text |

   Type must be "Number" for `engagement_score`; everything else single-line text.
   Internal names are auto-lowercased/snake_cased by HubSpot — keep them verbatim.

2. **Create a Private App** (Settings → Integrations → Private Apps) with the
   scopes from § 2. Copy the access token into `.env`:

   ```env
   CRM_API_KEY=pat-na2-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   FEATURE_HUBSPOT_LIVE=true
   # CRM_SYNC_EXTENDED_PROPERTIES=true   # default true; false = base props only
   ```

3. `CRM_API_URL` defaults to the contacts endpoint — override only if you target
   a different object/portal proxy.

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `400` `PROPERTY_DOESNT_EXIST` for `visit_date` / others | Custom property missing in portal | Create it (§ 7). The strip-loop will drop it until then — data won't sync |
| Duplicate contacts per lead in HubSpot | Pre-fix code always POSTed | Upgrade to current code (PATCH on re-sync); merge existing dupes by `phone` |
| Contact updates take up to ~5 min | `crm_resync_job` interval (by design) | Wait for next tick, or trigger `lead.created`-equivalent event; interval in `main.py` |
| `401` Unauthorized | Wrong/rotated PAT | Follow § 2 step-by-step to regenerate/reveal the token → `.env` → restart API |
| `403` scope error | Token missing contacts write scope | Add `crm.objects.contacts.write` to Private App (§ 2 step 5) — no new token needed |
| `429` rate limit | Too many requests | Tenacity backs off (2s→30s); raise limit / add retry-after handling |
| `external_crm_id` overwritten with a new id | Legacy duplicate path ran before fix | Re-run sync once; new code PATCHes by stored id |
| Status stuck `pending` | phone+name empty at create time | Next field update re-syncs (P5.3) |

### Debugging aids

- Raw HubSpot 400 body is logged: `CRM 400 response body: {...}`.
- Property-strip retries log: `CRM rejected property 'X'; retrying without it.`
- Successful pushes log the external id: `Synced Lead 1 to CRM. External ID: 5367...`

---

## 9. Env reference

| Env var | Default | Purpose |
|---------|---------|---------|
| `CRM_API_URL` | `https://api.hubapi.com/crm/v3/objects/contacts` | HubSpot contacts endpoint |
| `CRM_API_KEY` | `demo-hubspot-key` | Private App token (`Authorization: Bearer`) |
| `FEATURE_HUBSPOT_LIVE` | `false` | `true` + real key → live path; `false` → demo stub (fake UUID) |
| `CRM_SYNC_EXTENDED_PROPERTIES` | `true` | Send the extended property map |
| `IS_PRODUCTION` | `false` | Blocks live push when key is still `demo-hubspot-key` |

> `IS_PRODUCTION=true` + `CRM_API_KEY=demo-hubspot-key` raises
> `RuntimeError` — production safety check.

---

## 10. Verification

```powershell
# Unit tests
pytest tests/test_f4_hubspot_flag.py tests/test_p5_crm.py -v

# Manual end-to-end (TEST_MODE=false, real Twilio sandbox + real HubSpot):
#   send "im <name> i want 2bhk in wakad" → budget → visit date
#   expect in API logs:
#     POST .../contacts "201"   (first push)
#     PATCH .../contacts/<id> "200"  (subsequent field updates)
#   expect exactly ONE contact in HubSpot with all fields filled.
```

Related: `docs/DLQ_REPLAY_PROCESS.md` · `docs/TIMEOUTS_AND_TIMINGS.md` § 8 ·
`docs/MAINTENANCE.md` (integrations table).