# Unified Execution Order — Product Phase 4 (IREIOS 4.0)

| This doc owns | Does not own |
|---|---|
| Which Phase 4 work unit runs next; exit gates | Task file lists / code steps → `IREIOS_4.0_STEP_BY_STEP.md` |
| Status for Product Phase 4 only | IREIOS 3.0 history → `../phase3/UNIFIED_EXECUTION_ORDER.md` |
| | Lead product decisions → `TEAM_LEAD_QUESTIONNAIRE.md` |

**Status legend:** `[ ]` pending · `[~]` in progress · `[x]` done · `[-]` skipped (reason required) · `[?]` blocked on lead

**Companion:** root brief `../../IREIOS_Phase_4_Master_Sprint_Plan.md` (ownership dates only; **baseline % in that file is incorrect** — see questionnaire § False claims).

**Prerequisite:** IREIOS 3.0 G2/G3 complete (`../phase3/`). G4 n8n WF-1 may remain ops-pending; does not block P4-0.

---

## 1. Hard rules

1. **Serial only** within this table unless a step explicitly says parallel FE/BE against **frozen contracts**.
2. **Contract-first:** no FE binding to unfrozen response shapes (P4-1 before P4-5…P4-8).
3. **No dual brains:** Sales NBA / assignment / FSM stay Python CEO→AE→EE. n8n = side-plane only (`docs/N8N_INTEGRATION.md`).
4. **Tenant isolation never regresses** — `python gate_isolation_test.py` after data-plane changes.
5. **Do not rebuild** shipped 3.0 modules listed in baseline (P4-0) without lead override.
6. **Feature-flag** anything that threatens Week 3 hard freeze.
7. Path references to Phase 3 docs use `../phase3/…`.

---

## 2. Why this order

| Decision | Reason |
|---|---|
| Baseline audit before build | Sprint claims 0%; backend already has KG, Sales AI, predictions, CRM outbound |
| Contracts before FE | Sprint mitigation #1; avoids translation-layer thrash |
| Graph/twin APIs before FE wire | FE mocks need `{nodes,edges}` / layout shapes 3.0 context API does not provide |
| Sales AI + forecast FE early | Backend ready today; highest demo value, lowest BE risk |
| HubSpot track isolated | Org/email portal blocker; must not stall FE |
| G5 before QA freeze | Evidence pack + gates before RC1 |

---

## 3. Master sequence

| Step | Unit | Summary | Exit gate | Status |
|---:|---|---|---|---|
| **P4-0** | Baseline | Ship inventory vs sprint; correct false claims; freeze non-goals | Baseline section in Evidence Pack signed | `[ ]` |
| **P4-1** | Contracts | Freeze OpenAPI/human contracts: neighborhood, twin, sales-ai, predictions, SSE auth | `IREIOS_4.0_API_CONTRACTS.md` reviewed | `[?]` |
| **P4-2** | Graph API | Tenant-scoped neighborhood `{nodes,edges}` (+ health); optional schema stretch | STEP P4-2 Done + pytest `test_f4_graph*` | `[?]` |
| **P4-3** | Twin API | `GET` inventory twin layout from `InventoryUnit` + seed | STEP P4-3 Done + seed script | `[?]` |
| **P4-4** | HubSpot track | Per lead Q2: live outbound / bi-di / n8n / defer | Explicit DoD in Evidence Pack | `[?]` |
| **P4-5** | FE Sales AI | Button on CRM/leads (+ copilot); `POST .../sales-ai`; error boundaries | No mock NBA on wired surfaces | `[ ]` |
| **P4-6** | FE Forecast | Replace `mockForecastData` with `/api/v1/predictions/*` | FRONTEND_BACKLOG §7 | `[ ]` |
| **P4-7** | FE Graph | Wire force-graph to neighborhood API; JWT | Zero console errors; live or empty-state | `[?]` |
| **P4-8** | FE Twin | Wire R3F to twin API | Responsive; seeded demo tenant | `[?]` |
| **P4-9** | FE SSE/JWT | Purge hard-coded api_key; MockSSE unused; selected-lead timeline | FRONTEND_BACKLOG acceptance | `[ ]` |
| **P4-10** | Ops/n8n | Only deltas required by lead (not NBA rewrite) | Smoke list in Evidence Pack | `[?]` |
| **G5** | Gate | Phase 4 MVP complete | Evidence Pack G5 + full pytest + isolation + DLQ + FE lint | `[ ]` |
| **P4-QA** | Week 3 | Hard freeze; RC1; E2E | Prod readiness checklist | `[ ]` |
| **P4-REL** | Week 4 | Production release + telemetry | Runbook approved | `[ ]` |

---

## 4. Dependency matrix (engineering)

| Dependent | Blocked by | Notes |
|---|---|---|
| P4-5…P4-9 FE | P4-1 contracts | Parallel OK after contract freeze using mocks |
| P4-7 Graph FE | P4-2 | Or temporary adapter on context API if lead chooses ego-only lite |
| P4-8 Twin FE | P4-3 | Mock-only only if lead Q6 = mock/defer |
| P4-4 HubSpot | Lead Q2 + portal secrets | Non-blocking for G5 if marked `[-]` |
| P4-10 | Lead Q4 | Default = no new WF beyond 3.0 set |
| G5 | P4-0…P4-9 except explicitly `[-]` | |

**Sprint dependency table falsehoods:** see questionnaire — several “Blocked By Week 1 APIs” rows are already unblocked in code.

---

## 5. Day-to-day workflow

1. Open this table → first non-`[x]` / non-`[-]` step.  
2. Implement via `IREIOS_4.0_STEP_BY_STEP.md`.  
3. Log entry in `IREIOS_4.0_CHANGELOG.md`.  
4. Flip status here + Evidence Pack checkboxes.  
5. Update `docs/FRONTEND_BACKLOG.md` / `AGENTS.md` when paths or commands change.

---

## 6. Rollback / emergency

| Problem | Action |
|---|---|
| FE broken on prod routes | Feature-flag command-center; keep `(dashboard)` on 3.0 APIs only |
| Graph/Neo4j down | Neighborhood API returns empty + `available:false`; UI empty-state (3.0 pattern) |
| HubSpot failing | DLQ `hubspot_crm`; disable live key; demo stub |
| Need 3.0 behavior | `FEATURE_WHATSAPP_V3` / `FOLLOWUP_ENGINE` already documented; do not invent new kill switches without changelog |

---

## 7. Pointers

| Need | Path |
|---|---|
| Atomic tasks | `IREIOS_4.0_STEP_BY_STEP.md` |
| Lead decisions | `TEAM_LEAD_QUESTIONNAIRE.md` |
| API shapes | `IREIOS_4.0_API_CONTRACTS.md` |
| 3.0 spine / event catalog | `../phase3/IREIOS_3.0_Architecture_Diagrams.md` |
| FE checklist | `../../docs/FRONTEND_BACKLOG.md` |
| n8n rules | `../../docs/N8N_INTEGRATION.md` |
