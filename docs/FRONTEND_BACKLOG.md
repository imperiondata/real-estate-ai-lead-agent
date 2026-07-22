# Frontend Backlog (Post–Backend IREIOS 3.0 + G3)

Backend Waves A–D / Gate G3 are **code-complete**. FE cutover (Expansion Phase 9.3–9.7) remains **Mayank-owned**. This file is the checklist for that work.

## Already available from backend

| Endpoint / signal | Auth | Purpose |
|-------------------|------|---------|
| `GET /api/v1/events/stream` | API key query **or** `jwt` cookie | SSE envelopes (tenant-filtered) |
| `GET /api/v1/events/leads/{id}/timeline` | API key / JWT | Envelope list for Sales Copilot |
| `POST /api/v1/events/stub` | `X-Admin-Token` | Demo inject (dev only) |
| `GET /api/v1/leads/{id}/score` | JWT | Score breakdown |
| `GET /api/v1/leads/{id}/prediction` | JWT | Conversion / closure |
| `GET /api/v1/predictions/revenue` | JWT | Heuristic revenue forecast |
| `GET /api/v1/predictions/cancellation-risk` | JWT | At-risk style cancel proxy |
| `GET /api/v1/predictions/inventory` | JWT | Inventory unit counts |
| `GET /api/v1/predictions/cashflow` | JWT | Heuristic cashflow slice |
| `GET /api/v1/graph/leads/{id}/context` | API key / JWT | Neo4j similar leads |
| `GET /api/v1/approvals` + approve/reject | JWT | HITL |
| `POST /api/v1/leads/{id}/sales-ai` | JWT | Sales copilot action (also bus-driven backend) |
| `POST /api/v1/chat` | API key | Reply; may include `media_url` after brochure/floorplan turn |
| `POST /api/v1/lifecycle/events` | Admin | Ops inject booking/payment/document events |
| SSE `marketing.report.generated` | stream | Marketing / executive panels |
| SSE `brochure.sent` / `floorplan.sent` | stream | Media share timeline |

Contracts: `plans/IREIOS_3.0_API_SSE_CONTRACTS.md`, OpenAPI `plans/openapi_ireios3.json`.  
Backend depth log: `plans/IREIOS_3.0_WAVE_A_D_CHANGELOG.md`.

## Required FE work (still open)

### 1. Remove MockSSEService
- File: `frontend/src/lib/api/mockService.ts` (`MockSSEService`)
- Replace with `EventSource` (or fetch-stream) against  
  `${NEXT_PUBLIC_API_URL}/api/v1/events/stream`  
- Auth: prefer **cookie JWT** (HttpOnly `jwt`) so EventSource works same-origin / proxy.
- If cross-origin: Next.js rewrite proxy that attaches cookie, or `?api_key=` only in dev.

### 2. Live dashboard pulse
- Bind KPI / activity widgets to SSE `event_type` filters:  
  `lead.created`, `lead.scored`, `lead.assigned`, `conversation.updated`, `whatsapp.sent`, `approval.requested`, `marketing.report.generated`
- Graceful reconnect + `: ping` ignore

### 3. Lead timeline (Sales Copilot)
- `GET /api/v1/events/leads/{id}/timeline` → replace static/mock timeline
- Render envelope: `event_type`, `timestamp`, `payload` summary

### 4. Graph panel (optional but recommended)
- `GET /api/v1/graph/leads/{id}/context` when `available`

### 5. Approvals UI
- List pending from `GET /api/v1/approvals`; approve / reject

### 6. Sales AI button
- `POST /api/v1/leads/{id}/sales-ai` → show recommended next action + stage

### 7. Forecast widgets
- Replace `mockForecastData` with `/api/v1/predictions/*` (heuristic MVP)

### 8. Optional media preview
- When chat returns `media_url`, show PDF/image link in UI

### 9. Env / proxy
- `NEXT_PUBLIC_API_URL` → backend; cookie path works for SSE

## Out of scope for FE
- Changing bus schema (frozen in Phase 1b)
- Direct Redis / Neo4j access
- Twilio webhooks
- Backend Wave A–D implementation (done)

## Acceptance
- [ ] `MockSSEService` unused / deleted
- [ ] Dashboard shows live event within 2s of chat/WA message (with API up)
- [ ] Timeline loads for owned lead; 404 for cross-tenant
- [ ] No console errors on SSE disconnect/reconnect
- [ ] Forecast widgets not using hardcoded mock revenue only
