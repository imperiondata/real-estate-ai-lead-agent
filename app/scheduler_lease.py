"""Redis lease so only one API replica runs each scheduler tick."""
from __future__ import annotations

import logging
from typing import Callable, Optional

import redis

from config import settings

logger = logging.getLogger("scheduler_lease")


def run_with_lease(job_id: str, lease_seconds: int, fn: Callable, client=None):
    """Run fn only if this process wins scheduler_lease:{job_id}.

    The key is not deleted. The TTL is the lease, so a late replica cannot
    run the same tick after the winner finishes early. Redis down or a
    missing URL skips the job.
    """
    if not job_id or lease_seconds <= 0:
        logger.warning("scheduler skip %s: bad lease", job_id)
        return None
    redis_client = client
    if redis_client is None:
        url = (getattr(settings, "REDIS_URL", None) or "").strip()
        if not url:
            logger.warning("scheduler skip %s: redis url missing", job_id)
            return None
        try:
            redis_client = redis.Redis.from_url(
                url, socket_connect_timeout=2, socket_timeout=2
            )
        except Exception as exc:
            logger.warning("scheduler skip %s: redis client failed: %s", job_id, exc)
            return None
    key = f"scheduler_lease:{job_id}"
    try:
        acquired = redis_client.set(key, "1", nx=True, ex=int(lease_seconds))
    except Exception as exc:
        logger.warning("scheduler skip %s: redis error: %s", job_id, exc)
        return None
    if not acquired:
        logger.info("scheduler skip %s: lease held", job_id)
        return None
    return fn()


def leased(job_id: str, lease_seconds: int, fn: Callable):
    def wrapped(*args, **kwargs):
        return run_with_lease(job_id, lease_seconds, lambda: fn(*args, **kwargs))

    wrapped.__name__ = getattr(fn, "__name__", job_id)
    wrapped.__wrapped__ = fn
    return wrapped
