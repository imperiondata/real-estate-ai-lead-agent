"""IREIOS 3.0 — Phase 4.1 Follow-up scheduler workflow.

Ports the state-machine follow-up logic from root ``follow_up.py`` into the
Execution-Engine pipeline. The ML payload generation, inactivity handling,
state transitions and quiet-hours logic are reused verbatim from ``follow_up``;
the only behavioural change is that outbound messages are dispatched through
``AutomationEngine.submit({action_type: "send_whatsapp", ...})`` instead of a
direct Twilio call. The Execution Engine owns retries/DLQ, so this module no
longer writes ``DLQEvent`` for dispatch failures directly (the AE/EE path does).

The legacy ``follow_up.check_and_send_followups`` is retained for the
``FOLLOWUP_ENGINE=legacy`` selector; this workflow is selected via ``v3`` (or
``shadow`` dry-run). See Plan Task 4.2/4.4.

Runtime: ``Event -> CEO -> Workflow -> Automation Engine -> Execution Engine -> Event``.
"""
from __future__ import annotations

import asyncio
import logging
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone

from app.automation_engine.engine import submit
from config import settings, tenant_id_ctx
from database import SessionLocal
from follow_up import (
    SCHEDULER_JOB_DURATION,
    apply_quiet_hours,
    compute_send_failure_backoff,
    generate_followup_payload,
    next_followup_stage,
    resolve_followup_agent_label,
)
from metrics import BACKGROUND_FAILURE_COUNT, SCHEDULER_JOB_FAILURES
from models import Client, EventLog, FollowUpState, Lead, Message, Session

logger = logging.getLogger("workflow.followup")

# Reuse the tenant context var if config exposes it; otherwise a local one.
try:  # pragma: no cover
    from config import tenant_id_ctx as _tenant_ctx  # type: ignore
except Exception:  # noqa: BLE001
    _tenant_ctx: ContextVar = tenant_id_ctx


def _build_action(session_id: str, client_id: int, to: str, body: str, source: str) -> dict:
    return {
        "action_type": "send_whatsapp",
        "tenant_id": f"Client_{client_id}",
        "entity_id": session_id,
        "parameters": {"phone": to, "message": body, "source": source},
    }


async def _dispatch_message(action: dict) -> bool:
    """Send via the Automation Engine. Returns True on success/accepted."""
    try:
        result = await submit(action)
        return result.get("status") in ("success", "pending_approval")
    except Exception as exc:  # noqa: BLE001
        logger.error("Follow-up AE dispatch failed: %s", exc)
        return False


