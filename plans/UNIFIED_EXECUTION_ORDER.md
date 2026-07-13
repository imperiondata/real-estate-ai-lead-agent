# Unified Execution Order

**Single source of truth for implementation order** across:

| Plan | Path |
|---|---|
| Bug fixes | `plans/BUG_AUDIT_AND_PHASED_FIX_PLAN.md` |
| IREIOS 3.0 expansion | `plans/IREIOS_3.0_STEP_BY_STEP_EXPANSION.md` |

| This doc owns | Does not own |
|---|---|
| Which work unit runs next; exit gates between units | Bug root causes, fix steps, tests → bug plan |
| Hard serial order only | Expansion task steps, file lists → expansion plan |
| Status tracking for the overall program | Architecture / agent workflows → other 3.0 docs |

**Status legend:** `[ ]` pending · `[~]` in progress · `[x]` done · `[-]` skipped (must note why)

---

## 1. Hard rules

1. **Serial only.** Complete one step fully before starting the next. No parallel tracks between the two source plans. No interleaving of bug phases with expansion phases.
2. **One step at a time.** Do not start step *N+1* until step *N* exit gate is green.
3. **Source detail lives in source plans.** This doc only orders work. Open the linked phase/task for how to implement.
4. **Do not skip** a step unless marked `[-]` with a written reason in the master table.
5. **Do not decommission** monolith modules until Expansion Phase 10 says so.
6. **Regression after each major step:** at minimum `python gate_isolation_test.py` when data/tenant code changed; full checklists at block gates.

### Not allowed

- Starting any Expansion Phase (1–10) before **Block 1 (all bug phases) exit gate**
- Starting Bug Phase *N+1* before Bug Phase *N* checklist
- Starting Expansion Phase *N+1* before Expansion Phase *N* exit gate
- “Infrastructure first while bugs continue” or any dual-track schedule
- Reordering steps to “save time” without updating this document first

---

## 2. Why this order

| Decision | Reason |
|---|---|
| **All bug phases before any expansion** | Expansion Phase 4–6 ports `follow_up.py`, `agent.py`, assignment, CRM, notifications. Fixing first avoids copying broken behavior into new modules. |
| **Bug 0 → 1 → 2 → 3 → 4 → 5 → 6** | Matches bug plan criticality (safety → assignment → FSM → concurrency → polish → CRM → structural). |
| **Expansion 0 → 1 → 1b → 2…10** | Bus (Redis Streams) first; **API/SSE stubs next (1b)** so FE is unblocked; then AE, agents, graph, FE cutover (9). |
| **No interleaving bugs with expansion** | Explicit program rule: finish Block 1 before Block 2. Within expansion, order is serial. |

---

## 3. Master sequence (execute top to bottom)

