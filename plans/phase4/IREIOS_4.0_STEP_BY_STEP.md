# IREIOS 4.0 — Step-by-step tasks

| This doc owns | Does not own |
|---|---|
| Atomic tasks: Files / Steps / Test / Done / Rollback | Order → `UNIFIED_EXECUTION_ORDER.md` |
| | Lead decisions → `TEAM_LEAD_QUESTIONNAIRE.md` |

**Status legend:** `[ ]` · `[~]` · `[x]` · `[-]` · `[?]` = blocked on lead  
**Test prefix:** `tests/test_f4_*.py`

Fill concrete schemas after questionnaire returns. Items marked ⚠ stay high-level until then.

---

## P4-0 — Baseline audit

### Task P4-0.1 — Inventory vs sprint
- **Files:** Evidence Pack baseline; optional note in root sprint header
- **Steps:**
  1. Confirm shipped matrix (Sales AI, graph context, predictions, CRM outbound, n8n bridge).
  2. List false claims from sprint (see questionnaire §F).
  3. Freeze non-goals in Implementation Plan §2.
- **Test:** N/A (doc)
- **Done:** Evidence Pack § Baseline all checked; UNIFIED P4-0 → `[x]`
- **Rollback:** N/A
- **Status:** `[ ]`

---

## P4-1 — Contract freeze

### Task P4-1.1 — Capture live OpenAPI for shipped routes
- **Files:** `openapi_ireios4.json` (regen); `IREIOS_4.0_API_CONTRACTS.md` §0
- **Steps:**
  1. Run API locally; dump `/openapi.json`.
  2. Document exact `sales-ai` + predictions response keys.
  3. Mark §0 `FROZEN` after Mayank ack.
- **Test:** Contract smoke curls in API_CONTRACTS §5 (shipped routes only)
- **Done:** §0 FROZEN; no FE blocked on unknown keys
- **Rollback:** Revert contract doc only
- **Status:** `[ ]`

### Task P4-1.2 — Freeze proposed neighborhood + twin shapes ⚠
- **Files:** `IREIOS_4.0_API_CONTRACTS.md` §1–2
- **Steps:** Apply lead Q5/Q6 answers; mark FROZEN or CUT.
- **Test:** N/A
- **Done:** FE can mock against frozen JSON
- **Status:** `[?]`

---

## P4-2 — Graph neighborhood API ⚠ Q5

### Task P4-2.1 — Implement neighborhood endpoint
- **Files (expected):** `app/knowledge_graph/graph_api.py`, `neo4j_kg.py` / read helpers, `tests/test_f4_graph_neighborhood.py`
- **Steps:**
  1. Add JWT tenant-scoped `GET .../neighborhood`.
  2. Map Neo4j Lead/Agent (+ stretch units) → `{nodes,edges}`.
  3. Soft-fail when Neo4j down (`available: false`).
  4. Optional: PG hydrate names/scores like event writers.
- **Test:** `pytest tests/test_f4_graph_neighborhood.py -v`; isolation if queries touch client_id
- **Done:** Contract §1 satisfied; p95 smoke noted in Evidence Pack
- **Rollback:** Feature-flag route off; FE keeps mock
- **Status:** `[?]`

### Task P4-2.2 — Schema stretch (only if lead Q5=B)
- **Files:** `neo4j_client.migrate_schema`, writers, seed
- **Status:** `[?]`

---

## P4-3 — Twin inventory API ⚠ Q6

### Task P4-3.1 — Layout endpoint + seed
- **Files (expected):** new router or `app/api/inventory.py`, model usage `InventoryUnit`, `seed_*.py`, `tests/test_f4_twin.py`
- **Steps:**
  1. Define grouping (project/tower/floor) from existing columns or additive columns ⚠ lead.
  2. `GET /api/v1/inventory/twin` client-scoped.
  3. Seed script for demo tenant (Client_1).
  4. Wire counts consistency with `/predictions/inventory` where possible.
- **Test:** `pytest tests/test_f4_twin.py -v`
- **Done:** Seeded tenant returns ≥1 tower with units; empty tenant → empty towers[]
- **Rollback:** Flag route; FE mock
- **Status:** `[?]`

---

## P4-4 — HubSpot track ⚠ Q2

### Task P4-4.1 — Decision record
- **Files:** Evidence Pack HubSpot section; `.env.example` notes only if needed
- **Steps:** Apply Q2 A/B/C/D; if D mark UNIFIED `[-]` with reason.
- **Status:** `[?]`

### Task P4-4.2 — Live outbound (if A or B)
- **Files:** `crm_sync.py` config only if mapping changes; no chat-path `sync_lead_to_crm` calls
- **Steps:** Real `CRM_API_*`; portal property create; drill `gate_dlq_drill` + replay
- **Done:** One real contact upsert in sandbox/prod portal
- **Status:** `[?]`