def check_and_send_followups_v3() -> None:
    """State-machine follow-up sender that routes through the AE->EE pipeline.

    Synchronous entrypoint (APScheduler-compatible). Wraps the async dispatch in
    an event loop so the existing scheduler registration keeps working.
    """
    _JOB = "check_and_send_followups_v3"
    db = SessionLocal()
    try:
        with SCHEDULER_JOB_DURATION.labels(job_name=_JOB).time():
            now = datetime.now(timezone.utc)

            triggered_states = db.query(FollowUpState).filter(
                FollowUpState.follow_up_status == "active",
                FollowUpState.next_follow_up_at <= now,
            ).all()

            logger.info(f"FOLLOWUP_V3 | Triggers found: {len(triggered_states)}")

            for state in triggered_states:
                session_id = state.session_id
                _tenant_ctx.set(f"Client_{state.client_id}")

                session = db.query(Session).filter(Session.id == session_id).first()
                lead = db.query(Lead).filter(Lead.session_id == session_id).first()
                if not session:
                    state.follow_up_status = "stopped"
                    state.next_follow_up_at = None
                    db.commit()
                    logger.warning(
                        "Follow-up v3 stopped: session missing session_id=%s",
                        session_id,
                    )
                    continue

                clean_phone = None
                if lead and lead.phone:
                    clean_phone = lead.phone.strip()
                    if not clean_phone.startswith("+"):
                        clean_phone = f"+{clean_phone}"

                # Terminal-state guards (defense-in-depth).
                if lead and lead.whatsapp_opt_in is False:
                    state.follow_up_status = "stopped"
                    state.next_follow_up_at = None
                    db.commit()
                    continue
                if session.status == "closed" or (lead and lead.visit_date):
                    state.follow_up_status = "stopped"
                    db.commit()
                    continue

                current_stage = state.follow_up_stage
                hour_map = {"Day 0": 0, "Day 1": 24, "Day 3": 72, "Day 7": 168}
                current_day = hour_map.get(current_stage, 0)

                inactivity = False
                if state.last_user_reply_timestamp:
                    user_tz = state.last_user_reply_timestamp
                    if user_tz.tzinfo is None:
                        user_tz = user_tz.replace(tzinfo=timezone.utc)
                    delta = now - user_tz
                    if settings.FOLLOW_UP_TEST_MODE:
                        inactivity = delta.total_seconds() > 60
                    else:
                        inactivity = delta.days > 7
                if inactivity and state:
                    state.inactivity_score = (state.inactivity_score or 0) + 1
                    if lead:
                        lead.inactivity_penalty = state.inactivity_score * 10
                        if lead.conversion_probability and lead.conversion_probability > 10:
                            lead.conversion_probability -= 5
                        if getattr(lead, "conversion_probability", 0) < 55:
                            lead.lead_temperature = "cold"
                            lead.score = "Low"

                lead_data: dict = {}
                assigned_agent = None
                if lead:
                    lead_data = {
                        "name": lead.name,
                        "location": lead.location,
                        "budget": lead.budget,
                        "property_type": lead.property_type,
                        "conversion_probability": getattr(lead, "conversion_probability", 0) or 0,
                        "urgency_level": getattr(lead, "urgency_level", "low") or "low",
                        "engagement_score": getattr(lead, "engagement_score", 0) or 0,
                        "expected_closure_days": getattr(lead, "expected_closure_days", 0),
                        "budget_alignment_status": getattr(
                            lead, "budget_alignment_status", None
                        ) or "aligned",
                        "response_speed_score": 50,
                        "inactive_lead": inactivity,
                    }
                    client_row = db.query(Client).filter(Client.id == state.client_id).first()
                    agent_label = resolve_followup_agent_label(lead, client_row)
                    assigned_agent = {"assigned_agent": agent_label} if agent_label else None

                try:
                    if not settings.IS_PRODUCTION and settings.FOLLOW_UP_TEST_MODE and settings.FOLLOW_UP_DLQ_TEST:
                        raise Exception("QA_DLQ_TEST — intentional failure to verify DLQ pipeline")

                    if current_stage == "Day 7":
                        if not lead:
                            state.follow_up_status = "stopped"
                            state.next_follow_up_at = None
                            db.commit()
                            logger.warning(
                                "Day 7 v3 stopped: lead missing session_id=%s",
                                session_id,
                            )
                            continue
                        closure_msg = (
                            f"Hi {lead.name or 'there'}, we haven't heard back from you in a while. "
                            f"We'll pause our updates for now. Feel free to reach out anytime — "
                            f"we're happy to help with your property search. Take care! 🏡"
                        )
                        sent = _run_dispatch(db, state, lead, clean_phone, closure_msg, "day7_closure")
                        if not sent:
                            from follow_up import apply_quiet_hours
                            from datetime import timedelta
                            state.next_follow_up_at = apply_quiet_hours(now + timedelta(hours=24))
                            db.commit()
                            continue
                        state.follow_up_status = "stopped"
                        state.next_follow_up_at = None
                        session.status = "closed"
                        db.add(EventLog(
                            session_id=session_id, client_id=state.client_id,
                            event_type="tracking", action_type="Day 7 follow_up_sent",
                        ))
                        db.add(Message(session_id=session_id, client_id=state.client_id,
                                       role="assistant", content=f"[AUTO DAY7 CLOSURE] {closure_msg}"))
                        db.add(Message(session_id=session_id, client_id=state.client_id,
                                       role="assistant", content="[SESSION CLOSED DUE TO INACTIVITY]"))
                        db.commit()
                        continue

                    generated_payload = generate_followup_payload(
                        lead_data=lead_data, assigned_agent=assigned_agent,
                        session_id=session_id, current_day=current_day, inactivity=inactivity,
                    )
                    payload_msg = generated_payload.get("message")
                    if not payload_msg:
                        raise ValueError("ML Engine returned an empty message payload.")

                    sent = _run_dispatch(db, state, lead, clean_phone, payload_msg, f"followup_{current_stage}")
                    if not sent:
                        from follow_up import apply_quiet_hours
                        from datetime import timedelta
                        state.next_follow_up_at = apply_quiet_hours(now + timedelta(hours=24))
                        db.commit()
                        continue

                    if sent:
                        state.follow_up_sent_at = now
                        state.last_ai_reply_timestamp = now
                        state.send_retry_count = 0
                        session.follow_up_count = (session.follow_up_count or 0) + 1
                        if lead:
                            lead.followup_stage = current_stage
                        db.add(EventLog(
                            session_id=session_id, client_id=state.client_id,
                            event_type="tracking", action_type=f"{current_stage} follow_up_sent",
                        ))
                        db.add(Message(
                            session_id=session_id, client_id=state.client_id,
                            role="assistant", content=f"[AUTO {current_stage.upper()}] {payload_msg}",
                        ))
                        followups = generated_payload.get("followups") or generated_payload.get("sequence", [])

                        def _next_delay(prod_hours):
                            if settings.FOLLOW_UP_TEST_MODE:
                                return timedelta(minutes=1)
                            return timedelta(hours=prod_hours)

                        next_stage, gap_days = next_followup_stage(followups, current_stage)
                        if next_stage:
                            state.follow_up_stage = next_stage
                            state.next_follow_up_at = apply_quiet_hours(now + _next_delay(gap_days))
                        else:
                            state.follow_up_status = "stopped"
                            state.next_follow_up_at = None
                            session.status = "closed"
                            db.add(Message(
                                session_id=session_id, client_id=state.client_id,
                                role="assistant", content="[SESSION CLOSED DUE TO INACTIVITY]",
                            ))
                        db.commit()
                    else:
                        _backoff(db, state, now)

                except Exception as ml_err:
                    logger.error(f"ML Follow-up Engine failed for session {session_id}: {ml_err}")
                    BACKGROUND_FAILURE_COUNT.labels(component="scheduler").inc()
                    _backoff(db, state, now)
    except Exception as e:
        logger.error(f"Follow-up v3 scheduler main loop error: {e}")
        SCHEDULER_JOB_FAILURES.labels(job_name=_JOB).inc()
    finally:
        db.close()


