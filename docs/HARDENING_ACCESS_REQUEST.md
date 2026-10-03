# Hardening Sprint — Access & Environment Request (Aritro + Maitri)

| This doc owns | Does not own |
|---|---|
| Everything Mayank must provide before live cert drills start | Cert procedures → `docs/PRODUCTION_HARDENING_SPRINT.md` |

**SoT:** `production/main` @ `a0a2a53` (Imperion repo) · **Work branch:** `cert-sprint`
**Status:** UNBLOCKED 2026-09-11 — Mayank fulfilled (a)–(g). Live drills may start. Secrets stay out of git (password manager only).

---

## 1. Identities

| Person | GitHub | Vercel request email |
|---|---|---|
| Aritro | `Macmill-340` | `captainmacmill340@gmail.com` (already requested) |
| Maitri | `maitriishahh` | `maitrishah142004@gmail.com` (already requested) |

---

## 2. Message to Mayank (copy-paste as-is)

Hardening sprint — access and environment needed before live drills

I am on cert-sprint from production/main (a0a2a53). The sprint plan is committed locally (0afd84e) but I cannot push: git push to imperiondata/real-estate-ai-lead-agent returned 403 for GitHub user Macmill-340. Please add Macmill-340 and maitriishahh as write collaborators (or send invites) so we can push cert-sprint.

Vercel: the Production frontend is https://real-estate-ai-lead-agent-j330jhuc-imperion-s-projects1.vercel.app. It is team-protected. I requested access as captainmacmill340@gmail.com and Maitri requested as maitrishah142004@gmail.com — please approve both Vercel team requests.

GitHub Deployments only shows that Vercel URL (commits a0a2a53 and 5166055). I do not see a Render service on the repo. Please confirm:
1. Frontend = that Vercel URL (as-is).
2. Backend API + Postgres + Redis live on Imperion Render — send the Render service URL (e.g. https://….onrender.com) and invite us both to the Render team (or the project) so we can hit /health, read logs, and take the Postgres snapshot for the DR drill.
3. n8n live host URL + UI logins for us both (Published WFs; we need execution counts, not screenshots).

I also need, via a secure channel (not Slack/Git if possible):
- Dedicated test-tenant API key (not Client A prod traffic) for load + 100-eval, plus dashboard JWT logins on that tenant so Maitri can see leads.
- Confirmation TEST_MODE=false and IS_PRODUCTION=true on Render (Twilio signatures on), FOLLOW_UP_TEST_MODE=false.
- Twilio webhook currently configured for +1 (334) 731-7182 (should be https://<render-api>/api/v1/whatsapp).
- Twilio console read for us both, or you replay a duplicate MessageSid from the console while we watch logs.
- Confirmation Redis is the company instance (session_lock + n8n bridge depend on it).
- Gemini quota / max convos per hour so Maitri can rate-limit the 100 live turns.

Permissions:
- Who owns /metrics (public today) — firewall/allow-list, and may we scrape it during load?
- Is read-only gate_isolation_test.py allowed against live Postgres after load/DR (no wipes, ever)?
- Who takes the Render PG snapshot at DR time (me if invited, else you on call)?

Maitri-specific:
- Confirm she may text the live number from her phone (or assign a sandbox sender).
- Client id for the 100-eval (test tenant, not Client A).
- Stop-on-reply: prod follow-up gaps apply (not 1-min). Confirm proof = FollowUpState stopped after reply, not waiting Day 1–7 wall clock.
- n8n: WF-1 Gmail To already set so one lead.hot produces a real execution?

Coordination:
- DR window: not proposed yet. We will send a time after Render snapshot access exists; you and Maitri stay off the dashboard and 100-eval until I confirm restore. Snapshot first, then backup / fail / restore / verify Client A and B.
- No phase4_tests merge; no task3_runner vs live.

Until the Render API URL + GitHub write + test key are in, we will only run the tenant-log audit against the production/main tree (no live load, no webhook hammer, no DB restore).

Please reply with: (a) GitHub invites, (b) Vercel approvals, (c) Render URL + invite, (d) n8n URL + logins, (e) test API key path, (f) /metrics + isolation-test permissions, (g) Twilio replay plan.

---

## 3. Fulfillment (Mayank 2026-09-11 — public values only, no secrets)

| Ask | Result |
|---|---|
| (a) GitHub write | Invites sent to `Macmill-340` + `maitriishahh` — **accepted**; push `cert-sprint` |
| (b) Vercel | Hobby tier = 1 external collab → **Aritro approved**. Maitri uses live URL + Client B login. URL: `https://real-estate-ai-lead-agent-j330jhuc-imperion-s-projects1.vercel.app` |
| (c) Render | API: `https://real-estate-ai-lead-agent-21nh.onrender.com`. **Free tier = no dashboard snapshots → DR uses manual `pg_dump` / `pg_restore` via external DB URL.** External DB URL **received** (held off-repo; Render invites N/A on non-Pro). Notify Mayank before the window. |
| (d) n8n | Live cloud: `https://imperiondata.app.n8n.cloud`. WF-1…WF-6 imported, authenticated, Published. **Corrected owner login received and verified working (held off-repo, never git).** |
| (e) Test tenant | **Client B** for load + 100-eval. Live `api_key` **received** (held off-repo). Note: no "Generate key" UI exists (`/settings` = profile/notifications only). |
| Flags | Live: `TEST_MODE=false`, `IS_PRODUCTION=true`, `FOLLOW_UP_TEST_MODE=false` |
| (f) Metrics/isolation | `/metrics` scrape allowed during load. Read-only `gate_isolation_test.py` vs live allowed. |
| Twilio replay | Mayank triggers duplicate from Meta/Twilio console — **ping him when PH-C starts** |
| Redis | Company-hosted — confirmed |
| (g) Maitri | Cleared to text live number. Client B tenant. Proof = `FollowUpState` stopped. WF-1 Gmail recipient set. Gemini: rate-limited, avoid 429 skew. |

## 4. Ask checklist (tick on reply)

- [x] (a) GitHub write: `Macmill-340` (accepted) + `maitriishahh` (invite sent)
- [x] (b) Vercel: Aritro approved; Maitri via live URL + Client B login
- [x] (c) Render API URL + external DB URL received (off-repo); invites N/A on non-Pro
- [x] (d) n8n URL + working owner login received (off-repo)
- [x] (e) Tenant = Client B; live `api_key` received (off-repo)
- [x] Flags confirmed on Render (`TEST_MODE=false`, `IS_PRODUCTION=true`, `FOLLOW_UP_TEST_MODE=false`)
- [x] Twilio replay plan: Mayank-assisted (ping at PH-C)
- [x] Redis confirmed company-hosted
- [x] Gemini rate cap guidance for the 100-eval
- [x] (f) `/metrics` scrape + read-only isolation test allowed
- [x] (g) DR = manual `pg_dump`/`pg_restore` (no snapshot on Free tier)
- [x] Maitri live-sender + Client B + WF-1 Gmail To set

## 5. Run state (2026-09-11)

**Run order:** PH-0 (`/health` + env sheet) → PH-A.1 (log audit) → PH-C (**ping Mayank** for Twilio replay; n8n UI exec count = 1) → PH-A.2 ∥ PH-B (Client B, rate-limited) → PH-A.4 → PH-R.

**PH-A.3 DR:** credentials exist — **do not run until you send Mayank a window notice** (he asked to be notified; Maitri quiet; `DATABASE_URL` = local export only).

**Note:** `https://real-estate-ai-lead-agent-21nh.onrender.com/dashboard` is the product CRM, not the Render control plane.
