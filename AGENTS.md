# Agent Instructions — Real Estate Revenue OS

High-signal, repo-specific facts an agent would likely miss without help.

---

## Dev Commands

| Context | Command |
|---------|---------|
| Start API | `uvicorn main:app --host 0.0.0.0 --port 8000 --reload` (venv active) |
| Install deps | `pip install -r requirements.lock` (not `requirements.txt`) |
| Start frontend | `cd frontend && npm run dev` |
| Docker services | `docker compose up -d` (pg, redis, ngrok, frontend) |
| Seed local test clients | `python seed.py` → keys `secret-client-key-123` / `secret-client-key-456` |
| Provision production client | `python add_client.py` (interactive, generates secure keys) |
| Stress test (126 cases) | `python task3_runner.py` |
| Filter stress test | `python task3_runner.py --category HOT` (`--test-id R01`, `--skip-db`, `--base-url`, `--api-key`) |
| Tenant isolation drill | `python gate_isolation_test.py` |
| DLQ drill | `python gate_dlq_drill.py` then `python dlq_replay.py` |
| DB backup / restore | `python db_backup.py` / `python db_restore.py backups/backup_*.sql` |
| Frontend lint | `cd frontend && npm run lint` (ESLint, no TypeScript check) |
| Phase 3 concurrency tests | `pytest tests/test_p3_concurrency.py -v` (dependency-free source-inspection suite) |

---

## Architecture

- **Backend:** FastAPI + Gemini 3.1 Flash Lite + Twilio WhatsApp + PostgreSQL + Redis + FAISS RAG
- **Frontend:** Next.js 16.2.6 with React 19.2.4, Tailwind CSS v4, TypeScript. Route groups: `(public)` and `(dashboard)` with per-group layouts.
- **Static dashboard:** HTML/JS/CSS served by FastAPI at `/dashboard`
- **Scheduler (APScheduler):** 4 jobs — follow-up checker (1min), nightly backup (2am), nightly cleanup (3am), escalation checker (1min)
- **App entrypoint:** `main.py` — FastAPI app, lifespan starts scheduler, webhook handlers, metrics

---

## Multi-Tenant Isolation

- Session IDs prefixed with `{client_id}_` at the routing boundary (`main.py:329`, `agent.py:264`)
- Every DB query on client tables must filter by `client_id`
- **Exceptions:** `/api/v1/roi/*` and `/api/v1/reports/pipeline` — require `X-Admin-Key` header, query globally across all clients. Never expose to client dashboards without adding JWT + `client_id` filter.

---

## Auth Layers

| Layer | Mechanism | Applies to |
|-------|-----------|------------|
| API Key | `X-API-Key` header or `?api_key=` query param | `/api/v1/whatsapp`, `/api/v1/chat`, `/api/v1/ingest`, `/api/v1/webhook/meta`, `/api/v1/webhook/portals`, `/api/v1/incoming_sms` |
| JWT Bearer | `Authorization: Bearer <token>` (7-day, bcrypt) | Dashboard routes: `/api/v1/analytics`, `/api/v1/leads`, `/api/v1/leads/export`, `/api/v1/leads/*/stage`, `/api/v1/settings`, `/api/v1/agents`, `/api/v1/roi/*` |
| Admin Key | `X-Admin-Key` header | Internal ops only |
| **Public** | None | `/health`, `/metrics`, `/docs`, `/openapi.json`, `/api/v1/contact`, `/api/v1/webhook/stripe` |

- Frontend JWT stored as HttpOnly cookie named `jwt` by server action (`frontend/src/lib/auth.ts`)
- Middleware (`frontend/src/proxy.ts`) guards `/dashboard/*`, `/leads/*`, `/crm/*`, `/settings/*` — redirects to `/login` if no cookie
- Twilio webhook validates `X-Twilio-Signature` — **bypassed when `TEST_MODE=true`**
- `/metrics` is public — firewall-restrict in production

---

## LLM & Lead Qualification

- **6-field strict gate** before visit confirmation: `visit_date AND phone AND name AND location AND budget AND property_type`
- LLM must ask for missing details, cannot confirm booking until all present
- **RAG** fires only when `is_rag_eligible` (property keyword + location in message or lead context)
- **Confidence score** < 75 → `lead.requires_manual_review = True`
- **Class-vs-instance:** Assign `lead.urgency_level` (lowercase), never `Lead.urgency_level`
- **Budget normalization:** handles `lakhs`, `cr/crores`, `k/thousand` + `PERMONTH` suffix for rentals
- **Location normalization:** joins all canonical matches (sorted by length desc), with fallback mapping for near-miss areas
- **History window:** last 6 turns (12 messages); consecutive same-role messages auto-merged
- **Duplicate message saving:** `message_saved` flag prevents saving assistant message twice when tool-call block already saved

