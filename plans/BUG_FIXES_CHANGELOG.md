# Bug Fixes Changelog

Living record of bug-fix work on branch **`bugfixes`**.  
Full root-cause analysis remains in `BUG_AUDIT_AND_PHASED_FIX_PLAN.md`.  
Execution order: `UNIFIED_EXECUTION_ORDER.md`.

## How to maintain

After every bug-fix slice:

1. Implement code  
2. Extend `tests/`  
3. **Append / update this file** (same change)  
4. Mark phase IDs in the status table below  

---

## Phase 0 status

| ID | Status | Summary | Tests |
|---|---|---|---|
| P0.1 | **done** | Closing detection: whole-word bye/goodbye, not buyer/maybe | `tests/test_p0_safety.py` |
| P0.2 | **done** | Hot-lead WhatsApp never uses lead phone | same |
| P0.3 | **done** | Missing agent phone fails closed (no crash) | same |
| P0.4 | **done** | Terminal chat state not forced active | same |
| P0.5 | **done** | Opt-out durable (re-arm + scheduler + early reply) | same |
| P0.6 | **done** | Failed notification ops alert only once → `failed_alerted` | same |

**Phase 0 verification checklist**

- [x] `"I am a buyer in Baner"` does not close session  
- [x] `"bye"` / `"goodbye"` still close  
- [x] No agents → hot path does not WhatsApp lead phone  
- [x] Missing agent phone does not crash  
- [x] Fully qualified + later `"hi"` stays closed / no Day 0 re-arm  
- [x] Opt-out + later message → no automated follow-up re-arm / scheduler skip  
- [x] Failed notification produces one ops alert path, then terminal status  

---

## Entries

### P0.1 — `"bye" in msg_clean` closes on “buyer”

**Bug:** Substring `"bye" in msg_clean` treated “buyer”, “maybe”, “byelaw” as goodbye → session closed mid-qualification.

**Fix:** Helpers `clean_user_message`, `has_goodbye_token` (whole-word only), `is_closing_message`. Closing branch uses helpers only.

**Files:** `agent.py`

**Tests:** parametrized closing cases; buyer not goodbye token.

---

### P0.2 — Hot alert can WhatsApp the customer

**Bug:** `agent_phone = target_agent.phone if target_agent else lead.phone` sent internal hot-lead ops text to the prospect when no agent/manager.

**Fix:** `resolve_hot_alert_recipient` requires an Agent with non-empty phone. On failure: critical log, optional admin email, `NotificationLog(status="failed")`, no Twilio. Never uses `lead.phone`.

**Files:** `notification_service.py`

**Tests:** resolve returns None without agent / without phone; OK with agent phone.

---

### P0.3 — `agent_phone` None crash

**Bug:** Missing phone still called `agent_phone.startswith(...)` → AttributeError, often swallowed.

**Fix:** Same fail-closed path as P0.2; `.startswith` only after validated non-empty agent phone.

**Files:** `notification_service.py`

**Tests:** blank/None phone → None recipient.

---

### P0.4 — Closed / qualified sessions reopened

**Bug:** Non-closing messages always did `session.status = "active"`, reopening fully qualified or handoff sessions.

**Fix:** `is_fully_qualified`, `is_terminal_chat_state` (opt-out | fully qualified | Human Handoff). Only set `active` when not terminal. `should_rearm_day0` blocks re-arm when terminal or closed. Polite thanks-only close (not terminal) may reopen.

**Files:** `agent.py`

**Tests:** terminal/qualified/handoff/open-lead cases; re-arm eligibility.

---

### P0.5 — Opt-out not durable

**Bug:** Scheduler never checked `whatsapp_opt_in`; re-arm ignored opt-out; reopen + re-arm could message after “stop”.

**Fix:** Early opt-out reply + stop follow-ups + stay closed. Re-arm never when opted out. `follow_up.py` skips when `whatsapp_opt_in is False`.

**Files:** `agent.py`, `follow_up.py`

**Tests:** terminal when opted out; should not re-arm when opted out.

---

