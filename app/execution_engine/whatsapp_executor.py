"""IREIOS 3.0 — Phase 3.1 WhatsApp Executor.

Ports the Twilio WhatsApp send (currently scattered across ``main.py``,
``follow_up.py``, ``notification_service.py``) into a single Execution-Engine
executor so every outbound WhatsApp message flows through ``AE -> EE -> Event``.

Runtime: ``Event -> CEO -> Agent/Workflow -> Automation Engine -> Execution Engine -> Event``.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from app.execution_engine.base_executor import BaseExecutor
from config import settings

logger = logging.getLogger("executor.whatsapp")


def get_twilio_client():
    """Return a configured Twilio REST client, or ``None`` if unconfigured.

    Centralised so legacy call sites could refactor onto this helper later.
    """
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        return None
    from twilio.rest import Client

    return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)


def _normalize_to(to: str) -> str:
    """Ensure a WhatsApp-formatted destination number."""
    to = (to or "").strip()
    if to.startswith("whatsapp:"):
        return to
    return f"whatsapp:{to}"


class WhatsAppExecutor(BaseExecutor):
    """Sends a WhatsApp message via Twilio.

    Expected ``parameters``:
        - ``phone`` / ``to`` (destination, with or without ``whatsapp:`` prefix)
        - ``message`` / ``body`` (text)
        - ``media_url`` (optional — brochure / floor plan / document)
        - ``status_callback`` (optional)

    In ``TEST_MODE`` no client is created and a fake success is returned so the
    pipeline can be exercised end-to-end without hitting Twilio.
    """

    action_type = "send_whatsapp"

    async def execute(self, action_request: dict) -> dict:
        params = action_request.get("parameters", {}) or {}
        to = params.get("phone") or params.get("to")
        body = params.get("message") or params.get("body")
        media_url = params.get("media_url")
        status_callback = params.get("status_callback")

        if not to:
            return {"status": "error", "error": "missing 'phone'/'to' in parameters"}
        if not body and not media_url:
            return {"status": "error", "error": "missing 'message'/'body' or 'media_url'"}

        to_number = _normalize_to(to)

        if settings.TEST_MODE:
            logger.info("[TEST_MODE] WhatsApp send skipped to %s: %s", to_number, (body or "")[:80])
            return {
                "status": "success",
                "mode": "test",
                "to": to_number,
                "sid": "TEST_MODE",
            }

        client = get_twilio_client()
        if client is None:
            return {"status": "error", "error": "twilio_not_configured"}

        try:
            sid = await asyncio.to_thread(
                self._send_sync, client, to_number, body or "", media_url, status_callback
            )
            return {"status": "success", "to": to_number, "sid": sid}
        except Exception as exc:  # noqa: BLE001 - EE captures into DLQ
            logger.error("WhatsApp send failed to %s: %s", to_number, exc)
            return {"status": "error", "error": str(exc)}

    @staticmethod
    def _send_sync(client, to_number: str, body: str, media_url, status_callback) -> str:
        kwargs: dict[str, Any] = {
            "from_": settings.TWILIO_PHONE_NUMBER,
            "body": body,
            "to": to_number,
        }
        if media_url:
            kwargs["media_url"] = [media_url] if isinstance(media_url, str) else list(media_url)
        if status_callback and getattr(settings, "WEBHOOK_BASE_URL", ""):
            kwargs["status_callback"] = status_callback
        message = client.messages.create(**kwargs)
        return getattr(message, "sid", "unknown")
