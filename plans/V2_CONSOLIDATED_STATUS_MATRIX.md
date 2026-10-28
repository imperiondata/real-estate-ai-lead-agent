# V2 Consolidated Status Matrix

**Date:** 29 October 2026
**Owner:** Maitri (Industry Profile) with Aritro (Migration)
**Audience:** Piyush
**Purpose:** Reconcile the Phase 1 documents with the current code and lock the decisions that Phase 2 implementation depends on.

**Baseline for code checks:** `bafa585` (`docs(v2): add Industry Profile Schema json`).
**Branch:** `remediation/p0-security-fixes` (54 commits ahead of `origin/main` at the time of writing; not yet pushed).

---

## 1. Frozen baseline

- Piyush has reviewed the Phase 1 package. The architectural baseline is frozen.
- Implementation may proceed in an **isolated environment only**. No live database changes, no Render DDL, no writes to production.
- `V2_DUAL_WRITE` remains `false` by default and is not approved for live use.
- This matrix is a documentation and decision artifact. No schema, application code, or database change was made for it.
- `V2_Industry_Profile.md` and `Industry_Profile_Schema.json` are canonical for the profile. `V2_Migration_and_Security.md` is canonical for migration and security. This matrix records where those documents disagree with each other or with the code.

---

## 2. Status legend

| Status | Meaning |
|---|---|
| `Aligned` | Document and code agree. |
| `Partial` | Part of the claim exists in code; part is still target-only. |
| `Contradicts` | Document and code explicitly disagree. |
| `Target-only` | Document describes the approved target; code does not implement it yet. |
| `Decided` | Cross-document decision made; implementation follows. |
| `Superseded` | A Phase 1 constraint that no longer applies in Phase 2. |
| `Blocked` | Cannot close until an external dependency or evidence exists. |
| `Fixed 29 Oct` | Documentation contradiction corrected in this pass. |

---

## 3. Matrix

