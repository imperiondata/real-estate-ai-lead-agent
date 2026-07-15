# IREIOS 3.0 Expansion — Changelog

Living record of expansion implementation work (Steps 8–19 of `UNIFIED_EXECUTION_ORDER.md`), kept parallel to `BUG_FIXES_CHANGELOG.md`.

- **How (design/implementation detail):** `plans/IREIOS_3.0_STEP_BY_STEP_EXPANSION.md`
- **When / order:** `plans/UNIFIED_EXECUTION_ORDER.md`
- **Supporting reference (read-only):** `IREIOS_3.0_Architecture_Diagrams.md`, `IREIOS_3.0_AI_Automation_Workflows.md`, `IREIOS_3.0_IMPLEMENTATION_PLAN.md`

## Naming convention (separation from bug fixes)

| Suite | Prefix | Example | Run independently |
|-------|--------|---------|-------------------|
| Bug fixes (Phases 0–6) | `test_pN_*.py` | `tests/test_p0_safety.py` | `python -m pytest tests/test_p*.py` |
| Expansion (Phases 0–10) | `test_eN_*.py` | `tests/test_e1_eventbus.py` | `python -m pytest tests/test_e*.py` |

The `e` prefix guarantees the two suites never collide and can be collected/run separately. `1b` is preserved as `e1b`.

## How to maintain (per slice)

1. Implement code for the task.
2. Add/expand the matching `tests/test_eN_*.py`.
3. Append/update this file (status table row + entry).
4. Flip the matching Step row (and Gate G2 at the end) in `UNIFIED_EXECUTION_ORDER.md`.
5. Keep the standing bug-fix regression guards green: `gate_isolation_test.py`, `gate_dlq_drill.py` + `dlq_replay.py`, and `task3_runner.py` when Gemini quota allows.

---

## Phase 0 status (Task 0.2 — branch / env hygiene)

| ID | Status | Summary | Tests |
|---|---|---|---|
| 0.2 | `[x]` | Branch/env hygiene; app boots on clean env | `tests/test_e0_env.py` |

### Entry — 0.2 (Step 8)

- **Branch:** work carried on `phase3_expansion` feature branch (created by user; no branch ops performed by agent).
- **Env files:** added expansion placeholders to `.env.example` and local `.env`:
  `EVENT_STREAM_KEY`, `EVENT_CONSUMER_GROUP`, `FEATURE_WHATSAPP_V3`, `FOLLOWUP_ENGINE`, `NEO4J_URI/USER/PASSWORD`, `N8N_BASE_URL/API_KEY`. All default to legacy-safe values (no behavior change).
- **config.py:** `Settings` forbids extra env vars, so the new vars were added as typed `Settings` fields (minimal env plumbing pulled forward from Phase 1.2/1.7) to keep the app importing/booting. Defaults: `EVENT_STREAM_KEY="ireios:events"`, `EVENT_CONSUMER_GROUP="ireios-cg"`, `FEATURE_WHATSAPP_V3=False`, `FOLLOWUP_ENGINE="legacy"`.
- **Docs:** `AGENTS.md` (new "IREIOS 3.0 Expansion Env Vars" section) and `README.md` (`.env Reference` block) updated.
- **Redis:** `docker compose up -d` brings `redis-local` up; `redis.Redis.ping()` returns PONG — Phase 1 bus transport is reachable.
- **Tests:** `tests/test_e0_env.py` replaced skeleton with 5 real checks (branch, env vars present, config importable, Redis reachable, `/health` route registered). All green.
- **Regression:** full suite `python -m pytest tests/` → 152 passed, 11 skipped. No regressions.

---

## Phase 1 status (Tasks 1.1–1.8 — Redis Streams bus, CEO, BaseAgent, EE)

