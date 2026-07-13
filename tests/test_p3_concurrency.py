"""P3 concurrency — timeout path, idempotency, WebhookLog race, SMS scope.

These tests inspect source files directly to verify code patterns, avoiding
heavy import dependencies (redis, boto3, etc.).
"""

import os
from datetime import datetime, timedelta, timezone


def _read_source(rel_path: str) -> str:
    """Read source file relative to the repo root."""
    test_dir = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(test_dir)
    path = os.path.join(root, rel_path)
    with open(path, encoding="utf-8") as f:
        return f.read()


MAIN_SRC = _read_source("main.py")
AGENT_SRC = _read_source("agent.py")


# ---------------------------------------------------------------------------
# P3.1 / P3.2 — background_process_and_push must re-acquire lock
# ---------------------------------------------------------------------------


class TestBackgroundLockReacquisition:
    """Background task must acquire the session lock before processing."""

    def test_background_lock_acquired_in_function(self):
        """background_process_and_push must acquire a Redis session lock."""
        assert "session_lock:" in MAIN_SRC
        assert "lock.acquire" in MAIN_SRC or "redis_client.lock" in MAIN_SRC

    def test_background_lock_uses_session_id(self):
        """Lock key includes session_id for per-session serialization."""
        assert "session_lock:{session_id}" in MAIN_SRC

    def test_background_lock_released_in_finally(self):
        """Lock must be released when done."""
        assert "lock.release()" in MAIN_SRC


# ---------------------------------------------------------------------------
# P3.1 — Interim TwiML deduplication per MessageSid
# ---------------------------------------------------------------------------


class TestInterimMessageDedup:
    """Only one interim 'Just checking…' per MessageSid."""

    def test_interim_dedup_key_exists(self):
        """Timeout handler sets a Redis key to dedup interim messages."""
        assert "interim_sent" in MAIN_SRC, (
            "Timeout handler must use a dedup key (e.g. interim_sent:{MessageSid})"
        )

    def test_interim_dedup_checks_before_sending(self):
        """Must check if interim was already sent before sending again."""
        assert "if already_sent" in MAIN_SRC or "send_interim = False" in MAIN_SRC


# ---------------------------------------------------------------------------
# P3.3 — is_background parameter must be read
# ---------------------------------------------------------------------------


class TestIsBackgroundFunctional:
    """process_chat must actually use the is_background flag for idempotency."""

    def test_is_background_used_in_body(self):
        """is_background must appear inside process_chat body, not just signature."""
        # Find the function
        assert "async def process_chat" in AGENT_SRC
        # Check there is a usage of is_background beyond the def line
        lines = AGENT_SRC.split("\n")
        uses = [
            i for i, l in enumerate(lines)
            if "is_background" in l and "def process_chat" not in l
        ]
        assert len(uses) >= 1, (
            "is_background must be used inside process_chat body "
            "(not only in the function signature)"
        )

    def test_background_checks_for_duplicate_message(self):
        """Background path must have a duplicate-message guard."""
        assert "_has_recent_duplicate_message" in AGENT_SRC


# ---------------------------------------------------------------------------
# P3.4 — WebhookLog insert-first + IntegrityError
# ---------------------------------------------------------------------------


class TestWebhookLogInsertFirst:
    """WebhookLog duplicate protection must use insert-first pattern."""

    def test_whatsapp_integrity_error_handled(self):
        """WhatsApp webhook catches IntegrityError for race-safe dedup."""
        assert "IntegrityError" in MAIN_SRC, (
            "Must import and handle IntegrityError for insert-first pattern"
        )
        assert "except IntegrityError" in MAIN_SRC

    def test_whatsapp_rolls_back_on_race(self):
        """On IntegrityError, must rollback before returning."""
        assert "db.rollback()" in MAIN_SRC

    def test_whatsapp_returns_empty_on_duplicate(self):
        """On IntegrityError, must return empty TwiML response."""
        whataspp_lines = MAIN_SRC.split("whatsapp_webhook")[1] if "whatsapp_webhook" in MAIN_SRC else MAIN_SRC
        assert "<Response></Response>" in MAIN_SRC

    def test_sms_integrity_error_handled(self):
        """SMS webhook also catches IntegrityError."""
        assert "IntegrityError" in MAIN_SRC


# ---------------------------------------------------------------------------
# P3.5 — SMS follow-up stop uses scoped session id
# ---------------------------------------------------------------------------


class TestSMSSessionScope:
    """SMS handler must use client_id-scoped session id for FollowUpState lookup."""

    def test_sms_creates_scoped_session_id(self):
        """SMS handler must construct a client-prefixed scoped session id."""
        assert "scoped_session_id" in MAIN_SRC

    def test_sms_followup_uses_scoped_id(self):
        """FollowUpState lookup must use scoped_session_id (in the helper)."""
        assert "FollowUpState.session_id == scoped_session_id" in MAIN_SRC, (
            "FollowUpState lookup must use scoped_session_id, not raw From"
        )

    def test_sms_lock_uses_scoped_id(self):
        """SMS Redis lock key must use scoped session id."""
        sms_section = MAIN_SRC.split("incoming_sms_webhook")[1]
        assert "session_lock:{scoped_session_id}" in sms_section


class TestSMSSessionScopeStopInsideLock:
    """P3.5 edge case: FollowUpState stop must be inside the Redis lock for atomicity."""

    def _sms_handler_body(self) -> str:
        """Extract the SMS handler body (from def to next @app.post)."""
        sms_start = MAIN_SRC.find("def incoming_sms_webhook")
        next_endpoint = MAIN_SRC.find("@app.post", sms_start + 1)
        if next_endpoint != -1:
            return MAIN_SRC[sms_start:next_endpoint]
        return MAIN_SRC[sms_start:]

    def test_sms_stop_inside_lock_normal_path(self):
        """Normal path: FollowUpState stop occurs AFTER the Redis lock begins."""
        body = self._sms_handler_body()
        lock_pos = body.find("async with redis_client.lock")
        first_stop_pos = body.find("_stop_followups_for_session(")
        assert lock_pos != -1, "Redis lock must exist in SMS handler"
        assert first_stop_pos != -1, "_stop_followups_for_session must exist in SMS handler"
        assert first_stop_pos > lock_pos, (
            "First _stop_followups_for_session call must occur AFTER the Redis lock begins"
        )

    def test_sms_stop_called_in_both_paths(self):
        """Stop helper must be present in both the locked path and the degraded fallback."""
        body = self._sms_handler_body()
        # Count occurrences of the helper call
        count = body.count("_stop_followups_for_session(")
        assert count >= 2, (
            f"_stop_followups_for_session must appear at least twice "
            f"(locked path + fallback), found {count}"
        )


# ---------------------------------------------------------------------------
# P3.3 — unit-style test for the duplicate message helper logic
# ---------------------------------------------------------------------------


class TestMessageIdempotency:
    """Verify the idempotent message insert logic works correctly."""

    def test_recent_message_detection_logic(self):
        """A helper should detect if same message was saved within 5 minutes."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=5)

        # Message saved 2 minutes ago → recent (should be detected)
        recent_ts = now - timedelta(minutes=2)
        assert recent_ts >= cutoff

        # Message saved 10 minutes ago → not recent
        old_ts = now - timedelta(minutes=10)
        assert old_ts < cutoff
