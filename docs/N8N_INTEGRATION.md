# n8n Integration (Future / Config-Later)

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

1. **`lead.hot` → Slack** — consume bus or poll `GET /api/v1/cs/at-risk`; notify sales channel.
2. **DLQ depth alert** — if pending `dlq_events` > N, page on-call.
3. **Weekly marketing segment** — on `cron.weekly_report` / `marketing.report.generated`, push CSV to Drive.
4. **HITL email** — on `approval.requested`, email manager with deep link to `/api/v1/approvals/{id}/approve`.

## Env

```env
N8N_BASE_URL=https://n8n.example.com
N8N_API_KEY=...
```

## What must stay in IREIOS (not n8n)

- WhatsApp 15s TwiML reply path  
- 6-field qualification gate + RAG  
- Tenant isolation / JWT  
- Follow-up Day0→7 state machine (v3 via AE→EE)  
- Multi-tenant `client_id` enforcement  

n8n is **orchestration around** the OS, not a replacement for the CEO/AE/EE spine.

## Status

- Client scaffold: **shipped** (`app/automation_engine/n8n_client.py`)
- AE `template_type=n8n` dispatch: **shipped** (Wave A.3) — `engine.py` branches on `template_type`, calls `N8NClient.trigger_workflow` or falls back to linear EE.
- **Workflow 1: `ireios_hot_lead_slack`** — webhook path `/webhook/ireios-hot-lead-slack`.
  Trigger: `template_type="n8n"`, `workflow_id="ireios_hot_lead_slack"` from `hot_lead_notify.py` template.
  Payload:
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
  Action: Post to sales Slack channel.
- **Workflow 2 (recommended): Weekly marketing CSV** — subscribe to `marketing.report.generated` via n8n Redis Streams trigger or HTTP webhook from marketing_agent optional second publish. Push CSV to Google Drive / email.
- **Workflow 3 (recommended): DLQ depth alert** — cron in n8n polling `GET /api/v1/admin/dlq-count` (admin-gated) or subscribe to Redis Streams DLQ events. Alert ops if count > threshold.
- **Live workflows: not provisioned** — webhook endpoints are accepted by n8n but the instance is not stood up yet. Deploy as part of Wave D.3 config-later.
- **Owner:** backend ops when first workflow is approved

## Practicality vs LangGraph

Prefer **n8n** for Slack/email/Drive/partner connectors. Prefer **LangGraph** (or existing HITL pause) for in-process multi-step AI. Do not put WhatsApp TwiML or the 6-field gate in n8n. Full decision table: Wave plan §0.3 Q1.
