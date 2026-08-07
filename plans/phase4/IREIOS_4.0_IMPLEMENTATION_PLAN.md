# IREIOS 4.0 — Implementation Plan (macro)

| This doc owns | Does not own |
|---|---|
| Frozen decisions, phase overview, target surfaces, risks | Atomic steps → `IREIOS_4.0_STEP_BY_STEP.md` |
| Corrected program baseline | 3.0 file tree history → `../phase3/IREIOS_3.0_IMPLEMENTATION_PLAN.md` |

**Status:** Draft defaults · **confirm via** `TEAM_LEAD_QUESTIONNAIRE.md`  
**Spine unchanged:** `Event → CEO → Agent/Workflow → AE → EE → Event`

---

## 1. What Product Phase 4 is

**Product Phase 4** (this folder) is **not**:

- Bug Phase 4 (P4.1–P4.3 notifications) — already `[x]` in `../phase3/`
- Expansion Phase 4 (follow-up AE→EE) — already `[x]`

It **is** the 4-week sprint in `../../IREIOS_Phase_4_Master_Sprint_Plan.md`, reinterpreted against the **live codebase**.

### Corrected baseline (engineering audit 2026-08-07)

| Area | Sprint claim | Code reality |
|---|---|---|
| Progress | 0% Day 1 | Backend ~70–80% of named Week 1–2 scope already shipped under IREIOS 3.0 |
| Neo4j | Week 1 greenfield | Schema v1, writers, `/graph/*`, reply-path context **live** |
| Forecast | Models trained | **Heuristic** prediction APIs live; no training pipeline |
| Sales AI | LangGraph in n8n | **Python** `SalesAgent` + `POST .../sales-ai` + bus **live** |
| Marketing routing | In n8n | **Python** assignment/escalation; n8n = report/Gmail fan-out |
| HubSpot bi-di | Week 2 complete | Outbound+DLQ code ready; **portal skipped**; **no inbound webhook** |
| FE graph/forecast/twin/sales-ai | Week 2 | Mock shells; Sales AI button **missing**; forecast still mock |

**Overall project ~70%** in the sprint doc is directionally OK; **Phase 4 at 0% is false** for backend.

---

## 2. Frozen decisions (defaults until lead overrides)

| ID | Decision | Default |
|---|---|---|
| D1 | Program intent | Integrate + FE cutover + QA/release — **not** rebuild agents |
| D2 | Runtime spine | Keep CEO→AE→EE; no second orchestrator |
| D3 | Sales NBA | Python only; FE calls existing HTTP API |
| D4 | n8n role | Ops side-plane (Gmail/Sheets/notify); **not** FSM/assignment/NBA |
| D5 | Forecasts | Heuristic MVP + honest OpenAPI text; optional &lt;200ms smoke |
| D6 | Graph MVP | Neighborhood `{nodes,edges}` API (ego Lead + similar + agent [+ units stretch]) |
| D7 | Twin MVP | Live layout from `InventoryUnit` + seed; wire R3F |
| D8 | FE surfaces | Sales AI + scores on `(dashboard)` CRM/leads; graph/twin on `(command-center)`; forecast both |
| D9 | Auth in browser | JWT cookie / same-origin; **no** hard-coded `secret-client-key-123` in shipped bundles |
| D10 | HubSpot | Outbound live when portal ready; bi-di only if Q2=B; else `[-]` with reason |
| D11 | Dual-path monolith | Root `agent.py` / `crm_sync.py` / `follow_up.py` remain shared libs (3.0 defer stands) |
| D12 | Test prefix | `tests/test_f4_*.py` for Phase 4 |
| D13 | Feature flags | Prefer env flags for HubSpot live, twin live, graph viz if freeze threatened |

---

## 3. Phase overview

| Phase | Goal | Exit |
|---|---|---|
| P4-0 Baseline | Truth vs sprint; non-goals | Evidence baseline signed |
| P4-1 Contracts | Day-1 shapes for FE/BE | API_CONTRACTS approved |
| P4-2 Graph API | Neighborhood endpoint | pytest green |
| P4-3 Twin API | Layout + seed | pytest + seed |
| P4-4 HubSpot | Scoped track | DoD or `[-]` |
| P4-5…9 FE | Sales AI, forecast, graph, twin, SSE | Backlog acceptance |
| P4-10 Ops | n8n deltas only if required | Smoke |
| G5 | MVP gate | Full gates |
| QA / REL | Freeze + prod | Checklist |

---

## 4. Target surfaces (delta vs 3.0)

### Backend (likely new or extend)

| Surface | Purpose |
|---|---|
| `GET /api/v1/graph/neighborhood` or extend context | `{nodes,edges}` for force-graph |
| `GET /api/v1/inventory/twin` | Tower/floor/unit layout for R3F |
| Optional `POST /api/v1/webhook/hubspot` | Only if bi-di chosen |
| Existing keep | `/predictions/*`, `/leads/{id}/sales-ai`, `/graph/health`, `/events/stream` |

### Frontend

| Surface | Action |
|---|---|
| `(dashboard)/crm` + `leads` | Sales AI button |
| `dashboard-mvp` + product dashboard | Live forecast widgets |
| `knowledge-graph` | Replace `mockGraphService` |
| `digital-twin` | Replace `mockTwinService` |
| `sales-copilot` | Selected lead + sales-ai + timeline JWT |
| SSE clients | JWT; remove hard-coded api_key |

### Out of scope (default non-goals)

- LangGraph-in-n8n NBA rewrite  
- Full ML training platform  
- Mobile native  
- Monolith module delete  
- Fake accuracy claims on heuristics  

---

## 5. Risks

| Risk | Mitigation |
|---|---|
| Sprint DoD vs architecture conflict | Questionnaire + D1–D4; rewrite DoD language |
| HubSpot email/portal blocker | Isolate P4-4; flag off |
| Graph mock >> backend schema | Ego MVP; stretch full topology |
| Twin without seed data | `seed_inventory` / new twin seed mandatory for demo |
| Week 3 freeze slip | Feature-flag incomplete tracks |
| Plans path break | `plans/phase3` archive; update AGENTS pointers |

---

## 6. Success metrics (MVP)

- FE acceptance in `docs/FRONTEND_BACKLOG.md` all required boxes  
- G5 evidence pack green  
- No High/Critical open at RC1  
- Demo scripts in questionnaire Q12 pass on staging  
