# IREIOS — End-to-End Maintenance Guide

Operational runbook for the **current** codebase (FastAPI monolith + IREIOS 3.0 bus/agents/KG).  
Companion to `AGENTS.md` (agent-oriented facts) and `plans/IREIOS_3.0_EVIDENCE_PACK.md` (release gates).

**Last aligned:** July 2026 · Branch baseline: post–Phase 10 / BD closeout

---

## 1. System map (what you are maintaining)

```text
                    ┌──────────── Docker ────────────┐
Twilio/Web ──► FastAPI (main.py)                     │
                 │  PostgreSQL  ◄── source of truth  │
                 │  Redis Streams (event bus)        │
                 │  Neo4j (projected graph, optional)│
                 │  FAISS RAG (in-process / files)   │
                 ▼                                   │
            CEO → Agents/Workflows → AE → EE         │
                 │                                   │
                 ▼                                   │
         WhatsApp / CRM / Calendar / Notify          │
                    └────────────────────────────────┘
Frontend (Next.js) ── JWT cookie ──► /api/v1/*
```

| Store | Role | Lose it? |
|-------|------|----------|
| **PostgreSQL** | Leads, sessions, messages, approvals, DLQ, memory, clients | **Catastrophic** — restore from backup |
| **Redis** | Session locks, interim dedupe, **event bus stream** | Bus lag / lost unacked events; app mostly recovers |
| **Neo4j** | Lead/agent graph projection | **Safe** — rebuild via `project_leads_to_neo4j.py` |
| **FAISS / RAG files** | Property retrieval | Rebuild on next RAG init / reindex path |
| **`.env`** | Secrets & feature flags | Redeploy broken until restored |

---

## 2. Local day-2 startup

```powershell
# 1) Infra
docker compose up -d

# 2) Python env (uv or venv)
.\.venv\Scripts\Activate.ps1
# Prefer lock for reproducibility:
pip install -r requirements.lock
# Or fresh from directs: pip install -r requirements.txt  then  pip freeze > requirements.lock

# 3) Clients + agents
python seed.py

# 4) API
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 5) Optional frontend
cd frontend; npm run dev
```

**Smoke:**

| Check | Expect |
|-------|--------|
| `GET http://localhost:8000/health` | 200 |
| Uvicorn log | `EventBus started`, executors registered, agents registered, `Application startup complete` |
| Neo4j configured | `Neo4j schema v1 applied` (idempotent “already exists” INFO is OK) |
| `GET /api/v1/graph/health` | `available: true` when `NEO4J_*` set |

---

## 3. Environment & feature flags

| Flag | Dev default | Prod go-live |
|------|-------------|--------------|
| `IS_PRODUCTION` | `false` | `true` |
| `TEST_MODE` | `true` | `false` |
| `FOLLOW_UP_TEST_MODE` | `true` | `false` |
| `FOLLOW_UP_DLQ_TEST` | off | **must be false** |
| `FEATURE_WHATSAPP_V3` | `true` | `true` |
| `FOLLOWUP_ENGINE` | `v3` | `v3` (`legacy` = emergency only) |
| `NEO4J_URI` | `bolt://localhost:7687` | real or empty (no-op graph) |
| `N8N_*` / `GOOGLE_CALENDAR_*` | empty OK | set when integrating |

Full lists: `.env.example`, `AGENTS.md` → Config / Expansion env vars.

**Never commit** real Twilio, Gemini, admin, or DB passwords.

---

## 4. PostgreSQL maintenance

### Backup / restore

```powershell
python db_backup.py
python db_restore.py backups\backup_YYYYMMDD_HHMMSS.sql
```

- Run backup before migrations, bulk seeds, or deploys.
- Nightly backup job is scheduled in-app (2am) when scheduler is up — still keep off-box copies in prod.

### Migrations

```powershell
python migrate_db.py
```

Idempotent-ish additive SQL. After pull: migrate → restart uvicorn.

### Useful cleanup (dev)

| Goal | Approach |
|------|----------|
| Reset dummy graph load test | `python seed_dummy_leads.py --purge-only` |
| Soft / hard wipes | §4.1 below (canonical) |
| Full tenant wipe | Postgres **hard** + `seed.py`; or restore from backup |
| DLQ stuck events | `python dlq_replay.py` after fixing root cause |

### Multi-tenant rule

Every query on client data **must** filter `client_id`. Session ids are scoped `{client_id}_…` at the webhook boundary.

### 4.1 Soft / hard wipes (canonical — current schema)

Postgres and Neo4j are **independent**. Truncating Postgres does **not** clear Neo4j.

