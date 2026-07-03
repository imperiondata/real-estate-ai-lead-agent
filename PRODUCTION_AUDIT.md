# Production Design & Workflow Audit

Audit date: July 3, 2026  
Scope: Backend (FastAPI), Frontend (Next.js), Automation Engine (follow-up scheduler, ML scoring, notification service)

---

## Severity Key

| Label | Meaning |
|-------|---------|
| **CRITICAL** | Will cause data loss, missed leads, or silent failure in production. Fix before deploy. |
| **HIGH** | Will degrade reliability, observability, or correctness under production conditions. |
| **MEDIUM** | Usability, maintainability, or edge-case defects. |
| **LOW** | Code quality or cosmetic issues. |

---

## CRITICAL

### 1. DLQ test hook live in production code path

**File:** `follow_up.py:422-423`

**Bug:** The scheduler loop checks `FOLLOW_UP_TEST_MODE and FOLLOW_UP_DLQ_TEST` inside its main execution path and intentionally raises an exception when both are true. If someone deploys to production with these flags accidentally left in `.env`, every scheduler tick will throw for every active session.

**Fix:** Gate the entire test hook behind an additional `not settings.IS_PRODUCTION` check, or remove it entirely from the production code path. Better: move it to a dedicated test script that directly calls the dispatch logic.

```python
# follow_up.py:422-423
if not settings.IS_PRODUCTION and settings.FOLLOW_UP_TEST_MODE and settings.FOLLOW_UP_DLQ_TEST:
    raise Exception("QA_DLQ_TEST — intentional failure to verify DLQ pipeline")
```

Or remove the hook and rely on the dedicated `gate_dlq_drill.py` script for DLQ testing.

---

### 2. Duplicate hot-lead notifications for the same lead

**Files:** `agent.py:960-967` and `agent.py:488-489`

**Bug:** `trigger_hot_lead_notification()` is called from two different paths:
- Line 965: when ML scoring sets `conversion_probability >= 82`
- Line 488: when the user explicitly requests a human agent

A lead that scores ≥82 and then says "talk to an agent" will trigger two calls. The idempotency check in `notification_service.py:75-82` prevents a duplicate DB row, but the second call silently skips — so the human-handoff-specific reason (`"Explicit human agent requested."`) is lost, and the first generic reason is what the agent sees.

**Fix:** Coalesce the two triggers. Remove the duplicate call at one of the two sites and unify the reason string. For example, remove the generic trigger at line 965 and let the handoff handler at line 488 carry the specific reason:

```python
# agent.py:960-967 — remove or comment out lines 964-966
# Remove:
# asyncio.create_task(
#     trigger_hot_lead_notification(lead.id, "Explicit human agent requested.")
# )
```

The human handoff at line 488 already calls it with the correct reason.

---

### 3. Failed Twilio notifications silently disappear with no retry or escalation

**File:** `notification_service.py:153-156`

**Bug:** When all 3 Twilio dispatch attempts fail, `delivery_status` is set to `"failed"` and a `NotificationLog` row is written with that status. However, the escalation cron job (`main.py:132-190`) only processes statuses `"pending_ack"`, `"escalated_10m"`, and `"escalated_30m"`. It never queries for `"failed"` rows. The agent receives no alert, no retry, and no escalation.

**Fix:** Either:
- A. Set `delivery_status = "pending_ack"` even after Twilio failure (and rely on the email fallback + cron to escalate), or
- B. Add a `"failed"` handler to the escalation job that retries the Twilio dispatch after a cooldown period, or
- C. At least log a critical alert so operators know the notification failed.

Option B is recommended:

```python
# main.py:escalation_cron_job — add after line 186
failed_notifs = db.query(NotificationLog).filter(
    NotificationLog.status == "failed",
    NotificationLog.sent_at <= now - timedelta(minutes=5)
).all()
for log in failed_notifs:
    logger.error(f"⚠️ NOTIFICATION DELIVERY FAILED: Lead {log.lead_id}, agent {log.assigned_agent}")
    send_critical_alert("Notification Delivery Failure",
        f"Hot lead notification for lead {log.lead_id} could not be delivered to {log.assigned_agent}.")
```