| Step | Source | Unit | Summary | Exit gate | Status |
|---:|---|---|---|---|---|
| **1** | Bug | Phase 0 (P0.1–P0.6) | Safety hotfixes | Bug Phase 0 verification checklist | `[x]` |
| **2** | Bug | Phase 1 (P1.1–P1.13) | Agent assignment | Bug Phase 1 verification checklist | `[x]` |
| **3** | Bug | Phase 2 (P2.1–P2.6) | Chat/follow-up FSM, language, data quality | Bug Phase 2 verification checklist | `[x]` |
| **4** | Bug | Phase 3 (P3.1–P3.5) | WhatsApp/webhook concurrency | Bug Phase 3 verification checklist | `[x]` |
| **5** | Bug | Phase 4 (P4.1–P4.3) | Notification / escalation polish | Items done; no infinite failed alerts; escalation roles as specified | `[x]` |
| **6** | Bug | Phase 5 (P5.1–P5.3) | CRM sync completeness | CRM reflects post-qualification fields; no false success on empty identity | `[x]` |
| **7** | Bug | Phase 6 (P6.1–P6.6) | Structural backlog | Structural items done or explicitly deferred in this table as `[-]` | `[x]` |
| **G1** | Gate | **Block 1 complete** | Monolith stable | **Bug master regression checklist** (§13 of bug plan) all green | `[ ]` |
| **8** | Expansion | Phase 0 Task 0.2 | Branch / env hygiene + Redis available | App boots; Redis reachable | `[ ]` |
| **9** | Expansion | Phase 1 (Tasks 1.1–1.8) | **Redis Streams** bus, CEO, BaseAgent, EE skeleton | Expansion Phase 1 exit gate (durable publish) | `[ ]` |
| **10** | Expansion | Phase 1b (Tasks 1b.1–1b.4) | **Early SSE + API envelopes** (stub producers OK) | Expansion Phase 1b exit gate — **FE unblocked** | `[ ]` |
| **11** | Expansion | Phase 2 (Tasks 2.1–2.7) | Automation Engine, HITL, LangGraph/n8n hooks | Expansion Phase 2 exit gate | `[ ]` |
| **12** | Expansion | Phase 3 (Tasks 3.1–3.4) | WhatsApp & CRM executors | Expansion Phase 3 exit gate | `[ ]` |
| **13** | Expansion | Phase 4 (Tasks 4.1–4.5) | Follow-up scheduler via AE→EE | Expansion Phase 4 exit gate | `[ ]` |
| **14** | Expansion | Phase 5 (Tasks 5.1–5.9) | WhatsApp Agent, brochure/floorplan, scoring | Expansion Phase 5 exit gate (`task3_runner`, isolation) | `[ ]` |
| **15** | Expansion | Phase 6 (Tasks 6.1–6.4) | CRM automation + Sales AI | Expansion Phase 6 exit gate | `[ ]` |
| **16** | Expansion | Phase 7 (Tasks 7.1–7.7) | Neo4j KG + Memory | Expansion Phase 7 exit gate | `[ ]` |
| **17** | Expansion | Phase 8 (Tasks 8.1–8.5) | Prediction APIs + Marketing/CS/Competitor | Expansion Phase 8 exit gate | `[ ]` |
| **18** | Expansion | Phase 9 (Tasks 9.1–9.8) | FE cutover to live SSE/APIs (contracts from 1b) | Expansion Phase 9 exit gate | `[ ]` |
| **19** | Expansion | Phase 10 (Tasks 10.1–10.5) | Placeholders, decommission, evidence | Expansion Phase 10 final gate | `[ ]` |
| **G2** | Gate | **Program complete** | MVP close | Expansion plan **Program final gate (G2)** checklist + Task 10.4–10.5 | `[ ]` |

**Expansion Task 0.1** (doc freeze) is already done; do not re-open it as a blocking step.

---

## 4. Block 1 — Bug audit (monolith stabilization)

Implement using `plans/BUG_AUDIT_AND_PHASED_FIX_PLAN.md` only. Within each phase, follow item IDs in numeric order (e.g. P0.1 before P0.2).

**Shipped fixes narrative:** update `plans/BUG_FIXES_CHANGELOG.md` after every slice (with tests).

### Step 1 — Bug Phase 0 (Safety)

| ID | Focus |
|---|---|
| P0.1 | `"bye"` must not close on “buyer” |
| P0.2–P0.3 | Never WhatsApp hot alert to lead phone; null phone safe |
| P0.4–P0.5 | Terminal session + durable opt-out |
| P0.6 | Failed notifications terminal status |

**Exit:** Bug plan “Phase 0 verification checklist.”

### Step 2 — Bug Phase 1 (Assignment)

| ID | Focus |
|---|---|
| P1.1–P1.5 | `ensure_lead_assignment`, sticky claim, workload, match→commit→notify, handoff assigns |
| P1.6–P1.10 | Speciality map, location match, live counts, fake follow-up name, notify reason |
| P1.11–P1.13 | Claim binds assignee; FE shows assignee; remove mock Jane Doe filter |

**Exit:** Bug plan “Phase 1 verification checklist.”

### Step 3 — Bug Phase 2 (FSM / language / quality)

| ID | Focus |
|---|---|
| P2.1–P2.3 | `finalize_turn`, terminal state policy, name interceptor guard |
| P2.4–P2.5 | Funnel enum alignment; session vs conversion status clarity |
| P2.6 | Strict English default; Hinglish only when user initiates |

**Exit:** Bug plan “Phase 2 verification checklist.”

### Step 4 — Bug Phase 3 (Concurrency)

| ID | Focus |
|---|---|
| P3.1–P3.3 | Timeout path: no double process; lock ownership; idempotency |
| P3.4 | MessageSid insert-first / IntegrityError |
| P3.5 | SMS follow-up stop uses tenant-scoped session id |

**Exit:** Bug plan “Phase 3 verification checklist.”

### Step 5 — Bug Phase 4 (Notification polish)