**Connect PG:** `psql postgresql://realestate:localpass@localhost:5432/realestate_db`  
**Neo4j Browser:** `http://localhost:7474` · bolt `bolt://localhost:7687` · user/pass `neo4j` / `localpass`

#### Postgres — soft (keep `clients` + `agents`)

```sql
TRUNCATE
  messages,
  event_logs,
  dlq_events,
  follow_up_states,
  lead_memories,
  approval_requests,
  agent_learning,
  notification_logs,
  leads,
  sessions,
  webhook_logs
RESTART IDENTITY CASCADE;
```

#### Postgres — hard (wipe tenants too)

```sql
TRUNCATE
  messages,
  event_logs,
  dlq_events,
  follow_up_states,
  lead_memories,
  approval_requests,
  agent_learning,
  notification_logs,
  leads,
  sessions,
  webhook_logs,
  agents,
  clients
RESTART IDENTITY CASCADE;
```

Then: `python seed.py`

#### Neo4j — soft (leads; keep `:SchemaVersion`)

```cypher
MATCH (n:Lead) DETACH DELETE n;
```

Optional orphan cleanup after soft lead delete:

```cypher
MATCH (n:Agent) DETACH DELETE n;
```

#### Neo4j — hard (all nodes except schema marker)

```cypher
MATCH (n) WHERE NOT n:SchemaVersion DETACH DELETE n;
```

#### Fresh WhatsApp retest

| Goal | Commands |
|------|----------|
| Chat/CRM only | Postgres **soft** → send WA |
| Chat + clean graph UI / similar-lead context | Postgres **soft** + Neo4j **soft** → send WA |
| Full local reset | Postgres **hard** + `seed.py` + Neo4j **hard** |

New WA traffic **upserts** into Neo4j; it does **not** remove old dummy nodes left from a prior bulk seed.

---

## 5. Redis & Event Bus

| Item | Detail |
|------|--------|
| Stream key | `EVENT_STREAM_KEY` (default `ireios:events`) |
| Consumer group | `EVENT_CONSUMER_GROUP` (default `ireios-cg`) |
| Runtime | `Event → CEO → Agent/Workflow → AE → EE → Event` |

**Ops tips:**

- Redis down → bus publish fails loud; WhatsApp path may degrade depending on lock fallback.
- After Redis volume wipe: groups recreate on `event_bus.start()`; in-flight PEL is gone.
- Do **not** treat Redis as durable business state; Postgres is.

### SSE smoke (Phase 1b)

```powershell
# Terminal A — tenant-filtered live stream (seed.py key for client 1)
curl -N "http://localhost:8000/api/v1/events/stream?api_key=secret-client-key-123"

# Terminal B — publish without WhatsApp/LLM
python publish_stub_event.py --event-type lead.created --tenant-id Client_1 --payload "{\"name\":\"demo\"}"
```

| Route | Auth | Notes |
|-------|------|--------|
| `GET /api/v1/events/stream` | `?api_key=` / `X-API-Key` **or** `jwt` cookie | `: ping` every 15s; `503` if bus down |
| `GET /api/v1/events/leads/{id}/timeline` | same | From `event_logs`; 404 cross-tenant |
| `POST /api/v1/events/stub` | `X-Admin-Token` = `ADMIN_API_KEY` | Returns `event_id` |

Envelope fields (bus): `event_id`, `event_type`, `tenant_id`, `entity_id`, `source`, `timestamp`, `correlation_id`, `payload`.  
Contracts: `plans/IREIOS_3.0_API_SSE_CONTRACTS.md`.

---

## 6. Neo4j maintenance

### Model (current)

- **Postgres = source of truth** for leads.
- Neo4j = **async projection** (`kg_event_writer` on bus) + WhatsApp pre/post-turn upsert + optional batch project.
- Similarity today: same `client_id` + same `location` string (not vector layout in Browser).
- Local: `NEO4J_URI=bolt://localhost:7687`, `NEO4J_USER=neo4j`, `NEO4J_PASSWORD=localpass` (see `.env.example`).

### Health

```text
GET http://localhost:8000/api/v1/graph/health
GET /api/v1/graph/leads/{id}/context   # tenant-scoped
```

Browser (`http://localhost:7474`): use filtered Cypher only:

```cypher
MATCH (l:Lead {client_id: 1}) RETURN count(l);
MATCH (l:Lead {client_id: 1, location: 'Baner'}) RETURN l LIMIT 25;
MATCH (l:Lead)-[:ASSIGNED_TO]->(a:Agent) WHERE l.client_id = 1 RETURN l, a LIMIT 50;
```

