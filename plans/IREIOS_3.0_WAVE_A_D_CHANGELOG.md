# IREIOS 3.0 — Wave A–D Changelog

Living record of **post-G2 depth fill** (Waves A–D). Parallel to `IREIOS_3.0_EXPANSION_CHANGELOG.md` (Phases 0–10).

- **How (tasks):** `plans/IREIOS_3.0_WAVE_A_D_EXPANSION.md`
- **Order:** `plans/UNIFIED_EXECUTION_ORDER.md` Steps 20–23 + G3 (append when starting)
- **Tests:** `tests/test_e14_wave_a.py` … `tests/test_e17_wave_d.py` (+ extend e2/e3/e6/e8/e11)

## Naming

| Suite | Prefix | Example |
|-------|--------|---------|
| Expansion Phases 0–10 | `test_e0`–`test_e13` | `tests/test_e11_parity.py` |
| Waves A–D | `test_e14`–`test_e17` | `tests/test_e14_wave_a.py` |
| Bug fixes | `test_pN_*` | `tests/test_p5_crm.py` |

## How to maintain (per task)

1. Implement code for the task in `IREIOS_3.0_WAVE_A_D_EXPANSION.md`.
2. Replace skeleton/skip tests with real assertions in the matching `test_e1N_*.py`.
3. Append/update this file (status table + Entry).
4. Flip UNIFIED Steps 20–23 / G3 when a wave exits.
5. Update `AGENTS.md`, `README.md`, integration docs as the plan requires.
6. Regression: `python -m pytest tests/ -q` + `gate_isolation_test.py` when tenant/bus/CRM touched.

**Status legend:** `[ ]` pending · `[~]` in progress · `[x]` done · `[-]` skipped (reason)

---

## Wave A status — Close dead loops + live integrations

**Benefit:** Existing Marketing/CS/AE/integration code paths actually run with real HubSpot/Calendar and event producers.

| ID | Status | Summary | Tests |
|----|--------|---------|-------|
| A.0.1 | `[ ]` | HubSpot real credentials + smoke | manual / ops |
| A.0.2 | `[ ]` | Google Calendar SA + smoke | manual / ops |
| A.0.3 | `[ ]` | n8n instance up (Docker/Cloud) | manual / ops |
| A.1 | `[ ]` | `cron.weekly_report` scheduler job | `test_e14_wave_a.py` |
| A.2 | `[ ]` | Lifecycle event producers + admin inject | `test_e14_wave_a.py` |
| A.3 | `[ ]` | AE `template_type` n8n \| langgraph dispatch | `test_e14_wave_a.py`, `test_e2_automation.py` |
| A.4 | `[ ]` | Schedule `expire_stale_approvals` | `test_e14_wave_a.py` |
| A.5 | `[ ]` | NotificationExecutor admin/manager real notify | `test_e14_wave_a.py`, `test_e3_executors.py` |
| A.6 | `[ ]` | Docs/env for integrations | — |
| **A exit** | `[ ]` | Wave A gate | full suite + isolation |

### Entry — A.0.x (template)

- **Date:**
- **What:**
- **Env:**
- **Smoke evidence:**
- **Tests:**
- **Regression:**

### Entry — A.1 (template)

- **Date:**
- **Files:**
- **Behavior:**
- **Tests:**
- **Regression:** `pytest` N passed; isolation _

### Entry — A.2 (template)

- **Date:**
- **Files:**
- **Events produced:**
- **Tests:**
- **Regression:**

### Entry — A.3 (template)

- **Date:**
- **Files:** `app/automation_engine/engine.py`, …
- **Behavior:** n8n/langgraph branch …
- **Tests:**
- **Regression:**

### Entry — A.4 (template)

- **Date:**
- **Files:** `main.py`
- **Behavior:**
- **Tests:**
- **Regression:**

### Entry — A.5 (template)

- **Date:**
- **Files:** `notification_executor.py`, …
- **Behavior:**
- **Tests:**
- **Regression:**

### Entry — A.6 (template)

- **Date:**
- **Docs touched:**
- **Regression:** n/a

### Entry — Wave A exit

- **Date:**
- **pytest:**
- **isolation / DLQ:**
- **HubSpot/Calendar smoke:**
- **UNIFIED Step 20:** `[ ]` → `[x]`

---

## Wave B status — Deepen Maitri agents

**Benefit:** Sales/CS/Marketing execute on the bus with real customer/ops side effects; AE templates + first n8n workflow.

