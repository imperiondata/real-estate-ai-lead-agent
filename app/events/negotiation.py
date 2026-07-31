"""IREIOS 3.0 — Negotiation event helpers with debounce.

Negotiation events fire when:
  - Layer 1: User mentions negotiation keywords (agent.py intercept)
  - Layer 2: Budget alignment is misaligned after scoring (whatsapp_agent.py)

Debounce TTL: 300 seconds (5 minutes).
  WHY 5MIN: Negotiation is a single escalation event per lead, not a recurring
  signal like lead.hot (which uses 30min). Once the lead is flagged as
  negotiating, duplicate events are noise. Adjust via env var if needed.

Event: lead.negotiation.started
  -> NegotiationAgent flags lead.is_negotiating = True (no HITL pause)
  - Frontend shows "Open for Negotiation" badge
  - Human agent claims lead from dashboard
"""
from __future__ import annotations

import logging

from config import settings

logger = logging.getLogger(__name__)

# Debounce TTL: 5 minutes (300 seconds).
# WHY 5MIN: Negotiation is a single escalation event per lead, not a recurring
# signal like lead.hot (which uses 30min). Once the lead is flagged as
# negotiating, duplicate events are noise. Adjust via
# NEGOTIATION_DEBOUNCE_TTL_SECONDS env var if needed.
NEGOTIATION_DEBOUNCE_TTL = 300


def debounce_key(client_id: int, lead_id: int) -> str:
    """Redis key for per-lead negotiation debounce."""
    return f"negotiation_emitted:{client_id}:{lead_id}"


async def _debounce_allow(client_id: int, lead_id: int) -> bool:
    """Redis SET NX gate -- returns True if key was set (first call within TTL).

    If Redis is down, returns True (best-effort -- proceed without debounce).
    """
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        key = debounce_key(client_id, lead_id)
        set_result = await r.set(key, "1", ex=NEGOTIATION_DEBOUNCE_TTL, nx=True)
        await r.aclose()
        return bool(set_result)
    except Exception:
        return True


async def publish_negotiation_started(
    *,
    client_id: int,
    lead_id: int,
    session_id: str,
    trigger: str,
    message: str = "",
    budget: str = "",
    budget_alignment_status: str = "",
    source: str = "agent",
) -> bool:
    """Publish lead.negotiation.started with debounce.

    Returns True if event was published, False if debounced or failed.
    """
    if not await _debounce_allow(client_id, lead_id):
        return False

    try:
        from app.clients.event_bus_client import event_bus

        if not getattr(event_bus, "_running", False):
            return False

        await event_bus.publish(
            "lead.negotiation.started",
            f"Client_{client_id}",
            str(lead_id),
            {
                "lead_id": lead_id,
                "session_id": session_id,
                "trigger": trigger,
                "message": message[:200],
                "budget": budget,
                "budget_alignment_status": budget_alignment_status,
            },
            source=source,
        )
        return True
    except Exception as e:
        logger.warning("negotiation publish failed: client=%s lead=%s err=%s", client_id, lead_id, e)
        return False