### P0.6 — Failed notifications alert forever

**Bug:** Escalation cron selected `status == "failed"` and called `send_critical_alert` every minute without updating status.

**Fix:** After alert, set status via `terminal_status_after_failed_delivery_alert("failed")` → `"failed_alerted"` (helper in `notification_service`). Document status on `NotificationLog`.

**Files:** `main.py`, `notification_service.py`, `models.py`

**Tests:** `terminal_status_after_failed_delivery_alert` mapping.

---

## Phase 1 status

| ID | Status | Summary | Tests |
|---|---|---|---|
| P1.1 | **done** | `ensure_lead_assignment` extracted | `tests/test_p1_assignment.py` |
| P1.2 | **done** | Sticky after `claimed` (no rematch) | same |
| P1.3 | **done** | Workload +1 only on assignee change; -1 previous | same |
| P1.4 | **done** | Match/commit before hot notify | (wired in agent) |
| P1.5 | **done** | Handoff assigns before notify | (wired in agent) |
| P1.6 | **done** | Speciality alias map (investor↔investment, etc.) | same |
| P1.7 | **done** | Soft location match (exact / substring) | same |
| P1.8 | **done** | Live open-lead COUNT for load penalty | (matcher) |
| P1.9 | **done** | No ABC Properties Team; company/assignee label | same |
| P1.10 | **done** | Hot threshold reason (not “explicit human”) | same |
| P1.11 | **done** | Claim API optional `agent_name` / `agent_id` | (API body) |
| P1.12 | **done** | Assignee on Kanban, leads table, priority card | FE |
| P1.13 | **done** | Removed Jane Doe mock dashboard filter | FE |

**Phase 1 complete.**

---

## Phase 1 entries

### P1.1 — Extract `ensure_lead_assignment`

**Bug:** Assignment only at end of `process_chat`; handoff could not reuse it.

**Fix:** `ensure_lead_assignment` in `app/intelligence/agent_matcher.py`; used from score path and handoff.

**Files:** `agent_matcher.py`, `agent.py`

---

### P1.2 — Sticky after claim

**Bug:** Rematch every turn could overwrite assignee after dashboard claim.

**Fix:** If `conversion_status == "claimed"` and not `force`, return existing `assigned_agent` without matching.

**Files:** `agent_matcher.py`

---

### P1.3 — Workload inflation

**Bug:** Every match did `active_leads += 1` even for the same agent.

**Fix:** `match_best_agent` no longer bumps by default. `apply_workload_on_assignment` only when assignee changes (+1 new, -1 old, floor 0).

**Files:** `agent_matcher.py`

---

### P1.4 — Match → commit → notify

**Bug:** Hot notify scheduled before assignment commit → null assignee race.

**Fix:** Score path: ensure assignment → commit → then `create_task(notify)`.

**Files:** `agent.py`

---

### P1.5 — Handoff never assigns

**Bug:** Handoff notified without calling matcher.

**Fix:** Handoff calls `ensure_lead_assignment`, commits, then notifies with explicit-human reason.

**Files:** `agent.py`

---

### P1.10 — Wrong hot notification reason

**Bug:** Score ≥ 82 used “Explicit human agent requested.”

**Fix:** `hot_threshold_notification_reason(prob)` for score path; handoff keeps explicit human wording.

**Files:** `agent_matcher.py`, `agent.py`

---

### P1.11 — Claim does not bind assignee

**Bug:** Acknowledge set `claimed` without `assigned_agent` → sticky freeze of null.

**Fix:** Optional body `agent_name` / `agent_id` on `POST /api/v1/notifications/acknowledge` (tenant-scoped Agent lookup).

**Files:** `main.py`

---

### P1.6 — Speciality taxonomy

**Bug:** Classifier `investor`/`tenant` never matched agent `investment`/`rental` specialities.

**Fix:** `SPECIALITY_ALIASES` + `specialities_match()` used in scoring.

**Files:** `agent_matcher.py`

---

### P1.7 — Location match too strict

**Bug:** Exact token equality only.