def _run_dispatch(db, state, lead, clean_phone, body, source) -> bool:
    """Build + send the message via AE; persist audit message; commit DB.

    Returns True if FSM should advance. False = hold stage (e.g. no phone).
    """
    session_id = state.session_id
    if settings.TEST_MODE:
        logger.info(f"[TEST MODE] Follow-up v3 skipped send for {session_id}")
        db.add(Message(session_id=session_id, client_id=state.client_id,
                       role="assistant", content=f"[AUTO TEST] {body}"))
        db.commit()
        return True
    if not settings.TWILIO_ACCOUNT_SID:
        logger.info(f"Simulated follow-up v3 for {session_id}")
        db.add(Message(session_id=session_id, client_id=state.client_id,
                       role="assistant", content=f"[AUTO SIM] {body}"))
        db.commit()
        return True
    if not (lead and lead.phone and clean_phone):
        logger.warning("Follow-up v3 deferred (no phone) session=%s", session_id)
        return False
    to = f"whatsapp:{clean_phone}" if lead and lead.source == "whatsapp" else clean_phone
    action = _build_action(session_id, state.client_id, to, body, source)
    sent = asyncio.run(_dispatch_message(action))
    db.add(Message(session_id=session_id, client_id=state.client_id,
                   role="assistant", content=f"[AUTO {source.upper()}] {body}"))
    db.commit()
    return sent


def _backoff(db, state, now) -> None:
    """P4.3 backoff: advance next_follow_up_at (or stop) instead of per-tick retry.

    The dispatch failure is already recorded as a DLQ row by the Execution
    Engine, so this only reschedules (or stops) the state row.
    """
    try:
        retry_count = (state.send_retry_count or 0) + 1
        state.send_retry_count = retry_count
        backoff_delay, exhausted = compute_send_failure_backoff(
            retry_count, test_mode=settings.FOLLOW_UP_TEST_MODE,
        )
        if exhausted:
            state.follow_up_status = "stopped"
            state.next_follow_up_at = None
            logger.error(
                f"P4.3: follow-up v3 permanently failed for {state.session_id} "
                f"after {retry_count} attempts; stopping (DLQ written by EE)."
            )
        else:
            state.next_follow_up_at = apply_quiet_hours(now + backoff_delay)
            logger.warning(
                f"P4.3: follow-up v3 failed for {state.session_id}; "
                f"retry {retry_count} scheduled in {backoff_delay} (backoff)."
            )
        db.commit()
    except Exception as dlq_err:  # noqa: BLE001
        logger.error(f"Follow-up v3 backoff error for {state.session_id}: {dlq_err}")