| ID | Claim / contradiction | Source | Current code reality | Status | Owner | Resolution |
|---|---|---|---|---|---|---|
| M-01 | The profile is one full envelope, but Mayank's ER stores `qualification_schema` and `base_ai_prompt` as two columns and the document calls this a "storage gap". | `V2_Industry_Profile.md:19-30` | No profile table or loader exists. | `Decided` | Maitri + Aritro | Runtime profile is one `industry_profiles.document` JSONB row per `(key, version)`. Tenant overrides live in `tenant_configurations.overrides`. Two-column storage is superseded. Mayank ER update requested. |
| M-02 | `Industry_Profile_Schema.json` is a meta-schema with `examples`, not a runtime profile instance. | `Industry_Profile_Schema.json:100-246` | No seeded `real_estate/1` or `education/1` profile exists. | `Target-only` | Maitri | Seed both profiles from the `examples` array. `FileProfileStore` first; `DbProfileStore` for the isolated `v2` schema later. |
| M-03 | Hot threshold is 82. | `V2_Industry_Profile.md:69`; `Industry_Profile_Schema.json:135` | `app/agents/whatsapp_agent.py:178` uses `>= 70`; `app/intelligence/analytics_engine.py:245` and `app/intelligence/followup_engine.py:173` also use 70. | `Contradicts` | Maitri | 82 is canonical. The 70 cutoffs are implementation gaps to remove behind the profile engine. |
| M-04 | Warm is 45, full-qualify floor is 88, visit floor is 82. | `V2_Industry_Profile.md:69`; `Industry_Profile_Schema.json:134-139` | `score_lead` uses 45 for warm, but does not apply the 88 full-qualify floor or 82 visit floor. | `Partial` | Maitri | Scoring reads `temperature.*` from the profile. |
| M-05 | `score` is engine-owned scoring data. | `V2_Industry_Profile.md:67` | `models.Lead.score` is a String defaulting to `"Low"` (`models.py:90`); numeric outputs are separate columns. | `Contradicts` | Maitri | Keep `Lead.score` as a legacy display field. Profile scoring writes `conversion_probability`, `lead_temperature`, `engagement_score`, `urgency_level`, and `budget_alignment_status`. |
| M-06 | The profile has no hardcoded city price table; budget alignment uses tenant pricing/catalog and returns `unknown` when data is missing. | `V2_Industry_Profile.md:71`; `Industry_Profile_Schema.json:145-149` | `app/intelligence/budget_alignment.py:61-80` uses `PUNE_LOCATIONS` from `app/data_manager.py`. | `Contradicts` | Maitri | Target is tenant `PricingRule`/`InventoryUnit`. No Pune table in the profile. Treat the current lookup as a known deviation. |
| M-07 | Kanban uses stage keys from `pipeline_stages`; unknown stage writes fail. | `V2_Industry_Profile.md:79-85`; `Industry_Profile_Schema.json:154-166` | `agent.FUNNEL_STAGES` is label-based (`agent.py:122`); `main.py:1661` validates against it; `frontend/src/app/(dashboard)/crm/KanbanBoard.tsx:8` hardcodes the same labels; `main.py:944` writes `"New"`. | `Contradicts` | Maitri | Profile keys are canonical. Publish the legacy label-to-key map and reject unknown stages. Frontend follows the profile or the API exposes stages. |
| M-08 | Unknown rule keys fail profile load; override paths and ranges are validated. | `V2_Industry_Profile.md:38`; `Industry_Profile_Schema.json:90-98` | The meta-schema leaves `scoring_rules` sub-objects unconstrained (`:54-67`) and `overrides.ranges` untyped (`:96`). | `Partial` | Maitri | JSON Schema alone is not sufficient. The loader validator enforces nested rule keys, numeric bounds, stage uniqueness, dashboard ids, prompt slots, and override paths/ranges. |
| M-09 | The booking gate is code-enforced and separate from storage validation. | `V2_Industry_Profile.md:40`; `Industry_Profile_Schema.json:117-118` | `agent.is_fully_qualified` and `agent.py:661-662` hardcode the six fields; the prompt also instructs the model. There is no profile-driven gate. | `Partial` | Maitri | `required_for_booking` comes from the profile. `name` and `phone` stay global. The gate runs before any booking tool call. |
| M-10 | Phase 1 does not add a validator library, script, or test. | `V2_Industry_Profile.md:104` | No V2 validator or test exists. | `Superseded` | Maitri | Phase 2 requires a validator and tests. Phase 1's "docs only" constraint no longer applies. |
| M-11 | Every profile supports `inactivity` and `behavior`, or the engine owns them. | `Industry_Profile_Schema.json:120-153` vs `:193-224` | `education` omits both blocks; the meta-schema does not require them. | `Target-only` | Maitri | Missing blocks mean engine-owned defaults. The loader normalizes every profile to the same engine contract. |
| M-12 | No live schema change is allowed until Piyush reviews the package. | `V2_Migration_and_Security.md:7-9` | Phase 1 is reviewed. Code is unchanged. | `Fixed 29 Oct` | Aritro | Status updated: approved for isolated implementation; live schema changes remain banned. |
| M-13 | Mayank accepted "all four decisions"; dates mix 25 and 26 October. | `V2_Migration_and_Security.md:9`, `:281-291` | Five decisions are listed in section 12. | `Fixed 29 Oct` | Aritro | Text now says five decisions and uses "accepted 25 October 2026; clarified 26 October 2026". |
| M-14 | Industry keys are strings; `intent` is `buy|rent|unknown`; `visit_date` has `format: date`. | `Industry_Profile_Schema.json:105-118` | V1 stores `budget`, `intent`, `visit_date` as free-text strings (`models.py:86-91`). | `Target-only` | Aritro | Backfill mapping is defined in `V2_Migration_and_Security.md` section 5.1: trim, empty to null, intent mapping, date normalization, quarantine only wrong type/format or unknown key. |
| M-15 | Name and phone are relational and nullable for this cut. | `V2_Migration_and_Security.md:117`; `V2_Industry_Profile.md:28` | `models.Lead.name` and `.phone` are already nullable (`models.py:84-85`). | `Aligned` | Aritro | Backfill copies empty values as null, never `""`. |
| M-16 | `FORCE ROW LEVEL SECURITY`, a non-owner app role, and `app.current_tenant_id` isolate tenants. | `V2_Migration_and_Security.md:192-216` | No RLS or tenant session variable exists in V1. | `Target-only` | Tenancy/Security owner | Do not claim isolation is shipped. Design is accepted; implementation is out of this docs pass. |
| M-17 | The evidence package needs CI run URLs and commit SHAs. | Oct 30 requirement | There is no `.github/workflows` in the repo. V2 commits are local only. | `Blocked` | CI/evidence owner | Add a minimal workflow or record local pytest output and state that no CI URL exists. Push a PR before Oct 30. |
| M-18 | `schema.json` is a repository artifact. | Repo root | `schema.json` is an untracked 5.3 MB UTF-16 opencode session export, not a DB schema. It contains prior conversation text. | `Blocked` | Evidence owner | Move it outside the repo or ignore it. Do not commit or submit it. |
| M-19 | `webhook_logs` has no `client_id` in V1; V2 adds `tenant_id`. | `V2_Migration_and_Security.md:36`, `:176` | V1 table has no tenant column. | `Target-only` | Aritro | Create `v2.webhook_logs.tenant_id` in the shadow schema only. No live alter. |
| M-20 | One scoring contract. | `V2_Industry_Profile.md:63-69` | Two scoring paths exist: `whatsapp_agent.score_lead` (`:160-203`) and `app.intelligence.lead_scoring.calculate_lead_score` called from `agent.py:1453`. | `Contradicts` | Maitri | Add one profile adapter and mark the non-profile path legacy, or converge both before staging. |

