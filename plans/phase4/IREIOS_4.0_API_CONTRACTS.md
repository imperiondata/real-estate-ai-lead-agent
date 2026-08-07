# IREIOS 4.0 — API contracts (FE / integration)

| This doc owns | Does not own |
|---|---|
| Human-readable contracts for Phase 4 surfaces | Full 3.0 SSE history → `../phase3/IREIOS_3.0_API_SSE_CONTRACTS.md` |
| Freeze rules for Mayank/Aritro | Runtime OpenAPI dump → regen `openapi_ireios4.json` after code lands |

**Status:** Draft from **code + FE mocks** · mark `FROZEN` per section after lead/P4-1  
**Compat:** Do not rename fields after `FROZEN` without versioning (`/api/v2` or additive-only).

Auth legend: **JWT** = Bearer or HttpOnly `jwt` cookie · **API key** = `X-API-Key` / `?api_key=` (prefer **not** in browser bundles) · **Admin** = `X-Admin-Key` / token

---

## 0. Already shipped (bind FE now — shapes from live code)

### 0.1 Sales AI — `FROZEN-CANDIDATE` (exists)

| | |
|---|---|
| Route | `POST /api/v1/leads/{lead_id}/sales-ai` |
| Auth | JWT · tenant-scoped lead |
| Errors | `404` wrong tenant/missing · `401` · `422` |

**Response (approximate — confirm via OpenAPI/`main.py` during P4-1):**

```json
{
  "status": "success",
  "lead_id": 1,
  "scores": {
    "conversion_probability": 72.0,
    "lead_temperature": "hot",
    "engagement_score": 60.0,
    "urgency_level": "high"
  },
  "assigned_agent": "Agent Name",
  "recommendation": {
    "action": "schedule_site_visit",
    "rationale": "string"
  },
  "funnel_stage": "string",
  "crm_sync": {}
}
```

**NBA `action` enum (current code):**  
`request_info` | `schedule_site_visit` | `escalate_hot` | `send_brochure` | `assign_agent` | `nurture_followup`

⚠ Confirm exact nested keys in P4-1 against running `/openapi.json`.

### 0.2 Predictions portfolio — `FROZEN-CANDIDATE`

| Route | Auth | Notes |
|---|---|---|
| `GET /api/v1/predictions/revenue` | JWT | Heuristic Σ budget×prob |
| `GET /api/v1/predictions/cashflow` | JWT | Heuristic slice |
| `GET /api/v1/predictions/inventory` | JWT | Status counts |
| `GET /api/v1/predictions/cancellation-risk` | JWT | At-risk proxy |
| `GET /api/v1/leads/{id}/prediction` | JWT | Per-lead conversion + closure days |

All documented in code as **MVP heuristics — not ML accuracy**. FE must not label “AI trained model” unless lead overrides Q1.

### 0.3 Graph context (LLM/ego lite) — exists, **not** full force-graph

| Route | Auth | Returns |
|---|---|---|
| `GET /api/v1/graph/health` | per router | Neo4j up/down |
| `GET /api/v1/graph/leads/{id}/context` | JWT/API key | `similar_leads`, `assigned_agent` |
| `POST /api/v1/graph/upsert` | Admin | Manual upsert |

### 0.4 SSE / timeline — exists

| Route | Auth | Notes |
|---|---|---|
| `GET /api/v1/events/stream` | API key **or** jwt cookie | Tenant filter; `: ping` 15s |
| `GET /api/v1/events/leads/{id}/timeline` | JWT/API key | 404 cross-tenant |

Phase 4 FE **must** prefer jwt cookie (P4-9).

---

## 1. Graph neighborhood — **PROPOSED** (P4-2) ⚠ BLOCKED ON LEAD Q5

| | |
|---|---|
| Route | `GET /api/v1/graph/neighborhood` |
| Auth | JWT |
| Query | `lead_id` (optional) · `limit` (default 50, max 200) |
| Errors | `404` lead · `503` graph unavailable (body still JSON) |