| ID | Status | Summary | Tests |
|----|--------|---------|-------|
| B.1 | `[ ]` | SalesAgent CEO bus + NBA→AE | `test_e15_wave_b.py`, `test_e6_sales_agent.py` |
| B.2 | `[ ]` | Objection lexicon + memory | `test_e15_wave_b.py` |
| B.3 | `[ ]` | CS `send_whatsapp` templates | `test_e15_wave_b.py`, `test_e11_parity.py` |
| B.4 | `[ ]` | Marketing + market.alert | `test_e15_wave_b.py` |
| B.5 | `[ ]` | Named templates + n8n hot-lead | `test_e15_wave_b.py` |
| B.6 | `[ ]` | Competitor → notify | `test_e15_wave_b.py` |
| B.7 | `[ ]` | `create_task` executor (optional) | `test_e15_wave_b.py` |
| **B exit** | `[ ]` | Wave B gate | full suite + isolation |

### Entry — B.1 … B.7 / B exit (fill when shipping)

_Use same entry shape as Wave A._

---

## Wave C status — Placeholder agents → active

**Benefit:** All six Layer-2 placeholders become real event-driven agents (negotiation, pricing, inventory, onboarding, finance, legal).

| ID | Status | Summary | Tests |
|----|--------|---------|-------|
| C.0 | `[ ]` | `inventory_units` (+ optional pricing_rules) + seed script | `test_e16_wave_c.py` |
| C.1 | `[ ]` | `negotiation_agent` active + HITL | `test_e16_wave_c.py` |
| C.2 | `[ ]` | `pricing_agent` active | `test_e16_wave_c.py` |
| C.3 | `[ ]` | `inventory_agent` active | `test_e16_wave_c.py` |
| C.4 | `[ ]` | `onboarding_agent` active | `test_e16_wave_c.py` |
| C.5 | `[ ]` | `finance_agent` active | `test_e16_wave_c.py` |
| C.6 | `[ ]` | `legal_agent` active | `test_e16_wave_c.py` |
| C.7 | `[ ]` | placeholders.py cleaned; Workflows §10 | `test_e16_wave_c.py` |
| **C exit** | `[ ]` | Wave C gate | full suite + isolation |

### Entry — C.x (fill when shipping)

---

## Wave D status — Forecast, memory, n8n, brochure Approach B

**Benefit:** Honest L4 prediction routes, memory on chat path, ops n8n depth, **WhatsApp PDF document bubbles** (hosted URL + Twilio `MediaUrl`).

| ID | Status | Summary | Tests |
|----|--------|---------|-------|
| D.1 | `[ ]` | Revenue / cancel / inventory / cashflow routes | `test_e17_wave_d.py`, `test_e8_prediction.py` |
| D.2 | `[ ]` | Memory auto-write on WA turn | `test_e17_wave_d.py` |
| D.3 | `[ ]` | n8n workflows 2–3 + docs | manual + `test_e17` mock |
| D.4 | `[ ]` | **Approach B** brochure/floorplan: `resolve_tool_media_url` + AE `media_url` (W1) + text fallback | `test_e17_wave_d.py`, `test_e12`, `test_e5`, `test_e3` |
| D.5 | `[ ]` | Evidence pack + G3 | — |
| **D exit / G3** | `[ ]` | Program wave complete | full suite + isolation + DLQ |

### Entry — D.4 Approach B (template)

- **Date:**
- **Decision:** Approach B (hosted HTTPS PDF/image + Twilio MediaUrl); delivery W1 (AE media + ack TwiML); text fallback when env empty.
- **Files:** `config.py`, `whatsapp_agent.py`, `main.py` (TwiML ack), `.env.example`, docs…
- **Smoke:** sandbox WA “send brochure” → document bubble; empty env → plain text; e12 green.
- **Tests:**
- **Regression:**

### Entry — D.x / G3 (fill when shipping)

---

## Regression log (append-only)

| Date | After task | `pytest tests/` | isolation | DLQ | Notes |
|------|------------|-----------------|-----------|-----|-------|
| _|_ | _ | _ | _ | _ | skeleton |

---

## Deferred (do not track as Wave failure)

| Item | Reason |
|------|--------|
| Meta/Google Ads | Out of scope |
| FE MockSSE cutover | `docs/FRONTEND_BACKLOG.md` — Mayank |
| Monolith dual-path delete | Expansion 10.2/10.3 |
| Full competitor crawl | Keyword MVP only |
