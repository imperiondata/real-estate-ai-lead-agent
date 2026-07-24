"""Canonical ``lead.hot`` + PR #10 alias ``lead.escalated`` (dual-publish).

Product HOT rule: ``conversion_probability >= 82`` OR
``lead_temperature == "hot"`` (case-insensitive).

Long-term prefer catalog ``lead.hot`` (SalesAgent already subscribes).
Alias ``lead.escalated`` mirrors the same payload for n8n workflows named
in PR #10 review — n8n should pick **one** event type per workflow to avoid
double Slack. Aliases can be retired later without changing catalog consumers.

Redis debounce: ``lead_hot_emitted:{client_id}:{lead_id}:{trigger}`` (30m TTL).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from config import settings

logger = logging.getLogger("lead_hot")

HOT_PROBABILITY_THRESHOLD = 82
DEBOUNCE_TTL_SEC = 30 * 60

# Catalog primary + PR #10 alias (same payload).
PRIMARY_EVENT = "lead.hot"
ALIAS_EVENT = "lead.escalated"


def is_hot(
    *,
    conversion_probability: Any = None,
    lead_temperature: Any = None,
) -> bool:
    try:
        if conversion_probability is not None and float(conversion_probability) >= HOT_PROBABILITY_THRESHOLD:
            return True
    except (TypeError, ValueError):
        pass
    return (str(lead_temperature or "")).strip().lower() == "hot"


def debounce_key(client_id: int, lead_id: int, trigger: str) -> str:
    return f"lead_hot_emitted:{client_id}:{lead_id}:{trigger}"


async def _debounce_allow(client_id: int, lead_id: int, trigger: str) -> bool:
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            ok = await r.set(
                debounce_key(client_id, lead_id, trigger),
                "1",
                ex=DEBOUNCE_TTL_SEC,
                nx=True,
            )
            return bool(ok)
        finally:
            try:
                await r.aclose()
            except Exception:  # noqa: BLE001
                pass
    except Exception as exc:  # noqa: BLE001
        logger.debug("lead.hot debounce skipped: %s", exc)
        return True


def build_lead_hot_payload(
    lead: Any,
    *,
    trigger: str,
    reason: str,
    session_id: Optional[str] = None,
    chat_context: str = "",
    score: Any = None,
) -> dict:
    prob = getattr(lead, "conversion_probability", None)
    if score is None:
        score = prob
    return {
        "lead_id": getattr(lead, "id", None),
        "session_id": session_id or getattr(lead, "session_id", None),
        "name": getattr(lead, "name", None),
        "phone": getattr(lead, "phone", None),
        "location": getattr(lead, "location", None),
        "budget": getattr(lead, "budget", None),
        "property_type": getattr(lead, "property_type", None),
        "intent": getattr(lead, "intent", None),
        "lead_temperature": getattr(lead, "lead_temperature", None),
        "conversion_probability": prob,
        "score": score,
        "trigger": trigger,
        "reason": reason,
        "assigned_agent": getattr(lead, "assigned_agent", None),
        "chat_context": (chat_context or "")[:4000],
        "catalog_event": PRIMARY_EVENT,
    }


async def _safe_publish(event_type: str, client_id: int, lead_id: Any, payload: dict, source: str) -> None:
    try:
        from app.clients.event_bus_client import event_bus

        await event_bus.publish(
            event_type,
            f"Client_{client_id}",
            str(lead_id),
            payload,
            source=source,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s publish failed client=%s lead=%s: %s", event_type, client_id, lead_id, exc)


async def publish_lead_hot(
    *,
    client_id: int,
    lead: Any,
    trigger: str,
    reason: str,
    session_id: Optional[str] = None,
    chat_context: str = "",
    score: Any = None,
    source: str = "system",
    force: bool = False,
    dual_publish_alias: bool = True,
) -> bool:
    """Publish ``lead.hot`` and optionally alias ``lead.escalated`` (PR #10).

    Returns True if at least the primary publish was attempted (not debounced).
    """
    lead_id = getattr(lead, "id", None)
    if lead_id is None or client_id is None:
        return False

    if not force:
        allowed = await _debounce_allow(int(client_id), int(lead_id), trigger)
        if not allowed:
            logger.debug(
                "lead.hot debounced client=%s lead=%s trigger=%s",
                client_id, lead_id, trigger,
            )
            return False

    payload = build_lead_hot_payload(
        lead,
        trigger=trigger,
        reason=reason,
        session_id=session_id,
        chat_context=chat_context,
        score=score,
    )
    # Primary catalog event
    await _safe_publish(PRIMARY_EVENT, int(client_id), lead_id, payload, source)
    # ALIAS: lead.escalated mirrors lead.hot for n8n PR#10; prefer lead.hot long-term.
    if dual_publish_alias:
        alias_payload = {**payload, "alias_of": PRIMARY_EVENT}
        await _safe_publish(ALIAS_EVENT, int(client_id), lead_id, alias_payload, source)
    return True


async def publish_session_completed(
    *,
    client_id: int,
    lead: Any,
    session_id: str,
    close_reason: str,
    chat_context: str = "",
    source: str = "agent",
) -> bool:
    """Publish PR #10 ``session.completed`` (alias alongside catalog ``lead.qualified``).

    Call only on transition to session.status == closed. Prefer ``lead.qualified``
    for CRM field sync; this event carries transcript for n8n notes.
    """
    lead_id = getattr(lead, "id", None)
    if lead_id is None or client_id is None:
        return False
    payload = {
        "lead_id": lead_id,
        "session_id": session_id,
        "close_reason": close_reason,
        "name": getattr(lead, "name", None),
        "phone": getattr(lead, "phone", None),
        "location": getattr(lead, "location", None),
        "budget": getattr(lead, "budget", None),
        "property_type": getattr(lead, "property_type", None),
        "intent": getattr(lead, "intent", None),
        "lead_temperature": getattr(lead, "lead_temperature", None),
        "conversion_probability": getattr(lead, "conversion_probability", None),
        "chat_context": (chat_context or "")[:4000],
        "catalog_note": "Prefer lead.qualified for field sync; session.completed is PR#10 alias for n8n CRM notes",
    }
    await _safe_publish("session.completed", int(client_id), lead_id, payload, source)
    return True
