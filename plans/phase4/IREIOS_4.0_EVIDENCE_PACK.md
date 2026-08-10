# IREIOS 4.0 — Evidence pack

| This doc owns | Does not own |
|---|---|
| Gate checkboxes + smoke proof for Product Phase 4 | 3.0 G2/G3 → `../phase3/IREIOS_3.0_EVIDENCE_PACK.md` |

**Decisions:** `TEAM_LEAD_QUESTIONNAIRE_ANSWERED.md`  
**Release:** 2026-09-03 · **Freeze:** 2026-08-20

---

## Baseline (P4-0) — already true before 4.0 coding

### Backend shipped

- [x] Event bus + CEO + AE + EE
- [x] `POST /api/v1/leads/{id}/sales-ai` + bus SalesAgent (execute path)
- [x] Neo4j schema v1 + `/graph/health|context|upsert` + reply-path context
- [x] Heuristic `/predictions/*` + per-lead prediction
- [x] CRM outbound + DLQ `hubspot_crm` (portal often skipped)
- [x] Marketing/CS agents + n8n bridge (WF-1 may be ops-pending — non-blocking)
- [x] SSE stream + lead timeline

### Frontend partial

- [x] Command-center shells (graph, twin, mvp, copilot)
- [x] Product dashboard/leads/CRM live
- [~] Sales AI button shell on copilot (needs preview body + Confirm wire → P4-5)
- [~] Forecast revenue on product dashboard; mvp still mock → P4-6
- [ ] Graph/twin mock → P4-7/8 (APIs ready)
- [ ] Hard-coded api_key → P4-9

### Sprint corrections (lead authorized)

- [x] §6 = ~75% BE / ~15% FE / ~10% HubSpot-ops (not 0%)
- [x] DoD rewritten: heuristic forecast, Python NBA, Python routing, HubSpot outbound
- [x] Dependency matrix corrected (UI/contract/portal)

**P4-0 sign-off:** Backend Wave 1 date: 2026-08-10

---

## Contracts (P4-1)

- [x] sales-ai `preview`/`execute` FROZEN in API_CONTRACTS + implemented
- [x] predictions display rules (₹ Cr + disclaimer) FROZEN
- [x] neighborhood FROZEN + implemented
- [x] twin FROZEN + implemented
- [x] Day-1 mocks aligned (ego graph + 40-unit twin)
- [x] `openapi_ireios4.json` regenerated post-code (2026-08-10; includes neighborhood/twin/sales-ai)

---

## Graph (P4-2)

- [x] `GET /neighborhood` tenant-scoped
- [x] Neo4j down soft-empty
- [x] `test_f4_graph*` green
- [x] Soft latency note (optional log >200ms)
- [x] FEATURE_GRAPH_VIZ documented

---

## Twin (P4-3)

- [x] `GET /inventory/twin` shape matches contract
- [x] Seed 1×2×10×40 for demo client (`python seed_twin_demo.py --client-id 1`)
- [x] `test_f4_twin*` green
- [x] FEATURE_TWIN_LIVE documented

---

## HubSpot (P4-4)

- [x] Scope: outbound only (bi-di 4.1)
- [x] FEATURE_HUBSPOT_LIVE
- [x] Live contact upsert **or** `[-]` Sheets/fallback until Piyush key
- [ ] DLQ drill if live
- [x] No inbound webhook shipped

---

## Frontend (P4-5…P4-9)

- [x] Sales AI preview+confirm on **sales-copilot**
- [x] Sales AI on Leads table
- [x] Forecast live + ₹ Cr + heuristic label
- [x] Graph ego embed on copilot + SSE refetch
- [x] Twin live read-only 30s poll
- [x] Zero `secret-client-key-123` in `frontend/src`
- [x] MockSSE unused (no MockSSE class; mock chart series only)
- [x] Command-center JWT middleware
- [x] Login home `/dashboard`
- [x] Timeline uses selected lead
- [x] Approvals UI **not** required (deferred 4.1)
- [~] `npm run lint` — touched FE files clean; repo-wide still has pre-existing errors
- [x] `docs/FRONTEND_BACKLOG.md` updated

---

## Ops (P4-10)

- [x] No new n8n WFs (lead Q4.2 None) — default `[-]`
- [ ] Optional existing bridge smoke if env ready

---

## G5 — MVP gate

- [ ] UNIFIED required steps `[x]` or `[-]` with reason
- [ ] `pytest tests/test_f4_*.py` green
- [ ] Full pytest matrix green — log: ________
- [ ] `gate_isolation_test.py` green
- [ ] DLQ drill N/A or green
- [ ] `task3_runner.py` green or Mayank-acked skip
- [ ] FE lint green
- [ ] Q12 demos signed (list below)
- [ ] Zero High/Critical GitHub Issues

### Q12 demos

| Demo | Pass? |
|---|---|
| WA → SSE &lt;2s | |
| Sales AI preview → confirm NBA | |
| Forecast from `/predictions/*` | |
| Graph neighborhood hot lead | |
| Twin seeded 40 units | |
| HubSpot upsert or deferred note | |
| Isolation drill | |
| DLQ if HubSpot live | |

**G5 sign-off (Mayank):** ________ date: ________

---

## QA freeze / RC1 (from 2026-08-20)

- [ ] Hard freeze honored
- [ ] RC1 on **read-replica** — tag: ________
- [ ] E2E UI + automations
- [ ] Runbook draft

---

## Production (2026-09-03)

- [ ] Secrets filled (were N/A in Q11 — Piyush/Mayank track)
- [ ] `IS_PRODUCTION=true`, test flags off
- [ ] FEATURE_* production values set
- [ ] Telemetry `/metrics` owner: Mayank
- [ ] Incident owner: ________

---

## Deferred to 4.1

| Item | Reason |
|---|---|
| HubSpot bi-directional | Q2.8 best-effort / 4.1 |
| Approvals UI | Q7.4 |
| LLM email draft | Q3.8 |
| Full Project/Tower/Comm graph | Q5.1 ego only |
| Twin write-back | Q6.4 read-only |
| New n8n WFs | Q4.2 None |
| Trained ML models | Q1.1 |
