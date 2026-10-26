# V2 Industry Profile

**Phase 1 deliverable: qualification schema, scoring rules, and dashboard config.**

Owner: Maitri. This document defines the Industry Profile shape and one real profile, `real_estate` version `1`. It does not change the database. It does not design tenancy, RLS, or the migration.

The profile is a configuration engine. A prompt cannot add a field, drop a required key, or change a score threshold.

---

## 1. What an Industry Profile is

An Industry Profile is three JSON documents plus a constrained prompt template.

| Document | Stored on | Job |
|---|---|---|
| `qualification_schema` | `industry_profiles.qualification_schema` | JSON Schema for `leads.industry_dynamic_data` |
| `scoring_rules` | profile JSON, beside the schema | Numeric rules the engine executes |
| `dashboard_config` | profile JSON, beside the schema | Field ids for columns, cards, filters, and badges |
| `base_ai_prompt` | `industry_profiles.base_ai_prompt` | Template only. Slots must already exist |

`industry_profiles` rows are versioned. A tenant points at one profile version. Tenant `config_overrides` may change labels, column order, and a threshold inside a range the profile allows. Overrides may not remove a required qualification field or add a free-form key.

Global lead columns are not industry JSON. The engine owns `id`, `tenant_id`, `status`, `created_at`, `name`, and `phone`. Name and phone stay relational. Mayank accepted that placement on 25 October 2026. Claim-check and CRM sync read them as columns. It is not an industry-schema decision.

---

## 2. Qualification schema

The application validates `industry_dynamic_data` against `qualification_schema` before insert or update. Validation failure rejects the write. The database does not accept the row and then hope a prompt was well behaved.

Rules for every profile:

- The document is a JSON Schema.
- `additionalProperties` is false.
- A required key must be present and non-empty.
- Unknown keys are rejected.
- The prompt cannot declare a new field.

### 2.1 `real_estate` version `1`

Booking still requires name and phone. Those checks live in the engine, not in this schema.

Industry keys:

| Key | Type | Required to book | Notes |
|---|---|---|---|
| `location` | string | yes | Canonical area after the existing location normalizer |
| `budget` | string | yes | Existing normalizer: lakhs, crores, thousands, per-month |
| `property_type` | string | yes | Existing extractor |
| `intent` | string enum `buy`, `rent`, `unknown` | no | Used for budget formatting and scoring. Not part of the booking gate |
| `visit_date` | string, date | yes | Site visit. Industry field, not a global column |

This matches the current six-field booking gate once name and phone are counted as engine fields: `visit_date`, `location`, `budget`, and `property_type` from this schema, plus `name` and `phone` from columns.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "industry-profile/real_estate/1/qualification_schema",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "location": { "type": "string", "minLength": 1 },
    "budget": { "type": "string", "minLength": 1 },
    "property_type": { "type": "string", "minLength": 1 },
    "intent": { "type": "string", "enum": ["buy", "rent", "unknown"] },
    "visit_date": { "type": "string", "minLength": 1 }
  },
  "required": ["location", "budget", "property_type", "visit_date"]
}
```

Migration backfill, owned by the migration plan, copies these five V1 columns into `industry_dynamic_data` and no others:

- `location`
- `budget`
- `property_type`
- `intent`
- `visit_date`

Empty V1 strings are omitted, not written as `""`. A row that fails this schema is not backfilled as valid. It is reported and left for repair. Name and phone are not copied into JSONB.

### 2.2 Stub profile

`field_service` version `1` exists only to prove a second profile can name different keys and still validate. It is not a designed industry and it is not seeded in production.

```json
{
  "$id": "industry-profile/field_service/1/qualification_schema",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "service_type": { "type": "string", "minLength": 1 },
    "site_address": { "type": "string", "minLength": 1 },
    "appointment_date": { "type": "string", "minLength": 1 }
  },
  "required": ["service_type", "site_address"]
}
```

The same engine validates both documents. No real-estate field name is hardcoded in the validator.

---

## 3. Scoring rules

`scoring_rules` is JSON. The engine reads numbers and field names. It does not parse a paragraph.

Score results are global engine columns, not industry JSON:

- `conversion_probability`
- `lead_temperature`
- `engagement_score`
- `urgency_level`
- `budget_alignment_status`
- `confidence_score`
- `requires_manual_review`

The current code has two hot cutoffs. The WhatsApp helper treats probability 70 as hot. `agent.py` treats 82 as hot, with floors when the booking gate is complete or a visit date is set. This profile picks the `agent.py` contract. The helper's 70 cutoff is not the contract.

`real_estate` version `1`:

```json
{
  "engagement": {
    "fields": ["name", "phone", "budget", "location", "property_type", "visit_date"],
    "points_per_field": 16,
    "opt_in_points": 4,
    "cap": 100
  },
  "temperature": {
    "hot_min_probability": 82,
    "warm_min_probability": 45,
    "full_qualify_floor": 88,
    "visit_date_floor": 82
  },
  "urgency": {
    "high_when": ["visit_date"],
    "medium_when_all": ["budget", "location"],
    "else": "low"
  },
  "budget_alignment": {
    "run_when_all": ["budget", "location", "property_type"],
    "else": "unknown"
  },
  "manual_review": {
    "when_confidence_below": 75
  }
}
```

Rules:

- Each filled completeness field adds 16 to engagement. WhatsApp opt-in adds 4. Cap is 100.
- Hot if probability is at least 82, or the booking gate is complete, or `visit_date` is set. The full-qualify floor is 88. The visit floor is 82.
- Warm if probability is at least 45 and the lead is not hot. Otherwise cold.
- Urgency is high when `visit_date` is set, medium when budget and location are set, otherwise low.
- Budget alignment runs only when budget, location, and property type are present. Otherwise the status is `unknown`.
- `confidence_score` below 75 sets `requires_manual_review`.

A tenant override may move `hot_min_probability` only inside the profile range 70 to 90. It may not remove a completeness field or replace the rule with free text.

---

## 4. Dashboard config

`dashboard_config` names field ids. It does not contain SQL or React. The dashboard renders whatever ids the active profile lists, if those ids are either global columns or keys in that profile's qualification schema.

`real_estate` version `1`:

```json
{
  "kanban": ["New", "Contacted", "Appointment Scheduled", "Closed Won", "Lost"],
  "card_fields": ["name", "phone", "location", "budget", "property_type", "visit_date", "lead_temperature"],
  "badges": ["lead_temperature", "is_negotiating", "requires_manual_review"],
  "filters": ["lead_temperature", "location", "property_type", "funnel_stage"]
}
```

Kanban values are the current `FUNNEL_STAGES`. Temperature badges stay case-sensitive on the client and title-cased at the API boundary, as they are today.

The stub profile uses different card fields (`service_type`, `site_address`, `appointment_date`) and the same renderer. That is the proof this is configuration, not a real-estate screen with a prompt pasted on top.

Tenant overrides may reorder `card_fields` and `filters`. They may not add an id that is absent from the global columns and the qualification schema.

---

## 5. Prompt rule

`base_ai_prompt` may only be a template. A slot must name a global column or a key in `qualification_schema`. The template cannot:

- declare a new qualification field
- change `required`
- change a score threshold
- instruct the model to skip validation

If a slot names an unknown field, profile load fails. The tenant does not get a silent free-form prompt.

---

## 6. What this document does not do

- It does not move name or phone into JSONB.
- It does not collapse messages into `conversation.message_history`.
- It does not define RLS, API keys, or the Agency model.
- It does not design the other eight sectors. One real profile and one stub are enough to prove the engine.
- It does not authorize a live schema change. Piyush reviews the package before any table is altered.
