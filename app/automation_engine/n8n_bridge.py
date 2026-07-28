"""Bus → n8n webhook bridge (separate Redis Streams consumer group).

Stock n8n cannot consume Redis Streams (Redis Trigger = Pub/Sub only). This
bridge joins consumer group ``ireios-n8n`` on the same stream as the CEO
(``ireios-cg``), filters allowlisted ``event_type`` values, and POSTs the full
bus envelope to ``POST {N8N_BASE_URL}/webhook/{path}``.

Never joins the CEO group (would steal messages). No-ops when n8n is
unconfigured or ``N8N_BRIDGE_ENABLED=false``. Failures never crash the API.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import uuid
from typing import Any, Optional

import redis.asyncio as aioredis

from config import settings

logger = logging.getLogger("n8n_bridge")

# Catalog events only — never map lead.escalated alongside lead.hot (double email).
DEFAULT_WEBHOOK_MAP: dict[str, str] = {
    "lead.hot": "ireios_hot_lead_alert",
    "site_visit.scheduled": "ireios_visit_fanout",
    "approval.requested": "ireios_hitl_notify",
    "lead.qualified": "ireios_crm_append",
    "marketing.report.generated": "ireios_marketing_csv",
}

# 5xx / network: leave in PEL and retry. 4xx / success: XACK.
_RETRYABLE_ERRORS = frozenset({"n8n_unreachable", "n8n_http_500", "n8n_http_502", "n8n_http_503", "n8n_http_504"})


def parse_webhook_map(raw: Optional[str] = None) -> dict[str, str]:
    """Parse ``N8N_WEBHOOK_MAP`` JSON override; fall back to defaults."""
    text = (raw if raw is not None else getattr(settings, "N8N_WEBHOOK_MAP", "") or "").strip()
    if not text:
        return dict(DEFAULT_WEBHOOK_MAP)
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            logger.warning("N8N_WEBHOOK_MAP is not a JSON object; using defaults")
            return dict(DEFAULT_WEBHOOK_MAP)
        out: dict[str, str] = {}
        for k, v in data.items():
            if k and v is not None and str(v).strip():
                out[str(k)] = str(v).strip()
        return out or dict(DEFAULT_WEBHOOK_MAP)
    except (TypeError, ValueError) as exc:
        logger.warning("N8N_WEBHOOK_MAP parse failed (%s); using defaults", exc)
        return dict(DEFAULT_WEBHOOK_MAP)


class N8NBridge:
    """Independent Streams consumer that forwards allowlisted events to n8n."""

    def __init__(
        self,
        *,
        stream: Optional[str] = None,
        group: Optional[str] = None,
        redis_url: Optional[str] = None,
        consumer: Optional[str] = None,
        webhook_map: Optional[dict[str, str]] = None,
        n8n_client: Any = None,
    ):
        self.stream = stream or settings.EVENT_STREAM_KEY
        self.group = group or getattr(settings, "N8N_BRIDGE_GROUP", None) or "ireios-n8n"
        self.redis_url = redis_url or settings.REDIS_URL
        self._consumer = consumer or f"n8n-{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.webhook_map = dict(webhook_map) if webhook_map is not None else parse_webhook_map()
        self._n8n_client = n8n_client
        self._redis: Optional[aioredis.Redis] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._drained_pending = False

    @property
    def enabled(self) -> bool:
        return bool(getattr(settings, "N8N_BRIDGE_ENABLED", True))

    def _client(self):
        if self._n8n_client is not None:
            return self._n8n_client
        from app.automation_engine.n8n_client import N8NClient

        return N8NClient()

    async def start(self) -> None:
        if self._running:
            return
        if not self.enabled:
            logger.info("n8n bridge disabled (N8N_BRIDGE_ENABLED=false)")
            return
        self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
        try:
            await self._redis.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except aioredis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        self._running = True
        self._drained_pending = False
        self._task = asyncio.create_task(self._consume_loop())
        logger.info(
            "n8n bridge started: stream=%s group=%s consumer=%s map=%s",
            self.stream,
            self.group,
            self._consumer,
            sorted(self.webhook_map.keys()),
        )

    async def stop(self) -> None:
        if not self._running and self._task is None:
            return
        self._running = False
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        if self._redis is not None:
            try:
                if hasattr(self._redis, "aclose"):
                    await self._redis.aclose()
                else:  # pragma: no cover
                    await self._redis.close()
            except Exception:  # noqa: BLE001
                pass
        self._redis = None
        logger.info("n8n bridge stopped: stream=%s group=%s", self.stream, self.group)

    async def _fetch_entries(self):
        assert self._redis is not None
        if not self._drained_pending:
            self._drained_pending = True
            try:
                resp = await asyncio.wait_for(
                    self._redis.xreadgroup(
                        self.group, self._consumer, {self.stream: "0"}, count=10, block=10
                    ),
                    timeout=2,
                )
            except (asyncio.TimeoutError, aioredis.RedisError) as exc:
                logger.warning("n8n bridge pending-drain skipped: %s %r", type(exc).__name__, exc)
                return []
            if resp:
                return resp[0][1]
            return []
        resp = await self._redis.xreadgroup(
            self.group, self._consumer, {self.stream: ">"}, count=10, block=250
        )
        if resp:
            return resp[0][1]
        return []

    async def _consume_loop(self) -> None:
        try:
            while self._running:
                try:
                    entries = await self._fetch_entries()
                except Exception as exc:  # noqa: BLE001
                    logger.error("n8n bridge fetch failed: %s", exc)
                    await asyncio.sleep(1.0)
                    continue
                if not entries:
                    continue
                for msg_id, fields in entries:
                    await self._handle_message(msg_id, fields)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("n8n bridge consume loop crashed: %s", exc)
        finally:
            self._running = False

    async def _handle_message(self, msg_id: str, fields: dict) -> None:
        assert self._redis is not None
        try:
            envelope = json.loads(fields.get("data", "{}"))
        except (ValueError, TypeError):
            logger.error("n8n bridge bad envelope json msg=%s; acking", msg_id)
            await self._redis.xack(self.stream, self.group, msg_id)
            return

        event_type = (envelope or {}).get("event_type") or ""
        path = self.webhook_map.get(event_type)
        if not path:
            await self._redis.xack(self.stream, self.group, msg_id)
            return

        client = self._client()
        if not getattr(client, "configured", False):
            # Unconfigured: ack so PEL does not grow forever while n8n is optional.
            logger.debug("n8n bridge skip (not configured) type=%s msg=%s", event_type, msg_id)
            await self._redis.xack(self.stream, self.group, msg_id)
            return

        result = await self.forward_envelope(envelope, path=path, client=client)
        status = (result or {}).get("status")
        err = (result or {}).get("error") or ""
        if status == "success":
            logger.info(
                "n8n_bridge_forwarded type=%s path=%s event_id=%s",
                event_type,
                path,
                envelope.get("event_id"),
            )
            await self._redis.xack(self.stream, self.group, msg_id)
            return

        if err == "n8n_not_configured" or err.startswith("n8n_http_4"):
            logger.warning(
                "n8n_bridge_error permanent type=%s path=%s err=%s; acking",
                event_type,
                path,
                err,
            )
            await self._redis.xack(self.stream, self.group, msg_id)
            return

        # Retryable — leave in PEL for next drain / restart.
        logger.warning(
            "n8n_bridge_error retryable type=%s path=%s err=%s msg=%s",
            event_type,
            path,
            err,
            msg_id,
        )

    async def forward_envelope(
        self,
        envelope: dict,
        *,
        path: Optional[str] = None,
        client: Any = None,
    ) -> dict:
        """POST full bus envelope to n8n webhook. Testable without Redis."""
        event_type = (envelope or {}).get("event_type") or ""
        wf_path = path or self.webhook_map.get(event_type)
        if not wf_path:
            return {"status": "skipped", "error": "no_webhook_mapping"}
        c = client or self._client()
        try:
            return await c.trigger_workflow(wf_path, envelope)
        except Exception as exc:  # noqa: BLE001
            logger.error("n8n bridge forward failed path=%s: %s", wf_path, exc)
            return {"status": "error", "error": "n8n_unreachable"}


# Module-level singleton started from main.py lifespan.
n8n_bridge = N8NBridge()
