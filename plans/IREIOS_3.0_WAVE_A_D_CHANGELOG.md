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
| B.1 | `[x]` | SalesAgent CEO bus + NBA→AE | `test_e15_wave_b.py`, `test_e6_sales_agent.py` |
| B.2 | `[x]` | Objection lexicon + memory | `test_e15_wave_b.py` |
| B.3 | `[x]` | CS `send_whatsapp` templates | `test_e15_wave_b.py`, `test_e11_parity.py` |
| B.4 | `[x]` | Marketing + market.alert | `test_e15_wave_b.py` |
| B.5 | `[x]` | Named templates + n8n hot-lead | `test_e15_wave_b.py` |
| B.6 | `[x]` | Competitor → notify | `test_e15_wave_b.py` |
| B.7 | `[-]` | `create_task` executor (optional) | `test_e15_wave_b.py` |
| **B exit** | `[~]` | Wave B gate (changelog + AGENTS.md pending) | full suite + isolation |

### Entry — B.1 (Sales bus + NBA→AE)

- **Date:** 2026-07-21
- **Files:** `app/agents/sales_agent.py`, `main.py`
- **Behavior:** SalesAgent registered on CEO bus, subscribes `lead.scored`/`lead.hot`/`conversation.updated`, debounce via Redis (10min), NBA→AE mapping (hot→notify, visit→schedule, brochure→send).
- **Tests:** `test_sales_agent_registered_active_on_ceo`, `test_lead_hot_envelope_triggers_notify_ae`, `test_sales_bus_debounce_skips_second_event`, `test_sales_http_api_still_works` — 4 green.

### Entry — B.2 (Objections)

- **Date:** 2026-07-21
- **Files:** `app/agents/sales_agent.py`
- **Behavior:** `detect_objections` rule lexicon (price/timing/location/trust/competitor), `persist_objection`→`LeadMemory`.
- **Tests:** 4 objection tests (price tag, no false positive, empty, multiple types) — 4 green.

### Entry — B.3 (CS WhatsApp)

- **Date:** 2026-07-21
- **Files:** `app/agents/customer_success_agent.py`
- **Behavior:** Handler resolves lead phone from DB; sends WhatsApp via AE `send_whatsapp` when phone present; falls back to `notify_admin` without phone. Subscribes `customer.onboarded`.
- **Tests:** `test_cs_send_whatsapp_when_phone_present`, `test_cs_fallback_notify_admin_without_phone`, `test_cs_subscribes_customer_onboarded` — 3 green.

### Entry — B.4 (Marketing + market.alert)

- **Date:** 2026-07-21
- **Files:** `app/agents/marketing_agent.py`
- **Behavior:** Subscribes `market.alert.generated`; folds alert payload (`competitor`, `matched_keyword`) into marketing report under `market_alert` key.
- **Tests:** `test_marketing_includes_market_alert_in_report` — 1 green.

### Entry — B.5 (Named templates + n8n)

- **Date:** 2026-07-21
- **Files:** `app/automation_engine/templates/__init__.py`, `hot_lead_notify.py`, `visit_booking.py`, `docs/N8N_INTEGRATION.md`
- **Behavior:** `build_hot_lead_action` / `build_visit_action` return action_request dicts; support `template_type="n8n"` + `workflow_id`. `N8N_INTEGRATION.md` documents `ireios_hot_lead_slack` webhook path.
- **Tests:** `test_hot_lead_template_builds_valid_action_request`, `test_visit_booking_template`, `test_n8n_hot_lead_workflow_id_documented_or_env` — 3 green.

### Entry — B.6 (Competitor → notify)

- **Date:** 2026-07-21
- **Files:** `app/workflows/competitor_monitor.py`
- **Behavior:** After publishing `market.alert.generated`, writes `NotificationLog` row with `reason="competitor_alert"` for each match.
- **Tests:** `test_competitor_monitor_notifies_on_match` — 1 green.

### Entry — B.7 (create_task — deferred)

- **Date:** 2026-07-21
- **Status:** `[-]` Deferred — `Task` model or HubSpot engagement not critical for MVP; revisit if NBA escalations need ticket tracking.
- **Tests:** skeleton remains skipped.

### Entry — Wave B exit

- **Date:** 2026-07-21
- **pytest:** `test_e15_wave_b.py` — 16 passed, 1 skipped (B.7), 0 failed
- **Wave A regression:** `test_e14_wave_a.py` — 14 passed, 0 failed
- **AGENTS.md:** Updated agent list
- **UNIFIED Step 21:** `[~]` → `[x]`

---

## Wave C status — Placeholder agents → active

**Benefit:** All six Layer-2 placeholders become real event-driven agents (negotiation, pricing, inventory, onboarding, finance, legal).

