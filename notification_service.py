import logging
import os
import smtplib
from email.message import EmailMessage
from datetime import datetime, timezone, timedelta

from twilio.rest import Client

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
    ))
    db.commit()


async def trigger_hot_lead_notification(lead_id: int, reason: str = "High-intent behavior detected"):
    """
    Asynchronously fires a WhatsApp notification to the assigned agent.
    Guarantees idempotency (no duplicate spam).
    Never sends hot-lead ops alerts to the lead's own phone (P0.2/P0.3).
    """
    with SessionLocal() as db:
        try:
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if not lead:
                return

            # 1. IDEMPOTENCY CHECK
            existing_log = db.query(NotificationLog).filter(
                NotificationLog.lead_id == lead.id,
                NotificationLog.status.in_(["pending_ack", "acknowledged", "escalated_10m", "escalated_30m"])
            ).first()

            if existing_log:
                logger.info(f"Notification bypassed: Lead {lead.id} already has an active escalation state.")
                return

            # 2. RESOLVE AGENT VIA DATABASE (never fall back to lead.phone)
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

            recipient = resolve_hot_alert_recipient(target_agent, settings.ADMIN_EMAIL)
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

            agent_phone = recipient["phone"]
            agent_name = recipient["name"]
            agent_email = recipient["email"]

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
            delivery_status = "pending_ack"
            twilio_sid = None
            twilio_success = False

            if settings.TEST_MODE:
                logger.info(f"[TEST MODE] Simulated WhatsApp Alert to {agent_name} ({agent_phone})")
                twilio_success = True
            elif settings.TWILIO_ACCOUNT_SID:
                client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
                to_number = f"whatsapp:{agent_phone}" if not agent_phone.startswith("whatsapp:") else agent_phone

                base_url = settings.WEBHOOK_BASE_URL
                status_callback_url = f"{base_url}/api/v1/webhook/twilio-status" if base_url else None

                for attempt in range(3):
                    try:
                        message = client.messages.create(
                            from_=settings.TWILIO_PHONE_NUMBER,
                            body=message_body,
                            to=to_number,
                            status_callback=status_callback_url
                        )
                        twilio_sid = message.sid
                        delivery_status = "pending_ack"
                        twilio_success = True
                        logger.info(
                            f"WhatsApp Alert dispatched to {agent_name} | SID: {twilio_sid} | Attempt: {attempt + 1}")
                        break
                    except Exception as e:
                        logger.warning(f"WhatsApp Alert attempt {attempt + 1} failed: {e}")
                        import asyncio
                        await asyncio.sleep(1)

                if not twilio_success:
                    logger.error("All 3 Twilio attempts failed. Triggering Email Fallback.")
                    delivery_status = "failed"
                    send_fallback_email(agent_email, agent_name, lead, reason)

            # 5. CREATE AUDIT LOG (10-minute escalation timer)
            escalation_deadline = datetime.now(timezone.utc) + timedelta(minutes=10)
            new_log = NotificationLog(
                client_id=lead.client_id,
                lead_id=lead.id,
                assigned_agent=agent_name,
                status=delivery_status,
                escalate_at=escalation_deadline,
                twilio_message_sid=twilio_sid
            )
            db.add(new_log)
            db.commit()

        except Exception as e:
            logger.error(f"Notification Engine crashed: {e}")
