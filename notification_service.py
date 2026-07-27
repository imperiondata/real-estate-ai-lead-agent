import logging
import os
import smtplib
from email.message import EmailMessage
from datetime import datetime, timezone, timedelta

from config import settings
from database import SessionLocal
from models import Lead, NotificationLog, Agent

logger = logging.getLogger("notification_service")


def terminal_status_after_failed_delivery_alert(current_status: str) -> str:
    """P0.6: after ops is notified of a failed delivery, stop re-selecting the row."""
    if current_status == "failed":
        return "failed_alerted"
    return current_status


def send_fallback_email(agent_email: str, agent_name: str, lead: Lead, reason: str):
    """Sends an email fallback if Twilio WhatsApp dispatch fails."""
    try:
        smtp_host = settings.SMTP_HOST
        smtp_port = settings.SMTP_PORT
        smtp_user = settings.SMTP_USER
        smtp_pass = settings.SMTP_PASS

        if not smtp_user or not smtp_pass:
            logger.error("Email fallback failed: SMTP credentials not configured in environment.")
            return

        msg = EmailMessage()
        msg['Subject'] = f"🚨 URGENT: Hot Lead Alert (System Fallback) - {lead.name or 'Unknown'}"
        msg['From'] = smtp_user
        msg['To'] = agent_email

        dashboard_link = f"http://localhost:3000/crm?lead_id={lead.id}"
        body = f"""
Hello {agent_name},

Our WhatsApp notification system encountered a connectivity issue. 
This is an automated EMAIL FALLBACK for a Hot Lead.

Lead Name: {lead.name or 'Unknown'}
Intent: {lead.intent or 'explore'}
Property Type: {lead.property_type or 'property'}
Location: {lead.location or 'Pune'}
Budget: {lead.budget or 'TBD'}

Reason for Alert: {reason}

Please contact the lead immediately.
View in CRM: {dashboard_link}
        """
        msg.set_content(body)

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)

        logger.info(f"Fallback email successfully sent to {agent_email}")
    except Exception as email_err:
        logger.error(f"Fallback email dispatch failed: {email_err}")


def resolve_hot_alert_recipient(target_agent, admin_email: str = "") -> dict | None:
    """
    P0.2 / P0.3: Only an Agent (or manager) may receive hot-lead WhatsApp.
    Never falls back to the lead's phone. Returns None if dispatch is unsafe.
    """
    if not target_agent:
        return None
    phone = (getattr(target_agent, "phone", None) or "").strip()
    if not phone:
        return None
    return {
        "phone": phone,
        "name": getattr(target_agent, "name", None) or "Agent",
        "email": getattr(target_agent, "email", None) or admin_email or "",
    }


def pick_escalation_agent(agents, tier: str) -> "Agent | None":
    """
    P4.1 (pure): choose the escalation recipient from a list of agent-like rows.

    - tier == "30m": prefer a director (is_director == True); if none, fall back
      to a manager.
    - tier == "10m": a manager only.

    Returns the chosen agent, or None if no eligible recipient exists.
    """
    if tier == "30m":
        director = next((a for a in agents if getattr(a, "is_director", False)), None)
        if director:
            return director
    return next((a for a in agents if getattr(a, "is_manager", False)), None)


def resolve_escalation_recipient(db, client_id: int, tier: str) -> "Agent | None":
    """
    P4.1: resolve the human who should receive an escalation for a tenant.

    - tier == "10m": the first manager.
    - tier == "30m": the first director; if no director exists, fall back to the
      first manager and log the fallback so the behavior is observable (the 30m
      tier must never silently no-op).

    Selection logic lives in `pick_escalation_agent` (unit-tested without a DB).
    """
    agents = db.query(Agent).filter(Agent.client_id == client_id).all()
    chosen = pick_escalation_agent(agents, tier)
    if tier == "30m" and chosen is not None and not getattr(chosen, "is_director", False):
        logger.warning(
            f"P4.1 ESCALATION FALLBACK: no director for client {client_id}; "
            f"falling back to manager for 30m escalation."
        )
    return chosen


# P4.2: severity ranking for hot-lead alerts. An explicit human handoff must be
# able to "upgrade" an already-open score-threshold alert instead of being
# silently dropped by the idempotency guard.
SEVERITY_SCORE_ALERT = 1
SEVERITY_HANDOFF = 2

