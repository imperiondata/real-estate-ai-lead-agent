# V2 Industry Profile

**Phase 1 deliverable: qualification schema, scoring rules, and dashboard config.**

Owner: Maitri. This document is the package narrative. The machine-readable companion is `Industry_Profile_Schema.json`. If they disagree, the JSON is the source of truth for keys, thresholds, and stage ids.

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

Mayank's ER still stores `qualification_schema` and `base_ai_prompt` as two columns. This package JSON is the full profile. Those two columns do not yet hold scoring, dashboard, or pipeline. That is a storage gap. It is not an ER rewrite in this package.

---

## 2. Four validation layers

| Layer | Checks | Failure |
|---|---|---|
| Profile load | Stage keys exist. Dashboard and scoring ids resolve. Prompt slots resolve. Override paths and ranges exist. Unknown rule keys fail. | Profile does not load |
| Write | Types, enums, formats, and unknown keys. `required` is empty, so a partial object is valid. | API returns 400. LLM extraction drops the bad key and warns. The rest may store. |
| Booking gate | Engine requires `name`, `phone`, and every `required_for_booking` key. Code enforces this. The prompt cannot waive it. | Booking tool call is rejected |
| Backfill | Copy partial objects. Quarantine only a wrong type or an unknown key. A missing visit date is not a failure. | Parity failure only for invalid JSON |

`additionalProperties` is false on every qualification schema. A prompt cannot declare a new field.

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

Budget alignment runs only when its `run_when_all` fields are present. Data comes from tenant pricing or tenant catalog. If that data is missing, status is `unknown`. There is no hardcoded city price table in the profile.

A tenant may change only paths listed in `overrides.allowed`, and only inside `overrides.ranges`. Real-estate hot threshold range is 70 to 90. Education is 65 to 85. An unknown rule key fails profile load.

---

## 4. Dashboard

`dashboard_config.kanban` lists stage keys, not labels. Labels come from `pipeline_stages`. A stage write that is not in the active profile fails. It does not fall back to a global real-estate funnel.

Card fields, badges, and filters must be a global column, a key in that profile's qualification schema, or a stage key. An unknown id fails profile load. It does not render blank.

API resolution, when this is implemented later: global columns stay top-level. Industry keys are returned under `attributes.<key>`. The stage is `{key, label}`.

Real-estate stages match today's funnel: `new`, `contacted`, `appointment_scheduled`, `closed_won`, `lost`. Education uses a different set, listed in the JSON.

---

## 5. Prompt rule

Slots are `{{field:<key>}}` and `{{tenant:<column>}}` only. An unknown slot fails profile load. The prompt is advisory. The booking gate is code. The template must not contain a secret, a raw profile dump, or an instruction to skip validation.

The real-estate and education examples are in the JSON.

---

## 6. What this document does not do

- It does not move name or phone into JSONB.
- It does not collapse messages into `conversation.message_history`.
- It does not define RLS, API keys, or the Agency model.
- It does not design the remaining sectors. One live profile and one example profile are enough.
- It does not authorize a live schema change.
- It does not add a validator library, a script, or a test. `python -m json.tool` is the parse check for this package.

`plans/architecture-sprint/` is historical for this package. The V2 markdown and `Industry_Profile_Schema.json` are canonical.
