# IREIOS 3.0 --- AI Automation Workflows

## 1. WhatsApp AI Workflow

Handles inbound WhatsApp conversations, lead qualification, FAQs,
brochure and floor-plan sharing, site-visit requests, reminders,
follow-ups, and human escalation.

### Mermaid Diagram

``` mermaid
flowchart TD
 W1[Incoming WhatsApp Message] --> W2[API Gateway: Validate + Resolve Tenant]
 W2 --> W3[Publish whatsapp.received] --> W4[Event Bus] --> W5[WhatsApp AI]
 W5 --> W6[Fetch Lead + Conversation + Memory + Graph Context]
 W6 --> W7[Pre-Checks: Opt-Out, Guardrail, Human Handoff]
 W7 --> W8[Intent Detection] --> W9{Detected Intent?}
 W9 -->|FAQ| FAQ[FAQ Request] --> RAG[RAG / Knowledge Retrieval]
 W9 -->|Brochure| BRO[Brochure Request] --> DOC[Document Lookup]
 W9 -->|Floor Plan| FP[Floor Plan Request] --> DOC
 W9 -->|Qualification| Q[Lead Qualification] --> EXT[Extract Budget, Location, BHK, Intent]
 W9 -->|Site Visit| SV[Site Visit Request] --> VC[Check Visit Requirements]
 W9 -->|Other| GEN[General Conversation]
 RAG --> LLM[LLM Response Generation]
 DOC --> LLM
 EXT --> LLM
 VC --> LLM
 GEN --> LLM
 LLM --> DEC[WhatsApp AI Decision] --> A{Action Required?}
 A -->|Reply| SEND[send_whatsapp]
 A -->|Document| MEDIA[send_whatsapp + media_url]
 A -->|Lead Update| CRM[update_crm]
 A -->|Visit| VISIT[schedule_visit]
 A -->|Human| ESC[escalate_to_human]
 SEND --> AE[Automation Engine]
 MEDIA --> AE
 CRM --> AE
 VISIT --> AE
 ESC --> AE
 AE --> EE[Execution Engine]
 EE --> WX[WhatsApp Executor]
 EE --> CX[CRM Executor]
 EE --> CAL[Calendar Executor]
 EE --> NX[Notification Executor]
 WX --> RES[Publish Result Event]
 CX --> RES
 CAL --> RES
 NX --> RES
 RES --> EB[Event Bus]
 EB --> MEM[Company Memory]
 EB --> KG[Knowledge Graph]
 EB --> SCORE[Lead Scoring Handler]
 EB --> FU[Follow-Up Scheduler]
```

### Simple Arrow View

``` text
WhatsApp Message
        ↓
API Gateway
        ↓
whatsapp.received
        ↓
Event Bus
        ↓
WhatsApp AI
        ↓
Fetch Lead + Conversation Context
        ↓
Pre-Checks
        ↓
Intent Detection
        ↓
 ┌──────────┬──────────┬────────────┬──────────────┬─────────────┐
 ↓          ↓          ↓            ↓              ↓
FAQ      Brochure   Floor Plan   Qualification   Site Visit
 ↓          ↓          ↓            ↓              ↓
RAG     Doc Lookup  Doc Lookup   Extract Info   Visit Check
 └──────────┴──────────┴────────────┴──────────────┴─────────────┘
                              ↓
                       Generate Response
                              ↓
                         Agent Decision
                              ↓
                       Automation Engine
                              ↓
                       Execution Engine
                              ↓
       WhatsApp / CRM / Calendar / Escalation Executors
                              ↓
                         Result Event
                              ↓
                           Event Bus
                              ↓
            Memory + Graph + Scoring + Follow-Up
```

## 2. Marketing AI Workflow

Processes campaign events and scheduled reports. It combines Meta,
Google Ads, CRM lead-quality, conversion, and graph context to generate
campaign, audience, budget, and performance recommendations.

### Mermaid Diagram