---

## Follow-Up Scheduler

- State machine: `Day 0 → Day 1 → Day 3 → Day 7 → closure message`
- `FOLLOW_UP_TEST_MODE=true` compresses all inter-stage gaps to **1 minute**
- `FOLLOW_UP_DLQ_TEST=true` forces scheduler to throw at `follow_up.py:423` → writes to `dlq_events`
- **Quiet hours:** follow-ups shifted to 8AM IST if time falls between 10PM–8AM IST
- **Inactivity:** 60s in test mode, 7 days in production → applies penalty + temperature downgrade
- **CRM sync** runs as background task with `await asyncio.sleep(2)` delay to avoid race with `agent.py` DB writes

---

## Webhook Flow & Timeouts

- WhatsApp endpoint: 15s timeout via `asyncio.wait_for` → on timeout, dispatches `background_process_and_push` + returns interim TwiML.
- **Idempotency (P3.4):** Both `/api/v1/whatsapp` and `/api/v1/incoming_sms` insert `WebhookLog(message_sid=MessageSid)` FIRST. On `IntegrityError` (PK race on `MessageSid`) it rolls back and returns empty `<Response></Response>` — duplicate `MessageSid`s are silently dropped (`main.py:655`, `main.py:760`).
- **Interim dedup (P3.1):** At most one interim "Just checking..." is sent per `MessageSid`, gated by Redis key `interim_sent:{MessageSid}` (120s TTL) (`main.py:696`).
- **Background lock (P3.1/P3.2):** `background_process_and_push` re-acquires `session_lock:{session_id}` (`timeout=45.0, blocking_timeout=10.0`) before processing; if another worker holds it, the run is skipped. It passes `background=True` downstream (`main.py:357`).
- **Duplicate message guard (P3.3):** On the background path (`is_background=True`), `agent.py` skips inserting a user message when `_has_recent_duplicate_message` finds identical content within the last 5 minutes (`agent.py:182`).
- **Per-session Redis lock:** Both handlers wrap `process_unified_lead` in `async with redis_client.lock(f"session_lock:{session_id}", timeout=20.0, blocking_timeout=30.0)`. The SMS handler falls back to best-effort processing without the lock if Redis is down.

## SMS Follow-Up Scoping (P3.5)

- `incoming_sms_webhook` does NOT use the raw `From` number as the session id. It builds `scoped_session_id = f"{current_client.id}_{raw_from}"` and uses it for the `FollowUpState` lookup, the Redis lock, and the `process_unified_lead` payload — keeping SMS follow-up state isolated per tenant.
- `_stop_followups_for_session(db, scoped_session_id)` (`main.py:431`) stops follow-ups. It runs INSIDE the Redis lock (normal path) and again in the Redis-down fallback, so follow-ups are always stopped even if Redis is unavailable.

## Notifications & Escalation

- Hot-lead **10m** escalation targets an `Agent` where `is_manager == True`; **30m** critical escalation targets `is_director == True`, falling back to the first manager (with a `P4.1 ESCALATION FALLBACK` log) when no director exists for the tenant.
- Resolution helper: `resolve_escalation_recipient(db, client_id, tier)` in `notification_service.py`; pure selection in `pick_escalation_agent(agents, tier)`.
- `Agent.is_director` added via `migrate_db.py`; `/api/v1/agents` accepts `is_director` (flows through `AgentCreate`).
- **Alert severity / upgrade (P4.2):** `trigger_hot_lead_notification(lead_id, reason, severity=None)` ranks reasons — `SEVERITY_HANDOFF (2)` > `SEVERITY_SCORE_ALERT (1)`. An open lower-severity alert is *upgraded* (one extra "UPGRADED" message + in-place `NotificationLog.reason/severity` update) instead of being dropped by the idempotency guard. Equal/lower severity or terminal status still bypasses. `NotificationLog` has `reason` + `severity` columns.
- **Follow-up send backoff (P4.3):** `compute_send_failure_backoff(retry_count, ...)` in `follow_up.py` returns `(next_delay, exhausted)` (exp 15→30→60→120→cap 240m; test mode → 1m; ≥5 retries → stop). On dispatch failure the scheduler advances `next_follow_up_at` (via backoff) so it no longer retries every tick; `FollowUpState.send_retry_count` tracks attempts and resets on success.

---

## DLQ (Dead Letter Queue)

- 3 event types: `hubspot_crm`, `twilio_outbound`, `ml_followup_scheduler`
- CRM sync: 5 retries (exponential backoff 2s→30s) via Tenacity, DLQ on permanent failure
- Replay: `python dlq_replay.py` (processes all `pending` → `resolved`)
- HubSpot sync is **demo-stubbed** (returns fake UUID) unless real `CRM_API_URL` + `CRM_API_KEY` configured

