# n8n Integration (optional / config-later)

## Purpose

n8n is the **external workflow automation plane** for IREIOS 3.0. It is **not** required for core lead qualification. Use it when business processes leave the real-time chat path:

| Use case | Why n8n (not in-app code) |
|----------|---------------------------|
| Multi-step human approvals outside the dashboard | Visual BPM, email/Slack nodes |
| Nightly CRM hygiene / spreadsheet exports | Cron + connectors without redeploying API |
| Marketing drip beyond WhatsApp follow-up FSM | Channel mix (email, SMS, ads) |
| Partner webhooks (portals, accounting) | Quick connector library |
| Ops alerts to Slack/Teams on `lead.hot` / DLQ depth | Subscribe to Redis Streams or HTTP webhooks |

## Architecture fit

```text
Event Bus (Redis Streams: ireios:events)
    │
    ├─► CEO agents (in-process) — scoring, CRM AE, KG, follow-up arm
    │
    └─► n8n (optional)
          • Redis Streams trigger (same stream/group or dedicated consumer)
          • OR HTTP webhook from AutomationEngine (N8NClient.trigger_workflow)

AutomationEngine
    template_type="n8n"  →  app/automation_engine/n8n_client.py
         → POST {N8N_BASE_URL}/webhook/{workflow_id}
         → header X-N8N-API-KEY
```

When `N8N_BASE_URL` / `N8N_API_KEY` are empty, `N8NClient` returns  
`{"status":"error","error":"n8n_not_configured"}` and **never crashes** the bus.

## Recommended first workflows (when enabling)

Full closeout plan (payloads, lane split, ordered tasks): **`plans/PHASE3_AUTOMATIONS_CLOSEOUT.md`**.

