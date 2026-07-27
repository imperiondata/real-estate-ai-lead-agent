"""IREIOS 3.0 — Wave A.1: Weekly Marketing Cron.

Scheduler job that publishes a ``cron.weekly_report`` event for every active
client, waking the MarketingAgent to produce segmentation + suggestions.

Runs from the BackgroundScheduler (a worker thread), so it publishes to the
Redis Streams bus via a short-lived async connection inside ``asyncio.run``
(the loop-bound ``event_bus`` singleton belongs to the app lifespan loop and
cannot be driven from a scheduler thread).
"""
from __future__ import annotations

import asyncio
import json
import logging

import redis.asyncio as aioredis

from config import settings
from database import SessionLocal
from models import Client

logger = logging.getLogger("weekly_marketing_cron")

WEEKLY_MARKETING_CRON_EVENT = "cron.weekly_report"


async def _publish_envelopes(envelopes: list[dict]) -> None:
    """Publish envelopes via a fresh, short-lived Redis connection."""
    if not envelopes:
        return
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        for env in envelopes:
            await r.xadd(settings.EVENT_STREAM_KEY, {"data": json.dumps(env, default=str)})
    finally:
        try:
            await r.aclose()
        except Exception:
            pass


def weekly_marketing_cron_job() -> None:
    """Scheduler entry point: publish ``cron.weekly_report`` per active client."""
    db = SessionLocal()
    envelopes: list[dict] = []
    try:
        clients = db.query(Client).filter(Client.is_active.is_(True)).all()
        for client in clients:
            envelopes.append({
                "event_id": f"weekly_report_{client.id}",
                "event_type": WEEKLY_MARKETING_CRON_EVENT,
                "tenant_id": f"Client_{client.id}",
                "entity_id": "marketing",
                "source": "weekly_marketing_cron",
                "payload": {"source": "scheduler"},
            })
        if not envelopes:
            logger.debug("weekly_marketing_cron: no active clients; skip")
            return
    finally:
        db.close()
    try:
        asyncio.run(_publish_envelopes(envelopes))
        logger.info("weekly_marketing_cron published %d events", len(envelopes))
    except Exception as e:
        logger.error("weekly_marketing_cron publish failed: %s", e)
