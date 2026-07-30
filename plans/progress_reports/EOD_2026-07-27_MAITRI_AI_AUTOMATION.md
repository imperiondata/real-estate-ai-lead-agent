# Daily Progress Report — Maitri

**Date:** Monday, 27 July 2026  
**Role:** AI Automation Owner  
**Branch:** `phase3_automations`  
**Program context:** Post-G3 · Automation agents live · Gate **G4** blocked on n8n WF-1 ops evidence  
**Relative plans:** `plans/PHASE3_AUTOMATIONS_CLOSEOUT.md`, `plans/IREIOS_3.0_WAVE_A_D_CHANGELOG.md`, `plans/IREIOS_3.0_AI_Automation_Workflows.md`, `docs/N8N_INTEGRATION.md`, negotiation design (`negotiation.md`)

---

## 1. Summary of work completed

### Today (27 Jul)

| Area | Outcome |
|------|---------|
| **Sales AI / calendar booking path** | Fixed debounce that blocked visit booking on `lead.qualified`; NBA priority: schedule before escalate |
| **Natural-language visit dates** | CalendarExecutor parses `"Saturday 10:00 AM"`-style strings into next weekday slot |
| **Google event richness** | Location passed into Calendar event body + `schedule_visit` params |
| **Hot + visit dual action** | When hot lead books visit, fire hot-lead notify **alongside** `schedule_visit` (escalate was bypassed by visit priority) |
| **LLM timeout bump (interim)** | Increased LLM response timeout early in day (later superseded/aligned by backend P3.7 defaults) |

### Recent (25 Jul — still current product surface)

| Area | Outcome |
|------|---------|
| **Non-blocking negotiation automation** | Dual-layer detection, `is_negotiating` flag, bus event, NegotiationAgent notify-only (no HITL pause), CRM purple badge + claim |

### Commits authored (git)

```text
68150a4  fix: calendar booking debounce, date parsing, location, and hot lead alert   (27 Jul)
6cef706  feat: increased timeout for llm response                                      (27 Jul)
b9a37ec  feat(ireios): non-blocking negotiation UI with dual-layer detection           (25 Jul)
```

*(Earlier program work still in scope for status: Waves A–D depth fill `d11558f`, Wave changelog `e7d9192`, Phase 1/1b bus+SSE, P3 concurrency hardening — see §3.4.)*

---

## 2. Current status of assigned tasks

### vs program master table

| Step / Gate | Status | Maitri ownership |
|-------------|--------|------------------|
| Waves A–D automation depth (Sales/CS/Marketing/templates/agents) | **Done** | Code + 54 wave tests green (prior) |
| Negotiation agent + UI contract | **Done** | Dual-layer + non-blocking HITL design |
| Calendar / Sales NBA path for site visits | **Hardened today** | Debounce bypass + NL dates + location |
| **n8n WF-1** `ireios_hot_lead_slack` on `lead.hot` | **`[~]` Open — ops** | **Primary remaining G4 item** |
| n8n WF-2…WF-6 | Pending | After WF-1 smoke |
| Gate **G4** | **Partial** | Backend BA-7 done; needs WF-1 Active + screenshot |

### Lane split (locked)

```text
Python Revenue OS (bus, WA, AE→EE, Calendar create)  →  Backend (Aritro)
Extension plane n8n (Slack, ops email, Drive CSV, external CRM nodes)  →  Maitri
```

**n8n must NOT own:** 6-field qualify gate, Day0→7 follow-up FSM, 10m/30m escalation cron, Twilio TwiML race, tenant JWT.

---

## 3. Detailed work with evidence

### 3.1 Sales bus: `lead.qualified` + debounce bypass (today)

**Bug:** SalesAgent 10-minute Redis debounce treated all bus events equally. After a `conversation.updated` / score tick, a subsequent **`lead.qualified`** (visit fields complete) was **skipped** — so `schedule_site_visit` never reached AE→EE→CalendarExecutor.

**Fix (`app/agents/sales_agent.py`):**

```python
SALES_BUS_EVENTS = [
    "lead.scored", "lead.hot", "conversation.updated", "lead.qualified"
]

# In sales_bus_handler:
# P3: lead.qualified bypasses debounce — visit booking is time-critical.
if event_type == "lead.qualified":
    logger.debug(
        "sales_bus debounce bypassed for lead.qualified: lead %s client %s",
        lid, client_id,
    )
else:
    # normal SET NX debounce skip...
```

**NBA reorder (visit beats hot escalate):**

```python
# visit_date present and stage not yet Site Visit Booked / Negotiation
→ action: schedule_site_visit

# else if temperature == hot
→ action: escalate_hot
```

