# Memory, knowledge, tools

What the runtime may read, and the only tools it may call. Isolation rules are in `04_SECURITY_MODEL.md`. The loop is in `08_AGENT_RUNTIME.md`.

---

## Memory

Three layers. They are not interchangeable.

### Turn window

Last 6 turns. Consecutive same-role messages merge before the prompt is built. This is runtime state. The profile does not configure the window in this draft.

### Attributes

Keys come from `qualification_schema` in `09_INDUSTRY_PROFILE.md`. Storage is `lead` or `attribute` as that schema says.

The current extractor writes a fixed set: name, location, budget, property type, intent. That set moves into the profile. The writer stores the schema's keys and drops the rest.

### Recall

Table `conversation_memory`. Columns `key`, `value`, `memory_type`.

| memory_type | Use |
|---|---|
| `fact` | A captured field worth restating next turn |
| `preference` | A stated preference that is not a required field |
| `objection` | A matched objection phrase |

Objection phrases are `conversation.objection_phrases` in `09_INDUSTRY_PROFILE.md`. There is one list. The real-estate seed is discount, too expensive, best price, final price, and lower price. An empty list means no objection is stored.

Recall queries filter `agency_id`, `tenant_id`, and `lead_id`. A recall without those three is a defect.

Writes are idempotent: if the latest value for the key already matches, do not insert.

---

## Knowledge

One retriever.

- Filter is `agency_id` plus `tenant_id`, applied in the query, not in the prompt.
- A chunk with a foreign tenant is dropped.
- A missing filter fails the query. It does not run unfiltered.
- The graph is an optional second retriever with the same filter. If it is down or over budget, the prompt has no graph block.
- The model never receives a namespace argument.
- `knowledge_namespace` in the profile is the literal `tenant`. The runtime fills the ids. See `09_INDUSTRY_PROFILE.md`.

Today's vector index already drops a chunk with a foreign client id. The target filter is both ids, not client id alone.

---

## Tools

A fixed registry. The profile turns ids on and may set parameters. The schema has no `agency_id` and no `tenant_id` field. The runtime injects both before execute. A model output that includes either is rejected.

| Id | Does | Replaces |
|---|---|---|
| `search_knowledge` | Retriever plus optional graph | RAG and graph context injection |
| `get_lead` | Read identity and attributes for this lead | Ad-hoc column reads |
| `update_lead` | Write identity and in-schema attributes | `extract_lead_info` |
| `calculate_qualification` | Required keys present or missing | The six-field function |
| `score_lead` | Run the profile's rule ids | Both current scorers |
| `schedule_appointment` | Create an appointment of a profile-allowed type | `schedule_visit` |
| `send_message` | Outbound text | WhatsApp and SMS send |
| `send_media` | Outbound media URL from configuration, else text | Brochure and floor plan |
| `create_task` | Insert `tasks` | `agent_tasks` |
| `update_pipeline` | Set stage by key | Stage patch |
| `notify_sales` | Notify the escalation contact for this tenant | Hot-lead notify |
| `get_product_information` | Read profile `product_data` | Inventory and pricing tables |
| `get_availability` | Read open appointment slots if the integration is on | Calendar read |
| `run_sales` | Preview or execute the sales policy | Direct sales call |

`detect_tool_intent` does not survive as core code. Trigger phrases live on the profile `conversation.tool_triggers` map. The runtime matches those phrases to allowlisted ids only.

The words "brochure" and "floor plan" do not appear in the runtime. They appear in the real-estate profile's trigger list.

`send_media` reads a configured HTTPS URL from tenant settings or the profile. A non-HTTPS URL is rejected. An empty URL uses `get_product_information` only when that id is allowlisted. If it is not, the tool returns the profile text fragment. It does not call a tool the profile did not turn on.

---

## Parameters the profile may set

| Tool | Parameter | Example |
|---|---|---|
| `schedule_appointment` | `conversation.tool_params.schedule_appointment.allowed_types` | `["site_visit"]` |
| `send_media` | `media_key` | `brochure` or `floorplan`, resolved to a URL outside the model |
| `notify_sales` | `reason` | profile hot rule id |
| `get_product_information` | `source` | `product_data` |

Parameters do not include a tenant id, a raw SQL fragment, or a URL the model typed. Media URLs are configuration, not model output.

---

## Sales and negotiation

`run_sales` is allowlisted or not. It is not a separate agent class. Preview writes nothing. Execute may call `score_lead`, `update_pipeline`, `notify_sales`, and `create_task`. `score_lead` writes scores. It does not publish `lead.scored`. The subscriber in `08_AGENT_RUNTIME.md` is the only publisher.

Negotiation matches `conversation.objection_phrases`, stores `memory_type` `objection`, and sets `is_negotiating`. The loop does not pause for a human. A misaligned budget calls `notify_sales`. It does not stop the reply.
