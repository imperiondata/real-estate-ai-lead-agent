"""Calendar REST for n8n / ops (automations closeout BA-5).

Availability is labeled with ``provider`` (never a silent always-true).
Confirm updates the lead then routes through AE ``schedule_visit`` so
``site_visit.scheduled`` + DLQ stay on the EE spine.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import get_client_by_api_key
from config import settings
from database import get_db
from models import Client, Lead

logger = logging.getLogger("calendar_api")

router = APIRouter(prefix="/api/v1/calendar", tags=["calendar"])


class ConfirmBody(BaseModel):
    lead_id: int
    visit_date: str = Field(..., description="ISO-8601 visit datetime")


def _google_configured() -> bool:
    return bool(
        getattr(settings, "GOOGLE_CALENDAR_ID", "")
        and getattr(settings, "GOOGLE_CALENDAR_CREDENTIALS_JSON", "")
    )


def _heuristic_slots(date: str, duration_min: int) -> list[dict]:
    """Offline stub slots (morning/afternoon) when Google is not configured."""
    base = date[:10] if date else datetime.now(timezone.utc).date().isoformat()
    return [
        {"start": f"{base}T10:00:00", "end": f"{base}T{10 + duration_min // 60:02d}:{duration_min % 60:02d}:00"},
        {"start": f"{base}T14:00:00", "end": f"{base}T{14 + duration_min // 60:02d}:{(duration_min % 60):02d}:00"},
    ]


@router.get("/availability")
async def check_availability(
    date: str = Query(..., description="YYYY-MM-DD or ISO datetime"),
    duration_min: int = Query(60, ge=15, le=240),
    current_client: Client = Depends(get_client_by_api_key),
):
    """Return free slots. Always includes ``provider`` (google_calendar | stub)."""
    _ = current_client  # tenant auth only; freebusy is calendar-global for SA MVP
    if _google_configured():
        try:
            slots = _google_freebusy(date, duration_min)
            return {
                "status": "success",
                "provider": "google_calendar",
                "date": date,
                "duration_min": duration_min,
                "available": len(slots) > 0,
                "slots": slots,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("Google freebusy failed; falling back to stub: %s", exc)

    slots = _heuristic_slots(date, duration_min)
    return {
        "status": "success",
        "provider": "stub",
        "date": date,
        "duration_min": duration_min,
        "available": True,
        "slots": slots,
        "note": "stub_heuristic_slots_google_not_configured_or_failed",
    }


def _google_freebusy(date: str, duration_min: int) -> list[dict]:  # pragma: no cover - live API
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        settings.GOOGLE_CALENDAR_CREDENTIALS_JSON,
        scopes=["https://www.googleapis.com/auth/calendar.readonly"],
    )
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    day = date[:10]
    tz = getattr(settings, "GOOGLE_CALENDAR_TIMEZONE", "Asia/Kolkata")
    # Query full day UTC window (coarse); map busy blocks to free gaps heuristically
    time_min = f"{day}T00:00:00Z"
    time_max = f"{day}T23:59:59Z"
    body = {
        "timeMin": time_min,
        "timeMax": time_max,
        "timeZone": tz,
        "items": [{"id": settings.GOOGLE_CALENDAR_ID}],
    }
    fb = service.freebusy().query(body=body).execute()
    cal = (fb.get("calendars") or {}).get(settings.GOOGLE_CALENDAR_ID) or {}
    busy = cal.get("busy") or []
    # If no busy blocks, offer standard slots; else return empty free list + busy for n8n
    if not busy:
        return _heuristic_slots(day, duration_min)
    return []


@router.post("/confirm")
async def confirm_slot(
    body: ConfirmBody,
    current_client: Client = Depends(get_client_by_api_key),
    db: Session = Depends(get_db),
):
    """n8n confirms a negotiated slot: update lead + AE schedule_visit."""
    lead = (
        db.query(Lead)
        .filter(Lead.id == body.lead_id, Lead.client_id == current_client.id)
        .first()
    )
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead.visit_date = body.visit_date
    if lead.funnel_stage not in ("Appointment Scheduled", "Closed Won", "Lost"):
        lead.funnel_stage = "Appointment Scheduled"
    db.commit()
    db.refresh(lead)

    from app.automation_engine.engine import submit as ae_submit
    from app.automation_engine.templates.visit_booking import build_visit_action

    action = build_visit_action(
        tenant_id=f"Client_{current_client.id}",
        lead_id=lead.id,
        visit_date=body.visit_date,
        lead_name=lead.name or "",
        lead_phone=lead.phone or "",
        property_type=lead.property_type or "",
    )
    # Ensure EE payload has demographics for site_visit.scheduled merge
    action["parameters"] = {
        **(action.get("parameters") or {}),
        "lead_id": lead.id,
        "name": lead.name or "",
        "phone": lead.phone or "",
        "location": lead.location or "",
        "visit_date": body.visit_date,
    }
    result = await ae_submit(action)
    return {
        "status": "success" if result.get("status") == "success" else result.get("status", "error"),
        "lead_id": lead.id,
        "visit_date": body.visit_date,
        "ee_result": result,
    }
