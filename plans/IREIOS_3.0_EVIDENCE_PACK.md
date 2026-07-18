# IREIOS 3.0 — Evidence Pack (Gate G2 + BD closeout)

## Architecture & cutover
- [x] Event Bus = Redis Streams; inbound chat/WA publishes lifecycle events (`main._emit_turn_events`)
- [x] CEO agents on real traffic: followup_arm, lead_scoring, crm_automation, kg_event_writer, …
- [x] **BD-1** CRM create path = bus only (`crm_automation` → AE→EE); no dual `sync_lead_to_crm` on chat
- [x] **BD-2** Follow-up default `FOLLOWUP_ENGINE=v3` (AE→EE); legacy flag rollback only
- [x] **BD-3** Qualification entry = `app.agents.qualification`; WhatsAppAgent is default orchestrator
- [x] **BD-4** Outbound purity: escalation + hot alerts + background via `outbound` / `WhatsAppExecutor` (not ad-hoc Twilio Client in those paths). `dlq_replay` / legacy `follow_up` retain direct Twilio for rollback/recovery tools.
- [x] **BD-5** Neo4j used on WhatsApp reply path (`extra_context` → LLM summary)
- [x] Brochure tools: TwiML/chat body only (no AE double-send)
- [~] Full deletion of root `agent.py` / `follow_up.py` / `crm_sync.py` modules — not required; they are libraries for EE/v3. Dead *call paths* removed.
- [ ] FE MockSSE cutover — see `docs/FRONTEND_BACKLOG.md` (Mayank)

## Data, graph, memory
- [x] Neo4j schema v1; `/api/v1/graph/health` available when configured
- [x] Graph writers + reply-path read
- [x] ConversationMemory APIs

## Integrations
- [x] n8n client scaffold + purpose doc: `docs/N8N_INTEGRATION.md`
- [x] Google Calendar executor stub/real config-later
- [x] Twilio via WhatsAppExecutor for production send paths listed above

## Quality gates
- [x] `tests/test_e12_bus_wiring.py`, `tests/test_e13_bd_closeout.py`
- [x] Expansion + bug unit suites (run before release)
- [ ] `python task3_runner.py` when Gemini quota allows (live server)
- [x] `gate_isolation_test.py` / `gate_dlq_drill.py` (run before deploy)

## Manual smoke
1. `docker compose up -d` + uvicorn
2. `/health` + `/api/v1/graph/health` (available=true with local Neo4j)
3. Chat or Twilio sandbox message
4. SSE stream shows `conversation.updated` / `lead.created` / `lead.scored`
5. Neo4j Browser optional: `MATCH (l:Lead) RETURN l LIMIT 25`

## Go-live flags
```env
IS_PRODUCTION=true
TEST_MODE=false
FOLLOW_UP_TEST_MODE=false
FOLLOW_UP_DLQ_TEST=false
FEATURE_WHATSAPP_V3=true
FOLLOWUP_ENGINE=v3
NEO4J_URI=bolt://...   # optional but recommended
```