**Fix:** `location_match_score` — 40 exact, 25 substring either way.

**Files:** `agent_matcher.py`

---

### P1.8 — Live open-lead counts

**Bug:** Load penalty only used mutable `active_leads`.

**Fix:** Score using `COUNT` of open leads for that assignee; fall back to counter on query error.

**Files:** `agent_matcher.py`

---

### P1.9 — Fake default agent name

**Bug:** Follow-ups used `"ABC Properties Team"` when unassigned.

**Fix:** `resolve_followup_agent_label` → real assignee, else client `company_name`, else omit sentence.

**Files:** `agent_matcher.py`, `follow_up.py`

---

### P1.12 — Frontend never shows assignee

**Bug:** API had field; UI did not display.

**Fix:** Kanban card line, Leads table column, PriorityAlertCard meta.

**Files:** `KanbanBoard.tsx`, `LeadsTable.tsx`, `PriorityAlertCard.tsx`

---

### P1.13 — Mock sales-agent RBAC

**Bug:** Dashboard filtered to Jane Doe / even ids.

**Fix:** Removed mock filter; show full tenant list until real agent auth.

**Files:** `dashboard/page.tsx`

---

### Hotfix — multi-field lead backfill when tool omits clear signals

**Bug:** LLM tool often returned name/property_type without `location` (e.g. “2bhk in baner”), so CRM stayed null while the reply mentioned Baner.

**Fix:** Deterministic empty-only backfill for `location`, `property_type`, `budget`, `intent` from user text (`backfill_missing_lead_fields`). Runs after tool apply and when tool is skipped. Never overwrites set fields; no free-form name invent; visit_date left to the model.

**Files:** `agent.py`, `tests/test_lead_backfill.py`

---

### Hotfix — Twilio `Client` shadowed by models.Client (follow-up)

**Bug:** After P1.9, `follow_up.py` imported `models.Client` for company name while still using `from twilio.rest import Client`. Twilio sends became `models.Client(sid, token)` → `TypeError: __init__() takes 1 positional argument but 3 were given`. Day 0 follow-up failed in TEST/prod logs.

**Fix:** `from twilio.rest import Client as TwilioClient`; use `TwilioClient(...)` for sends; keep `models.Client` for DB company lookup.

**Files:** `follow_up.py`

---

### Hotfix — `is_fully_qualified` shadowing (post–Phase 1)

**Bug:** Scoring path set `is_fully_qualified = bool(...)`, shadowing the helper. Re-arm later called `is_fully_qualified(lead)` → `TypeError: 'bool' object is not callable`. Webhook returned fake “connectivity issue” TwiML even after hot alert succeeded.

**Fix:** Use `is_fully_qualified_row = is_fully_qualified(lead)` / `is_fully_qualified_now = is_fully_qualified(lead)`; never bind a bool to the function name.

**Files:** `agent.py`, `tests/test_p0_safety.py`

---

## Phase 2 status

| ID | Status | Summary | Tests |
|---|---|---|---|
| P2.1 | **done** | `finalize_turn` — early intercepts now re-arm Day 0 | `tests/test_p2_fsm_language.py` |
| P2.2 | **done** | Terminal state docstrings (FSM table) | doc-only |
| P2.3 | **done** | Name interceptor validation blocklist (`validate_extracted_name`) | `tests/test_p2_fsm_language.py` |
| P2.4 | **done** | Funnel stage enum aligned to Kanban columns | `tests/test_p2_fsm_language.py` |
| P2.5 | **done** | Two-FSM docstring (session.status vs conversion_status) | doc-only |
| P2.6 | **done** | Language enforcement (detect + lock + guard) | `tests/test_p2_fsm_language.py` |

---

## Entries

### P2.1 — Early intercepts leave follow-up permanently stopped

**Bug:** `follow_up_status = "stopped"` set for all non-qualified users at line 472. Re-arm block at end of `process_chat` only ran on the full LLM path. 4 early intercepts (instant reply, property intent, guardrail, fatal LLM fallback) returned before re-arm → Day 0 never scheduled.

