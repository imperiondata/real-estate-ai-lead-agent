# Production Hardening Sprint — Live IREIOS 3.0 Certification

| This doc owns | Does not own |
|---|---|
| Certify live `production/main` (IREIOS 3.0) as-is: Aritro backend cert, Maitri 100-eval, joint Twilio/n8n drill; exit = two cert reports | Order / gates → `plans/UNIFIED_EXECUTION_ORDER.md` |
| | Phase 4 / `phase4_tests` work (banned this sprint — do not merge) |
| | Day-to-day maintenance → `MAINTENANCE.md` |

**Status legend:** `[ ]` pending · `[~]` in progress · `[x]` done · `[-]` skipped (reason required)
**Date:** 2026-09-09 · **Branch of record:** `production/main` @ `a0a2a53` (Imperion repo, live on Render) · **Work branch:** `cert-sprint`
**Owners:** PH-A Aritro · PH-B Maitri · PH-C joint · sign-off Mayank
**Exit gate:** Appendix A (Backend Production Certification) + Appendix B (AI & Automation Certification) filled with evidence → **blocks P4-QA/REL**

**Prerequisite:** G1/G2/G3 green; G4 bridge done, WF-1 pending (`plans/UNIFIED_EXECUTION_ORDER.md`). This sprint proves the functionally complete MVP for real client onboarding.

---

## 0. Current blockers (2026-10-01 — new sessions read this first)

Prior blockers are **resolved** (Mayank 2026-09-11; secrets held off-repo, never in git):

| # | Was blocked on | Status |
|---|---|---|
| 1 | n8n login (`incorrect username or password`) | **Resolved** — corrected owner login works |
| 2 | Client B `api_key` (no dashboard "Generate key" UI) | **Resolved** — live key received, Client B for all live traffic |
| 3 | External Postgres URL for DR | **Resolved** — URL received; Render invites N/A on non-Pro workspaces |

**Done:** PH-0 `[x]` · PH-A.1 `[x]` · PH-C `[x]` 2026-09-17 (WF-1 exec 719; Cases 1–4; Case 4 exec 722 +0) · PH-A.2 `[x]` 2026-09-17 (25/50 0-drop; 100 ReadTimeout cliff) · **PH-B `[x]` 2026-09-17 (100 convos, 138 turns, all 200 0-drop; B.2 8/8 STOP + handoff; `reports/PH-B-100-EVAL-REPORT.md`)**.

**As of 2026-10-01 (no task flipped `[x]`):**

| # | Blocker | Status |
|---|---|---|
| 4 | n8n Cloud trial | **Resolved** — workspace upgraded and active. WF-1..5 published. WF-6 stays **unpublished** on purpose (15-minute cron). Do not publish it for these proofs. |
| 5 | WF-4 sheet-row proof | **n8n proven, Sheet1 is Mayank** — 2026-10-02 wrong token **403**. One `lead.qualified` stub **200**, `event_id` `1d9ff9f8-7a69-434d-b98e-97adcc40aef0`, `entity_id` `sheet-test-live-20261002`, `tenant_id` `Client_3`. WF-4 exec **859** Success (Oct 2, 23:15:20, 5.458s). Pin proofs 856/857/858 stay separate. Sheet1 row is Mayank's check. Do not fire a second stub. |

Cloud UI already done (not in repo JSON): WF-1/2/3 CRM links → verified Vercel base; WF-4 native Append node published; six payload expressions corrected (`$json.payload.name` and the same for phone/location/budget/property_type/visit_date; top-level `timestamp`/`tenant_id`/`entity_id` left as bracket keys). Live Sheet1 row is Mayank's check (exec 859). Pin append was already proven by exec 858.

### Oct 2 directive (Mayank 2026-10-01, due 2026-10-02 EOD)

Not a cert `[x]`. Sync with Aritro before the n8n check is coded. He runs the cross-tenant API test after both confirm production is live.

| Owner | Task |
|---|---|
| Aritro | Tenant context, Postgres `client_id` audit, and tagged-RAG filter are **coded on `cert-sprint` @ `bcf0f24`**. Mayank reported 2026-10-03 that this branch was merged to `main` and Render built it. SHA not re-read here. See Appendix A.1. |
| Maitri | n8n Tenant Gate **done 2026-10-01** on WF-1..WF-5 (cloud UI, `^Client_[0-9]+$`, false → Stop and Error; WF-2 gate renamed to `Tenant Gate`). Manual-pin proofs on WF-4: reject exec **856** (Error), accept exec **857**, full accept exec **858** (Sheet1 row appended). Live stub path is exec **859** Success (row 5). Sheet1 for that run is Mayank's check. |

Known bug, report only, do not fix in this pass: dashboard priority cards keep the first 3 hot leads after claim (`frontend/src/app/(dashboard)/dashboard/page.tsx:127-129`). Claim sets `conversion_status` but the widget does not drop claimed rows.

**Later — do not start in a new session until the blocker clears:**

