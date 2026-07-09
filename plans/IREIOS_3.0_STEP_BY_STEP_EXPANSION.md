# IREIOS 3.0 — Step-by-Step Expansion Plan

Atomic implementation tasks for expanding the current codebase into Phase 3.0.

| This doc owns | Does not own |
|---|---|
| Ordered tasks: files, steps, tests, done criteria, rollback | Architecture diagrams → `IREIOS_3.0_Architecture_Diagrams.md` |
| | Agent behavior detail → `IREIOS_3.0_AI_Automation_Workflows.md` |
| | Phase rationale / file tree overview → `IREIOS_3.0_IMPLEMENTATION_PLAN.md` |
| | Serial program order (bugs then expansion) → `UNIFIED_EXECUTION_ORDER.md` |

**How to use**

1. Execute **one task** at a time (or one explicitly marked parallel group).  
2. Run that task’s **Test** commands.  
3. Mark done only when **Done criteria** pass.  
4. Do not start the next phase until the previous phase exit gate passes.  
5. Do **not** decommission old modules until the task that says so.

**Global rules**

- Runtime: `Event → CEO → Agent/Workflow → Automation Engine → Execution Engine → Event`  
- Dual-path until cutover tasks.  
- No silent external I/O (Twilio/HubSpot/etc. only via Execution Engine after Phase 3).  
- All events use Architecture Diagrams §4 names + envelope: `event_id, event_type, tenant_id, entity_id, source, timestamp, correlation_id, payload`.  
- Tenant isolation must never regress (`gate_isolation_test.py`).  
- Prefer small PRs / commits per task or per phase gate.

**Baseline gates (run before Phase 1 and after major cutovers)**

```text
python gate_isolation_test.py
python gate_dlq_drill.py
# When API is up and configured:
# python task3_runner.py
```

**Status legend for tracking:** `[ ]` pending · `[~]` in progress · `[x]` done · `[-]` skipped

---

## Phase 0 — Prerequisites (docs already frozen)

### Task 0.1 — Confirm doc freeze
- **Files:** none (read-only)  
- **Steps:** Confirm the three architecture docs match product intent.  
- **Test:** Manual review.  
- **Done:** Team agrees event catalog + phases 1–10.  
- **Status:** `[x]` (approved before this plan)

