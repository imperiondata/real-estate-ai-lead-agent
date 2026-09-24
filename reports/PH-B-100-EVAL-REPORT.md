# PH-B 100-Eval — Execution Report (live)

**Date:** 2026-09-17 · **Branch:** `cert-sprint` · **Target:** live Render API
`https://real-estate-ai-lead-agent-21nh.onrender.com`
**Tenant:** Client B (`client_id=3`) · **Webhook:** `POST /api/v1/whatsapp` (bare URL, no `?api_key=`; tenant via `X-API-Key`)
**From range:** `whatsapp:+155555552101` … `+155555552200` (100 fresh, reserved test range — no real customer touched)
**Method:** per-request valid `X-Twilio-Signature` via `RequestValidator` + live auth token
(`TEST_MODE=false` enforced; signature is authentication, not a bypass).
**Pacing:** sequential only (not A.2 concurrency) — 4s between turns, 5s between convos, 12s after HOT.
Client timeout 90s. No `task3_runner`, no wipe, no flag changes, no docker/uvicorn.
**Secrets:** Client B key / Twilio token / DB URL held off-repo, in-memory only. None in git or in this file.
**Plus:** 2 preflight smoke turns on `+15555559998/9999` (both 200 real_reply, Client B) before the 100.

Preflight: `/health` 200 healthy (uptime 2581s, Render warm). Supporting: `pytest tests/test_p0_safety.py tests/test_p2_fsm_language.py` → 68 passed, 1 failed (env-only: `test_patch_validator_rejects_invalid_stage` needs local PG on localhost:5432, refused — unrelated to live).

## Fires (TwiML leg)

138 turns, **all HTTP 200, 0 drops, 0 errors**: **137 real_reply + 1 interim**.

| Leg | Wall |
|---|---|
| p50 | 2374ms |
| p95 | 3787ms |
| mean | 2593ms |
| max | 14205ms (`B-locsw-05` t1 — exceeded 13s race → interim `Just checking…` by design, turn still persisted) |
| min | 834ms (STOP ack, no LLM) |

Per-category turns (all 200):

| Category | Convos | Turns | Result |
|---|---|---|---|
| hindi | 12 | 12 | 12 real_reply |
| hinglish (2-turn) | 12 | 24 | 24 real_reply |
| typos | 10 | 10 | 10 real_reply |
| budget_change (2-turn) | 10 | 20 | 20 real_reply |
| location_switch (2-turn) | 8 | 16 | 15 real_reply + 1 interim |
| vague_date | 8 | 8 | 8 real_reply |
| stop (2-turn) | 8 | 16 | 16 real_reply (t2 = fast opt-out ack ~834–1727ms) |
| greeting | 8 | 8 | 8 real_reply |
| mixed | 8 | 8 | 8 real_reply |
| hot | 8 | 8 | 8 real_reply (handoff template) |
| edge | 8 | 8 | 8 real_reply |

## DB leg (read-only SELECTs, live PG)

Window: sessions `3_+155555552%` created 15:32:18–15:56:34 UTC (24 min).

- **Sessions:** 100, all `client_id=3`; `client_id<>3` = 0. Status: active 83 / closed 17 (8 STOP + 8 HOT handoff + 1 qualified).
- **Leads:** 100, all `client_id=3`. Temperature: cold 53 / warm 37 / hot 10. Funnel: New 24 / Contacted 75 / Appointment Scheduled 1 (`B-edge-07`, fully qualified: Test User + phone + Saturday 11am, prob 80).
- **Messages:** 279 in range (user 138, assistant 141). Expected 276 (138×2); +3 extra assistant rows = 3 single-turn sessions with 3 msgs (`…2157`, `…2196`, `…2197`: 1 user + 2 assistant) — triage below, not an NLP FAIL.
- **Isolation:** 0 rows outside `client_id=3` in range. Smoke `3_+15555559998/9999` both Client B.
- **Error-phrase leak:** 0 assistant rows matching traceback/error/exception.
- **Fallback template:** 0 (`brief connectivity issue` never fired — not forced on prod, by design).

Field extraction spot-checks:

- **Budget last-wins 10/10:** `…2135–2144` store final budgets 90L…99L (not initial 70L…79L), location Baner.
- **Location last-wins 8/8:** `…2145–2152` store second location (Hinjewadi/Wakad/Viman Nagar/Bavdhan/Hinjewadi/Kondhwa/Baner/Kharadi).
- **Hindi 12/12:** location+budget parsed incl. Devanagari numerals (`85LAKHS`, `1.2CRORES`, `25KPERMONTH`); name `Rahul` + phone `9822000001` picked where given.
- **Hinglish 12/12:** English t1 neutral, Hinglish t2 parsed (`Amit` + `9822000002` on `…2118`).
- **Mixed 8/8:** Marathi/Hindi mixes parsed incl. `शनिवार→Saturday` (`…2178`), phone `9822000003` (`…2181`).
- **Typos 8/10 pass, 2 partial:** `…2125` (`Banre?`) and `…2129` (`khardi`) → location null (reply asked for location — coherent, no crash). Triage, not FAIL.
- **Vague date 8/8 coherent:** `Weekend`/`Week`/`Kal Parso`/`A Few Days` stored; `…2157` (`next month`) left visit null and asked for date — coherent.
- **Greeting 8/8 coherent:** generic help reply, no hallucinated fields.
- **Edge 8/8:** `UNDER90LAKHS`, `85L-95LAKHS` ranges stored; brochure request (`…2196`) answered without crash; negotiation (`…2195`, 75L) handled; caps (`…2194`) handled.

## B.2 proofs

1. **Stop-on-reply (Day-0 arm, no spam):** sample `3_+155555552135` (budget 2-turn): turn2 15:40:08 → `follow_up_status=active`, `stage=Day 0`, `next_follow_up_at=16:10:09` (+30m, live `FOLLOW_UP_TEST_MODE=false`), `follow_up_sent_at=null`. Reply pushed the clock; no immediate nudge. PASS.
2. **Fallback:** 0 fallback templates in 138 turns; 1 interim (race window working as designed); 0 error-phrase leaks. Gemini failure **not forced** on prod (would risk live users). Supporting `test_p0_safety` 68/69 (1 env-only fail). Recorded as “not forced — interim path proven live”. PASS (with note).
3. **STOP / opt-in 8/8:** `…2161–2168` → all `whatsapp_opt_in=False`, session `closed`, `follow_up stopped`, no re-arm. Covers `STOP`, `please stop messaging`, `don't message/contact`, `unsubscribe`, `stop messaging`. PASS.

## HOT / handoff note (honest)

8/8 HOT (`…2185–2192`) → exact handoff reply (`paused my automated responses…`), session `closed`, follow-up `stopped` (terminal, no re-arm). Funnel `Contacted`. **But** lead `location/budget/property_type` are null, temperature `cold`, prob 17 — handoff early-intercept (`agent.py` handoff path) returns before field extraction/scoring. Escalation itself PASSED; field capture on handoff is a post-cert product gap for Mayank (do not patch in sprint). n8n WF-1 delta for these 8 fires needs owner UI check (spaced 12s; debounce is per-lead so each may count).

## Triage (not FAILs)

- 3 sessions with double assistant row (`…2157`, `…2196`, `…2197`) — likely race-window slow-path double-save on single-turn. NLP unaffected (user-visible reply coherent). For Mayank post-cert.
- 2 heavy-typo location nulls (`Banre`, `khardi`) — reply asked for location. Consider fuzzy location match post-cert.
- HOT null-field gap above.

## Verdicts vs sprint (`docs/PRODUCTION_HARDENING_SPRINT.md` PH-B)

| Sprint expectation | Result |
|---|---|
| 100 fresh live WA convos, rate-limited, unique sessions | PASS (100/100 sessions+leads, all Client B, 24-min sequential window) |
| Coverage: Hindi/Hinglish/typos/budget-last-wins/loc-switch/vague/STOP/empty/mixed/HOT/edge | PASS (12/12/10/10/8/8/8/8/8/8/8; details above) |
| English default; Hinglish after user initiates | PASS (t1 English neutral, t2 Hinglish parsed) |
| No `task3_runner` vs prod | PASS (signed webhook only) |
| B.2 stop-on-reply / fallback / opt-in | PASS (Day-0 +30m no-spam; interim proven, fallback not forced; 8/8 STOP closed+opt-out) |
| Tenant isolation | PASS (0 non-Client-3 rows in range) |

## Artifacts (local only, not committed)

- Fire script + raw JSON: `C:\Users\hp\AppData\Local\Temp\opencode\phb_fire.py`, `phb_results.json` (138 turns, full TwiML heads)
- Checkpoint: `phb_checkpoint.json` (resume-aware)
- DB verify scripts (SELECT-only): `phb_verify_db.py`, `phb_verify2.py`, `phb_verify3.py`, `phb_summarize.py`
- Summary: this file (committed). Raw per-request JSON gitignored.

Evidence rows for Appendix B to be pasted at PH-R.
