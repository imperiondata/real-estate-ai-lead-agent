# Product Phase 4 — Team Lead Questionnaire

**To:** Technical Lead / Sprint author of `IREIOS_Phase_4_Master_Sprint_Plan.md`  
**From:** Engineering (baseline audit against live repo)  
**Date:** 2026-08-07  
**Why:** Sprint DoD and status lines conflict with code already shipped in IREIOS 3.0. Answers below unlock implementation in `plans/phase4/`.

**How to answer:** For each question, pick an option or write a specific value.  
Where engineering has a **Recommended** default, accept with `ACK recommended` or override with an explicit alternative.

**Return format (copy block per Q):**

```text
Q#: ACK recommended | OVERRIDE: <specific decision>
Notes: …
Owner: …  Due: …
```

---

## §F — False / overstated claims in the sprint plan (please confirm or correct)

Engineering audited the repo against `IREIOS_Phase_4_Master_Sprint_Plan.md`.  
**Please reply True / False / Amend** on each row. If Amend, write the corrected sentence.

| ID | Sprint claim (paraphrase) | Engineering finding | Impact if uncorrected | Lead: T/F/Amend |
|---|---|---|---|---|
| **F1** | “Current Progress: **0%** (Sprint Day 1)” | Backend already has Neo4j v1 + graph APIs, Sales AI NBA + HTTP, heuristic predictions, CRM outbound+DLQ, marketing/CS agents, bus/SSE, n8n bridge. FE has mock shells. **0% is false.** | Week 1 rebuild waste; wrong exec reporting | |
| **F2** | “Execution is entirely unblocked — foundational Phase 3 infrastructure is 100% live” | Largely true for spine; **G4** n8n WF-1 may still be ops-pending; HubSpot portal still skipped; FE cutover incomplete | Overstates “100%” ops readiness | |
| **F3** | “Overall Project Completion: **70%**” | Directionally plausible; needs shared definition (BE/FE/ops weighted?) | Status theater | |
| **F4** | Week 1: “Neo4j … schemas and ingestion APIs completed” as if greenfield | **Already done** in 3.0 Phase 7 + BD-5. Missing is **viz neighborhood** payload for FE force-graph, not base schema | Fake Week 1 load on Aritro | |
| **F5** | Week 1: “Forecast Engine — **models trained** and serving endpoints finalized” | Endpoints exist; code states **heuristic MVP, not ML accuracy**. **No training pipeline / model artifacts** | Compliance risk if sold as trained ML | |
| **F6** | Week 1: “Marketing AI routing workflows finalized on the automation plane” | Marketing agent + segments + WF-5 report fan-out exist. **Assignment/escalation is Python**, not n8n router | Wrong owner/plane for “routing” | |
| **F7** | Week 2: “HubSpot CRM backend integration complete and **fully exposed**” / “**Bi-directional** webhook/API sync” | Outbound push+retry+DLQ **code** ready; **live portal skipped**; **no inbound HubSpot webhook** in codebase | Week 2 impossible without portal + greenfield inbound | |
| **F8** | Week 2: “Sales AI logic (NBA) deployed” as Maitri Week 2 | **Already deployed** in Python (`sales_agent.py`, bus, `POST .../sales-ai`). FE button missing | Maitri overloaded; Mayank under-scoped | |
| **F9** | Sales AI DoD: “**LangGraph** reasoning agents deployed to the **n8n** orchestrator” | NBA is **deterministic Python**, not LangGraph-in-n8n. n8n hard rules: **must not own FSM/assignment** (`docs/N8N_INTEGRATION.md`) | Architecture regression if forced | |
| **F10** | Marketing DoD: “Automated routing … **mapped in n8n**. Inbound leads assigned and escalated based on predictive scores” | Assignment = `ensure_lead_assignment` + CRM/Sales automation in **Python**. n8n = Gmail/Sheets/ops | Conflicts with shipped design | |
| **F11** | Dependency: Graph UI **blocked by** Neo4j APIs End of Week 1 | Context/health APIs **already exist**. Blocker is **nodes/edges contract + FE wire**, not “no Neo4j” | False critical path | |
| **F12** | Dependency: Forecast widgets **blocked by** Prediction APIs Week 1 | `/api/v1/predictions/*` **already live** | False critical path | |
| **F13** | Dependency: Sales AI Logic **blocked by** Prediction APIs | Sales AI already runs scoring internally; HTTP API live | False critical path | |
| **F14** | Dependency: HubSpot Automation **blocked by** HubSpot CRM Integration APIs Week 2 | Python CRM path exists; **portal credentials + bi-di** are real blockers, not “no API code” | Partial truth — clarify | |
| **F15** | Dependency: Sales AI Button blocked by “payload structure lock” Week 2 | Payload already returnable from live API; needs **contract freeze doc + FE**, not new Maitri agent | Mis-ordered dependency | |
| **F16** | Risk: “cascading backend bottlenecks centered on **Aritro**” for all Week 1 | Much of Aritro Week 1 is **done**. Real BE gaps: neighborhood API, twin layout API, HubSpot go-live/bi-di | Wrong risk focus; FE + HubSpot org blockers dominate | |
| **F17** | Mitigation: “Contract-First Day 1 mocks” | Still valid for **new** neighborhood/twin shapes; **not** needed to reinvent sales-ai/predictions | Keep mitigation; narrow scope | |
| **F18** | QA checklist: “Neo4j queries under **200ms**” | Not instrumented as a gate today; context path is soft-timeout 0.5s on reply path | Need explicit measure job or relax | |
| **F19** | Forecast DoD: “**200ms latency SLA**” + “ML scoring algorithms deployed” | Heuristics are fast enough typically; “ML deployed” is overstated | Redefine DoD | |
| **F20** | Mayank Graph DoD: “parses **Aritro's Week 1 API payload**” + “real-time node updates” | FE mock expects Project/Tower/Unit/Comm graph; backend returns **similar_leads + agent**, not that shape. **No graph SSE push** | Need new API or reduce DoD | |
| **F21** | Digital Twin: “mocked/stubbed **or** event bus” | FE mock only; **no twin bus API**; inventory counts only | Specify live layout vs mock-OK | |
| **F22** | “Deviation from these milestones is **strictly prohibited**” vs 4-week compress of 5-week work | Several milestones already met early; blind adherence causes **rebuild** | Allow re-baseline | |
| **F23** | Naming: “Phase 4” | Repo already used Phase 4 for **Bug P4** and **Expansion follow-up Phase 4** | Call this **Product Phase 4 / IREIOS 4.0** in comms | |