``` mermaid
flowchart TD
 M1[Campaign Completed / Weekly Report Trigger] --> M2[Event Bus] --> M3[Marketing AI]
 M3 --> M4[Fetch Marketing Context]
 M4 --> META[Meta Campaign Data]
 M4 --> GOOGLE[Google Ads Data]
 M4 --> CRM[CRM Lead Quality]
 M4 --> CONV[Conversion Data]
 M4 --> KG[Knowledge Graph]
 META --> ANA[Campaign Performance Analysis]
 GOOGLE --> ANA
 CRM --> ANA
 CONV --> ANA
 KG --> ANA
 ANA --> MET[Calculate CTR, CPL, Lead Quality, Conversion]
 MET --> AUD[Audience Analysis] --> REC[Campaign Recommendation Engine]
 REC --> T{Recommendation Type?}
 T --> C[Campaign Suggestion]
 T --> A[Audience Suggestion]
 T --> B[Budget Recommendation]
 T --> R[Performance Report]
 C --> D[Marketing AI Decision]
 A --> D
 B --> D
 R --> D
 D --> AP{Approval Required?}
 AP -->|Yes| HITL[Human Approval Workflow] --> AE[Automation Engine]
 AP -->|No| AE
 AE --> EE[Execution Engine]
 EE --> API[Meta / Google Executor]
 EE --> NR[Notification / Report Executor]
 API --> EVT[Publish campaign.updated / marketing.report.generated]
 NR --> EVT
 EVT --> EB[Event Bus]
 EB --> MEM[Company Memory]
 EB --> DASH[Dashboard]
 EB --> GRAPH[Knowledge Graph]
```

### Simple Arrow View

``` text
Campaign Event / Weekly Cron
            ↓
        Event Bus
            ↓
       Marketing AI
            ↓
 Fetch Campaign + CRM Data
            ↓
 Meta + Google + Lead Quality
            ↓
 Campaign Performance Analysis
            ↓
 Audience Analysis
            ↓
 Recommendation Generation
            ↓
 Campaign / Audience / Budget / Performance Report
            ↓
 Marketing Decision
            ↓
 Approval Required?
       ↙          ↘
 Human Approval   Automation
       └──────────→ Execution Engine
                         ↓
                Meta / Google Executor
                         ↓
                    Result Event
                         ↓
                    Event Bus
                         ↓
           Memory + Dashboard + Graph
```

## 3. Sales AI Workflow

Reacts to scored leads and conversation updates. It detects objections,
determines lead priority, and recommends the next best sales action.

### Mermaid Diagram

``` mermaid
flowchart TD
 S1[lead.scored / conversation.updated] --> S2[Event Bus] --> S3[Sales AI]
 S3 --> S4[Fetch Sales Context]
 S4 --> LP[Lead Profile]
 S4 --> CH[Conversation History]
 S4 --> PO[Previous Objections]
 S4 --> LS[Lead Score]
 S4 --> VH[Site Visit History]
 LP --> ANA[Sales Analysis]
 CH --> ANA
 PO --> ANA
 LS --> ANA
 VH --> ANA
 ANA --> OD[Objection Detection] --> O{Objection Found?}
 O -->|Price| P[Price Objection]
 O -->|Location| L[Location Objection]
 O -->|Timeline| T[Timeline Objection]
 O -->|Trust| TR[Trust / Project Objection]
 O -->|No| PR[Lead Priority Analysis]
 P --> PR
 L --> PR
 T --> PR
 TR --> PR
 PR --> ST{Lead Priority?}
 ST -->|Hot| H[Hot Lead]
 ST -->|Warm| W[Warm Lead]
 ST -->|Cold| C[Cold Lead]
 H --> NBA[Next Best Action Engine]
 W --> NBA
 C --> NBA
 NBA --> ACT{Recommended Action}
 ACT --> CALL[Call Lead]
 ACT --> VISIT[Schedule Site Visit]
 ACT --> DOC[Send Brochure / Floor Plan]
 ACT --> FU[Follow-Up Later]
 ACT --> NEG[Human Negotiation]
 CALL --> DEC[Sales AI Decision]
 VISIT --> DEC
 DOC --> DEC
 FU --> DEC
 NEG --> DEC
 DEC --> AP{Requires Approval?}
 AP -->|Yes| HITL[Human Approval Workflow] --> AE[Automation Engine]
 AP -->|No| AE
 AE --> EE[Execution Engine]
 EE --> TASK[Task Executor]
 EE --> CAL[Calendar Executor]
 EE --> WA[WhatsApp Executor]
 EE --> NOT[Notification Executor]
 TASK --> EVT[Publish Sales Action Event]
 CAL --> EVT
 WA --> EVT
 NOT --> EVT
 EVT --> EB[Event Bus]
 EB --> CRM[CRM Automation]
 EB --> MEM[Company Memory]
 EB --> DASH[Dashboard]
```