| ID | Status | Summary | Tests |
|---|---|---|---|
| 1.1 | `[x]` | Package skeletons | `tests/test_e1_eventbus.py` |
| 1.2 | `[x]` | Event Bus client (Redis Streams) | `tests/test_e1_eventbus.py` |
| 1.3 | `[x]` | Agent registry | `tests/test_e1_eventbus.py` |
| 1.4 | `[x]` | CEO Orchestrator | `tests/test_e1_eventbus.py` |
| 1.5 | `[ ]` | BaseExecutor + ExecutionEngine skeleton | same |
| 1.6 | `[ ]` | BaseAgent lifecycle | same |
| 1.7 | `[ ]` | Wire lifespan in `main.py` | same |
| 1.8 | `[ ]` | Phase 1 exit gate (durable publish) | same |

### Entry — 1.1 + 1.2 (Step 9, part 1)

- **1.1 Package skeletons:** created empty `__init__.py` for `app/clients`, `app/orchestrator`, `app/agents`, `app/execution_engine`, `app/workflows`, `app/automation_engine`, `app/knowledge_graph`, `app/memory`. Import check passes.
- **1.2 Event Bus client (`app/clients/event_bus_client.py`):** Redis Streams only (transport = `redis.asyncio`, same client style as `main.redis_client`; **no in-process `asyncio.Queue` bus**).
  - `EventBusClient` with `start()` (idempotent; `XGROUP CREATE mkstream`, ignore BUSYGROUP) / `stop()` (cancels loop, closes conns) / `subscribe(event_type, handler)` (+ `"*"` wildcard) / `publish(...)` → `XADD` envelope and returns `event_id`; raises loudly on Redis error (never pretends success).
  - Envelope shape per Architecture Diagrams §4: `event_id, event_type, tenant_id, entity_id, source, timestamp, correlation_id, payload`.
  - Consumer loop reads PEL on startup (crash-safe redelivery, at-least-once) then `XREADGROUP ... ">"`; dispatches to subscribed handlers with `return_exceptions=True` (one handler failure never crashes the loop); `XACK` after handling.
  - **Two separate redis clients** (consumer + publisher) — a blocking consumer read and a concurrent `XADD` on the *same* pool deadlocked the loop; isolated clients fixed it.
  - Module-level singleton `event_bus` (wired into lifespan at Task 1.7).