### F-follow-ups (required)

1. May engineering **edit the sprint doc §6** to replace 0% with a corrected split (e.g. Backend foundation ~75%, FE integration ~15%, HubSpot/ops ~10%)? **Yes/No**  
2. May engineering **rewrite DoD rows** F9/F10/F5/F7 to match CEO→AE→EE architecture? **Yes/No**  
3. Which dependency rows (F11–F15) stay as executive fiction vs get corrected publicly?

---

## Q0 — Program intent

**Context:** IREIOS 3.0 delivered the event spine and most named “Week 1–2 backend” items.  

**Recommended:** Phase 4 = **integrate + FE cutover + QA + release**. Credit backend. Do **not** rebuild Sales AI / KG / predictions from scratch. Isolate HubSpot org blockers.

1. Phase 4 is **(A)** finish/integrate what exists, **(B)** greenfield per literal sprint text, **(C)** other: ________  
2. Official release date still **2026-09-03**? Env names (staging URL, prod URL): ________  
3. Hard-freeze start date (Week 3): ________  
4. Technical Lead approver for prod runbook (name): ________  
5. Weekly status owner: ________  

---

## Q1 — Forecast / ML / 200ms

**Context:** Live routes in `app/api/predictions.py` are documented as **heuristic MVP**.  

**Recommended:** Ship FE on heuristics; UI/docs say “estimate”; optional p95 latency smoke; **no** training pipeline in 4-week MVP.

1. Accept heuristic forecasts for MVP? **Yes/No**. If No, specify models, data source, metrics, artifact store, retrain cadence.  
2. 200ms is **(a)** hard SLA all prediction GETs, **(b)** per-lead only, **(c)** aspirational, **(d)** drop from DoD.  
3. Currency/units for revenue widgets: ________  
4. FE label text approved: e.g. “Heuristic estimate (not a trained model)” **Yes/No/Alternate:** ________  
5. Any admin-global forecast (cross-tenant)? **Yes/No** (default No — security).  

---

## Q2 — HubSpot

**Context:** Outbound+DLQ ready; portal often blocked on **company email**; no inbound webhook; WF-4 is Sheets not HubSpot.  

**Recommended long-term sustainable:** **(A)** outbound + real portal when ready; bi-di as 4.1 if blocked; keep Python EE path; don’t make n8n sole CRM brain.

1. Scope: **(A)** outbound+portal **(B)** true bi-di **(C)** n8n HubSpot only **(D)** defer `[-]`.  
2. If A/B: sandbox or prod portal? Admin owner? API key due date?  
3. If email blocks portal: blocker owner + fallback (Sheets until when)?  
4. Field map confirm (add/remove): firstname, phone, budget, location, intent, property_type, visit_date, assignee, budget_alignment_status, urgency_level, engagement_score, lead_temperature.  
5. If B: which HubSpot edits flow back? Conflict rule: IREIOS wins / HubSpot wins / last-write-wins?  
6. Idempotency key: hubspot vid / email / phone / custom `ireios_lead_id`?  
7. Keep DLQ `hubspot_crm` + `dlq_replay.py`? **Yes/No**  
8. Is “bi-directional” in the sprint **mandatory for Sept 3** or best-effort?  

