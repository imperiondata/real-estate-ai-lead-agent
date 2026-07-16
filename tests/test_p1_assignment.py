"""P1 assignment — sticky claim, workload, ensure helper, matching polish."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.intelligence.agent_matcher import (
    apply_workload_on_assignment,
    ensure_lead_assignment,
    hot_threshold_notification_reason,
    location_match_score,
    resolve_followup_agent_label,
    specialities_match,
)


def test_hot_threshold_reason_not_explicit_human():
    reason = hot_threshold_notification_reason(84)
    assert "HOT threshold" in reason
    assert "Explicit human" not in reason
    assert "84" in reason


def test_apply_workload_same_agent_no_op():
    db = MagicMock()
    apply_workload_on_assignment(db, 1, "Alice", "Alice")
    db.query.assert_not_called()


def test_apply_workload_no_new_name_no_op():
    db = MagicMock()
    apply_workload_on_assignment(db, 1, "Alice", None)
    db.query.assert_not_called()


def test_apply_workload_reassignment_increments_and_decrements():
    new_agent = SimpleNamespace(name="Bob", active_leads=2)
    old_agent = SimpleNamespace(name="Alice", active_leads=5)

    def query_side_effect(model):
        q = MagicMock()
        chain = q.filter.return_value
        def first():
            # last filter kwargs inspected via call order: first query is new, second is old
            return None
        chain.first = first
        return q

    db = MagicMock()
    # Two sequential .query().filter(...).first() calls
    filter_mock = MagicMock()
    db.query.return_value.filter.return_value.first.side_effect = [new_agent, old_agent]

    apply_workload_on_assignment(db, 1, "Alice", "Bob")

    assert new_agent.active_leads == 3
    assert old_agent.active_leads == 4


def test_apply_workload_floor_at_zero():
    new_agent = SimpleNamespace(name="Bob", active_leads=0)
    old_agent = SimpleNamespace(name="Alice", active_leads=0)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.side_effect = [new_agent, old_agent]

    apply_workload_on_assignment(db, 1, "Alice", "Bob")
    assert new_agent.active_leads == 1
    assert old_agent.active_leads == 0


def test_ensure_sticky_when_claimed():
    lead = SimpleNamespace(
        conversion_status="claimed",
        assigned_agent="Alice",
        location="Baner",
    )
    db = MagicMock()
    with patch("app.intelligence.agent_matcher.match_best_agent") as match:
        result = ensure_lead_assignment(db, lead, 1, "want 2bhk", force=False)
        match.assert_not_called()
    assert result == "Alice"
    assert lead.assigned_agent == "Alice"


def test_ensure_claimed_force_rematches():
    lead = SimpleNamespace(
        conversion_status="claimed",
        assigned_agent="Alice",
        location="Baner",
    )
    db = MagicMock()
    with patch(
        "app.intelligence.agent_matcher.match_best_agent",
        return_value={"assigned_agent": "Bob", "match_score": 10},
    ):
        with patch("app.intelligence.agent_matcher.apply_workload_on_assignment") as wl:
            result = ensure_lead_assignment(db, lead, 1, "query", force=True)
            wl.assert_called_once()
    assert result == "Bob"
    assert lead.assigned_agent == "Bob"


def test_ensure_open_sets_agent_and_workload():
    lead = SimpleNamespace(
        conversion_status="open",
        assigned_agent=None,
        location="Baner",
    )
    db = MagicMock()
    with patch(
        "app.intelligence.agent_matcher.match_best_agent",
        return_value={"assigned_agent": "Carol", "match_score": 50},
    ):
        with patch("app.intelligence.agent_matcher.apply_workload_on_assignment") as wl:
            result = ensure_lead_assignment(db, lead, 1, "2bhk baner", force=False)
            wl.assert_called_once_with(db, 1, None, "Carol")
    assert result == "Carol"
    assert lead.assigned_agent == "Carol"


def test_ensure_same_agent_no_workload_bump():
    lead = SimpleNamespace(
        conversion_status="open",
        assigned_agent="Carol",
        location="Baner",
    )
    db = MagicMock()
    with patch(
        "app.intelligence.agent_matcher.match_best_agent",
        return_value={"assigned_agent": "Carol", "match_score": 50},
    ):
        with patch("app.intelligence.agent_matcher.apply_workload_on_assignment") as wl:
            result = ensure_lead_assignment(db, lead, 1, "more chat", force=False)
            wl.assert_not_called()
    assert result == "Carol"


def test_ensure_none_lead():
    assert ensure_lead_assignment(MagicMock(), None, 1, "x") is None


# --- P1.6 speciality ---


def test_specialities_match_investor_investment():
    assert specialities_match("investor", "investment") is True
    assert specialities_match("investor", "investor") is True
    assert specialities_match("tenant", "rental") is True
    assert specialities_match("buyer", "mid_range") is True
    assert specialities_match("luxury", "luxury") is True
    assert specialities_match("investor", "rental") is False
    assert specialities_match("buyer", None) is False


# --- P1.7 location ---


def test_location_match_exact():
    assert location_match_score("Baner", "Baner, Wakad") == 40


def test_location_match_substring():
    assert location_match_score("wakad west", "Wakad") == 25
    assert location_match_score("Baner", "baner east") == 25


def test_location_match_none():
    assert location_match_score(None, "Baner") == 0
    assert location_match_score("Baner", "Hinjewadi") == 0


# --- P1.9 follow-up agent label ---


def test_resolve_followup_agent_label_prefers_assignee():
    lead = SimpleNamespace(assigned_agent="Alice")
    client = SimpleNamespace(company_name="Acme Realty")
    assert resolve_followup_agent_label(lead, client) == "Alice"


def test_resolve_followup_agent_label_company_fallback():
    lead = SimpleNamespace(assigned_agent=None)
    client = SimpleNamespace(company_name="Acme Realty")
    assert resolve_followup_agent_label(lead, client) == "Acme Realty"


def test_resolve_followup_agent_label_no_demo_agency():
    lead = SimpleNamespace(assigned_agent="ABC Properties Team")
    client = SimpleNamespace(company_name="Real Co")
    # treat demo string as invalid → company
    assert resolve_followup_agent_label(lead, client) == "Real Co"


def test_resolve_followup_agent_label_none():
    lead = SimpleNamespace(assigned_agent=None)
    assert resolve_followup_agent_label(lead, None) is None
