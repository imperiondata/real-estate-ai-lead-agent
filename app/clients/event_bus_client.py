"""IREIOS 3.0 — Redis Streams Event Bus client.

Transport for the Phase 1 runtime: ``Event -> CEO -> Agent/Workflow ->
Automation Engine -> Execution Engine -> Event``.

The production bus is **Redis Streams only** (no in-process asyncio.Queue
fallback). Events are durable: a consumer that crashes before acking leaves
the message in the consumer-group Pending Entries List (PEL) and it is
redelivered to a restarted consumer. n8n can subscribe to the same stream
via a Redis Streams source node.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

import redis.asyncio as aioredis

from config import settings

logger = logging.getLogger("event_bus")

# A handler is an async or sync callable accepting the event envelope dict.
Handler = Callable[[dict], Any]


class EventBusClient:
    """Redis Streams backed publish/subscribe event bus.

    One instance == one consumer in the consumer group. Multi-worker
    deployments each run their own instance (distinct consumer name) so
    messages are load-balanced across workers, while the PEL guarantees
    at-least-once delivery even across restarts.
    """

    def __init__(
        self,
        stream: Optional[str] = None,
        group: Optional[str] = None,
        redis_url: Optional[str] = None,
        consumer: Optional[str] = None,
    ):
        self.stream = stream or settings.EVENT_STREAM_KEY
        self.group = group or settings.EVENT_CONSUMER_GROUP
        self.redis_url = redis_url or settings.REDIS_URL
        self._redis: Optional[aioredis.Redis] = None
        self._pub_redis: Optional[aioredis.Redis] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._handlers: dict[str, list[Handler]] = {}
        self._wildcards: list[Handler] = []
        self._consumer = consumer or f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self._drained_pending = False

    # ------------------------------------------------------------------ #
    # Envelope
    # ------------------------------------------------------------------ #
    @staticmethod
    def build_envelope(
        event_type: str,
        tenant_id: str,
        entity_id: str,
        payload: Any,
        source: str = "system",
        correlation_id: Optional[str] = None,
    ) -> dict:
        return {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "tenant_id": tenant_id,
            "entity_id": entity_id,
            "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "correlation_id": correlation_id or str(uuid.uuid4()),
            "payload": payload,
        }

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    async def start(self) -> None:
        """Idempotently connect, create the consumer group, start the loop."""
        if self._running:
            return
        self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
        # Dedicated client for publish so a blocking consumer read never
        # contends on the same connection/pool as a writer.
        self._pub_redis = aioredis.from_url(self.redis_url, decode_responses=True)
        try:
            await self._redis.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except aioredis.ResponseError as exc:
            if "BUSYGROUP" in str(exc):
                pass  # group already exists — safe to join
            else:
                raise
        self._running = True
        self._drained_pending = False
        self._task = asyncio.create_task(self._consume_loop())
        logger.info("EventBus started: stream=%s group=%s consumer=%s", self.stream, self.group, self._consumer)

    async def stop(self) -> None:
        """Cancel the consumer loop and close the connection safely."""
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
        for client in (self._redis, self._pub_redis):
            if client is not None:
                try:
                    if hasattr(client, "aclose"):
                        await client.aclose()
                    else:  # pragma: no cover - older redis-py
                        await client.close()
                except Exception:  # noqa: BLE001 - best-effort close
                    pass
        self._redis = None
        self._pub_redis = None
        logger.info("EventBus stopped: stream=%s group=%s", self.stream, self.group)

    # ------------------------------------------------------------------ #
    # Subscription
    # ------------------------------------------------------------------ #
    def subscribe(self, event_type: str, handler: Handler) -> None:
        """Register a handler for an exact event_type.

        Use ``event_type == "*"`` to receive every event (CEO uses this).
        """
        if event_type == "*":
            self._wildcards.append(handler)
        else:
            self._handlers.setdefault(event_type, []).append(handler)

    # ------------------------------------------------------------------ #
    # Publish
    # ------------------------------------------------------------------ #
    async def publish(
        self,
        event_type: str,
        tenant_id: str,
        entity_id: str,
        payload: Any,
        source: str = "system",
        correlation_id: Optional[str] = None,
    ) -> str:
        """Publish an event envelope to the stream.

        Fails loudly (raises) if Redis is unavailable — never pretends
        success.
        """
        if not self._running or self._pub_redis is None:
            raise RuntimeError("EventBusClient.publish called before start()")
        envelope = self.build_envelope(event_type, tenant_id, entity_id, payload, source, correlation_id)
        try:
            await self._pub_redis.xadd(self.stream, {"data": json.dumps(envelope, default=str)})
        except aioredis.RedisError as exc:
            logger.error("EventBus publish failed on stream=%s: %s", self.stream, exc)
            raise
        logger.info(
            "published event_id=%s type=%s tenant=%s entity=%s",
            envelope["event_id"],
            event_type,
            tenant_id,
            entity_id,
        )
        return envelope["event_id"]

    # ------------------------------------------------------------------ #
    # Consumer loop
    # ------------------------------------------------------------------ #
    async def _fetch_entries(self):
        if not self._drained_pending:
            self._drained_pending = True
            # Short blocking sweep of any messages left in the PEL by a
            # previous (crashed) consumer sharing this identity. We use a
            # small explicit `block` (not 0, which means block-forever, and
            # not omitted, which proved to stall in some clients) so the
            # loop never wedges on startup.
            try:
                resp = await asyncio.wait_for(
                    self._redis.xreadgroup(
                        self.group, self._consumer, {self.stream: "0"}, count=10, block=10
                    ),
                    timeout=2,
                )
            except (asyncio.TimeoutError, aioredis.RedisError) as exc:
                logger.warning("EventBus pending-drain skipped: %s %r", type(exc).__name__, exc)
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
                entries = await self._fetch_entries()
                if not entries:
                    continue
                for msg_id, fields in entries:
                    try:
                        envelope = json.loads(fields.get("data", "{}"))
                    except (ValueError, TypeError):
                        logger.error("bad envelope json for msg=%s; acking to avoid poison loop", msg_id)
                        await self._redis.xack(self.stream, self.group, msg_id)
                        continue
                    await self._dispatch(envelope)
                    await self._redis.xack(self.stream, self.group, msg_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - loop must not die silently
            logger.error("EventBus consume loop crashed: %s", exc)
        finally:
            self._running = False

    async def _dispatch(self, envelope: dict) -> None:
        event_type = envelope.get("event_type")
        handlers: list[Handler] = list(self._handlers.get(event_type, [])) + list(self._wildcards)
        if not handlers:
            return
        results = await asyncio.gather(
            *(self._safe_call(h, envelope) for h in handlers),
            return_exceptions=True,
        )
        for handler, res in zip(handlers, results):
            if isinstance(res, Exception):
                logger.error(
                    "handler %s failed on event_type=%s: %s",
                    getattr(handler, "__name__", handler),
                    event_type,
                    res,
                )

    @staticmethod
    async def _safe_call(handler: Handler, envelope: dict):
        if asyncio.iscoroutinefunction(handler):
            return await handler(envelope)
        return handler(envelope)


# Module-level singleton used by the application (wired in lifespan at 1.7).
event_bus = EventBusClient()