---

## Q3 — Sales AI / NBA

**Context:** Python NBA + `POST /api/v1/leads/{id}/sales-ai` live. FE button missing. Sprint asks LangGraph-in-n8n.  

**Recommended:** Keep Python SoT; Mayank wires button; n8n may fan-out notifications only.

1. Python remains NBA source of truth? **Yes/No** (if No, explain dual-path prevention).  
2. Button placement: **(A)** CRM Kanban **(B)** Leads table **(C)** sales-copilot **(D)** all — priority order: ________  
3. Click runs full pipeline incl. CRM sync (`sync_crm=true` today)? **Yes/No**  
4. UI must show: action, rationale, scores, funnel_stage, assigned_agent — add/remove: ________  
5. Freeze action enum: `request_info|schedule_site_visit|escalate_hot|send_brochure|assign_agent|nurture_followup`? **Yes/No + deltas**  
6. Execute side effects immediately vs preview+confirm?  
7. Manual button rate limit (bus path = 10 min Redis): ________  
8. LLM “Generate Email Draft” in scope? **Yes/No** + template rules.  

---

## Q4 — Marketing “routing in n8n”

**Context:** Python assigns/escalates; n8n reports/Gmail.  

**Recommended:** ACK Python routing; n8n ops only.

1. Accept Python-owned assignment/escalation? **Yes/No**  
2. New n8n WFs beyond WF-1…6? List `event → action` or **None**.  
3. Unassigned policy when match score &lt; `MIN_MATCH_SCORE`: leave unassigned (current) or force?  
4. Weekly report schedule/recipients changes?  

---

## Q5 — Knowledge Graph viz

**Context:** FE mock = Project→Tower→Unit→Lead→Comm. Backend = Lead/Agent/similarity + context API.  

**Recommended production path:** Neighborhood API ego network (Lead + similar + agent); stretch units; poll/SSE-refetch; JWT only.

1. MVP: **(A)** ego Lead network **(B)** full Project/Tower/Unit/Comm **(C)** mock OK for release.  
2. If B: SoT for towers = Postgres inventory / Neo4j / both?  
3. Approve proposed JSON in `IREIOS_4.0_API_CONTRACTS.md` §1? **Yes/No + diff**  
4. Realtime: **(A)** poll 30s **(B)** SSE refetch **(C)** none MVP.  
5. 200ms graph SLA: hard/soft/drop? Expected max leads/tenant for test: ________  
6. Canonical page: `/knowledge-graph` only or embed on lead detail?  
7. `ai_summary` required from LLM or static string OK?  

---

## Q6 — Digital Twin

**Context:** R3F mock UI; `InventoryUnit` + count API only.  

**Recommended:** Live `GET /api/v1/inventory/twin` + seed + wire R3F.

1. Twin MVP: **Yes live** / mock-only / defer.  
2. Demo layout size: #projects, #towers, #floors, #units: ________  
3. Status enum: `available|hold|sold` (+ add ________)?  
4. Interactions: read-only / open lead / place hold?  
5. `project_id` real FK in DB or single-project MVP?  
6. Live hold refresh SLA seconds: ________  
7. Max units client-side before aggregation: ________  

---

## Q7 — Frontend surface of truth

**Context:** `(dashboard)` product vs `(command-center)` MVP shells.  

**Recommended:** **Both** — Sales AI on CRM/leads; forecast on product + mvp; graph/twin command-center; JWT middleware on command-center.

1. ACK Both? **Yes/No**  
2. JWT-guard command-center routes? **Yes/No**  
3. Post-login home: `/dashboard` or `/dashboard-mvp`?  
4. Approvals UI in Phase 4? **Yes/No**  
5. Hard requirement: zero `secret-client-key-123` in client bundles before RC1? **Yes/No**  
6. Mobile/responsive requirements for graph & twin: ________  
7. Brand/theme changes? **None** / describe.  

---

## Q8 — Contract-first & staging

**Recommended:** Freeze shipped contracts immediately; freeze neighborhood/twin after Q5/Q6; Day-1 mocks for new only.

1. Contract freeze owner + date: ________  
2. Staging: local docker only / hosted URL: ________  
3. RC1 against prod DB? **No** / read-replica / yes-with-approval: ________  
4. Feature flag names approve: `FEATURE_GRAPH_VIZ`, `FEATURE_TWIN_LIVE`, `FEATURE_HUBSPOT_LIVE`? **Yes/No + list**  
5. OpenAPI path `plans/phase4/openapi_ireios4.json` OK? **Yes/No**  