**Hot + visit dual path:** when NBA is `schedule_site_visit` **and** temperature is hot, also submit hot-lead notification / task so the human agent still gets the WhatsApp alert even though pure `escalate_hot` was not selected:

```text
schedule_visit (Calendar)  +  notify_agent / create_task (hot lead with confirmed visit)
```

**Commit:** `68150a4`

---

### 3.2 CalendarExecutor — NL date parse + location (today)

**Problem:** LLM often stores visit as human text (`"Saturday 10:00 AM"`). ISO-only parse failed → fallback “tomorrow UTC”, wrong calendar slot. Location was not on the Google event.

**Fix (`app/execution_engine/calendar_executor.py`):**

```python
def _parse_start(visit_date) -> datetime:
    # 1. ISO-8601
    # 2. Natural language: "Saturday 10:00 AM", "friday 2:30pm"
    match = re.match(
        r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday)'
        r'\s+(\d{1,2}:\d{2})\s*(am|pm)?',
        text, re.IGNORECASE,
    )
    # → next occurrence of that weekday + AM/PM hour math
    # 3. Fallback: tomorrow UTC
```

Event body includes:

```python
"location": params.get("location", ""),
description = f"... Location: {params.get('location') or ''}"
# returns html_link when Google API succeeds
```

**Architecture note (still enforced):** CalendarExecutor does **not** `event_bus.publish`. EE maps `schedule_visit` → `site_visit.scheduled` after success (single event for n8n/KG).

---

### 3.3 Non-blocking negotiation automation (25 Jul — product live)

**Design goal:** Detect negotiation intent without pausing the AI chat (no HITL freeze). Flag lead for human claim from CRM.

| Layer | Where | Trigger |
|-------|--------|---------|
| **L1** | `agent.py` keyword intercept | negotiate, discount, reduce price, too expensive, best price, … |
| **L2** | `whatsapp_agent.py` | budget misalignment |
| **Bus** | `app/events/negotiation.py` | `lead.negotiation.started` (`trigger` = `user_phrase` \| `budget_misaligned`), **5 min Redis debounce** |
| **Agent** | `negotiation_agent.py` | misaligned → `notify_admin` only (approval pause **removed**) |
| **DB/UI** | `Lead.is_negotiating` | purple “Open for Negotiation” badge; claim on any Kanban column |

**Tests:** `tests/test_e19_negotiation_ui.py` (14 cases initially; Priority Alert coverage extended by backend FE polish today).

**Commit:** `b9a37ec` · Design note: `negotiation.md`

**Example event payload shape (catalog):**

```json
{
  "event_type": "lead.negotiation.started",
  "payload": {
    "trigger": "user_phrase",
    "budget": "80L",
    "budget_alignment_status": "misaligned",
    "message": "can you reduce the price..."
  }
}
```

---

### 3.4 Automation stack status (already shipped — current baseline)

| Domain | Status | Implementation |
|--------|--------|----------------|
| WhatsApp AI qualify / FAQ / brochure / floorplan | Done | `WhatsAppAgent` v3 default; Approach B `media_url` |
| Follow-up automation | Done | `FOLLOWUP_ENGINE=v3` → AE → WhatsAppExecutor; `followup_arm` |
| CRM automation | Done | bus `crm_automation` → AE→EE `update_crm` |
| Sales AI NBA + objections lexicon | Done + hardened today | bus + API `POST /api/v1/leads/{id}/sales-ai` |
| Marketing / CS / Competitor | Done (MVP) | bus + cron |
| Wave C agents (pricing, inventory, onboarding, finance, legal, negotiation) | Active | CEO-registered |
| AE templates | Done | `hot_lead_notify`, `visit_booking` (+ optional `template_type=n8n`) |
| HITL engine | Done | `approval.requested` + approve/reject APIs (n8n WF-3 consumer pending) |
| LangGraph | Scaffold | linear fallback if package absent |
| **n8n UI workflows WF-1…6** | **Ops incomplete** | Docker service ready; workflows not Active |

---

### 3.5 n8n contracts ready for Maitri activation (backend already emits)

From `docs/N8N_INTEGRATION.md` + closeout plan:

| WF | Trigger event | Action | Status |
|----|---------------|--------|--------|
| **WF-1 P0** | `lead.hot` (`trigger`: `hot_threshold` \| `human_handoff`) | Slack alert | **Must activate** |
| WF-2 | `site_visit.scheduled` | Email/Slack fan-out only (no second Google create if `provider=google_calendar`) | Pending |
| WF-3 | `approval.requested` | Manager links approve/reject | Pending |
| WF-4 | `lead.qualified` (+ `chat_context`) | External CRM note via n8n nodes | Pending |
| WF-5 | `marketing.report.generated` | CSV → Drive | Pending |
| WF-6 | Cron 15m | DLQ depth Slack | Pending |

