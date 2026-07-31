# IREIOS — Google Cloud + n8n Setup Guide (self-hosted Docker)

**Audience:** ops / automation owner setting up a **fresh** machine (or onboarding Mayank).  
**Last updated:** 2026-07-31 · n8n image `n8nio/n8n:2.31.5` · Docker Compose service `n8n` → `http://localhost:5678`

This guide covers **everything** needed for:

| Integration | Who uses it | Auth type |
|-------------|-------------|-----------|
| **Gmail** (hot lead, visit fan-out, HITL, marketing CSV, DLQ alert) | **n8n** workflows | OAuth2 (user login) |
| **Google Sheets** (CRM append on `lead.qualified`) | **n8n** WF-4 | OAuth2 (same OAuth client) |
| **Google Drive API** | Required by Sheets (enable only) | — |
| **Google Calendar** (create site-visit events) | **Python** `CalendarExecutor` — **not** n8n | **Service account** JSON |

> **n8n does not create Calendar events.** Python creates the event and publishes `site_visit.scheduled`; n8n only emails the fan-out (with real `html_link` when Calendar worked).

Architecture / bridge: [`docs/N8N_INTEGRATION.md`](N8N_INTEGRATION.md).  
Official n8n reference: [Google OAuth2 single service](https://docs.n8n.io/integrations/builtin/credentials/google/oauth-single-service/).

---

## Prerequisites

- Docker + this repo (`docker compose up -d n8n redis`)
- Python venv with project deps (`uv run` or activated `.venv`)
- Google account(s) for:
  - **Cloud Console owner** (creates project / OAuth / SA)
  - **n8n OAuth test users** (who click “Sign in with Google” — can be same or different Gmail)
  - **Ops inbox** (who **receives** alert emails — set later in n8n Gmail **To**)
- Browser access to `http://localhost:5678`

---

## Part A — Google Cloud Console

### A0. Open the correct project

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Top bar → **project dropdown** → select your project **or** **New Project**
3. Suggested name: `ireios-n8n` (or reuse an existing project)
4. Confirm the selected project name stays visible in the top bar for all later steps

---

### A1. Enable APIs

Path: **APIs & Services → Library**  
Direct: https://console.cloud.google.com/apis/library

Search and **Enable** each of these (one by one):

| API | Why |
|-----|-----|
| **Gmail API** | n8n Gmail nodes + WF-5 Gmail HTTP send |
| **Google Sheets API** | n8n WF-4 append rows |
| **Google Drive API** | **Required** by Sheets (n8n / Google docs) |
| **Google Calendar API** | Python `CalendarExecutor` creates events |

Verify: **APIs & Services → Enabled APIs & services** shows all four.

---

### A2. OAuth consent screen (Google Auth Platform)

Path: **APIs & Services → OAuth consent screen**  
(Google may redirect to **Google Auth Platform → Overview**)

1. Click **Get started** (if first time)
2. **App information**
   - App name: `IREIOS n8n`
   - User support email: your Google address
   - **Next**
3. **Audience**
   - Choose **External** (personal Gmail / any Google account)
   - **Internal** only works for Google Workspace org members
   - **Next**
4. **Contact information** — your email → **Next**
5. Accept User Data Policy → **Continue** → **Create**

#### Branding / authorized domains (optional for localhost)

1. Left nav → **Branding** (or OAuth branding)
2. **Authorized domains** — for pure `localhost` dev you can skip; for a real domain add it here
3. **Save**

#### Audience = Testing + test users (**critical**)

While status is **Testing**, **only Test users** can complete OAuth.

1. Left nav → **Audience**  
   Direct: https://console.cloud.google.com/auth/audience
2. Confirm **Publishing status: Testing** and **User type: External**
3. **Test users → + Add users**
4. Add every Google account that will:
   - Click **Sign in with Google** inside n8n, **and/or**
   - Own the Gmail that sends mail
5. Examples: `you@gmail.com`, teammate Gmails  
6. **Save**

> **Do not “Publish app”** unless you complete Google verification. Testing mode is fine for internal/dev (token refresh can expire ~7 days — just re-Sign in in n8n).

---

### A3. OAuth 2.0 Client ID (for **n8n** Gmail + Sheets)

This is a **Web application** OAuth client. One client is enough for both Gmail and Sheets credentials in n8n.

1. **APIs & Services → Credentials**  
   https://console.cloud.google.com/apis/credentials
2. **+ Create credentials → OAuth client ID**
3. Application type: **Web application**
4. Name: `ireios-n8n-oauth` (or `test-ireios-n8n`)
5. **Authorized JavaScript origins** — leave empty for local n8n
6. **Authorized redirect URIs → + Add URI**

   ```text
   http://localhost:5678/rest/oauth2-credential/callback
   ```

   - Must match **exactly** (scheme, host, port, path)
   - If n8n is exposed on another host later, add that callback too
7. **Create**
8. **Copy immediately:**
   - **Client ID** (`….apps.googleusercontent.com`)
   - **Client secret** (shown once — store in a password manager)

Optional: on the client detail page you can **Download JSON** (OAuth client JSON).  
That file is for **reference only** — n8n wants Client ID + Secret pasted into the UI, not the SA key.

---

### A4. Service account (for **Python Google Calendar** — not n8n)

n8n OAuth ≠ Calendar executor. Backend needs a **service account**.

1. **APIs & Services → Credentials → + Create credentials → Service account**
2. Name: `calendar-ireios` (or similar)
3. Create and open the service account
4. **Keys → Add key → Create new key → JSON → Create**
5. Save the downloaded JSON **outside the git repo** (never commit it), e.g.

   ```text
   D:/secrets/ireios-calendar-sa.json
   ```

6. Note the SA email, e.g. `calendar-ireios@PROJECT.iam.gserviceaccount.com`

#### Share a real Google Calendar with the SA

1. Open [Google Calendar](https://calendar.google.com) as the human who owns the calendar
2. Create or pick a calendar → **Settings and sharing**
3. **Share with specific people** → add the **service account email**
4. Permission: **Make changes to events**
5. Copy **Calendar ID** (often your email, or an `…@group.calendar.google.com` id under Integrate calendar)

#### `.env` (backend — not n8n)

```env
GOOGLE_CALENDAR_ID=your-calendar-id-or-email
# Windows: prefer forward slashes
GOOGLE_CALENDAR_CREDENTIALS_JSON=D:/secrets/ireios-calendar-sa.json
GOOGLE_CALENDAR_TIMEZONE=Asia/Kolkata
```

Restart **uvicorn** after changing these. Leave empty → CalendarExecutor uses **stub** (`provider=stub`, no real `html_link`).

---

### A5. Google Sheet for WF-4 (CRM append)

1. Create a Sheet in the Google account you will connect to n8n Sheets OAuth  
2. Tab name default used by WF-4: **`Sheet1`**  
3. Optional header row: `name, phone, location, budget, property_type, visit_date, timestamp, tenant_id, entity_id`
4. Copy spreadsheet ID from the URL:

   ```text
   https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit
   ```

5. WF-4 JSON embeds a default sheet ID — **after import**, open WF-4 → Google Sheets API node → paste **your** spreadsheet ID in the URL if different:

   ```text
   https://sheets.googleapis.com/v4/spreadsheets/YOUR_ID/values/Sheet1:append?valueInputOption=USER_ENTERED
   ```

---

## Part B — Docker n8n + IREIOS env

### B1. Start n8n

```powershell
docker compose up -d n8n redis
```

- UI: http://localhost:5678  
- First visit: create **owner** email/password  
- Data volume: `n8ndata` (persists credentials — **do not wipe** casually)

### B2. Two secrets in project `.env` (do not mix)

| Variable | Purpose | Example |
|----------|---------|---------|
| `N8N_BASE_URL` | n8n base | `http://localhost:5678` |
| `N8N_API_KEY` | **Webhook** Header Auth secret (backend → n8n) | `local-n8n-webhook-secret` |
| `N8N_MANAGEMENT_API_KEY` | JWT from n8n **Settings → n8n API** (import script only) | paste JWT |
| `N8N_BRIDGE_ENABLED` | Bus → webhook bridge | `true` |

```env
N8N_BASE_URL=http://localhost:5678
N8N_API_KEY=local-n8n-webhook-secret
N8N_MANAGEMENT_API_KEY=
N8N_BRIDGE_ENABLED=true
N8N_BRIDGE_GROUP=ireios-n8n
```

Restart **uvicorn** after edits so the bridge picks up keys.

---

## Part C — Credentials inside n8n UI

Open http://localhost:5678 → **Credentials** (or Overview → Credentials).

Exact **names** matter — `import_n8n_workflows.py` resolves by name:

| Name (exact) | Type | Purpose |
|--------------|------|---------|
| `IREIOS API Key` | **Header Auth** | Protect `/webhook/*` |
| `Gmail account` | **Gmail OAuth2 API** | Send mail |
| `Google Sheets account` | **Google Sheets OAuth2 API** | WF-4 |

### C1. Header Auth — `IREIOS API Key`

1. **Create credential → Header Auth**
2. Name: `IREIOS API Key`
3. **Name** (header name): `Authorization`
4. **Value**: `Bearer local-n8n-webhook-secret`  
   - Must match `.env` `N8N_API_KEY` **including** the word `Bearer ` and a space
5. Save

### C2. Gmail OAuth2 — `Gmail account`

1. **Create credential → Gmail OAuth2 API** (or Gmail OAuth2)
2. Name: `Gmail account`
3. **Client ID** / **Client Secret** from Part A3
4. Save
5. **Sign in with Google** → pick a **test user** from A2
6. Allow Gmail scopes → return to n8n → Save again  
7. Credential should show connected / green

### C3. Google Sheets OAuth2 — `Google Sheets account`

1. **Create credential → Google Sheets OAuth2 API**
2. Name: `Google Sheets account`
3. **Same** Client ID + Secret as Gmail
4. **Sign in with Google** (same or another test user that can edit the Sheet)
5. Save

### C4. Management API key (for import script)

1. n8n → **Settings → n8n API** (http://localhost:5678/settings/api)
2. **Create API key** → copy the **JWT**
3. Put in `.env`:

   ```env
   N8N_MANAGEMENT_API_KEY=eyJ...   # full JWT — NOT the webhook secret
   ```

4. Using `N8N_API_KEY` here always returns **401** on `/api/v1/workflows`

---

## Part D — Import workflows

From **repo root** (venv / uv):

```powershell
uv run python import_n8n_workflows.py
# or: python import_n8n_workflows.py
```

What it does:

1. Health-check n8n  
2. Lists existing workflows  
3. Resolves credentials by **name** (REST or `docker exec … export:credentials`)  
4. Creates WF-1…WF-6 from `n8n_workflows/*.json`  
5. Tries activate/publish  

### If import fails with 401

- `N8N_MANAGEMENT_API_KEY` missing or equals webhook secret → fix C4  
- See CLI fallback in `docs/N8N_INTEGRATION.md`

### If workflows already exist

Script skips create by name and tries activate. To re-import cleanly: delete workflows in UI (or archive), then re-run — **do not wipe the whole volume** just to fix IDs.

---

## Part E — After import (required before emails work)

Repo JSON intentionally leaves Gmail **To** empty (no surprise mail to old addresses).

For **each** of WF-1, WF-2, WF-3, WF-6:

1. Open workflow in editor  
2. Click **Gmail** node(s)  
3. Set **To** = ops inbox (e.g. your test Gmail)  
4. Confirm credential dropdown = `Gmail account`  
5. **Save**  
6. **Publish** (n8n v2 runs the **published** version — draft-only changes do not fire production webhooks)

**WF-4:**

1. Confirm Sheets credential = `Google Sheets account`  
2. URL spreadsheet ID = your sheet (A5)  
3. Save + Publish  

**WF-5:**

1. Open **Build MIME + Send** (Code node — middle node, `{ }` icon)  
2. Find:

   ```js
   const to = 'OPS_EMAIL_PLACEHOLDER';
   ```

3. Change **only that string** to your email (do **not** find-replace the whole file — that can break the validation `if`)  
4. Save + Publish  

**WF-6** is cron (every 15 min) — no webhook; still needs Gmail **To**.

---

## Part F — Smoke tests

### F1. Direct webhook (no bus)

```powershell
curl -X POST "http://localhost:5678/webhook/ireios_hot_lead_alert" `
  -H "Authorization: Bearer local-n8n-webhook-secret" `
  -H "Content-Type: application/json" `
  -d "{\"event_type\":\"lead.hot\",\"tenant_id\":\"Client_1\",\"entity_id\":\"1\",\"timestamp\":\"2026-07-31T12:00:00+00:00\",\"payload\":{\"lead_id\":1,\"name\":\"Demo\",\"phone\":\"+9199\",\"location\":\"Baner\",\"budget\":\"80L\",\"property_type\":\"2BHK\",\"score\":90,\"trigger\":\"hot_threshold\",\"assigned_agent\":\"Sneha\"}}"
```

Expect **200** + Gmail in the **To** inbox.  
**403** → Header Auth mismatch.  
**404** → workflow not Published / wrong path.

### F2. Via IREIOS bus (uvicorn + bridge)

```powershell
python publish_stub_event.py --event-type lead.hot --tenant-id Client_1 --entity-id 1 --payload "{\"lead_id\":1,\"name\":\"Demo\",\"phone\":\"+9199\",\"trigger\":\"hot_threshold\",\"score\":90,\"reason\":\"stub\"}"
```

API log should show `n8n_bridge_forwarded`.

### F3. Sheets (WF-4)

```powershell
python publish_stub_event.py --event-type lead.qualified --tenant-id Client_1 --entity-id 2 --payload "{\"name\":\"Sheet Test\",\"phone\":\"+9188\",\"location\":\"Baner\",\"budget\":\"50L\",\"property_type\":\"2BHK\",\"visit_date\":\"2026-08-01\"}"
```

### F4. Real calendar link (not n8n-only)

Needs Part A4 + a real WhatsApp/sales path that fires `schedule_visit`.  
Stub/test payloads with `html_link=…eid=test` will **not** open in Google (by design).

---

## Part G — What Mayank (or any new machine) must do — checklist

Order matters:

1. [ ] `docker compose up -d n8n redis` + owner account  
2. [ ] Google project + enable **Gmail, Sheets, Drive, Calendar** APIs  
3. [ ] OAuth consent **External / Testing** + **test users**  
4. [ ] OAuth **Web** client + redirect `http://localhost:5678/rest/oauth2-credential/callback`  
5. [ ] (Optional for real visits) Service account JSON + share Calendar + `.env` `GOOGLE_CALENDAR_*`  
6. [ ] n8n credentials: Header Auth + Gmail + Sheets (exact names)  
7. [ ] n8n Settings → API key → `N8N_MANAGEMENT_API_KEY` in `.env`  
8. [ ] `N8N_API_KEY` matches Header Auth value  
9. [ ] `uv run python import_n8n_workflows.py`  
10. [ ] Set Gmail **To** (+ WF-5 Code `to`) on all mail workflows  
11. [ ] **Publish** all 6 workflows  
12. [ ] Fix WF-4 spreadsheet ID if needed  
13. [ ] Smoke F1–F3; restart uvicorn if env changed  
14. [ ] FE work is **separate** — see [`docs/FRONTEND_BACKLOG.md`](FRONTEND_BACKLOG.md)

**Not enough** to only “create Google credentials + run import” without steps 6–11.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `redirect_uri_mismatch` | Redirect URI must be exact callback above |
| Google hasn’t verified this app | Add account under **Audience → Test users** |
| `invalid_client` | Re-copy Client ID/Secret; no trailing spaces |
| OAuth worked then died after ~7 days | Testing mode token expiry — Sign in with Google again in n8n |
| Import `401 unauthorized` | Use management JWT, not webhook secret |
| Webhook `403` | Header Auth = `Authorization` + `Bearer {N8N_API_KEY}` |
| Webhook `404` | Publish workflow; path e.g. `ireios_hot_lead_alert` |
| Gmail “To is required” | Set To in UI + Publish (repo ships empty To) |
| WF-5 always throws after find-replace | Only edit `const to = '…'`; don’t replace validation strings |
| Empty email fields / `—` in subject | Flatten node should ship in WF JSON; ensure published version is latest |
| Calendar link 400 | Fake `eid=test` or stub provider — need real CalendarExecutor + SA share |
| Sheets 403 | Sheet not shared with the Google user who OAuth’d Sheets credential |
| Wiped volume lost OAuth | Recreate C2–C3; do not wipe to “fix” IDs |

---

## Security notes

- Never commit OAuth client secrets, SA JSON, or management JWTs  
- `.env` and secret paths stay local  
- `N8N_ENCRYPTION_KEY` in Compose pins credential encryption across container recreates (change in real prod)  
- Prefer not wiping `n8ndata`; re-link credentials in UI instead  

---

## Related docs

| Doc | Contents |
|-----|----------|
| [`N8N_INTEGRATION.md`](N8N_INTEGRATION.md) | Bridge architecture, envelope, two-key table, CLI fallback |
| [`TIMEOUTS_AND_TIMINGS.md`](TIMEOUTS_AND_TIMINGS.md) | WA 13s race / LLM 22s |
| [`FRONTEND_BACKLOG.md`](FRONTEND_BACKLOG.md) | Mayank remaining FE work |
| `n8n_workflows/*.json` | WF-1…WF-6 definitions |
| `import_n8n_workflows.py` | REST import + credential name injection |
