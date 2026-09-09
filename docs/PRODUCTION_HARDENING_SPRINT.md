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

## 1. Hard rules

1. **Certify the live deploy as-is.** `production/main` @ `a0a2a53` only. **Do not merge `phase4_tests`. No new AI agents. No Digital Twin expansion** (Piyush final rule).
2. **Serial order:** PH-0 → PH-A.1(audit) → PH-C → (PH-A.2 ∥ PH-B) → PH-A.3 → PH-A.4 → PH-R. PH-C before the 100-eval so duplicates do not contaminate NLP evidence.
3. **Real Twilio, real signatures.** Live number `+1 (334) 731-7182`. Duplicate = resend the same webhook with a valid `X-Twilio-Signature` (computed with the auth token — that is authentication, not a bypass). **`TEST_MODE=true` is forbidden for cert evidence.**
4. **Live n8n mandatory.** Execution counts from the n8n UI. Unit mocks (`test_e20_n8n_bridge.py`) are supporting evidence only.
5. **DR on hosted Render PostgreSQL only.** Render snapshot **first** (protects seeded Client A/B), then backup → failure sim → restore → verify. Maintenance window agreed with Mayank + Maitri; no dashboard/eval traffic during the window. **No local `pg-staging`.**
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
| DR | Hosted Render PG; snapshot first; maintenance window with Mayank + Maitri |
| Gates | Sprint **blocks** P4-QA/REL |
| Owners | Aritro Appendix A (security, load, DR, logs) · Maitri Appendix B (100-eval, compliance, stop-on-reply) · joint PH-C |

---

## 3. Master sequence

| Step | Unit | Summary | Exit gate | Owner | Status |
|---:|---|---|---|---|---|
| **PH-0** | Prep | Record live env (Render URL, flags, Twilio, n8n, HEAD) | Env sheet in Appendix A | Both | `[ ]` |
| **PH-A.1** | Tenant-log audit | Inventory `tenant_id_ctx` coverage on jobs / APIs / queues | Gap table in Appendix A | Aritro | `[ ]` |
| **PH-C** | Joint drill | Signed duplicate / simultaneous / retry webhooks + live n8n single-fire | Matrix §C all PASS | Aritro+Maitri | `[ ]` |
| **PH-A.2** | Load | 25 / 50 / 100 concurrent vs live: latency + drop rates | Numbers table in Appendix A | Aritro | `[ ]` |
| **PH-B** | 100-eval | 100 fresh live WhatsApp convos + stop-on-reply / fallback / opt-in | JSON + summary in Appendix B | Maitri | `[ ]` |
| **PH-A.3** | DR | Snapshot → backup → fail → restore → verify on hosted Render PG | Appendix A §DR | Aritro | `[ ]` |
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
| DR PH-A.3 | Maintenance window on calendar + Render snapshot | Appendix A DR |
| Reports PH-R | All above + isolation re-run | Gate input |

---

## PH-0 — Prep

### Task PH-0.1 — Record the live env
- **Files:** none (evidence only)
- **Steps:**
  1. Confirm deploy tracks `production/main` @ `a0a2a53`. Record Render API URL, Vercel URL, Redis host, n8n host, Twilio number `+1 (334) 731-7182`.
  2. Record live flags: `TEST_MODE=false` (signature enforced), `IS_PRODUCTION=true`, `FOLLOW_UP_TEST_MODE=false`, `FOLLOWUP_ENGINE=v3`, `FEATURE_WHATSAPP_V3=true`.
  3. Confirm Client A + Client B seeded (isolation-safe read check only).
  4. `curl https://<render-api>/health` → 200.
- **Test:** `/health` 200 on the live host
- **Done:** Env sheet pasted into Appendix A header
- **Rollback:** N/A
- **Status:** `[ ]`

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
- **Status:** `[ ]`

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
- **Status:** `[ ]`

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
- **Status:** `[ ]`

---

## PH-A.2 — Load 25 / 50 / 100 (Aritro, live)

