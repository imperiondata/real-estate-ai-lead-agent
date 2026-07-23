"""IREIOS 3.0 — Phase 1b demo helper.

Fires a sample event onto the Redis Streams bus so you can watch it arrive on
the SSE stream (GET /api/v1/events/stream) without real WhatsApp/LLM
producers. Useful for frontend demos.

Usage:
    python publish_stub_event.py --event-type lead.created \
        --tenant-id Client_1 --entity-id lead_x --payload '{"name":"demo"}'
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.clients.event_bus_client import event_bus


async def main(args) -> None:
    import redis.asyncio as aioredis
    from config import settings
    redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        payload = json.loads(args.payload) if args.payload else {}
        envelope = event_bus.build_envelope(args.event_type, args.tenant_id, args.entity_id, payload, source="stub")
        await redis.xadd(settings.EVENT_STREAM_KEY, {"data": json.dumps(envelope, default=str)})
        print(f"published event_id={envelope['event_id']} type={args.event_type} tenant={args.tenant_id}")
    finally:
        await redis.aclose()


def parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Publish a stub event to the IREIOS 3.0 bus")
    p.add_argument("--event-type", default="lead.created")
    p.add_argument("--tenant-id", default="Client_1")
    p.add_argument("--entity-id", default="stub")
    p.add_argument("--payload", default=None, help="JSON object string")
    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse()))
