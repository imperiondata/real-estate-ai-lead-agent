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

1. **`lead.hot` → Slack** — webhook `ireios_hot_lead_slack` (see below).
2. **DLQ depth alert** — if pending `dlq_events` > N, page on-call.
3. **Weekly marketing segment** — on `cron.weekly_report` / `marketing.report.generated`, push CSV to Drive.
4. **HITL email** — on `approval.requested`, email manager with deep link to `/api/v1/approvals/{id}/approve`.

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

## Status (post-G3 + audit 2026-07-22)

| Piece | Status |
|-------|--------|
| Client scaffold | **Shipped** — `app/automation_engine/n8n_client.py` |
| AE `template_type=n8n` dispatch | **Shipped** (Wave A.3) — `engine.py` branches; fallback linear / `fallback_action` |
| Named template helper | **Shipped** — `hot_lead_notify.py` supports `workflow_id` |
| Docker Compose service | **Shipped** — `n8n` in `docker-compose.yml` → http://localhost:5678 |
| Live n8n **instance** | **Running** when `docker compose up -d n8n` (audit: HTTP 200) |
| Live n8n **workflows** | **INCOMPLETE** — create owner account, activate webhook + Header Auth; until then AE trigger returns `n8n_http_404` |
| Workflows 2–3 (CSV / DLQ) | **Not started** |

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
