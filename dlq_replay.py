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

def _send_twilio(body: str, to: str) -> None:
    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    client.messages.create(
        from_=settings.TWILIO_PHONE_NUMBER,
        body=body,
        to=to,
    )

def _claim_followup(db: Session, event_id: int, worker_id: str | None) -> bool:
    claimed = db.query(DLQEvent).filter(
        DLQEvent.id == event_id,
        DLQEvent.status == "pending",
    ).update(
        {
            "status": "processing",
            "error_trace": f"claimed:{worker_id or 'unknown'}",
        },
        synchronize_session=False,
    )
    db.commit()
    return claimed == 1

def process_ml_followup(
    payload: dict,
    db: Session,
    event_client_id: int | None = None,
    event_id: int | None = None,
    worker_id: str | None = None,
    sender=None,
) -> bool:
    session_id = payload.get("session_id") if payload else None
    if not session_id:
        logger.error("DLQ Replay Failed Closed: Missing session_id in payload.")
        return False

    session_record = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session_record or session_record.client_id is None:
        logger.error("DLQ Replay Failed Closed: Session %s not found in database.", session_id)
        return False

    if event_client_id and session_record.client_id != event_client_id:
        logger.error(
            "DLQ Replay Failed Closed: Tenant mismatch. Event client_id=%s, Session client_id=%s",
            event_client_id,
            session_record.client_id,
        )
        return False

    client_id = session_record.client_id

    if event_id is not None:
        try:
            won = _claim_followup(db, event_id, worker_id)
        except Exception as e:
            logger.error("ML Followup Replay Failed: %s: %s", type(e).__name__, e)
            try:
                db.rollback()
            except Exception:
                pass
            return False
        if not won:
            logger.info("DLQ event %s not claimed by %s.", event_id, worker_id)
            return False

    try:
        from follow_up import generate_followup_payload

        current_stage = payload.get("stage", "Day 0")
        lead_data = payload.get("lead_data", {})
        day_map = {"Day 0": 0, "Day 1": 1, "Day 3": 3, "Day 7": 7}
        current_day = day_map.get(current_stage, 0)
        assigned_agent = {"assigned_agent": lead_data.get("assigned_agent", "ABC Properties Team")}

        generated = generate_followup_payload(
            lead_data=lead_data,
            assigned_agent=assigned_agent,
            session_id=session_id,
            current_day=current_day,
            inactivity=lead_data.get("inactive_lead", False),
        )
        payload_msg = generated.get("message")
        if not payload_msg:
            raise ValueError("Empty message generated.")

        to_addr = f"whatsapp:{session_id}" if str(session_id).startswith("+") else str(session_id)
        if sender is not None:
            sender(body=payload_msg, to=to_addr)
        elif settings.TWILIO_ACCOUNT_SID:
            _send_twilio(payload_msg, to_addr)

        db.add(EventLog(
            session_id=session_id,
            client_id=client_id,
            event_type="tracking",
            action_type="follow_up_sent_from_dlq",
        ))
        db.add(Message(
            session_id=session_id,
            client_id=client_id,
            role="assistant",
            content=f"[DLQ RECOVERY {current_stage.upper()}] {payload_msg}",
        ))
        if event_id is not None:
            row = db.query(DLQEvent).filter(DLQEvent.id == event_id).one()
            row.status = "resolved"
        db.commit()
        return True
    except Exception as e:
        logger.error("ML Followup Replay Failed: %s: %s", type(e).__name__, e)
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

            if event.target_endpoint == "ml_followup_scheduler":
                success = process_ml_followup(
                    event.payload,
                    db,
                    event_client_id=event.client_id,
                    event_id=event.id,
                    worker_id="replay-main",
                )
                if success:
                    logger.info(f"[PASS] Event {event.id} resolved.")
                    success_count += 1
                else:
                    logger.error(
                        f"[FAIL] Event {event.id} not resolved. Leaving claim state unchanged."
                    )
                continue

            success = False

            if event.target_endpoint == "hubspot_crm":
                success = await process_hubspot_crm(event.payload)
            elif event.target_endpoint == "twilio_outbound":
                success = process_twilio_outbound(event.payload)
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
