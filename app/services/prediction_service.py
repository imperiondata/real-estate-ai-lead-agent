"""IREIOS 3.0 — Phase 8: Prediction APIs + Marketing / CS / Competitor (Tasks 8.1–8.5).

Deterministic, offline-safe analytics & prediction helpers built on top of the
lead scores produced by `whatsapp_agent.score_lead` / `sales_agent`:

  * 8.1 `predict_conversion` / `predict_closure_days` — conversion probability
        and expected days-to-close from a lead's stored scores.
  * 8.2 `segment_leads` — bucket a client's leads into hot/warm/cold for
        marketing campaigns.
  * 8.3 `marketing_campaign_suggestion` — recommend a channel/message per segment.
  * 8.4 `detect_at_risk` — customer-success: leads gone cold / inactive.
  * 8.5 `competitor_signals` — configured competitor keyword monitor (no external
        network call; returns the configured watch-list and any matches in lead
        text when supplied).

All functions are pure/DB reads and never raise on missing data.

See plans/IREIOS_3.0_STEP_BY_STEP_EXPANSION.md (Phase 8) and
plans/IREIOS_3.0_EXPANSION_CHANGELOG.md.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from config import settings
from models import Lead

logger = logging.getLogger("prediction_service")


def predict_conversion(lead: Lead) -> dict:
    """Return conversion prediction derived from stored lead scores."""
    prob = lead.conversion_probability or 0
    temp = (lead.lead_temperature or "cold").lower()
    expected_days = max(1, round((100 - prob) / 8)) if prob < 100 else 1
    return {
        "lead_id": lead.id,
        "conversion_probability": prob,
        "temperature": temp,
        "expected_closure_days": expected_days,
        "confidence": "high" if prob >= 70 else ("medium" if prob >= 45 else "low"),
    }


def predict_closure_days(lead: Lead) -> int:
    prob = lead.conversion_probability or 0
    return max(1, round((100 - prob) / 8)) if prob < 100 else 1


def segment_leads(db: Session, client_id: int) -> dict:
    """Bucket a client's open leads into hot/warm/cold by temperature."""
    leads = (
        db.query(Lead)
        .filter(Lead.client_id == client_id, Lead.conversion_status == "open")
        .all()
    )
    buckets = {"hot": [], "warm": [], "cold": []}
    for l in leads:
        temp = (l.lead_temperature or "cold").lower()
        if temp not in buckets:
            temp = "cold"
        buckets[temp].append(l.id)
    return {
        "total_open": len(leads),
        "hot": buckets["hot"],
        "warm": buckets["warm"],
        "cold": buckets["cold"],
        "counts": {k: len(v) for k, v in buckets.items()},
    }


_CHANNEL_BY_SEGMENT = {
    "hot": "WhatsApp call + site-visit invite (human agent)",
    "warm": "WhatsApp brochure + retargeting ad",
    "cold": "Nurture sequence + email digest",
}


def marketing_campaign_suggestion(segment: str) -> dict:
    segment = (segment or "cold").lower()
    if segment not in _CHANNEL_BY_SEGMENT:
        segment = "cold"
    return {
        "segment": segment,
        "recommended_channel": _CHANNEL_BY_SEGMENT[segment],
        "message_hint": (
            "Limited inventory — book a slot" if segment == "hot"
            else "New listings matching your criteria" if segment == "warm"
            else "Still searching? Here's what's new this week"
        ),
    }


def detect_at_risk(db: Session, client_id: int, inactivity_days: int = 7) -> list:
    """CS: open leads that are cold or inactive beyond `inactivity_days`."""
    cutoff = datetime.now(timezone.utc)
    leads = (
        db.query(Lead)
        .filter(Lead.client_id == client_id, Lead.conversion_status == "open")
        .all()
    )
    at_risk = []
    for l in leads:
        temp = (l.lead_temperature or "cold").lower()
        stale = False
        if l.updated_at:
            try:
                age = (cutoff - l.updated_at).days
                stale = age >= inactivity_days
            except Exception:
                stale = False
        if temp == "cold" or stale:
            at_risk.append({"lead_id": l.id, "temperature": temp, "stale": stale})
    return at_risk


def competitor_signals(lead_text: Optional[str] = None) -> dict:
    """8.5: return the configured competitor watch-list and any matches.

    No external network call — uses the comma-separated `COMPETITOR_KEYWORDS`
    setting (empty by default). When `lead_text` is supplied, flags matches.
    """
    raw = getattr(settings, "COMPETITOR_KEYWORDS", "") or ""
    keywords = [k.strip().lower() for k in raw.split(",") if k.strip()] if raw else []
    matches = []
    if lead_text and keywords:
        low = (lead_text or "").lower()
        matches = [k for k in keywords if k in low]
    return {
        "monitored": keywords,
        "matches": matches,
        "alert": bool(matches),
    }