# NotificationLog statuses that represent an open/active escalation.
_ACTIVE_ALERT_STATUSES = {"pending_ack", "acknowledged", "escalated_10m", "escalated_30m"}


def classify_reason_severity(reason: str) -> int:
    """
    P4.2 (pure): map an alert reason string to a severity rank.

    Explicit human-handoff reasons outrank score-threshold reasons so a later
    handoff can upgrade an earlier score alert.
    """
    r = (reason or "").lower()
    if "human" in r or "handoff" in r or "requested an agent" in r or "agent requested" in r:
        return SEVERITY_HANDOFF
    return SEVERITY_SCORE_ALERT


def should_upgrade_alert(existing_status: str, existing_severity, new_severity: int) -> bool:
    """
    P4.2 (pure): decide whether an incoming alert should upgrade an existing one.

    True only when there is an active alert AND the new reason is strictly more
    severe than what is already recorded. This bounds upgrades: once upgraded to
    handoff severity, an equal-severity handoff will not upgrade again.
    """
    if existing_status not in _ACTIVE_ALERT_STATUSES:
        return False
    current = existing_severity if existing_severity is not None else SEVERITY_SCORE_ALERT
    return new_severity > current


def _record_failed_notification(db, lead: Lead, assigned_agent: str, reason: str):
    """Persist a failed hot-lead attempt without WhatsApp to the customer."""
    escalation_deadline = datetime.now(timezone.utc) + timedelta(minutes=10)
    db.add(NotificationLog(
        client_id=lead.client_id,
        lead_id=lead.id,
        assigned_agent=assigned_agent,
        status="failed",
        escalate_at=escalation_deadline,
        twilio_message_sid=None,
        reason=reason,
        severity=classify_reason_severity(reason),
    ))
    db.commit()


def _resolve_alert_recipient(db, lead):
    """P0.2/P0.3: resolve the agent (or manager fallback) for a hot-lead alert.

    Never falls back to the lead's own phone. Returns a recipient dict or None.
    """
    target_agent = None
    if lead.assigned_agent:
        target_agent = db.query(Agent).filter(
            Agent.client_id == lead.client_id,
            Agent.name == lead.assigned_agent
        ).first()

    if not target_agent:
        target_agent = db.query(Agent).filter(
            Agent.client_id == lead.client_id,
            Agent.is_manager == True
        ).first()

    return resolve_hot_alert_recipient(target_agent, settings.ADMIN_EMAIL)


async def _send_alert_whatsapp(message_body: str, recipient: dict, lead: Lead, reason: str):
    """Dispatch a WhatsApp alert via EE (WhatsAppExecutor) with retries + email fallback.

    Returns (delivery_status, twilio_sid): "pending_ack" on success (including
    TEST_MODE / no-Twilio simulation) or "failed" when every attempt fails.
    """
    import asyncio

    from app.execution_engine.whatsapp_executor import WhatsAppExecutor

    agent_phone = recipient["phone"]
    agent_name = recipient["name"]
    agent_email = recipient["email"]

    delivery_status = "pending_ack"
    twilio_sid = None
    twilio_success = False

    if settings.TEST_MODE:
        logger.info(f"[TEST MODE] Simulated WhatsApp Alert to {agent_name} ({agent_phone})")
        twilio_success = True
    elif settings.TWILIO_ACCOUNT_SID and agent_phone:
        base_url = settings.WEBHOOK_BASE_URL
        status_callback_url = f"{base_url}/api/v1/webhook/twilio-status" if base_url else None
        executor = WhatsAppExecutor()
        params = {
            "to": agent_phone,
            "body": message_body,
            "source": "hot_lead_alert",
        }
        if status_callback_url:
            params["status_callback"] = status_callback_url

        for attempt in range(3):
            try:
                result = await executor.execute({"parameters": params})
                if result.get("status") == "success":
                    twilio_sid = result.get("sid")
                    delivery_status = "pending_ack"
                    twilio_success = True
                    logger.info(
                        f"WhatsApp Alert dispatched to {agent_name} | SID: {twilio_sid} | Attempt: {attempt + 1}"
                    )
                    break
                raise RuntimeError(result.get("error") or "ee_send_failed")
            except Exception as e:
                logger.warning(f"WhatsApp Alert attempt {attempt + 1} failed: {e}")
                await asyncio.sleep(1)

        if not twilio_success:
            logger.error("All 3 Twilio attempts failed. Triggering Email Fallback.")
            delivery_status = "failed"
            send_fallback_email(agent_email, agent_name, lead, reason)

    return delivery_status, twilio_sid


