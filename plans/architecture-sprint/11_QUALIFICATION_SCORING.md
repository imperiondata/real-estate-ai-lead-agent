# Qualification and scoring

One gate. One scorer. Field lists, weights, and thresholds come from the profile. See `09_INDUSTRY_PROFILE.md`.

---

## Gate

Required fields are `qualification_schema` entries with `required: true`.

The runtime asks for missing keys and does not confirm an appointment until every required key is non-empty.

| storage | Writes to |
|---|---|
| `lead` | `leads` identity columns. Required: `name`, `phone`. Optional: `email`. Email is not a qualification field |
| `attribute` | `lead_attributes.data` |

Name and phone stay on the lead row because every profile needs them. Email may be stored there and is not required. Every other required field is an attribute. See `02_ERD.md`.

The function that today checks visit date, phone, name, location, budget, and property type does not survive as core code. The rule "all required keys non-empty" does.

### Real-estate required set

name, phone, location, budget, property type, visit date.

That is the live gate. It is the real-estate profile, not the engine.

### Education required set

name, phone, course, education level, preferred location, budget, intake, eligibility.

Same engine. The education profile does not mention visit date. The engine does not notice.

### Confirm

"Confirm" means the runtime may call `schedule_appointment` and may emit `lead.qualified`. It does not mean a free-text promise in the reply. If required keys are missing, the tool call is rejected and the reply asks for the missing keys.

Opt-out and a closed handoff still end the loop even when the gate would pass. Those are runtime guardrails. See `08_AGENT_RUNTIME.md`.

---

## Scorer

One function. The profile supplies `scoring_schema`. The engine reads it.

Two live scorers collapse into this function. The completeness scorer's hot-at-70 is dropped. It is not a profile field and not an engine constant.

The real-estate seed keeps warm at 45, review below 75, and hot when probability is at least 82 or temperature is hot. Those three numbers live only on the profile. Education may set different numbers. The engine does not contain them.

### Outputs

Written to `leads`:

| Column | Meaning |
|---|---|
| `temperature` | `hot`, `warm`, or `cold` |
| `conversion_probability` | integer |
| `engagement_score` | integer |
| `urgency_level` | string from the urgency rule |
| `budget_alignment_status` | `aligned`, `unknown`, or `mismatch`. `unknown` if the profile did not enable `budget_band` |
| `inactivity_penalty` | integer. 0 if that rule is off |
| `confidence_score` | integer. Written by the runtime from the extraction. No rule id writes it |
| `requires_manual_review` | true when that confidence is below `review_below_confidence`. Set by the runtime, not by a rule |

The real-estate seed uses 75 for that threshold. That is today's rule, stored on the profile.

After a successful score the engine publishes `lead.scored`. If the profile hot rule matches, it also publishes `lead.hot`. See `06_EVENTS.md`.

### Hot rule

The profile hot rule is: probability greater than or equal to `hot_probability`, or temperature equal to `hot_temperature`. Both values are profile fields. There is not a second hot event.

---

## Rule ids

The engine implements these ids and no others. A profile may only list ids from this table.

| Id | Reads | Writes |
|---|---|---|
| `field_completeness` | Required keys present | `engagement_score`, feeds probability |
| `budget_band` | Attribute `budget` against profile product data, if present | `budget_alignment_status` |
| `urgency_from_date` | The attribute whose `role` is `urgency_date`. Real-estate seed: `visit_date`. No such attribute means the rule no-ops | `urgency_level` |
| `inactivity_penalty` | Time since last user message. Quiet hours do not change the penalty | `inactivity_penalty` |
| `behavior_signals` | `conversation.behavior_phrases` in `09_INDUSTRY_PROFILE.md`. Empty list means the rule no-ops | feeds probability only |

`budget_band` no-ops when the profile has no product price data. It does not call a housing price table in the core.

A new rule id is a core change. Travel must score with this list. If it cannot, this file is wrong.

---

## Follow-up

This file does not arm follow-up. `06_EVENTS.md` arms the sequence on `lead.created`. Qualification complete does not start a second sequence. Gaps and quiet hours are `workflows` on the profile, not constants in the scheduler. The scheduler job stays the one named in `01_SPINE.md`.

This file does not define the sequence. `09_INDUSTRY_PROFILE.md` does. The real-estate seed is days 0, 1, 3, 7, quiet hours 22:00–08:00 Asia/Kolkata.

---

## Travel check

- Required fields are a `qualification_schema` list. No new gate function.
- Score uses only the five rule ids. No new scorer.
- Hot and review thresholds are numbers on the profile.
- Appointment confirm uses `schedule_appointment` with a type the profile allows.
- No column added to `leads` for a Travel field.

If any line fails, the design fails.
