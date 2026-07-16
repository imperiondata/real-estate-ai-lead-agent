"""Deterministic lead field backfill when the LLM tool omits clear signals."""

from types import SimpleNamespace

import pytest

from agent import (
    backfill_missing_lead_fields,
    extract_budget_from_text,
    extract_intent_from_text,
    extract_location_from_text,
    extract_property_type_from_text,
)


def _empty_lead(**overrides):
    base = dict(
        name=None,
        phone=None,
        budget=None,
        location=None,
        property_type=None,
        intent=None,
        visit_date=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# --- location ---


def test_extract_location_baner():
    assert extract_location_from_text("hi i am aritro i want 2bhk in baner") == "Baner"


def test_extract_location_wakad_road_prefers_longer():
    assert extract_location_from_text("looking near wakad road") == "Wakad Road"


def test_extract_location_none():
    assert extract_location_from_text("budget is 90 lakhs") is None


# --- property type ---


def test_extract_property_2bhk():
    assert extract_property_type_from_text("i want 2bhk in baner") == "2BHK"
    assert extract_property_type_from_text("need a 3 BHK flat") == "3BHK"


def test_extract_property_villa():
    assert extract_property_type_from_text("looking for a villa") == "Villa"


# --- budget ---


def test_extract_budget_lakhs():
    b = extract_budget_from_text("budget is around 90 lakhs")
    assert b is not None
    assert "90" in b and "LAKH" in b.upper()


def test_extract_budget_none():
    assert extract_budget_from_text("i want to visit sunday") is None


# --- intent ---


def test_extract_intent_buy():
    assert extract_intent_from_text("i want to buy a flat") == "Buy"


def test_extract_intent_rent():
    assert extract_intent_from_text("looking for rent in baner") == "Rent"


def test_extract_intent_weak_looking_no_match():
    assert extract_intent_from_text("i am looking around") is None


# --- backfill pipeline ---


def test_backfill_first_message_location_and_type():
    lead = _empty_lead()
    filled = backfill_missing_lead_fields(
        lead, "hi i am aritro i want 2bhk in baner"
    )
    assert "location" in filled
    assert "property_type" in filled
    assert lead.location == "Baner"
    assert lead.property_type == "2BHK"


def test_backfill_does_not_overwrite():
    lead = _empty_lead(location="Kharadi", property_type="3BHK", budget="50LAKHS")
    filled = backfill_missing_lead_fields(
        lead, "actually 2bhk in baner budget 90 lakhs"
    )
    assert filled == []
    assert lead.location == "Kharadi"
    assert lead.property_type == "3BHK"
    assert lead.budget == "50LAKHS"


def test_backfill_budget_and_intent():
    lead = _empty_lead()
    filled = backfill_missing_lead_fields(
        lead, "budget is around 90 lakhs and i want to buy"
    )
    assert "budget" in filled
    assert "intent" in filled
    assert lead.intent == "Buy"
    assert lead.budget is not None


def test_backfill_empty_message():
    lead = _empty_lead()
    assert backfill_missing_lead_fields(lead, "") == []
    assert backfill_missing_lead_fields(None, "baner") == []
