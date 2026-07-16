"""P4.1 — escalation recipient resolution (10m manager vs 30m director).
P4.2 — alert severity ranking / handoff upgrade over score alert.
P4.3 — follow-up dispatch-failure backoff.
"""

from datetime import timedelta
from types import SimpleNamespace

from notification_service import (
    pick_escalation_agent,
    classify_reason_severity,
    should_upgrade_alert,
    SEVERITY_HANDOFF,
    SEVERITY_SCORE_ALERT,
)
from follow_up import compute_send_failure_backoff


def _agent(name, is_manager=False, is_director=False):
    return SimpleNamespace(name=name, is_manager=is_manager, is_director=is_director)


# --- 10m tier: manager only ---


def test_10m_returns_manager():
    agents = [_agent("Rep"), _agent("Mgr", is_manager=True), _agent("Dir", is_manager=True, is_director=True)]
    chosen = pick_escalation_agent(agents, "10m")
    assert chosen is not None
    assert chosen.name == "Mgr"
    assert chosen.is_manager is True


def test_10m_ignores_director_when_manager_exists():
    agents = [_agent("Dir", is_manager=True, is_director=True), _agent("Mgr", is_manager=True)]
    # First eligible manager wins; director acting as manager is still a manager
    chosen = pick_escalation_agent(agents, "10m")
    assert chosen.is_manager is True


def test_10m_none_when_no_manager():
    agents = [_agent("Rep"), _agent("Dir", is_director=True)]
    assert pick_escalation_agent(agents, "10m") is None


# --- 30m tier: director preferred, manager fallback ---


def test_30m_prefers_director_over_manager():
    agents = [_agent("Mgr", is_manager=True), _agent("Dir", is_manager=True, is_director=True)]
    chosen = pick_escalation_agent(agents, "30m")
    assert chosen.name == "Dir"
    assert chosen.is_director is True


def test_30m_falls_back_to_manager_when_no_director():
    agents = [_agent("Rep"), _agent("Mgr", is_manager=True)]
    chosen = pick_escalation_agent(agents, "30m")
    assert chosen is not None
    assert chosen.name == "Mgr"
    assert chosen.is_director is False


def test_30m_none_when_no_manager_and_no_director():
    agents = [_agent("Rep")]
    assert pick_escalation_agent(agents, "30m") is None


def test_30m_director_without_manager_flag():
    """A director who is not also a manager must still be chosen for 30m."""
    agents = [_agent("Dir", is_director=True)]
    chosen = pick_escalation_agent(agents, "30m")
    assert chosen is not None
    assert chosen.name == "Dir"


# --- P4.2: severity ranking + upgrade ---


def test_handoff_reason_is_higher_severity_than_score():
    handoff = classify_reason_severity("Explicit human agent requested.")
    score = classify_reason_severity("Lead crossed HOT threshold (conversion_probability ≥ 82)")
    assert handoff == SEVERITY_HANDOFF
    assert score == SEVERITY_SCORE_ALERT
    assert handoff > score


def test_classify_handoff_variants():
    assert classify_reason_severity("customer requested an agent") == SEVERITY_HANDOFF
    assert classify_reason_severity("Human handoff triggered") == SEVERITY_HANDOFF
    assert classify_reason_severity("") == SEVERITY_SCORE_ALERT
    assert classify_reason_severity(None) == SEVERITY_SCORE_ALERT


def test_handoff_upgrades_open_score_alert():
    assert should_upgrade_alert("pending_ack", SEVERITY_SCORE_ALERT, SEVERITY_HANDOFF) is True


def test_score_does_not_upgrade_open_handoff():
    assert should_upgrade_alert("pending_ack", SEVERITY_HANDOFF, SEVERITY_SCORE_ALERT) is False


def test_same_severity_does_not_upgrade():
    assert should_upgrade_alert("pending_ack", SEVERITY_HANDOFF, SEVERITY_HANDOFF) is False


def test_no_upgrade_when_alert_terminal():
    for terminal in ("failed", "failed_alerted", "resolved"):
        assert should_upgrade_alert(terminal, SEVERITY_SCORE_ALERT, SEVERITY_HANDOFF) is False


def test_upgrade_treats_missing_severity_as_score():
    assert should_upgrade_alert("pending_ack", None, SEVERITY_HANDOFF) is True


# --- P4.3: dispatch-failure backoff ---


def test_backoff_is_exponential():
    d1, ex1 = compute_send_failure_backoff(1)
    d2, ex2 = compute_send_failure_backoff(2)
    d3, ex3 = compute_send_failure_backoff(3)
    assert (ex1, ex2, ex3) == (False, False, False)
    assert d1 == timedelta(minutes=15)
    assert d2 == timedelta(minutes=30)
    assert d3 == timedelta(minutes=60)


def test_backoff_is_capped():
    delay, exhausted = compute_send_failure_backoff(4, cap_minutes=240)
    assert exhausted is False
    assert delay == timedelta(minutes=120)


def test_backoff_exhausts_after_max_retries():
    delay, exhausted = compute_send_failure_backoff(5)
    assert exhausted is True
    assert delay is None


def test_backoff_test_mode_collapses_to_one_minute():
    delay, exhausted = compute_send_failure_backoff(3, test_mode=True)
    assert exhausted is False
    assert delay == timedelta(minutes=1)


def test_backoff_never_negative_shift():
    delay, exhausted = compute_send_failure_backoff(1)
    assert delay == timedelta(minutes=15)
    assert exhausted is False