**Slice A (own PR):** P4.1 — 10m manager vs 30m director (model + migration + seed + backend cron + team UI). **Status: done.**

**Slice B (own PR):** P4.2 + P4.3 — handoff-upgrade severity ranking + follow-up send-failure backoff (backend-only, one new test file). **Status: done.**

| ID | Focus | Slice |
|---|---|---|
| P4.1 | 10m manager vs 30m director | A (done) |
| P4.2 | Handoff upgrades over score alert | B (done) |
| P4.3 | Follow-up send failure backoff | B (done) |

**Exit:** All P4 items implemented and verified per bug plan.

### Step 6 — Bug Phase 5 (CRM quality)

**Status: done.** P5.1 (debounced re-sync via `crm_resync_pending` + `crm_resync_job` scheduler, 5-min), P5.2 (extended property map gated by `CRM_SYNC_EXTENDED_PROPERTIES` + 4xx property-drop retry), P5.3 (`decide_crm_status_after_poll` leaves `pending` when identity still empty). Tests in `tests/test_p5_crm.py`.

| ID | Focus |
| --- | --- |
| P5.1 | Re-sync after meaningful field changes |
| P5.2 | Expand CRM property map |
| P5.3 | No success with empty identity |

**Exit:** All P5 items implemented and verified per bug plan.

### Step 7 — Bug Phase 6 (Structural)

**Status: done** (P6.2 deferred). P6.1 (persisted agent learning), P6.3 (min match score), P6.4 (AB/day-gap derivation), P6.5 (temperature casing), P6.6 (atomic workload already single-transaction). Tests in `tests/test_p6_structure.py`.

| ID | Focus | Status |
| --- | --- | --- |
| P6.1 | Persist feedback-loop success rates | done (AgentLearning table) |
| P6.2 | `Lead.assigned_agent` → FK to `agents.id` | `[-]` deferred (high-risk blast radius; see note) |
| P6.3 | Min match score threshold | done (`MIN_MATCH_SCORE`) |
| P6.4 | AB follow-up stage timing vs strategy B day units | done (`next_followup_stage`) |
| P6.5 | Temperature badge casing | done (`serialize_lead`) |
| P6.6 | Atomic workload updates | done (already single-transaction) |

**P6.2 deferral reason:** converting `assigned_agent` (string) to a real FK to `agents.id` requires a data backfill + query rewrites across `main.py`, `agent.py`, `agent_matcher.py`, `notification_service.py`, `follow_up.py`, `dlq_replay.py` (all join/compare on the agent *name*). Benefit is rename-safety only; risk is broad regression mid-program. Deferred to the Expansion Phase 10 decommission window where module boundaries are redrawn anyway.

**Exit:** All P6 items done, or each skipped item listed as `[-]` with reason in this doc’s master table / notes.

### Gate G1 — Block 1 complete

Before **any** expansion work:

1. Run bug plan **§13 Master regression checklist** (Safety, Assignment, FSM/language, Concurrency, CRM/notif).  
2. Run: `python gate_isolation_test.py`  
3. Run: `python gate_dlq_drill.py` (and recovery path as applicable)  
4. Run: `python task3_runner.py` when API/env allow  

**Only when G1 is `[x]` may Step 8 begin.**

---

## 5. Block 2 — IREIOS 3.0 expansion

Implement using `plans/IREIOS_3.0_STEP_BY_STEP_EXPANSION.md` only. Within each phase, follow task numbers in order (e.g. 1.1 before 1.2).

Supporting architecture (read-only reference, not alternate queues) — all under `plans/`:

- `IREIOS_3.0_Architecture_Diagrams.md`
- `IREIOS_3.0_AI_Automation_Workflows.md`
- `IREIOS_3.0_IMPLEMENTATION_PLAN.md`

### Step 8 — Expansion Phase 0

- Task **0.2** only: branch/env hygiene, app boots.  
- Task 0.1 already complete.

### Step 9 — Expansion Phase 1

- Tasks **1.1 → 1.8**: packages, **Redis Streams** Event Bus, registry, CEO, EE skeleton, lifespan, exit gate.  
- **Not allowed:** in-process `asyncio.Queue` as the production bus.

### Step 10 — Expansion Phase 1b (FE unblock)

