import asyncio
import logging

from sqlalchemy.orm import Session
from twilio.rest import Client

from config import settings
from crm_sync import _push_to_hubspot
from database import SessionLocal
from models import DLQEvent, EventLog, Message, Session as SessionModel

logging.basicConfig(level=logging.INFO, format='%(asctime)s - DLQ Replay - %(levelname)s - %(message)s')
logger = logging.getLogger("dlq_replay")

async def process_hubspot_crm(payload: dict) -> bool:
    try:
        await _push_to_hubspot(payload)
        return True
    except Exception as e:
        logger.error(f"HubSpot CRM Replay Failed: {e}")
        return False

def process_twilio_outbound(payload: dict) -> bool:
    if not settings.TWILIO_ACCOUNT_SID:
        logger.warning("Twilio credentials missing, cannot replay.")
        return False
    
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        client.messages.create(
            from_=settings.TWILIO_PHONE_NUMBER,
            body=payload.get("body"),
            to=payload.get("to")
        )
        return True
    except Exception as e:
        logger.error(f"Twilio Outbound Replay Failed: {e}")
        return False

def process_ml_followup(payload: dict, db: Session) -> bool:
    try:
        # Import dynamically to avoid circular issues
        from follow_up import generate_followup_payload

        session_id = payload.get("session_id")
        if not session_id:
            logger.error("ML Followup Replay refused: missing session_id. Leaving pending.")
            return False

        # Resolve the tenant BEFORE any external send or DB write (SEC02 fail-closed).
        session_record = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if session_record is None or getattr(session_record, "client_id", None) is None:
            logger.error(
                "ML Followup Replay refused: no session row for session_id=%s. "
                "No send, no write. Leaving pending.", session_id
            )
            return False
        client_id = session_record.client_id

        current_stage = payload.get("stage", "Day 0")
        lead_data = payload.get("lead_data", {})

        day_map = {"Day 0": 0, "Day 1": 1, "Day 3": 3, "Day 7": 7}
        current_day = day_map.get(current_stage, 0)

        # We mock assigned_agent here just to replay the message payload generation
        assigned_agent = {"assigned_agent": lead_data.get("assigned_agent", "ABC Properties Team")}

        generated = generate_followup_payload(
            lead_data=lead_data,
            assigned_agent=assigned_agent,
            session_id=session_id,
            current_day=current_day,
            inactivity=lead_data.get("inactive_lead", False)
        )

        payload_msg = generated.get("message")
        if not payload_msg:
            raise ValueError("Empty message generated.")

        if settings.TWILIO_ACCOUNT_SID:
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            sid_str = str(session_id)
            client.messages.create(
                from_=settings.TWILIO_PHONE_NUMBER,
                body=payload_msg,
                to=f"whatsapp:{sid_str}" if sid_str.startswith("+") else sid_str
            )

        # Log successful recovery with mandatory multi-tenant client_id mapping
        event = EventLog(
            session_id=session_id,
            client_id=client_id,
            event_type="tracking",
            action_type="follow_up_sent_from_dlq"
        )
        db.add(event)

        db.add(Message(
            session_id=session_id,
            client_id=client_id,
            role="assistant",
            content=f"[DLQ RECOVERY {current_stage.upper()}] {payload_msg}"
        ))
        db.commit()
        return True
    except Exception as e:
        logger.error(f"ML Followup Replay Failed: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return False

async def main():
    logger.info("Starting DLQ Replay Job...")
    db = SessionLocal()
    try:
        pending_ids = [
            row_id
            for (row_id,) in db.query(DLQEvent.id).filter(DLQEvent.status == "pending").all()
        ]
        if not pending_ids:
            logger.info("No pending events in DLQ.")
            return

        logger.info(f"Found {len(pending_ids)} pending events. Beginning replay...")
        success_count = 0

        for event_id in pending_ids:
            # Reload each row under lock; a missing row means another run holds
            # it or it is no longer pending — skip without sending.
            event = (
                db.query(DLQEvent)
                .filter(DLQEvent.id == event_id, DLQEvent.status == "pending")
                .with_for_update(skip_locked=True)
                .first()
            )
            if event is None:
                logger.info(f"Skipping Event ID: {event_id} (locked or no longer pending).")
                db.rollback()
                continue
            logger.info(f"Replaying Event ID: {event.id} | Target: {event.target_endpoint}")

            success = False

            if event.target_endpoint == "hubspot_crm":
                success = await process_hubspot_crm(event.payload)
            elif event.target_endpoint == "twilio_outbound":
                success = process_twilio_outbound(event.payload)
            elif event.target_endpoint == "ml_followup_scheduler":
                success = process_ml_followup(event.payload, db)
            else:
                logger.warning(f"Unknown target endpoint: {event.target_endpoint}")

            if success:
                event.status = "resolved"
                db.commit()
                logger.info(f"[PASS] Event {event.id} resolved.")
                success_count += 1
            else:
                db.rollback()
                logger.error(f"[FAIL] Event {event.id} failed again. Keeping as pending.")
                
        logger.info(f"DLQ Replay complete. {success_count}/{len(pending_ids)} events recovered successfully.")
    except Exception as e:
        logger.error(f"DLQ Replay Job crashed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(main())
