# PH-C.1 Cases 1–4 — Execution Report (live)

**Date:** 2026-09-17 · **Branch:** `cert-sprint` · **Target:** live Render API
`https://real-estate-ai-lead-agent-21nh.onrender.com`
**Tenant:** Client B (`client_id=3`) · **Webhook:** `POST /api/v1/whatsapp` (bare URL, no `?api_key=`; tenant via `X-API-Key`)
**From:** `whatsapp:+15555550100` (reserved test range — no real customer touched)
**Method:** per-request valid `X-Twilio-Signature` via `RequestValidator` + live auth token
(`TEST_MODE=false` enforced; signature is authentication, not a bypass).
**Secrets:** Client B key / Twilio token / DB URL held off-repo, in-memory only. None in git or in this file.

Preflight: `/health` 200 healthy (all subsystems connected), Render warm.

## Fires (TwiML leg)

| Case | Time (UTC / IST) | MessageSid (short) | HTTP | Wall | TwiML |
|---|---|---|---|---|---|
| 1 first (neutral Body) | 10:10:58 / 15:40:58 | `SM0ede…fa066` | 200 | 2719ms | **real_reply** (fast path, 1 Gemini turn): 2BHK Baner 90L–1.4cr + asks budget/name |
| 1 duplicate (same Sid) | 10:10:59 / 15:40:59 | `SM0ede…fa066` | 200 | 520ms | **empty** `<Response></Response>` — no 2nd turn |
| 2B simultaneous | 10:11:01 / 15:41:01 | `SMd773…40d5c` | 200 | 1672ms | **real_reply**, distinct content (premium projects from 90L) |
| 2A simultaneous | 10:11:02 / 15:41:02 | `SM7d71…beeaf` | 200 | 2785ms | **real_reply**, distinct content (asks budget + buy/rent) |
| 3 retry (same Sid, +12s) | 10:11:11 / 15:41:11 | `SM0ede…fa066` | 200 | 1015ms | **empty** — idempotent, no 2nd turn |

Neutral Body throughout: `Hi, what 2BHK options are available in Baner?` (Cases 2A/2B suffixed `(A)`/`(B)` so the two parallel turns stay distinguishable).

## DB leg (read-only SELECTs, live PG)

**`webhook_logs`** — exactly 3 rows, one per unique Sid. `SM0ede…fa066` appears **once** despite 3 POSTs
(Case 1 first + duplicate + Case 3 retry) → duplicates hit `IntegrityError` → rollback → empty TwiML
(`main.py:1159-1164`). PASS.

**`messages`** for `3_+15555550100` (drill window) — exactly 6 rows, strict user/assistant alternation:

| id | role | content head | timestamp UTC |
|---|---|---|---|
| 19 | user | `Hi, what 2BHK options are available in Baner?` | 10:10:57 |
| 20 | assistant | `We have some excellent 2BHK options in Baner…` | 10:10:58 |
| 21 | user | `…Baner? (B)` | 10:11:00 |
| 22 | assistant | `We have a variety of premium 2BHK projects…` | 10:11:01 |
| 23 | user | `…Baner? (A)` | 10:11:01 |
| 24 | assistant | `Since you are looking for a 2BHK in Baner…` | 10:11:02 |

Duplicates produced **zero** extra message rows → zero extra Gemini turns. Simultaneous pair serialized
(B fully answered before A processed — `session_lock`, no interleave). PASS.

**`leads`** — `id=4, session_id=3_+15555550100, client_id=3, temperature=warm, funnel_stage=New,
conversion_probability=46`. Tenant isolation correct; neutral Bodies stayed below the HOT threshold
(82) → no `lead.hot` pollution of the WF-1 count. PASS.

## Verdicts vs sprint (`docs/PRODUCTION_HARDENING_SPRINT.md` PH-C.1)

| Sprint expectation | Result |
|---|---|
| Case 1: 2nd same-Sid POST → empty, one Gemini turn, one `WebhookLog` row | PASS (200 empty in 520ms; 1 log row; 2 message rows) |
| Case 2: parallel same-`From` different Sids → serialized, no garble | PASS (both 200 real_reply, distinct coherent texts, alternating DB rows) |
| Case 3: delayed same-Sid retry → idempotent | PASS (200 empty in 1015ms; no new rows) |
| Case 4: handoff → WF-1 +1, duplicate → empty + WF-1 +0 | PASS (4a 200 handoff + exec 722; 4b 200 empty, zero new rows; +0 UI tick pending) |
| No Client A traffic; no wipes; no flag changes | PASS (Client B only; SELECT-only DB access) |

## Still to confirm (needs n8n UI — owner)

- [x] Case 4 fire-1 WF-1 delta: **+1 — exec 722 Success @ 15:53:12 IST** (2.221s), matches fire-1 second.
- [x] Case 4 fire-2 WF-1 delta: **+0 confirmed** — no execution after 722; DB shows no new rows.

## Case 4 — handoff duplicate → WF-1 +1 then +0 (executed 2026-09-17)

Handoff Body: `Hi, looking for 2BHK in Baner budget 80L please connect me to a human agent`
(f same phrase that produced the PH-C.2 handoff). Same session/lead as Cases 1–3
(`3_+15555550100`, lead 4 — debounce key `lead_hot_emitted:3:4:human_handoff` was free).

| Fire | Time (UTC / IST) | MessageSid (short) | HTTP | Wall | TwiML |
|---|---|---|---|---|---|
| 4a first | 10:23:11 / 15:53:11 | `SM3d38…28fa` | 200 | 1399ms | **real_reply** handoff (`paused my automated responses…`) |
| 4b duplicate (same Sid, identical Body, fresh signature) | 10:26:02 / 15:56:02 | `SM3d38…28fa` | 200 | 1092ms | **empty** `<Response></Response>` |

DB leg: after 4a — 1 `webhook_logs` row for the Sid; messages +2 (id 25 user handoff, 26 assistant handoff);
lead 4 funnel `New → Contacted` (warm/46, Client B). After 4b — **zero** new rows anywhere
(same single log row @ 10:23:10, messages end at 26, lead unchanged). Duplicate never reached the
agent/publish path. n8n: 4a → **+1 (exec 722)**; 4b → **+0 expected** (UI check above).

Verdict: **PASS** (4b +0 confirmed in UI + DB). Sprint PH-C.2 step 4 + Appendix B.3 row 3 satisfied.

## Artifacts (local only, not committed)

- Fire script + raw JSON: `C:\Users\hp\AppData\Local\Temp\opencode\phc1_fire.py`, `phc1_results.json`
- DB verify script (SELECT-only): `C:\Users\hp\AppData\Local\Temp\opencode\phc1_verify_db.py`

Evidence rows for Appendices A/B to be pasted at PH-R.