### Task P4-4.3 — Inbound webhook (if B only)
- **Files:** new route, signature verify, tests `test_f4_hubspot_inbound.py`
- **Steps:** ⚠ full design from Q2.4–2.6
- **Status:** `[?]`

### Task P4-4.4 — n8n HubSpot node (if C only)
- **Files:** `n8n_workflows/*`, `docs/N8N_INTEGRATION.md`
- **Status:** `[?]`

---

## P4-5 — FE Sales AI button

### Task P4-5.1 — CRM + Leads button
- **Files (expected):** `frontend/src/app/(dashboard)/crm/KanbanBoard.tsx`, `leads/LeadsTable.tsx`, small API helper
- **Steps:**
  1. JWT fetch `POST /api/v1/leads/{id}/sales-ai`.
  2. Loading + error boundary; render action/rationale/scores/stage.
  3. Optional: refresh lead row after success.
- **Test:** Manual + `npm run lint`
- **Done:** No mock NBA on these surfaces; works on seeded lead
- **Rollback:** Hide button behind flag
- **Status:** `[ ]`

### Task P4-5.2 — Sales copilot wire
- **Files:** `frontend/src/app/(command-center)/sales-copilot/page.tsx`
- **Steps:** Selected lead id (not hardcoded `1`); call sales-ai; timeline JWT
- **Done:** FRONTEND_BACKLOG §6 + timeline §3
- **Status:** `[ ]`

---

## P4-6 — FE Forecast widgets

### Task P4-6.1 — Replace mockForecastData
- **Files:** `dashboard-mvp/page.tsx`, optional product `dashboard/page.tsx` / Charts, `mockService.ts`
- **Steps:**
  1. Fetch `/predictions/revenue|cashflow|inventory|cancellation-risk`.
  2. Map to existing cards/charts.
  3. Remove demo `+150000` SSE math for KPIs where replaced by APIs.
  4. Label UI as estimate/heuristic if required by Q1.
- **Test:** lint; manual network tab
- **Done:** FRONTEND_BACKLOG §7; no hardcoded mock revenue as sole source
- **Status:** `[ ]`

---

## P4-7 — FE Graph panel ⚠ depends P4-2

### Task P4-7.1 — Wire knowledge-graph page
- **Files:** `knowledge-graph/page.tsx`, `GraphWrapper.tsx`, replace/retire `mockGraphService` prod path
- **Steps:** JWT fetch neighborhood; empty/unavailable states; filter UI keeps working
- **Done:** Sprint Mayank graph DoD (live payload, no console errors)
- **Status:** `[?]`

---

## P4-8 — FE Digital Twin ⚠ depends P4-3

### Task P4-8.1 — Wire R3F to twin API
- **Files:** `digital-twin/page.tsx`, `mockTwinService.ts`
- **Steps:** Fetch twin layout; status colors; hide sold if existing UX; empty state
- **Done:** Seeded demo renders real unit ids/statuses
- **Status:** `[?]`

---

## P4-9 — FE SSE / JWT harden

### Task P4-9.1 — Remove hard-coded api_key from client
- **Files:** `dashboard-mvp/page.tsx`, `sales-copilot/page.tsx`, any EventSource callers
- **Steps:** Cookie/same-origin pattern; reconnect; ignore `: ping`
- **Done:** FRONTEND_BACKLOG acceptance; grep client src has no `secret-client-key-123`
- **Status:** `[ ]`

### Task P4-9.2 — MockSSE quarantine
- **Files:** `frontend/src/lib/api/mockService.ts`
- **Steps:** Delete or move under `__mocks__` / dev-only; no prod imports
- **Status:** `[ ]`

### Task P4-9.3 — Command-center auth parity ⚠ Q7.2
- **Files:** `frontend/src/proxy.ts` (middleware)
- **Steps:** If lead Yes — guard command-center routes like dashboard
- **Status:** `[?]`

---

## P4-10 — Ops / n8n ⚠ Q4

### Task P4-10.1 — Only lead-requested WF deltas
- **Default:** no code if Q4 says accept Python routing
- **Status:** `[?]`

---

## G5 — Phase 4 MVP gate

### Task G5.1 — Gate run
- **Steps:**
  1. `pytest tests/ -q` (or agreed subset + all `test_f4_*`)
  2. `python gate_isolation_test.py`
  3. `python gate_dlq_drill.py` (+ replay if HubSpot live)
  4. `cd frontend && npm run lint`
  5. Manual demos Q12
  6. Evidence Pack G5 all `[x]` or `[~]` with owner
- **Done:** UNIFIED G5 → `[x]`
- **Status:** `[ ]`

---

## P4-QA / P4-REL

### Task QA.1 — Hard freeze
- Zero new features; bugfix only; RC1 cut
- **Status:** `[ ]`

### Task REL.1 — Production
- Flip go-live env flags per AGENTS checklist; runbook; telemetry watch
- **Status:** `[ ]`