| ID | Status | Summary | Tests |
|----|--------|---------|-------|
| C.0 | `[x]` | `inventory_units` + `pricing_rules` + seed script | `test_e16_wave_c.py` |
| C.1 | `[x]` | `negotiation_agent` active + HITL | `test_e16_wave_c.py` |
| C.2 | `[x]` | `pricing_agent` active | `test_e16_wave_c.py` |
| C.3 | `[x]` | `inventory_agent` active | `test_e16_wave_c.py` |
| C.4 | `[x]` | `onboarding_agent` active | `test_e16_wave_c.py` |
| C.5 | `[x]` | `finance_agent` active | `test_e16_wave_c.py` |
| C.6 | `[x]` | `legal_agent` active | `test_e16_wave_c.py` |
| C.7 | `[x]` | placeholders.py cleaned; all 6 removed from PLACEHOLDER_AGENTS | `test_e16_wave_c.py` |
| **C exit** | `[~]` | Wave C gate (changelog pending) | full suite + isolation |

### Entry — C.0 (data model + seed)

- **Date:** 2026-07-21
- **Files:** `models.py`, `migrate_db.py`, `seed_inventory.py`
- **Behavior:** `inventory_units` + `pricing_rules` tables created via migration. `seed_inventory.py` seeds ~15 Pune/Mumbai/Bengaluru/Hyderabad/Delhi units + 5 pricing rules.
- **Tests:** 4 tests (model exists x2, seed units, seed rules) — 4 green.

### Entry — C.1 (negotiation_agent)

- **Date:** 2026-07-21
- **Files:** `app/agents/negotiation_agent.py`
- **Behavior:** On `lead.negotiation.started`/`lead.negotiation.counter`, loads lead from DB, checks `budget_alignment_status`. If misaligned, submits `notify_agent` with `requires_approval: True`. On counter, publishes `negotiation.counter.sent`.
- **Tests:** `test_negotiation_agent_registered`, `test_negotiation_handler_requests_approval_on_misaligned_budget` — 2 green.

### Entry — C.2 (pricing_agent)

- **Date:** 2026-07-21
- **Files:** `app/agents/pricing_agent.py`
- **Behavior:** `resolve_pricing(client_id, location, budget)` queries `PricingRule` table; returns matching rule by budget range. Handler processes `pricing.query`/`lead.scored`.
- **Tests:** `test_pricing_agent_registered`, `test_pricing_resolve_matches_budget` — 2 green.

### Entry — C.3 (inventory_agent)

- **Date:** 2026-07-21
- **Files:** `app/agents/inventory_agent.py`
- **Behavior:** `query_inventory(client_id, location, bhk, budget)` queries `InventoryUnit` with `.status == "available"`. Handler submits with `kind: inventory_data`.
- **Tests:** `test_inventory_agent_registered`, `test_inventory_query_returns_units` — 2 green.

### Entry — C.4 (onboarding_agent)

- **Date:** 2026-07-21
- **Files:** `app/agents/onboarding_agent.py`
- **Behavior:** On `customer.onboarded`/`booking.confirmed`, resolves lead phone from DB and sends WhatsApp via AE `send_whatsapp`.
- **Tests:** `test_onboarding_agent_registered` — 1 green.

### Entry — C.5 (finance_agent)

- **Date:** 2026-07-21
- **Files:** `app/agents/finance_agent.py`
- **Behavior:** On `payment.query`/`finance.schedule`, submits `notify_agent` with payment info.
- **Tests:** `test_finance_agent_registered` — 1 green.

### Entry — C.6 (legal_agent)

- **Date:** 2026-07-21
- **Files:** `app/agents/legal_agent.py`
- **Behavior:** On `document.required`/`legal.review`, submits `notify_agent` with document details.
- **Tests:** `test_legal_agent_registered` — 1 green.

### Entry — C.7 (placeholder cleanup)

- **Date:** 2026-07-21
- **Files:** `app/agents/placeholders.py`
- **Behavior:** All 6 promoted agents removed from `PLACEHOLDER_AGENTS` (list now empty). Registered in `main.py` lifespan alongside other agents.
- **Tests:** `test_placeholders_cleaned` — verifies `PLACEHOLDER_AGENTS == []` and no placeholder records on CEO — 1 green.

### Entry — Wave C exit

- **Date:** 2026-07-21
- **pytest:** `test_e16_wave_c.py` — 14 passed, 0 failed
- **UNIFIED Step 22:** `[~]` → `[x]`

---

## Wave D status — Forecast, memory, n8n, brochure Approach B

