"""IREIOS 3.0 — n8n webhook HTTP client.

Used by:
  * Automation Engine when ``template_type="n8n"``
  * ``n8n_bridge`` (bus consumer group ``ireios-n8n`` → POST full envelopes)

Stock n8n cannot XREADGROUP Redis Streams — the bridge is the supported
bus→n8n path. See ``docs/N8N_INTEGRATION.md``.

When ``N8N_BASE_URL`` / ``N8N_API_KEY`` are empty the client returns
``n8n_not_configured`` (never crashes).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from config import settings

logger = logging.getLogger("n8n_client")


class N8NClient:
    """Async trigger client for n8n workflows."""

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        # None → settings; explicit "" stays empty (tests + forced unconfigured).
        self.base_url = (
            (settings.N8N_BASE_URL or "") if base_url is None else (base_url or "")
        ).rstrip("/")
        self.api_key = (
            (settings.N8N_API_KEY or "") if api_key is None else (api_key or "")
        )

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    async def trigger_workflow(self, workflow_id: str, payload: dict) -> dict:
        """Trigger an n8n workflow by id/path with the given payload.

        Returns the n8n response JSON, or ``{"status":"error","error":"n8n_not_configured"}``
        when the service is not configured. Uses an async httpx client with a
        sensible timeout. Empty / non-JSON success bodies are treated as success.
        """
        if not self.configured:
            logger.warning("n8n trigger skipped: not configured (N8N_BASE_URL/N8N_API_KEY)")
            return {"status": "error", "error": "n8n_not_configured"}

        url = f"{self.base_url}/webhook/{workflow_id}"
        headers = {"X-N8N-API-KEY": self.api_key, "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                body: Any = None
                if resp.content:
                    try:
                        body = resp.json()
                    except Exception:  # noqa: BLE001 - plain text / empty ok
                        body = {"raw": resp.text[:500]}
                return {"status": "success", "workflow_id": workflow_id, "response": body}
        except httpx.HTTPStatusError as exc:
            logger.error("n8n trigger %s returned %s", workflow_id, exc.response.status_code)
            return {"status": "error", "error": f"n8n_http_{exc.response.status_code}"}
        except Exception as exc:  # noqa: BLE001 - network/timeout etc.
            logger.error("n8n trigger %s failed: %s", workflow_id, exc)
            return {"status": "error", "error": "n8n_unreachable"}


# Module-level singleton consumed by the Automation Engine for n8n actions.
n8n_client = N8NClient()
