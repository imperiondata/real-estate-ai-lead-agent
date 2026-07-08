# IREIOS 3.0 — Multi-Agent Event-Driven Architecture Implementation Plan

> **Status:** Finalized — Phase 0 (Cross-Check Complete)
> **Based on:** Existing `agent.py` (1066 lines), `main.py` (1118 lines), `follow_up.py` (620 lines), `crm_sync.py` (132 lines), IREIOS 3.0 Architecture Diagrams, industry research (CallSphere, Martinke, RoanBrasil patterns)
> **Architecture Philosophy:** Event → Agent → Decision → Execution → Event

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [File Structure](#3-file-structure)
4. [Detailed Specifications](#4-detailed-specifications)
   - [Phase 1: Infrastructure](#41-phase-1-infrastructure)
   - [Phase 2: Twilio & CRM Extraction](#42-phase-2-twilio--crm-extraction)
   - [Phase 3: Follow-Up Scheduler Refactor](#43-phase-3-follow-up-scheduler-refactor)
   - [Phase 4: WhatsApp Agent (Core agent.py Extraction)](#44-phase-4-whatsapp-agent-core-agentpy-extraction)
   - [Phase 5: Remaining Agents & Workflows](#45-phase-5-remaining-agents--workflows)
5. [Migration Mapping](#5-migration-mapping)
6. [main.py Updated Routing](#6-mainpy-updated-routing)
7. [Testing Strategy](#7-testing-strategy)
8. [Risks & Mitigations](#8-risks--mitigations)

---

## 1. Executive Summary

The existing codebase is a **monolithic FastAPI application** where `agent.py` (1066 lines) orchestrates everything: session management, lead CRUD, LLM chat, RAG, tool calling, ML scoring, agent matching, follow-up state machine, and message persistence — all in one function (`process_chat`).

**Goal:** Refactor into a **decoupled event-driven multi-agent system** where:
- **No action happens silently** — every side effect flows through `ExecutionEngine` then publishes an event
- **Agents are stateless** — they receive events, fetch context, analyze, decide, dispatch actions
- **Executors are dumb** — they only call APIs (Twilio, HubSpot) and return success/failure
- **EventBus is the nervous system** — connects everything via pub/sub

**Key insight from cross-check:** The original plan glosses over the hardest 80% of the migration (agent.py). This plan addresses it with a realistic 5-phase approach.

---

## 2. Architecture Overview

```
                ┌──────────────────────────────┐
                │   External Sources           │
                │  (WhatsApp, Web, Meta, APIs) │
                └──────────┬───────────────────┘
                           │ HTTP/Twilio Webhook
                           ▼
                ┌──────────────────────────────┐
                │     API Gateway (main.py)     │
                │  Auth, RBAC, Rate Limiting    │
                │  Returns TwiML immediately     │
                └──────────┬───────────────────┘
                           │ asyncio.create_task()
                           ▼
                ┌──────────────────────────────┐
                │     Event Bus (In-Process)    │
                │  subscribe() + publish()      │
                │  asyncio.Queue processing     │
                └──┬───────┬───────┬───────────┘
                   │       │       │
        ┌──────────┘       │       └──────────┐
        ▼                  ▼                   ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│  Event Router │ │  CEO Agent    │ │  Scheduled    │
│  (routes by   │ │  Orchestrator │ │  Jobs (Cron)  │
│   event_type) │ │  (Phase 4)    │ │               │
└───────┬───────┘ └───────────────┘ └───────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────┐
│              Agent Layer (Brains)                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │
│  │ WhatsApp │ │  Sales   │ │Marketing │ │ CS     │ │
│  │ Agent    │ │  Agent   │ │ Agent    │ │ Agent  │ │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └───┬────┘ │
│       │            │            │            │       │
│  Template Method: fetch_context → analyze → decide  │
└───────┴────────────┴────────────┴────────────┴───────┘
        │
        ▼
┌─────────────────────────────────────────────────────┐
│         Execution Engine (Muscle)                    │
│  ┌──────────────────┐ ┌──────────────────────────┐   │
│  │ WhatsAppExecutor │ │ CRMExecutor              │   │
│  │ (Twilio API)     │ │ (HubSpot/Sync + Tenacity)│   │
│  └──────────────────┘ └──────────────────────────┘   │
│  ┌──────────────────┐                                │
│  │ dispatch() routes│ → Success? → EventBus.publish │
│  │ by action_type   │ → Failure?  → DLQEvent table │
│  └──────────────────┘                                │
└─────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────┐
│              Workflows (Linear Logic)               │
│  ┌──────────────────┐ ┌──────────────────────────┐   │
│  │ CRMAutomation   │ │ CompetitorMonitor        │   │
│  │ (agent_matcher) │ │ (cron-based pricing)     │   │
│  └──────────────────┘ └──────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

---

## 3. File Structure

```
app/
├── __init__.py
│
├── clients/                          # Cross-system communication
│   ├── __init__.py
│   ├── event_bus_client.py           # In-process pub/sub EventBus
│   └── graph_client.py               # Knowledge Graph context fetcher
│
├── execution_engine/                 # The "Muscle"
│   ├── __init__.py
│   ├── base_executor.py              # Abstract class
│   ├── whatsapp_executor.py          # Twilio API calls
│   ├── crm_executor.py               # HubSpot sync (from crm_sync.py)
│   └── execution_engine.py           # Router + DLQ integration
│
├── agents/                           # The "Brains"
│   ├── __init__.py
│   ├── base_agent.py                 # Template method lifecycle
│   ├── whatsapp_agent.py             # LLM, RAG, tool calling
│   ├── sales_agent.py                # Objection detection, next-best-action
│   ├── marketing_agent.py            # Campaign ROI analysis
│   └── customer_success_agent.py     # Payment reminders
│
├── workflows/                        # Linear automations
│   ├── __init__.py
│   ├── crm_automation.py             # Agent matching + tagging
│   ├── followup_scheduler.py         # State machine (from follow_up.py)
│   └── competitor_monitor.py         # Pricing intelligence
│
└── intelligence/                     # EXISTING — keep unchanged
    ├── agent_matcher.py
    ├── lead_scoring.py
    ├── push_wait_engine.py
    ├── followup_engine.py
    ├── budget_alignment.py
    └── ... (18 modules total)

# No new top-level files — main.py, config.py, models.py unchanged
# KEY: agent.py, crm_sync.py, follow_up.py will be DECOMMISSIONED after migration
```

---

## 4. Detailed Specifications

### 4.1 Phase 1: Infrastructure

**Files to create:** `event_bus_client.py`, `graph_client.py`, `base_executor.py`, `execution_engine.py`, `base_agent.py`

#### `app/clients/event_bus_client.py`

An **in-process async event bus** with pub/sub. Unlike the original plan's stub, this is a real bus:

```python
class EventBusClient:
    """In-process async event bus with pub/sub pattern.
    
    Phase 1: asyncio.Queue (single process)
    Phase 5 upgrade: Redis Streams (distributed)
    """
    
    _handlers: dict[str, list[Callable]] = {}
    _queue: asyncio.Queue = None
    _processing_task: asyncio.Task = None
    
    @classmethod
    def subscribe(cls, event_type: str, handler: Callable):
        """Register a handler for an event type."""
        if event_type not in cls._handlers:
            cls._handlers[event_type] = []
        cls._handlers[event_type].append(handler)
    
    @classmethod
    async def publish(cls, event_type: str, tenant_id: int, 
                      entity_id: str, payload: dict, 
                      source: str = "system"):
        """Publish event to the bus (queued for async processing)."""
        event = {
            "event_id": f"evt_{uuid4().hex[:12]}",
            "event_type": event_type,
            "tenant_id": tenant_id,
            "entity_id": str(entity_id),
            "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
            "correlation_id": str(uuid4())
        }
        logger.info(f"📡 Event published: {event_type} | entity={entity_id}")
        await cls._queue.put(event)
    
    @classmethod
    async def _processing_loop(cls):
        """Background loop: dequeue events → fan-out to handlers."""
        while True:
            event = await cls._queue.get()
            handlers = cls._handlers.get(event["event_type"], [])
            if handlers:
                await asyncio.gather(
                    *[h(event) for h in handlers],
                    return_exceptions=True
                )
            cls._queue.task_done()
    
    @classmethod
    def start(cls):
        """Call during FastAPI lifespan startup."""
        cls._queue = asyncio.Queue()
        cls._processing_task = asyncio.create_task(cls._processing_loop())
    
    @classmethod
    async def stop(cls):
        """Call during FastAPI lifespan shutdown."""
        if cls._processing_task:
            cls._processing_task.cancel()
```

#### `app/clients/graph_client.py`

```python
class GraphClient:
    """Fetches lead context from Knowledge Graph (Neo4j).
    
    Phase 1: Mock/stub returning dummy data.
    Future: async HTTP call to Aritro's Neo4j API.
    """
    
    @staticmethod
    async def get_lead_context(lead_id: str) -> dict:
        return {
            "location": "Baner",
            "budget": "80L",
            "property_type": "2BHK",
            "previous_objections": ["Price too high"],
            "intent": "buy",
        }
    
    @staticmethod
    async def get_conversation_history(session_id: str) -> list[dict]:
        return []
```

#### `app/execution_engine/base_executor.py`

```python
from abc import ABC, abstractmethod

class BaseExecutor(ABC):
    @abstractmethod
    async def execute(self, action_request: dict) -> dict:
        """Execute an action, return {"status": "success"|"error", ...}."""
        pass
```

#### `app/execution_engine/execution_engine.py`

```python
class ExecutionEngine:
    """
    Central dispatcher.
    1. Routes action_type → executor
    2. Calls executor.execute()
    3. On success: EventBus.publish()
    4. On failure: DLQEvent table write
    """
    
    _executors: dict[str, BaseExecutor] = {}
    
    @classmethod
    def register(cls, action_type: str, executor: BaseExecutor):
        cls._executors[action_type] = executor
    
    @classmethod
    async def dispatch(cls, action_request: dict) -> dict:
        action_type = action_request["action_type"]
        executor = cls._executors.get(action_type)
        if not executor:
            raise ValueError(f"No executor for {action_type}")
        
        result = await executor.execute(action_request)
        
        if result["status"] == "error":
            # Write to DLQEvent table
            db = SessionLocal()
            db.add(DLQEvent(
                target_endpoint=action_type,
                payload=action_request,
                error_trace=result.get("error", ""),
                status="pending",
                client_id=action_request.get("tenant_id")
            ))
            db.commit()
            db.close()
            return result
        
        # Publish success event
        event_type = _EVENT_MAP.get(action_type, "action.completed")
        asyncio.create_task(EventBusClient.publish(
            event_type=event_type,
            tenant_id=action_request["tenant_id"],
            entity_id=action_request["entity_id"],
            payload={"action_request": action_request, "result": result},
            source="execution_engine"
        ))
        return result
```

**Event mapping table:**

| `action_type` | Published Event |
|---|---|
| `send_whatsapp` | `whatsapp.sent` |
| `update_crm` | `lead.crm_synced` |
| `create_task` | `task.created` |
| `schedule_visit` | `site_visit.scheduled` |

#### `app/agents/base_agent.py`

**Fixed** — `event` is now passed to all lifecycle methods:

```python
class BaseAgent(ABC):
    async def process_event(self, event: dict):
        """Standardized Agent Lifecycle."""
        try:
            context = await self.fetch_context(event)
            analysis = await self.analyze(event, context)
            action_request = await self.decide(event, analysis, context)
            
            if action_request:
                await ExecutionEngine.dispatch(action_request)
        except Exception as e:
            logger.error(f"Agent {self.__class__.__name__} failed: {e}")
            await EventBusClient.publish(
                event_type=f"{self.__class__.__name__.lower()}.failed",
                tenant_id=event.get("tenant_id", 0),
                entity_id=event.get("entity_id", ""),
                payload={"error": str(e), "original_event": event},
                source=self.__class__.__name__.lower()
            )
    
    @abstractmethod
    async def fetch_context(self, event: dict) -> dict:
        pass
    
    @abstractmethod
    async def analyze(self, event: dict, context: dict) -> dict:
        pass
    
    @abstractmethod
    async def decide(self, event: dict, analysis: dict, context: dict) -> dict:
        """Return an ActionRequest dict or None."""
        pass
```

---

### 4.2 Phase 2: Twilio & CRM Extraction

**Files to create:** `whatsapp_executor.py`, `crm_executor.py`

#### `app/execution_engine/whatsapp_executor.py`

Migrate Twilio sending from `agent.py` (lines 368-375, scattered throughout) and `main.py` (lines 368-375):

```python
class WhatsAppExecutor(BaseExecutor):
    async def execute(self, action_request: dict) -> dict:
        params = action_request.get("parameters", {})
        phone = params.get("phone")
        message = params.get("message")
        media_url = params.get("media_url")  # For brochures/floor plans
        
        if settings.TEST_MODE:
            logger.info(f"[TEST MODE] Simulated WhatsApp to {phone}")
            return {"status": "success", "sid": "test_sid"}
        
        try:
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            to_num = f"whatsapp:{phone}" if not phone.startswith("whatsapp:") else phone
            kwargs = {"from_": settings.TWILIO_PHONE_NUMBER, "body": message, "to": to_num}
            if media_url:
                kwargs["media_url"] = [media_url]
            
            msg = await asyncio.to_thread(client.messages.create, **kwargs)
            return {"status": "success", "sid": msg.sid}
        except Exception as e:
            logger.error(f"Twilio execution failed: {e}")
            return {"status": "error", "error": str(e)}
```

#### `app/execution_engine/crm_executor.py`

Migrate from `crm_sync.py` (preserve tenacity retry logic exactly):

```python
class CRMExecutor(BaseExecutor):
    async def execute(self, action_request: dict) -> dict:
        """Execute HubSpot CRM sync with tenacity retry."""
        params = action_request.get("parameters", {})
        payload = params.get("payload", {})
        
        try:
            response_data = await _push_to_hubspot(payload)
            return {"status": "success", "external_id": response_data.get("id")}
        except Exception as e:
            return {"status": "error", "error": str(e)}
```

The `_push_to_hubspot()` function is migrated **as-is** from `crm_sync.py:38-65` (including tenacity decorator, demo stub, production safety check).

#### Registration in `execution_engine.py`:

```python
ExecutionEngine.register("send_whatsapp", WhatsAppExecutor())
ExecutionEngine.register("update_crm", CRMExecutor())
```

---

### 4.3 Phase 3: Follow-Up Scheduler Refactor

**Files to create:** `app/workflows/followup_scheduler.py`

**Critical:** The existing `follow_up.py` (620 lines) is a polling-based APScheduler job that runs every 60 seconds. The new architecture must **preserve the state machine logic** while making it event-driven where possible.

**Hybrid approach:**
1. **Keep APScheduler polling** for time-based triggers (Day 0→1→3→7 transitions)
2. **Make the scheduler emit events** instead of calling Twilio directly
3. **Add event listeners** for `lead.created` and `lead.updated` to create/reset FollowUpState

```python
# app/workflows/followup_scheduler.py

class FollowUpSchedulerWorkflow:
    """
    Migrated from follow_up.py.
    
    Architecture:
    - Polling loop (APScheduler) checks for due follow-ups
    - For each due follow-up, builds payload via intelligence layer
    - Dispatches send_whatsapp via ExecutionEngine (NOT direct Twilio call)
    - Transitions state machine (Day 0→1→3→7)
    
    Changes from original:
    - No direct Twilio calls → uses ExecutionEngine
    - No direct DB writes for DLQ → ExecutionEngine handles it
    - Emits followup.sent event on success
    """
    
    @staticmethod
    async def check_and_send():
        """Called by APScheduler every 60s. Args-less for APScheduler compat."""
        # ... migrated logic from follow_up.py:313-620 ...
        # Key changes:
        # - Replace Twilio client calls with:
        #   await ExecutionEngine.dispatch({"action_type": "send_whatsapp", ...})
        # - Remove DLQEvent writes (handled by ExecutionEngine)
        # - Add EventBus.publish("followup.sent", ...) after successful send
    
    @staticmethod
    async def on_lead_created(event: dict):
        """Event handler: create FollowUpState when a new lead arrives."""
        # Creates FollowUpState with status=active, stage=Day 0
        pass
```

---

### 4.4 Phase 4: WhatsApp Agent (Core agent.py Extraction)

**Files to create:** `app/agents/whatsapp_agent.py`

**This is the hardest part.** The existing `process_chat()` in `agent.py` (830+ lines) must be decomposed into focused methods.

**Decomposition strategy:**

| Existing agent.py Functionality | New Location |
|---|---|
| Session creation/lookup (236-268) | `WhatsAppAgent.fetch_context()` |
| Lead creation/lookup (236-268) | `WhatsAppAgent.fetch_context()` |
| FollowUpState management (275-308) | `WhatsAppAgent.fetch_context()` |
| Closing/opt-out detection (310-339) | `WhatsAppAgent.analyze()` — pre-check |
| Instant-reply intercept (347-372) | `WhatsAppAgent._instant_reply()` |
| Property intent intercept (377-448) | `WhatsAppAgent._property_intent()` |
| Guardrail intercept (453-464) | `WhatsAppAgent._guardrail()` |
| Human handoff (469-495) | `WhatsAppAgent._human_handoff()` |
| History window + sanitize (500-522) | `WhatsAppAgent.fetch_context()` |
| Lead summary injection (524-581) | `WhatsAppAgent.analyze()` |
| RAG gateway (583-632) | `WhatsAppAgent._rag_retrieve()` |
| Gemini chat with retries (634-734) | `WhatsAppAgent._llm_chat()` |
| Tool execution + lead update (736-845) | `WhatsAppAgent._execute_tool()` |
| ML scoring pipeline (874-977) | **Separate event handler** — not in agent |
| Agent matching (979-1028) | **Separate event handler** — not in agent |
| Message saving (1034-1066) | `WhatsAppAgent.analyze()` |
| Re-arm Day 0 follow-up (1044-1063) | Publish event → FollowUpWorkflow |

**Why separate ML scoring into its own handler?**

The original plan had the WhatsAppAgent calling `calculate_lead_score()` and `match_best_agent()` inside `analyze()`. This is **wrong** — it makes the WhatsApp response wait for ML computation. Instead:

1. WhatsAppAgent responds to the user **immediately** (fast path)
2. WhatsAppAgent publishes `whatsapp.response.generated` event **after** deciding
3. A separate `LeadScoringHandler` (registered on EventBus) picks up the event and runs ML asynchronously
4. If the ML scoring bumps probability above 82, it publishes `lead.hot` → triggers notification

This mirrors the existing architecture where `sync_lead_to_crm()` runs as `asyncio.create_task()` — non-blocking.

```python
# app/agents/whatsapp_agent.py

class WhatsAppAgent(BaseAgent):
    """
    Handles incoming WhatsApp messages.
    
    Lifecycle:
    1. fetch_context() → session, lead, followup state, history
    2. analyze() → guardrails → instant reply → intent → RAG → LLM → tool
    3. decide() → package action request for ExecutionEngine
    
    Post-decision event: "whatsapp.response.generated"
    - Picked up by LeadScoringHandler (async ML pipeline)
    - Picked up by FollowUpWorkflow (re-arm Day 0)
    """
    
    async def fetch_context(self, event: dict) -> dict:
        # Session/Lead creation/lookup
        # FollowUpState management
        # History window (last 6 turns)
        # Returns context dict with all DB state
    
    async def analyze(self, event: dict, context: dict) -> dict:
        # 1. Pre-checks (instant reply, property intent, guardrail, handoff)
        # 2. Inject lead summary
        # 3. RAG retrieval (if eligible)
        # 4. Gemini chat with 3-retry + concurrent name extraction
        # 5. Tool execution (extract_lead_info)
        # 6. Save messages
        # Returns analysis dict with reply_text and tool_results
    
    async def decide(self, event: dict, analysis: dict, context: dict) -> dict:
        # Package reply into ActionRequest
        # If analysis has tool_result → update lead fields
        # Return ActionRequest for send_whatsapp
        
        # AFTER dispatching, publish event for async ML pipeline
        asyncio.create_task(EventBusClient.publish(
            event_type="whatsapp.response.generated",
            tenant_id=event["tenant_id"],
            entity_id=event["entity_id"],
            payload={"analysis": analysis, "context": context}
        ))
        
        return {
            "action_type": "send_whatsapp",
            "tenant_id": event["tenant_id"],
            "entity_id": event["entity_id"],
            "parameters": {
                "phone": context["phone"],
                "message": analysis["reply_text"],
                "media_url": analysis.get("media_url")
            }
        }
```

#### `app/agents/lead_scoring_handler.py` (new)

```python
class LeadScoringHandler:
    """Async ML pipeline triggered by whatsapp.response.generated."""
    
    @staticmethod
    async def handle(event: dict):
        """Picked up by EventBus subscription."""
        # 1. Run calculate_lead_score()
        # 2. Run match_best_agent()
        # 3. Run budget alignment
        # 4. If probability >= 82: publish lead.hot → trigger notification
        # 5. Update lead fields in DB
```

---

### 4.5 Phase 5: Remaining Agents & Workflows

#### `app/agents/sales_agent.py`

```python
class SalesAgent(BaseAgent):
    """Listens for lead.scored. Detects objections, advises next-best-action."""
    
    SUBSCRIPTIONS = ["lead.scored", "conversation.updated"]
    
    async def fetch_context(self, event: dict) -> dict:
        # Fetch lead, conversation history, previous objections
        pass
    
    async def analyze(self, event: dict, context: dict) -> dict:
        # LLM prompt: "Analyze conversation for objections (Price, Timeline, Location)"
        # Returns objection type, urgency, recommended action
        pass
    
    async def decide(self, event: dict, analysis: dict, context: dict) -> dict:
        # If objection detected → create task for human agent
        return {
            "action_type": "create_task",
            "tenant_id": event["tenant_id"],
            "entity_id": event["entity_id"],
            "parameters": {
                "task_name": f"Call Lead - {analysis['objection']} Negotiation",
                "priority": analysis["urgency"]
            }
        }
```

#### `app/agents/marketing_agent.py`

```python
class MarketingAgent(BaseAgent):
    """Listens for campaign.completed. Generates ROI summary."""
    
    SUBSCRIPTIONS = ["campaign.completed", "cron.weekly_report"]
    
    async def analyze(self, event: dict, context: dict) -> dict:
        # Fetch campaign data + lead quality scores
        # LLM: generate markdown summary
        # Return report text
        pass
    
    async def decide(self, event: dict, analysis: dict, context: dict) -> dict:
        # Email report to admin or post to dashboard
        return {
            "action_type": "notify_admin",
            ...
        }
```

#### `app/agents/customer_success_agent.py`

```python
class CustomerSuccessAgent(BaseAgent):
    """Listens for payment.due. Sends friendly reminders."""
    
    SUBSCRIPTIONS = ["payment.due", "booking.completed"]
    
    async def analyze(self, event: dict, context: dict) -> dict:
        # LLM: draft friendly payment reminder
        pass
    
    async def decide(self, event: dict, analysis: dict, context: dict) -> dict:
        return {
            "action_type": "send_whatsapp",
            "parameters": {"message": analysis["reminder_text"]}
        }
```

#### `app/workflows/crm_automation.py`

```python
class CRMAutomationWorkflow:
    """Listens for lead.qualified. Routes to best agent, creates tags."""
    
    @staticmethod
    async def handle(event: dict):
        # Call match_best_agent()
        # Generate tags (HOT_LEAD, Premium_Budget, etc.)
        # Dispatch update_crm via ExecutionEngine
```

#### `app/workflows/competitor_monitor.py`

```python
class CompetitorMonitorWorkflow:
    """Scheduled job (cron). Fetches mock competitor data, publishes alerts."""
    
    @staticmethod
    async def run():
        # Fetch competitor pricing
        # If significant change → publish market.alert.generated
```

---

## 5. Migration Mapping

| Existing File | Lines | New Home | Strategy |
|---|---|---|---|
| `agent.py` — Twilio sending | ~30 scattered | `WhatsAppExecutor` | Direct copy |
| `agent.py` — Session/Lead CRUD | ~50 lines | `WhatsAppAgent.fetch_context()` | Migrate |
| `agent.py` — Instant-reply intercept | ~25 lines | `WhatsAppAgent._instant_reply()` | Migrate |
| `agent.py` — Property intent | ~70 lines | `WhatsAppAgent._property_intent()` | Migrate |
| `agent.py` — Guardrails | ~15 lines | `WhatsAppAgent._guardrail()` | Migrate |
| `agent.py` — Human handoff | ~30 lines | `WhatsAppAgent._human_handoff()` | Migrate |
| `agent.py` — History window | ~25 lines | `WhatsAppAgent.fetch_context()` | Migrate |
| `agent.py` — Lead summary | ~60 lines | `WhatsAppAgent.analyze()` | Migrate |
| `agent.py` — RAG retrieval | ~50 lines | `WhatsAppAgent._rag_retrieve()` | Migrate |
| `agent.py` — Gemini chat + retries | ~100 lines | `WhatsAppAgent._llm_chat()` | Migrate |
| `agent.py` — Tool execution | ~110 lines | `WhatsAppAgent._execute_tool()` | Migrate |
| `agent.py` — ML scoring | ~100 lines | `LeadScoringHandler` | New (refactored) |
| `agent.py` — Agent matching | ~50 lines | `LeadScoringHandler` | New (refactored) |
| `agent.py` — Message saving | ~30 lines | `WhatsAppAgent.decide()` | Migrate |
| `crm_sync.py` — All | 132 lines | `CRMExecutor` | ~95% direct copy |
| `follow_up.py` — State machine | ~420 lines | `FollowUpSchedulerWorkflow` | Copy + refactor Twilio calls |
| `follow_up.py` — Payload builder | ~240 lines | `FollowUpSchedulerWorkflow` | Copy as-is |
| `follow_up.py` — Quiet hours | ~15 lines | `FollowUpSchedulerWorkflow` | Copy as-is |
| `main.py` — Twilio webhook | ~80 lines | Keep in main.py, call WhatsAppAgent | Refactor call target |
| `main.py` — Chat endpoint | ~20 lines | Keep in main.py, call WhatsAppAgent | Refactor call target |
| `main.py` — Scheduler jobs | ~30 lines | Keep in main.py, update call targets | Refactor |
| `main.py` — Escalation cron | ~80 lines | Keep in main.py | Defer refactor |
| `main.py` — All other endpoints | ~700 lines | Keep in main.py | No change |

---

## 6. main.py Updated Routing

### `/api/v1/whatsapp` (Twilio Webhook)

```python
@app.post("/api/v1/whatsapp")
async def whatsapp_webhook(
    request: Request, background_tasks: BackgroundTasks,
    MessageSid: str = Form(None), From: str = Form(...), Body: str = Form(...),
    current_client: models.Client = Depends(auth.get_client_by_api_key),
    db: DBSession = Depends(get_db)
):
    # ...SECURITY: signature validation (same as before)...
    # ...dedup via WebhookLog (same as before)...
    
    session_id = From.replace("whatsapp:", "")
    client_id = current_client.id
    
    # Duplicate protection
    if MessageSid:
        existing = db.query(models.WebhookLog).filter(
            models.WebhookLog.message_sid == MessageSid).first()
        if existing:
            return Response(content="<Response></Response>", media_type="application/xml")
        db.add(models.WebhookLog(message_sid=MessageSid))
        db.commit()
    
    # Format as Event
    incoming_event = {
        "event_type": "whatsapp.received",
        "tenant_id": client_id,
        "entity_id": session_id,
        "payload": {
            "phone": session_id,
            "message": Body,
            "message_sid": MessageSid or "unknown"
        }
    }
    
    # Dispatch to EventBus (not direct agent call)
    await EventBusClient.publish(
        event_type="whatsapp.received",
        tenant_id=client_id,
        entity_id=session_id,
        payload={
            "phone": session_id,
            "message": Body,
            "message_sid": MessageSid or "unknown"
        }
    )
    
    # But we ALSO need the sync agent call for the 15s timeout pattern:
    # Option A: Have WhatsAppAgent subscribed to "whatsapp.received" on EventBus
    # Option B: Keep direct agent call with asyncio.create_task for now (Phase 1-3)
    #
    # RECOMMENDATION for Phase 1-3: Keep direct agent call, ADD event bus publish.
    # In Phase 4, switch to EventBus subscription.
    
    redis_key = f"session_lock:{session_id}"
    async with redis_client.lock(redis_key, timeout=20.0, blocking_timeout=30.0):
        try:
            reply_text = await asyncio.wait_for(
                agent.process_event(incoming_event),  # WhatsAppAgent
                timeout=15.0
            )
            twiml = MessagingResponse()
            twiml.message(reply_text)
            return Response(content=str(twiml), media_type="application/xml")
        except asyncio.TimeoutError:
            background_tasks.add_task(
                background_process_and_push, session_id, Body, client_id)
            twiml = MessagingResponse()
            twiml.message("Just checking that for you...")
            return Response(content=str(twiml), media_type="application/xml")
```

### `/api/v1/chat` (Website Chat)

```python
@app.post("/api/v1/chat")
async def chat_endpoint(
    session_id: str, message: str,
    current_client: models.Client = Depends(auth.get_client_by_api_key),
    db: DBSession = Depends(get_db)
):
    client_id = current_client.id
    prefix = f"{client_id}_"
    scoped_session_id = session_id if session_id.startswith(prefix) else f"{prefix}{session_id}"
    
    try:
        # Same pattern as WhatsApp webhook
        incoming_event = {
            "event_type": "chat.received",
            "tenant_id": client_id,
            "entity_id": scoped_session_id,
            "payload": {"message": message}
        }
        reply = await agent.process_event(incoming_event)
        return {"status": "success", "session_id": session_id, "reply": reply}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### Lifespan (Scheduler + EventBus)

```python
@asynccontextmanager
async def lifespan(app):
    # Start EventBus processing loop
    EventBusClient.start()
    
    # Subscribe agents to events
    EventBusClient.subscribe("whatsapp.received", WhatsAppAgent().process_event)
    EventBusClient.subscribe("lead.scored", SalesAgent().process_event)
    EventBusClient.subscribe("payment.due", CustomerSuccessAgent().process_event)
    EventBusClient.subscribe("lead.qualified", CRMAutomationWorkflow.handle)
    EventBusClient.subscribe("whatsapp.response.generated", LeadScoringHandler.handle)
    
    # Start scheduler
    scheduler.start()
    logger.info("IREIOS 3.0: EventBus + Scheduler started")
    yield
    scheduler.shutdown()
    await EventBusClient.stop()
```

---

## 7. Testing Strategy

| Phase | Test | Method |
|---|---|---|
| **Phase 1** | EventBus publish → deliver to subscribed handler | Unit test with mock handler |
| **Phase 1** | ExecutionEngine dispatch → executor called | Unit test with mock executor |
| **Phase 1** | ExecutionEngine error → DLQEvent created | Integration test with test DB |
| **Phase 2** | WhatsAppExecutor sends via Twilio API | `TEST_MODE=true` assertion |
| **Phase 2** | CRMExecutor retries on 429/5xx | Mock httpx, verify tenacity |
| **Phase 3** | Follow-up state machine transitions | Integration test with FollowUpState |
| **Phase 3** | Quiet hours shift correctly | Unit test time mocking |
| **Phase 4** | WhatsAppAgent full pipeline (RAG → LLM → Tool → Reply) | Integration with Gemini + FAISS |
| **Phase 4** | Guardrail intercepts topic drift | Unit test check_topic_drift |
| **Phase 4** | Human handoff triggers notification + closes session | Integration test |
| **Phase 5** | End-to-end: WhatsApp msg → Agent → Executor → Event | Full integration |
| **All** | Existing `task3_runner.py` (126 cases) passes | `python task3_runner.py` |
| **All** | Tenant isolation not broken | `python gate_isolation_test.py` |
| **All** | DLQ still works | `python gate_dlq_drill.py` → `python dlq_replay.py` |

**Critical:** Until Phase 4 is complete, **all existing tests must still pass against the old agent.py path**. The new code runs alongside the old code — we don't remove old code until the new path is validated.

---

## 8. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **agent.py extraction breaks LLM responses** | High | High | Keep old path side-by-side; route traffic gradually (10% → 50% → 100%) |
| **EventBus asyncio.Queue messages lost on crash** | Medium | Medium | Phase 1 is in-process; Phase 5 upgrades to Redis Streams for durability |
| **Follow-up scheduler missed events during transition** | Medium | High | Keep old follow_up.py running until Phase 3 validated; compare outputs |
| **Deadlock: agent awaits ExecutionEngine which awaits agent** | Low | High | Never allow circular dependencies → agents call ExecutionEngine one-way |
| **Gemini API timeout in new architecture** | Medium | Medium | Preserve existing 6s timeout + 3-retry logic in WhatsAppAgent |
| **`decide()` signature change breaks handlers** | Medium | Medium | Our fix (pass `event` to all lifecycle methods) prevents this |
| **Race condition: EventBus handler modifies DB while agent holds session** | Medium | Medium | Use Redis lock (already exists in main.py) — extend to EventBus handlers |

---

## Appendix A: File Creation Order

```
Phase 1 (Foundation)
├── app/clients/__init__.py
├── app/clients/event_bus_client.py
├── app/clients/graph_client.py
├── app/execution_engine/__init__.py
├── app/execution_engine/base_executor.py
├── app/execution_engine/execution_engine.py
├── app/agents/__init__.py
├── app/agents/base_agent.py
├── app/workflows/__init__.py
└── Update main.py lifespan + EventBus start/stop

Phase 2 (Executor Extraction)
├── app/execution_engine/whatsapp_executor.py
├── app/execution_engine/crm_executor.py
└── Register executors in execution_engine.py

Phase 3 (Follow-Up Refactor)
└── app/workflows/followup_scheduler.py
    └── Still uses APScheduler; replace Twilio calls with ExecutionEngine.dispatch()

Phase 4 (Core WhatsApp Agent) — IN PARALLEL:
├── app/agents/whatsapp_agent.py
├── app/agents/lead_scoring_handler.py
└── Update main.py webhooks to call WhatsAppAgent

Phase 5 (Remaining Agents)
├── app/agents/sales_agent.py
├── app/agents/marketing_agent.py
├── app/agents/customer_success_agent.py
├── app/workflows/crm_automation.py
├── app/workflows/competitor_monitor.py
├── Decommission agent.py, crm_sync.py, follow_up.py
└── Upgrade EventBus to Redis Streams (optional)
```

## Appendix B: Key Decisions

1. **Why in-process EventBus first, not Kafka/Redis Streams?** — The existing Redis infrastructure supports Redis Streams, but the overhead of distributed messaging isn't justified until we have multi-worker deployments. In-process asyncio.Queue is simpler, faster, and zero-infrastructure for Phase 1-4.

2. **Why keep APScheduler for follow-ups?** — The follow-up scheduler checks due dates (e.g., "is it time for Day 3 follow-up?"). This is inherently a polling problem, not an event problem. Event-driven follow-ups would require a timer service (e.g., RabbitMQ delayed queues). APScheduler is simpler and already battle-tested in this codebase.

3. **Why not create a separate "CEO Orchestrator"?** — The IREIOS 3.0 diagrams show one, but it's unnecessary indirection at this stage. The EventBus + EventRouter (simple dict mapping `event_type → agent`) serves the same purpose with less complexity. A CEO Orchestrator can be added later if agent routing logic becomes complex.

4. **Why publish `whatsapp.response.generated` from `decide()` instead of from `ExecutionEngine`?** — The ML scoring pipeline needs data about the LLM response (analysis) and current context (lead state). The ExecutionEngine only knows about the action execution result, not the reasoning behind it. The agent has the richest data, so it publishes from there.
