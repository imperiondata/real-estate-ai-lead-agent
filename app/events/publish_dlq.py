"""Record a failed bus publish. Replay does not republish these rows."""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("publish_dlq")


def _client_id(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def record_publish_failure(
    event_type: str,
    client_id: Any,
    entity_id: Any,
    payload: Optional[dict],
    source: str,
    error: BaseException,
    session_factory=None,
) -> None:
    """Write one pending dlq_events row. Never raises. Never defaults client_id to 1."""
    stored_client = _client_id(client_id)
    body = dict(payload or {})
    body.pop("phone", None)
    row_payload = {
        "event_type": event_type,
        "tenant_id": f"Client_{stored_client}" if stored_client else None,
        "entity_id": None if entity_id is None else str(entity_id),
        "source": source,
        "payload": body,
    }
    try:
        if session_factory is None:
            from database import SessionLocal

            session_factory = SessionLocal
        db = session_factory()
        try:
            from models import DLQEvent

            db.add(
                DLQEvent(
                    client_id=stored_client,
                    target_endpoint="event_bus",
                    payload=row_payload,
                    error_trace=str(error),
                    status="pending",
                )
            )
            db.commit()
        finally:
            close = getattr(db, "close", None)
            if close:
                close()
    except Exception as exc:  # noqa: BLE001 - DLQ write must not break the caller
        logger.error("publish DLQ write failed event=%s: %s", event_type, exc)