- WF-4 live stub is done (row 5): HTTP 200, exec **859** Success. Sheet1 row for `Live Stub Test` is Mayank's check. Do not fire a second stub.
- PH-A.3 DR done 2026-10-03. Appendix A.3. Do not re-run. Dump stays off-repo until sign-off.
- PH-R signs and Aritro checkboxes. After cert and the Oct 2 task. Do not flip `[x]` early.
- Claim widget. Report only. Do not fix.
- WF-6. Leave unpublished (15-minute cron).
- Do not import `n8n_workflows/*.json` (would revert the live Append node and CRM links).
- Deploy: Mayank reported 2026-10-03, before this DR window, that `cert-sprint` was merged to `main` and Render built the new image. This session did not re-read that git SHA.

**Still later (do not mix into this commit's live work):**
- **PH-B** — Maitri 100 live WA, Client B, rate-limited (Appendix B.1/B.2) `[x]` 2026-09-17 — see B.1/B.2 + `reports/PH-B-100-EVAL-REPORT.md`
- **PH-A.3** — `[x]` 2026-10-03. Appendix A.3. Do not re-run.
- **PH-A.4** — repo grep + live flags
- **PH-R** — remaining appendix cells + signs

Render curls use `LIVE_*` in local `.env` (not `DATABASE_URL` / local `N8N_*`). No docker/uvicorn for live cert.

---

## 1. Hard rules

1. **Certify the live deploy as-is.** `production/main` @ `a0a2a53` only. **Do not merge `phase4_tests`. No new AI agents. No Digital Twin expansion** (Piyush final rule).
2. **Serial order:** PH-0 → PH-A.1(audit) → PH-C → (PH-A.2 ∥ PH-B) → PH-A.3 → PH-A.4 → PH-R. PH-C before the 100-eval so duplicates do not contaminate NLP evidence.
3. **Real Twilio, real signatures.** Live number `+1 (334) 731-7182`. Duplicate = resend the same webhook with a valid `X-Twilio-Signature` (computed with the auth token — that is authentication, not a bypass). **`TEST_MODE=true` is forbidden for cert evidence.**
4. **Live n8n mandatory.** Execution counts from the n8n UI. Unit mocks (`test_e20_n8n_bridge.py`) are supporting evidence only.
5. **DR on hosted Render PostgreSQL only.** Manual `pg_dump` off-box **first** (Free tier: no dashboard snapshots; protects seeded Client A/B), then backup → failure sim → restore → verify. Maintenance window agreed with Mayank + Maitri; no dashboard/eval traffic during the window. **No local `pg-staging`.**
6. **`task3_runner.py` is not a prod command.** Do not run it against the live deploy (Gemini quota + not the webhook race path). As-is cert: no tree changes for it.
7. **Tenant isolation never regresses** — `python gate_isolation_test.py` after load and after DR (read-safe checks against prod only with Mayank's OK; never wipe prod traffic tables).
8. **As-is means as-is.** PH-A.1 is an **audit** of the logs `production/main` already emits. No product code deploy from cert findings unless Mayank explicitly asks after the report.

---

## 2. Locked decisions (Mayank — Option 1)

| Topic | Decision |
|---|---|
| SoT | `production/main` (Imperion `imperiondata/real-estate-ai-lead-agent`) @ `a0a2a53` — PR #11 + Client B seed. Reports describe **this tree only**. |
| Out of scope | `phase4_tests` merge, twin, new agents, 4.0 APIs |
| Deploy | Live Render API + Vercel + Redis + Twilio `+1 (334) 731-7182`. Local docker ≠ cert target. |
| Load | HTTP 25 / 50 / 100+ vs **live** API; latency + drop rates. Gemini budget: HTTP load, not 100 live LLM blasts |
| Twilio | Real signatures; deliberate same-webhook resend; duplicate handling verified |
| n8n | Live workflow + scheduler execution proof required |
| DR | Hosted Render PG; manual `pg_dump`/`pg_restore` (Free tier, no snapshots); maintenance window with Mayank + Maitri |
| Gates | Sprint **blocks** P4-QA/REL |
| Owners | Aritro Appendix A (security, load, DR, logs) · Maitri Appendix B (100-eval, compliance, stop-on-reply) · joint PH-C |

---

## 3. Master sequence

| Step | Unit | Summary | Exit gate | Owner | Status |
|---:|---|---|---|---|---|
| **PH-0** | Prep | Record live env (Render URL, flags, Twilio, n8n, HEAD) | Env sheet in Appendix A | Both | `[x]` 2026-09-15 — /health 200, A.0 filled |
| **PH-A.1** | Tenant-log audit | Inventory `tenant_id_ctx` coverage on jobs / APIs / queues | Gap table in Appendix A | Aritro | `[x]` 2026-09-15 — 5 set sites, 10 gaps, no patches |
| **PH-C** | Joint drill | Signed duplicate / simultaneous / retry webhooks + live n8n single-fire | Matrix §C all PASS | Aritro+Maitri | `[x]` 2026-09-17 — `reports/PH-C.1-CASES1-3-REPORT.md` |
| **PH-A.2** | Load | 25 / 50 / 100 concurrent vs live: latency + drop rates | Numbers table in Appendix A | Aritro | `[x]` 2026-09-17 — 25/50 0-drop; 100 cliff |
| **PH-B** | 100-eval | 100 fresh live WhatsApp convos + stop-on-reply / fallback / opt-in | JSON + summary in Appendix B | Maitri | `[x]` 2026-09-17 — 138 turns all 200 0-drop; `reports/PH-B-100-EVAL-REPORT.md` |
| **PH-A.3** | DR | Manual `pg_dump` → fail → `pg_restore` → verify on hosted Render PG | Appendix A §DR | Aritro | `[x]` 2026-10-03 — counts matched; post-resume chat 200 |
| **PH-A.4** | Security | Live secrets / flags / auth / `/metrics` audit | Appendix A §Security | Aritro | `[ ]` |
| **PH-R** | Reports | Fill Appendices A+B, Mayank sign-off | UNIFIED **PH** → `[x]` | Both | `[ ]` |

PH-A.2 ∥ PH-B allowed after PH-C. Everything else serial.

---

## 4. Dependency matrix

| Dependent | Blocked by | Clears |
|---|---|---|
| Joint drill PH-C | PH-0 env sheet (live URLs, keys, HEAD) | PH-C |
| Load PH-A.2 | PH-C (dedupe proven first) + dedicated test tenant | Appendix A load |
| 100-eval PH-B | PH-C + rate-limit plan (clean corpus on live) | Appendix B |
| DR PH-A.3 | Maintenance window on calendar + external DB URL + off-box `pg_dump` | Appendix A DR |
| Reports PH-R | All above + isolation re-run | Gate input |

---

## PH-0 — Prep

### Task PH-0.1 — Record the live env
- **Files:** none (evidence only)
- **Steps:**
  1. Confirm deploy tracks `production/main` @ `a0a2a53`. Live env (Mayank 2026-09-11): API `https://real-estate-ai-lead-agent-21nh.onrender.com`, Vercel `https://real-estate-ai-lead-agent-j330jhuc-imperion-s-projects1.vercel.app`, n8n `https://imperiondata.app.n8n.cloud`, Twilio `+1 (334) 731-7182`, company Redis. Test tenant = **Client B** (`api_key`: ask Mayank — seed-time value, no dashboard "Generate key" UI on this tree).
  2. Record live flags: `TEST_MODE=false` (signature enforced), `IS_PRODUCTION=true`, `FOLLOW_UP_TEST_MODE=false`, `FOLLOWUP_ENGINE=v3`, `FEATURE_WHATSAPP_V3=true`.
  3. Confirm Client A + Client B seeded (isolation-safe read check only).
  4. `curl https://real-estate-ai-lead-agent-21nh.onrender.com/health` → 200.
- **Test:** `/health` 200 on the live host
- **Done:** Env sheet pasted into Appendix A header
- **Rollback:** N/A
- **Status:** `[x]` 2026-09-15

---

## PH-A.1 — Tenant-log audit (Aritro, read-only)

### Task PH-A.1.1 — Inventory `tenant_id_ctx` coverage
- **Files (reference, do not change):**
  - Set today: `auth.py` (per-client), `app/api/events.py`, `follow_up.py:388`, escalation loop in `main.py`, `app/workflows/followup_scheduler.py:87`, middleware `main.py:530` (`"Pending"`)
  - Check: `EventBusClient._dispatch`, `CEOOrchestrator.handle_event`, `N8NBridge._handle_message`, `ExecutionEngine.dispatch`, `crm_resync_job`, `competitor_monitor_job`, `weekly_marketing_cron_job`, `expire_stale_approvals`, `daily_cleanup_job`, `backup_postgres`
  - Filter: `main.py` `SecurePIILogFilter` (`[Req: …] [Tenant: …]` + phone/email masking)
- **Steps:**
  1. For each job/queue path, trigger or inspect one live log line; record whether it carries `[Tenant: Client_N]` / `[Tenant: ops]` or falls back to `"None"`/`"Pending"`.
  2. Record gaps in the Appendix A table with file:line. **Do not patch prod code in this sprint** — findings go to Mayank for a post-cert decision.
- **Test:** N/A (audit)
- **Done:** Gap table complete with log excerpts
- **Rollback:** N/A
- **Status:** `[x]` 2026-09-15

---

## PH-C — Joint Twilio + n8n drill (Aritro + Maitri, coordinate window)

### Task PH-C.1 — Signed duplicate / simultaneous / retry webhooks
- **Files (reference):** `main.py` (`WebhookLog` insert-first, `interim_sent:{MessageSid}` TTL, `_session_turn_locked`, `_await_inflight_and_push`), `agent.py` (`_has_recent_duplicate_message`), `tests/test_p3_concurrency.py` (source baseline — now prove live)
- **Steps:**
  1. Live number, `TEST_MODE=false`. Compute a valid `X-Twilio-Signature` per request (Twilio helper + auth token).
  2. Case 1 — duplicate `MessageSid`: POST the **same signed webhook twice** to live `/api/v1/whatsapp`. Expect: first processes, second returns empty `<Response></Response>`; one Gemini turn; one `WebhookLog` row.
  3. Case 2 — simultaneous, same `From`, different Sids: parallel signed POSTs. Expect: `session_lock:{session_id}` serializes; no interleaved mid-Gemini replies.
  4. Case 3 — Twilio retry: repeat the same signed Sid after a delay. Expect: idempotent, no second turn.
  5. Per case record: HTTP code, TwiML vs empty vs interim, Gemini turns, `WebhookLog`/`Message` row counts.
- **Test:** `pytest tests/test_p3_concurrency.py -v` (supporting) + `python gate_isolation_test.py` (read-safe)
- **Done:** Case table with counts in both appendices
- **Rollback:** N/A (proof; use a dedicated test tenant, not Client A prod traffic)
- **Status:** `[x]` 2026-09-17 — Cases 1–4 PASS (`reports/PH-C.1-CASES1-3-REPORT.md`)

### Task PH-C.2 — Live n8n single-fire proof
- **Files (reference):** `app/automation_engine/n8n_bridge.py` (`DEFAULT_WEBHOOK_MAP`, catalog `lead.hot` only — never alias `lead.escalated` alongside), `app/events/lead_hot.py`, `docs/N8N_INTEGRATION.md`, `tests/test_e20_n8n_bridge.py` (supporting only)
- **Steps:**
  1. Fire **one** `lead.hot` on live. Assert n8n WF-1 executes **once** (execution count from the n8n UI, not a mock).
  2. Assert alias `lead.escalated` does **not** fire a second workflow.
  3. Assert bridge and AE `template_type="n8n"` are not both armed for the same alert (else double Gmail).
  4. Repeat the duplicate-Sid case with the bridge on; n8n execution count stays 1.
- **Test:** `python -m pytest tests/test_e20_n8n_bridge.py -q` (supporting)
- **Done:** n8n UI execution counts pasted into both appendices; double-fire = FAIL, stop drills, report to Mayank
- **Rollback:** `N8N_BRIDGE_ENABLED=false` to isolate if it blocks
- **Status:** `[x]` 2026-09-17 — WF-1 exec 719; Case 4 exec 722 then +0

---

## PH-A.2 — Load 25 / 50 / 100 (Aritro, live)

### Task PH-A.2.1 — Concurrency vs live API
- **Files (reference):** `docs/TIMEOUTS_AND_TIMINGS.md` (13s race, 22s LLM cap), `wa_sse_smoke.py` (turn baselines)
- **Steps:**
  1. `python load_chat_concurrency.py --leg 25|50|100` against `LIVE_API_BASE_URL` + `LIVE_CLIENT_B_KEY` (local `.env`; never swap `DATABASE_URL`). Neutral `/api/v1/chat` (no human-agent phrase).
  2. Warm `/health` first (Render Free sleep). Legs 25 → 50 → 100 concurrent.
  3. Record p50/p95, 5xx, drops. Isolation = live SQL `client_id=3` only — **do not** run `gate_isolation_test.py` vs prod (it posts to localhost and writes a lead).
- **Test:** live SQL isolation (0 rows with load session + `client_id <> 3`)
- **Done:** Appendix A.2 filled
- **Rollback:** N/A; stop legs if live users impacted
- **Status:** `[x]` 2026-09-17 — 25/50 all 200 0-drop; 100 ReadTimeout cliff (49/100 persisted)

---

## PH-B — Fresh 100-conversation eval (Maitri, live)

### Task PH-B.1 — 100 fresh live WhatsApp conversations
- **Files (reference):** `tests/test_p0_safety.py` (opt-out), `tests/test_p2_fsm_language.py` (language gate)
- **Steps:**
  1. 100 **fresh** conversations on the live number (no `seed_dummy_leads.py` / demo reuse), **rate-limited** for Gemini quota. Unique sessions.
  2. Coverage: Hindi (Devanagari) · Hinglish · typos · budget change mid-thread (last-wins) · location switch · vague visit date · STOP / "don't message" · empty / greeting-only · mixed-language · HOT escalation-worthy.
  3. Per convo record: turns, replies, `Lead` extraction (location/budget/property_type/name/phone/visit_date), temperature, fallback hits, error phrases.
  4. Language rule: English by default; Hinglish only after the user initiates.
  5. **Do not run `task3_runner.py` against prod.**
- **Test:** `pytest tests/test_p0_safety.py tests/test_p2_fsm_language.py -v` (supporting)
- **Done:** Pass-rate table by category + FAIL triage in Appendix B; artifact paths recorded
- **Rollback:** N/A
- **Status:** `[x]` 2026-09-17 — 100 convos / 138 turns all 200 0-drop; report `reports/PH-B-100-EVAL-REPORT.md`

### Task PH-B.2 — Stop-on-reply + fallback + opt-in proof (live)
- **Files (reference):** `app/intelligence/push_wait_engine.py` (`replied` → `stop_followups`), `follow_up.py` opt-out skip, `agent.py` `is_opt_out_message`
- **Steps:**
  1. Stop-on-reply: arm Day-0 follow-up, then user replies → assert scheduler skips/stops (no further auto nudges).
  2. Fallback: force Gemini failure/timeout → assert safe template reply, no error-phrase leak, DLQ row only where specified.
  3. Opt-in: STOP variants → `whatsapp_opt_in=False`, session closed, no re-arm while opted out.
- **Test:** `pytest tests/test_p0_safety.py tests/test_e4_followup.py -v` (supporting)
- **Done:** Three mini-tables with DB/log evidence in Appendix B
- **Rollback:** N/A
- **Status:** `[x]` 2026-09-17 — stop-on-reply Day-0 +30m no-spam; fallback not forced (1 interim + 0 leaks); 8/8 STOP closed+opt-out

---

## PH-A.3 — Disaster recovery drill (Aritro, maintenance window)

### Task PH-A.3.1 — Backup → fail → restore → verify (hosted Render PG, Free tier: manual `pg_dump` / `pg_restore`)
- **Files (reference):** `docs/BACKUP_RESTORE_DRILL.md` (procedure + 7-table check), `docs/MAINTENANCE.md` §4–5, `db_backup.py`, `db_restore.py`
- **Steps:**
  1. **Window first:** propose exact time to Mayank; confirm Maitri runs nothing during it. Record the window in Appendix A.
  2. **Manual `pg_dump`** via the external DB URL (Free tier has no dashboard snapshots). Copy the dump off-box; record artifact + size + time. This dump **is** the rollback — keep it until sign-off.
  3. `python db_backup.py` with prod `DATABASE_URL` as a second artifact (belt-and-suspenders). Record artifact + size.
  4. Failure sim: stop/restart Render web and/or break DB connectivity; record `/health` + chat behavior with timestamps.
  5. Restore hosted PG via `pg_restore` / `db_restore.py` from the step-2 dump; record which path was used + log.
  6. Verify: Client A/B rows, 7-table counts (`clients`, `sessions`, `leads`, `messages`, `event_logs`, `follow_up_states`, `dlq_events`), one real WA turn on the live number, isolation check.
  7. Record observed RTO/RPO + off-box backup gap.
- **Test:** `python gate_isolation_test.py` · `python gate_dlq_drill.py` + `dlq_replay.py` (post-restore, Mayank's OK)
- **Done:** Appendix A §DR filled (window, dump artifact, backup artifact, kill log, restore log, counts, RTO/RPO)
- **Rollback:** The step-2 `pg_dump` **is** the rollback; keep it until sign-off
- **Status:** `[x]` 2026-10-03

---

## PH-A.4 — Security / secrets audit (Aritro, live)

### Task PH-A.4.1 — Audit live posture
- **Files (reference):** `AGENTS.md` (auth layers), `docs/BACKEND_RELIABILITY_CHECKLIST.md`, `.env.example`
- **Steps:**
  1. Confirm no secrets / demo keys in tracked files; `.env*` gitignored; `frontend/src` free of `secret-client-key-123`.
  2. Verify three auth layers live: API key (ingest), JWT Bearer-or-cookie (dashboard), `X-Admin-Key` on ROI/pipeline (admin-only, no client exposure).
  3. Verify Twilio signature enforced (`TEST_MODE=false`); drill flags off for prod (`FOLLOW_UP_TEST_MODE`, `FOLLOW_UP_DLQ_TEST`).
  4. `/metrics` exposure → firewall/allow-list note + owner (Mayank).
  5. Default `ADMIN_API_KEY` rejected at boot (`main.py:verify_admin_key`).
- **Test:** `pytest tests/test_f4_jwt_auth.py -v` where applicable on this tree + manual 401-unauth check
- **Done:** Appendix A §Security ticked with evidence
- **Rollback:** N/A (audit; flag flips are a deploy decision, not this doc)
- **Status:** `[ ]`

---

## PH-R — Reports + sign-off

### Task PH-R.1 — Fill certs, hand to Mayank
- **Files:** this doc Appendices A+B
- **Steps:**
  1. Aritro fills Appendix A; Maitri fills Appendix B (numbers, not adjectives).
  2. Both record HEAD (`production/main` @ `a0a2a53` + any cert-branch doc commits), env, artifact paths, FAIL triage with file:line.
  3. Mayank signs; UNIFIED **PH** → `[x]`; open FAILs become tracked issues.
- **Done:** Two reports complete; gate input ready
- **Status:** `[ ]`

---

## 6. Rollback / emergency

| Problem | Action |
|---|---|
| Load impacts live users | Stop legs immediately; report; resume in window |
| n8n double-fires | `N8N_BRIDGE_ENABLED=false`; fix map (catalog only); re-run PH-C.2 |
| DR restore fails | Restore is from the Render snapshot; retry; escalate Mayank; keep snapshot |
| 100-eval pollutes prod leads | Dedicated test tenant only; tag and close test sessions after |
| Live DB drill overruns window | Abort to snapshot restore; reschedule with Mayank + Maitri |

---

## 7. Pointers

| Need | Path |
|---|---|
| Order / gates | `plans/UNIFIED_EXECUTION_ORDER.md` |
| Timeouts map | `docs/TIMEOUTS_AND_TIMINGS.md` |
| Wipes / scheduler ops (non-prod) | `docs/MAINTENANCE.md` |
| Backup/restore base | `docs/BACKUP_RESTORE_DRILL.md` |
| Reliability baseline | `docs/BACKEND_RELIABILITY_CHECKLIST.md` |
| n8n arch | `docs/N8N_INTEGRATION.md`, `docs/N8N_GOOGLE_CREDENTIALS_SETUP.md` |
| Evidence | `plans/IREIOS_3.0_EVIDENCE_PACK.md` |
| Access request (blocks live drills) | `docs/HARDENING_ACCESS_REQUEST.md` |

---

## Appendix A — Backend Production Certification Report (Aritro)

**HEAD at cert start:** `production/main` @ `a0a2a53` · **Live API:** `https://real-estate-ai-lead-agent-21nh.onrender.com` · **DR window:** 2026-10-03 13:16Z–13:30Z

### A.0 Env sheet (PH-0) `[x]` 2026-09-15

| Field | Value |
|---|---|
| HEAD | `production/main` @ `a0a2a53` · work branch `cert-sprint` |
| Live API | `https://real-estate-ai-lead-agent-21nh.onrender.com` |
| Vercel | `https://real-estate-ai-lead-agent-j330jhuc-imperion-s-projects1.vercel.app` |
| n8n | `https://imperiondata.app.n8n.cloud` (Trial; WF-6 Fetch Metrics mis-pointed — see PH-C notes) |
| Twilio | `+1 (334) 731-7182` |
| Redis | company-hosted (confirmed) |
| Tenant | Client B (key off-repo) |
| Flags (Mayank) | `TEST_MODE=false`, `IS_PRODUCTION=true`, `FOLLOW_UP_TEST_MODE=false` |
| `/health` | **200** in 7.0s (cold start; first 60s attempt timed out, retry OK): `{"status":"healthy","database_postgres":"connected","cache_redis":"connected","provider_twilio":"configured","provider_gemini":"configured","scheduler":"running","uptime_seconds":11}` |
| `/health` recheck | **2026-09-24** HTTP 200, same healthy body, `uptime_seconds` 12 (cold start). Does not replace the 2026-09-15 row. Does not prove WF-4 or a backend URL deploy. |
| `/health` recheck | **2026-10-01** HTTP 200, same healthy body, `uptime_seconds` 12986. Does not prove WF-4. |
| `/health` recheck | **2026-10-03** 13:30:51Z HTTP 200 after DR resume, postgres connected, scheduler running. One Client B chat 200, `client_id` 3. |
| `/metrics` | **200**, 4662 bytes, 0.9s (scrape allowed) |
| Client A/B seeded | Client B dashboard reachable (CRM renders); no wipes performed |

### A.1 Tenant-log audit `[x]` 2026-09-15 audit; 10 gaps patched on `cert-sprint` @ `bcf0f24` (Mayank reported the merge live 2026-10-03; SHA not re-read)
| Job / path | Emits `[Tenant: …]`? | Evidence / gap (file:line) |
|---|---|---|
| Request auth | Yes | `auth.py:65,88`, `app/api/events.py:62,77` |
| `follow_up` scheduler | Yes | `follow_up.py:388`, `followup_scheduler.py:87` (via `_tenant_ctx` alias) |
| Escalation loop | Yes | `main.py:271,298,326` |
| Middleware default | `Pending` until auth | `main.py:530`; filter reads at `main.py:201` (`SecurePIILogFilter`) |
| Bus `_dispatch` / CEO `handle_event` | **Yes** — `use_tenant` from envelope `tenant_id`, reset in `finally` | `event_bus_client.py` `_dispatch`, `ceo_orchestrator.py` `handle_event` |
| `N8NBridge._handle_message` | **Yes** | `n8n_bridge.py` — set before scoped handler, including ack paths |
| `ExecutionEngine.dispatch` | **Yes** | `execution_engine.py` `dispatch` — `action_request["tenant_id"]` |
| `crm_resync_job` | **Yes** — per lead | `crm_sync.py` `Client_{lead.client_id}` |
| `competitor_monitor` / weekly marketing | **Yes** — per client | `competitor_monitor.py`, `weekly_marketing_cron.py` |
| `expire_stale_approvals` | **Yes** — per row | `engine.py` `Client_{row.client_id}` |
| `daily_cleanup` / `nightly_backup` | **Yes** — `"ops"` | `main.py` `daily_cleanup_job`, `db_backup.py` `backup_postgres` |

`follow_up.py:388` already sets `Client_{state.client_id}` and still does not reset. Left as-is.

**Postgres API audit (2026-10-01):** client dashboard routes, including ROI (`main.py:1330`, `1360`, `1388`, `1413`), already filter `client_id`. No new client-facing filter added. Exceptions left in place: `app/api/lifecycle.py:104` (admin token, lead by id), `main.py:1241` (Twilio status callback by `MessageSid`), `daily_cleanup_job` (ops delete of rows older than 90 days). Internal PK lookups (`notification_service.py`, `crm_sync.py`, `crm_executor.py`) are not client APIs.

**Vector retrieval:** `data/faq.json` has no `client_id` (shared catalog). `rag.retrieve` drops a hit only when the chunk has `client_id` and it does not match the caller. Untagged FAQ rows stay visible. `agent.py` passes `lead.client_id`.

### A.2 Load — 25 / 50 / 100 concurrent (live) `[x]` 2026-09-17
Target: `POST /api/v1/chat` Client B (`LIVE_*`). Warm `/health` 200 (uptime 785s).

| Leg | p50 | p95 | 5xx | Drops | HTTP 200 | Verdict |
|---|---|---|---|---|---|---|
| 25 | 15.0s | 15.0s | 0 | 0 | 25/25 | PASS 0-drop; p95 above draft 13s (live Gemini) |
| 50 | 22.3s | 23.2s | 0 | 0 | 50/50 | PASS 0-drop; p95 above draft 15s |
| 100 | 60.4s | 60.4s | 0 | 100 | 0/100 | CLIFF — client `ReadTimeout` 60s; 49/100 leads still persisted |

Isolation: 124 load leads all `client_id=3`; `non_client_b=0`. Report: `reports/PH-A.2-LOAD-REPORT.md`. Raw JSON gitignored. Harness: `load_chat_concurrency.py`.

### A.3 Disaster recovery (hosted Render PG) `[x]` 2026-10-03
| Step | Evidence |
|---|---|
| Window (Mayank + Maitri confirmed quiet) | Mayank 2026-10-03: queue cleared, web service suspended on request, resumed only after the count match. Database was not suspended. |
| Manual `pg_dump` artifact + size + time (rollback copy) | `backup_20261003_131629_a.sql`, 948128 bytes, 13:16:29Z. Off-repo `dr_dumps/`. Contains `CREATE TABLE` for `clients`. Not in git. |
| `db_backup.py` artifact + size | Not used. That script reads `DATABASE_URL`. Second copy is `backup_20261003_131629_b.sql`, same size, same flags (`--no-owner --no-privileges --clean`) against `LIVE_DATABASE_URL`. |
| Failure sim log (`/health` + chat) | Web service suspended. 13:19:28Z `GET /health` **503**. 13:19:30Z `POST /api/v1/chat` **503**. |
| Restore path (`pg_restore` / `db_restore.py`) + log | `psql -f backup_20261003_131629_a.sql` on `LIVE_DATABASE_URL`. Start 13:19:33Z. Exit 0. `db_restore.py` not used. |
| Client A/B + 7-table counts | Before dump and after restore: clients 3, sessions 235, leads 235, messages 880, event_logs 663, follow_up_states 235, dlq_events 1057. Client ids 1, 2, 3. |
| Post-restore live WA turn + isolation + DLQ | No WhatsApp turn. No `gate_isolation_test.py` (it writes to localhost). No `dlq_replay.py`. Agreed check: 13:30:51Z `GET /health` **200** in 1.0s, postgres connected. 13:30:52Z one `POST /api/v1/chat` **200** in 1.1s, `client_id` 3, session `dr-restore-20261003`. That chat is after the count match, so it is not in the 235. |
| Observed RTO / RPO + off-box gap | Restore exit 0 on the first try; counts matched before resume. Service RTO: confirmed down 13:19:28Z, health 200 at 13:30:51Z after Mayank resumed. RPO: dump 13:16:29Z to confirmed down 13:19:28Z. Writes in that gap would have been replaced by the dump. Off-box copies stay until sign-off. |

### A.4 Security / secrets (live)
Repo pass 2026-09-24 plus live probes 2026-10-01. Task stays `[ ]`. Aritro sign stays blank.

| Check | Result |
|---|---|
| No secrets / demo keys in git; `.env*` ignored; `frontend/src` clean | Partial. `.gitignore` ignores `.env` and `frontend/.env`. Demo key in docs (`AGENTS.md`) is an example, not a live secret. **Not clean:** `frontend/src/app/(command-center)/sales-copilot/page.tsx:28` and `dashboard-mvp/page.tsx:23` hardcode `secret-client-key-123`. Not patched (as-is). |
| API-key / JWT / Admin-key layers live; ROI admin-only | 2026-10-01: chat no key **401**, leads no JWT **401**. 2026-10-02: wrong `X-Admin-Token` on `POST /api/v1/events/stub` → **403** `Invalid or missing Admin API Key`. Code still has no `X-Admin-Key`. ROI/pipeline (`main.py:1324`, `1354`) are client-scoped JWT. |
| Twilio sig enforced (`TEST_MODE=false`); drill flags off | Not re-read on the Render dashboard this pass. Prior statement only: A.0 flags row (Mayank 2026-09-15). Code bypass is `main.py:1130` when `TEST_MODE`. |
| `/metrics` firewall note + owner | 2026-10-01 `GET /metrics` **200**, 23243 bytes, no auth. Public in code (`main.py:583`). No firewall evidence in repo. Owner: Mayank. |
| Boot rejects default `ADMIN_API_KEY` | Code: `main.py:183-186` and `app/api/events.py:84-87` raise if missing or equal to `real-estate-super-secret-key`. 2026-10-01 **500** matched a missing Render var. 2026-10-02 after Mayank set `ADMIN_API_KEY` and restarted: wrong token **403**, real token **200**. Not a boot-log read. |

**Aritro sign:** ________

---

## Appendix B — AI & Automation Certification Report (Maitri)

**HEAD:** `production/main` @ `a0a2a53` · **Live number:** `+1 (334) 731-7182` · **Date:** 2026-09-17

### B.1 Fresh 100 — pass by category (live, rate-limited, no `task3_runner`)
| Category | n | Pass | Notes / FAIL ids |
|---|---|---|---|
| Hindi (Devanagari) | 12 | 12 | location+budget parsed incl. Devanagari (`85LAKHS`, `1.2CRORES`); `Rahul`/`9822000001` picked |
| Hinglish | 12 | 12 | t1 English neutral → t2 Hinglish parsed; `Amit`+`9822000002` on `…2118` |
| Typos / noisy input | 10 | 8 + 2 partial | `…2125` (`Banre?`) + `…2129` (`khardi`) → location null, coherent ask-for-location; no crash |
| Budget change mid-thread (last-wins) | 10 | 10 | `…2135–2144` store final 90L…99L, not initial 70L…79L |
| Location switch | 8 | 8 | `…2145–2152` store 2nd location (last-wins) |
| Vague visit date | 8 | 8 | `Weekend`/`Week`/`Kal Parso`/`A Few Days` stored; `…2157` (`next month`) asked date — coherent |
| STOP / opt-out | 8 | 8 | `…2161–2168` all `whatsapp_opt_in=False`, closed, stopped (see B.2) |
| Empty / greeting-only | 8 | 8 | generic help reply, no hallucinated fields |
| Mixed-language | 8 | 8 | `शनिवार→Saturday` (`…2178`), phone `9822000003` (`…2181`) |
| HOT escalation-worthy | 8 | 8 handoff* | `…2185–2192` exact handoff template, closed+stopped; *fields null + temp cold (early-intercept gap — post-cert) |
| Edge (other) | 8 | 8 | ranges `UNDER90LAKHS`/`85L-95LAKHS`; `…2199` fully qualified → Appointment Scheduled, hot 80 |
| **Total** | **100** | **98 + 2 partial** | 138 turns: 138×200 0-drop (137 real_reply + 1 interim `…2149` t1, 14.2s race); p50 2.4s / p95 3.8s |

### B.2 Stop-on-reply / fallback / opt-in (live)
| Check | Proof (DB/log) | Verdict |
|---|---|---|
| Reply after Day-0 arm → no further nudges | `3_+155555552135` t2 15:40:08 → `active/Day 0`, `next=+30m` (16:10:09), `sent_at=null` | PASS |
| Gemini fail → safe template, no error-phrase leak | 0 fallback in 138 turns; 1 interim (13s race, by design); 0 error-phrase rows; supporting `test_p0_safety`+`test_p2_fsm_language` 68/69 (1 env-only local-PG fail); not forced on prod | PASS (with note) |
| STOP → `whatsapp_opt_in=False`, closed, no re-arm | `…2161–2168` 8/8 `opt_in=False` + session `closed` + follow-up `stopped` | PASS |

### B.3 Joint n8n (with Aritro, live UI counts)
| Case | n8n executions | Verdict |
|---|---|---|
| Single `lead.hot` → WF-1 | 1 — exec **719** Success 2026-09-17 | PASS |
| `lead.escalated` alias → no 2nd fire | 0 extra WF | PASS |
| Duplicate-Sid turn → n8n count unchanged | +0 after exec **722** (Case 4b) | PASS |

Artifacts: `reports/PH-C.1-CASES1-3-REPORT.md` · `reports/PH-B-100-EVAL-REPORT.md` (100 convos / 138 turns, all Client B `client_id=3`) · raw per-turn JSON gitignored (local Temp)

**Maitri sign:** ________ · **Mayank sign:** ________