### Task 0.2 — Branch / env hygiene
- **Files:** none required  
- **Steps:**  
  1. Create git branch e.g. `feature/ireios-3.0`.  
  2. Ensure `.env` has existing keys; leave room for `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `N8N_BASE_URL`, `N8N_API_KEY`, `FEATURE_WHATSAPP_V3` later.  
  3. Note `TEST_MODE` behavior for Twilio.  
- **Test:** App still boots: `uvicorn main:app` (or project start command).  
- **Done:** Clean branch; app starts.  
- **Status:** `[ ]`

---

## Phase 1 — Event Bus, CEO, BaseAgent, EE skeleton

**Exit gate:** publish → CEO → handler works; EE dispatches known action; unknown action fails; forced failure can write DLQ; app lifespan starts/stops bus without breaking existing routes.

### Task 1.1 — Package skeletons
- **Create:**
  - `app/clients/__init__.py`
  - `app/orchestrator/__init__.py`
  - `app/agents/__init__.py`
  - `app/execution_engine/__init__.py`
  - `app/workflows/__init__.py`
  - `app/automation_engine/__init__.py` (empty ok)
  - `app/knowledge_graph/__init__.py` (empty ok)
  - `app/memory/__init__.py` (empty ok)
- **Steps:** Empty or minimal exports only. Do not change `main.py` yet.  
- **Test:** `python -c "import app.clients, app.orchestrator, app.agents, app.execution_engine"`  
- **Done:** Imports succeed.  
- **Rollback:** Delete new packages.  
- **Status:** `[ ]`

### Task 1.2 — Event Bus client
- **Create:** `app/clients/event_bus_client.py`  
- **Steps:**  
  1. Implement class/module with: `start()`, `async stop()`, `subscribe(event_type, handler)`, `async publish(event_type, tenant_id, entity_id, payload, source="system")`.  
  2. Build event envelope (uuid event_id + correlation_id, UTC timestamp).  
  3. Background `_processing_loop` with `asyncio.Queue`; `asyncio.gather(..., return_exceptions=True)` for handlers.  
  4. Log every publish at INFO (no PII dump of full message body in production if avoidable; entity_id ok).  
  5. `start()` is idempotent; `stop()` cancels processing task safely.  
- **Test:** Standalone script or pytest: subscribe mock → publish → assert handler called once with correct `event_type` and `tenant_id`.  
- **Done:** Unit test green; no dependency on FastAPI.  
- **Status:** `[ ]`

### Task 1.3 — Agent registry
- **Create:** `app/orchestrator/agent_registry.py`  
- **Steps:**  
  1. Store records: `agent_id`, `handler` (callable), `subscriptions: list[str]`, `status: active|placeholder`, `last_error`, `last_seen`.  
  2. Methods: `register(...)`, `unregister`, `get_subscribers(event_type)`, `list_agents()`, `record_success/failure`.  
- **Test:** Register two agents on same event; `get_subscribers` returns both; placeholder still listed.  
- **Done:** Registry unit test green.  
- **Status:** `[ ]`

### Task 1.4 — CEO Orchestrator
- **Create:** `app/orchestrator/ceo_orchestrator.py`  
- **Steps:**  
  1. `register_agent` wraps registry.  
  2. `async handle_event(event)`: resolve subscribers for `event["event_type"]`; invoke active handlers; skip placeholders; record health.  
  3. On handler exception: log, record failure, optionally publish `{agent}.failed` (do not crash bus).  
  4. Wire: bus may call CEO for all events **or** CEO subscribes to `"*"` pattern — prefer: **publish always goes to bus; CEO is a bus subscriber for routed types**, and agents are registered with CEO which subscribes those types on the bus.  
  5. Recommended pattern:  
     - `CEOOrchestrator.bootstrap()` registers itself to forward: for each known subscription type, `EventBusClient.subscribe(type, CEOOrchestrator._dispatch)`.  
     - `_dispatch` → registry handlers.  
- **Test:** Register mock agent on `lead.created` → publish → handler runs. Placeholder not invoked.  
- **Done:** CEO routing unit test green.  
- **Status:** `[ ]`

### Task 1.5 — BaseExecutor + ExecutionEngine skeleton
- **Create:**  
  - `app/execution_engine/base_executor.py`  
  - `app/execution_engine/execution_engine.py`  
- **Steps:**  
  1. `BaseExecutor.execute(action_request) -> dict` abstract.  
  2. `ExecutionEngine.register(action_type, executor)`, `async dispatch(action_request)`.  
  3. Missing executor → `{"status":"error","error":"no_executor"}` (do not raise uncaught in production path).  
  4. On `status=="error"`: write `DLQEvent` via `SessionLocal` (same fields as existing model: `target_endpoint`, `payload`, `error_trace`, `status`, `client_id`).  
  5. On success: `asyncio.create_task(EventBusClient.publish(...))` using a small `_EVENT_MAP` (can be empty map initially; add in Phase 3).  
  6. Do **not** implement Twilio/CRM yet — add a `NoopExecutor` for tests only (or register in tests).  
- **Test:**  
  - Unknown action → error.  
  - Registered noop success → no DLQ.  
  - Registered failing executor → DLQ row (use test DB or sqlite if available; else mock SessionLocal).  
- **Done:** Tests green.  
- **Status:** `[ ]`

### Task 1.6 — BaseAgent lifecycle
- **Create:** `app/agents/base_agent.py`  
- **Steps:**  
  1. Abstract `fetch_context`, `analyze`, `decide`.  
  2. `process_event`: try lifecycle; if `decide` returns action_request, call **temporary** path:  
     - Phase 1 only: `ExecutionEngine.dispatch` **or** a stub `AutomationEngine.submit` that forwards to EE (prefer stub file `app/automation_engine/engine.py` with `submit = forward to EE` so Phase 2 only fills in).  
  3. On exception: log + publish `{ClassName}.failed`.  
  4. Pass `event` into all lifecycle methods.  
- **Create:** `app/automation_engine/engine.py` with:

  ```text
  async def submit(action_request) -> dict:
      # Phase 1: forward only
      return await ExecutionEngine.dispatch(action_request)
  ```

- **Test:** Concrete test agent returns `send_test` action → noop executor → success.  
- **Done:** Lifecycle unit test green.  
- **Status:** `[ ]`

### Task 1.7 — Wire lifespan in main.py
- **Edit:** `main.py`  
- **Steps:**  
  1. In `lifespan`: `EventBusClient.start()` before scheduler; on shutdown `await EventBusClient.stop()` after scheduler shutdown.  
  2. Call `CEOOrchestrator.bootstrap()` (no agents yet ok).  
  3. Do **not** change webhook behavior yet.  
- **Test:** Start app; hit `/health` (or existing health); shutdown clean (no hanging tasks).  
- **Done:** Existing endpoints still work; logs show bus started.  
- **Status:** `[ ]`

### Task 1.8 — Phase 1 exit gate
- **Steps:** Re-run isolation + DLQ drill if env allows; smoke all critical routes manually once.  
- **Done:** Checklist: bus, CEO, BaseAgent, EE skeleton, lifespan.  
- **Status:** `[ ]`

---

## Phase 2 — Automation Engine, HITL, LangGraph/n8n hooks

**Exit gate:** `requires_approval=true` does not execute until approve; reject path logs; retry policy works; approve/reject HTTP APIs work with auth.

### Task 2.1 — Approval model + migration
- **Edit:** `models.py`, `migrate_db.py` (or Alembic if present — this repo uses `migrate_db.py`)  
- **Steps:**  
  1. Add `ApprovalRequest` table: `id`, `client_id`, `entity_id`, `action_type`, `action_payload` (JSONB), `status` (`pending|approved|rejected|expired`), `requested_by`, `resolved_by`, `reason`, `correlation_id`, timestamps.  
  2. Migration safe for existing DBs.  
- **Test:** App boots; table exists.  
- **Done:** Migration applied on dev DB.  
- **Status:** `[ ]`

### Task 2.2 — HITL module
- **Create:** `app/automation_engine/hitl.py`  
- **Steps:**  
  1. `async request_approval(action_request, tenant_id, ...) -> approval_id` — persist pending; publish `approval.requested`.  
  2. `async resolve(approval_id, decision, manager_id, reason=None)` — set status; publish `approval.resolved`; if approved return action_request for resume.  
  3. Notify manager: reuse `notification_service` or NotificationExecutor stub (log + optional WhatsApp later).  
- **Test:** request → pending row; resolve approve/reject transitions.  
- **Done:** Unit/integration tests green.  
- **Status:** `[ ]`

### Task 2.3 — AutomationEngine core
- **Edit:** `app/automation_engine/engine.py`  
- **Steps:**  
  1. `submit(action_request)`:  
     - Validate required keys: `action_type`, `tenant_id`, `entity_id`, `parameters` (dict).  
     - Read `requires_approval` (bool) and optional `template_type` (`linear|langgraph|n8n`).  
     - If approval required → HITL pause; return `{"status":"pending_approval","approval_id":...}`.  
     - Else → `_execute_with_retry` → `ExecutionEngine.dispatch`.  
  2. Retry: up to 3 attempts, exponential backoff (async sleep); then optional `fallback_action` in request; then DLQ already handled by EE.  
  3. Default template_type = `linear`.  
- **Test:**  
  - Valid linear success.  
  - Invalid request rejected without EE call.  
  - Approval short-circuits EE.  
  - Failing executor retried N times (mock).  
- **Done:** Tests green; BaseAgent uses `AutomationEngine.submit` only.  
- **Status:** `[ ]`

### Task 2.4 — LangGraph runner scaffold
- **Create:** `app/automation_engine/langgraph_runner.py`  
- **Deps:** Add `langgraph` (and minimal langchain deps if required) to `requirements.txt`.  
- **Steps:**  
  1. Minimal graph: `plan → (hitl checkpoint) → execute` that can pause with state dict serializable to JSON.  
  2. `run_graph(action_request) -> result`; `resume_graph(state, approval_decision)`.  
  3. If langgraph not installed in CI, guard import with clear error.  
- **Test:** Unit test of linear graph without external APIs.  
- **Done:** Scaffold importable; one unit test.  
- **Status:** `[ ]`

### Task 2.5 — n8n client scaffold
- **Create:** `app/automation_engine/n8n_client.py`  
- **Steps:**  
  1. Config: `N8N_BASE_URL`, `N8N_API_KEY` in `config.py` / settings.  
  2. `async trigger_workflow(workflow_id, payload) -> dict` via httpx.  
  3. If URL missing: return `{"status":"error","error":"n8n_not_configured"}` (no crash).  
- **Test:** Mock httpx response.  
- **Done:** Client exists; safe when unconfigured.  
- **Status:** `[ ]`

### Task 2.6 — Approve/reject API
- **Edit:** `main.py`  
- **Steps:**  
  1. `POST /api/v1/approvals/{id}/approve` and `/reject` with manager/client auth (reuse `get_current_client` or agent manager flag).  
  2. Call HITL resolve → if approved, `AutomationEngine.resume` / submit without approval flag.  
- **Test:** Manual or httpx: create pending via unit helper → approve → EE mock called.  
- **Done:** Endpoints documented in OpenAPI.  
- **Status:** `[ ]`

### Task 2.7 — Phase 2 exit gate
- **Done:** HITL + AE retry + scaffolds green; existing chat still on old path.  
- **Status:** `[ ]`

---

## Phase 3 — WhatsApp & CRM executors

**Exit gate:** `send_whatsapp` and `update_crm` work via EE; CRM tenacity preserved; success events published; old `crm_sync.sync_lead_to_crm` still callable until cutover task.

### Task 3.1 — WhatsAppExecutor
- **Create:** `app/execution_engine/whatsapp_executor.py`  
- **Steps:**  
  1. Port Twilio `messages.create` from existing code (`TEST_MODE` short-circuit).  
  2. Support `parameters`: `phone`, `message`, optional `media_url`.  
  3. Return `{status, sid}` or `{status:error, error}`.  
  4. Register `send_whatsapp`; event map → `whatsapp.sent`.  
- **Test:** `TEST_MODE=true` dispatch success; media_url accepted in kwargs.  
- **Done:** No Twilio import needed outside executor for new code.  
- **Status:** `[ ]`

### Task 3.2 — CRMExecutor
- **Create:** `app/execution_engine/crm_executor.py`  
- **Steps:**  
  1. Move/copy `_push_to_hubspot` + tenacity from `crm_sync.py` (keep `crm_sync.py` as thin wrapper calling executor **or** leave old function intact and copy logic — prefer **copy then later thin-wrap** to avoid break).  
  2. Register `update_crm` → event `lead.crm_synced`.  
- **Test:** Mock httpx 429 → retries; success returns external_id.  
- **Done:** Executor registered.  
- **Status:** `[ ]`

### Task 3.3 — Optional calendar + notification executor stubs
- **Create:**  
  - `calendar_executor.py` — log/store visit; publish readiness for `site_visit.scheduled`  
  - `notification_executor.py` — wrap `notification_service` patterns  
- **Register:** `schedule_visit`, `notify_agent` / `notify_admin`  
- **Test:** TEST_MODE style success.  
- **Done:** Stubs callable (can be minimal).  
- **Status:** `[ ]`

### Task 3.4 — Phase 3 exit gate
- **Done:** EE action types documented; DLQ still works for forced Twilio failure.  
- **Status:** `[ ]`

---

## Phase 4 — Follow-up scheduler via AE→EE

**Exit gate:** New scheduler sends only through AE→EE; state machine parity; old job disabled only after shadow compare.

### Task 4.1 — Port follow-up module
- **Create:** `app/workflows/followup_scheduler.py`  
- **Steps:**  
  1. Copy `resolve_current_followup_stage`, `generate_followup_payload`, `apply_quiet_hours`, `check_and_send_followups` logic from `follow_up.py`.  
  2. Replace Twilio client calls with:

     ```text
     await AutomationEngine.submit({
       "action_type": "send_whatsapp",
       "tenant_id": ...,
       "entity_id": ...,
       "parameters": {"phone": ..., "message": ...},
     })
     ```

  3. On success publish/log `followup.sent` (EE may already publish `whatsapp.sent`; also emit `followup.sent` with stage metadata).  
  4. Remove direct DLQ writes if EE handles them.  
- **Test:** Unit tests for quiet hours + stage resolution (pure functions).  
- **Done:** Module has **no** `from twilio` import.  
- **Status:** `[ ]`

### Task 4.2 — Shadow mode switch
- **Edit:** `main.py` scheduler jobs  
- **Steps:**  
  1. Add setting `FOLLOWUP_ENGINE=legacy|v3|shadow`.  
  2. `legacy`: old `follow_up.check_and_send_followups`.  
  3. `v3`: new workflow only.  
  4. `shadow`: run new in dry-run (build payload, log, do not send) alongside old — optional if timeboxed.  
- **Test:** With `v3` + TEST_MODE, due follow-up creates success path.  
- **Done:** Default remains `legacy` until Task 4.3.  
- **Status:** `[ ]`

### Task 4.3 — Arm FollowUpState on lead events
- **Steps:**  
  1. Subscribe handler for `lead.created` (and activity re-arm) to ensure FollowUpState exists (logic already partly in agent — keep consistent).  
  2. Document who owns re-arm after WhatsApp reply (Phase 5 will publish event).  
- **Test:** Creating lead state via handler.  
- **Done:** No duplicate FollowUpState rows (unique session_id).  
- **Status:** `[ ]`

### Task 4.4 — Cut over follow-ups
- **Steps:** Set default `FOLLOWUP_ENGINE=v3` after validation; keep `follow_up.py` importable for rollback.  
- **Test:** 24h staging or simulated due rows.  
- **Done:** Production path uses v3.  
- **Status:** `[ ]`

### Task 4.5 — Phase 4 exit gate
- **Status:** `[ ]`

---

## Phase 5 — WhatsApp Agent, brochure/floorplan, scoring

**Exit gate:** Feature-flagged v3 chat path matches task3; brochure/floorplan tools work; scoring async; old `process_chat` remains fallback.

### Task 5.1 — Feature flag + event publish from webhooks (non-breaking)
- **Edit:** `main.py`  
- **Steps:**  
  1. Setting `FEATURE_WHATSAPP_V3=false` by default.  
  2. On WhatsApp webhook: always publish `whatsapp.received` (for timeline later) **and** if flag false call `agent.process_chat` as today.  
  3. Preserve signature validation, WebhookLog dedupe, Redis lock, 15s timeout + background push.  
- **Test:** Flag false → identical behavior to pre-change.  
- **Done:** task3 still passes on legacy path.  
- **Status:** `[ ]`

### Task 5.2 — WhatsAppAgent.fetch_context
- **Create:** `app/agents/whatsapp_agent.py` (skeleton)  
- **Steps:** Port session/lead create-lookup, FollowUpState ensure, history window (last N turns) from `agent.py`.  
- **Test:** Unit test with DB fixtures or integration.  
- **Done:** Context dict stable keys: `session`, `lead`, `history`, `phone`, `client_id`.  
- **Status:** `[ ]`

### Task 5.3 — Pre-checks + analyze helpers
- **Steps:** Port opt-out, guardrail (`check_topic_drift`), human handoff, instant-reply, property-intent intercepts into private methods.  
- **Test:** Guardrail unit tests; handoff triggers notification path.  
- **Done:** Behavior parity with legacy for those intercepts.  
- **Status:** `[ ]`

### Task 5.4 — RAG + LLM + extract_lead_info tool
- **Steps:**  
  1. Port RAG gateway eligibility + `retrieve`.  
  2. Port Gemini chat retries + tool `extract_lead_info` / normalize_lead_data.  
  3. Persist messages.  
- **Test:** Integration with TEST_MODE / mocked LLM if available; else careful live Gemini test.  
- **Done:** Reply text produced without calling Twilio inside agent.  
- **Status:** `[ ]`

### Task 5.5 — Brochure & floor plan tools
- **Edit:** `system_prompt.py`, WhatsAppAgent tools  
- **Steps:**  
  1. **System prompt** — insert FAQ & document rules (before TOOL USE RULE):  
     - FAQ (amenities, hospitals, maintenance, pricing): answer via RAG / property context; **do not** use document tools.  
     - Brochure/catalog/PDF ask → `share_brochure` tool.  
     - Floor plan/layout/map/dimensions ask → `share_floor_plan` tool.  
     - If document requested but location/project missing → ask location first.  
  2. **Tools** (register with Gemini alongside `extract_lead_info`):  
     - `share_brochure(location, property_type, conversational_reply)`  
     - `share_floor_plan(location, property_type, conversational_reply)`  
  3. Expand property/RAG keyword set with brochure, floor plan, amenities-related terms as needed.  
  4. **decide / EE:** build `send_whatsapp` with `message` + `media_url` from config/document map (not hardcoded dummy URLs in prod). **No** direct Twilio in the agent.  
  5. On success publish `brochure.sent` / `floorplan.sent` via ExecutionEngine event map or bus after EE success.  
  6. Use real `EventBusClient` only — never a stub HTTP mock event bus.  
- **Test:** User asks “send brochure” with location → media action; without location → clarifying question; FAQ amenities → RAG path not document tool.  
- **Done:** Media path through AE→EE; events published; no direct Twilio in agent.  
- **Status:** `[ ]`

### Task 5.6 — decide → AE + async scoring event
- **Steps:**  
  1. `decide` returns `send_whatsapp` action_request.  
  2. After decision, publish `whatsapp.response.generated` (do not await scoring).  
  3. On qualification complete publish `lead.qualified` / ensure `lead.created` once.  
- **Create:** `app/agents/lead_scoring_handler.py` — call `calculate_lead_score`, budget alignment, optional match; publish `lead.scored` / `lead.hot`.  
- **Register** handler with CEO on `whatsapp.response.generated`.  
- **Test:** Scoring not on critical path (time mock); hot threshold fires notification.  
- **Done:** Handler registered; agent does not import heavy scoring in decide.  
- **Status:** `[ ]`

### Task 5.7 — Enable v3 path behind flag
- **Edit:** `main.py`  
- **Steps:**  
  1. When `FEATURE_WHATSAPP_V3=true`: CEO routes `whatsapp.received` / `chat.received` to WhatsAppAgent; return reply for TwiML (agent must expose reply text — either return from `process_event` or store on context/result channel).  
  2. **Design note:** WhatsApp webhook needs reply string within 15s. Implement `WhatsAppAgent.process_event` to return `analysis["reply_text"]` (extend BaseAgent return value) **or** use a response buffer keyed by correlation_id. Prefer **return reply_text from process_event** for WA/chat.  
- **Test:** Flag true + task3_runner (subset then full).  
- **Done:** task3 green on v3.  
- **Status:** `[ ]`

### Task 5.8 — Default flag + keep legacy fallback
- **Steps:** Document rollback: set `FEATURE_WHATSAPP_V3=false`. Do not delete `agent.py` yet.  
- **Done:** Runbook note in this file status section.  
- **Status:** `[ ]`

### Task 5.9 — Phase 5 exit gate
- **Commands:** `python task3_runner.py`, `python gate_isolation_test.py`  
- **Status:** `[ ]`

---

## Phase 6 — CRM automation + Sales AI

**Exit gate:** `lead.qualified` → tags/assign/CRM; Sales reacts to `lead.scored` with NBA/tasks; HITL for risky actions.

### Task 6.1 — CRMAutomationWorkflow
- **Create:** `app/workflows/crm_automation.py`  
- **Steps:** On `lead.created` / `lead.qualified` / `lead.scored`: classify, tags, `match_best_agent`, build `update_crm` + assignment; AE→EE; publish `lead.assigned` when assigned.  
- **Register** with CEO.  
- **Test:** Fixture lead → assigned_agent set; CRM executor called (mock).  
- **Done:** No duplicate assign storms (idempotent per lead version).  
- **Status:** `[ ]`

### Task 6.2 — SalesAgent
- **Create:** `app/agents/sales_agent.py`  
- **Steps:** Subscriptions: `lead.scored`, `conversation.updated`, `lead.hot`. Objection + priority + NBA; actions: `create_task`, `schedule_visit`, `send_whatsapp`, `notify_agent`; set `requires_approval` for discounts.  
- **Test:** Mock analysis path or scripted event.  
- **Done:** CEO registration; HITL path smoke-tested.  
- **Status:** `[ ]`

### Task 6.3 — create_task executor (if missing)
- **Steps:** Persist task to DB or CRM; minimal model if needed (`tasks` table) or HubSpot task via CRM executor parameters.  
- **Done:** Sales `create_task` does not no-op silently — either real write or explicit TODO log **only in placeholder mode** (prefer real write).  
- **Status:** `[ ]`

### Task 6.4 — Phase 6 exit gate
- **Status:** `[ ]`

---

## Phase 7 — Neo4j Knowledge Graph + Memory

**Exit gate:** Schema migrated; Graph APIs secured by tenant; async writers on core events; agents can fetch graph context with Postgres fallback.

### Task 7.1 — Neo4j infra
- **Edit:** `docker-compose.yml`, `config.py`, `.env.example`  
- **Steps:** Add Neo4j service + `NEO4J_URI/USER/PASSWORD`.  
- **Deps:** `neo4j` driver in `requirements.txt`.  
- **Test:** `docker compose up neo4j` (or equivalent); driver verifies connectivity.  
- **Done:** Documented in `.env.example`.  
- **Status:** `[ ]`

### Task 7.2 — Schema v1
- **Create:** `app/knowledge_graph/schema/v1.cypher` (or Python migrate script)  
- **Steps:** Constraints/indexes for PDF entities; relationship types from Architecture Diagrams §5.  
- **Create:** `app/knowledge_graph/neo4j_client.py` — session helper, run_query, health.  
- **Create:** migrate command or startup optional migrate.  
- **Test:** Migrate on empty DB twice (idempotent).  
- **Done:** Version marker node e.g. `(:SchemaVersion {version:1})`.  
- **Status:** `[ ]`

### Task 7.3 — Graph API routes
- **Create:** `app/knowledge_graph/graph_api.py`  
- **Mount in:** `main.py`  
- **Endpoints (minimum):**  
  - `GET /api/v1/graph/health`  
  - `GET /api/v1/graph/leads/{id}/context`  
  - `POST /api/v1/graph/upsert` (internal/service auth)  
- **Test:** Auth required; tenant cannot read other tenant.  
- **Done:** OpenAPI shows routes.  
- **Status:** `[ ]`

### Task 7.4 — Event writers
- **Create:** `app/knowledge_graph/event_writers.py`  
- **Steps:** Subscribe (via CEO or bus) to `lead.created`, `lead.qualified`, `lead.assigned`, `site_visit.scheduled`, `whatsapp.sent`, `payment.received`, `booking.confirmed` — upsert nodes/edges **async**.  
- **Test:** Publish event → node exists; publisher returns before write completes (async).  
- **Done:** Failure in writer logs + optional DLQ; does not fail agent.  
- **Status:** `[ ]`

### Task 7.5 — GraphClient for agents
- **Create:** `app/clients/graph_client.py`  
- **Steps:** `get_lead_context(lead_id, tenant_id)`; on Neo4j down return `{}` and log (Postgres remains SoT).  
- **Wire:** WhatsAppAgent/SalesAgent fetch_context optional merge.  
- **Test:** Mock client; timeout behavior.  
- **Done:** No hard dependency crash if Neo4j down.  
- **Status:** `[ ]`

### Task 7.6 — Memory store + retrieval
- **Create:** `app/memory/memory_store.py`, `retrieval.py`  
- **Steps:**  
  1. Persist decision/action records (table or JSONB).  
  2. Conversation = existing messages.  
  3. Long-term = lead fields + objections list.  
  4. `retrieve_context(tenant_id, entity_id, query)` merges memory + optional graph.  
- **API (optional thin):** internal functions first; REST if FE needs.  
- **Test:** Write decision → retrieve.  
- **Done:** Agents can call retrieval without circular imports.  
- **Status:** `[ ]`

### Task 7.7 — Phase 7 exit gate
- **Status:** `[ ]`

---

## Phase 8 — Prediction APIs + Marketing + CS + Competitor

**Exit gate:** Prediction routes tenant-scoped; three agents/workflows registered; competitor cron emits `market.alert.generated`.

### Task 8.1 — Prediction API router
- **Create:** e.g. `app/prediction/api.py` or routes in `main.py`  
- **Endpoints:**  
  - `GET/POST .../predictions/lead-score`  
  - `.../booking`  
  - `.../revenue`  
  - `.../cancellation-risk`  
  - `.../cashflow`  
  - `.../inventory`  
- **Steps:** Wrap `app/intelligence` where possible; else explicit heuristic or `501` with `{"status":"not_implemented","model":"..."}` — **never fake high confidence**.  
- **Test:** Auth + tenant isolation; lead-score returns real scoring for known lead.  
- **Done:** Documented response shapes.  
- **Status:** `[ ]`

### Task 8.2 — MarketingAgent
- **Create:** `app/agents/marketing_agent.py`  
- **Register** on `campaign.completed`, `cron.weekly_report` (publish cron event from scheduler).  
- **HITL** for spend changes.  
- **Test:** Weekly cron fires report path (notify_admin).  
- **Status:** `[ ]`

### Task 8.3 — CustomerSuccessAgent
- **Create:** `app/agents/customer_success_agent.py`  
- **Subscriptions:** `payment.due`, `payment.received`, `booking.confirmed`, `document.pending`, `renewal.due` (emit stubs from admin/cron as needed).  
- **Test:** `booking.confirmed` → reminder action_request.  
- **Status:** `[ ]`

### Task 8.4 — CompetitorMonitorWorkflow
- **Create:** `app/workflows/competitor_monitor.py`  
- **Scheduler:** midnight or configurable cron in `main.py`.  
- **Publish:** `market.alert.generated` when change detected (start with mock data source).  
- **Test:** Force change → event published.  
- **Status:** `[ ]`

### Task 8.5 — Phase 8 exit gate
- **Status:** `[ ]`

---

## Phase 9 — Frontend wire (backend contracts + Mayank UI)

**Exit gate:** MVP pages no longer depend on mock SSE/chat for happy path; backend SSE + graph + chat APIs stable.

### Task 9.1 — Backend SSE stream
- **Edit:** `main.py`  
- **Steps:**  
  1. `GET /api/v1/events/stream` (SSE) authenticated by tenant.  
  2. Bridge: EventBus handlers for dashboard-relevant events push to per-tenant queues.  
  3. Heartbeat comments every N seconds.  
- **Test:** `curl -N` stream; publish test event → client receives JSON.  
- **Done:** Envelope matches FE expectations (document fields).  
- **Status:** `[ ]`

### Task 9.2 — Backend executive chat API (optional thin)
- **Steps:** `POST /api/v1/executive/chat` → CEO/agent channel or WhatsAppAgent-like with admin context; stream or JSON reply.  
- **Test:** Auth required; tenant scoped.  
- **Status:** `[ ]`

### Task 9.3 — FE: API client config
- **Owner:** Mayank (coordinate)  
- **Files:** `frontend/src/lib/api/*`  
- **Steps:** Base URL + API key/JWT from env; remove hard mock-only paths behind `NEXT_PUBLIC_USE_MOCKS=false`.  
- **Done:** Flag switches mock vs real.  
- **Status:** `[ ]`

### Task 9.4 — FE: Replace MockSSEService
- **Files:** `frontend/src/lib/api/mockService.ts`, dashboard-mvp page  
- **Steps:** Real EventSource/fetch stream to `/api/v1/events/stream`.  
- **Done:** KPI/alert pulse from backend test publish.  
- **Status:** `[ ]`

### Task 9.5 — FE: AI chat real stream
- **Files:** `mockChatService.ts`, ai-chat page  
- **Steps:** Call executive chat or token stream API; tool-call UI can map graph tool names from real events.  
- **Status:** `[ ]`

### Task 9.6 — FE: Knowledge Graph + Digital Twin data
- **Steps:** Fetch `/api/v1/graph/...` for viz; twin uses graph snapshot + recent events.  
- **Status:** `[ ]`

### Task 9.7 — FE: Sales Copilot timeline
- **Steps:** Timeline from events API or lead-scoped event list endpoint (add `GET /api/v1/leads/{id}/timeline` if needed — **backend task** if missing).  
- **If missing endpoint:** do Task 9.7b backend first.  
- **Status:** `[ ]`

### Task 9.7b — Backend lead timeline API (if needed)
- **Steps:** Query EventLog + bus projections + memory actions for lead/session.  
- **Status:** `[ ]`

### Task 9.8 — Phase 9 exit gate
- **Done:** Demo script: inbound WA (or chat) → dashboard SSE update → graph node → timeline entry.  
- **Status:** `[ ]`

---

## Phase 10 — Placeholders, decommission, evidence

**Exit gate:** Placeholders registered; legacy modules unused; gates green; deliverable checklist filled.

### Task 10.1 — Placeholder agents
- **Create:** `app/agents/placeholders.py`  
- **Steps:** Register remaining Layer-2 names (Pricing, Negotiation, Inventory, Legal, etc.) with `status=placeholder`, no-op handler or log-only.  
- **Done:** `CEOOrchestrator.list_agents()` shows active + placeholders.  
- **Status:** `[ ]`

### Task 10.2 — Remove dual-path WhatsApp
- **Steps:** Default `FEATURE_WHATSAPP_V3=true`; delete dead call paths carefully; keep `agent.py` only if still imported — then move any shared helpers to `app/` and deprecate root `agent.py`.  
- **Test:** Full task3 + isolation + DLQ.  
- **Done:** No production code path calls `process_chat` except explicit legacy flag.  
- **Status:** `[ ]`

### Task 10.3 — Decommission crm_sync / follow_up direct usage
- **Steps:**  
  1. `crm_sync.sync_lead_to_crm` → thin wrapper to EE or delete callers.  
  2. `follow_up.py` → re-export from workflow or delete after imports cleaned.  
- **Test:** Grep repo for `from crm_sync` / `from follow_up` / `process_chat` — only tests/docs remain.  
- **Done:** Grep clean for production imports.  
- **Status:** `[ ]`

### Task 10.4 — Evidence pack
- **Create folder:** e.g. `docs/ireios_3_evidence/` or fill assignment report  
- **Include:**  
  - API list (OpenAPI export)  
  - Graph schema export  
  - Test logs (task3, isolation, DLQ)  
  - Architecture diagrams link  
  - Integration notes (Neo4j, n8n, Twilio)  
  - Deployment steps  
- **Done:** Checklist matches PDF deliverables.  
- **Status:** `[ ]`

### Task 10.5 — Final gate (commands)

```text
python gate_isolation_test.py
python gate_dlq_drill.py
python task3_runner.py
# health + graph health + SSE smoke
```

- **Done:** Commands green; then complete **Program final gate (G2)** below.  
- **Status:** `[ ]`

---

## Program final gate (G2)

Used by `UNIFIED_EXECUTION_ORDER.md` Gate **G2**. Mark complete only when **all** items pass.

### Architecture & cutover

- [ ] Expansion Phases 1–10 exit gates are all done (or explicitly `[-]` with reason)
- [ ] Runtime path is `Event → CEO → Agent/Workflow → AE → EE → Event` for new work
- [ ] `FEATURE_WHATSAPP_V3` default documented for production; rollback `false` still works until dual-path removed
- [ ] Follow-up on `FOLLOWUP_ENGINE=v3` (or intentional legacy only with written reason)
- [ ] CEO registry lists active agents (WhatsApp, Sales, Marketing, CS, CRM automation, Competitor, scoring handler) and Layer-2 placeholders
- [ ] Production code does not import decommissioned monolith paths (`process_chat` / direct `crm_sync` / direct `follow_up` Twilio) except documented rollback flag

### Data, graph, memory

- [ ] Neo4j schema migrated; `GET /api/v1/graph/health` ok
- [ ] Graph lead-context query works for a known lead (tenant-scoped)
- [ ] Async graph writers do not block chat path
- [ ] Memory decision/action write + retrieve smoke ok

### APIs & realtime

- [ ] Prediction routes: auth required, tenant-scoped; lead-score returns real scoring for known lead
- [ ] SSE: authenticated stream receives a published test event
- [ ] Approve/reject APIs work for a pending HITL action (if HITL used in demo)

### Quality gates (commands)

- [ ] `python gate_isolation_test.py`
- [ ] `python gate_dlq_drill.py` (+ replay path as applicable)
- [ ] `python task3_runner.py` (v3 path when flag on)
- [ ] App `/health` (or equivalent) ok
- [ ] Graph health + SSE smoke ok

### Evidence (Task 10.4)

- [ ] OpenAPI / API list exported
- [ ] Graph schema export attached
- [ ] Test logs retained (task3, isolation, DLQ)
- [ ] Architecture + workflow + implementation links in evidence pack
- [ ] Integration notes (Neo4j, n8n, Twilio, flags)
- [ ] Deployment steps documented

**G2 status:** `[ ]`

---

## Parallelism cheat sheet

| Can start early | Depends on |
|---|---|
| 7.1 Neo4j docker | Nothing (after 0.2) |
| 7.2 schema | 7.1 |
| 9.1 SSE design | Phase 1 bus |
| 2.4/2.5 scaffolds | Phase 1 |
| FE 9.3 env work | Backend URL known |
| Must not parallel with cutover | 5.7–5.8, 4.4, 10.2–10.3 |

---

## Suggested commit cadence

| After tasks | Commit message example |
|---|---|
| 1.1–1.8 | `feat(ireios): event bus, CEO orchestrator, EE skeleton` |
| 2.x | `feat(ireios): automation engine and HITL approvals` |
| 3.x | `feat(ireios): whatsapp and CRM executors` |
| 4.x | `feat(ireios): follow-up scheduler via execution engine` |
| 5.x | `feat(ireios): whatsapp agent v3 and document tools` |
| 6.x | `feat(ireios): CRM automation and sales agent` |
| 7.x | `feat(ireios): neo4j knowledge graph and memory` |
| 8.x | `feat(ireios): prediction APIs and remaining agents` |
| 9.x | `feat(ireios): wire frontend to SSE and graph APIs` |
| 10.x | `feat(ireios): decommission monolith paths and evidence` |

---

## Quick reference — event → first consumer

| Event | First consumer |
|---|---|
| `whatsapp.received` / `chat.received` | CEO → WhatsAppAgent |
| `whatsapp.response.generated` | LeadScoringHandler |
| `lead.created` / `lead.qualified` | CRMAutomation + KG writer + Follow-up arm |
| `lead.scored` / `lead.hot` | SalesAgent (+ notify) |
| `lead.assigned` | KG + Dashboard SSE |
| `approval.requested` | Managers / FE |
| `market.alert.generated` | Marketing/Sales + Dashboard |
| `followup.sent` / `whatsapp.sent` | Memory + Timeline SSE |

---

## Rollback cheat sheet

| Problem | Action |
|---|---|
| WA v3 bad replies | `FEATURE_WHATSAPP_V3=false` |
| Follow-up spam/miss | `FOLLOWUP_ENGINE=legacy` |
| Neo4j down | GraphClient returns {}; writers log only |
| n8n down | AE uses linear/LangGraph; n8n actions error cleanly |
| HITL stuck | Expire pending approvals job; manual reject |

---

## Immediate next action

**Do not start this plan until** `UNIFIED_EXECUTION_ORDER.md` Gate **G1** is complete (all bug-audit phases first).

After G1: Expansion Task **0.2**, then **1.1**. Do not skip phase exit gates.

When implementing with an AI coding agent, paste a single task block (e.g. Task 1.2 only) and require its Test + Done criteria before the next task.
