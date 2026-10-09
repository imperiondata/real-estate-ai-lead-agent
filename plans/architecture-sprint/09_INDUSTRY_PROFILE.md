# Industry profile

The JSON document `industry_profiles.document` holds, and `tenant_configurations` binds one published version per tenant. Shape only. The runtime that loads it is `08_AGENT_RUNTIME.md`. The gate and the scorer are `11_QUALIFICATION_SCORING.md`.

One tenant, one profile. A published version is immutable. A second industry is a second tenant.

---

## Document

```json
{
  "key": "real_estate",
  "version": 1,
  "terminology": {},
  "qualification_schema": [],
  "scoring_schema": {},
  "conversation": {},
  "tool_allowlist": [],
  "pipeline_stages": [],
  "workflows": {},
  "kpis": [],
  "knowledge_namespace": "tenant"
}
```

`knowledge_namespace` is the literal `tenant`. The runtime substitutes the auth tenant. The document must not contain a tenant id, an agency id, a phone number, or a secret.

`industry_profiles.key` and `industry_profiles.version` are the columns. The same two values inside `document` must equal those columns. A write sets both in one transaction. They are not two sources.

---

## Keys

| Key | Holds | Must not hold |
|---|---|---|
| `terminology` | Display words. Appointment label, lead label | Code branches |
| `qualification_schema` | Field key, type, required, prompt hint. One attribute may set `"role": "urgency_date"` | SQL |
| `scoring_schema` | Weights, thresholds, rule ids from `11` | A new scorer |
| `conversation` | Instruction fragments, tool-trigger phrases, `objection_phrases`, `behavior_phrases`, `tool_params` | The whole system prompt |
| `tool_allowlist` | Ids from `10_MEMORY_KNOWLEDGE_TOOLS.md` | Tool source |
| `pipeline_stages` | `key`, `label`, `position` | A check constraint on `leads` |
| `workflows` | Follow-up gaps, quiet hours, keyword lists | A new scheduler job |
| `kpis` | Names and which event counts them | A second analytics database |
| `knowledge_namespace` | Always `tenant` | A path the model can edit |

Overrides on `tenant_configurations.overrides` may replace `terminology`, `conversation` fragments, `tool_allowlist` by removing an id, `pipeline_stages` labels, `workflows` gaps, and `product_data`. They may not add a tool id that is not in the registry, and they may not remove a required identity field (`name`, `phone`).

---

## Real estate

Worked example. Values match the live gate and the live stage list. They are data.

```json
{
  "key": "real_estate",
  "version": 1,
  "terminology": {
    "appointment": "Site visit",
    "product": "Property"
  },
  "qualification_schema": [
    { "key": "name", "type": "string", "required": true, "storage": "lead" },
    { "key": "phone", "type": "string", "required": true, "storage": "lead" },
    { "key": "location", "type": "string", "required": true, "storage": "attribute" },
    { "key": "budget", "type": "string", "required": true, "storage": "attribute" },
    { "key": "property_type", "type": "string", "required": true, "storage": "attribute" },
    { "key": "visit_date", "type": "string", "required": true, "storage": "attribute", "role": "urgency_date" }
  ],
  "scoring_schema": {
    "hot_probability": 82,
    "hot_temperature": "hot",
    "warm_at": 45,
    "review_below_confidence": 75,
    "rules": ["field_completeness", "budget_band", "urgency_from_date", "inactivity_penalty", "behavior_signals"]
  },
    "conversation": {
    "fragments": ["Ask for missing required fields. Do not confirm a visit until they are present."],
    "tool_triggers": {
      "send_media": ["brochure", "floor plan", "floorplan", "layout"],
      "get_product_information": ["availability", "price", "inventory"]
    },
    "tool_params": {
      "schedule_appointment": { "allowed_types": ["site_visit"] }
    },
    "objection_phrases": ["discount", "too expensive", "best price", "final price", "lower price"],
    "behavior_phrases": ["ready to buy", "book visit", "site visit"]
  },
  "tool_allowlist": [
    "search_knowledge", "get_lead", "update_lead", "calculate_qualification",
    "score_lead", "schedule_appointment", "send_message", "send_media",
    "create_task", "update_pipeline", "notify_sales", "get_product_information",
    "run_sales"
  ],
  "pipeline_stages": [
    { "key": "new", "label": "New", "position": 1 },
    { "key": "contacted", "label": "Contacted", "position": 2 },
    { "key": "appointment_scheduled", "label": "Appointment Scheduled", "position": 3 },
    { "key": "closed_won", "label": "Closed Won", "position": 4 },
    { "key": "lost", "label": "Lost", "position": 5 }
  ],
  "workflows": {
    "followup_days": [0, 1, 3, 7],
    "quiet_hours": { "start": "22:00", "end": "08:00", "tz": "Asia/Kolkata" },
    "competitor_keywords": []
  },
  "kpis": ["leads", "qualified", "appointments", "hot"],
  "knowledge_namespace": "tenant"
}
```

