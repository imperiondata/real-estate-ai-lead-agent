# IREIOS 4.0 — Architecture delta (vs 3.0)

| This doc owns | Does not own |
|---|---|
| **New/changed** layers, APIs, events for Product Phase 4 | Full 3.0 diagrams/event catalog → `../phase3/IREIOS_3.0_Architecture_Diagrams.md` |

**Spine (unchanged):**

```text
Event → CEO → Agent/Workflow → Automation Engine → Execution Engine → Event
```

n8n remains **ops side-plane** via `n8n_bridge` (not CEO consumer group).

---

## 1. What stays (do not re-litigate)

| Layer | Location |
|---|---|
| Event bus Redis Streams | `app/clients/event_bus_client.py` |
| CEO | `app/orchestrator/ceo_orchestrator.py` |
| AE / EE | `app/automation_engine/*`, `app/execution_engine/*` |
| SalesAgent NBA | `app/agents/sales_agent.py` |
| Neo4j client + writers | `app/knowledge_graph/*` |
| Predictions heuristic | `app/api/predictions.py`, `app/services/prediction_service.py` |
| CRM outbound | `crm_sync.py`, `CRMExecutor`, `crm_automation` |
| SSE | `app/api/events.py` |

---

## 2. Proposed deltas (pending lead)

### 2.1 Graph neighborhood (P4-2)

```text
FE force-graph
  → GET /api/v1/graph/neighborhood?lead_id= | ?scope=tenant_sample
  → Neo4j read (tenant-scoped) + optional PG inventory join
  → { status, data: { nodes[], edges[] }, ai_summary?, available }
```

**Node labels (MVP):** `Lead`, `Agent`  
**Stretch:** `Unit`, `Project`/`Tower` if inventory supports  
**Not default MVP:** full Communication node storm from mock (unless lead requires)

Existing `GET /graph/leads/{id}/context` remains for LLM/reply-path; neighborhood is **viz-oriented**.

### 2.2 Digital twin layout (P4-3)

```text
FE R3F
  → GET /api/v1/inventory/twin
  → Postgres InventoryUnit (+ grouping keys)
  → { projects[] | towers[]: { floors[]: { units[] } } }
```

Bus: optional refresh on `inventory.hold` / inventory events (poll OK for MVP).

### 2.3 HubSpot inbound (only if Q2=B)

```text
HubSpot → POST /api/v1/webhook/hubspot → verify signature
  → map fields → PG lead (client-scoped)
  → publish catalog event (e.g. conversation.updated or lead.* — **no invented types without catalog update**)
```

### 2.4 FE auth delta

Browser EventSource / fetch: **JWT cookie** preferred over `?api_key=` embedded in JS bundles.

---

## 3. Event catalog

**Default:** no new event types for Phase 4 MVP.

| If needed | Proposal | Gate |
|---|---|---|
| Twin/UI refresh hint | reuse existing inventory/lead events | Prefer |
| NBA manually requested | optional `sales.nba.requested` | Only if lead wants timeline audit; else HTTP-only is enough |
| HubSpot inbound applied | enrich `lead.*` payload | Catalog amend in phase3 arch doc or delta § here |

Amend `../phase3/IREIOS_3.0_Architecture_Diagrams.md` §4 **or** add rows below when frozen — do not silently invent names in code.

---

## 4. Explicit non-deltas

| Rejected (default) | Reason |
|---|---|
| LangGraph NBA inside n8n | Dual brain; violates n8n hard rules |
| Second prediction service claiming ML accuracy without models | Honesty / compliance |
| FE → Redis/Neo4j direct | Tenant + security |
| Replacing CEO with n8n | 3.0 spine |

---

## 5. Diagram (Phase 4 FE integration)

```text
                    ┌─────────────────────────────┐
  Twilio/WA ───────►│ FastAPI main + agents (3.0) │
                    └─────────────┬───────────────┘
                                  │ bus events
                    ┌─────────────▼───────────────┐
                    │ CEO → agents → AE → EE      │
                    └─────────────┬───────────────┘
                                  │
         ┌────────────────────────┼────────────────────────┐
         ▼                        ▼                        ▼
   Neo4j KG                 Postgres                  HubSpot (out)
   neighborhood API         twin + predictions         optional in
         │                        │                        │
         └────────────────────────┼────────────────────────┘
                                  ▼
                    Next.js (dashboard + command-center)
                    JWT · SSE · Sales AI button · widgets
```