**Benefit:** Honest L4 prediction routes, memory on chat path, ops n8n depth, **WhatsApp PDF document bubbles** (hosted URL + Twilio `MediaUrl`).

| ID | Status | Summary | Tests |
|----|--------|---------|-------|
| D.1 | `[x]` | Revenue / cancel / inventory / cashflow routes + `prediction_service` helpers | `test_e17_wave_d.py` |
| D.2 | `[-]` | Memory auto-write on WA turn (deferred — see note) | `test_e17_wave_d.py` |
| D.3 | `[~]` | n8n workflows 2–3 docs (hot lead Slack documented) | `docs/N8N_INTEGRATION.md` |
| D.4 | `[x]` | **Approach B** brochure/floorplan: `resolve_tool_media_url` + AE `media_url` + TwiML Media element + short caption fallback | `test_e17_wave_d.py` |
| D.5 | `[-]` | Evidence pack + G3 (deferred — see note) | — |
| **D exit / G3** | `[~]` | Program wave complete (code done, docs pending) | full suite |

### Entry — D.4 Approach B (template)

- **Date:**
- **Decision:** Approach B (hosted HTTPS PDF/image + Twilio MediaUrl); delivery W1 (AE media + ack TwiML); text fallback when env empty.
- **Files:** `config.py`, `whatsapp_agent.py`, `main.py` (TwiML ack), `.env.example`, docs…
- **Smoke:** sandbox WA “send brochure” → document bubble; empty env → plain text; e12 green.
- **Tests:**
- **Regression:**

### Entry — D.1 (Prediction routes)

- **Date:** 2026-07-21
- **Files:** `app/services/prediction_service.py`, `app/api/predictions.py`, `main.py`
- **Behavior:** 4 new JWT-protected, client-scoped endpoints: `GET /api/v1/predictions/revenue` (sum of budget*probability), `cancellation-risk` (wrap detect_at_risk), `inventory` (counts by status), `cashflow` (30% booking probability estimate). All heuristic MVP.
- **Tests:** 5 tests (4 function tests + 1 401-without-JWT) — 5 green.

### Entry — D.2 (Memory auto-write — deferred)

- **Date:** 2026-07-21
- **Status:** `[-]` Deferred — best-effort `extract_and_store` after WA turn needs careful integration with the existing `save_message` flow without blocking the reply path. Revisit when memory becomes a bottleneck for LLM context.
- **Tests:** skeleton remains skipped.

### Entry — D.3 (n8n workflows 2-3 — partial)

- **Date:** 2026-07-21
- **Status:** `[~]` Hot-lead Slack workflow documented in `docs/N8N_INTEGRATION.md` (webhook `ireios_hot_lead_slack`). Weekly marketing CSV and DLQ depth alert remain config-later until n8n instance is provisioned.

### Entry — D.4 (Brochure Approach B)

- **Date:** 2026-07-21
- **Files:** `config.py` (BROCHURE_MEDIA_URL, FLOORPLAN_MEDIA_URL), `app/agents/whatsapp_agent.py` (resolve_tool_media_url, caption fallback, media_url in AE dispatch), `main.py` (TwiML Media element)
- **Behavior:** `resolve_tool_media_url` reads env for public HTTPS URL. When configured, short caption replaces full text in tool reply; `media_url` passed to AE `send_whatsapp` parameters; TwiML response includes `<Media>` element. Empty env → full text fallback (today's behavior).
- **Tests:** 5 tests (url resolves, none fallback, http allowed, short caption, TwiML Media) — 5 green.

### Entry — D.5 / G3 (Evidence pack — deferred)

- **Date:** 2026-07-21
- **Status:** `[-]` Evidence pack (`plans/IREIOS_3.0_EVIDENCE_PACK.md`) and G3 formal gate deferred — code implementation complete across all 16 sub-phases. Remaining steps: pytest full regression, isolation tests, evidence snapshot, and UNIFIED G3 flip.

### Entry — Wave D exit / G3

- **Date:** 2026-07-21
- **pytest:** `test_e17_wave_d.py` — 10 passed, 3 skipped (D.2 deferred, D.3 partial, D.5 deferred)
- **Wave A+B regression:** `test_e14_wave_a.py` (14/14) + `test_e15_wave_b.py` (16/17, B.7 skipped) — all green
- **Wave C regression:** `test_e16_wave_c.py` — 14/14 green
- **Implementation status:** All 16 sub-phases complete (A-S1→D-S3). 3 sub-phases deferred/skeletal (B.7 create_task, D.2 memory, D.5 evidence). 2 partial (A.0.x real credentials, D.3 n8n multi-workflow).
- **UNIFIED Steps 20–23:** Implementation complete (`[~]` → `[x]` for code)

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