### Simple Arrow View

``` text
lead.scored / conversation.updated
                  ↓
              Event Bus
                  ↓
               Sales AI
                  ↓
       Fetch Complete Lead Context
                  ↓
          Objection Detection
                  ↓
 Price / Location / Timeline / Trust
                  ↓
          Lead Priority Analysis
                  ↓
          Hot / Warm / Cold
                  ↓
          Next Best Action
                  ↓
 Call / Site Visit / Send Docs / Follow-Up / Negotiation
                  ↓
            Sales Decision
                  ↓
          Approval Required?
             ↙         ↘
       Human Approval   Automation
             └──────────→ Execution Engine
                              ↓
                 Task / Calendar / WhatsApp
                              ↓
                     Sales Action Event
                              ↓
                         Event Bus
                              ↓
                CRM + Memory + Dashboard
```

## 4. Customer Success AI Workflow

Automates payment reminders, document reminders, referral requests,
review collection, and renewal reminders based on customer lifecycle
events.

### Mermaid Diagram

``` mermaid
flowchart TD
 T[Trigger Event] --> PD[payment.due]
 T --> DP[document.pending]
 T --> BC[booking.completed]
 T --> CO[customer.onboarded]
 T --> RD[renewal.due]
 PD --> EB[Event Bus]
 DP --> EB
 BC --> EB
 CO --> EB
 RD --> EB
 EB --> CS[Customer Success AI] --> FC[Fetch Customer Context]
 FC --> CP[Customer Profile]
 FC --> PS[Payment Status]
 FC --> DS[Document Status]
 FC --> BH[Booking History]
 FC --> CH[Conversation History]
 CP --> LA[Customer Lifecycle Analysis]
 PS --> LA
 DS --> LA
 BH --> LA
 CH --> LA
 LA --> RA{Required Action?}
 RA -->|Payment Due| PR[Payment Reminder]
 RA -->|Document Missing| DR[Document Reminder]
 RA -->|Successful Customer| RR[Referral Request]
 RA -->|Completed Journey| RC[Review Collection]
 RA -->|Renewal Due| REN[Renewal Reminder]
 PR --> MSG[Generate Personalized Message]
 DR --> MSG
 RR --> MSG
 RC --> MSG
 REN --> MSG
 MSG --> DEC[Customer Success Decision] --> AE[Automation Engine] --> EE[Execution Engine]
 EE --> WA[WhatsApp Executor]
 EE --> CRM[CRM Executor]
 WA --> EVT[Publish Customer Event]
 CRM --> EVT
 EVT --> BUS[Event Bus]
 BUS --> MEM[Company Memory]
 BUS --> CA[CRM Automation]
 BUS --> DASH[Dashboard]
```

### Simple Arrow View

