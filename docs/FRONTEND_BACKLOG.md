# Frontend Backlog (Post–Backend IREIOS 3.0 + G3)

Backend Waves A–D / Gate G3 are **code-complete**. FE cutover (Expansion Phase 9.3–9.7) is **Mayank-owned**. This file is the live checklist.

**Last reviewed:** 2026-07-30

---

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
| `GET /api/v1/approvals` + approve/reject | JWT | HITL (tenant-scoped) |
| `POST /api/v1/leads/{id}/sales-ai` | JWT | Sales copilot action (also bus-driven backend) |
| `POST /api/v1/chat` | API key | Reply; may include `media_url` after brochure/floorplan turn |
| `POST /api/v1/lifecycle/events` | Admin | Ops inject booking/payment/document events |
| SSE `marketing.report.generated` | stream | Marketing / executive panels |
| SSE `brochure.sent` / `floorplan.sent` | stream | Media share timeline |

Contracts (3.0 SSE): `plans/phase3/IREIOS_3.0_API_SSE_CONTRACTS.md`, OpenAPI `plans/phase3/openapi_ireios3.json`.  
Phase 4 contracts / queue: `plans/phase4/IREIOS_4.0_API_CONTRACTS.md`, `plans/phase4/UNIFIED_EXECUTION_ORDER.md`.  
Backend depth log (3.0): `plans/phase3/IREIOS_3.0_WAVE_A_D_CHANGELOG.md`.

---

## Progress (Mayank)

| Item | Status | Evidence |
|------|--------|----------|
| Real SSE on command-center dashboard | **Partial `[~]`** | `a10aa68` — `dashboard-mvp/page.tsx` uses `EventSource` → `/api/v1/events/stream?api_key=…` |
| Lead timeline API | **Partial `[~]`** | `a10aa68` — `sales-copilot/page.tsx` fetches `/api/v1/events/leads/1/timeline` (hardcoded lead `1` + api_key) |
| Delete / stop using `MockSSEService` | **Open** | Class still in `frontend/src/lib/api/mockService.ts`; not used by dashboard-mvp anymore but file remains |
| Forecast widgets → real predictions API | **Open** | `dashboard-mvp` still seeds KPIs/forecast from `mockForecastData` |
| JWT cookie auth for SSE (not hard-coded api_key) | **Open** | Dev uses `secret-client-key-123` query param |
| Approvals UI | **Open** | Backend ready; no FE list/approve flow confirmed |
| Sales AI button | **Open** | Backend `POST /api/v1/leads/{id}/sales-ai` ready |
| Graph panel | **Open** | Optional |
| Media preview from chat `media_url` | **Open** | Optional |
| Main `(dashboard)` route group vs command-center | **Clarify** | Primary product routes may still differ from MVP pages |

---

## Required FE work (still open)

### 1. Finish MockSSE cutover
- [x] MVP dashboard uses live `EventSource` (not MockSSE)
- [ ] Remove or isolate `MockSSEService` so nothing imports it for prod paths
- [ ] Prefer **HttpOnly `jwt` cookie** + same-origin/proxy (not hard-coded `api_key` in client bundle)
- [ ] Graceful reconnect + ignore SSE `: ping` heartbeats

### 2. Live dashboard pulse (harden)
- [x] Basic mapping: `lead.created`, `lead.scored`, `approval.requested`, `marketing.report.generated`
- [ ] Bind real KPIs from APIs (not artificial `+150000` demo math)
- [ ] Cover: `lead.assigned`, `conversation.updated`, `whatsapp.sent`, `lead.hot`, `site_visit.scheduled`

### 3. Lead timeline (Sales Copilot)
- [x] Calls real timeline endpoint
- [ ] Use **selected lead id** (not hardcoded `1`)
- [ ] Auth via JWT; tenant 404 handling
- [ ] Poll or SSE refresh after new events

### 4. Graph panel (optional)
- [ ] `GET /api/v1/graph/leads/{id}/context` when `available`

### 5. Approvals UI
- [ ] List `GET /api/v1/approvals`; approve / reject (tenant-scoped)

### 6. Sales AI button
- [ ] `POST /api/v1/leads/{id}/sales-ai` → show recommended next action + stage

### 7. Forecast widgets
- [ ] Replace `mockForecastData` with `/api/v1/predictions/*`

### 8. Optional media preview
- [ ] When chat returns `media_url`, show PDF/image link

### 9. Env / proxy
- [ ] `NEXT_PUBLIC_API_URL` → backend; cookie path works for SSE in prod

---

## Out of scope for FE
- Changing bus schema (frozen in Phase 1b)
- Direct Redis / Neo4j access
- Twilio webhooks
- Backend Wave A–D implementation (done)

---

## Acceptance (production FE)
- [ ] `MockSSEService` unused / deleted for shipped routes
- [ ] Dashboard shows live event within 2s of chat/WA message (API up)
- [ ] Timeline loads for **selected owned lead**; 404 for cross-tenant
- [ ] No console errors on SSE disconnect/reconnect
- [ ] Forecast widgets not using hardcoded mock revenue only
- [ ] No hard-coded `secret-client-key-123` in client source