`intent` is not required. It may be an optional attribute. The live extractor stores it today; the profile decides.

---

## Education

Same keys. Different values. Proves the shape.

```json
{
  "key": "education",
  "version": 1,
  "terminology": { "appointment": "Counselling", "product": "Course" },
  "qualification_schema": [
    { "key": "name", "type": "string", "required": true, "storage": "lead" },
    { "key": "phone", "type": "string", "required": true, "storage": "lead" },
    { "key": "course", "type": "string", "required": true, "storage": "attribute" },
    { "key": "education_level", "type": "string", "required": true, "storage": "attribute" },
    { "key": "preferred_location", "type": "string", "required": true, "storage": "attribute" },
    { "key": "budget", "type": "string", "required": true, "storage": "attribute" },
    { "key": "intake", "type": "string", "required": true, "storage": "attribute" },
    { "key": "eligibility", "type": "string", "required": true, "storage": "attribute" }
  ],
  "scoring_schema": {
    "hot_probability": 80,
    "hot_temperature": "hot",
    "warm_at": 45,
    "review_below_confidence": 75,
    "rules": ["field_completeness", "urgency_from_date", "inactivity_penalty"]
  },
    "conversation": {
    "fragments": ["Ask for missing required fields. Do not confirm a counselling slot until they are present."],
    "tool_triggers": { "send_media": ["brochure", "prospectus"], "schedule_appointment": ["counselling", "campus visit"] },
    "tool_params": {
      "schedule_appointment": { "allowed_types": ["counselling"] }
    },
    "objection_phrases": [],
    "behavior_phrases": []
  },
  "tool_allowlist": [
    "search_knowledge", "get_lead", "update_lead", "calculate_qualification",
    "score_lead", "schedule_appointment", "send_message", "send_media",
    "create_task", "update_pipeline", "notify_sales", "run_sales"
  ],
  "pipeline_stages": [
    { "key": "new", "label": "Enquiry", "position": 1 },
    { "key": "contacted", "label": "Contacted", "position": 2 },
    { "key": "appointment_scheduled", "label": "Counselling booked", "position": 3 },
    { "key": "closed_won", "label": "Enrolled", "position": 4 },
    { "key": "lost", "label": "Lost", "position": 5 }
  ],
  "workflows": { "followup_days": [0, 1, 3, 7], "quiet_hours": { "start": "22:00", "end": "08:00", "tz": "Asia/Kolkata" } },
  "kpis": ["leads", "qualified", "appointments", "hot"],
  "knowledge_namespace": "tenant"
}
```

Education does not enable `get_product_information`. The runtime does not notice. The allowlist does.

---

## Banned

The document must not contain:

- Auth material, API keys, or webhook secrets.
- `agency_id` or `tenant_id`.
- SQL, table names, or a check constraint.
- A tool implementation or a Python import.
- An industry branch for the core to execute.

---

## Travel check

A Travel profile must fit these keys: terminology, qualification schema, scoring schema using only rule ids from `11_QUALIFICATION_SCORING.md`, conversation fragments, a tool allowlist from the registry, pipeline stages, workflow gaps, KPIs, `knowledge_namespace` = `tenant`.

If Travel needs a new key in this document, or a new tool id, this shape is wrong.
