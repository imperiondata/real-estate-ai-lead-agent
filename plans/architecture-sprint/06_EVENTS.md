# Events

Neutral names. One envelope. One runner interface. A consumer that lacks either id acks, does not run, and does not dead-letter.

---

## Envelope

```json
{
  "event_id": "01H...",
  "event_type": "lead.qualified",
  "agency_id": 1,
  "tenant_id": 4,
  "entity_id": "10",
  "payload": {},
  "occurred_at": "2026-10-09T12:00:00Z"
}
```

`agency_id` and `tenant_id` are integers from the auth context or from the lead row. They are not strings the publisher invents. The current `Client_{id}` form does not appear on new events.

A consumer sets context from the envelope, then queries. Missing `agency_id` or `tenant_id`: ack, do not run, do not write, do not dead-letter. A missing id is poison, not a retry. Do not substitute a default.

---

## Catalog

| Event | When |
|---|---|
| `lead.created` | First persist of a lead |
| `lead.updated` | Identity or attribute change after create |
| `lead.qualified` | All required profile fields present |
| `lead.scored` | Scorer wrote temperature and probability |
| `lead.hot` | Profile hot rule matched |
| `lead.assigned` | Owner set |
| `message.received` | Inbound chat. `payload.channel` is `whatsapp`, `sms`, or `web`. Meta and portal are `lead.created`, not this event |
| `message.sent` | Outbound send succeeded |
| `conversation.updated` | Turn stored |
| `followup.scheduled` | Next step armed |
| `followup.executed` | Step sent or exhausted |
| `appointment.scheduled` | Appointment row created |
| `appointment.completed` | Appointment closed |
| `pipeline.stage_changed` | Stage write |
| `ai.action.executed` | A tool finished. `payload.tool_id` names it |
| `integration.failed` | External call failed closed |
| `customer.onboarded` | Ops inject only |
| `payment.received` | Ops inject only |
| `payment.due` | Ops inject only |
| `renewal.due` | Ops inject only |
| `document.pending` | Ops inject only |

`lead.hot` is the only escalation event. There is no second event with the same meaning.

---

## Rename

| Current | Target |
|---|---|
| `whatsapp.received`, `sms.received`, `chat.received` | `message.received` + `payload.channel` |
| `facebook.received`, `{portal}.received` | `lead.created`. Not `message.received` |
| `site_visit.scheduled` | `appointment.scheduled` + `payload.appointment_type` |
| `brochure.sent`, `brochure.generated`, `floorplan.sent`, `floorplan.generated` | `ai.action.executed` + `payload.tool_id` |
| `lead.escalated` | not emitted. Callers that meant it emit `lead.hot` |
| `lead.created`, `lead.qualified`, `lead.scored`, `conversation.updated`, `lead.assigned` | unchanged |

Current consumers that subscribe to a renamed event move to the new name. They do not subscribe to both after cutover. During the side-by-side window, the V1 process keeps its current names on the V1 stream. The V2 process uses this catalog. They do not share a consumer group.

---

## Who publishes

| Publisher | Events |
|---|---|
| Runtime, when the inbound message is stored | `message.received` |
| Runtime, after the reply is stored | `conversation.updated`, `lead.created`, `lead.qualified`, `ai.action.executed` |
| Lead patch | `lead.updated` |
| Scorer | `lead.scored`, `lead.hot` |
| Assignment | `lead.assigned` |
| Follow-up job | `followup.scheduled`, `followup.executed` |
| Execution engine | `message.sent`, `appointment.scheduled`, `integration.failed` |
| Appointment complete | `appointment.completed` |
| Stage write | `pipeline.stage_changed` |
| Ops inject | only `customer.onboarded`, `payment.received`, `payment.due`, `renewal.due`, `document.pending` |

The model does not publish. A tool does not publish a tenant other than the injected one. `POST /api/v2/appointments` does not publish `appointment.scheduled`. Only the execution engine does, after `schedule_appointment` succeeds.

---

## Core reactions

These workflows are code. They read the profile for thresholds and sequences. They do not branch on industry name.

| On | Does |
|---|---|
| `lead.created`, `conversation.updated` | Arm follow-up from the profile sequence |
| `conversation.updated` | Score, then publish `lead.scored` |
| `lead.qualified` | CRM sync if the tenant's integration is on |
| `lead.hot` | Notify, create task, start the profile follow-up if not already armed |
| `lead.scored` | Sales tool policy from the profile. No industry class |

Pricing, inventory, brochure, and floor plan are tools. See `10_MEMORY_KNOWLEDGE_TOOLS.md`. They are not subscribers.

---

## Runner

```text
submit(envelope) -> { "status": "ack" | "skipped" | "error" }
```

The core calls `submit`. It does not import a vendor client and does not name a webhook path.

The first adapter is n8n. Its map is data:

| Event | Adapter path |
|---|---|
| `lead.hot` | hot lead alert |
| `appointment.scheduled` | visit fan-out |
| `approval.requested` | approval notify |
| `lead.qualified` | sheet append |
| `marketing.report.generated` | report mail |

Those path strings live in the adapter table, not in the runtime. An unconfigured adapter returns `skipped`. The turn still completes.

`approval.requested` is published by the approval workflow when a human gate opens. `marketing.report.generated` is published by the weekly report job. Both are adapter inputs. They are not in the core catalog above. The model does not publish them. The adapter may listen to this wider set. If the adapter is unconfigured, the publish still succeeds and `submit` returns `skipped`.

---

## DLQ

| target_endpoint | When |
|---|---|
| `outbound_send` | Execution send failed |
| `crm` | CRM push failed closed |
| `followup` | Scheduler send failed closed |
| `unknown` | No executor for the action |

Replay is an ops script. It loads the row, restores both ids from the row, and retries. It does not accept a tenant override.

---

## Idempotency

`event_id` is unique per publish. Consumers ack by `event_id`. A redelivery does not double-send. Webhook dedupe remains the `webhook_logs` insert, separate from the bus. See `04_SECURITY_MODEL.md`.