---

## Q9 — QA gates & non-goals

**Recommended G5:** full pytest (or matrix), isolation, DLQ if CRM live, FE lint, Q12 demos.

1. G5 command list add/remove: ________  
2. `task3_runner.py` (126) before RC1? **Yes/No**  
3. Confirm non-goals (strike any you reject):  
   - [ ] LangGraph-in-n8n NBA rewrite  
   - [ ] Full multi-model ML training platform  
   - [ ] HubSpot bi-di unless Q2=B  
   - [ ] Monolith `agent.py` deletion  
   - [ ] Mobile native apps  
   - [ ] Multi-region  
4. Bug tracker for High/Critical bar: ________  
5. Release telemetry: `/metrics` enough? **Yes/No + extras**  

---

## Q10 — Ownership & comms

1. Owners still Aritro BE / Maitri automation / Mayank FE? Changes: ________  
2. Who corrects sprint % weekly?  
3. Standup cadence + channel: ________  
4. Binding “Clears By End Week 1/2” when work already shipped? **Re-baseline** / keep fiction / other.  
5. Product name in external decks: IREIOS 4.0 vs Phase 4?  

---

## Q11 — Secrets & env (fill or N/A)

| Item | Value or N/A | Owner | Due |
|---|---|---|---|
| Staging base URL | | | |
| Prod base URL | | | |
| HubSpot portal + key | | | |
| `NEO4J_*` prod | | | |
| `N8N_*` / bridge | | | |
| `CRM_API_*` | | | |
| `GOOGLE_CALENDAR_*` | | | |
| Brochure/floorplan HTTPS URLs | | | |
| Twilio prod | | | |
| Admin key rotation | | | |
| Go-live flag flips checklist owner | | | |

---

## Q12 — Acceptance demos (Required / Optional / Cut)

| Demo | Engineering default | Lead |
|---|---|---|
| WA → SSE dashboard alert &lt;2s | Required | |
| Sales AI button → NBA render | Required | |
| Forecast widgets from `/predictions/*` | Required | |
| Graph neighborhood hot lead | Required if Q5≠C | |
| Twin seeded units + colors | Required if Q6=Yes live | |
| HubSpot contact upsert | Per Q2 | |
| n8n Gmail on `lead.hot` | Optional ops | |
| Isolation drill green | Required | |
| DLQ replay green | Required if HubSpot live | |

---

## Q13 — Blockers called out in sprint “Risk / Dependency” — validate each

For each, lead marks: **Still a blocker** / **Not a blocker (already shipped)** / **Different blocker:** …

| Sprint blocker narrative | Engineering view | Lead |
|---|---|---|
| Mayank Graph UI blocked on Aritro Neo4j Week 1 | APIs exist; need neighborhood shape | |
| Mayank Forecast blocked on Prediction APIs Week 1 | APIs exist; FE wire only | |
| Maitri Sales AI blocked on Prediction APIs | Sales AI already live | |
| Maitri HubSpot automation blocked on Aritro HubSpot Week 2 | Code path exists; **portal + bi-di policy** are real | |
| Mayank Sales AI button blocked on Maitri payload lock Week 2 | Lock = document existing JSON; Maitri not on critical path for button | |
| Aritro is single point of failure for all Week 1 | Overstated; FE + HubSpot org are equal/larger risks | |
| 4-week compress → stability risk | Valid residual risk for **new** twin/graph/FE/HubSpot, not full stack rewrite | |

---

## Q14 — Definition of Done rewrite permission

May engineering treat the following as **official Phase 4 DoD** unless you override?

| Owner | Rewritten DoD (recommended) | ACK? |
|---|---|---|
| **Mayank** | Sales AI button live on CRM/leads; forecast widgets on live predictions; graph on neighborhood API (or accepted mock); twin on layout API (or accepted mock/defer); JWT SSE; no hard-coded client keys; lint clean | |
| **Aritro** | Neighborhood graph API + twin layout API + latency smoke; HubSpot per Q2; no fake “models trained” claim; OpenAPI updated | |
| **Maitri** | No NBA rewrite; n8n remains ops; only agreed WF deltas; HubSpot automation only if Q2 says so; Python routing remains SoT | |

---

## After you answer

Engineering will:

1. Remove `⚠ BLOCKED ON LEAD` / `[?]` from `UNIFIED` + `STEP_BY_STEP`  
2. Freeze `IREIOS_4.0_API_CONTRACTS.md`  
3. Implement P4-0→G5 in order  
4. Optionally patch root sprint §6 status with your approved numbers  

**Active plans path:** `plans/phase4/`  
**Archived 3.0 plans:** `plans/phase3/`
