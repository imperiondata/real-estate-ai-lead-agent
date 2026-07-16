"""P6 — structural cleanup (min match score, AB-timing, temperature casing)."""

from types import SimpleNamespace

import pytest

from app.intelligence.agent_matcher import ensure_lead_assignment
from app.intelligence import agent_matcher
from follow_up import next_followup_stage
from config import settings
from main import serialize_lead


# --- P6.5: temperature casing on API serialization ---


def test_serialize_lead_title_cases_temperature():
    class Col:
        def __init__(self, name):
            self.name = name

    class FakeLead:
        __table__ = SimpleNamespace(columns=[Col("lead_temperature"), Col("name")])
        lead_temperature = "hot"
        name = "X"

    out = serialize_lead(FakeLead())
    assert out["lead_temperature"] == "Hot"


def test_serialize_lead_empty_temperature_passthrough():
    class Col:
        def __init__(self, name):
            self.name = name

    class FakeLead:
        __table__ = SimpleNamespace(columns=[Col("lead_temperature")])
        lead_temperature = ""

    assert serialize_lead(FakeLead())["lead_temperature"] == ""


# --- P6.4: AB / strategy-B day gap derivation ---


def test_next_stage_day0_to_day1_gap():
    followups = [{"day": 0}, {"day": 1}, {"day": 3}, {"day": 7}]
    stage, gap = next_followup_stage(followups, "Day 0")
    assert stage == "Day 1"
    assert gap == 1


def test_next_stage_day3_to_day7_gap():
    followups = [{"day": 0}, {"day": 1}, {"day": 3}, {"day": 7}]
    stage, gap = next_followup_stage(followups, "Day 3")
    assert stage == "Day 7"
    assert gap == 4


def test_next_stage_terminal_returns_none():
    followups = [{"day": 0}, {"day": 1}, {"day": 3}, {"day": 7}]
    stage, gap = next_followup_stage(followups, "Day 7")
    assert stage is None
    assert gap == 0


def test_next_stage_short_sequence_stops():
    followups = [{"day": 0}]
    stage, gap = next_followup_stage(followups, "Day 0")
    assert stage is None
    assert gap == 0


# --- P6.3: minimum match score threshold ---


class _FakeAgent:
    def __init__(self, name, conversion_rate=30, lead_type="buyer", speciality="buyer",
                 deal_size="low", locations="baner", response_speed_score=50):
        self.name = name
        self.conversion_rate = conversion_rate
        self.lead_type = lead_type
        self.speciality = speciality
        self.deal_size = deal_size
        self.locations = locations
        self.response_speed_score = response_speed_score
        self.active_leads = 0
        self.phone = "+910000000000"
        self.email = f"{name.lower()}@example.com"


class _FakeLead:
    def __init__(self):
        self.location = "baner"
        self.assigned_agent = None
        self.conversion_status = "open"
        self.id = 99


class _FakeDB:
    """Minimal in-memory stand-in for the matcher's queries."""
    def __init__(self, agents):
        self._agents = agents

    def query(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self._agents

    def first(self):
        return self._agents[0] if self._agents else None

    def commit(self):
        pass


def test_min_match_score_blocks_poor_assignment():
    saved = settings.MIN_MATCH_SCORE
    settings.MIN_MATCH_SCORE = 10_000  # impossibly high → always below threshold
    try:
        db = _FakeDB([_FakeAgent("Raj")])
        lead = _FakeLead()
        result = ensure_lead_assignment(db, lead, 1, "2bhk in baner", force=False)
        # Below threshold → lead stays unassigned.
        assert result is None or result == lead.assigned_agent
        assert lead.assigned_agent is None
    finally:
        settings.MIN_MATCH_SCORE = saved


def test_min_match_score_zero_allows_assignment():
    saved = settings.MIN_MATCH_SCORE
    settings.MIN_MATCH_SCORE = 0
    try:
        db = _FakeDB([_FakeAgent("Raj")])
        lead = _FakeLead()
        result = ensure_lead_assignment(db, lead, 1, "2bhk in baner", force=False)
        assert result == "Raj"
        assert lead.assigned_agent == "Raj"
    finally:
        settings.MIN_MATCH_SCORE = saved
