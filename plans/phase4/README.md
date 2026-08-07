# IREIOS 4.0 / Product Phase 4 — Active plans

| This folder owns | Does not own |
|---|---|
| Product Phase 4 execution order, tasks, contracts, evidence, lead Qs | IREIOS 3.0 history → `../phase3/` |
| Corrected baseline vs root sprint brief | Day-to-day ops runbooks → `docs/` |

**Status:** Skeletons ready · **blocked on** team-lead answers in `TEAM_LEAD_QUESTIONNAIRE.md`  
**Owners:** Aritro (backend) · Maitri (automation/ops) · Mayank (frontend)  
**Target release (sprint):** 2026-09-03 (confirm in questionnaire)

## Doc roles

```text
UNIFIED_EXECUTION_ORDER.md     ← when / what next (single queue)
IREIOS_4.0_STEP_BY_STEP.md     ← how (atomic tasks)
IREIOS_4.0_IMPLEMENTATION_PLAN.md ← macro phases + frozen decisions
IREIOS_4.0_ARCHITECTURE_DELTA.md  ← deltas only vs 3.0 spine
IREIOS_4.0_API_CONTRACTS.md    ← FE/integration contracts
IREIOS_4.0_CHANGELOG.md        ← living shipped log
IREIOS_4.0_EVIDENCE_PACK.md    ← gate proof
TEAM_LEAD_QUESTIONNAIRE.md     ← decisions + false-claim audit
openapi_ireios4.json           ← regen after routes land (placeholder)
```

## Recommended defaults (until lead overrides)

See `IREIOS_4.0_IMPLEMENTATION_PLAN.md` § Frozen decisions. Summary:

- Phase 4 = **integrate + FE cutover + release**, not rebuild of shipped Python agents
- Sales AI stays **Python** (`POST /api/v1/leads/{id}/sales-ai`); n8n = ops side-plane
- Forecasts stay **heuristic MVP** (honest labeling); wire FE to `/api/v1/predictions/*`
- Graph: **ego-network / neighborhood API** production path; full Project→Tower mock parity = stretch
- Twin: **live inventory layout API** + wire R3F
- FE: Sales AI on product CRM/leads; graph/twin on command-center; JWT not hard-coded api_key
- HubSpot: outbound + real portal when unblocked; bi-di only if lead chooses

## Start here

1. Send `TEAM_LEAD_QUESTIONNAIRE.md` to the technical lead  
2. Fold answers into STEP_BY_STEP (remove `⚠ BLOCKED ON LEAD`)  
3. Execute `UNIFIED_EXECUTION_ORDER.md` top to bottom  
