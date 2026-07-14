# IREIOS 3.0 — API & SSE Contracts

Source of truth for the realtime + API envelopes the frontend (Mayank UI) consumes.
Created at **Step 10 (Expansion Phase 1b)** so the FE can be wired to stable contracts
while backend phases 2–9 continue. Mirrors `BUG_FIXES_CHANGELOG.md` in intent (a
living contract doc), not the bug plan's test log.

> Status: SKELETON. Fill shapes in as Phase 1b lands; keep `source: "stub"` payloads
> clearly marked until the producing phase goes live.

## 1. SSE stream endpoint

- **Route:** `GET /api/v1/events/stream` (or mounted in `app/api/events.py`)
- **Auth:** JWT Bearer (`get_current_client`) — same as dashboard routes.
- **Transport:** `text/event-stream`, one JSON event per `data:` frame.
- **Envelope (all events):**

```json
{
  "type": "timeline.event" | "kpi.update" | "lead.update" | "agent.status",
  "source": "stub" | "automation_engine" | "event_bus",
  "tenant_id": "Client_<id>",
  "ts": "<iso8601>",
  "payload": { }
}
```

## 2. Timeline envelope (`type: timeline.event`)

TODO (Phase 1b.2): define event kinds (lead.created, lead.scored, followup.sent,
hot.alert, handoff). Each payload includes `lead_id`, `actor`, `summary`.

## 3. KPI envelope (`type: kpi.update`)

TODO: define metrics (open_leads, hot_count, followup_pending, conversion_rate).
Stub publisher sends zeros/static until Phase 4/8 produce real values.

## 4. Lead / agent updates

TODO: shape of `lead.update` and `agent.status` frames consumed by Kanban / copilot.

## 5. Backward compatibility

- Stub publisher MUST emit the same envelope shape as the eventual real producer.
- Frontend MUST NOT depend on stub-only fields; mark them `source: "stub"`.
- Contract changes require a version bump in this doc + a changelog entry.