---

## 4. Locked decisions (29 October 2026)

1. **Profile storage (option B):** one published immutable document per `(key, version)`.

```text
v2.industry_profiles
  id            uuid primary key
  key           text not null
  version       integer not null
  status        text not null check (status in ('draft','published'))
  document      jsonb not null
  created_at    timestamptz not null default now()
  unique (key, version)

v2.tenant_configurations
  tenant_id     uuid primary key references v2.tenants(id) on delete cascade
  profile_id    uuid not null references v2.industry_profiles(id)
  overrides     jsonb not null default '{}'
  updated_at    timestamptz not null default now()
```

2. **No separate profile columns.** `qualification_schema` and `base_ai_prompt` are fields inside `document`, not columns on the profile table. The earlier ER shape is superseded; Mayank's ER update is pending.
3. **Name and phone stay relational** on `leads` and are nullable for this cut. They do not enter `industry_dynamic_data`.
4. **Messages stay rows.** No `conversation.message_history` source of truth.
5. **CASCADE now, RESTRICT later.** `v2` tenant foreign keys use `ON DELETE CASCADE` for this cut.
6. **RLS is target-only.** No shipped isolation claim in this matrix.
7. **Validation is layered:** profile load, write, booking gate, backfill. JSON Schema is one layer; the engine validator is required for nested bounds and cross-references.

---

## 5. Open dependencies

| Dependency | Impact | Owner | Needed by |
|---|---|---|---|
| Mayank ER update for `industry_profiles.document` | ER no longer matches the frozen decision | Mayank | Oct 30 |
| No CI workflow in repo | No CI run URL can be produced | CI/evidence owner | Oct 30 |
| `jsonschema` not installed in the venv or `requirements.lock` | Validator must be stdlib or add a dependency deliberately | Maitri | Oct 30 |
| `remediation/p0-security-fixes` not pushed | Commit SHAs have no public reference | CI/evidence owner | Oct 30 |
| `schema.json` / `v2 plan.md` untracked at repo root | Session text could leak into the package | Evidence owner | Oct 29 |
| RLS implementation owner | Staging isolation proof is a dependency | Tenancy/Security owner | Nov 1 |