## CRM Sync (P5)

- `crm_sync.py`: create-time sync fires once (`sync_lead_to_crm`); later field changes are debounced, not per-turn.
- **P5.1:** after a meaningful field change on an already-synced lead, `agent.py` sets `Lead.crm_resync_pending = True`; `crm_resync_job` (scheduler, every 5 min) re-pushes and clears the flag. Failed re-sync keeps the flag set for retry.
- **P5.2:** extended property map (location, intent, property_type, visit_date, assignee, budget_alignment_status, urgency_level, engagement_score, lead_temperature) gated by `CRM_SYNC_EXTENDED_PROPERTIES` (default True). A 4xx for an unknown custom property drops that property and retries once.
- **P5.3:** `decide_crm_status_after_poll` leaves `crm_sync_status = "pending"` (never "success") when both `phone` and `name` are still empty after the create-time poll, so the next field update re-syncs.

## Feedback learning (P6.1)

- Agent win/loss learning is **persisted** in the `agent_learning` table (client-scoped), not in-process memory, so multi-worker deployments converge. `record_feedback(... client_id=...)` persists; `get_agent_success_rate(name, client_id)` reads it first.
- `config.MIN_MATCH_SCORE` (default 0): below this dynamic match score, `ensure_lead_assignment` leaves the lead unassigned rather than forcing a poor routing (P6.3).
- `main.py` `serialize_lead` title-cases `lead_temperature` (`Hot`/`Warm`/`Cold`) so the dashboard's case-sensitive badge compares match the backend's lowercase storage (P6.5).
- `follow_up.py` `next_followup_stage(followups, current_stage)` derives the next stage + day-gap from the ML `followups` sequence, keeping the scheduler aligned with strategy B (P6.4).

---

## Testing Flags (`.env`)

```env
FOLLOW_UP_TEST_MODE=true   # compress timings
FOLLOW_UP_DLQ_TEST=true    # force DLQ entry (requires TEST_MODE)
TEST_MODE=true             # bypass Twilio sig validation, skip WhatsApp sends
IS_PRODUCTION=false
```

**Remove all before production deploy.**

---

## Key Database Schema

- Table `event_logs` (model `EventLog`), not `event_log`
- Core tables: `clients`, `sessions`, `leads`, `messages`, `event_logs`, `follow_up_states`, `dlq_events`, `agents`, `notification_logs`, `webhook_logs`
- Lead ML columns: `conversion_probability`, `lead_temperature`, `urgency_level`, `engagement_score`, `inactivity_penalty`, `confidence_score`, `requires_manual_review`, `budget_alignment_status`

---

## Config / Env Quirks

- Settings via `pydantic_settings` (`config.py` class `Settings`) — reads `.env`
- `contextvars`: `request_id_ctx` and `tenant_id_ctx` for structured logging
- RAG FAISS index built in **background thread** (`rag.py:75`) — first request may wait ≤5s for index to be ready
- Gemini embeddings LRU-cached (128 entries) via `@lru_cache` on `get_query_embedding_cached`
- `google.generativeai` SDK deprecation warning — known, still functional
- `GEMINI_MODEL` defaults to `gemini-3.1-flash-lite` — can revert to `gemini-2.5-flash` in `.env`

## IREIOS 3.0 Expansion Env Vars (added in Phase 0, consumed in later phases)

- `EVENT_STREAM_KEY` (default `ireios:events`) — Redis Streams key for the Phase 1 event bus.
- `EVENT_CONSUMER_GROUP` (default `ireios-cg`) — consumer group name for the bus.
- `FEATURE_WHATSAPP_V3` (default `false`) — when `true`, WhatsApp/chat routes use the new `WhatsAppAgent` (Phase 5); `false` keeps legacy `agent.process_chat`.
- `FOLLOWUP_ENGINE` (default `legacy`) — `legacy|v3|shadow` selector for the Phase 4 follow-up port.
- `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` — Neo4j connection (Phase 7); left empty until the service is added.
- `N8N_BASE_URL` / `N8N_API_KEY` — n8n automation (Phase 2); left empty = `n8n_not_configured`.
- These are logged/stored in `.env` (gitignored) and `.env.example`. Adding them in Phase 0 is env hygiene only — no production behavior changes until the consuming phases land.

---

## Frontend-Specific

- Next.js 16 — check `node_modules/next/dist/docs/` for breaking changes before writing code
- `NEXT_PUBLIC_API_URL` must point to backend (e.g. `http://localhost:8000`)
- JWT login via server action → `POST /api/v1/auth/login` with `application/x-www-form-urlencoded` body
- Theme persisted in localStorage key `dashboard-theme` (default: dark)
- Key deps: `recharts` (charts), `jspdf` (export), `lucide-react` (icons), `next-themes` (dark mode)
