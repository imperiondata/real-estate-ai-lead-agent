# IREIOS 4.0 — Evidence pack

| This doc owns | Does not own |
|---|---|
| Gate checkboxes + smoke proof for Product Phase 4 | 3.0 G2/G3 evidence → `../phase3/IREIOS_3.0_EVIDENCE_PACK.md` |

**Status legend:** `[ ]` · `[~]` · `[x]` · `[-]` (reason) · `[?]` blocked on lead

---

## Baseline (P4-0) — already true in codebase before Phase 4 coding

### Backend shipped (do not re-count as greenfield)

- [ ] Event bus + CEO + AE + EE on real traffic (3.0 G2)
- [ ] `POST /api/v1/leads/{id}/sales-ai` + bus SalesAgent NBA
- [ ] Neo4j schema v1 + `/api/v1/graph/health|leads/{id}/context|upsert` + reply-path context
- [ ] Heuristic `/api/v1/predictions/*` + per-lead prediction
- [ ] CRM outbound path + DLQ `hubspot_crm` (portal often skipped)
- [ ] Marketing agent + segments + n8n bridge + WF recipes (ops may lag WF-1)
- [ ] SSE `/api/v1/events/stream` + lead timeline

### Frontend partial

- [ ] Command-center shells exist (graph, twin, dashboard-mvp, sales-copilot)
- [ ] Product `(dashboard)` live leads/CRM/analytics
- [ ] Sales AI button **missing**
- [ ] Forecast widgets still mock
- [ ] Graph/twin still mock
- [ ] Hard-coded api_key still present on some SSE/timeline calls

### Sprint doc corrections logged

- [ ] “0% progress” flagged false for backend (questionnaire §F)
- [ ] Dependency blockers flagged where APIs already exist
- [ ] LangGraph-in-n8n / trained-ML / bi-di HubSpot claims flagged vs code

**P4-0 exit:** all baseline boxes reviewed with lead or tech owner initials: ________ date: ________

---

## Contracts (P4-1)

- [ ] `sales-ai` response keys FROZEN
- [ ] predictions keys FROZEN + heuristic disclaimer agreed
- [ ] neighborhood contract FROZEN or CUT
- [ ] twin contract FROZEN or CUT
- [ ] `openapi_ireios4.json` regenerated after code (post P4-2/3)

---

## Graph (P4-2)

- [ ] Neighborhood endpoint tenant-scoped
- [ ] Neo4j down → soft empty JSON
- [ ] pytest `test_f4_graph*` green
- [ ] Latency note (target 200ms): ________ measured: ________
- [ ] Schema stretch (Project/Tower/…) `[x]` / `[-]` reason: ________

---

## Twin (P4-3)

- [ ] Twin layout endpoint tenant-scoped
- [ ] Seed script for demo tenant
- [ ] pytest `test_f4_twin*` green
- [ ] FE empty-state verified

---

## HubSpot (P4-4)

- [ ] Scope recorded: A outbound / B bi-di / C n8n / D defer
- [ ] If live: sandbox contact proof (screenshot/link)
- [ ] DLQ drill green if outbound live
- [ ] Inbound signature tests if B
- [ ] If D: written reason in UNIFIED

---

## Frontend (P4-5…P4-9)

- [ ] Sales AI button on agreed surfaces
- [ ] Forecast from live predictions API
- [ ] Graph wired or explicitly mock-accepted
- [ ] Twin wired or explicitly mock/deferred
- [ ] No `secret-client-key-123` in client source (grep clean)
- [ ] MockSSE unused on shipped routes
- [ ] Timeline uses selected lead id
- [ ] `npm run lint` exit 0
- [ ] `docs/FRONTEND_BACKLOG.md` acceptance section updated

---

## Ops (P4-10)

- [ ] No unauthorized n8n NBA/FSM ownership
- [ ] Only agreed WF deltas smoked
- [ ] WF-1 status (from 3.0 G4): ________

---

## G5 — Phase 4 MVP gate

- [ ] All required UNIFIED steps `[x]` or `[-]` with reason
- [ ] `pytest tests/ -q` (or agreed matrix) green — log: ________
- [ ] `python gate_isolation_test.py` green
- [ ] DLQ drill (+ replay if needed) green or N/A
- [ ] FE lint green
- [ ] Q12 demos on staging signed
- [ ] Zero High/Critical bugs
- [ ] Feature flags documented for anything slipped

**G5 sign-off:** ________ date: ________

---

## QA freeze / RC1 (P4-QA)

- [ ] Hard freeze start date honored
- [ ] RC1 tag/commit: ________
- [ ] E2E across UI + automations
- [ ] Prod DB test policy followed (Q8.3)
- [ ] Rollout runbook approved

---

## Production (P4-REL)

- [ ] `IS_PRODUCTION=true`, `TEST_MODE=false`, follow-up test flags off
- [ ] Real Twilio / optional Neo4j / n8n / CRM keys
- [ ] Telemetry watch window: ________
- [ ] Incident owner: ________

---

## Deferred (explicit)

| Item | Reason | Owner | Target |
|---|---|---|---|
| | | | |
