"""IREIOS 3.0 — Phase 3.3 / D: Calendar Executor (Google Calendar + stub fallback).

Schedules a site visit (Google Calendar API or synthetic stub).

**Bus ownership (PR #10):** this executor does **not** call ``event_bus.publish``.
It returns a result dict only. The Execution Engine success map
(``register_event("schedule_visit", "site_visit.scheduled")`` in
``app/execution_engine/registry.py``) publishes ``site_visit.scheduled`` after
a successful dispatch — AE → EE → Event. Do not add a second publish here
(would double-fire n8n / KG).

When ``GOOGLE_CALENDAR_CREDENTIALS_JSON`` (service-account key file) and
``GOOGLE_CALENDAR_ID`` are configured, a real Google Calendar event is created
and its event id is returned as ``visit_id``. When they are NOT configured (or
the API call fails) it falls back to a synthetic ``visit_id`` so the AE contract
(``action_type="schedule_visit"`` → ``{"status":"success","visit_id":...}``) is
unchanged and the rest of the pipeline keeps working (config-later safe).
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

from app.execution_engine.base_executor import BaseExecutor
from config import settings

logger = logging.getLogger("executor.calendar")

_SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _google_configured() -> bool:
    return bool(
        getattr(settings, "GOOGLE_CALENDAR_ID", "")
        and getattr(settings, "GOOGLE_CALENDAR_CREDENTIALS_JSON", "")
    )


_DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _calendar_tz():
    name = getattr(settings, "GOOGLE_CALENDAR_TIMEZONE", None) or "Asia/Kolkata"
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name), name
    except Exception:  # noqa: BLE001
        return timezone.utc, "UTC"


def _parse_start(visit_date) -> datetime:
    """Best-effort parse of visit_date into a timezone-aware datetime.

    Wall-clock times without offset are interpreted in GOOGLE_CALENDAR_TIMEZONE
    (default Asia/Kolkata), not UTC — matches how sales agents phrase visits.
    """
    tz, _tz_name = _calendar_tz()
    if visit_date:
        # 1. Try ISO-8601
        try:
            raw = str(visit_date).replace("Z", "+00:00")
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=tz)
            return dt
        except (ValueError, TypeError):
            pass

        # 2. Try natural language: "Saturday 10:00 AM", "friday 2:30pm", etc.
        text = str(visit_date).strip()
        match = re.match(
            r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday)'
            r'\s+(\d{1,2}:\d{2})\s*(am|pm)?',
            text, re.IGNORECASE,
        )
        if match:
            day_name = match.group(1).lower()
            time_str = match.group(2)
            ampm = (match.group(3) or "").upper()

            parts = time_str.split(":")
            hour, minute = int(parts[0]), int(parts[1])
            if ampm == "PM" and hour != 12:
                hour += 12
            elif ampm == "AM" and hour == 12:
                hour = 0

            now = datetime.now(tz)
            target_weekday = _DAY_NAMES.index(day_name)
            days_ahead = target_weekday - now.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            target = (now + timedelta(days=days_ahead)).replace(
                hour=hour, minute=minute, second=0, microsecond=0,
            )
            return target

    # 3. Fallback: tomorrow at current local wall-clock
    return datetime.now(tz) + timedelta(days=1)


class CalendarExecutor(BaseExecutor):
    """Creates a Google Calendar event (or a stub visit) for a site visit.

    ``parameters``:
        - ``lead_id`` (optional)
        - ``visit_date`` (ISO string, optional)
        - ``name`` / ``phone`` / ``location`` (optional, for the event body)
    """

    action_type = "schedule_visit"

    def _create_google_event(self, params: dict, entity_id) -> dict:  # pragma: no cover - needs live API
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds = service_account.Credentials.from_service_account_file(
            settings.GOOGLE_CALENDAR_CREDENTIALS_JSON, scopes=_SCOPES
        )
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        start = _parse_start(params.get("visit_date"))
        end = start + timedelta(hours=1)
        _tzinfo, tz_name = _calendar_tz()
        # Naive local wall-clock + timeZone avoids UTC offset vs zone mismatch.
        start_local = start.astimezone(_tzinfo).replace(tzinfo=None) if start.tzinfo else start
        end_local = end.astimezone(_tzinfo).replace(tzinfo=None) if end.tzinfo else end
        summary = f"Site visit — {params.get('name') or entity_id}"
        description = (
            f"Lead: {params.get('name') or ''}\nPhone: {params.get('phone') or ''}\n"
            f"Location: {params.get('location') or ''}"
        )
        body = {
            "summary": summary,
            "description": description,
            "location": params.get("location", ""),
            "start": {"dateTime": start_local.isoformat(), "timeZone": tz_name},
            "end": {"dateTime": end_local.isoformat(), "timeZone": tz_name},
        }
        event = service.events().insert(
            calendarId=settings.GOOGLE_CALENDAR_ID, body=body
        ).execute()
        return {
            "visit_id": event.get("id"),
            "visit_date": start.isoformat(),
            "html_link": event.get("htmlLink"),
            "provider": "google_calendar",
        }

    async def execute(self, action_request: dict) -> dict:
        params = action_request.get("parameters", {}) or {}
        entity_id = action_request.get("entity_id")

        if _google_configured():
            try:  # pragma: no cover - requires live Google API
                result = self._create_google_event(params, entity_id)
                logger.info("Calendar: created Google event %s for entity=%s",
                            result.get("visit_id"), entity_id)
                return {"status": "success", "scheduled_at":
                        datetime.now(timezone.utc).isoformat(), **result}
            except Exception as exc:  # noqa: BLE001
                # Prod + configured: surface failure (no fake "booked" success).
                # Dev/test: stub so local demos keep working without a live portal.
                if getattr(settings, "IS_PRODUCTION", False):
                    logger.error("Google Calendar create failed in production: %s", exc)
                    return {
                        "status": "error",
                        "error": f"google_calendar_failed:{type(exc).__name__}",
                        "provider": "google_calendar",
                    }
                logger.warning("Google Calendar create failed; using stub: %s", exc)

        visit_id = f"visit_{uuid.uuid4().hex[:12]}"
        visit_date = params.get("visit_date")
        logger.info("Calendar(stub): scheduled visit %s for entity=%s visit_date=%s",
                    visit_id, entity_id, visit_date)
        return {
            "status": "success",
            "visit_id": visit_id,
            "visit_date": visit_date,
            "provider": "stub",
            "scheduled_at": datetime.now(timezone.utc).isoformat(),
        }
