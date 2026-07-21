# Frontend Backlog (Post–Backend IREIOS 3.0)

Backend contracts for realtime + timeline are live. FE cutover (Expansion Phase 9.3–9.7) remains **Mayank-owned**. This file is the checklist for that work.

## Already available from backend

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `GET /api/v1/events/stream` | API key query **or** `jwt` cookie | SSE envelopes (tenant-filtered) |
| `GET /api/v1/events/leads/{id}/timeline` | API key / JWT | Envelope list for Sales Copilot |
| `POST /api/v1/events/stub` | `X-Admin-Token` | Demo inject (dev only) |
| `GET /api/v1/leads/{id}/score` | JWT | Score breakdown |
| `GET /api/v1/leads/{id}/prediction` | JWT | Conversion / closure |
| `GET /api/v1/graph/leads/{id}/context` | API key / JWT | Neo4j similar leads |
| `GET /api/v1/approvals` + approve/reject | JWT | HITL |
| `POST /api/v1/leads/{id}/sales-ai` | JWT | Sales copilot action |

Contracts: `plans/IREIOS_3.0_API_SSE_CONTRACTS.md`, OpenAPI `plans/openapi_ireios3.json`.

## Required FE work

### 1. Remove MockSSEService
- File: `frontend/src/lib/api/mockService.ts` (`MockSSEService`)
- Replace with `EventSource` (or fetch-stream) against  
  `${NEXT_PUBLIC_API_URL}/api/v1/events/stream`  
  Auth: browser cannot set custom headers on `EventSource` easily — prefer **cookie JWT** (already HttpOnly `jwt`) so EventSource works same-origin / proxy.
- If cross-origin: Next.js rewrite proxy that attaches cookie, or use `?api_key=` only in dev.

### 2. Live dashboard pulse
- Bind KPI / activity widgets to SSE `event_type` filters:  
  `lead.created`, `lead.scored`, `lead.assigned`, `conversation.updated`, `whatsapp.sent`, `approval.requested`
- Graceful reconnect + `: ping` ignore

### 3. Lead timeline (Sales Copilot)
- `GET /api/v1/events/leads/{id}/timeline` → replace static/mock timeline
- Render envelope: `event_type`, `timestamp`, `payload` summary

### 4. Graph panel (optional but recommended)
- `GET /api/v1/graph/leads/{id}/context` when `available`
- Show “similar demand in this micro-market” without PII of other leads

### 5. Approvals UI
- List pending from `GET /api/v1/approvals`
- Approve / reject actions

### 6. Sales AI button
- `POST /api/v1/leads/{id}/sales-ai` → show recommended next action + stage

### 7. Env / proxy
- `NEXT_PUBLIC_API_URL` → backend
- Ensure cookie path works for SSE (same site)

## Upcoming backend APIs (Wave A–D — do not block current cutover)

Backend depth-fill plan: `plans/IREIOS_3.0_WAVE_A_D_EXPANSION.md`. When shipped, FE can later bind:

| API / event | Wave | FE use |
|-------------|------|--------|
| `marketing.report.generated` (SSE) | A–B | Marketing / executive panels |
| Lifecycle inject is admin-only | A | Optional ops tools |
| Sales auto-NBA still exposes `POST .../sales-ai` | B | Copilot button (already listed) |
| `GET /api/v1/predictions/revenue` etc. | D | Replace `mockForecastData` |
| `GET /api/v1/inventory/match` | C | Twin / inventory widgets |
| Approvals already live | — | HITL UI |

## Out of scope for FE
- Changing bus schema (frozen in Phase 1b)
- Direct Redis / Neo4j access
- Twilio webhooks
- Implementing Wave A–D backend (backend-owned)

## Acceptance
- [ ] `MockSSEService` unused / deleted
- [ ] Dashboard shows live event within 2s of chat/WA message (with API up)
- [ ] Timeline loads for owned lead; 404 for cross-tenant
- [ ] No console errors on SSE disconnect/reconnect