- **Tests:** `tests/test_e1_eventbus.py` replaced skeleton with 5 real async checks (publish→receive, wildcard, durable redelivery after restart, Redis-down fails loud, handler-failure doesn't kill loop). All green.
- **Regression:** full suite `python -m pytest tests/` → 157 passed, 10 skipped. No regressions. Step 9 stays `[ ]` until Task 1.8 exit gate.

### Entry — 1.3 (Step 9, part 2)

- **Agent registry (`app/orchestrator/agent_registry.py`):** `AgentRecord` dataclass (`agent_id`, `handler`, `subscriptions`, `status`, `last_error`, `last_seen`) + `AgentRegistry` with `register` (upsert; validates `status ∈ {active, placeholder}`), `unregister` (no-op if absent), `get_subscribers(event_type)` (returns active **and** placeholder agents subscribed to the event or `"*"`, sorted by `agent_id` for deterministic dispatch), `list_agents()`, `record_success`/`record_failure` (health tracking used by the CEO in 1.4).
- Module-level singleton `agent_registry` for the CEO to consume (Task 1.4).
- Plain `dict` — safe under asyncio's single thread; no locks.
- **Tests:** 6 new pure (no-Redis) registry checks in `tests/test_e1_eventbus.py` — two agents same event, placeholder still listed, wildcard, unregister, success/failure health, invalid-status rejection. All green.
- **Regression:** full suite `python -m pytest tests/` → 163 passed, 10 skipped. No regressions. Step 9 stays `[ ]` until Task 1.8 exit gate.

### Entry — 1.4 (Step 9, part 3)

- **CEO Orchestrator (`app/orchestrator/ceo_orchestrator.py`):** `CEOOrchestrator` that routes events to registered agents and owns their health.
  - `register_agent(agent_id, handler, capabilities, priority, status)` — registers into the supplied `AgentRegistry` (default module singleton `agent_registry`); stores a handler override map for direct invocation.
  - `bootstrap()` — subscribes the CEO itself as a **single `"*"` wildcard** consumer on the bus (robust to agents that register late, per decided design) so it sees every event and dispatches to active subscribers.
  - `handle_event(event)` — routes to all `get_subscribers(event_type)`; skips `placeholder` status; invokes each handler; on handler raise records `record_failure` and, if a bus is present, publishes a `{agent_id}.failed` event so downstream automation can react. With `bus=None` it runs fully in-process (used for direct/test paths).
  - Module-level singleton `ceo` for lifespan wiring at Task 1.7.
- **Tests:** 4 new CEO checks in `tests/test_e1_eventbus.py` — routes to active agent and skips placeholder, skips placeholder via bus path, publishes `{agent_id}.failed` on handler error (bus path), and direct in-process dispatch with `bus=None` records `last_error`. Plus a fix to the no-bus test assertion (lookup `bad_a` specifically rather than `get_subscribers(...)[0]`). File now 15 tests, all green.
- **Regression:** full suite `python -m pytest tests/` → 167 passed, 10 skipped (163 baseline + 4 CEO tests). No regressions. Step 9 stays `[ ]` until Task 1.8 exit gate.

---

## Phase 1b status (Tasks 1b.1–1b.4 — early SSE + API envelopes)

| ID | Status | Summary | Tests |
|---|---|---|---|
| 1b.1 | `[ ]` | SSE stream endpoint | `tests/test_e1b_sse.py` |
| 1b.2 | `[ ]` | Timeline / KPI envelope stubs | same |
| 1b.3 | `[ ]` | Stub event publisher | same |
| 1b.4 | `[ ]` | Phase 1b exit gate (FE unblocked) | same |

---

## Phase 2 status (Tasks 2.1–2.7 — Automation Engine, HITL, LangGraph/n8n)

| ID | Status | Summary | Tests |
|---|---|---|---|
| 2.1 | `[ ]` | Approval model + migration | `tests/test_e2_automation.py` |
| 2.2 | `[ ]` | HITL module | same |
| 2.3 | `[ ]` | AutomationEngine core | same |
| 2.4 | `[ ]` | LangGraph runner scaffold | same |
| 2.5 | `[ ]` | n8n client scaffold | same |
| 2.6 | `[ ]` | Approve/reject API | same |
| 2.7 | `[ ]` | Phase 2 exit gate | same |

---

## Phase 3 status (Tasks 3.1–3.4 — WhatsApp & CRM executors)

| ID | Status | Summary | Tests |
|---|---|---|---|
| 3.1 | `[ ]` | WhatsAppExecutor | `tests/test_e3_executors.py` |
| 3.2 | `[ ]` | CRMExecutor | same |
| 3.3 | `[ ]` | Calendar + notification executor stubs | same |
| 3.4 | `[ ]` | Phase 3 exit gate | same |

---

## Phase 4 status (Tasks 4.1–4.5 — Follow-up scheduler via AE→EE)

| ID | Status | Summary | Tests |
|---|---|---|---|
| 4.1 | `[ ]` | Port follow-up module | `tests/test_e4_followup.py` |
| 4.2 | `[ ]` | Shadow mode switch | same |
| 4.3 | `[ ]` | Arm FollowUpState on lead events | same |
| 4.4 | `[ ]` | Cut over follow-ups | same |
| 4.5 | `[ ]` | Phase 4 exit gate | same |

---

## Phase 5 status (Tasks 5.1–5.9 — WhatsApp Agent, brochure/floorplan, scoring)

| ID | Status | Summary | Tests |
|---|---|---|---|
| 5.1 | `[ ]` | Feature flag + event publish from webhooks | `tests/test_e5_whatsapp_agent.py` |
| 5.2 | `[ ]` | WhatsAppAgent.fetch_context | same |
| 5.3 | `[ ]` | Pre-checks + analyze helpers | same |
| 5.4 | `[ ]` | RAG + LLM + extract_lead_info tool | same |
| 5.5 | `[ ]` | Brochure & floor plan tools | same |
| 5.6 | `[ ]` | decide → AE + async scoring event | same |
| 5.7 | `[ ]` | Enable v3 path behind flag | same |
| 5.8 | `[ ]` | Default flag + keep legacy fallback | same |
| 5.9 | `[ ]` | Phase 5 exit gate | same |

---

## Phase 6 status (Tasks 6.1–6.4 — CRM automation + Sales AI)

| ID | Status | Summary | Tests |
|---|---|---|---|
| 6.1 | `[ ]` | CRMAutomationWorkflow | `tests/test_e6_crm_sales.py` |
| 6.2 | `[ ]` | SalesAgent | same |
| 6.3 | `[ ]` | create_task executor | same |
| 6.4 | `[ ]` | Phase 6 exit gate | same |

---

## Phase 7 status (Tasks 7.1–7.7 — Neo4j KG + Memory)

| ID | Status | Summary | Tests |
|---|---|---|---|
| 7.1 | `[ ]` | Neo4j infra | `tests/test_e7_graph.py` |
| 7.2 | `[ ]` | Schema v1 | same |
| 7.3 | `[ ]` | Graph API routes | same |
| 7.4 | `[ ]` | Event writers | same |
| 7.5 | `[ ]` | GraphClient for agents | same |
| 7.6 | `[ ]` | Memory store + retrieval | same |
| 7.7 | `[ ]` | Phase 7 exit gate | same |

---

## Phase 8 status (Tasks 8.1–8.5 — Prediction APIs + Marketing/CS/Competitor)

| ID | Status | Summary | Tests |
|---|---|---|---|
| 8.1 | `[ ]` | Prediction API router | `tests/test_e8_prediction.py` |
| 8.2 | `[ ]` | MarketingAgent | same |
| 8.3 | `[ ]` | CustomerSuccessAgent | same |
| 8.4 | `[ ]` | CompetitorMonitorWorkflow | same |
| 8.5 | `[ ]` | Phase 8 exit gate | same |

---

## Phase 9 status (Tasks 9.1–9.8 — Frontend cutover to live SSE/APIs)

| ID | Status | Summary | Tests |
|---|---|---|---|
| 9.1 | `[ ]` | Backend: replace stub producers | `tests/test_e9_fe_cutover.py` |
| 9.2 | `[ ]` | Backend exec chat API | same |
| 9.3 | `[ ]` | FE: API client config | same |
| 9.4 | `[ ]` | FE: replace MockSSEService | same |
| 9.5 | `[ ]` | FE: AI chat real stream | same |
| 9.6 | `[ ]` | FE: KG + Digital Twin data | same |
| 9.7 | `[ ]` | FE: Sales Copilot timeline | same |
| 9.8 | `[ ]` | Phase 9 exit gate | same |

---

## Phase 10 status (Tasks 10.1–10.5 — Placeholders, decommission, evidence)

| ID | Status | Summary | Tests |
|---|---|---|---|
| 10.1 | `[ ]` | Placeholder agents | `tests/test_e10_decommission.py` |
| 10.2 | `[ ]` | Remove dual-path WhatsApp | same |
| 10.3 | `[ ]` | Decommission crm_sync / follow_up direct usage | same |
| 10.4 | `[ ]` | Evidence pack | `plans/IREIOS_3.0_EVIDENCE_PACK.md` |
| 10.5 | `[ ]` | Final gate (commands) | G2 |

---

*Entries for each phase are appended as slices land (same format as `BUG_FIXES_CHANGELOG.md`). Bug-fix suites remain the regression baseline for Gate G1 and must stay green throughout expansion.*
