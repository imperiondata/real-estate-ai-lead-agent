"""Shared outbound WhatsApp send — single path through WhatsAppExecutor.

Production code (escalation, notifications, background helpers) should call
these helpers instead of constructing a Twilio Client directly.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger("outbound")


async def send_whatsapp_async(
    *,
    to: str,
    body: str,
    tenant_id: str = "system",
    entity_id: str = "outbound",
    source: str = "outbound",
    media_url: Optional[str] = None,
) -> dict[str, Any]:
    """Send via AutomationEngine → WhatsAppExecutor (DLQ-protected)."""
    from app.automation_engine.engine import submit as ae_submit

    params: dict[str, Any] = {"to": to, "body": body, "source": source}
    if media_url:
        params["media_url"] = media_url
    return await ae_submit(
        {
            "action_type": "send_whatsapp",
            "tenant_id": tenant_id,
            "entity_id": entity_id,
            "parameters": params,
            "source": source,
        }
    )


async def send_whatsapp_via_executor(
    *,
    to: str,
    body: str,
    source: str = "outbound",
    media_url: Optional[str] = None,
) -> dict[str, Any]:
    """Direct EE path (no AE approval). Used by sync cron when AE loop is awkward."""
    from app.execution_engine.whatsapp_executor import WhatsAppExecutor

    params: dict[str, Any] = {"to": to, "body": body, "source": source}
    if media_url:
        params["media_url"] = media_url
    return await WhatsAppExecutor().execute({"parameters": params})


def send_whatsapp_blocking(
    *,
    to: str,
    body: str,
    tenant_id: str = "system",
    entity_id: str = "outbound",
    source: str = "outbound",
    media_url: Optional[str] = None,
) -> dict[str, Any]:
    """Sync wrapper for APScheduler / non-async call sites."""

    async def _run() -> dict[str, Any]:
        # Prefer full AE when possible; executor-only is fine for cron.
        try:
            return await send_whatsapp_async(
                to=to,
                body=body,
                tenant_id=tenant_id,
                entity_id=entity_id,
                source=source,
                media_url=media_url,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("AE send failed (%s); falling back to executor: %s", source, exc)
            return await send_whatsapp_via_executor(
                to=to, body=body, source=source, media_url=media_url
            )

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_run())
    # Already inside an event loop (rare for cron): schedule on a fresh loop in a thread.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(_run())).result(timeout=45)