- Tasks **1b.1 → 1b.4**: authenticated SSE, timeline/KPI envelopes, stub publisher.  
- **Purpose:** Mayank can replace frontend mocks immediately with stable contracts; dummy/`source: stub` payloads OK.  
- **Does not wait** for Phase 9.

### Step 11 — Expansion Phase 2

- Tasks **2.1 → 2.7**: Approval model, HITL, AutomationEngine, LangGraph/n8n scaffolds, approve APIs, exit gate.

### Step 12 — Expansion Phase 3

- Tasks **3.1 → 3.4**: WhatsAppExecutor, CRMExecutor, calendar/notification stubs, exit gate.

### Step 13 — Expansion Phase 4

- Tasks **4.1 → 4.5**: Follow-up port via AE→EE, shadow/legacy switch, arm state, cutover, exit gate.  
- **Ports bug-fixed** `follow_up.py` behavior.

### Step 14 — Expansion Phase 5

- Tasks **5.1 → 5.9**: Feature flag, WhatsAppAgent, brochure/floorplan, scoring handler, v3 cutover gates.  
- **Ports bug-fixed** `agent.py` / language / FSM behavior.

### Step 15 — Expansion Phase 6

- Tasks **6.1 → 6.4**: CRM automation + Sales AI (uses fixed assignment patterns).

### Step 16 — Expansion Phase 7

- Tasks **7.1 → 7.7**: Neo4j, Graph APIs, event writers, GraphClient, Memory.

### Step 17 — Expansion Phase 8

- Tasks **8.1 → 8.5**: Prediction APIs, Marketing, CS, Competitor monitor.

### Step 18 — Expansion Phase 9

- Tasks **9.1 → 9.8**: FE cutover to **live** producers on Phase 1b contracts (Mayank UI).  
- **Not** first creation of SSE/API routes.

### Step 19 — Expansion Phase 10

- Tasks **10.1 → 10.5**: Placeholders, decommission dual paths, evidence pack, final gate.

### Gate G2 — Program complete

Complete the checklist **Program final gate (G2)** in `IREIOS_3.0_STEP_BY_STEP_EXPANSION.md` (architecture/cutover, graph/memory, APIs/SSE, quality commands, evidence pack).  

That section is the expansion equivalent of bug-audit §13. Do not mark G2 done until every G2 checkbox is green.

---

## 6. Day-to-day workflow

1. Open **this file**.  
2. Find the first step with status `[ ]`.  
3. Open the **source plan** section for that phase.  
4. Implement **one** bug ID or expansion task at a time (as ordered inside that phase).  
5. Run that item’s tests / checklist.  
6. When the **phase exit gate** passes, set that step to `[x]` in the master table.  
7. Only then move to the next step number.  
8. At G1 / G2, run the full gate commands before proceeding or closing.

### Suggested status update habit

After finishing a step, edit the master table Status column in this file in the same PR/commit as the code when practical.

---

## 7. Intra-phase ordering (no ambiguity)

| Block | Rule |
|---|---|
| Bug Phase *X* | Complete all `PX.y` in ascending *y* as listed in the bug plan. |
| Expansion Phase *X* | Complete all Tasks `X.y` in ascending *y* as listed in the expansion plan (including **1b**). |
| Suggested PR slices in bug plan | Still serial; use them as commit boundaries, not parallel workstreams. |
| FE work after Phase 1b | Mayank may wire FE to stub SSE/APIs as soon as Step 10 exits; that is intended. Backend continues Steps 11–19 serially. |

---

## 8. Rollback / emergency

If production breaks mid-program:

1. Fix the incident on the **current path** (legacy monolith until Expansion Phase 5+ cutover).  
2. Do **not** jump ahead in this order to “build around” the bug.  
3. If a hotfix is outside the current step, log it, ship the hotfix, then return to the **same** step—do not skip forward.  
4. Expansion rollbacks (when in Block 2): use expansion plan rollback cheat sheet (`FEATURE_WHATSAPP_V3`, `FOLLOWUP_ENGINE=legacy`, etc.).

---

## 9. Pointers for other docs

- Bug plan and expansion plan remain detailed sources of **how**.  
- This plan is the only source of **when / what comes next**.  
- If this order must change, update **this file first**, then continue.

---

## 10. Immediate next action

**Step 1 — Bug Phase 0**, starting with **P0.1** in `plans/BUG_AUDIT_AND_PHASED_FIX_PLAN.md`.

Do not open Expansion Task 1.1 until Gate **G1** is complete.
