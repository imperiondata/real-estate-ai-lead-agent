# V2 Industry Profile

**Phase 1 deliverable: qualification schema, scoring rules, and dashboard config.**

Owner: Maitri. This document is the package narrative. The machine-readable companion is `Industry_Profile_Schema.json`. If they disagree, the JSON is the source of truth for keys, thresholds, and stage ids.

Status 29 October 2026: the Phase 1 baseline is frozen. Phase 2 implementation runs in an isolated environment only. Cross-document contradictions are tracked in `plans/V2_CONSOLIDATED_STATUS_MATRIX.md`.

It does not change the database. It does not design tenancy, RLS, or the migration. It does not authorize a live schema change.

The profile is a configuration engine. A prompt cannot add a field, drop a required key, or change a score threshold.

---

## 1. Envelope

One profile document. Not three loose files.

| Section | Job |
|---|---|
| `qualification_schema` | JSON Schema for `leads.industry_dynamic_data`, plus `required_for_booking` |
| `scoring_rules` | Numeric rules the engine executes |
| `dashboard_config` | Field ids and stage keys for cards, filters, badges, and Kanban |
| `pipeline_stages` | `{key, label, position}` for that profile |
| `base_ai_prompt` | Template only. Slots must already exist |
| `overrides` | Dot-paths a tenant may change, and numeric ranges |

`key`, `version`, and `status` identify the document. A published version is immutable. A tenant binds one version. Cache by `(key, version)`.

Global columns are not industry JSON. The engine owns `id`, `tenant_id`, `status`, `created_at`, `name`, and `phone`. Name and phone stay relational. Mayank accepted that on 25 October 2026, and nullable-for-this-cut on 26 October 2026.

**Storage decision, 29 October 2026 (option B).** The runtime profile is one document. `v2.industry_profiles` stores `key`, `version`, `status`, and `document` JSONB, with one immutable row per published `(key, version)`. `v2.tenant_configurations` stores the tenant binding and `overrides` JSONB. The earlier ER shape that kept `qualification_schema` and `base_ai_prompt` as two columns is superseded; Mayank's ER update is requested. No live DDL is performed in this phase.

The JSON file in this repository is a meta-schema with `examples`. It is not itself a tenant's runtime profile. Implementation seeds `real_estate` version `1` and `education` version `1` from those examples and loads them through the same validator.

---

## 2. Four validation layers

| Layer | Checks | Failure |
|---|---|---|
| Profile load | Stage keys exist. Dashboard and scoring ids resolve. Prompt slots resolve. Override paths and ranges exist. Unknown rule keys fail. | Profile does not load |
| Write | Types, enums, formats, and unknown keys. `required` is empty, so a partial object is valid. | API returns 400. LLM extraction drops the bad key and warns. The rest may store. |
| Booking gate | Engine requires `name`, `phone`, and every `required_for_booking` key. Code enforces this. The prompt cannot waive it. | Booking tool call is rejected |
| Backfill | Copy partial objects. Quarantine only a wrong type or an unknown key. A missing visit date is not a failure. | Parity failure only for invalid JSON |

`additionalProperties` is false on every qualification schema. A prompt cannot declare a new field.

JSON Schema is only the structural layer. The profile loader must also enforce the following, because the meta-schema leaves `scoring_rules` sub-objects and `overrides.ranges` open:

- Every scoring rule key is known, and every numeric value is inside its hard bound.
- `temperature.hot_min_probability` is greater than `temperature.warm_min_probability`; every `field_floors` value is 0 to 100.
- Pipeline stage keys are unique, positions are unique and contiguous from 1, and at least one stage exists.
- Every Kanban, card, badge, and filter id is a global column, a qualification-schema key, or a stage key.
- Every prompt slot resolves. `{{field:<key>}}` must exist in the qualification schema; `{{tenant:<column>}}` must be in the tenant-column allowlist.
- Every override path exists in the document, is listed in `overrides.allowed`, is a leaf or list, and every numeric range contains its default.
- `inactivity` and `behavior` are optional in the document. When absent, the engine applies its owned defaults; profiles are normalized to one engine contract.
- `visit_date` and other `format: "date"` values are normalized to `YYYY-MM-DD` before write. An unparsable value is a write failure, not a partial success.

### 2.3 Security boundary (30 October 2026)

Publishing a profile cannot change tenant isolation, API auth, or server-side security controls. This is a closed set, not a warning in the prompt.

`security_boundary` is a const. `locked` is true. `forbidden` is the sorted denylist in `app/industry/profile_guard.py`. The same object is the `const` in `Industry_Profile_Schema.json`. A publish that omits it, unlocks it, or shrinks it does not load.

`overrides.allowed` is a closed enum of scoring and dashboard leaves: hot and warm thresholds, the manual-review floor, and card, filter, and badge id lists. A path outside that enum is rejected. A numeric leaf in `allowed` must have a range, and the published default must sit inside that range.

The loader rejects any other path that normalizes onto the denylist. Case, dots, dashes, and camelCase do not bypass it. `tenant_id`, `api_key_hash`, `rls`, `test_mode`, `twilio_secret`, and the rest of the const are in the set. Stuffing one of those keys inside `scoring_rules` or `overrides.ranges` is still a publish failure. The intersection of `overrides.allowed` and the denylist must be empty.

Proof: `python scripts/validate_industry_profile.py` prints `INDUSTRY_PROFILE_GUARD_OK`. `tests/test_v2_industry_profile_guard.py` rejects each forbidden token. This lock does not implement RLS or API auth. Those stay in `V2_Migration_and_Security.md`.