**Avoid** `MATCH (n) RETURN n` on large graphs — Browser will choke; the DB may still be fine.

### Rebuild projection from Postgres

```powershell
python project_leads_to_neo4j.py
python project_leads_to_neo4j.py --client-id 1 --source dummy_seed
python project_leads_to_neo4j.py --dry-run
```

Use after: Neo4j volume reset, schema change, bulk SQL seed without bus events. Wipes: §4.1.

### Schema

Lifespan runs `neo4j_client.migrate_schema()` (idempotent). INFO notifications “constraint already exists” are **normal**.

### Scale notes

| Leads | Engine | Browser “show all” | App similar-lead query |
|------:|--------|--------------------|-------------------------|
| ≤1k–10k | Easy | OK if filtered | Fine |
| 100k+ | Fine with indexes | Never global draw | Keep `client_id` + indexed props |
| 1M+ | Capacity planning | App ego-graphs only | Cache context; archive cold nodes |

Indexes already cover lead key, `client_id`, `location`. Later: shared `:Location` nodes, Redis cache on `get_lead_context`, CDC if write volume explodes.

### WhatsApp path (ops awareness)

Graph context is **LLM-only** (not sent as a WhatsApp bubble):

```text
Knowledge graph signal: N similar prior lead(s) in graph near Baner (2BHK). …
```

If Neo4j is down, chat continues with empty context.

---

## 7. Dummy data load (dev / graph demos)

```powershell
# 1000 full leads → Postgres + Neo4j (client 1). source=dummy_seed
python seed_dummy_leads.py

python seed_dummy_leads.py --count 100 --client-id 1
python seed_dummy_leads.py --no-neo4j
python seed_dummy_leads.py --purge-only
```

- Requires `python seed.py` clients first.
- Does **not** create 1000 follow-up scheduler storms by default (no FollowUpState rows).
- Purge before re-seed is default (idempotent dev loop).

---

## 8. Application processes & scheduler

| Job | When | Notes |
|-----|------|--------|
| `dispatch_followups` | ~1 min | `FOLLOWUP_ENGINE=v3` → AE→WhatsAppExecutor |
| `backup_postgres` | 2am | Local backup helper |
| `daily_cleanup_job` | 3am | Retention-style cleanup |
| `escalation_cron_job` | ~1 min | Hot lead manager/director |
| `crm_resync_job` | ~5 min | Debounced CRM field push |
| `competitor_monitor_job` | 01:00 | No-op if `COMPETITOR_KEYWORDS` empty |

Restart uvicorn to pick up code; scheduler lives in the API process (not a separate worker today).

---

## 9. Integrations checklist

| Integration | Config | Failure mode |
|-------------|--------|--------------|
| Gemini | `GEMINI_API_KEY`, `GEMINI_MODEL` | Chat fails / quota errors |
| Twilio WA | `TWILIO_*`; `TEST_MODE` skips send | DLQ / logs |
| HubSpot CRM | `CRM_API_URL` + key; else demo stub | DLQ `hubspot_crm` |
| Neo4j | `NEO4J_*` | Graph no-op |
| n8n | `N8N_*` | `n8n_not_configured` |
| Google Calendar | `GOOGLE_CALENDAR_*` | Synthetic `visit_id` stub |
| Stripe | webhook + keys | Billing routes only |
| AWS secrets | optional boto path in `config` | Falls back to env |

DLQ drill:

```powershell
python gate_dlq_drill.py
python dlq_replay.py
```

---

## 10. Testing & gates (before deploy)

```powershell
python -m pytest tests/ -q
python gate_isolation_test.py
python gate_dlq_drill.py
python dlq_replay.py
# Live conversation stress (server up + Gemini quota):
python task3_runner.py
python task3_runner.py --category HOT
```

| Suite | Prefix |
|-------|--------|
| Bug regressions | `tests/test_p*.py` |
| Expansion / IREIOS 3.0 | `tests/test_e*.py` |

Evidence: `plans/IREIOS_3.0_EVIDENCE_PACK.md`, `python ireios_evidence.py`.

---

## 11. Frontend maintenance

```powershell
cd frontend
npm install
npm run dev
npm run lint
```

- `NEXT_PUBLIC_API_URL` → backend (e.g. `http://localhost:8000`)
- Auth: HttpOnly `jwt` cookie via server login action
- Live SSE cutover still backlog: `docs/FRONTEND_BACKLOG.md` (replace MockSSE)

---

## 12. Dependency maintenance

