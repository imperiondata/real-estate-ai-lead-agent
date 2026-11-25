# V2 Consolidated Status Matrix

**Date:** 29 October 2026
**Updated:** 25 November 2026 (Item 6 closure: assigned Item 4 evidence tier for `ad54d6f` / `POST_CUTOVER_ROLLBACK.log`; explicit 4-category evidence classification added across all matrix, gap-register, and evidence-index rows; `/sales-copilot` remains `Partially Implemented`; M-16 remains `Target-only` / `Proposed`; `V2_DUAL_WRITE=false`)
**Owner:** Maitri (Industry Profile) with Aritro (Migration)
**Audience:** Piyush
**Purpose:** Reconcile the Phase 1 documents with the current code and lock the decisions that Phase 2 implementation depends on.

**Baseline for code checks:** `bafa585` (`docs(v2): add Industry Profile Schema json`).
**Branch:** `remediation/p0-security-fixes` (unified PR #4 head `143c92e6415af8045c230670a8170bd436e18ab8`; Item 6 baseline pulled from `270897a5246f502f46f0fda731d160397ec1e651`).

---

## 1. Frozen baseline

- Piyush has reviewed the Phase 1 package. The architectural baseline is frozen.
- Implementation may proceed in an **isolated environment only**. No live database changes, no Render DDL, no writes to production.
- `V2_DUAL_WRITE` remains `false` by default and is not approved for live use.
- This matrix is a documentation and decision artifact. Every claim in this matrix explicitly separates the four mandated evidence tiers (see Section 2.1) and never claims actual staging/Render execution where none occurred.
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
| `Proposed` | Approved target or design; not implemented or shipped. |
| `Scrubbed` | Scheduled gate removed from this cycle; not an environment-config issue. |
| `CI-Tested on 143c92e` | Verified and passing in full-suite CI run 42046238418 on merged unified head 143c92e. |
| `Fixed 29 Oct` | Documentation contradiction corrected in this pass. |

### 2.1 Four-Category Evidence Classification (Piyush Mandate)

Every row in Sections 3, 5.1, and 7 explicitly distinguishes these four evidence categories:

1. **(1) Local tests** — Unit tests, structural/AST checks, or localhost loopback listener tests executed on a developer workstation (`127.0.0.1` / in-memory).
2. **(2) Synthetic database fixtures** — Isolated, throwaway local PostgreSQL databases on `127.0.0.1` (e.g., `v2_isolation_drill`, `v2_process_restart`, `v2_post_cutover_rollback`, `v2_nov1_drill`, `v2_nov2_reliability`, `v2_app_rollback`) seeded with synthetic fixtures and dropped afterward; never touches `realestate_db` or Render.
3. **(3) CI-tested application behavior** — Automated GitHub Actions workflow runs (`v2-isolation` / `v2-full-suite`) executing application modules and pytest assertions in CI runners.
4. **(4) Actual staging behavior** — Execution against the live staging / Render deployment (`Not executed on staging` across all V2 items unless explicitly verified on Render).

---

## 3. Matrix

| ID | Claim / contradiction | Source | Current code reality | Status | Evidence Tier Breakdown `(1) Local / (2) Synthetic DB / (3) CI App / (4) Staging` | Owner | Resolution |
|---|---|---|---|---|---|---|---|
| M-01 | The profile is one full envelope, but Mayank's ER stores `qualification_schema` and `base_ai_prompt` as two columns and the document calls this a "storage gap". | `V2_Industry_Profile.md:19-30` | Option B decided (`industry_profiles.document` JSONB); file loader exists; DB table not yet created in V1. | `Decided` | (1) Local test (`test_v2_docs_consistency.py`); (2) Synthetic DB: None; (3) CI App (`v2-full-suite` docs check); (4) Staging: **Not executed on staging** | Maitri + Aritro | Runtime profile is one `industry_profiles.document` JSONB row per `(key, version)`. Tenant overrides live in `tenant_configurations.overrides`. Two-column storage is superseded. Mayank ER update requested. |
| M-02 | `Industry_Profile_Schema.json` is a meta-schema with `examples`, not a runtime profile instance. | `Industry_Profile_Schema.json:100-246` | File loader (`FileProfileStore` / `profile_loader.py`) reads `examples`; DB-backed profile seeding (`v2.industry_profiles` / `DbProfileStore`) is not implemented. | `Target-only` (`Proposed`) | (1) Local test (file loader unit tests); (2) Synthetic DB: None (DB store not shipped); (3) CI App (`test_v2_industry_profile_scorer.py`); (4) Staging: **Not executed on staging** | Maitri | Seed both profiles from `examples` into `v2.industry_profiles` (`DbProfileStore`) in Phase 2. DB-backed seeding remains strictly `Target-only` / `Proposed`. |
| M-03 | Hot threshold is 82. | `V2_Industry_Profile.md:69`; `Industry_Profile_Schema.json:135` | `score_lead` in `app/agents/whatsapp_agent.py` is profile-driven; uses 82 hot cut from `real_estate` v1; literal 70 removed. | `CI-Tested on 143c92e` | (1) Local test (`SCORING_MATH_PROOF.log`); (2) Synthetic DB: None (`score_lead` returns dict); (3) CI App (`v2-full-suite` run `42046238418` on `143c92e` & `45584681163` on `ad54d6f`); (4) Staging: **Not executed on staging** | Maitri | 82 is canonical and profile-driven. Verified in CI run `42046238418` on `143c92e` and `SCORING_MATH_PROOF.md`. |
| M-04 | Warm is 45, full-qualify floor is 88, visit floor is 82. | `V2_Industry_Profile.md:69`; `Industry_Profile_Schema.json:134-139` | `score_lead` applies profile cuts and floors: 45 warm cut, 88 full-qualify floor (loaded dynamically, not hardcoded), and 82 visit floor. | `CI-Tested on 143c92e` | (1) Local test (`SCORING_MATH_PROOF.log`); (2) Synthetic DB: None (`score_lead` pure return); (3) CI App (`v2-full-suite` run `42046238418` on `143c92e` & `45584681163` on `ad54d6f`); (4) Staging: **Not executed on staging** | Maitri | Scoring reads `temperature.*` from profile. Verified in CI run `42046238418` on `143c92e`. |
| M-05 | `score` is engine-owned scoring data. | `V2_Industry_Profile.md:67` | `models.Lead.score` is a String defaulting to `"Low"` (`models.py:90`); numeric outputs are separate columns. | `Contradicts` | (1) Local test (`SCORING_MATH_PROOF.log` outputs); (2) Synthetic DB: None; (3) CI App (`v2-full-suite`); (4) Staging: **Not executed on staging** | Maitri | Keep `Lead.score` as a legacy display field. Profile scoring writes `conversion_probability`, `lead_temperature`, `engagement_score`, `urgency_level`, and `budget_alignment_status`. |
| M-06 | The profile has no hardcoded city price table; budget alignment uses tenant pricing/catalog and returns `unknown` when data is missing. | `V2_Industry_Profile.md:71`; `Industry_Profile_Schema.json:145-149` | `app/intelligence/budget_alignment.py:61-80` uses `PUNE_LOCATIONS` from `app/data_manager.py`. | `Contradicts` | (1) Local test: Code inspection only; (2) Synthetic DB: None; (3) CI App: None for V2 catalog cutover; (4) Staging: **Not executed on staging** | Maitri | Target is tenant `PricingRule`/`InventoryUnit`. No Pune table in the profile. Treat the current lookup as a known deviation. |
| M-07 | Kanban uses stage keys from `pipeline_stages`; unknown stage writes fail. | `V2_Industry_Profile.md:79-85`; `Industry_Profile_Schema.json:154-166` | `agent.FUNNEL_STAGES` is label-based (`agent.py:122`); `main.py:1661` validates against it; `frontend/src/app/(dashboard)/crm/KanbanBoard.tsx:8` hardcodes the same labels; `main.py:944` writes `"New"`. | `Contradicts` | (1) Local test (`test_dashboard_stage_keys_resolve` structural only); (2) Synthetic DB: None; (3) CI App (`test_v2_docs_consistency.py`); (4) Staging: **Not executed on staging** | Maitri | Profile keys are canonical. Publish the legacy label-to-key map and reject unknown stages. Frontend follows the profile or the API exposes stages. |
| M-08 | Unknown rule keys fail profile load; override paths and ranges are validated. | `V2_Industry_Profile.md:38`; `Industry_Profile_Schema.json:90-98` | Override range validation enforced in `app/industry/profile_guard.py` (`validate_override_value`) and `profile_loader.py`. Nested rule-key validation remains Phase 2. | `CI-Tested on 143c92e` | (1) Local test (`test_v2_industry_profile_guard.py`, `test_v2_industry_profile_scorer.py`); (2) Synthetic DB: None; (3) CI App (`v2-full-suite` run `42046238418` on `143c92e`, 27-test provenance gate); (4) Staging: **Not executed on staging** | Maitri | Override range validation implemented and passing in `tests/test_v2_industry_profile_guard.py` & `test_v2_industry_profile_scorer.py` on `143c92e`. |
| M-09 | The booking gate is code-enforced and separate from storage validation. | `V2_Industry_Profile.md:40`; `Industry_Profile_Schema.json:117-118` | `agent.is_fully_qualified` and `agent.py:661-662` hardcode the six fields; the prompt also instructs the model. There is no profile-driven gate. | `Partial` | (1) Local test (`test_partial_leads_are_valid_but_booking_keys_are_separate` schema check only); (2) Synthetic DB: None; (3) CI App (`v2-full-suite`); (4) Staging: **Not executed on staging** | Maitri | `required_for_booking` comes from the profile. `name` and `phone` stay global. The gate runs before any booking tool call. |
| M-10 | Phase 1 does not add a validator library, script, or test. | `V2_Industry_Profile.md:104` | V2 validators and tests now exist in repo (`profile_guard.py`, `test_v2_*.py`). | `Superseded` | (1) Local test; (2) Synthetic DB: None; (3) CI App (`v2-full-suite`); (4) Staging: **Not executed on staging** | Maitri | Phase 2 requires a validator and tests. Phase 1's "docs only" constraint no longer applies. |
| M-11 | Every profile supports `inactivity` and `behavior`, or the engine owns them. | `Industry_Profile_Schema.json:120-153` vs `:193-224` | `education` omits both blocks; the meta-schema does not require them. | `Target-only` | (1) Local test: None; (2) Synthetic DB: None; (3) CI App: None; (4) Staging: **Not executed on staging** | Maitri | Missing blocks mean engine-owned defaults. The loader normalizes every profile to the same engine contract. |
| M-12 | No live schema change is allowed until Piyush reviews the package. | `V2_Migration_and_Security.md:7-9` | Phase 1 is reviewed. Live production/Render schema is unchanged. | `Fixed 29 Oct` | (1) Local test (`test_stale_contradictions_are_removed`); (2) Synthetic DB: None; (3) CI App (`v2-full-suite`); (4) Staging: **Not executed on staging** (live DDL banned) | Aritro | Status updated: approved for isolated implementation; live schema changes remain banned. |
| M-13 | Mayank accepted "all four decisions"; dates mix 25 and 26 October. | `V2_Migration_and_Security.md:9`, `:281-291` | Five decisions are listed in section 12. | `Fixed 29 Oct` | (1) Local test (`test_stale_contradictions_are_removed`); (2) Synthetic DB: None; (3) CI App (`v2-full-suite`); (4) Staging: **Not executed on staging** | Aritro | Text now says five decisions and uses "accepted 25 October 2026; clarified 26 October 2026". |
| M-14 | Industry keys are strings; `intent` is `buy|rent|unknown`; `visit_date` has `format: date`. | `Industry_Profile_Schema.json:105-118` | V1 stores `budget`, `intent`, `visit_date` as free-text strings (`models.py:86-91`). | `Target-only` | (1) Local test (`test_v2_migration_dry_run.py`); (2) Synthetic DB (`v2_nov1_drill` dry run); (3) CI App (`v2-full-suite`); (4) Staging: **Not executed on staging** | Aritro | Backfill mapping is defined in `V2_Migration_and_Security.md` section 5.1: trim, empty to null, intent mapping, date normalization, quarantine only wrong type/format or unknown key. |
| M-15 | Name and phone are relational and nullable for this cut. | `V2_Migration_and_Security.md:117`; `V2_Industry_Profile.md:28` | `models.Lead.name` and `.phone` are already nullable (`models.py:84-85`). | `Aligned` | (1) Local test (`test_v2_migration_dry_run.py`); (2) Synthetic DB (`v2_nov1_drill`); (3) CI App (`v2-full-suite`); (4) Staging: **Not executed on staging** | Aritro | Backfill copies empty values as null, never `""`. |
| M-16 | `FORCE ROW LEVEL SECURITY`, a non-owner app role, and `app.current_tenant_id` isolate tenants. | `V2_Migration_and_Security.md:192-216` | No RLS or tenant session variable exists in V1 (`database.py` / `main.py` still filter by `client_id` only). `app.migration.tenant_context` targets V2 only. | `Target-only` (`Proposed`; Not executed on staging) | (1) Local test (`test_v2_tenant_context.py`, `test_v2_agency_isolation.py`); (2) Synthetic DB (`ISOLATION_DRILL.log`, `RLS_CANONICAL_TENANT.log` on throwaway `v2_isolation_drill`); (3) CI App (`v2-isolation` run `41316092168`, `v2-full-suite`); (4) Staging: **Not executed on staging** (`v1_render_rls=not_shipped`) | Tenancy/Security owner | Do not claim isolation is shipped on V1 or Render. Design accepted 25 October; V1 and Render enforce nothing. `ISOLATION_DRILL.log` and `RLS_CANONICAL_TENANT.log` prove policy shape on synthetic DB fixtures only. |
| M-17 | The evidence package needs CI run URLs and commit SHAs. | Oct 30 requirement | `.github/workflows/v2-isolation.yml` and `.github/workflows/v2-full-suite.yml` are present; CI run URLs and 40-char SHAs recorded. | `Fixed 1 Nov` | (1) Local test (`test_matrix_has_no_shipped_isolation_claim`); (2) Synthetic DB: N/A; (3) CI App (`41316092168`, `42046238418`, `45584681163`); (4) Staging: **Not executed on staging** | CI/evidence owner | Workflows added and passing; GitHub runs recorded in Section 7. |
| M-18 | `schema.json` is a repository artifact. | Repo root | `schema.json` is an untracked 5.3 MB UTF-16 opencode session export, not a DB schema. It contains prior conversation text. | `Blocked` | (1) Local test: Repo hygiene rule; (2) Synthetic DB: N/A; (3) CI App: N/A; (4) Staging: **Not executed on staging** | Evidence owner | Move it outside the repo or ignore it. Do not commit, copy into evidence packages, or submit it. |
| M-19 | `webhook_logs` has no `client_id` in V1; V2 adds `tenant_id`. | `V2_Migration_and_Security.md:36`, `:176` | V1 table has no tenant column. | `Target-only` | (1) Local test (`test_every_v1_table_and_every_lead_column_is_classified`); (2) Synthetic DB: Shadow schema definition only; (3) CI App (`v2-full-suite`); (4) Staging: **Not executed on staging** | Aritro | Create `v2.webhook_logs.tenant_id` in the shadow schema only. No live alter. |
| M-20 | One scoring contract. | `V2_Industry_Profile.md:63-69` | `score_lead` in `app/agents/whatsapp_agent.py` is the profile-driven v3 scoring path; `lead_scoring` marked legacy. | `CI-Tested on 143c92e` | (1) Local test (`SCORING_MATH_PROOF.log`); (2) Synthetic DB: None; (3) CI App (`v2-full-suite` run `42046238418` on `143c92e` & `45584681163` on `ad54d6f`); (4) Staging: **Not executed on staging** | Maitri | v3 chat/scoring path (`whatsapp_agent.score_lead`) is profile-driven and verified in CI on `143c92e`; legacy non-profile path isolated. |

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
| CI isolation workflow | Added, path-widened (`app/migration/**`, `app/industry/**`, `scripts/**`), passing; run URL recorded | CI/evidence owner | Done |
| `jsonschema` not installed in the venv or `requirements.lock` | Validator uses stdlib enforcement | Maitri | Done |
| `remediation/p0-security-fixes` pushed to the production remote | Commit SHAs have a remote reference | CI/evidence owner | Done |
| `schema.json` / `v2 plan.md` untracked at repo root | Session text could leak into the package | Evidence owner | Excluded from evidence package |
| Engine-level RLS implementation (Phase 2) | Policy-shape drill is synthetic evidence only; no V1 or Render enforcement | Maitri | Phase 2 (no date) |

### 5.1 Gap register

| Gap | Classification | Owner | Severity | Remediation | Target closure | Evidence Tier Breakdown `(1) Local / (2) Synthetic DB / (3) CI App / (4) Staging` & Notes |
|---|---|---|---|---|---|---|
| M-02: seed `real_estate/1` and `education/1` runtime profiles | `Target-only` (`Proposed`) | Maitri | Medium | Loader reads the schema `examples`; DB store (`v2.industry_profiles`) later | Phase 2 (no date) | **(1)** Local test: file loader; **(2)** Synthetic DB: None; **(3)** CI App: file loader unit tests; **(4)** Staging: **Not executed on staging**. DB seeding remains Phase 2. |
| M-03: hot threshold is 82, not 70 | `CI-Tested on 143c92e` | Maitri | High | Profile loader + `score_lead` cuts | Closed on `143c92e` | **(1)** Local test (`SCORING_MATH_PROOF.log`); **(2)** Synthetic DB: None; **(3)** CI App (runs `42046238418`, `45584681163`); **(4)** Staging: **Not executed on staging**. 70 removed from `score_lead`. |
| M-04: full-qualify floor 88 and visit floor 82 | `CI-Tested on 143c92e` | Maitri | High | `score_lead` loads and applies `full_qualify_floor` and `field_floors.visit_date` | Closed on `143c92e` | **(1)** Local test (`SCORING_MATH_PROOF.log`); **(2)** Synthetic DB: None; **(3)** CI App (runs `42046238418`, `45584681163`); **(4)** Staging: **Not executed on staging**. Dynamic loading proved (`88` and `90` tests). |
| M-05: `Lead.score` is a legacy display field | `Contradicts` | Maitri | Medium | Keep `Lead.score` legacy; profile writes numeric columns | Phase 2 (no date) | **(1)** Local test (`SCORING_MATH_PROOF.log`); **(2)** Synthetic DB: None; **(3)** CI App (`v2-full-suite`); **(4)** Staging: **Not executed on staging**. |
| M-06: hardcoded Pune price table | `Contradicts` | Maitri | High | Tenant `PricingRule` / `InventoryUnit` only | Phase 2 (no date) | **(1)** Local test: Code audit; **(2)** Synthetic DB: None; **(3)** CI App: None; **(4)** Staging: **Not executed on staging**. Current Pune lookup remains a known deviation. |
| M-07: stage keys vs label-based funnel | `Contradicts` | Maitri | Medium | Publish label-to-key map; reject unknown stages | Phase 2 (no date) | **(1)** Local test (schema check); **(2)** Synthetic DB: None; **(3)** CI App (`test_v2_docs_consistency.py`); **(4)** Staging: **Not executed on staging**. |
| M-08: profile validator (override range validation) | `CI-Tested on 143c92e` | Maitri | High | Loader + override-value range check | Closed on `143c92e` | **(1)** Local test (`test_v2_industry_profile_guard.py`); **(2)** Synthetic DB: None; **(3)** CI App (runs `42046238418`, `45584681163`); **(4)** Staging: **Not executed on staging**. Nested rule-key validation remains Phase 2. |
| M-09: profile-driven booking gate | `Partial` | Maitri | High | `required_for_booking` from profile before booking | Phase 2 (no date) | **(1)** Local test (schema check); **(2)** Synthetic DB: None; **(3)** CI App (`v2-full-suite`); **(4)** Staging: **Not executed on staging**. `name` and `phone` stay global. |
| M-10: Phase 1 "no validator/test" constraint | `Superseded` | Maitri | Low | No action | n/a | **(1)** Local test; **(2)** Synthetic DB: None; **(3)** CI App (`v2-full-suite`); **(4)** Staging: **Not executed on staging**. |
| M-11: `inactivity` / `behavior` engine defaults | `Target-only` | Maitri | Low | Normalize every profile to the engine contract | Phase 2 (no date) | **(1)** Local test: None; **(2)** Synthetic DB: None; **(3)** CI App: None; **(4)** Staging: **Not executed on staging**. |
| M-14: backfill mapping | `Target-only` | Aritro | Medium | Section 5.1 trim/null/intent/date mapping | Aritro migration closure | **(1)** Local test (`test_v2_migration_dry_run.py`); **(2)** Synthetic DB (`NOV1_ISOLATED_DRILL.log`); **(3)** CI App (`v2-full-suite`); **(4)** Staging: **Not executed on staging**. |
| M-16: engine-level RLS implementation | `Target-only` (`Proposed`; Not executed on staging) | Maitri | Moderate | Phase 2 implementation | Phase 2 (no date) | **(1)** Local test (`test_v2_tenant_context.py`, `test_v2_agency_isolation.py`); **(2)** Synthetic DB (`ISOLATION_DRILL.log`, `RLS_CANONICAL_TENANT.log` on `v2_isolation_drill`); **(3)** CI App (`v2-isolation` run `41316092168`, `v2-full-suite`); **(4)** Staging: **Not executed on staging** (`v1_render_rls=not_shipped`). |
| M-18: `schema.json` session export at repo root | `Blocked` | Evidence owner | Low | Move outside the repo or ignore; exclude from evidence package | Before evidence submission | **(1)** Local check; **(2)** Synthetic DB: N/A; **(3)** CI App: N/A; **(4)** Staging: **Not executed on staging**. Do not commit or submit it. |
| M-19: `webhook_logs.tenant_id` | `Target-only` | Aritro | Low | Add `v2.webhook_logs.tenant_id` in the shadow schema only | Aritro migration closure | **(1)** Local test (`test_v2_migration_dry_run.py`); **(2)** Synthetic DB: Shadow schema DDL; **(3)** CI App (`v2-full-suite`); **(4)** Staging: **Not executed on staging**. No live alter. |
| M-20: two scoring paths (score_lead v3 path) | `CI-Tested on 143c92e` | Maitri | High | `score_lead` is the profile-driven v3 path; non-profile path marked legacy | Closed on `143c92e` | **(1)** Local test (`SCORING_MATH_PROOF.log`); **(2)** Synthetic DB: None; **(3)** CI App (runs `42046238418`, `45584681163`); **(4)** Staging: **Not executed on staging**. |
| Analytics recommended-action and follow-up priority still use >= 70 | `Contradicts` | Maitri | Low | Leave for a later pass. The profile has no key for these bands. | Phase 2, no date | **(1)** Local test: Code audit; **(2)** Synthetic DB: None; **(3)** CI App: None; **(4)** Staging: **Not executed on staging**. Not the hot threshold. |
| Full-suite CI | `green` at `143c92e` & `ad54d6f` | CI/Team | High | Full-suite checks passed on unified head `143c92e` (run `42046238418`: 520 passed, 3 skipped, 0 failed) and on `ad54d6f` (run `45584681163`, 27-test provenance gate) | [run 42046238418](https://github.com/imperiondata/real-estate-ai-lead-agent/actions/runs/42046238418) / [run 45584681163](https://github.com/imperiondata/real-estate-ai-lead-agent/actions/runs/45584681163) | **(1)** Local test: matching pytest suite; **(2)** Synthetic DB: CI Postgres 18 & throwaway drill DBs; **(3)** CI App: GitHub Actions green; **(4)** Staging: **Not executed on staging**. |
| 2 November staging demo | `Scrubbed` | Team | High | No action this cycle | n/a (scrubbed) | **(1)-(3)** N/A; **(4)** Staging: **Scrubbed / Not executed on staging**. |
| KMS, HIPAA, PCI controls | `Proposed` | Mayank | High | Compliance controls program | Q1 2027 | **(1)-(3)** Not shipped; **(4)** Staging: **Not executed on staging**. |
| Live migration and read cutover (`V2_DUAL_WRITE=false`) | `Blocked` (`Proposed` / `Target-only`) | Aritro | High | Approval plus cutover plan | Blocked; no date (`V2_DUAL_WRITE=false`) | **(1)** Local test (`test_v2_migration_dry_run.py`); **(2)** Synthetic DB (`NOV1_ISOLATED_DRILL.log`, `NOV2_RELIABILITY_DRILL.log`, `DUAL_WRITE_CALL_PATH.log`, `POST_CUTOVER_ROLLBACK.log`); **(3)** CI App (`v2-full-suite` run `45584681163`); **(4)** Staging: **Not executed on staging**. Global `V2_DUAL_WRITE=false`. |
| `/sales-copilot` timeline and summary UI | `Partially Implemented` | Maitri | Medium | Same-origin timeline fetch, or a proxy that forwards the HttpOnly `jwt` cookie. Replace the static summary panel with the selected lead. | Before evidence close | **(1)** Local test: Loopback verification only; **(2)** Synthetic DB: None; **(3)** CI App: Not covered in frontend E2E; **(4)** Staging: **Not executed on staging**. Timeline request exists (`GET /api/v1/events/leads/{id}/timeline`), static John Doe summary placeholder, cross-origin cookie missing on `NEXT_PUBLIC_API_URL`. Do not cite as TENANT DELIVERY proof. |

The `v2-isolation` workflow ran `test_v2_agency_isolation.py` and has been widened (`app/migration/**`, `app/industry/**`, `scripts/**`). Neither CI workflow executes tests against live staging or Render.

---

## 6. Contradiction fix log

| ID | File | Change | Commit |
|---|---|---|---|
| M-01 | `V2_Industry_Profile.md` section 1 | Replaced the "storage gap" paragraph with the option-B storage decision | `aed2fd6` |
| M-02 | `V2_Industry_Profile.md` section 2 | Added the runtime profile artifact and normalization rule | `aed2fd6` |
| M-03/M-04/M-05 | `V2_Industry_Profile.md` section 3 | Added scoring source of truth and code-deviation note | `aed2fd6` |
| M-07 | `V2_Industry_Profile.md` section 4 | Added legacy label-to-key map | `aed2fd6` |
| M-08/M-11 | `V2_Industry_Profile.md` section 2 | Listed validator invariants and engine defaults | `aed2fd6` |
| M-10 | `V2_Industry_Profile.md` section 6 | Marked the "no validator/test" constraint superseded | `aed2fd6` |
| M-12/M-13 | `V2_Migration_and_Security.md` header | Updated status, decision count, and dates | `aed2fd6` |
| M-14/M-19 | `V2_Migration_and_Security.md` section 5 | Added backfill mapping and profile storage | `aed2fd6` |
| M-15 | `V2_Migration_and_Security.md` section 5 | Clarified empty-to-null backfill | `aed2fd6` |

---

## 7. Evidence index

| Evidence | Status | Evidence Tier `(1: Local / 2: Synthetic DB / 3: CI App / 4: Staging)` | Location |
|---|---|---|---|
| Matrix | Complete (this file) | Documentation / Reconciliation Matrix (Not staging) | `plans/V2_CONSOLIDATED_STATUS_MATRIX.md` |
| Profile JSON parse check | Passed: `python -m json.tool Industry_Profile_Schema.json` | **(1)** Local test; **(2)** Synthetic DB: N/A; **(3)** CI App (`v2-full-suite`); **(4)** Staging: **Not executed on staging** | `Industry_Profile_Schema.json` |
| Docs consistency test | Passed: `pytest tests/test_v2_docs_consistency.py -q` (10 passed) | **(1)** Local test; **(2)** Synthetic DB: N/A; **(3)** CI App (`v2-full-suite` provenance); **(4)** Staging: **Not executed on staging** | `tests/test_v2_docs_consistency.py` |
| Commit SHAs | Base `bafa585`; Oct 30 docs `aed2fd6`; 1 Nov drill `15b854c`; isolation proof `bf456fe`; unified head `143c92e6415af8045c230670a8170bd436e18ab8` (PR #4); matrix sync `eb02435941111d7b3e3753449af863dd3908f601`; rollback CI `ad54d6fec8c6a69b468af19c6c4f5b6995c66a13`; evidence closure `270897a5246f502f46f0fda731d160397ec1e651` | Git provenance (remediation branch) | Git |
| CI run URL | Isolation passed: https://github.com/imperiondata/real-estate-ai-lead-agent/actions/runs/41316092168 (`v2-isolation`, `bf456fe`). Full-suite passed on `143c92e`: https://github.com/imperiondata/real-estate-ai-lead-agent/actions/runs/42046238418 (`v2-full-suite`, 520 passed, 3 skipped, 0 failed) and on `ad54d6f`: https://github.com/imperiondata/real-estate-ai-lead-agent/actions/runs/45584681163 (`v2-full-suite`, 27-test provenance gate). | **(1)** Local suite parity; **(2)** Synthetic DB (CI Postgres 18 / throwaway drill DBs); **(3)** CI App (GitHub Actions green); **(4)** Staging: **Not executed on staging** | `.github/workflows/v2-isolation.yml`, `.github/workflows/v2-full-suite.yml` |
| Isolated migration dry-run | Passed 1 Nov: `NOV1_DRILL_PASS`; tenant 2 mismatch reported, three crash phases durable and idempotent. RLS not executed. | **(1)** Local drill script; **(2)** Synthetic DB (`v2_nov1_drill` on `127.0.0.1`); **(3)** CI App (`test_v2_migration_dry_run.py`); **(4)** Staging: **Not executed on staging** | `plans/evidence/NOV1_ISOLATED_DRILL.log` |
| Isolated agency-isolation proof | Passed 1 Nov: `ISOLATION_DRILL_PASS`; cross-agency isolation, agency-admin restrictions, and tenant-consistent FKs. Policy shape only; no V1 or Render change. | **(1)** Local test; **(2)** Synthetic DB (`v2_isolation_drill` on `127.0.0.1`); **(3)** CI App (`v2-isolation` run `41316092168`); **(4)** Staging: **Not executed on staging** | `plans/evidence/ISOLATION_DRILL.log` |
| Reliability drill | Passed 2 Nov: `RELIABILITY_DRILL_PASS`; update, delete, concurrent writes, new-connection read-back, retry, and SQL rollback. Not a V1 or Render change. | **(1)** Local test (`test_v2_reliability_drill.py`); **(2)** Synthetic DB (`v2_nov2_reliability` on `127.0.0.1`); **(3)** CI App (`v2-full-suite`); **(4)** Staging: **Not executed on staging** | `plans/evidence/NOV2_RELIABILITY_DRILL.log` |
| Application rollback proof (pre-cutover) | Passed 4 Nov: `APP_ROLLBACK_PASS`; dual-write off, reads on V1, shadow schema dropped, checksum unchanged. Read through `serialize_lead`; no HTTP server started. | **(1)** Local script (`prove_v2_app_rollback.py`); **(2)** Synthetic DB (`v2_app_rollback` on `127.0.0.1`); **(3)** CI App (`test_rollback_drops_the_shadow_and_leaves_v1`); **(4)** Staging: **Not executed on staging** | `plans/evidence/NOV4_APP_ROLLBACK.log` |
| Scoring math proof (Item 1) | 24 Nov: blend caps at 80; `full_qualify_floor` is loaded from the profile (88); loaded floor 90 returns 90; removing key returns 80/warm; 81/82 cut and visit floor 82 covered. 20 targeted tests. | **(1)** Local test (`SCORING_MATH_PROOF.log`: 20 passed); **(2)** Synthetic DB: None; **(3)** CI App (`v2-full-suite` runs `42046238418`, `45584681163`); **(4)** Staging: **Not executed on staging** | `plans/evidence/SCORING_MATH_PROOF.md`, `plans/evidence/SCORING_MATH_PROOF.log` |
| Local tenant delivery proof (Item 5) | 24 Nov: loopback SMTP and HTTP listeners on `127.0.0.1`; receipts `451→250` and `503→200`, `replay_receipts=0`, `key_absent_from_client=true`. Not a `TEST_MODE` recorded row. | **(1)** Local test (`prove_tenant_delivery_local.py` on `127.0.0.1`, `test_tenant_delivery.py`, `test_widget_api_key_server_side.py`); **(2)** Synthetic DB (fake local tenant row deleted afterward); **(3)** CI App (`v2-full-suite`); **(4)** Staging: **Not executed on staging** | `plans/evidence/TENANT_DELIVERY_LOCAL.md`, `plans/evidence/TENANT_DELIVERY_LOCAL.log` |
| Canonical tenant GUC and RLS proof (Item 2) | 24 Nov: one tenant GUC `app.current_tenant_id`; `rolsuper=false`, `rolbypassrls=false`, `relforcerowsecurity=true`; app privileges SELECT/INSERT/UPDATE only; missing and invalid settings return 0 rows. Not V1 or Render. | **(1)** Local test (`test_v2_tenant_context.py`, `test_v2_agency_isolation.py`); **(2)** Synthetic DB (`v2_isolation_drill` on `127.0.0.1`); **(3)** CI App (`v2-full-suite`); **(4)** Staging: **Not executed on staging** (`v1_render_rls=not_shipped`) | `plans/evidence/RLS_CANONICAL_TENANT.md`, `plans/evidence/RLS_CANONICAL_TENANT.log` |
| Dual-write call path proof (Item 3) | 24 Nov: cross-PID process termination & recovery; `live_dual_write_flag=false` observed; `order=injected production_order=v1_then_v2`; `duplicate=false`. | **(1)** Local test (`test_v2_process_restart.py`, `test_v2_dual_write_call_path.py`); **(2)** Synthetic DB (`v2_process_restart` on `127.0.0.1`); **(3)** CI App (`v2-full-suite`); **(4)** Staging: **Not executed on staging** | `plans/evidence/DUAL_WRITE_CALL_PATH.md`, `plans/evidence/DUAL_WRITE_CALL_PATH.log` |
| Post-cutover rollback drill (Item 4) | Passed 25 Nov: `POST_CUTOVER_ROLLBACK_PASS`; `switch_reads_to_v1` with dual-write still on and shadow retained, one new row written V1-then-V2, newest V1 row read through `serialize_lead`, original and table checksums unchanged, no lost or duplicated row. `v2-full-suite` green on `ad54d6f` (run `45584681163`), including 27-test provenance gate. | **Assigned Tier:** `Local test + Synthetic DB fixture + CI-tested application behavior (Not executed on staging)` — **(1)** Local test (`test_v2_post_cutover_rollback.py`); **(2)** Synthetic DB (`v2_post_cutover_rollback` on `127.0.0.1`); **(3)** CI App (`v2-full-suite` run `45584681163` on `ad54d6f`); **(4)** Staging: **Not executed on staging** | `plans/evidence/POST_CUTOVER_ROLLBACK.md`, `plans/evidence/POST_CUTOVER_ROLLBACK.log` |
| Scorer RCA (82 unreachable / v3 used 70) | 4 Nov: profile-driven cuts + floors; 44 targeted tests; DB proof 88/hot and 72/warm; `/ai-chat` + `/widget` wiring proven. Live LLM reply hit upstream Gemini `503`. | **(1)** Local test; **(2)** Synthetic DB (local deleted test rows); **(3)** CI App (`v2-full-suite` runs `42046238418`, `45584681163`); **(4)** Staging: **Not executed on staging** | `plans/evidence/NOV4_SCORER_RCA.md` |
| Live database changes | None | **(1)-(4)** No live DDL, no Render mutations, `V2_DUAL_WRITE=false` | N/A |

---

## 8. Next gates

| Date | Gate | Owner |
|---|---|---|
| 30 October 2026 | Technical evidence package: SHAs, PR/CI URLs, test output, migration dry-run plan | Maitri + Aritro + CI owner |
| 1 November 2026 | Isolated integration run: profile engine, backfill, parity, rollback gates | Maitri + Aritro |
| 2 November 2026 | End-to-end staging demo — `Scrubbed`. Reason: widget, locked-profile scorer, and tenant email are not in the running build. Not an environment-config issue. | Team |

**Demo acceptance (not demonstrated; 2 November demo scrubbed):** partial lead is storable; booking is blocked until `required_for_booking` passes; switching `real_estate` to `education` changes stages and scoring; parity check is green; tenant B cannot read tenant A.

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