---

### 4. CRM HubSpot sync silently succeeds with fake data in production

**File:** `crm_sync.py:47-49`

**Bug:** When `CRM_API_URL` and `CRM_API_KEY` are at their default values (`"https://api.hubapi.com/crm/v3/objects/contacts"` and `"demo-hubspot-key"`), the `_push_to_hubspot` function returns a randomly generated UUID without making any HTTP call. Every lead gets `crm_sync_status = "success"` with a fake external ID. If someone deploys to production without configuring real credentials, this gives a false confirmation that data is flowing to HubSpot.

**Fix:** Remove the demo stub and raise a clear configuration error instead:

```python
# crm_sync.py:47-49 — replace the demo block with:
if not settings.IS_PRODUCTION:
    # Demo stub for local dev only
    import uuid
    return {"id": str(uuid.uuid4())}

# Or better, validate at startup (config.py or main.py lifespan):
if settings.IS_PRODUCTION and (CRM_API_KEY == "demo-hubspot-key" or CRM_API_URL == "https://api.hubapi.com/crm/v3/objects/contacts"):
    raise RuntimeError("CRITICAL: Production HubSpot credentials not configured. Set CRM_API_URL and CRM_API_KEY.")
```

---

### 5. SQLite fallback instead of hard crash on missing DATABASE_URL

**File:** `config.py:28`

**Bug:** `DATABASE_URL` defaults to `"sqlite:///./real_estate_agent.db"`. If someone forgets to set `DATABASE_URL` in `.env`, the app silently runs on SQLite. SQLite does not support JSONB columns, certain PostgreSQL functions, or concurrent writes. The app will appear to work until it hits a Postgres-specific feature, which will manifest as a confusing runtime error.

**Fix:** Remove the SQLite default so the app fails fast at startup:

```python
# config.py:28
DATABASE_URL: str = ""  # No default — will be checked at startup
```

Then in `main.py` or `database.py`:

```python
# database.py — add after engine creation
if not settings.DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set. Check your .env file.")
if "sqlite" in settings.DATABASE_URL and settings.IS_PRODUCTION:
    raise RuntimeError("SQLite is not supported in production. Use PostgreSQL.")
```

---

## HIGH

### 6. TLS enforcement misses `IS_PRODUCTION` setting

**File:** `main.py:215`

**Bug:** The HTTPS redirect middleware checks `os.getenv("RENDER") or os.getenv("PRODUCTION")` directly from environment variables, bypassing the `Settings` class. If someone deploys to a non-Render host and sets `IS_PRODUCTION=true` in their `.env`, TLS will not be enforced.

**Fix:** Use `settings.IS_PRODUCTION` instead of raw `os.getenv()`:

```python
# main.py:215
if settings.IS_PRODUCTION or os.getenv("RENDER"):
    app.add_middleware(HTTPSRedirectMiddleware)
```

---

### 7. Race condition in CRM sync uses fragile sleep

**File:** `crm_sync.py:71`

**Bug:** `await asyncio.sleep(2)` delays CRM sync to avoid a race with `agent.py`'s DB writes. Under production load or latency spikes, 2 seconds may not be sufficient. The sleep is a fragile timing hack.

**Fix:** Replace the sleep with a polling loop that checks for a stable state:

```python
# crm_sync.py:69-72 — replace the sleep with:
for attempt in range(10):
    db.refresh(lead)
    if lead.phone and lead.name:
        break
    await asyncio.sleep(0.5)
```

---

### 8. DLQ entries missing `client_id`

**Files:** `crm_sync.py:114-119`, `main.py:389-393`

