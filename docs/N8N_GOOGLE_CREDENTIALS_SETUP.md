# n8n Google Credentials Setup — Step-by-Step Guide

Complete guide to set up Google OAuth2 credentials in Google Cloud Console and connect them to your self-hosted n8n instance for Gmail and Google Sheets integration.

> **Scope:** Gmail OAuth2 (send emails, read labels) + Google Sheets OAuth2 (append rows).  
> One OAuth Client covers **both** services — you do not need separate credentials per Google API.

---

## Prerequisites

- A Google account (personal Gmail or Google Workspace)
- Access to [Google Cloud Console](https://console.cloud.google.com)
- n8n running locally (`docker compose up -d n8n`) at `http://localhost:5678`
- n8n owner account created (first visit setup)

---

## Step 1 — Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Click the **project dropdown** in the top navigation bar (next to "Google Cloud")
3. Click **New Project**
4. Enter a project name: `ireios-n8n`
5. Select your organization (or "No organization" for personal accounts)
6. Click **Create**
7. Wait 10–15 seconds, then **select the new project** from the dropdown

> **Already have a project?** Skip to Step 2.

---

## Step 2 — Enable Required APIs

You need to enable two APIs: **Gmail API** and **Google Sheets API**.

### Enable Gmail API

1. Go to **APIs & Services > Library** ([direct link](https://console.cloud.google.com/apis/library))
2. Search for `Gmail API`
3. Click the **Gmail API** card
4. Click **Enable**
5. Wait for the confirmation

### Enable Google Sheets API

1. Return to **APIs & Services > Library**
2. Search for `Google Sheets API`
3. Click the **Google Sheets API** card
4. Click **Enable**

### Enable Google Drive API (required for Sheets)

> Google Sheets API requires Google Drive API to be enabled as well.

1. Return to **APIs & Services > Library**
2. Search for `Google Drive API`
3. Click **Google Drive API**
4. Click **Enable**

### Verify enabled APIs

Go to **APIs & Services > Enabled APIs & services**. You should see:

| API | Status |
|-----|--------|
| Gmail API | Enabled |
| Google Sheets API | Enabled |
| Google Drive API | Enabled |

---

## Step 3 — Configure OAuth Consent Screen

This screen appears when n8n asks for permission to access your Google account.

1. Go to **APIs & Services > OAuth consent screen** ([direct link](https://console.cloud.google.com/apis/credentials/consent))
2. Click **Get started**
3. Fill in **App information**:
   - **App name:** `IREIOS n8n`
   - **User support email:** your email address
4. Click **Next**
5. **Audience:** Select **External** (works for any Google account)
   - **Internal** only works for Google Workspace org members
6. Click **Next**
7. **Contact information:** Enter your email address
8. Click **Next**
9. Check the checkbox to agree to Google's User Data Policy
10. Click **Continue** then **Create**

### Add authorized domain

1. In the left sidebar, click **Branding**
2. Under **Authorized domains**, click **Add domain**
3. Enter: `localhost`
   - For production: enter your actual domain (e.g., `yourcompany.com`)
4. Click **Save**

### Add test users

> **Critical:** In Testing mode, only accounts listed here can complete the OAuth flow.

1. In the left sidebar, click **Audience**
2. Under **Test users**, click **Add users**
3. Enter the Gmail address you want to connect to n8n (e.g., `maitridj01@gmail.com`)
4. Click **Add**
5. Click **Save**

> **Note:** Up to 100 test users are allowed. Your app stays in Testing mode until you submit for Google verification (not required for development/internal use).

---

## Step 4 — Create OAuth Client Credentials

1. Go to **APIs & Services > Credentials** ([direct link](https://console.cloud.google.com/apis/credentials))
2. Click **+ Create credentials** > **OAuth client ID**
3. **Application type:** Select **Web application**
4. **Name:** `ireios-n8n-oauth`
5. **Authorized JavaScript origins:** (leave empty for now)
6. **Authorized redirect URIs:**
   - Click **Add URI**
   - Enter: `http://localhost:5678/rest/oauth2-credential/callback`
   - This is the callback URL n8n uses for local development
7. Click **Create**
8. **Immediately copy both values:**

| Field | Format | Example |
|-------|--------|---------|
| Client ID | `数字-字母.apps.googleusercontent.com` | `123456789-abc123.apps.googleusercontent.com` |
| Client Secret | `GOCSPX-字母数字` | `GOCSPX-abc123xyz789` |

> **Warning:** The Client Secret is only shown once. If you lose it, you must create a new OAuth client.

9. Click **OK** to close the modal

---

## Step 5 — Create Gmail Credential in n8n

1. Open n8n at `http://localhost:5678`
2. Go to **Credentials** (left sidebar)
3. Click **Add Credential** (top right)
4. Search for `Gmail OAuth2`
5. Select **Gmail OAuth2 API**
6. Fill in:
   - **Credential Name:** `Gmail account`
   - **Client ID:** paste from Step 4
   - **Client Secret:** paste from Step 4
7. Click **Save**
8. Click **Sign in with Google**
9. A new browser tab opens — select the Gmail account you added as a test user
10. Click **Continue** on the permission screen
11. Review the scopes (should include Gmail access)
12. Click **Continue** to grant access
13. Browser redirects back to n8n with a success message
14. Click **Save** again

### Verify connection

The credential should show a green indicator. If you see an error, see [Troubleshooting](#troubleshooting) below.

---

## Step 6 — Create Google Sheets Credential in n8n

> **One OAuth Client, multiple services.** You can reuse the same Client ID and Secret from Step 4.

1. In n8n, go to **Credentials** > **Add Credential**
2. Search for `Google Sheets`
3. Select **Google Sheets OAuth2 API**
4. Fill in:
   - **Credential Name:** `Google Sheets account`
   - **Client ID:** paste the same Client ID from Step 4
   - **Client Secret:** paste the same Client Secret from Step 4
5. Click **Save**
6. Click **Sign in with Google**
7. Select the same Gmail account
8. Grant Google Sheets access
9. Redirect back to n8n — success
10. Click **Save**

> **Why one credential works for both:** OAuth2 credentials are scoped by the APIs you enabled in Step 2. When you authorize, Google requests permission for all enabled scopes. The same Client ID can authenticate for Gmail, Sheets, Drive, Calendar, etc.

---

## Step 7 — Import IREIOS Workflows

With credentials created, import the 6 pre-built IREIOS workflows:

```powershell
# From the project root (venv active)
python import_n8n_workflows.py
```

This will:
1. Check n8n health at `http://localhost:5678`
2. Create 6 workflows from `n8n_workflows/*.json`
3. Activate each workflow
4. Print the webhook URLs

### Verify workflows

In the n8n UI, go to **Workflows**. You should see:

| WF | Name | Webhook Path | Status |
|----|------|-------------|--------|
| WF-1 | IREIOS — Hot Lead Alert → Gmail | `ireios_hot_lead_alert` | Active |
| WF-2 | IREIOS — Site Visit Fan-out → Gmail | `ireios_visit_fanout` | Active |
| WF-3 | IREIOS — HITL Manager Notify → Gmail | `ireios_hitl_notify` | Active |
| WF-4 | IREIOS — CRM Note → Google Sheets | `ireios_crm_append` | Active |
| WF-5 | IREIOS — Marketing Report → Gmail | `ireios_marketing_csv` | Active |
| WF-6 | IREIOS — DLQ Depth Monitor → Gmail | (cron, no webhook) | Active |

---

## Step 8 — Test the Connection

### Test Gmail (WF-1)

```powershell
python publish_stub_event.py --event-type lead.hot --tenant-id Client_1 --entity-id 1 --payload "{\"lead_id\":1,\"name\":\"Demo Lead\",\"phone\":\"+919999999999\",\"trigger\":\"hot_threshold\",\"score\":90,\"reason\":\"stub test\",\"chat_context\":\"User: hi\"}"
```

Check your Gmail inbox — you should receive a "Hot Lead Alert" email.

### Test Google Sheets (WF-4)

```powershell
python publish_stub_event.py --event-type lead.qualified --tenant-id Client_1 --entity-id 2 --payload "{\"name\":\"Sheet Test\",\"phone\":\"+918888888888\",\"location\":\"Baner\",\"budget\":\"50L\",\"property_type\":\"2BHK\",\"visit_date\":\"2026-08-01\"}"
```

Check your Google Sheet — a new row should be appended.

---

## Current Credential IDs (IRIOS Local)

These are the credential IDs in your local n8n instance. Reference these when editing workflow JSONs:

| Credential | Type | n8n ID |
|-----------|------|--------|
| IREIOS API Key | httpHeaderAuth | `G00Bi1IyHkT5zo68` |
| Gmail account | gmailOAuth2 | `13auoI7CTqojlGZh` |
| Google Sheets account | googleSheetsOAuth2Api | `wpcizRhlDTPwGFM8` |

> **Note:** These IDs are generated by n8n and may change if you delete and recreate credentials.

---

## Troubleshooting

### `redirect_uri_mismatch`

The redirect URI in Google Cloud Console doesn't match what n8n sends.

**Fix:** Copy the **OAuth Redirect URL** from the n8n credential panel and paste it *exactly* into Google Console's **Authorized redirect URIs**. Must include `http://localhost:5678/rest/oauth2-credential/callback`.

### `invalid_client`

Client ID or Secret doesn't match.

**Fix:** Go back to Google Cloud Console > Credentials, copy both values fresh, and re-enter in n8n. Watch for accidental spaces.

### `Access blocked: This app's request is invalid`

The OAuth consent screen is not configured or the app is in Testing mode and your account is not added as a test user.

**Fix:**
1. Go to **OAuth consent screen > Audience**
2. Add your Gmail address as a **Test user**
3. Try the OAuth flow again

### `403 access_denied` during OAuth

Same as above — your account is not in the test users list.

**Fix:** Add your email under OAuth consent screen > Test Users.

### Gmail node `options.attachments` not working

The Gmail node v2.1 in n8n v2.31.5 has a known issue with `options.attachments` — binary data is not attached to emails.

**Workaround (used in WF-5):** Build the MIME message in a Code node and send via Gmail API using an HTTP Request node. See `n8n_workflows/wf5_marketing_report.json` for the pattern.

### n8n shows "Connection tested successfully" but emails don't send

Check that:
1. The workflow is **Active** (toggle in top-right)
2. The Webhook node has the correct path
3. The bridge is forwarding events (`N8N_BRIDGE_ENABLED=true`)

### Token expired / credential needs re-auth

OAuth tokens can expire. In n8n:
1. Go to **Credentials**
2. Click the credential
3. Click **Sign in with Google** to re-authorize

---

## OAuth Scopes Reference

| Service | Scope | Purpose |
|---------|-------|---------|
| Gmail (full) | `https://mail.google.com/` | Send, read, modify, delete emails |
| Gmail (modify) | `https://www.googleapis.com/auth/gmail.modify` | Read + send (no delete) |
| Gmail (readonly) | `https://www.googleapis.com/auth/gmail.readonly` | Read only |
| Google Sheets | `https://www.googleapis.com/auth/spreadsheets` | Read/write spreadsheets |
| Google Drive | `https://www.googleapis.com/auth/drive.file` | Access files created by the app |

> **Recommended:** Use `https://mail.google.com/` for full Gmail access in automation workflows.

---

## Production Considerations

### App verification

In Testing mode, your app works for test users only. To use with any Google account:
1. Go to **OAuth consent screen > Audience**
2. Click **Publish App**
3. Submit for Google verification (takes 1–7 days)

> **For internal use:** You can stay in Testing mode and just add all required email addresses as test users.

### Token refresh

OAuth tokens expire. n8n automatically refreshes them using the refresh token obtained during the initial authorization flow. If refresh fails:
- Re-authorize the credential in n8n
- Check that the OAuth client is still active in Google Cloud Console

### Domain restriction

For Google Workspace accounts, you can set the consent screen to **Internal** to restrict access to your organization's users only.
