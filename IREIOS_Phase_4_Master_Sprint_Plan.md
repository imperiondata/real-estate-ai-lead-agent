# IREIOS Phase 4 — Master Sprint Plan & Execution Matrix

> **Operational plans (authoritative for engineering):** [`plans/phase4/`](plans/phase4/)  
> **Lead decisions required:** [`plans/phase4/TEAM_LEAD_QUESTIONNAIRE.md`](plans/phase4/TEAM_LEAD_QUESTIONNAIRE.md)  
> **Archived IREIOS 3.0 plans:** [`plans/phase3/`](plans/phase3/)
>
> **Baseline audit (2026-08-07):** Several claims below are **incorrect or overstated** relative to the live codebase (e.g. “Current Progress: 0%”, “models trained”, LangGraph-in-n8n Sales AI, bi-directional HubSpot complete, Week-1 Neo4j/Prediction APIs as greenfield blockers). Full claim-by-claim table is questionnaire **§F**. Do not treat §6 0% or the dependency matrix as engineering truth until the lead re-baselines.
>
> **Naming:** This is **Product Phase 4 / IREIOS 4.0**. It is distinct from already-shipped Bug Phase 4 (notifications) and Expansion Phase 4 (follow-up AE→EE) in `plans/phase3/`.

## 1. Sprint Milestones & Strict Delivery Dates

4-week compressed execution timeline. **Deviation from these milestones is strictly prohibited.**

### Week 1 — Backend Foundation
- **Aritro**: Neo4j Knowledge Graph schemas and ingestion APIs completed and deployed to staging.
- **Aritro**: Forecast Engine (Prediction APIs) — models trained and serving endpoints finalized.
- **Maitri**: Marketing AI routing workflows finalized on the automation plane.

### Week 2 — Integration & UI Completion
- **Aritro**: HubSpot CRM backend integration complete and fully exposed.
- **Maitri**: Sales AI logic (Next Best Action) deployed; HubSpot CRM automation workflows fully wired.
- **Mayank**: All frontend UI dependencies completed and integrated with live APIs (Graph Visualization, Forecast Widgets, Digital Twin MVP UI, Sales AI Button).

### Week 3 — QA & Testing
- Hard code freeze. Zero new development permitted.
- Internal QA and end-to-end integration testing across all full-stack layers.
- Pilot Release Candidate (RC1) cut and validated against the production database.

### Week 4 — Production Release
- Phase 4 MVP Production Release formally deployed to the main environment.
- Final telemetry validation and stability monitoring.

---

## 2. Task Ownership & Definition of Done (DoD)

### Mayank — Frontend Lead

| Task | Definition of Done |
|---|---|
| Knowledge Graph Visualization | Interactive Neo4j graph UI fully rendered, accepts real-time node updates without blocking the main thread, correctly parses Aritro's Week 1 API payload. Zero console errors. |
| Predictive Forecast Widgets | Dashboard widgets accurately reflect prediction data streams, dynamically updating based on CRM state changes. |
| Digital Twin MVP UI | Base MVP shell deployed and responsive, seamlessly communicating with mocked/stubbed endpoints or the core event bus as dictated by backend availability. |
| Sales AI Button | Action button active on the lead entity; successfully triggers Maitri's Next Best Action payload and renders the actionable response in the UI with strict error boundaries. |

### Aritro — Backend Lead

| Task | Definition of Done |
|---|---|
| Neo4j Knowledge Graph schema/APIs | Base schema constraints enforced. Ingestion APIs fully tested under concurrent load and integrated with the Redis Event Bus. Endpoints document standard HTTP response codes and return valid JSON structures for Mayank's UI. |
| Forecast Engine (Prediction APIs) | ML scoring algorithms deployed. API endpoints securely authenticated, fully documented via OpenAPI, capable of returning predictions within a strict 200ms latency SLA. |
| HubSpot CRM integration | Bi-directional webhook/API sync established. Validated mapping of all core CRM fields with comprehensive retry logic and DLQ (Dead Letter Queue) handling for failed syncs. |

