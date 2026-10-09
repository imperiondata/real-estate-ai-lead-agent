# Agent runtime

One loop. No industry class. Tenant context is already set before step 1. See `03_TENANCY_AND_RBAC.md`.

The current WhatsApp turn is the worked trace. A second industry adds no step.

---

## Loop

```text
1. Context is set (agency_id, tenant_id). This loop does not resolve them.
2. Load the one profile for that tenant. See 09_INDUSTRY_PROFILE.md.
3. Build context. Last 6 turns, memory, knowledge, optional graph.
4. Assemble the prompt. Stable shell + profile fragments.
5. Call the model. Tool list is the profile allowlist.
6. Validate tool calls. Inject both ids. Reject a call that passes either.
7. Write identity, attributes, and the reply.
8. Emit the post-reply events. `message.received` was already emitted when the inbound message was stored. See `06_EVENTS.md`.
```

Adapters that are down return empty. They do not block the reply and they do not fail the turn. Timeouts and the WhatsApp race window stay in `01_SPINE.md`. They are channel details, not loop steps.

---

## Step 3

- Turn window: last 6 turns (12 messages). Consecutive messages with the same role merge.
- Memory and knowledge: `10_MEMORY_KNOWLEDGE_TOOLS.md`.
- Graph block: optional. Same tenant filter. Omitted if the adapter is down or over its budget.
- The model receives no namespace argument and no tool that can change tenant.

---

## Step 4

The shell says the assistant operates for the loaded profile. It does not name an industry. Terminology, instruction fragments, and tool-trigger phrases come from the profile `conversation` block.

The shell still owns: do not invent fields, do not confirm a booking while required fields are missing, do not claim a human has been assigned unless a tool did it.

---

## Step 6

Injected arguments, not visible to the model:

```json
{ "agency_id": 1, "tenant_id": 4 }
```

If the model output contains `agency_id` or `tenant_id`, reject the call. Do not override and continue. See `04_SECURITY_MODEL.md`.

Only tool ids in the profile allowlist may run. An unknown id is a guardrail failure, not a new tool.

---

## Step 7 and 8

- Identity fields (name, phone, email) write to `leads`.
- Other captured fields write to `lead_attributes` if they are in `qualification_schema`. Other keys are dropped.
- One assistant message per turn. If the tool path already saved it, the loop does not save it again.
- `message.received` is emitted when the inbound message is stored, before the model call.
- Events after the reply is stored, off the channel reply path: `conversation.updated`, `lead.created` when the row is new, `lead.qualified` when the gate passes, `ai.action.executed` when a tool finished.
- Do not emit `brochure.sent`, `floorplan.sent`, or `site_visit.scheduled`.

---

## Guardrails

These stay in the runtime. Thresholds and field lists come from the profile.

| Rule | Source of the value |
|---|---|
| Do not confirm a booking until required fields are present | `qualification_schema` |
| Confidence below threshold sets `requires_manual_review` | profile threshold. Real-estate seed is 75 |
| Opt-out stops the loop and does not re-arm follow-up | lead `opt_in` |
| Duplicate assistant content is not saved twice | runtime |
| A down retriever does not widen the search | runtime |

---

## WhatsApp trace

Current path, mapped onto the loop. Names on the left are today's. Names on the right are the loop.

| Today | Loop |
|---|---|
| API key resolves `client_id` | Step 1, already done. Target resolves both ids |
| Session id `{client_id}_{From}` | `{tenant_id}_{raw}` |
| Webhook log insert, then lock | Channel, before the loop. See `01_SPINE.md` |
| Graph context, then qualify, then tools, then score | Steps 3–7. The subscriber on `conversation.updated` calls `score_lead` and is the only publisher of `lead.scored` |
| 6-field gate on visit date, phone, name, location, budget, property type | Step 7 gate, field list from the profile |
| Brochure or floor plan keyword | Allowlisted `send_media` or `get_product_information`, triggers from the profile |
| `lead.qualified` when the six fields are set | `lead.qualified` when the profile's required keys are set |
| Interim line if the race window expires | Channel. Same loop, one model call |

SMS and web chat enter at step 3 after resolution. They emit `message.received`. Ingest, Meta, and portals do not enter this loop. They write a lead and emit `lead.created` only. See `06_EVENTS.md`.

---

## What this loop does not contain

- No class per industry.
- No `if industry` branch.
- No tool implementation. Registry is `10_MEMORY_KNOWLEDGE_TOOLS.md`.
- No scoring weights. Those are `11_QUALIFICATION_SCORING.md`.
- No tenant resolution.
