# Local tenant delivery proof

**Date:** 24 November 2026
**Owner:** Maitri
**Scope:** localhost only. Not staging. Not a live email. Not Render.

A `TEST_MODE=true` `event_logs` row with `agent_type=recorded` is not this proof. That path never opens a socket.

## What was run

`python scripts/prove_tenant_delivery_local.py`

The script forces `TEST_MODE=false` for its own process. It binds an SMTP listener and an HTTP listener on `127.0.0.1` only, creates a fake tenant row, and deletes that row afterward. It refuses a non-loopback `DATABASE_URL`.

`deliver_tenant_lead` uses the real webhook poster and, because the SMTP host is loopback, the real SMTP sender without STARTTLS. Any other SMTP host still uses STARTTLS and login.

## What the raw log must show

`plans/evidence/TENANT_DELIVERY_LOCAL.log`

- `SMTP_RECEIPT attempt=1 code=451` — the listener saw the first message and asked for a retry.
- `SMTP_RECEIPT attempt=2 code=250` — the listener accepted the retry.
- `HTTP_RECEIPT attempt=1 status=503` — the receiver rejected the first POST as transient.
- `HTTP_RECEIPT attempt=2 status=200` — the receiver accepted the retry.
- `replay_receipts=0` — a second call after success did not send again.
- `key_absent_from_client=true` — `WIDGET_API_KEY` is read only in `frontend/src/app/api/chat/route.ts`. The scan does not open `frontend/.env.local` and does not print the key.

## Unit coverage

`tests/test_tenant_delivery.py`

- Three attempts and one failed row when every attempt raises.
- One transient failure, then success, then a replay that does not send.
- HTTP 400 is not retried.
- A failed row does not block a later send.
- `TEST_MODE=true` still does not call the transport.

`tests/test_widget_api_key_server_side.py` asserts the key name is absent from client files and is not `NEXT_PUBLIC_WIDGET_API_KEY`.