### Maitri — AI Automation Lead

| Task | Definition of Done |
|---|---|
| Sales AI Logic (Next Best Action) | LangGraph reasoning agents deployed to the n8n orchestrator. Logic correctly ingests user state and outputs a deterministic, secure Next Best Action payload to the Event Bus. |
| Marketing AI Routing | Automated routing algorithms mapped in n8n. Inbound leads successfully assigned and escalated based on predictive engagement scores with zero routing dead-ends. |
| HubSpot CRM Automation Logic | n8n operational workflows actively listening to Event Bus triggers (`lead.escalated`, etc.) and executing Aritro's HubSpot APIs with verified idempotency. |

---

## 3. Dependency Matrix

| Dependent Task | Owner | Blocked By | Blocking Owner | Clears By |
|---|---|---|---|---|
| Knowledge Graph Visualization UI | Mayank | Neo4j APIs | Aritro | End of Week 1 |
| Predictive Forecast Widgets | Mayank | Prediction APIs | Aritro | Week 1 |
| Sales AI Logic | Maitri | Prediction APIs (predictive heuristic data for routing) | Aritro | Week 1 |
| HubSpot Automation Logic | Maitri | HubSpot CRM Integration APIs | Aritro | Week 2 |
| Sales AI Button | Mayank | Sales AI Logic (payload structure lock) | Maitri | Week 2 |

---

## 4. Risk Assessment & Mitigation Plan

**Critical Risk**: Compressing a 5-week integration schedule into a 4-week window poses severe stability risks, specifically cascading backend bottlenecks centered on Aritro.

**Mitigations:**
1. **Contract-First Development** — Aritro must publish strict, mocked API contracts (Swagger/OpenAPI JSON stubs) on Day 1 of Week 1. Mayank and Maitri build against these mocks. If final APIs deviate from the Day 1 contract, Aritro is solely responsible for writing translation layers.
2. **Parallelization** — No developer is permitted to wait for a live endpoint. Dependency blocking is theoretical with respect to final integration; development must proceed against stubs immediately.
3. **Ruthless Triage** — Any feature threatening the Week 3 QA hard freeze will be feature-flagged off for the MVP release. Stability supersedes scope.

---

## 5. Production Readiness Checklist (Week 3 QA)

- [ ] All Week 1 & 2 tickets closed, merged, and deployed to Staging.
- [ ] Zero High or Critical severity bugs in the tracker.
- [ ] Full end-to-end integration test executed successfully across all UI layers and n8n automations.
- [ ] Redis Event Bus telemetry verified with simulated concurrent stress tests.
- [ ] Neo4j Knowledge Graph queries executing under the 200ms threshold.
- [ ] Frontend CI/CD build passing with Exit Code 0 (zero linting errors, zero TypeScript errors).
- [ ] Production rollout runbook documented and approved by the Technical Lead.

---

## 6. Project Status & Release Metrics

- **Current Progress**: ~~0% (Sprint Day 1)~~ — **DISPUTED by engineering baseline (2026-08-07).** Backend already includes Neo4j v1 + graph APIs, Sales AI NBA + `POST .../sales-ai`, heuristic prediction APIs, CRM outbound+DLQ, marketing/CS agents, bus/SSE, n8n bridge. FE shells exist but are largely mock-wired; Sales AI button and live forecast/graph/twin cutover remain open. See `plans/phase4/TEAM_LEAD_QUESTIONNAIRE.md` §F and `plans/phase4/IREIOS_4.0_IMPLEMENTATION_PLAN.md` §1. **Lead must re-baseline % before exec reporting.**
- **Overall Project Completion**: 70% (sprint figure — directionally OK; confirm weighting BE/FE/ops). Justified in part by Redis Event Bus, Next.js dashboard, and n8n integrations — not by “Phase 4 not started.”
- **Expected Phase 4 Release Date**: September 3, 2026 (Phase 4 MVP Production Release) — confirm in questionnaire Q0.