async def trigger_hot_lead_notification(
    lead_id: int,
    reason: str = "High-intent behavior detected",
    severity: int | None = None,
):
    """
    Asynchronously fires a WhatsApp notification to the assigned agent.
    Guarantees idempotency (no duplicate spam), except that a higher-severity
    reason (P4.2, e.g. an explicit handoff) upgrades an existing lower-severity
    alert once instead of being silently dropped.
    Never sends hot-lead ops alerts to the lead's own phone (P0.2/P0.3).
    """
    with SessionLocal() as db:
        try:
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if not lead:
                return

            new_severity = severity if severity is not None else classify_reason_severity(reason)

            # 1. IDEMPOTENCY CHECK (+ P4.2 severity upgrade)
            existing_log = db.query(NotificationLog).filter(
                NotificationLog.lead_id == lead.id,
                NotificationLog.status.in_(list(_ACTIVE_ALERT_STATUSES))
            ).first()

            if existing_log:
                if not should_upgrade_alert(existing_log.status, existing_log.severity, new_severity):
                    logger.info(f"Notification bypassed: Lead {lead.id} already has an active escalation state.")
                    return

                # P4.2: an existing (lower-severity) alert is upgraded — e.g. a
                # score-threshold alert followed by an explicit human handoff.
                # Send ONE upgrade message and update the existing row in place;
                # never create a duplicate pending escalation.
                logger.info(
                    f"P4.2 ALERT UPGRADE: Lead {lead.id} escalation upgraded to "
                    f"severity {new_severity} (reason: {reason})."
                )
                recipient = _resolve_alert_recipient(db, lead)
                if recipient:
                    upgrade_body = (
                        f"⏫ *Hot Lead Alert — UPGRADED*\n\n"
                        f"*{lead.name or 'Unknown'}* now requires priority attention.\n\n"
                        f"*Updated Reason:* {reason}\n"
                        f"*Next Action:* Please contact immediately.\n\n"
                        f"View Lead: http://localhost:3000/crm?lead_id={lead.id}"
                    )
                    await _send_alert_whatsapp(upgrade_body, recipient, lead, reason)
                existing_log.reason = reason
                existing_log.severity = new_severity
                db.commit()
                return

            # 2. RESOLVE AGENT VIA DATABASE (never fall back to lead.phone)
            recipient = _resolve_alert_recipient(db, lead)
            if not recipient:
                fail_label = (lead.assigned_agent or "Unassigned")
                logger.error(
                    f"CRITICAL: Hot lead {lead.id} has no agent/manager phone. "
                    f"Refusing to notify lead phone. assigned_agent={lead.assigned_agent!r}"
                )
                if settings.ADMIN_EMAIL:
                    send_fallback_email(
                        settings.ADMIN_EMAIL,
                        "Admin",
                        lead,
                        f"{reason} | No agent/manager available for WhatsApp dispatch.",
                    )
                _record_failed_notification(db, lead, fail_label, reason)
                return

            agent_name = recipient["name"]

            # 3. FORMAT THE MESSAGE
            dashboard_link = f"http://localhost:3000/crm?lead_id={lead.id}"
            message_body = (
                f"🚨 *Hot Lead Alert*\n\n"
                f"*{lead.name or 'Unknown'}* is looking to {lead.intent or 'explore'} a "
                f"{lead.property_type or 'property'} in {lead.location or 'Pune'} "
                f"with a budget of {lead.budget or 'TBD'}.\n\n"
                f"*Reason:* {reason}\n"
                f"*Next Action:* Please contact within 10 minutes.\n\n"
                f"View Lead: {dashboard_link}"
            )

            # 4. DISPATCH VIA TWILIO
            delivery_status, twilio_sid = await _send_alert_whatsapp(message_body, recipient, lead, reason)

            # 5. CREATE AUDIT LOG (10-minute escalation timer)
            escalation_deadline = datetime.now(timezone.utc) + timedelta(minutes=10)
            new_log = NotificationLog(
                client_id=lead.client_id,
                lead_id=lead.id,
                assigned_agent=agent_name,
                status=delivery_status,
                escalate_at=escalation_deadline,
                twilio_message_sid=twilio_sid,
                reason=reason,
                severity=new_severity,
            )
            db.add(new_log)
            db.commit()

        except Exception as e:
            logger.error(f"Notification Engine crashed: {e}")
