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

1. **`lead.hot` → Slack** — Redis Streams filter **or** webhook `ireios_hot_lead_slack` (see below). Prefer catalog name `lead.hot`.
2. **`site_visit.scheduled` → Slack/Gmail fan-out** — EE publishes after CalendarExecutor success (do not expect publish inside the executor file).
3. **`session.completed` → CRM note** (PR #10 alias) — optional; prefer `lead.qualified` for field upsert.
4. **DLQ depth alert** — if pending `dlq_events` > N, page on-call.
5. **Weekly marketing segment** — on `marketing.report.generated`, push CSV to Drive.
6. **HITL email** — on `approval.requested`, deep link to `/api/v1/approvals/{id}/approve`.

## Dual-publish aliases (PR #10 — n8n bus hooks)

Backend **dual-publishes** catalog + review aliases so n8n names from PR review work without breaking Sales/KG:

| Business signal | Catalog (prefer long-term) | Alias (PR #10 / n8n) | Code |
|-----------------|----------------------------|----------------------|------|
| Hot score or handoff | `lead.hot` (`payload.trigger` = `hot_threshold` \| `human_handoff`) | `lead.escalated` (same payload) | `app/events/lead_hot.py` |
| Session closed (handoff / full qualify) | keep using `lead.qualified` for fields | `session.completed` (+ `chat_context`, `close_reason`) | same module |
| Site visit booked | `site_visit.scheduled` | — (no alias) | **EE** after `CalendarExecutor` (`registry.py`) |

**n8n rule:** subscribe to **one** of `lead.hot` **or** `lead.escalated` per workflow — never both (double Slack). Aliases may be retired later; catalog names stay.

### Out of scope / deferred (do not re-request on this PR)

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

- WhatsApp 15s TwiML reply path  
- 6-field qualification gate + RAG  
- Tenant isolation / JWT  
- Follow-up Day0→7 state machine (v3 via AE→EE)  
- Multi-tenant `client_id` enforcement  

n8n is **orchestration around** the OS, not a replacement for the CEO/AE/EE spine.

## Status (post-G3 + PR #10 bus hooks)

| Piece | Status |
|-------|--------|
| Client scaffold | **Shipped** — `app/automation_engine/n8n_client.py` |
| AE `template_type=n8n` dispatch | **Shipped** (Wave A.3) |
| Named template helper | **Shipped** — `hot_lead_notify.py` supports `workflow_id` |
| Docker Compose service | **Shipped** — `n8n` in `docker-compose.yml` |
| Bus: `lead.hot` + alias `lead.escalated` | **Shipped** — scoring + handoff (`app/events/lead_hot.py`) |
| Bus: `session.completed` | **Shipped** — handoff + full qualify close |
| Bus: `site_visit.scheduled` | **Shipped** — EE success map (not CalendarExecutor) |
| Turn `chat_context` | **Shipped** — `_emit_turn_events` |
| Live n8n **workflows** | **INCOMPLETE** — Maitri activates WF UI |
| Workflows CSV / DLQ | **Not started** |

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

## Practicality vs LangGraph

Prefer **n8n** for Slack/email/Drive/partner connectors. Prefer **LangGraph** (or existing HITL pause) for in-process multi-step AI. Do not put WhatsApp TwiML or the 6-field gate in n8n.
