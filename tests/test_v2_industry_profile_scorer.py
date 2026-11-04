"""Proof that the v3 scorer reads the published Industry Profile.

No database. The scorer is exercised with in-memory ``Lead`` instances; the
threshold and override checks are pure. The published default is 82, warm is 45,
the full-qualify floor is 88, and the visit floor is 82.
"""

from __future__ import annotations

import inspect

import pytest

from app.agents.whatsapp_agent import score_lead
from app.industry.profile_guard import ProfileGuardError, validate_override_value
from app.industry.profile_loader import (
    HOT_PATH,
    WARM_PATH,
    classify_temperature,
    load_profile,
    resolve_threshold,
)
from models import Lead


def _profile() -> dict:
    return load_profile("real_estate", 1)


def _fully_qualified() -> Lead:
    return Lead(
        name="A",
        phone="+919999999999",
        budget="80L",
        location="Wakad",
        property_type="2BHK",
        visit_date="2026-08-01",
        whatsapp_opt_in=True,
        lead_temperature="hot",
    )


def _visit_only() -> Lead:
    return Lead(visit_date="2026-08-01", lead_temperature="hot")


def _partial() -> Lead:
    return Lead(
        name="B",
        phone="+919999999998",
        budget="80L",
        location="Wakad",
        property_type="2BHK",
        whatsapp_opt_in=True,
        lead_temperature="hot",
    )


def test_profile_key_version_and_defaults():
    profile = _profile()
    assert profile["key"] == "real_estate"
    assert profile["version"] == 1
    assert profile["scoring_rules"]["temperature"]["hot_min_probability"] == 82
    assert profile["scoring_rules"]["temperature"]["warm_min_probability"] == 45
    assert profile["scoring_rules"]["temperature"]["full_qualify_floor"] == 88
    assert profile["scoring_rules"]["temperature"]["field_floors"]["visit_date"] == 82
    assert resolve_threshold(profile, HOT_PATH) == 82
    assert resolve_threshold(profile, WARM_PATH) == 45


def test_classification_at_the_locked_thresholds():
    assert classify_temperature(80, 82, 45) == "warm"
    assert classify_temperature(81, 82, 45) == "warm"
    assert classify_temperature(82, 82, 45) == "hot"
    assert classify_temperature(44, 82, 45) == "cold"
    assert classify_temperature(45, 82, 45) == "warm"


def test_tenant_override_85_is_honored():
    profile = _profile()
    assert resolve_threshold(profile, HOT_PATH, 85) == 85
    assert classify_temperature(84, 85, 45) == "warm"
    assert classify_temperature(85, 85, 45) == "hot"


def test_tenant_override_69_and_91_are_rejected():
    profile = _profile()
    for value in (69, 91):
        with pytest.raises(ProfileGuardError):
            validate_override_value(profile, HOT_PATH, value)
        assert resolve_threshold(profile, HOT_PATH, value) == 82


def test_unknown_override_path_is_rejected():
    profile = _profile()
    with pytest.raises(ProfileGuardError):
        validate_override_value(profile, "scoring_rules.temperature.unknown", 82)


def test_score_lead_applies_profile_floors():
    qualified = score_lead(_fully_qualified())
    assert qualified["conversion_probability"] == 88
    assert qualified["lead_temperature"] == "hot"

    visit_only = score_lead(_visit_only())
    assert visit_only["conversion_probability"] == 82
    assert visit_only["lead_temperature"] == "hot"

    partial = score_lead(_partial())
    assert partial["conversion_probability"] == 72
    assert partial["lead_temperature"] == "warm"


def test_score_lead_honors_valid_override_and_ignores_invalid():
    lead = _visit_only()
    assert score_lead(lead)["lead_temperature"] == "hot"
    assert score_lead(lead, {HOT_PATH: 85})["lead_temperature"] == "warm"
    assert score_lead(lead, {"hot_min_probability": 82})["lead_temperature"] == "hot"

    rejected_low = score_lead(lead, {HOT_PATH: 69})
    assert rejected_low["conversion_probability"] == 82
    assert rejected_low["lead_temperature"] == "hot"

    rejected_high = score_lead(lead, {HOT_PATH: 91})
    assert rejected_high["conversion_probability"] == 82
    assert rejected_high["lead_temperature"] == "hot"


def test_score_lead_no_longer_contains_the_literal_70_threshold():
    source = inspect.getsource(score_lead)
    assert "70" not in source