**Bug:** DLQ events for CRM failures and Twilio fallback failures do not include `client_id`. In a multi-tenant system, this makes it impossible to attribute DLQ entries to specific clients without parsing the payload JSON.

**Fix:** Pass `client_id` when creating both DLQ events:

```python
# crm_sync.py:114-119
dlq_entry = DLQEvent(
    target_endpoint="hubspot_crm",
    payload=payload,
    error_trace=str(e),
    status="pending",
    client_id=lead.client_id  # ← ADD THIS
)
```

```python
# main.py:389-393
dlq_entry = models.DLQEvent(
    target_endpoint="twilio_outbound",
    payload=payload_dlq,
    error_trace=str(fallback_err),
    status="pending",
    client_id=client_id  # ← ADD THIS
)
```

---

### 9. ML scoring errors written to ephemeral local file

**File:** `lead_scoring.py:629`

**Bug:** On scoring error, `traceback.format_exc()` is written to `lead_scoring_error.log` on the local filesystem through a raw file write, bypassing the Python logging system. On containerized deployments (Render, Docker), this file is on ephemeral disk and lost on restart. Operators won't see the error in their log aggregation.

**Fix:** Use the Python logger instead of raw file writes:

```python
# lead_scoring.py:628-634 — replace with:
except Exception as e:
    logger.error("Lead scoring failed", exc_info=True)
```

---

### 10. Single Uvicorn worker blocks all concurrent traffic

**File:** `Procfile`

**Bug:** `uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1` means one worker handles all requests. During an LLM call (up to 6s timeout + retries), all other incoming requests queue behind it. Under concurrent load, this causes cascading latency spikes and timeouts.

**Fix:** Increase workers and use Gunicorn for process management:

```
web: gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app --timeout 30
```

Or at minimum, increase Uvicorn workers to 2:

```
web: uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2
```

---

## MEDIUM

### 11. Frontend doesn't handle JWT expiration gracefully

**File:** `frontend/src/lib/api.ts`

**Bug:** Both `fetchLeads()` and `fetchAnalytics()` return `null` on any HTTP error (401, 500, etc.). If the JWT expires mid-session, the dashboard and lead pages silently show empty data with no redirect to `/login`. The middleware only checks cookie existence at page navigation, not during API calls.

**Fix:** Add 401 detection and redirect in the API client:

```typescript
// frontend/src/lib/api.ts — add a helper:
async function authFetch(url: string, options?: RequestInit) {
  const res = await fetch(url, options)
  if (res.status === 401) {
    const { redirect } = await import('next/navigation')
    redirect('/login')
  }
  return res
}

// Use authFetch instead of fetch in fetchLeads() and fetchAnalytics()
```

---

### 12. Settings page never syncs to backend

**File:** `frontend/src/app/(dashboard)/settings/page.tsx`

**Bug:** All user settings are persisted to `localStorage` only. Backend endpoints `GET /api/v1/settings` and `PATCH /api/v1/settings` exist but are never called. A user's preferences are device-local — switching machines or clearing localStorage loses all settings.

**Fix:** Call the backend API on mount (GET) and on save (PATCH):

```typescript
// On mount — fetch from backend
useEffect(() => {
  fetchBackendSettings().then(s => {
    if (s?.displayName) setDisplayName(s.displayName)
    // ... apply each field
  })
}, [])

// On save — patch backend + localStorage
const handleSave = async () => {
  await fetch(`${BACKEND_URL}/api/v1/settings`, {
    method: 'PATCH',
    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ settings: { displayName, company, defaultView, /* ... */ } })
  })
  // Also write to localStorage as fallback cache
}
```

---

### 13. CRM Kanban revert destroys subsequent changes

**File:** `KanbanBoard.tsx:59`

**Bug:** When a drop fails on the backend, the error handler calls `setLeads(initialLeads)`, which reverts to the snapshot captured at page render time. If the user made multiple successful drops and the last one fails, all previous drops are also reverted.

**Fix:** Maintain an undo stack or revert only the specific lead:

```typescript
// KanbanBoard.tsx:57-60 — replace with:
} catch (error) {
  console.error('Failed to update lead stage:', error)
  setToast({ message: 'Failed to update stage. Please try again.', type: 'error' })
  // Revert only the failed lead, not all changes
  setLeads(prev => prev.map(lead =>
    lead.id === leadId ? { ...lead, funnel_stage: leadToMove.funnel_stage } : lead
  ))
}
```

---

### 14. Kanban groups unknown-stage leads into "New" column

**File:** `KanbanBoard.tsx:25`

**Bug:** The column grouping logic includes: `stage === "New" && !STAGES.includes(l.funnel_stage)`. Leads with unexpected stages (e.g., `"Human Handoff"`, `"Site Visit Done"`) are dumped into the "New" column alongside genuinely new leads. This is misleading — they should be in their own "Other" column or handled explicitly.

**Fix:** Replace with an explicit fallback column:

```typescript
const STAGES = ["New", "Contacted", "Appointment Scheduled", "Closed Won", "Lost"]
const columns = STAGES.map(stage => ({
  name: stage,
  items: leads.filter(l => l.funnel_stage === stage)
}))
// Add overflow column
columns.push({
  name: "Other",
  items: leads.filter(l => !STAGES.includes(l.funnel_stage))
})
```

---

### 15. Hardcoded CORS origin for Vercel

**File:** `main.py:223`

**Bug:** `"https://real-estate-ai-lead-agent-5q20tzn22.vercel.app"` is hardcoded as a CORS origin. If the frontend is deployed under a different domain, renamed, or if there are staging/preview deployments, CORS will break.

**Fix:** Read from environment variable, fall back to current value:

```python
# main.py:222-224
allow_origins=[
    "http://localhost:3000",
    os.getenv("FRONTEND_URL", "https://real-estate-ai-lead-agent-5q20tzn22.vercel.app")
],
```

---

### 16. Sort field "score" maps to `engagement_score` not `conversion_probability`

**File:** `LeadsTable.tsx:53-54`

**Bug:** Clicking the "Intelligence" column header sorts by `engagement_score`, but the adjacent "Probability" column header sorts by `conversion_probability`. A user clicking "Intelligence" likely expects the primary scoring metric, not a sub-metric. The sort field key `"score"` is misleading.

**Fix:** Either rename the column header to "Engagement" or change the sort mapping to use `conversion_probability`:

```typescript
// Option A: rename the sort action
} else if (sortField === 'score') {
  valA = a.conversion_probability || 0  // Use probability, not engagement
  valB = b.conversion_probability || 0
}

// Option B: rename the column header to match what it actually sorts
<SortHeader label="Engagement" field="engagement_score" ... />
```

---

## LOW

### 17. `is_valid_email` defined twice

**File:** `add_client.py:21-24`

**Bug:** The function `is_valid_email` is defined at lines 16-19 and then immediately redefined at lines 21-24 with identical code. The first definition is dead code.

**Fix:** Remove the first definition (lines 16-19).

---

### 18. `if True:` dead conditional

**File:** `agent.py:898`

**Bug:** `if True:` wraps the ML scoring block. The comment says "Ensure it runs even if past_messages is empty" but the condition is literally `True`, not checking anything. The block always executes.

**Fix:** Remove the `if True:` wrapper. Indent the block body to the parent scope.

---

### 19. Variables assigned twice in notification service

**File:** `notification_service.py:119-120`

**Bug:** `delivery_status` and `twilio_sid` are assigned at lines 115-116 and then immediately reassigned to the same values at lines 119-120. Lines 115-116 are dead code.

**Fix:** Remove lines 115-116.

---

### 20. `success = False` assigned on consecutive lines

**File:** `follow_up.py:491-492`

**Bug:** `success = False` appears on two consecutive lines. The second assignment overwrites the first with the same value. Copy-paste residue.

**Fix:** Remove line 491.