1. **`lead.hot` → Slack** — Redis Streams filter **or** webhook `ireios_hot_lead_slack` (see below). Prefer catalog name `lead.hot`.
2. **`site_visit.scheduled` → Slack/Gmail fan-out** — EE publishes after CalendarExecutor success (do not expect publish inside the executor file). Do **not** double-create Google events if `provider=google_calendar`.
3. **`session.completed` → CRM note** (PR #10 alias) — optional; prefer `lead.qualified` for field upsert.
4. **HITL email/Slack** — on `approval.requested`, manager notify with `/api/v1/approvals/{id}/approve|reject`.
5. **`lead.qualified` → external CRM** (n8n HubSpot/SF nodes) — Python HubSpot portal stays skipped.
6. **Weekly marketing segment** — on `marketing.report.generated`, push CSV to Drive.
7. **DLQ depth alert** — n8n cron if pending `dlq_events` > N.

### What n8n must NOT own

- WhatsApp TwiML race (`WHATSAPP_WEBHOOK_TIMEOUT`, default 12s) / 6-field gate / RAG  
- Follow-up Day0→7 FSM / 10m–30m escalation cron / competitor monitor job  
- Tenant isolation / JWT issuance  
- Treating `lead.escalated` / `session.completed` as separate product events — they are **dual-publish aliases** of catalog signals (see below)

## Dual-publish aliases (PR #10 — n8n bus hooks)

Backend **dual-publishes** catalog + review aliases so n8n names from PR review work without breaking Sales/KG:

| Business signal | Catalog (prefer long-term) | Alias (PR #10 / n8n) | Code |
|-----------------|----------------------------|----------------------|------|
| Hot score or handoff | `lead.hot` (`payload.trigger` = `hot_threshold` \| `human_handoff`) | `lead.escalated` (same payload) | `app/events/lead_hot.py` |
| Session closed (handoff / full qualify) | keep using `lead.qualified` for fields | `session.completed` (+ `chat_context`, `close_reason`) | same module |
| Site visit booked | `site_visit.scheduled` | — (no alias) | **EE** after `CalendarExecutor` (`registry.py`) |

**n8n rule:** subscribe to **one** of `lead.hot` **or** `lead.escalated` per workflow — never both (double Slack). Aliases may be retired later; catalog names stay.

### Out of scope / deferred

| Item | Status |
|------|--------|
| Always-true dummy `GET /calendar/availability` | **Rejected** (lies to n8n). Optional honest freebusy later is not scheduled. |
| `event_bus.publish` inside `calendar_executor.py` | **Not needed** — EE owns success publish (single event). Executor is pure I/O. |
| Dual-path delete of root `agent.py` / `crm_sync.py` / `follow_up.py` (Phase 10.2/10.3) | **Deferred** — shared libraries for v3; not a second product path (`AGENTS.md`). |
| HubSpot Python live portal | Skipped; external CRM via n8n nodes OK. |

## Local Docker (recommended for credentials + webhooks)

```powershell
docker compose up -d n8n
# UI: http://localhost:5678  (create owner email/password on first visit)
```

| Item | Value |
|------|--------|
| Image | `n8nio/n8n` service `n8n` in `docker-compose.yml` |
| UI / API base | `http://localhost:5678` |
| Data volume | `n8ndata` → `/home/node/.n8n` (workflows + credentials survive restart) |
| Encryption key | `N8N_ENCRYPTION_KEY` (compose default for local; set in `.env` for prod) |
| Webhooks | `http://localhost:5678/webhook/<path>` (production URL once workflow is **Active**) |

**Create credentials in the UI**

1. Open http://localhost:5678 → finish owner setup.
2. **Credentials** → add Slack / Gmail / etc. as needed (stored encrypted in the volume).
3. New workflow → **Webhook** node:
   - Method: POST  
   - Path: e.g. `ireios_hot_lead_slack`  
   - Authentication: **Header Auth**  
   - Header name: `X-N8N-API-KEY`  
   - Header value: same string as `.env` `N8N_API_KEY` (e.g. `local-n8n-webhook-secret`)
4. Add Slack (or Set/Respond) node → **Activate** the workflow.
5. Point IREIOS at the instance:

```env
N8N_BASE_URL=http://localhost:5678
N8N_API_KEY=local-n8n-webhook-secret
```

Restart uvicorn after changing `.env`. AE calls  
`POST {N8N_BASE_URL}/webhook/{workflow_id}` with header `X-N8N-API-KEY`.

**From another container** (if API ever runs in Compose): use  
`N8N_BASE_URL=http://n8n:5678` instead of localhost.

## Env

```env
N8N_BASE_URL=http://localhost:5678
# or https://yourname.app.n8n.cloud
N8N_API_KEY=shared-secret-matching-n8n-header-auth
```

## What must stay in IREIOS (not n8n)

- WhatsApp TwiML reply path (12s race + await-inflight; no double Gemini)  
- 6-field qualification gate + RAG  
- Tenant isolation / JWT  
- Follow-up Day0→7 state machine (v3 via AE→EE)  
- Multi-tenant `client_id` enforcement  

n8n is **orchestration around** the OS, not a replacement for the CEO/AE/EE spine.

## Status (post-G3 + BA closeout + PR #10 bus hooks)

| Piece | Status |
|-------|--------|
| Client scaffold | **Shipped** — `app/automation_engine/n8n_client.py` |
| AE `template_type=n8n` dispatch | **Shipped** (Wave A.3) |
| Named template helper | **Shipped** — `hot_lead_notify.py` supports `workflow_id` |
| Docker Compose service | **Shipped** — `n8n` in `docker-compose.yml` → http://localhost:5678 |
| Bus: `lead.hot` + alias `lead.escalated` | **Shipped** — scoring + handoff (`app/events/lead_hot.py`) |
| Bus: `session.completed` | **Shipped** — handoff + full qualify close |
| Bus: `site_visit.scheduled` | **Shipped** — EE success map (not CalendarExecutor) |
| Turn `chat_context` | **Shipped** — `_emit_turn_events` |
| Calendar REST (BA-5) | **Shipped** — `GET/POST /api/v1/calendar/*` (confirm → AE) |
| HITL approve/reject paths | **Shipped** |
| Live n8n **workflows** | **INCOMPLETE** — Maitri activates WF UI |
| Workflows CSV / DLQ | **Not started** |

### Ingest mode (BA-6 locked)

| Mode | Role |
|------|------|
| **Redis Streams on `ireios:events` (primary)** | Filter one of `lead.hot` **or** `lead.escalated` (not both). |
| AE webhook `template_type=n8n` | **Fallback only** when n8n cannot reach Redis. Do not enable both for the same alert. |

### Workflow 1: `ireios_hot_lead_slack`

- Webhook path: `/webhook/ireios_hot_lead_slack`
- Trigger from IREIOS: `template_type="n8n"`, `workflow_id="ireios_hot_lead_slack"`
- Payload shape (example):

```json
{
  "action_type": "notify_agent",
  "tenant_id": "Client_1",
  "entity_id": "42",
  "parameters": { "kind": "hot_lead", "lead_name": "...", "lead_phone": "...", "score": 0.95 },
  "template_type": "n8n",
  "workflow_id": "ireios_hot_lead_slack"
}
```

- n8n side: Webhook (POST) + Header Auth `X-N8N-API-KEY` + Slack (or log-only Set node for smoke)
- Activate workflow before testing

### Workflow 2–3 (recommended later)

- Weekly marketing CSV on `marketing.report.generated`
- DLQ depth alert (cron or stream)

## Canonical payloads (closeout target — backend BA-1…BA-4)

Bus envelope (all events): `event_id`, `event_type`, `tenant_id` (`Client_<id>`), `entity_id`, `source`, `timestamp`, `correlation_id`, `payload`.

### `lead.hot` (notification / escalation — catalog event)

Prefer `lead.hot` + `payload.trigger`. If using the PR #10 alias `lead.escalated`, subscribe to **one** of the two — never both.

```json
{
  "event_type": "lead.hot",
  "tenant_id": "Client_1",
  "entity_id": "123",
  "source": "agent | lead_scoring_handler",
  "payload": {
    "lead_id": 123,
    "session_id": "1_+919999999999",
    "name": "John Doe",
    "phone": "+919999999999",
    "location": "Baner",
    "budget": "80L",
    "property_type": "2BHK",
    "lead_temperature": "hot",
    "conversion_probability": 85,
    "score": 85,
    "trigger": "hot_threshold | human_handoff",
    "reason": "HOT threshold crossed | Explicit human agent requested.",
    "assigned_agent": "Sneha",
    "chat_context": "User: ...\nAgent: ..."
  }
}
```

| Chat / audit wording | What bus emits |
|----------------------|----------------|
| `human.requested` | `lead.hot` + `lead.escalated` with `trigger=human_handoff` |
| `lead.escalated` (as sole name) | Dual-published with `lead.hot` (same payload) — pick one in n8n |
| `session.completed` | Dual-published on close (plus keep `lead.qualified` for fields) |

**Shipped:** `app/events/lead_hot.py` dual-publish + `lead_scoring_handler` (`hot_threshold`) + handoff/qualify-close. Redis debounce 30m per `(client, lead, trigger)`.

### `lead.qualified` (CRM fields + transcript)

Emitted from `main.py` `_emit_turn_events` when 6-field gate complete. Closeout adds `chat_context` (BA-2):

```json
{
  "event_type": "lead.qualified",
  "tenant_id": "Client_1",
  "entity_id": "123",
  "payload": {
    "lead_id": 123,
    "session_id": "1_+919999999999",
    "name": "John Doe",
    "phone": "+919999999999",
    "location": "Baner",
    "budget": "80L",
    "property_type": "2BHK",
    "intent": "buy",
    "lead_temperature": "hot",
    "conversion_probability": 85,
    "chat_context": "User: Hi...\nAgent: Great..."
  }
}
```

### `site_visit.scheduled` (calendar — EE after `CalendarExecutor`)

Python owns Google create when `GOOGLE_CALENDAR_*` set. n8n = invite email / Slack only.

```json
{
  "event_type": "site_visit.scheduled",
  "tenant_id": "Client_1",
  "entity_id": "123",
  "source": "execution_engine",
  "payload": {
    "lead_id": 123,
    "visit_id": "...",
    "visit_date": "2026-08-01T10:00:00+05:30",
    "name": "John Doe",
    "phone": "+919999999999",
    "location": "Baner",
    "provider": "google_calendar | stub",
    "html_link": "https://calendar.google.com/..."
  }
}
```

**Do not** rely on a dummy `GET /api/v1/calendar/availability` that always returns `available: true` without `provider`. Optional authenticated freebusy API is BA-5 only if needed.

### `approval.requested` (HITL)

Already published from `app/automation_engine/hitl.py`. Closeout BA-4 adds relative `approve_path` / `reject_path`.

### `marketing.report.generated`

Shipped from `marketing_agent`. Use for Drive CSV workflow.

## Ingest: Redis Streams vs AE webhook

| Mode | When to use |
|------|-------------|
| **Redis Streams** on `ireios:events` (filter `event_type`) | Preferred for bus-native events (`lead.hot`, `lead.qualified`, `site_visit.scheduled`, …) |
| **Webhook** `POST {N8N_BASE_URL}/webhook/{workflow_id}` + `X-N8N-API-KEY` | When AE submits `template_type=n8n` (e.g. hot_lead template) |

Pick **one primary** per workflow with backend owner to avoid double Slack messages.

## Practicality vs LangGraph

Prefer **n8n** for Slack/email/Drive/partner connectors. Prefer **LangGraph** (or existing HITL pause) for in-process multi-step AI. Do not put WhatsApp TwiML or the 6-field gate in n8n.

## Python email vs n8n email

| Kind | Owner | Purpose |
|------|--------|---------|
| Critical / Twilio failure fallback | Python notification paths | Disaster recovery |
| Business ops (digests, rich HTML, Slack blocks, manager HITL formatting) | n8n | Day-to-day ops routing |
