"""Tenant-scoped email and webhook delivery for a new lead.

This is not ``notification_service.send_fallback_email`` (an agent alert when
WhatsApp fails) and it is not ``WebhookLog`` (inbound MessageSid dedupe). It
reads the tenant's own ``notify_email`` and ``webhook_url`` from
``Client.settings`` and records every attempt in a client-scoped ``EventLog``
row, so a delivery failure can never turn a chat reply into a 500.

When ``settings.TEST_MODE`` is true no SMTP connection and no HTTP request is
made, even if the real callables are passed in. The row is written with
``agent_type=recorded``.

Only ``sent`` and ``recorded`` suppress a later send. A failed row stays for
audit and does not block a retry. Transient failures are retried up to
``MAX_DELIVERY_ATTEMPTS`` inside the call. Permanent failures are not retried.

Transport callables are injectable for tests:

- ``email_sender(to, subject, body)``
- ``webhook_poster(url, payload)``
"""

from __future__ import annotations

import json
import logging
import smtplib
import time
import urllib.error
import urllib.request
from email.message import EmailMessage
from typing import Callable, Optional

from config import settings
from models import EventLog

logger = logging.getLogger(__name__)

EVENT_TYPE = "tenant_delivery"
ACTION_EMAIL = "tenant_email"
ACTION_WEBHOOK = "tenant_webhook"
ACTION_SKIPPED = "tenant_delivery_skipped"

AGENT_SENT = "sent"
AGENT_RECORDED = "recorded"
AGENT_NO_TARGET = "no_target"
AGENT_SMTP_UNCONFIGURED = "smtp_unconfigured"
AGENT_WEBHOOK_FAILED = "webhook_failed"
AGENT_EMAIL_FAILED = "email_failed"

COMPLETED_AGENTS = frozenset({AGENT_SENT, AGENT_RECORDED})
MAX_DELIVERY_ATTEMPTS = 3
EMAIL_SUBJECT = "New lead"
WEBHOOK_TIMEOUT_SECONDS = 5
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

EmailSender = Callable[[str, str, str], None]
WebhookPoster = Callable[[str, dict], None]
Sleeper = Callable[[float], None]


class PermanentDeliveryError(Exception):
    """Non-retryable transport failure. HTTP 4xx (except 408/429) and SMTP 5xx."""


class TransientDeliveryError(Exception):
    """Retryable transport failure. Connection loss, timeout, SMTP 4xx, HTTP 5xx."""


def _targets(client) -> tuple[Optional[str], Optional[str]]:
    """Read only notify_email and webhook_url. Anything unusable is ignored."""
    raw = getattr(client, "settings", None) or {}
    if not isinstance(raw, dict):
        return None, None

    email = raw.get("notify_email")
    email = email.strip() if isinstance(email, str) else ""
    if "@" not in email:
        email = ""

    webhook = raw.get("webhook_url")
    webhook = webhook.strip() if isinstance(webhook, str) else ""
    if not webhook.startswith(("http://", "https://")):
        webhook = ""

    return email or None, webhook or None


def _smtp_configured() -> bool:
    return bool(
        getattr(settings, "SMTP_HOST", "")
        and getattr(settings, "SMTP_PORT", 0)
        and getattr(settings, "SMTP_USER", "")
        and getattr(settings, "SMTP_PASS", "")
    )


def _is_loopback(host: str) -> bool:
    return (host or "").strip().lower() in _LOOPBACK_HOSTS


def _email_body(lead) -> str:
    return "\n".join(
        [
            "A new lead was created.",
            "",
            f"Name: {getattr(lead, 'name', None) or ''}",
            f"Phone: {getattr(lead, 'phone', None) or ''}",
            f"Location: {getattr(lead, 'location', None) or ''}",
            f"Budget: {getattr(lead, 'budget', None) or ''}",
        ]
    )


def _webhook_payload(client_id: int, lead) -> dict:
    return {
        "lead_id": getattr(lead, "id", None),
        "tenant_id": client_id,
        "name": getattr(lead, "name", None),
        "phone": getattr(lead, "phone", None),
    }


def _default_email_sender(to: str, subject: str, body: str) -> None:
    host = settings.SMTP_HOST
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.SMTP_USER
    message["To"] = to
    message.set_content(body)
    with smtplib.SMTP(host, settings.SMTP_PORT, timeout=5) as server:
        # A loopback sink is the local proof only. Any other host still uses TLS.
        if not _is_loopback(host):
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASS)
        server.send_message(message)


def _default_webhook_poster(url: str, payload: dict) -> None:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=WEBHOOK_TIMEOUT_SECONDS) as response:
        response.read(1)