| File | Purpose |
|------|---------|
| `requirements.txt` | Direct runtime deps, **unpinned** |
| `requirements.lock` | Full pinned tree for install/deploy (**UTF-8**) |

Refresh lock after changing `.txt`:

```powershell
# clean venv recommended
pip install -r requirements.txt
pip freeze | Out-File -Encoding utf8 requirements.lock
pip check
```

AGENTS.md install command: **`pip install -r requirements.lock`**.

Do not bulk “Optimize Imports” in IDE across `main.py` / lazy import modules without restart smoke — import order can change startup logs and circular-import safety.

---

## 13. Logging, metrics, health

| Endpoint | Auth | Use |
|----------|------|-----|
| `/health` | public | Liveness |
| `/metrics` | public | Prometheus — **firewall in prod** |
| `/docs` | public (dev) | OpenAPI — restrict in prod |

Structured logs use `request_id` / `tenant_id` contextvars when set.

---

## 14. Security maintenance

- Rotate `ADMIN_API_KEY`, client API keys, JWT secret, DB passwords on schedule / incident.
- Production: `TEST_MODE=false`, real Twilio signature validation.
- Never expose admin ROI/global routes to tenant dashboards without JWT + `client_id`.
- `/metrics` and OpenAPI: network policy in production.

---

## 15. Incident cheat sheet

| Symptom | Check |
|---------|--------|
| App won’t start | `.env`, Postgres up, `pip check`, traceback on import |
| EventBus errors | Redis container, `EVENT_STREAM_*` |
| No WA send | `TEST_MODE`, Twilio creds, EE WhatsAppExecutor logs, DLQ |
| CRM not updating | bus `crm_automation`, `crm_sync_status`, DLQ `hubspot_crm` |
| Graph empty | `NEO4J_URI`, `project_leads_to_neo4j.py`, writer logs |
| Wrong tenant data | isolation gate; missing `client_id` filter |
| Double messages | webhook MessageSid / Redis locks (P3) |
| Follow-ups stuck | `FollowUpState`, quiet hours, `FOLLOWUP_ENGINE`, send_retry backoff |
| Gemini 429 | quota; pause `task3_runner`; backoff |

---

## 16. Production deploy checklist

1. `IS_PRODUCTION=true`, all test flags **false**  
2. Real `DATABASE_URL`, Redis, Twilio, Gemini  
3. `pip install -r requirements.lock`  
4. `python migrate_db.py`  
5. Optional: Neo4j + `migrate_schema` via app start  
6. `gate_isolation_test` / DLQ drill against staging  
7. Backup before cutover  
8. Smoke: health, one chat/WA, SSE event, CRM stub/real  
9. Firewall `/metrics`, lock down `/docs`  
10. Monitor logs + DLQ depth first 24h  

---

## 17. Script index

| Script | Purpose |
|--------|---------|
| `seed.py` | Test clients + agents |
| `seed_dummy_leads.py` | Bulk full leads + Neo4j project (`dummy_seed`) |
| `project_leads_to_neo4j.py` | PG → Neo4j backfill anytime |
| `add_client.py` | Production client provisioning |
| `migrate_db.py` | SQL additive migrations |
| `db_backup.py` / `db_restore.py` | DB snapshots |
| `gate_isolation_test.py` | Tenant isolation |
| `gate_dlq_drill.py` / `dlq_replay.py` | DLQ path |
| `task3_runner.py` | Live conversation matrix |
| `publish_stub_event.py` | Bus/SSE demo events |
| `ireios_evidence.py` | Architecture evidence dump |
| `dlq_replay.py` | Replay pending DLQ |

---

## 18. Related docs

| Doc | Contents |
|-----|----------|
| `AGENTS.md` | Agent/dev high-signal facts |
| `README.md` | Product overview & setup |
| `docs/FRONTEND_BACKLOG.md` | FE SSE/API cutover |
| `docs/N8N_INTEGRATION.md` | n8n config-later |
| `plans/UNIFIED_EXECUTION_ORDER.md` | Program order / gates |
| `plans/IREIOS_3.0_EVIDENCE_PACK.md` | Release evidence |
| `plans/IREIOS_3.0_API_SSE_CONTRACTS.md` | Realtime contracts |

---

## 19. What not to do

- Do not delete dual-path helpers (`agent` qualification core, `crm_sync` helpers, `follow_up` pure helpers) without a dedicated decommission window — v3 **reuses** them.
- Do not use Neo4j Browser as the production observability UI for full graphs.
- Do not run `FOLLOW_UP_DLQ_TEST` or `TEST_MODE` in production.
- Do not install from an outdated lock after editing `requirements.txt` without regenerating the lock.
