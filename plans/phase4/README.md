# IREIOS 4.0 / Product Phase 4 — Active plans

| This doc owns | Does not own |
|---|---|
| Product Phase 4 execution | IREIOS 3.0 history → `../phase3/` |

**Status:** **Implementation plans LOCKED** · **Backend Wave 1 + FE Wave done** (P4-0…P4-9, 2026-08-10) · G5/QA next  
**Release:** 2026-09-03 · **Hard freeze:** 2026-08-20 · **Tech lead:** Mayank

## Start here

1. Locked answers: `TEAM_LEAD_QUESTIONNAIRE_ANSWERED.md`  
2. Execute order: `UNIFIED_EXECUTION_ORDER.md`  
3. How: `IREIOS_4.0_STEP_BY_STEP.md`  
4. Contracts: `IREIOS_4.0_API_CONTRACTS.md` (**FROZEN**)  
5. Evidence: `IREIOS_4.0_EVIDENCE_PACK.md`

## Doc roles

| File | Role |
|------|------|
| `UNIFIED_EXECUTION_ORDER.md` | When / what next |
| `IREIOS_4.0_STEP_BY_STEP.md` | Atomic tasks |
| `IREIOS_4.0_IMPLEMENTATION_PLAN.md` | Macro + design notes §5 |
| `IREIOS_4.0_ARCHITECTURE_DELTA.md` | Deltas only |
| `IREIOS_4.0_API_CONTRACTS.md` | FE/BE contracts |
| `IREIOS_4.0_CHANGELOG.md` | Living log |
| `IREIOS_4.0_EVIDENCE_PACK.md` | Gate proof |
| `TEAM_LEAD_QUESTIONNAIRE_ANSWERED.md` | Decision source of truth |
| `openapi_ireios4.json` | Regen after routes |

## Locked defaults (do not re-open without Mayank)

- Integrate existing spine — no agent rebuild  
- Sales AI: Python · **preview + confirm** · copilot then leads  
- Forecast: heuristic · ₹ Cr · honest label  
- Graph: ego network · embed copilot · SSE refetch  
- Twin: live 40 units · read-only · 30s poll  
- HubSpot: outbound · bi-di 4.1 · flag until key  
- n8n: no new WFs  
- FE: JWT · home `/dashboard` · no Approvals UI  

## No further lead questionnaire

Ops secrets (Q11 all N/A) escalate to **Piyush/Mayank** in parallel — not a plan blocker.