def is_transient(exc: BaseException) -> bool:
    """True when another attempt might succeed. Permanent 4xx/5xx return False."""
    if isinstance(exc, PermanentDeliveryError):
        return False
    if isinstance(exc, TransientDeliveryError):
        return True
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in (408, 429) or exc.code >= 500
    if isinstance(exc, smtplib.SMTPResponseException):
        return 400 <= int(exc.smtp_code) < 500
    if isinstance(
        exc,
        (
            TimeoutError,
            ConnectionError,
            urllib.error.URLError,
            OSError,
            smtplib.SMTPServerDisconnected,
            smtplib.SMTPConnectError,
        ),
    ):
        return True
    # An unclassified drop is retried. Callers that mean "do not retry" raise
    # PermanentDeliveryError or an HTTP/SMTP permanent response.
    return True


def _send_with_retry(
    operation: Callable[[], None],
    *,
    max_attempts: int,
    retry_sleep: float,
    sleeper: Sleeper,
) -> None:
    attempts = max(1, int(max_attempts))
    for attempt in range(1, attempts + 1):
        try:
            operation()
            return
        except Exception as exc:
            if not is_transient(exc) or attempt >= attempts:
                raise
            logger.warning(
                "tenant delivery transient failure; retrying attempt=%s", attempt
            )
            if retry_sleep:
                sleeper(retry_sleep)


def _already_recorded(db, client_id: int, session_id: str, action_type: str) -> bool:
    return (
        db.query(EventLog.id)
        .filter(
            EventLog.client_id == client_id,
            EventLog.session_id == session_id,
            EventLog.event_type == EVENT_TYPE,
            EventLog.action_type == action_type,
        )
        .first()
        is not None
    )


def _already_succeeded(db, client_id: int, session_id: str, action_type: str) -> bool:
    """True only after a completed send. A failed row does not count."""
    return (
        db.query(EventLog.id)
        .filter(
            EventLog.client_id == client_id,
            EventLog.session_id == session_id,
            EventLog.event_type == EVENT_TYPE,
            EventLog.action_type == action_type,
            EventLog.agent_type.in_(tuple(COMPLETED_AGENTS)),
        )
        .first()
        is not None
    )


def _row(client_id: int, session_id: str, action_type: str, agent_type: str) -> EventLog:
    return EventLog(
        session_id=session_id,
        client_id=client_id,
        event_type=EVENT_TYPE,
        action_type=action_type,
        agent_type=agent_type,
    )


def deliver_tenant_lead(
    db,
    client,
    lead,
    session_id: str,
    *,
    email_sender: Optional[EmailSender] = None,
    webhook_poster: Optional[WebhookPoster] = None,
    max_attempts: int = MAX_DELIVERY_ATTEMPTS,
    retry_sleep: float = 0.0,
    sleeper: Optional[Sleeper] = None,
) -> list[str]:
    """Deliver to the tenant's own targets and record the outcome. Never raises."""
    client_id = getattr(client, "id", None)
    if client_id is None or not session_id:
        return []

    test_mode = bool(getattr(settings, "TEST_MODE", False))
    pause = sleeper or time.sleep
    rows: list[EventLog] = []
    try:
        email, webhook = _targets(client)

        if not email and not webhook:
            if not _already_recorded(db, client_id, session_id, ACTION_SKIPPED):
                rows.append(_row(client_id, session_id, ACTION_SKIPPED, AGENT_NO_TARGET))
                db.add_all(rows)
                db.commit()
                return [ACTION_SKIPPED]
            return []

        if email and not _already_succeeded(db, client_id, session_id, ACTION_EMAIL):
            if test_mode:
                agent_type = AGENT_RECORDED
            else:
                # An injected sender is the transport. SMTP configuration only
                # gates the default sender, so tests never touch a real server.
                sender = email_sender or _default_email_sender
                if email_sender is None and not _smtp_configured():
                    agent_type = AGENT_SMTP_UNCONFIGURED
                else:
                    try:
                        _send_with_retry(
                            lambda: sender(email, EMAIL_SUBJECT, _email_body(lead)),
                            max_attempts=max_attempts,
                            retry_sleep=retry_sleep,
                            sleeper=pause,
                        )
                        agent_type = AGENT_SENT
                    except Exception:
                        logger.exception("tenant email delivery failed")
                        agent_type = AGENT_EMAIL_FAILED
            rows.append(_row(client_id, session_id, ACTION_EMAIL, agent_type))

        if webhook and not _already_succeeded(db, client_id, session_id, ACTION_WEBHOOK):
            if test_mode:
                agent_type = AGENT_RECORDED
            else:
                try:
                    poster = webhook_poster or _default_webhook_poster
                    _send_with_retry(
                        lambda: poster(webhook, _webhook_payload(client_id, lead)),
                        max_attempts=max_attempts,
                        retry_sleep=retry_sleep,
                        sleeper=pause,
                    )
                    agent_type = AGENT_SENT
                except Exception:
                    logger.exception("tenant webhook delivery failed")
                    agent_type = AGENT_WEBHOOK_FAILED
            rows.append(_row(client_id, session_id, ACTION_WEBHOOK, agent_type))

        if not rows:
            return []

        db.add_all(rows)
        db.commit()
        return [row.action_type for row in rows]
    except Exception:
        logger.exception("tenant delivery failed")
        try:
            db.rollback()
        except Exception:
            pass
        return []
