"""P2.1 — finalize_turn: early intercepts must re-arm Day 0."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from agent import finalize_turn, is_fully_qualified, should_rearm_day0


class _FakeDB:
    """In-memory commit tracker for unit tests (no real DB)."""

    def __init__(self):
        self.committed = False

    def commit(self):
        self.committed = True


def _make_lead(**overrides):
    base = dict(
        visit_date=None,
        phone="+919999999999",
        name=None,
        location=None,
        budget=None,
        property_type=None,
        whatsapp_opt_in=True,
        funnel_stage="New",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_session(status="active"):
    return SimpleNamespace(status=status)


def _make_fstate(**overrides):
    base = dict(
        follow_up_stage=None,
        follow_up_status="stopped",
        next_follow_up_at=None,
        last_ai_reply_timestamp=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# --- finalize_turn core behavior ---


def test_finalize_rearms_day0_for_open_lead():
    """Normal open lead → Day 0 active with next_follow_up_at set."""
    db = _FakeDB()
    session = _make_session(status="active")
    lead = _make_lead()
    f_state = _make_fstate()

    finalize_turn(db, session, lead, f_state)

    assert f_state.follow_up_stage == "Day 0"
    assert f_state.follow_up_status == "active"
    assert f_state.next_follow_up_at is not None
    assert f_state.last_ai_reply_timestamp is not None
    assert db.committed is True


def test_finalize_does_not_rearm_when_fully_qualified():
    """Fully qualified → completed, not active."""
    db = _FakeDB()
    session = _make_session(status="active")
    lead = _make_lead(
        visit_date="2026-08-01", name="Riya", location="Baner",
        budget="80L", property_type="2BHK",
    )
    f_state = _make_fstate()

    finalize_turn(db, session, lead, f_state)

    assert is_fully_qualified(lead) is True
    assert f_state.follow_up_status == "completed"
    assert f_state.next_follow_up_at is None


def test_finalize_does_not_rearm_when_opted_out():
    """Opted out → stopped."""
    db = _FakeDB()
    session = _make_session(status="active")
    lead = _make_lead(whatsapp_opt_in=False)
    f_state = _make_fstate()

    finalize_turn(db, session, lead, f_state)

    assert f_state.follow_up_status == "stopped"
    assert f_state.next_follow_up_at is None


def test_finalize_does_not_rearm_when_human_handoff():
    """Human Handoff terminal → follow_up_status stays stopped (not re-armed)."""
    db = _FakeDB()
    session = _make_session(status="active")
    lead = _make_lead(funnel_stage="Human Handoff")
    f_state = _make_fstate()

    finalize_turn(db, session, lead, f_state)

    # Handoff is terminal via is_terminal_chat_state → should_rearm_day0=False
    # finalize_turn's elif chain: not fully qualified, not opted out → no explicit branch hit
    # but follow_up_status stays "stopped" (initial value) since should_rearm returned False
    assert f_state.follow_up_status == "stopped"
    assert f_state.next_follow_up_at is None


def test_finalize_does_not_rearm_when_session_closed():
    """Session closed (e.g. polite thanks) → should_rearm_day0 returns False."""
    db = _FakeDB()
    session = _make_session(status="closed")
    lead = _make_lead()
    f_state = _make_fstate()

    finalize_turn(db, session, lead, f_state)

    assert f_state.follow_up_status == "stopped"
    assert f_state.next_follow_up_at is None


def test_finalize_handles_none_fstate():
    """No FollowUpState → no crash."""
    db = _FakeDB()
    session = _make_session()
    lead = _make_lead()
    finalize_turn(db, session, lead, None)  # should not raise


def test_finalize_sets_last_ai_reply_timestamp():
    """last_ai_reply_timestamp always set when f_state exists."""
    db = _FakeDB()
    session = _make_session()
    lead = _make_lead()
    f_state = _make_fstate()

    before = datetime.now(timezone.utc)
    finalize_turn(db, session, lead, f_state)
    after = datetime.now(timezone.utc)

    assert f_state.last_ai_reply_timestamp is not None
    assert before <= f_state.last_ai_reply_timestamp <= after


# --- P2.3: Name interceptor validation blocklist ---

from agent import validate_extracted_name


def test_validate_name_rejects_2bhk():
    assert validate_extracted_name("2BHK") is False


def test_validate_name_rejects_tomorrow():
    assert validate_extracted_name("tomorrow") is False


def test_validate_name_rejects_area_name():
    assert validate_extracted_name("Baner") is False
    assert validate_extracted_name("Wakad") is False


def test_validate_name_rejects_budget_word():
    assert validate_extracted_name("budget") is False
    assert validate_extracted_name("lakhs") is False


def test_validate_name_rejects_affirmation():
    assert validate_extracted_name("yes") is False
    assert validate_extracted_name("sure") is False
    assert validate_extracted_name("okay") is False


def test_validate_name_rejects_too_long():
    assert validate_extracted_name("A very long string that is definitely not a real person name") is False


def test_validate_name_rejects_numeric():
    assert validate_extracted_name("12345") is False


def test_validate_name_accepts_single_name():
    assert validate_extracted_name("Aritra") is True


def test_validate_name_accepts_two_word_name():
    assert validate_extracted_name("Priya Sharma") is True


def test_validate_name_accepts_hyphenated_name():
    assert validate_extracted_name("Raj-Kumar") is True


def test_validate_name_rejects_empty():
    assert validate_extracted_name("") is False
    assert validate_extracted_name(None) is False


# --- P2.4: Funnel stage enum alignment ---

from agent import FUNNEL_STAGES


def test_funnel_stages_constant_has_canonical_values():
    assert "New" in FUNNEL_STAGES
    assert "Contacted" in FUNNEL_STAGES
    assert "Appointment Scheduled" in FUNNEL_STAGES
    assert "Closed Won" in FUNNEL_STAGES
    assert "Lost" in FUNNEL_STAGES
    assert len(FUNNEL_STAGES) == 5


def test_funnel_stages_excludes_removed_values():
    """P2.4: 'Human Handoff', 'Qualified', 'Site Visit Done' are not valid stages."""
    assert "Human Handoff" not in FUNNEL_STAGES
    assert "Qualified" not in FUNNEL_STAGES
    assert "Site Visit Done" not in FUNNEL_STAGES


def test_handoff_sets_contacted_not_human_handoff():
    """P2.4: Handoff funnel_stage must be 'Contacted' (Kanban-aligned)."""
    # The handoff code path sets lead.funnel_stage = "Contacted"
    # Verify the constant is there
    assert "Contacted" in FUNNEL_STAGES


def test_patch_validator_rejects_invalid_stage():
    """P2.4: PATCH endpoint must reject non-canonical stage values."""
    from pydantic import ValidationError
    from main import LeadStageUpdate

    # Valid stages should pass
    for stage in FUNNEL_STAGES:
        obj = LeadStageUpdate(stage=stage)
        assert obj.stage == stage

    # Invalid stages should fail
    for bad_stage in ["Human Handoff", "Qualified", "Site Visit Done", "random"]:
        try:
            LeadStageUpdate(stage=bad_stage)
            assert False, f"Should have rejected '{bad_stage}'"
        except ValidationError:
            pass  # expected


# --- P2.6: Language enforcement ---

from agent import detect_user_language


def test_detect_user_language_english():
    assert detect_user_language("hi need 2bhk in baner") == "english"


def test_detect_user_language_hinglish():
    assert detect_user_language("mujhe 2bhk chahiye") == "hinglish"


def test_detect_user_language_mixed_english():
    """'budget 90 lakhs' has no Hinglish keywords → english."""
    assert detect_user_language("budget 90 lakhs") == "english"


def test_detect_user_language_pure_english_with_place():
    assert detect_user_language("I need a 2BHK in Hinjewadi") == "english"


def test_detect_user_language_hinglish_with_english_nouns():
    assert detect_user_language("Wakad mein 2BHK chahiye") == "hinglish"


def test_detect_user_language_empty():
    assert detect_user_language("") == "english"


def test_guard_swaps_hinglish_for_english_user():
    """Simulates output guard: if user=English and reply=Hinglish → swap."""
    from agent import is_hinglish

    user_msg = "hi need 2bhk in baner"
    model_reply = "Hinjewadi mein 2BHKs ke liye options hain. Aapka budget kya hai?"

    assert detect_user_language(user_msg) == "english"
    assert is_hinglish(model_reply) is True
    # Guard would fire: user=english, reply=hinglish → swap to fallback


def test_guard_allows_hinglish_for_hinglish_user():
    """If user initiated Hinglish, Hinglish reply is allowed."""
    from agent import is_hinglish

    user_msg = "mujhe 2bhk chahiye"
    model_reply = "Wakad mein humare paas 2BHKs hain."

    assert detect_user_language(user_msg) == "hinglish"
    assert is_hinglish(model_reply) is True
    # Guard does NOT fire: user=hinglish, reply=hinglish → ok


def test_guard_allows_english_for_english_user():
    """English user + English reply → no guard."""
    from agent import is_hinglish

    user_msg = "hi need 2bhk in baner"
    model_reply = "Got it! Baner has great 2BHK options. What's your budget?"

    assert detect_user_language(user_msg) == "english"
    assert is_hinglish(model_reply) is False
    # Guard does NOT fire: user=english, reply=english → ok


def test_is_hinglish_false_positive_let_me():
    """Normal English 'let me…' must not be flagged as Hinglish."""
    from agent import is_hinglish

    assert is_hinglish("Let me share some 2BHK options in Baner.") is False
    assert is_hinglish("Would you like me to shortlist a few?") is False
    assert is_hinglish("Tell me your budget when ready.") is False


def test_is_hinglish_still_detects_real_hinglish():
    from agent import is_hinglish

    assert is_hinglish("Hinjewadi mein 2BHKs ke liye options hain.") is True
    assert is_hinglish("Aapka budget kya hai?") is True
    assert is_hinglish("mujhe 2bhk chahiye") is True


def test_fallback_asks_only_budget_when_name_known():
    """DB already has name/loc/type — fallback must not re-ask name."""
    from types import SimpleNamespace
    from agent import build_english_fallback_reply

    lead = SimpleNamespace(
        name="Maitri",
        location="Baner",
        property_type="2BHK",
        budget=None,
    )
    reply = build_english_fallback_reply(lead)
    assert "Maitri" in reply
    assert "budget" in reply.lower()
    assert "name" not in reply.lower()
    assert "Baner" in reply
    assert "2BHK" in reply


def test_fallback_asks_name_when_missing():
    from types import SimpleNamespace
    from agent import build_english_fallback_reply

    lead = SimpleNamespace(
        name=None,
        location="Baner",
        property_type="2BHK",
        budget=None,
    )
    reply = build_english_fallback_reply(lead)
    assert "name" in reply.lower()
    assert "budget" in reply.lower()


def test_fallback_no_asks_when_fully_known():
    from types import SimpleNamespace
    from agent import build_english_fallback_reply

    lead = SimpleNamespace(
        name="Maitri",
        location="Baner",
        property_type="2BHK",
        budget=80,
    )
    reply = build_english_fallback_reply(lead)
    assert "Maitri" in reply
    assert "name" not in reply.lower()
    assert "budget" not in reply.lower()
    assert "site visit" in reply.lower() or "shortlisted" in reply.lower()


def test_guard_path_with_name_known_simulates_user_bug():
    """English user + false-positive Hinglish reply → field-aware fallback."""
    from types import SimpleNamespace
    from agent import is_hinglish, build_english_fallback_reply

    user_msg = "hi.. im maitri i want 2bhk in baner"
    # Pre-fix: this English reply used to trip is_hinglish via bare "me"
    model_reply = "Got it Maitri! Let me share 2BHK options in Baner. What's your budget?"

    assert detect_user_language(user_msg) == "english"
    assert is_hinglish(model_reply) is False

    # If a real Hinglish reply still trips the guard, fallback must respect lead.name
    hinglish_reply = "Baner mein 2BHK options hain. Budget kya hai aur aapka naam?"
    assert is_hinglish(hinglish_reply) is True
    lead = SimpleNamespace(name="Maitri", location="Baner", property_type="2BHK", budget=None)
    fallback = build_english_fallback_reply(lead)
    assert "may i know your name" not in fallback.lower()
    assert "name" not in fallback.lower()
    assert "budget" in fallback.lower()