``` text
Payment / Document / Booking / Renewal Event
                       ↓
                   Event Bus
                       ↓
              Customer Success AI
                       ↓
             Fetch Customer Context
                       ↓
             Lifecycle State Analysis
                       ↓
               Required Action?
                       ↓
 Payment / Document / Referral / Review / Renewal
                       ↓
          Generate Personalized Message
                       ↓
          Customer Success Decision
                       ↓
              Automation Engine
                       ↓
              Execution Engine
                       ↓
            WhatsApp + CRM Executor
                       ↓
                Customer Event
                       ↓
                   Event Bus
                       ↓
            Memory + CRM + Dashboard
```

## 5. CRM Automation Workflow

A deterministic workflow for lead classification, auto-tagging, agent
matching, routing, CRM task creation, synchronization, retry, and DLQ
handling.

### Mermaid Diagram

``` mermaid
flowchart TD
 R1[lead.created / lead.qualified / lead.scored] --> R2[Event Bus] --> R3[CRM Automation]
 R3 --> R4[Fetch Lead Context]
 R4 --> LD[Lead Data]
 R4 --> LS[Lead Score]
 R4 --> BA[Budget Alignment]
 R4 --> LP[Location Preference]
 R4 --> AA[Agent Availability]
 LD --> LC[Lead Classification]
 LS --> LC
 BA --> LC
 LP --> LC
 LC --> ST{Lead Stage?}
 ST -->|High Score| HOT[Hot]
 ST -->|Medium Score| WARM[Warm]
 ST -->|Low Score| COLD[Cold]
 HOT --> TAG[Generate Auto Tags]
 WARM --> TAG
 COLD --> TAG
 TAG --> MATCH[Agent Matching]
 AA --> MATCH
 MATCH --> ROUTE[Lead Routing] --> TASK[Create CRM Tasks]
 TASK --> BUILD[Build CRM Update Action] --> AE[Automation Engine]
 AE --> EE[Execution Engine] --> CRM[CRM Executor] --> OK{Execution Success?}
 OK -->|Yes| EVT[Publish lead.crm_synced / lead.assigned]
 OK -->|No| RETRY[Retry] --> LIMIT{Retry Limit?}
 LIMIT -->|Retry| CRM
 LIMIT -->|Limit Reached| DLQ[DLQ]
 EVT --> EB[Event Bus]
 EB --> SALES[Sales AI]
 EB --> KG[Knowledge Graph]
 EB --> DASH[Dashboard]
```

### Simple Arrow View

``` text
Lead Created / Qualified / Scored
                 ↓
             Event Bus
                 ↓
          CRM Automation
                 ↓
          Fetch Lead Context
                 ↓
        Lead Classification
                 ↓
          Hot / Warm / Cold
                 ↓
          Generate Auto Tags
                 ↓
            Agent Matching
                 ↓
             Lead Routing
                 ↓
          CRM Task Creation
                 ↓
        Build CRM Update Action
                 ↓
          Automation Engine
                 ↓
          Execution Engine
                 ↓
            CRM Executor
                 ↓
          Execution Successful?
             ↙           ↘
           YES            NO
            ↓              ↓
 lead.crm_synced         Retry
 lead.assigned             ↓
            ↓          Limit Reached
        Event Bus            ↓
            ↓               DLQ
 Sales AI + Graph + Dashboard
```

## 6. Competitor Monitoring Workflow

A scheduled market-intelligence workflow that tracks competitor pricing,
projects, offers, inventory, news, and infrastructure changes and
generates prioritized alerts.

### Mermaid Diagram