**Dual-publish rule:** subscribe to **either** `lead.hot` **or** alias `lead.escalated` — never both (double Slack).

**Local n8n bring-up:**

```powershell
docker compose up -d n8n
# UI: http://localhost:5678
```

**Stub publish for WF-1 smoke (example):**

```powershell
curl -N "http://localhost:8000/api/v1/events/stream?api_key=secret-client-key-123"
python publish_stub_event.py --event-type lead.hot --tenant-id Client_1 --payload "{\"lead_id\":1,\"trigger\":\"hot_threshold\",\"name\":\"demo\"}"
```

---

### 3.6 LLM timeout note (today)

**Commit `6cef706`:** early increase of LLM response timeout in `agent.py` / `main.py` to reduce interim/fatal paths during negotiation+visit tests.

**Later same day (backend P3.7 `b61e84e`):** production defaults standardized to race **13s** / LLM **22s**, with **no TimeoutError retry**. Automation testing should use those Settings / `.env` knobs going forward (`docs/TIMEOUTS_AND_TIMINGS.md`).

---

## 4. Evidence checklist

| Evidence | Location |
|----------|----------|
| Calendar + Sales fix commit | `68150a4` |
| Negotiation feature commit | `b9a37ec` |
| Sales bus events | `app/agents/sales_agent.py` `SALES_BUS_EVENTS` |
| NL date parser | `app/execution_engine/calendar_executor.py` `_parse_start` |
| Negotiation event module | `app/events/negotiation.py` |
| Negotiation tests | `tests/test_e19_negotiation_ui.py` |
| Wave A–D automation completion | `plans/IREIOS_3.0_WAVE_A_D_CHANGELOG.md` |
| n8n ops guide | `docs/N8N_INTEGRATION.md` |
| G4 exit criteria | `plans/PHASE3_AUTOMATIONS_CLOSEOUT.md` §8 |
| Program table WF-1 | `plans/UNIFIED_EXECUTION_ORDER.md` Step 24 / G4 |

**Suggested terminal proof:**

```powershell
git log --author="maitri" --oneline -10
git show 68150a4 --stat
# After n8n WF-1 Active:
# screenshot of workflow "Active" + Slack message from stub/real lead.hot
```

---

## 5. Blockers / challenges

| Item | Severity | Notes |
|------|----------|--------|
| **WF-1 not yet Active with evidence** | **High (G4)** | Code path + events ready; needs n8n UI workflow + Slack credential + screenshot for closeout |
| **Live conversation stress pack** | Medium | `task3_runner.py` still best-effort (Gemini quota / server up) |
| **Meta/Google Ads spend APIs** | Out of MVP | Architecture ready; no live ad-spend integration |
| **HubSpot in Python** | Skipped by mandate | Use n8n HubSpot node on `lead.qualified` if business needs CRM upsert |
| **Coordination** | Low | Visit booking path depends on bus `lead.qualified` + EE calendar; verified in code today — joint E2E smoke still recommended |

No code-level blocker inside Sales/Calendar/Negotiation automation for current plan scope.

---

## 6. Plan for next steps

1. **P0 — Gate G4:** Activate n8n **WF-1** `ireios_hot_lead_slack` on Redis Streams (or AE webhook) filtered to `lead.hot`; capture screenshot of Active workflow + one Slack delivery (stub or real hot lead).  
2. **P1 — WF-2 / WF-3:** Fan-out on `site_visit.scheduled` (invite email only if Google already created); HITL manager notify on `approval.requested` with approve/reject deep links.  
3. **P2 — WF-4…6:** External CRM note from `chat_context`, marketing CSV, DLQ depth cron.  
4. **Joint smoke with backend:**  
   - Chat/WA full qualify → `lead.qualified` → Sales NBA → Calendar event with correct weekday + location  
   - Hot threshold / handoff → `lead.hot` → Slack  
   - Negotiation phrase → badge + notify without chat freeze  
5. **Evidence pack:** attach n8n screenshots + sample event JSON to deployment report; mark UNIFIED G4 `[x]` when WF-1 green.  
6. **Do not** move follow-up FSM or escalation crons into n8n.

---

## 7. One-line status for standup

> Sales/calendar automation fixed (qualified debounce bypass, NL visit dates, location, hot+visit dual notify); negotiation non-blocking path live — **G4 still needs n8n WF-1 Active + Slack smoke evidence**.