### Task PH-A.2.1 — Concurrency vs live API
- **Files (reference):** `docs/TIMEOUTS_AND_TIMINGS.md` (13s race, 22s LLM cap), `wa_sse_smoke.py` (turn baselines)
- **Steps:**
  1. Harness posts Twilio-shaped requests to the **live** API (signed webhook and/or `/api/v1/chat` with a dedicated test-tenant key — never Client A prod traffic). Unique `MessageSid` per request; N sessions for "concurrent chats"; reuse a Sid subset for drop-vs-dedupe.
  2. Run 25 → 50 → 100+ concurrent. Per leg record: HTTP code, wall ms, TwiML vs interim vs empty, 5xx count, drop count, duplicate-process count (same Sid processed twice = defect).
  3. Capture p50/p95, 5xx rate, interim rate, `/metrics` (latency histogram, DLQ depth, scheduler health).
  4. Re-run read-safe `gate_isolation_test.py` after the 100 leg.
- **Test:** `python gate_isolation_test.py` · `python gate_dlq_drill.py` + `dlq_replay.py` (careful on live — Mayank's OK)
- **Done:** Appendix A load table (draft pass: 25 → p95 < 13s, drop 0%; 50 → p95 < 15s, 5xx < 1%; 100 → document cliff + zero duplicate-Sid processing; tune with Mayank)
- **Rollback:** N/A; stop legs if live users impacted
- **Status:** `[ ]`

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
- **Status:** `[ ]`

### Task PH-B.2 — Stop-on-reply + fallback + opt-in proof (live)
- **Files (reference):** `app/intelligence/push_wait_engine.py` (`replied` → `stop_followups`), `follow_up.py` opt-out skip, `agent.py` `is_opt_out_message`
- **Steps:**
  1. Stop-on-reply: arm Day-0 follow-up, then user replies → assert scheduler skips/stops (no further auto nudges).
  2. Fallback: force Gemini failure/timeout → assert safe template reply, no error-phrase leak, DLQ row only where specified.
  3. Opt-in: STOP variants → `whatsapp_opt_in=False`, session closed, no re-arm while opted out.
- **Test:** `pytest tests/test_p0_safety.py tests/test_e4_followup.py -v` (supporting)
- **Done:** Three mini-tables with DB/log evidence in Appendix B
- **Rollback:** N/A
- **Status:** `[ ]`

---

## PH-A.3 — Disaster recovery drill (Aritro, maintenance window)

### Task PH-A.3.1 — Snapshot → backup → fail → restore → verify (hosted Render PG)
- **Files (reference):** `docs/BACKUP_RESTORE_DRILL.md` (procedure + 7-table check), `docs/MAINTENANCE.md` §4–5, `db_backup.py`, `db_restore.py`
- **Steps:**
  1. **Window first:** propose exact time to Mayank; confirm Maitri runs nothing during it. Record the window in Appendix A.
  2. **Render snapshot** of the hosted PostgreSQL (protects seeded Client A/B). Record snapshot id + time.
  3. `python db_backup.py` with prod `DATABASE_URL` → off-box copy. Record artifact + size.
  4. Failure sim: stop/restart Render web and/or break DB connectivity; record `/health` + chat behavior with timestamps.
  5. Restore hosted PG from the snapshot (primary) — `db_restore.py` only if the snapshot path is unavailable; record which path was used.
  6. Verify: Client A/B rows, 7-table counts (`clients`, `sessions`, `leads`, `messages`, `event_logs`, `follow_up_states`, `dlq_events`), one real WA turn on the live number, isolation check.
  7. Record observed RTO/RPO + off-box backup gap.
- **Test:** `python gate_isolation_test.py` · `python gate_dlq_drill.py` + `dlq_replay.py` (post-restore, Mayank's OK)
- **Done:** Appendix A §DR filled (window, snapshot id, backup artifact, kill log, restore log, counts, RTO/RPO)
- **Rollback:** The snapshot **is** the rollback; keep it until sign-off
- **Status:** `[ ]`

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

---

## Appendix A — Backend Production Certification Report (Aritro)

**HEAD:** `production/main` @ `a0a2a53` · **Live API:** ________ · **Date:** ________ · **DR window:** ________

### A.0 Env sheet (PH-0)
Render API / Vercel / Redis / n8n host / Twilio `+1 (334) 731-7182` / flags (`TEST_MODE=false`, `IS_PRODUCTION=true`) / `/health`:

### A.1 Tenant-log audit
| Job / path | Emits `[Tenant: …]`? | Evidence / gap (file:line) |
|---|---|---|
| Request auth | Yes | `auth.py`, `app/api/events.py` |
| `follow_up` scheduler | Yes | `follow_up.py:388`, `followup_scheduler.py:87` |
| Escalation loop | Yes | `main.py` escalation |
| Bus `_dispatch` / CEO / bridge / EE | | |
| `crm_resync_job` | | |
| `competitor_monitor` / weekly marketing | | |
| `expire_stale_approvals` | | |
| `daily_cleanup` / `nightly_backup` | | |

### A.2 Load — 25 / 50 / 100 concurrent (live)
| Leg | p50 | p95 | 5xx | Drops | Interim rate | Dup-Sid processed | Verdict |
|---|---|---|---|---|---|---|---|
| 25 | | | | | | 0 required | |
| 50 | | | | | | 0 required | |
| 100+ | | | | | (document cliff) | 0 required | |
Isolation after load: ________ · Artifacts: ________

### A.3 Disaster recovery (hosted Render PG)
| Step | Evidence |
|---|---|
| Window (Mayank + Maitri confirmed quiet) | |
| Render snapshot id + time | |
| `db_backup.py` artifact + size | |
| Failure sim log (`/health` + chat) | |
| Restore path (snapshot / `db_restore.py`) + log | |
| Client A/B + 7-table counts | |
| Post-restore live WA turn + isolation + DLQ | |
| Observed RTO / RPO + off-box gap | |

### A.4 Security / secrets (live)
| Check | Result |
|---|---|
| No secrets / demo keys in git; `.env*` ignored; `frontend/src` clean | |
| API-key / JWT / Admin-key layers live; ROI admin-only | |
| Twilio sig enforced (`TEST_MODE=false`); drill flags off | |
| `/metrics` firewall note + owner | |
| Boot rejects default `ADMIN_API_KEY` | |

**Aritro sign:** ________

---

## Appendix B — AI & Automation Certification Report (Maitri)

**HEAD:** `production/main` @ `a0a2a53` · **Live number:** `+1 (334) 731-7182` · **Date:** ________

### B.1 Fresh 100 — pass by category (live, rate-limited, no `task3_runner`)
| Category | n | Pass | Notes / FAIL ids |
|---|---|---|---|
| Hindi (Devanagari) | | | |
| Hinglish | | | |
| Typos / noisy input | | | |
| Budget change mid-thread (last-wins) | | | |
| Location switch / vague visit date | | | |
| STOP / opt-out | | | |
| Empty / greeting-only | | | |
| Mixed-language | | | |
| HOT escalation-worthy | | | |
| Edge (other) | | | |
| **Total** | **100** | | |

### B.2 Stop-on-reply / fallback / opt-in (live)
| Check | Proof (DB/log) | Verdict |
|---|---|---|
| Reply after Day-0 arm → no further nudges | | |
| Gemini fail → safe template, no error-phrase leak | | |
| STOP → `whatsapp_opt_in=False`, closed, no re-arm | | |

### B.3 Joint n8n (with Aritro, live UI counts)
| Case | n8n executions | Verdict |
|---|---|---|
| Single `lead.hot` → WF-1 | 1 required | |
| `lead.escalated` alias → no 2nd fire | 0 required | |
| Duplicate-Sid turn → n8n count unchanged | +0 required | |

Artifacts (JSON + summary): ________ · FAIL triage (file:line): ________

**Maitri sign:** ________ · **Mayank sign:** ________