**Fix:** `finalize_turn(db, session, lead, f_state)` helper consolidates re-arm/terminal logic. Called at every exit point: instant reply, property intent, guardrail, handoff, fatal LLM fallback, opt-out, and normal path end. Replaces the inline re-arm block that was only reachable on the full LLM path.

**Files:** `agent.py`

**Tests:** `tests/test_p2_fsm_language.py` — 7 tests covering re-arm for open lead, no re-arm for qualified/opt-out/handoff/closed, None f_state safety, timestamp set.

---

### P2.2 — Terminal state documentation

**Bug:** `closed` overloaded across 5+ events; reopen logic ad hoc; maintainers cannot tell which states are terminal without reading all of `agent.py`.

**Fix:** Canonical FSM table added as module docstring at top of `agent.py` and expanded docstring on `is_terminal_chat_state`. Follow-up scheduler (`follow_up.py`) annotated with defense-in-depth terminal guards.

**Files:** `agent.py`, `follow_up.py`

---

### P2.3 — Name interceptor can commit garbage

**Bug:** Parallel Gemini name extraction saves "2BHK", "tomorrow", "Baner", "yes please" as `lead.name` with no validation.

**Fix:** `validate_extracted_name` helper: 1–3 tokens, mostly alphabetic, blocklist (bhk variants, budget terms, affirmations, Pune areas). Wired into concurrent extraction commit path. Rejected names logged at debug.

**Files:** `agent.py`

**Tests:** `tests/test_p2_fsm_language.py` — 11 tests: reject 2bhk, tomorrow, area, budget, affirmation, long string, numeric; accept single/two-word/hyphenated names, empty/None.

---

### P2.5 — session.status vs conversion_status confusion

**Bug:** Two independent FSMs (chat vs sales) documented nowhere in code; maintainers conflate them.

**Fix:** Module-level docstring at top of `agent.py` explaining the two FSMs are intentionally independent. Full qualification closes chat but does NOT auto-claim.

**Files:** `agent.py`

---

### P2.4 — Funnel stage enum diverges from frontend

**Bug:** Backend writes `"Human Handoff"`, `"Site Visit Done"` which land in Kanban "Other". Frontend references `"Qualified"` which backend never sets. No shared enum; PATCH accepts any string.

**Fix:** `FUNNEL_STAGES` constant in `agent.py` (`New`, `Contacted`, `Appointment Scheduled`, `Closed Won`, `Lost`). Handoff maps to `"Contacted"`. Dead `"Site Visit Done"` check removed. PATCH validated via `@field_validator`. Pipeline report includes `"Lost"`. Frontend removed phantom `"Qualified"` from filters/chart.

**Files:** `agent.py`, `main.py`, `models.py`, `LeadsTable.tsx`, `dashboard/page.tsx`

**Tests:** `tests/test_p2_fsm_language.py` — constant values, excludes removed values, PATCH validator rejects invalid stages.

---

### P2.6 — English user gets Hinglish reply (language match failure)

**Bug:** Pure English opener (`"hi, need 2bhk in hinjewadi"`) gets Hinglish reply from Gemini. System prompt says "DEFAULT TO ENGLISH" but LLM ignores it for Pune/real-estate context. No runtime enforcement.

**Fix (5-layer defense):**
- **Layer A:** `detect_user_language(text)` → `"english"` | `"hinglish"` (default English)
- **Layer B:** Language lock injected adjacent to user turn before LLM call ("LANGUAGE LOCK: Reply in English only...")
- **Layer C:** `conversational_reply` schema description now requires language matching; hard rule added to system_prompt.py
- **Layer D:** Output guard before DB save — if user=English and reply=Hinglish → swap safe English fallback
- **Layer E:** 9 tests for detection, guard, and user-initiated Hinglish allowed

**Files:** `agent.py`, `system_prompt.py`, `tests/test_p2_fsm_language.py`

**Phase 2 COMPLETE.**

---

*Phase 3+ tracked in `UNIFIED_EXECUTION_ORDER.md`.*
