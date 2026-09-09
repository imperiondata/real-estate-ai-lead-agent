# Hardening Sprint — Access & Environment Request (Aritro + Maitri)

| This doc owns | Does not own |
|---|---|
| Everything Mayank must provide before live cert drills start | Cert procedures → `docs/PRODUCTION_HARDENING_SPRINT.md` |

**SoT:** `production/main` @ `a0a2a53` (Imperion repo) · **Work branch:** `cert-sprint`
**Status:** waiting on Mayank — no live load / webhook / eval / DR until this list is answered.

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

## 3. Ask checklist (tick on reply)

- [ ] (a) GitHub write: `Macmill-340` + `maitriishahh`
- [ ] (b) Vercel approvals: both emails
- [ ] (c) Render URL + team invite (API, Postgres, logs, snapshot)
- [ ] (d) n8n live URL + logins, WFs Published
- [ ] (e) Test-tenant API key + dashboard logins (secure channel)
- [ ] Flags confirmed on Render (`TEST_MODE=false`, `IS_PRODUCTION=true`, `FOLLOW_UP_TEST_MODE=false`)
- [ ] Twilio webhook target + replay plan (console read or Mayank-assisted)
- [ ] Redis confirmed company-hosted
- [ ] Gemini rate cap for the 100-eval
- [ ] (f) `/metrics` owner + scrape permission; isolation-test permission (read-only)
- [ ] (g) Snapshot owner for DR
- [ ] Maitri live-sender number + 100-eval client id + WF-1 Gmail To set

## 4. Blocked until answered

Live load (PH-A.2) · signed webhooks (PH-C.1) · 100-eval (PH-B) · n8n counts (PH-C.2) · DR (PH-A.3) · git push of `cert-sprint`.
Allowed now: tenant-log audit (PH-A.1, read-only, no live traffic).