**Proposed body (matches FE `mockGraphService` consumer):**

```json
{
  "status": "success",
  "available": true,
  "data": {
    "nodes": [
      {
        "id": "L-123",
        "label": "Lead",
        "properties": { "name": "…", "score": 82, "temperature": "Hot" },
        "val": 20,
        "color": "#ef4444"
      }
    ],
    "edges": [
      { "source": "L-123", "target": "A-1", "type": "ASSIGNED_TO", "properties": {} }
    ]
  },
  "ai_summary": "optional short string"
}
```

**MVP node `label` values:** `Lead`, `Agent`  
**Stretch:** `Unit`, `Tower`, `Project`, `Communication`  
**Colors:** FE may override; backend should send stable defaults.

**Empty / down:**

```json
{ "status": "success", "available": false, "data": { "nodes": [], "edges": [] }, "ai_summary": "graph_unavailable" }
```

**Latency target (sprint):** p95 &lt; 200ms on staging warm cache — **confirm Q5.5**.

**Real-time:** FE refetches on SSE `lead.scored` | `lead.assigned` | `lead.hot` (no graph-push protocol in MVP).

---

## 2. Digital twin layout — **PROPOSED** (P4-3) ⚠ BLOCKED ON LEAD Q6

| | |
|---|---|
| Route | `GET /api/v1/inventory/twin` |
| Auth | JWT |
| Query | `project_id` optional |
| Errors | `401` · empty data `200` |

**Proposed body (align to R3F page needs — refine in P4-1):**

```json
{
  "status": "success",
  "project": { "id": "PRJ-1", "name": "The Summit", "location": "…" },
  "towers": [
    {
      "id": "T-1",
      "name": "Tower A",
      "floors": [
        {
          "level": 1,
          "units": [
            {
              "id": "U-101",
              "unit_number": "A-101",
              "status": "available",
              "price": 1500000,
              "currency": "INR",
              "bhk": 3,
              "lead_id": null
            }
          ]
        }
      ]
    }
  ],
  "counts": { "available": 10, "hold": 2, "sold": 5 }
}
```

**Status enum (proposed):** `available` | `hold` | `sold` (FE today title-cases — normalize in client).

**Counts-only fallback:** existing `GET /api/v1/predictions/inventory` remains.

---

## 3. HubSpot — **CONDITIONAL** ⚠ Q2

| Mode | Contract |
|---|---|
| Outbound only | No new public API; EE `update_crm` + `crm_sync` |
| Bi-di | `POST /api/v1/webhook/hubspot` + signature header TBD by HubSpot app settings |
| Defer | No contract work |

Field map (current outbound): see `crm_sync.build_crm_properties` / AGENTS.md P5.2.

---

## 4. Compatibility rules

1. Additive JSON fields are OK after freeze.  
2. Renames/removals require FE coordinated PR + changelog.  
3. Heuristic prediction responses must keep a stable top-level key set once FROZEN (document `disclaimer` field if added).  
4. Regenerate `openapi_ireios4.json` from running app after P4-2/P4-3 merge:

```powershell
curl -o plans/phase4/openapi_ireios4.json http://localhost:8000/openapi.json
```

---

## 5. Smoke (after implement)

```powershell
# Sales AI
curl -X POST "http://localhost:8000/api/v1/leads/1/sales-ai" -H "Authorization: Bearer <jwt>"

# Predictions
curl "http://localhost:8000/api/v1/predictions/revenue" -H "Authorization: Bearer <jwt>"

# Neighborhood (post P4-2)
curl "http://localhost:8000/api/v1/graph/neighborhood?lead_id=1" -H "Authorization: Bearer <jwt>"

# Twin (post P4-3)
curl "http://localhost:8000/api/v1/inventory/twin" -H "Authorization: Bearer <jwt>"

# SSE
curl -N "http://localhost:8000/api/v1/events/stream" -H "Cookie: jwt=<token>"
```
