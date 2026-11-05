# Scorer RCA — 82 unreachable, v3 used 70

**Date:** 4 November 2026
**Owner:** Maitri (Industry Profile)
**Scope:** v3 chat/scoring path only. Legacy `agent.py` remains out of scope.

## Symptom

The published `real_estate` v1 profile says hot is **82**, but the v3 scorer
classified with a literal **70** and could not reach 82 even for a fully
qualified lead. An 80 was treated as hot in staging, which contradicts the
profile.

## Evidence

- `Industry_Profile_Schema.json`, profile `real_estate` v1:
  `hot_min_probability=82`, `warm_min_probability=45`,
  `full_qualify_floor=88`, `field_floors.visit_date=82`.
- Pre-change `app/agents/whatsapp_agent.py:178`:
  `if prob >= 70:`.
- Pre-change `app/intelligence/analytics_engine.py:245` and
  `app/intelligence/followup_engine.py:173`: `>= 70`.
- Blend math: `engagement * 0.5 + temp_weight * 0.5`, engagement cap 100,
  hot weight 60 → maximum **80**. The old path had no profile floors, so 82
  was mathematically unreachable.

## Root cause

The scorer did not read the published profile. It hard-coded the hot cut at 70
and omitted the profile's full-qualify and visit-date floors. The analytics and
follow-up high-priority cuts repeated the same literal.

## Fix

- `app/industry/profile_loader.py` (new): loads the `(key, version)` profile
  from the schema `examples`, resolves thresholds, classifies temperature, and
  validates tenant override values against the declared range.
- `app/industry/profile_guard.py`: `validate_override_value` rejects unknown,
  non-numeric, and out-of-range tenant values.
- `app/agents/whatsapp_agent.py`: `score_lead` is profile-driven, applies
  `full_qualify_floor` (88) and `field_floors.visit_date` (82), and classifies
  against 82/45. The literal 70 is gone.
- `app/intelligence/analytics_engine.py` and
  `app/intelligence/followup_engine.py`: high cuts resolve 82 from the profile.

## Verification

- `tests/test_v2_industry_profile_scorer.py`: 8 tests covering defaults,
  80/82/45 classification, 85 override, 69/91 rejection, floors, and the
  absence of the literal 70.
- DB proof (local, test rows deleted): fully qualified lead → `prob=88`,
  `temp=hot`; partial lead → `prob=72`, `temp=warm`.
- Targeted suites: 44 passed (`scorer`, `guard`, `docs`, `e5`, `e4`,
  migration dry run).
- App rollback proof: `APP_ROLLBACK_PASS`
  (`plans/evidence/NOV4_APP_ROLLBACK.log`). The V1 row was read through
  `serialize_lead` after the shadow schema was dropped. No HTTP server was started.
- UI wiring: `/ai-chat` and `/widget` return 200; `/api/chat` forwards to
  `/api/v1/chat` with `X-API-Key` and returns `status=success`, `client_id=1`.
  The live reply in this run was the fallback because Gemini returned
  `503 UNAVAILABLE` three times (`llm_main_call` logs), not because of the
  scorer.

## Out of scope / residual risk

- Legacy `agent.py:1503` is already `if prob >= 82`. That path is not the v3 scorer and was not the staging 70. Do not describe it as a remaining 70.
- `analytics_engine.py:273` and `followup_engine.py:211` are different cuts and
  were intentionally left unchanged.
- Profile loading reads the JSON file per call; a DB-backed store and caching
  are Phase 2 work.
- Full-suite check at `7b837cf` is green; merge to `remediation/p0-security-fixes` remains gated. The Render branch name still blocks deploy.