``` mermaid
flowchart TD
 P1[APScheduler / Cron Trigger] --> P2[Competitor Monitoring Workflow] --> P3[Fetch Market Data]
 P3 --> PRICE[Competitor Pricing]
 P3 --> PROJ[New Projects]
 P3 --> OFFER[Offers / Discounts]
 P3 --> INV[Inventory Changes]
 P3 --> NEWS[Market News]
 P3 --> INFRA[Infrastructure Updates]
 PRICE --> N[Normalize Market Data]
 PROJ --> N
 OFFER --> N
 INV --> N
 NEWS --> N
 INFRA --> N
 N --> COMP[Compare With Previous Snapshot] --> CHANGE{Significant Change?}
 CHANGE -->|No| STORE[Store Snapshot]
 CHANGE -->|Pricing| PC[Pricing Change]
 CHANGE -->|Project| NP[New Competitor Project]
 CHANGE -->|Offer| NO[New Offer]
 CHANGE -->|Inventory| IS[Inventory Shift]
 CHANGE -->|News| IN[Important News]
 CHANGE -->|Infrastructure| II[Infrastructure Impact]
 PC --> MI[Generate Market Intelligence]
 NP --> MI
 NO --> MI
 IS --> MI
 IN --> MI
 II --> MI
 MI --> DEC[Competitor Decision / Alert] --> PRI{Alert Priority?}
 PRI -->|Critical| CR[Critical Alert]
 PRI -->|High| HP[High Priority]
 PRI -->|Low| INFO[Informational]
 CR --> AE[Automation Engine]
 HP --> AE
 INFO --> AE
 AE --> EE[Execution Engine]
 EE --> NOT[Notification Executor]
 EE --> DASHX[Dashboard Executor]
 NOT --> EVT[Publish market.alert.generated]
 DASHX --> EVT
 EVT --> EB[Event Bus]
 EB --> MA[Marketing AI]
 EB --> SA[Sales AI]
 EB --> KG[Knowledge Graph]
 EB --> MEM[Company Memory]
 EB --> DASH[Executive Dashboard]
```

### Simple Arrow View

``` text
APScheduler / Cron
        ↓
Competitor Monitoring
        ↓
Fetch Market Data
        ↓
Pricing / Projects / Offers / Inventory / News / Infrastructure
        ↓
Normalize Market Data
        ↓
Compare Previous Snapshot
        ↓
Significant Change?
    ↙              ↘
   NO              YES
   ↓                ↓
Store Snapshot   Detect Change Type
                     ↓
          Generate Market Intelligence
                     ↓
             Alert Priority Analysis
                     ↓
       Critical / High / Informational
                     ↓
             Automation Engine
                     ↓
             Execution Engine
                     ↓
          Notification + Dashboard
                     ↓
          market.alert.generated
                     ↓
                 Event Bus
                     ↓
 Marketing AI + Sales AI + Graph + Memory
```

## 7. Automation Engine Workflow

Receives agent decisions and workflow triggers, validates actions,
selects LangGraph, n8n, or deterministic execution, manages human
approval, and routes actions through retry, fallback, DLQ, and replay
handling.

### Mermaid Diagram

``` mermaid
flowchart TD
 A1[Agent Decision / Workflow Trigger] --> A2[Automation Engine]
 A2 --> A3[Validate Action Request] --> A4[Load Workflow Template]
 A4 --> T{Workflow Type?}
 T -->|Stateful AI| LG[LangGraph Workflow]
 T -->|Integration Workflow| N8N[n8n Workflow]
 T -->|Deterministic| LIN[Linear Automation]
 LG --> PLAN[Build Execution Plan]
 N8N --> PLAN
 LIN --> PLAN
 PLAN --> AP{Requires Approval?}
 AP -->|Yes| PAUSE[Pause Workflow] --> NOT[Notify Manager] --> MD{Manager Decision}
 MD -->|Reject| REJ[Rejected] --> EB[Event Bus]
 MD -->|Approve| APP[Approved] --> EE[Execution Engine]
 AP -->|No| EE
 EE --> RES[Resolve Executor] --> EXEC[Execute Action] --> OK{Success?}
 OK -->|Yes| SUCCESS[Publish Success Event] --> EB
 OK -->|No| RETRY[Retry With Backoff] --> LIMIT{Retry Limit Reached?}
 LIMIT -->|No| AGAIN[Retry Action] --> EXEC
 LIMIT -->|Yes| FALL[Execute Fallback] --> FOK{Fallback Success?}
 FOK -->|Yes| FS[Publish Fallback Success] --> EB
 FOK -->|No| DLQ[Write DLQ Event] --> REPLAY[DLQ Replay] --> EXEC
 EB --> MEM[Company Memory]
 EB --> KG[Knowledge Graph]
 EB --> DASH[Dashboard]
 EB --> NEXT[Next Agent]
```

