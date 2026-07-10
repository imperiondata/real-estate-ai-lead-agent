"""P0 safety — closing detection + hot-lead notify recipient resolution."""

from types import SimpleNamespace

import pytest

from agent import (
    clean_user_message,
    has_goodbye_token,
    is_closing_message,
    is_fully_qualified,
    is_opt_out_message,
    is_terminal_chat_state,
    should_rearm_day0,
)
from notification_service import resolve_hot_alert_recipient


# --- P0.1 closing detection ---


@pytest.mark.parametrize(
    "message,expect_close",
    [
        ("I am a buyer in Baner", False),
        ("maybe tomorrow", False),
        ("society byelaw question", False),
        ("bye", True),
        ("Bye!", True),
        ("goodbye", True),
        ("ok thanks", True),
        ("thank you", True),
        ("stop", True),
        ("please stop", True),
        ("dont message me", True),
        ("hi need 2bhk", False),
    ],
)
def test_is_closing_message(message, expect_close):
    cleaned = clean_user_message(message)
    assert is_closing_message(cleaned) is expect_close


def test_buyer_is_not_goodbye_token():
    cleaned = clean_user_message("I am a buyer looking for 2BHK")
    assert has_goodbye_token(cleaned) is False
    assert is_closing_message(cleaned) is False


def test_bye_is_goodbye_token():
    assert has_goodbye_token(clean_user_message("bye")) is True
    assert has_goodbye_token(clean_user_message("Goodbye.")) is True


def test_opt_out_phrases():
    assert is_opt_out_message(clean_user_message("please stop")) is True
    assert is_opt_out_message(clean_user_message("I am a buyer")) is False


# --- P0.2 / P0.3 hot-lead recipient ---


def test_resolve_recipient_none_without_agent():
    assert resolve_hot_alert_recipient(None, "admin@example.com") is None


def test_resolve_recipient_none_without_phone():
    agent = SimpleNamespace(name="Agent A", phone=None, email="a@example.com")
    assert resolve_hot_alert_recipient(agent, "admin@example.com") is None


def test_resolve_recipient_none_blank_phone():
    agent = SimpleNamespace(name="Agent A", phone="   ", email="a@example.com")
    assert resolve_hot_alert_recipient(agent, "admin@example.com") is None


def test_resolve_recipient_ok_with_agent_phone():
    agent = SimpleNamespace(name="Agent A", phone="+919999999999", email="a@example.com")
    recipient = resolve_hot_alert_recipient(agent, "admin@example.com")
    assert recipient is not None
    assert recipient["phone"] == "+919999999999"
    assert recipient["name"] == "Agent A"
    assert recipient["email"] == "a@example.com"


def test_resolve_recipient_never_returns_lead_phone():
    """P0.2: lead phone must not appear in recipient resolution at all."""
    lead_phone = "+910000000001"
    assert resolve_hot_alert_recipient(None, "admin@example.com") is None
    agent = SimpleNamespace(name="X", phone="", email="")
    assert resolve_hot_alert_recipient(agent, "admin@example.com") is None
    assert lead_phone


# --- P0.4 / P0.5 terminal session + re-arm ---


def _qualified_lead(**overrides):
    base = dict(
        visit_date="2026-08-01",
        phone="+919999999999",
        name="Riya",
        location="Baner",
        budget="80L",
        property_type="2BHK",
        whatsapp_opt_in=True,
        funnel_stage="Appointment Scheduled",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_is_fully_qualified():
    assert is_fully_qualified(_qualified_lead()) is True
    assert is_fully_qualified(_qualified_lead(visit_date=None)) is False
    assert is_fully_qualified(None) is False


def test_is_fully_qualified_stays_callable_after_bool_check():
    """Regression: local bool must not shadow helper (connectivity fallback TypeError)."""
    lead = _qualified_lead()
    flag = is_fully_qualified(lead)
    assert flag is True
    assert callable(is_fully_qualified)
    assert is_fully_qualified(lead) is True


def test_terminal_when_fully_qualified():
    assert is_terminal_chat_state(_qualified_lead()) is True


def test_terminal_when_opted_out():
    lead = _qualified_lead(visit_date=None, name=None, whatsapp_opt_in=False)
    assert is_terminal_chat_state(lead) is True


def test_terminal_when_human_handoff():
    lead = SimpleNamespace(
        visit_date=None, phone="+1", name=None, location=None, budget=None,
        property_type=None, whatsapp_opt_in=True, funnel_stage="Human Handoff",
    )
    assert is_terminal_chat_state(lead) is True


def test_not_terminal_open_lead():
    lead = SimpleNamespace(
        visit_date=None, phone="+1", name="A", location="Baner", budget=None,
        property_type="2BHK", whatsapp_opt_in=True, funnel_stage="New",
    )
    assert is_terminal_chat_state(lead) is False


def test_should_not_rearm_when_qualified():
    session = SimpleNamespace(status="active")
    assert should_rearm_day0(session, _qualified_lead()) is False


def test_should_not_rearm_when_opted_out():
    session = SimpleNamespace(status="active")
    lead = _qualified_lead(visit_date=None, whatsapp_opt_in=False)
    assert should_rearm_day0(session, lead) is False


def test_should_not_rearm_when_session_closed():
    session = SimpleNamespace(status="closed")
    lead = SimpleNamespace(
        visit_date=None, phone="+1", name="A", location="Baner", budget=None,
        property_type="2BHK", whatsapp_opt_in=True, funnel_stage="New",
    )
    assert should_rearm_day0(session, lead) is False


def test_should_rearm_open_incomplete_lead():
    session = SimpleNamespace(status="active")
    lead = SimpleNamespace(
        visit_date=None, phone="+1", name="A", location="Baner", budget=None,
        property_type="2BHK", whatsapp_opt_in=True, funnel_stage="New",
    )
    assert should_rearm_day0(session, lead) is True


def test_polite_close_not_terminal_can_reopen_logic():
    """Thanks-only close without full qualify is not terminal — may set active again."""
    lead = SimpleNamespace(
        visit_date=None, phone="+1", name="A", location=None, budget=None,
        property_type=None, whatsapp_opt_in=True, funnel_stage="Contacted",
    )
    assert is_terminal_chat_state(lead) is False
    assert should_rearm_day0(SimpleNamespace(status="active"), lead) is True


# --- P0.6 failed notification terminal status ---


def test_failed_delivery_alert_is_terminal_once():
    from notification_service import terminal_status_after_failed_delivery_alert

    assert terminal_status_after_failed_delivery_alert("failed") == "failed_alerted"
    assert terminal_status_after_failed_delivery_alert("failed_alerted") == "failed_alerted"
    assert terminal_status_after_failed_delivery_alert("pending_ack") == "pending_ack"
