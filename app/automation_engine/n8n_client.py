"""IREIOS 3.0 — Phase 2 n8n client scaffold.

Thin async client for triggering n8n workflows via their webhook REST API.
n8n can also subscribe directly to the Redis Streams bus (same transport as
Phase 1) for event-driven automations — this client covers the outbound
HTTP-trigger direction so the Automation Engine can hand off ``template_type="n8n"``
actions.

When ``N8N_BASE_URL`` / ``N8N_API_KEY`` are not configured the client returns
a clean ``n8n_not_configured`` error (never crashes), matching the repo's
demo-stub philosophy (see ``crm_sync``).
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
        self.base_url = (base_url or settings.N8N_BASE_URL or "").rstrip("/")
        self.api_key = api_key or settings.N8N_API_KEY or ""

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    async def trigger_workflow(self, workflow_id: str, payload: dict) -> dict:
        """Trigger an n8n workflow by id/path with the given payload.

        Returns the n8n response JSON, or ``{"status":"error","error":"n8n_not_configured"}``
        when the service is not configured. Uses an async httpx client with a
        sensible timeout.
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
                return {"status": "success", "workflow_id": workflow_id, "response": resp.json()}
        except httpx.HTTPStatusError as exc:
            logger.error("n8n trigger %s returned %s", workflow_id, exc.response.status_code)
            return {"status": "error", "error": f"n8n_http_{exc.response.status_code}"}
        except Exception as exc:  # noqa: BLE001 - network/timeout etc.
            logger.error("n8n trigger %s failed: %s", workflow_id, exc)
            return {"status": "error", "error": "n8n_unreachable"}


# Module-level singleton consumed by the Automation Engine for n8n actions.
n8n_client = N8NClient()