### Simple Arrow View

``` text
Agent Decision / Trigger
          ↓
    Automation Engine
          ↓
   Validate Action Request
          ↓
    Load Workflow Template
          ↓
 LangGraph / n8n / Linear Workflow
          ↓
    Build Execution Plan
          ↓
   Requires Approval?
      ↙          ↘
    YES           NO
     ↓             ↓
Pause + Notify     │
     ↓             │
Approve / Reject   │
     └─────────────→ Execution Engine
                          ↓
                   Resolve Executor
                          ↓
                     Execute Action
                          ↓
                       Success?
                     ↙         ↘
                   YES          NO
                    ↓            ↓
             Success Event     Retry
                                  ↓
                          Retry Limit?
                           ↙        ↘
                          NO        YES
                          ↓          ↓
                       Retry      Fallback
                                      ↓
                              Fallback Success?
                                 ↙        ↘
                               YES         NO
                                ↓           ↓
                          Result Event     DLQ
                                              ↓
                                         DLQ Replay
                                              ↓
                                           Retry
                          ↓
                       Event Bus
                          ↓
 Memory + Knowledge Graph + Dashboard + Next Agent
```

## 8. Complete IREIOS AI Automation Arrow Flow

``` text
                        EXTERNAL SOURCES
                              ↓
                         API GATEWAY
                              ↓
                           EVENT BUS
                              ↓
                     CEO AI ORCHESTRATOR
                              ↓
     ┌────────────────────────┼────────────────────────────┐
     ↓                        ↓                            ↓
WHATSAPP AI             MARKETING AI               COMPETITOR MONITOR
     ↓                        ↓                            ↓
Lead Qualification      Campaign Analysis           Market Monitoring
FAQ / Documents         Audience Analysis           Price / Offer Changes
Site Visit              Recommendations             Market Alerts
     ↓                        ↓                            ↓
     └──────────────→ EVENT BUS ←─────────────────────────┘
                              ↓
                       CRM AUTOMATION
                              ↓
                  Tag + Score + Route Lead
                              ↓
                         EVENT BUS
                              ↓
                     PREDICTIVE ENGINE
                              ↓
                         lead.scored
                              ↓
                           SALES AI
                              ↓
              Objection + Priority + Next Best Action
                              ↓
                         EVENT BUS
                              ↓
                      AUTOMATION ENGINE
                              ↓
             LangGraph / n8n / Workflow Templates
                              ↓
                    HUMAN APPROVAL CHECK
                              ↓
                       EXECUTION ENGINE
                              ↓
         ┌────────────────────┼───────────────────────┐
         ↓                    ↓                       ↓
 WhatsApp Executor       CRM Executor          Calendar / Notification
         └────────────────────┼───────────────────────┘
                              ↓
                       ACTION RESULT EVENT
                              ↓
                           EVENT BUS
                              ↓
       ┌──────────────────────┼──────────────────────────┐
       ↓                      ↓                          ↓
KNOWLEDGE GRAPH        COMPANY MEMORY             EXECUTIVE DASHBOARD
       ↓                      ↓                          ↓
       └──────────────────────┴──────────────────────────┘
                              ↓
                    CUSTOMER LIFECYCLE EVENTS
                              ↓
                    CUSTOMER SUCCESS AI
                              ↓
 Payment / Document / Referral / Review / Renewal Automation
                              ↓
                      AUTOMATION ENGINE
                              ↓
                      EXECUTION ENGINE
                              ↓
                           EVENT BUS
```