---

## 6. Contradiction fix log

| ID | File | Change | Commit |
|---|---|---|---|
| M-01 | `V2_Industry_Profile.md` section 1 | Replaced the "storage gap" paragraph with the option-B storage decision | uncommitted working tree |
| M-02 | `V2_Industry_Profile.md` section 2 | Added the runtime profile artifact and normalization rule | uncommitted working tree |
| M-03/M-04/M-05 | `V2_Industry_Profile.md` section 3 | Added scoring source of truth and code-deviation note | uncommitted working tree |
| M-07 | `V2_Industry_Profile.md` section 4 | Added legacy label-to-key map | uncommitted working tree |
| M-08/M-11 | `V2_Industry_Profile.md` section 2 | Listed validator invariants and engine defaults | uncommitted working tree |
| M-10 | `V2_Industry_Profile.md` section 6 | Marked the "no validator/test" constraint superseded | uncommitted working tree |
| M-12/M-13 | `V2_Migration_and_Security.md` header | Updated status, decision count, and dates | uncommitted working tree |
| M-14/M-19 | `V2_Migration_and_Security.md` section 5 | Added backfill mapping and profile storage | uncommitted working tree |
| M-15 | `V2_Migration_and_Security.md` section 5 | Clarified empty-to-null backfill | uncommitted working tree |

---

## 7. Evidence index

| Evidence | Status | Location |
|---|---|---|
| Matrix | Complete (this file) | `plans/V2_CONSOLIDATED_STATUS_MATRIX.md` |
| Profile JSON parse check | Passed: `python -m json.tool Industry_Profile_Schema.json` | `Industry_Profile_Schema.json` |
| Docs consistency test | Passed: `pytest tests/test_v2_docs_consistency.py -q` (9 passed) | `tests/test_v2_docs_consistency.py` |
| Commit SHAs | Base `bafa585`; docs commit pending | Git |
| CI run URL | Not available: no workflow in repo | N/A |
| Isolated migration dry-run | Not in this pass; due Oct 30 | N/A |
| Live database changes | None | N/A |

---

## 8. Next gates

| Date | Gate | Owner |
|---|---|---|
| 30 October 2026 | Technical evidence package: SHAs, PR/CI URLs, test output, migration dry-run plan | Maitri + Aritro + CI owner |
| 1 November 2026 | Isolated integration run: profile engine, backfill, parity, rollback gates | Maitri + Aritro |
| 2 November 2026 | End-to-end staging demo | Team |

**Demo acceptance:** partial lead is storable; booking is blocked until `required_for_booking` passes; switching `real_estate` to `education` changes stages and scoring; parity check is green; tenant B cannot read tenant A.

---

## Appendix A - Industry engine contract (frozen for implementation)

| Concern | Contract |
|---|---|
| Input | One profile document from `industry_profiles.document`, plus optional tenant overrides |
| Identity | `(key, version)`; published versions immutable |
| Validation | Required top-level keys; `additionalProperties: false`; qualification types/enums/format; scoring rule allowlist and numeric bounds; stage keys unique and positions contiguous; dashboard ids resolve; prompt slots resolve; override paths exist and stay in range |
| Scoring outputs | `conversion_probability`, `lead_temperature`, `engagement_score`, `urgency_level`, `budget_alignment_status`, `requires_manual_review` |
| Engine-owned | `score`, `confidence_score`, `expected_closure_days`, `response_speed_score`, `inactivity_penalty` |
| Booking gate | `name` + `phone` + every `required_for_booking` key; enforced in code before the booking tool call |
| Prompt | `{{field:<key>}}` and `{{tenant:<column>}}` only; unknown slot fails profile load; no raw profile dump, secret, or skip-validation instruction |
| Failure behavior | Invalid profile does not load; invalid write returns 400 or drops the bad key with a warning; invalid backfill JSON is quarantined; a partial object is valid and is not a parity failure |
