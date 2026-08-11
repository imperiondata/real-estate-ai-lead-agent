# IREIOS 4.0 — Expansion changelog (living)

| This doc owns | Does not own |
|---|---|
| What shipped in Product Phase 4 + test evidence | Task specs → `IREIOS_4.0_STEP_BY_STEP.md` |

**Test naming:** `tests/test_f4_*.py`

---

## Status table

| ID | Status | Summary | Tests |
|---|---|---|---|
| P4-0 | `[x]` | Baseline + sprint re-baseline | doc |
| P4-1 | `[x]` | Contract freeze + Day-1 mocks + sales-ai preview | `test_f4_sales_ai*` |
| P4-2 | `[x]` | Graph neighborhood API | `test_f4_graph*` |
| P4-3 | `[x]` | Twin API + 40-unit seed | `test_f4_twin*` |
| P4-4 | `[x]` | HubSpot outbound flag (live key pending) | `test_f4_hubspot*` |
| P4-5 | `[x]` | FE Sales AI preview/confirm | lint + manual |
| P4-6 | `[x]` | FE Forecast ₹ Cr | lint + manual |
| P4-7 | `[x]` | FE Graph ego embed | lint + manual |
| P4-8 | `[x]` | FE Twin live | lint + manual |
| P4-9 | `[x]` | FE JWT/SSE/middleware | grep + lint |
| P4-10 | `[-]` | No new n8n WFs | n/a |
| G5 | `[x]` | MVP gate 2026-08-10 | 426 pytest; isolation; DLQ; task3 skip |
| Plans lock | `[x]` | Lead answers folded into all phase4 docs | n/a |

---

## Entries

### 2026-08-11 — G5 follow-ups (pre-QA)

- **WA → SSE live smoke:** `wa_sse_smoke.py` added (stdlib, repo root). Live local run PASS in
  both modes — turn 4.9–11.3s (13s window), SSE publish→delivery 10–2183ms; events
  `whatsapp.received` → `conversation.updated` → `lead.crm_synced` → `lead.scored` (+
  `lead.created` with `--new-lead`). Evidence Pack Q12 WA→SSE → `[x]`.
- **Bus resilience note:** a Redis blip can kill the `EventBusClient._consume_loop`
  (`_running=False`, SSE 503s) — restart uvicorn to recover; documented in MAINTENANCE §5.
- **n8n bridge:** `tests/test_e20_n8n_bridge.py` **14/14 green** (2026-08-11); live delivery
  still pending n8n UI WF activation (`ireios-n8n` group PEL growing — Maitri ops).
- **FE lint runbook:** full fix recipe (23e/17w baseline, per-file steps, shim gotcha)
  documented in `docs/MAINTENANCE.md` §11.1 — pre-freeze triage batch.

### 2026-08-10 — G5 MVP gate

- **Evidence:** `pytest` f4 22 passed; full suite 426 passed / 4 skipped; `gate_isolation_test.py` PASS; `gate_dlq_drill.py` PASS; `task3_runner` skipped (Mayank); `/health` healthy.
- **FE lint:** repo-wide residual errors pre-existing — not G5 blocker; freeze triage.
- **HubSpot live:** deferred note (PAT pending); flag path green.
- **UNIFIED G5:** `[x]`

### 2026-08-10 — FE Wave (P4-5…P4-9)

- **Files:** `frontend/next.config.ts` (rewrite `/api/v1/*`), `proxy.ts` (guard CC routes), `sales-copilot/*`, `SalesAiModal.tsx`, `LeadsTable.tsx`, `dashboard-mvp`, `dashboard/page.tsx`, `digital-twin`, `knowledge-graph`, `lib/format.ts`, `lib/api.ts` predictions helpers
- **Behavior:**
  - Same-origin proxy so EventSource/fetch send HttpOnly `jwt` (zero `secret-client-key-123` in `frontend/src`)
  - Sales AI preview then Confirm execute on copilot + Leads table
  - Forecasts from live `/predictions/*` with ₹ Cr + heuristic disclaimer
  - Ego neighborhood embed + SSE refetch; KG page lead selector
  - Twin live API, 30s poll, read-only; seed `seed_twin_demo.py`
- **Tests:** Backend suite still **426 passed, 4 skipped**. FE touched files eslint clean. Full `npm run lint` still has pre-existing errors outside this wave.
- **HubSpot PAT:** Backend already `Authorization: Bearer {CRM_API_KEY}`; contacts scopes sufficient; live flip remains ops when token arrives.

### 2026-08-10 — Backend Wave 1 (P4-0…P4-4)

- **Files:** `app/agents/sales_agent.py` (preview|execute + `SalesAiBody`), `main.py` sales-ai body, `app/knowledge_graph/graph_api.py` (`GET /neighborhood`), `app/api/inventory.py` (`GET /twin`), `seed_twin_demo.py`, `config.py` + `.env.example` (`FEATURE_GRAPH_VIZ`/`FEATURE_TWIN_LIVE`/`FEATURE_HUBSPOT_LIVE`), `crm_sync.py` hubspot live gate, FE Day-1 mocks (`mockGraphService.ts` ego, `mockTwinService.ts` 40u), `tests/test_f4_*.py`
- **Behavior:**
  - HTTP sales-ai defaults to `mode=preview` (no DB/CRM writes); `execute` keeps Phase 6 pipeline. Bus path unchanged (execute).
  - Neighborhood ego graph soft-empty when Neo4j down or flag off; tenant 404.
  - Twin groups `InventoryUnit` via `meta_json.floor`; seed 1×2×10×40 The Summit.
  - HubSpot live only when `FEATURE_HUBSPOT_LIVE=true` + non-demo key; else stub.
- **Tests:** Full suite with docker+uvicorn up: **`426 passed, 4 skipped`** (2026-08-10). f4_* + e3 green. Fixed stale path in `test_e20_n8n_bridge` → `plans/phase3/N8N_LIVE_WORKFLOWS_PLAN.md` (post-archive).
- **OpenAPI:** `plans/phase4/openapi_ireios4.json` regenerated from live app (neighborhood, twin, sales-ai present).
- **Follow-up (same day):** FE P4-5…P4-9 + **G5** also shipped; live HubSpot portal key still pending (flag ready).

### 2026-08-07 — Lead questionnaire locked → plans filled

- **Files:** All `plans/phase4/*` implementation docs; `TEAM_LEAD_QUESTIONNAIRE_ANSWERED.md` (source)
- **Behavior:** No runtime code. Decisions locked: integrate-only; heuristic forecasts INR Cr; Sales AI preview+confirm on copilot→leads; ego graph embed; live twin 40 units read-only; HubSpot outbound; no new n8n; freeze 2026-08-20; release 2026-09-03; Mayank tech lead.
- **Tests:** n/a
- **Follow-up questionnaire:** **Not required** — remaining gaps are ops secrets (Q11 N/A → Piyush) and engineering design choices documented in Implementation Plan §5.

### 2026-08-07 — Plans folder restructure + Phase 4 skeletons

- **Files:** `plans/phase3/*`, `plans/phase4/*` initial skeletons
- **Behavior:** Archive 3.0; create 4.0 queue
- **Tests:** n/a
