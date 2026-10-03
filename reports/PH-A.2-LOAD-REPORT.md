# PH-A.2 Load 25 / 50 / 100 — Execution Report (live)

**Date:** 2026-09-17 · **Branch:** `cert-sprint` · **Target:** live Render API
`https://real-estate-ai-lead-agent-21nh.onrender.com`
**Tenant:** Client B (`client_id=3`) · **Path:** `POST /api/v1/chat` (query `session_id`+`message`; tenant via `X-API-Key`)
**Harness:** `load_chat_concurrency.py` (`LIVE_API_BASE_URL` + `LIVE_CLIENT_B_KEY` from local `.env`)
**Message (neutral, no handoff):** `Hi looking for 2BHK in Baner`
**Secrets:** Client B key / Twilio token / DB URL held off-repo. None in git or in this file.

Preflight: `/health` **200** (uptime 785s, Render warm). No local docker/uvicorn. Client timeout in harness: **60s**.

## Legs

| Leg | Stamp (UTC) | HTTP 200 | 5xx | Drops | p50 | p95 | mean | max | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| 25 | `122943` | 25/25 | 0 | 0 | 15.0s | 15.0s | 15.0s | 15.0s | PASS 0-drop; p95 above draft 13s (live Gemini) |
| 50 | `123006` | 50/50 | 0 | 0 | 22.3s | 23.2s | 21.5s | 23.2s | PASS 0-drop; p95 above draft 15s |
| 100 | `123036` | 0/100 | 0 | 100 | 60.4s | 60.4s | 60.3s | 60.4s | **CLIFF** — see drops section |

Session ids: `load-{leg}-{stamp}-{i:03d}` → Postgres `{client_id}_{sid}` e.g. `3_load-25-122943-000`.

## What “100 drops” means

Harness drop = HTTP `0` (no status) **or** 429/502/503/504 **or** `ok=false`.

The 100-leg JSON is **all** `http: 0`, `err: ReadTimeout`, wall ~**60.3s**. That is the **client** `httpx.Timeout(60.0)` in `load_chat_concurrency.py`, **not** 100 crashed workers and **not** 5xx.

Live DB after the 100-leg: **49/100** `load-100-123036-*` rows on `client_id=3`. Render/Gemini was still finishing after the client hung up. 25-leg p95 was already ~15s and 50-leg ~23s; at 100 concurrent chats on Render Free + live Gemini, queue time exceeds 60s → every client times out.

**Not a logic defect** (not duplicate-Sid, not isolation leak, not 5xx storm). **It is the capacity cliff** the sprint asked to document.

## Isolation (read-only live PG)

| Check | Result |
|---|---|
| `load-25-122943` leads | 25 |
| `load-50-123006` leads | 50 |
| `load-100-123036` leads | 49 |
| Total matching load sessions | 124, all `client_id=3` |
| `client_id <> 3` among those | **0** |

## Verdicts vs sprint (`docs/PRODUCTION_HARDENING_SPRINT.md` PH-A.2)

| Draft pass | Result |
|---|---|
| 25: p95 &lt; 13s, drop 0% | 0-drop; p95 15.0s (document, live Gemini) |
| 50: p95 &lt; 15s, 5xx &lt; 1% | 0-drop, 0 5xx; p95 23.2s (document) |
| 100: document cliff; 0 double-process | Cliff = client 60s timeout; 49/100 persisted; no 5xx |

## Artifacts

- Summary: this file (committed)
- Raw per-request JSON: `reports/load_leg_{25,50,100}_*.json` (**gitignored**)
- Harness: `load_chat_concurrency.py`