### 2.1 `real_estate` version `1`

`required` is `[]`. `required_for_booking` is `location`, `budget`, `property_type`, `visit_date`. `intent` is `buy`, `rent`, or `unknown`, and is not required to book. `visit_date` uses `format: "date"`. Name and phone are not in this schema.

The canonical object is the first entry in `Industry_Profile_Schema.json` `examples`.

### 2.2 `education` version `1`

This is an example profile, not a promise to build an education product. It proves a second profile can load on the same engine.

Keys are `course`, `campus`, `fee_band`, and `counselling_date`. `required_for_booking` is `course`, `campus`, and `counselling_date`. Stages are `enquiry`, `contacted`, `counselling_booked`, `enrolled`, and `lost`. Weights, thresholds, cards, and filters differ from real estate. No real-estate key names.

`field_service` is not in this package.

---

## 3. Scoring

The engine reads numbers and field names from `scoring_rules`. It does not parse a paragraph.

Profile-configured outputs: `conversion_probability`, `lead_temperature`, `engagement_score`, `urgency_level`, `budget_alignment_status`, `requires_manual_review`.

Engine-owned in v1, not profile data: `score`, `confidence_score`, `expected_closure_days`, `response_speed_score`, `inactivity_penalty`. The JSON marks `inactivity` and `behavior` as `owner: "engine"` on the real-estate profile.

`real_estate` v1 keeps the live contract: 16 points per filled completeness field, plus 4 for WhatsApp opt-in, cap 100. Hot at 82. Warm at 45. Full-qualify floor 88. Visit floor 82, stored as `field_floors.visit_date`. Manual review when confidence is below 75. Probability is a weighted blend, engagement 0.5 and temperature 0.5, temperature weights 60/40/15, cap 98. The WhatsApp helper's hot cutoff of 70 is not the contract.

**Scoring source of truth, 29 October 2026.** The values above are the contract. Current code is not yet profile-driven: `app/agents/whatsapp_agent.py:178` uses a hot cutoff of 70, `app/intelligence/analytics_engine.py:245` and `app/intelligence/followup_engine.py:173` also use 70, and the 88 full-qualify and 82 visit floors are not applied by `score_lead`. These are implementation gaps tracked in the status matrix, not an alternate contract.

`Lead.score` (`models.py:90`) is a legacy display string. It is not `conversion_probability` and must not be used as the profile score. The two scoring paths, `whatsapp_agent.score_lead` and `app.intelligence.lead_scoring.calculate_lead_score`, converge on the profile adapter or one is explicitly marked legacy before staging.

Budget alignment runs only when its `run_when_all` fields are present. Data comes from tenant pricing or tenant catalog. If that data is missing, status is `unknown`. There is no hardcoded city price table in the profile.

A tenant may change only paths listed in `overrides.allowed`, and only inside `overrides.ranges`. Real-estate hot threshold range is 70 to 90. Education is 65 to 85. An unknown rule key fails profile load.

---

## 4. Dashboard

`dashboard_config.kanban` lists stage keys, not labels. Labels come from `pipeline_stages`. A stage write that is not in the active profile fails. It does not fall back to a global real-estate funnel.

Card fields, badges, and filters must be a global column, a key in that profile's qualification schema, or a stage key. An unknown id fails profile load. It does not render blank.

API resolution, when this is implemented later: global columns stay top-level. Industry keys are returned under `attributes.<key>`. The stage is `{key, label}`.

Real-estate stages match today's funnel: `new`, `contacted`, `appointment_scheduled`, `closed_won`, `lost`. Education uses a different set, listed in the JSON.

The current app, API, and Kanban still use labels (`agent.py:122`, `main.py:1661`, `frontend/src/app/(dashboard)/crm/KanbanBoard.tsx:8`). The compatibility map until they move to the profile is:

| Legacy label | Profile key |
|---|---|
| `New` | `new` |
| `Contacted` | `contacted` |
| `Appointment Scheduled` | `appointment_scheduled` |
| `Closed Won` | `closed_won` |
| `Lost` | `lost` |

A stage write that is not in the tenant's active profile fails. It does not fall back to the global real-estate funnel. The legacy labels are accepted only through this map during the compatibility window.

---

## 5. Prompt rule

Slots are `{{field:<key>}}` and `{{tenant:<column>}}` only. An unknown slot fails profile load. The renderer never leaves a `{{...}}` token in the prompt; an unresolved slot is a load failure, not an empty string.

`{{tenant:name}}` resolves to `clients.company_name` in V1 and `v2.tenants.name` in V2. The slot name is stable across both.

The prompt is advisory. The booking gate is code. A prompt cannot waive `required_for_booking`, add a field, or change a threshold. The template must not contain a secret, a raw profile dump, or an instruction to skip validation. The renderer scans for those before returning the prompt.

The real-estate and education examples are in the JSON.

---

## 6. What this document does not do

- It does not move name or phone into JSONB.
- It does not collapse messages into `conversation.message_history`.
- It does not define RLS, API keys, or the Agency model. Section 2.3 locks those paths out of a publish. It does not implement them.
- It does not design the remaining sectors. One live profile and one example profile are enough.
- It does not authorize a live schema change.
- It did not add a validator library, a script, or a test in Phase 1. That constraint is superseded as of 29 October 2026: Phase 2 requires the loader validator and tests. `python -m json.tool` remains the minimum parse check.

`plans/architecture-sprint/` is historical for this package. The V2 markdown and `Industry_Profile_Schema.json` are canonical.
