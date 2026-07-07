# IREIOS 3.0 — Multi-Agent Event-Driven Architecture

Compiled reference diagrams for the IREIOS platform (Phase 3.0), covering the system
overview and all five execution paths (A–E). Diagrams use [Mermaid](https://mermaid.js.org),
which renders natively on GitHub, GitLab, Notion, and most static site generators. In VS Code,
install the **"Markdown Preview Mermaid Support"** extension to preview locally, or paste any
block into [mermaid.live](https://mermaid.live).

## Legend

| Color | Meaning |
|---|---|
| Gray | Infrastructure / triggers / neutral steps |
| Blue | Data & execution layer (writes, engines) |
| Teal | Events / message bus |
| Purple | AI agents |
| Amber | Decision points / scoring |
| Coral | Fan-out targets / failure / escalation |

---

## System overview (Layers 1–11)

```mermaid
flowchart LR
    I1[WhatsApp] --> L1
    I2[Website] --> L1
    I3[Meta / Google Ads] --> L1
    I4[Other sources] --> L1

    L1[1. Lead enters system] --> L2[2. AI qualifies + stores lead]
    L2 --> L3[3. CEO AI orchestrator]
    L3 --> L4[4. Actions executed]
    L4 --> L5[5. Dashboard + insights]

    L3 <--> AG["6. AI agents<br/>Marketing, CRM, Sales, WhatsApp, Pricing..."]
    AG <--> KG["7. Knowledge graph<br/>Leads, projects, units, payments..."]
    KG --> PE["8. Predictive engine<br/>Scores, forecasts, risk"]
    KG --> EE["9. Execution engine<br/>Autonomous actions"]
    PE --> CM["10. Company memory<br/>Tasks, approvals, objections"]
    EE --> CM
    KG --> MI["11. Market intelligence<br/>Competitor + demand signals"]
    CM --> SL["Self-learning system<br/>Improves models + playbooks"]
    MI --> SL
    SL --> AG

    classDef gray fill:#F1EFE8,stroke:#5F5E5A,color:#2C2C2A;
    classDef blue fill:#E6F1FB,stroke:#185FA5,color:#0C447C;
    classDef teal fill:#E1F5EE,stroke:#0F6E56,color:#085041;
    classDef purple fill:#EEEDFE,stroke:#534AB7,color:#3C3489;
    classDef amber fill:#FAEEDA,stroke:#854F0B,color:#633806;
    classDef coral fill:#FAECE7,stroke:#993C1D,color:#712B13;

    class I1,I2,I3,I4 gray
    class L1,L2,L3,L4,L5 blue
    class AG purple
    class KG teal
    class PE,EE amber
    class CM,MI coral
    class SL gray
```

---

## Path A — Lead intake & qualification (happy path, part 1)

```mermaid
flowchart TD
    A1["WhatsApp message<br/>New inbound message"]
    A2["API gateway<br/>RBAC + tenant resolution"]
    A3["Event bus<br/>whatsapp.received"]
    A4["CEO orchestrator<br/>Routes to WhatsApp AI"]
    A5["Context fetch<br/>Postgres, FAISS, Neo4j"]
    A6{"Qualification check<br/>Enough info gathered?"}
    A7["Clarifying question sent<br/>waits for next message (Path B)"]

    A1 --> A2 --> A3 --> A4 --> A5 --> A6
    A6 -->|No| A7
    A6 -->|"Yes → continues below"| B1

    classDef gray fill:#F1EFE8,stroke:#5F5E5A,color:#2C2C2A;
    classDef blue fill:#E6F1FB,stroke:#185FA5,color:#0C447C;
    classDef teal fill:#E1F5EE,stroke:#0F6E56,color:#085041;
    classDef purple fill:#EEEDFE,stroke:#534AB7,color:#3C3489;
    classDef amber fill:#FAEEDA,stroke:#854F0B,color:#633806;
    classDef coral fill:#FAECE7,stroke:#993C1D,color:#712B13;

    class A1 gray
    class A2 blue
    class A3 teal
    class A4 purple
    class A5 purple
    class A6 amber
    class A7 gray
    class B1 teal
```

## Path A — Qualified lead fan-out (part 2)

```mermaid
flowchart TD
    B1["Action request<br/>update_lead"]
    B2["Execution engine<br/>n8n / LangGraph"]
    B3["CRM write<br/>Idempotency check, Postgres"]
    B4["Event bus<br/>lead.qualified"]
    B5["Neo4j graph<br/>Async, protects latency"]
    B6["Company memory<br/>Logs action + reasoning"]
    B7["Executive dashboard<br/>Real-time SSE pulse"]

    B1 --> B2 --> B3 --> B4
    B4 --> B5
    B4 --> B6
    B4 --> B7

    classDef gray fill:#F1EFE8,stroke:#5F5E5A,color:#2C2C2A;
    classDef blue fill:#E6F1FB,stroke:#185FA5,color:#0C447C;
    classDef teal fill:#E1F5EE,stroke:#0F6E56,color:#085041;
    classDef purple fill:#EEEDFE,stroke:#534AB7,color:#3C3489;
    classDef amber fill:#FAEEDA,stroke:#854F0B,color:#633806;
    classDef coral fill:#FAECE7,stroke:#993C1D,color:#712B13;

    class B1 teal
    class B2 blue
    class B3 blue
    class B4 teal
    class B5 purple
    class B6 teal
    class B7 coral
```

## Path A — Scoring to confirmation (part 3)

```mermaid
flowchart TD
    C1["CRM AI<br/>Auto-tags, publishes lead.assigned"]
    C2["Predictive engine<br/>e.g. 84% conversion, hot"]
    C3["Sales AI<br/>e.g. schedule site visit"]
    C4{"Approval check<br/>requires_approval?"}
    C5["Calendar executor<br/>site_visit.scheduled"]
    C6["Confirmation sent<br/>whatsapp.sent, via Twilio"]
    C7(["Routes to Path C<br/>approval queue"])

    C1 --> C2 --> C3 --> C4
    C4 -->|No| C5 --> C6
    C4 -->|Yes| C7

    classDef gray fill:#F1EFE8,stroke:#5F5E5A,color:#2C2C2A;
    classDef blue fill:#E6F1FB,stroke:#185FA5,color:#0C447C;
    classDef teal fill:#E1F5EE,stroke:#0F6E56,color:#085041;
    classDef purple fill:#EEEDFE,stroke:#534AB7,color:#3C3489;
    classDef amber fill:#FAEEDA,stroke:#854F0B,color:#633806;
    classDef coral fill:#FAECE7,stroke:#993C1D,color:#712B13;

    class C1 purple
    class C2 amber
    class C3 purple
    class C4 amber
    class C5 blue
    class C6 teal
    class C7 coral
```

## Path B — Multi-turn conversation

Path B is not a separate branch — every new WhatsApp message re-enters **Path A** at the top.
The only difference is that Context Fetch pulls short-term memory (previous questions asked)
and company memory (previously extracted intent), so the WhatsApp AI skips fields it already
has and only asks for what's missing. This loop continues until the qualification check in
Path A part 1 returns "Yes."

---

## Path C — Human-in-the-loop approval (Maitri's automation engine)

```mermaid
flowchart TD
    D1["Sales AI flags action<br/>requires_approval = true"]
    D2["Workflow pauses<br/>n8n / LangGraph"]
    D3["Notify manager<br/>Dashboard or WhatsApp"]
    D4{"Manager decision"}
    D5["Rejected<br/>Logged to company memory"]
    D6["Approved<br/>Resumes, sends proposal"]
    D7["Publish result event<br/>Fans out to Neo4j, memory, SSE"]

    D1 --> D2 --> D3 --> D4
    D4 -->|Reject| D5 --> D7
    D4 -->|Approve| D6 --> D7

    classDef gray fill:#F1EFE8,stroke:#5F5E5A,color:#2C2C2A;
    classDef blue fill:#E6F1FB,stroke:#185FA5,color:#0C447C;
    classDef teal fill:#E1F5EE,stroke:#0F6E56,color:#085041;
    classDef purple fill:#EEEDFE,stroke:#534AB7,color:#3C3489;
    classDef amber fill:#FAEEDA,stroke:#854F0B,color:#633806;
    classDef coral fill:#FAECE7,stroke:#993C1D,color:#712B13;

    class D1 purple
    class D2 blue
    class D3 amber
    class D4 amber
    class D5 coral
    class D6 teal
    class D7 teal
```

---

## Path D — Disaster recovery (execution failure)

```mermaid
flowchart TD
    E1["API call fails<br/>HubSpot, Twilio, or Meta"]
    E2["Retry with backoff<br/>Up to 3 attempts"]
    E3{"Retry limit reached?"}
    E4["Fallback channel<br/>e.g. send via email instead"]
    E5{"Fallback still failed?"}
    E6["Escalate to DLQ<br/>Written to dlq_events"]
    E7["Replay recovers data<br/>dlq_replay.py, once API is back"]

    E1 --> E2 --> E3
    E3 -->|No| E2
    E3 -->|Yes| E4 --> E5
    E5 -->|Yes| E6 --> E7
    E5 -->|No, delivered| E1

    classDef gray fill:#F1EFE8,stroke:#5F5E5A,color:#2C2C2A;
    classDef blue fill:#E6F1FB,stroke:#185FA5,color:#0C447C;
    classDef teal fill:#E1F5EE,stroke:#0F6E56,color:#085041;
    classDef purple fill:#EEEDFE,stroke:#534AB7,color:#3C3489;
    classDef amber fill:#FAEEDA,stroke:#854F0B,color:#633806;
    classDef coral fill:#FAECE7,stroke:#993C1D,color:#712B13;

    class E1 coral
    class E2 amber
    class E3 amber
    class E4 blue
    class E5 amber
    class E6 coral
    class E7 teal
```

---

## Path E — Scheduled / background work (proactive engine)

```mermaid
flowchart TD
    F1["APScheduler cron<br/>Runs every 60 seconds"]
    F2["Check FollowUpState<br/>Postgres, via follow_up.py"]
    F3{"Trigger found?"}
    F4["Send follow-up<br/>Logs followup.sent"]
    F5["Sleep<br/>no action"]
    F6["Midnight job<br/>Market intel + daily rollups"]

    F1 --> F2 --> F3
    F3 -->|Yes| F4
    F3 -->|No| F5
    F1 -.->|At midnight| F6

    classDef gray fill:#F1EFE8,stroke:#5F5E5A,color:#2C2C2A;
    classDef blue fill:#E6F1FB,stroke:#185FA5,color:#0C447C;
    classDef teal fill:#E1F5EE,stroke:#0F6E56,color:#085041;
    classDef purple fill:#EEEDFE,stroke:#534AB7,color:#3C3489;
    classDef amber fill:#FAEEDA,stroke:#854F0B,color:#633806;
    classDef coral fill:#FAECE7,stroke:#993C1D,color:#712B13;

    class F1 gray
    class F2 blue
    class F3 amber
    class F4 teal
    class F5 gray
    class F6 gray
```

---

## Appendix — Original architecture reference (source ASCII diagram)

```text
IREIOS 3.0 — MULTI-AGENT EVENT-DRIVEN ARCHITECTURE (REFINED)
────────────────────────────────────────────────────────────

PATH A — New lead, straightforward qualification (Happy Path)
────────────────────────────────────────────────────────────
WhatsApp message
  ↓
API Gateway → RBAC / API Key Validation → resolves client_id + tenant
  ↓
Publish event: `whatsapp.received` → Central Event Bus (Kafka/Redis)
  ↓
CEO AI Orchestrator (Layer 1) → Routes task to WhatsApp AI (Layer 2)
  ↓
Context Fetch (Layer 3 & 9):
      ├─ Postgres (Current transactional state — Source of Truth)
      ├─ FAISS (Past conversation vector history)
      └─ Neo4j (Entity relationships: Lead → Project → Unit)
  ↓
WhatsApp AI extracts intent (budget, location, unit type, objections)
  ↓
Enough info to qualify?
  ├── NO  → Generates clarifying question → WhatsApp Executor → (Ends, waits for Path B)
  └── YES → continue below
  ↓
Action Request: `update_lead`
  ↓
Execution / Automation Engine (n8n / LangGraph)
  ↓
Idempotency check → CRM Executor writes to Postgres (Transactional)
  ↓
Publish event: `lead.qualified` → Central Event Bus
  ↓
        ┌────────────────────────┬────────────────────────┬────────────────────────┐
        ▼                        ▼                        ▼
  Neo4j Knowledge Graph    Company Memory (Layer 9)   Executive Dashboard (Layer 11)
  (STRICTLY ASYNC to       (Logs the action PLUS      (Pushes real-time SSE pulse
  protect chat latency)    objections & AI reasoning) to UI / Digital Twin / Timeline)
        └────────────────────────┴────────────────────────┴────────────────────────┘
  ↓
CRM AI (Layer 2): Auto-tags, routes to human agent → publishes `lead.assigned`
  ↓
Predictive Engine (Layer 4): Calculates Lead Conversion Score (e.g., 84% / Hot)
  ↓
Sales AI (Layer 2): Determines Next Best Action (e.g., "Schedule site visit for Tower B")
  ↓
requires_approval?
  ├── YES → Routes to Approval Queue (Human-in-the-loop — See Path C)
  └── NO  → continue below
  ↓
Execution Engine (n8n / LangGraph) → Calendar Executor → `site_visit.scheduled`
  ↓
WhatsApp AI generates confirmation → WhatsApp Executor sends via Twilio
  ↓
Publish event: `whatsapp.sent` → Event Bus → SSE → AI Timeline UI


PATH B — Multi-turn conversation (Info gathered over several messages)
────────────────────────────────────────────────────────────
Each new WhatsApp message triggers `whatsapp.received` and re-enters Path A.
  ↓
Context Fetch pulls "Short-Term Memory" (previous questions asked) and
"Company Memory" (previously extracted intent).
  ↓
WhatsApp AI realizes it already has [Location] and only asks for [Budget].
  ↓
Loop continues until qualification criteria are met → joins Path A at "Action Request".


PATH C — Action needs human approval (Maitri's Automation Engine)
────────────────────────────────────────────────────────────
Sales AI suggests action flagged `requires_approval = true` (e.g., 10% Discount Offer)
  ↓
LangGraph / n8n workflow pauses → Sends notification to Manager (Dashboard / WhatsApp)
  ↓
Manager Decision:
  ├── REJECTED → Action logged to Company Memory ("Manager denied discount"), flow resumes.
  └── APPROVED → Execution Engine resumes → generates proposal → sends to client.
  ↓
Publish result event → Event Bus → Fan-out to Neo4j, Memory, and SSE Dashboard.


PATH D — Execution Fails (Disaster Recovery)
────────────────────────────────────────────────────────────
Execution Engine attempts API call (HubSpot, Twilio, Meta) → Fails
  ↓
Native Retry with exponential backoff (e.g., 3 attempts)
  ↓
Retry limit reached?
  ├── NO  → Retry again
  └── YES → Fallback logic (e.g., send via Email instead)
             ↓
        Still failed? → Escalate → Write to Dead Letter Queue (dlq_events)
             ↓
        `python dlq_replay.py` safely recovers data when API comes back online.


PATH E — Scheduled / Background Work (Proactive Engine)
────────────────────────────────────────────────────────────
APScheduler (Cron-based, operating outside the real-time Event Bus)
  ↓
Every 60s: `follow_up.py` checks Postgres `FollowUpState`
  ├── Trigger found → generates AI payload → sends message → logs `followup.sent` to Event Bus
  └── No trigger → sleeps
  ↓
Midnight: Triggers AI Market Intelligence (Layer 10) and Daily Rollups.
```