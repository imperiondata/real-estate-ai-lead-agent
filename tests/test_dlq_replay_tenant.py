"""P0 SEC02 — DLQ replay must fail closed on tenant. No live DB, no Render."""
import asyncio
from pathlib import Path

import dlq_replay
from app.workflows import followup_arm

REPO = Path(__file__).resolve().parent.parent
SRC = (REPO / "dlq_replay.py").read_text(encoding="utf-8")


class _EmptyQuery:
    def filter(self, *a, **k):
        return self

    def first(self):
        return None


class FakeDb:
    def __init__(self):
        self.add_calls = []
        self.committed = False
        self.rolled_back = False

    def query(self, *a, **k):
        return _EmptyQuery()

    def add(self, obj):
        self.add_calls.append(obj)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def test_missing_session_does_not_send_or_write(monkeypatch):
    twilio_calls = []
    monkeypatch.setattr(dlq_replay.settings, "TWILIO_ACCOUNT_SID", "sid-for-test")

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        @property
        def messages(self):
            outer = self

            class _M:
                def create(self, **kwargs):
                    twilio_calls.append(kwargs)

            return _M()

    monkeypatch.setattr(dlq_replay, "Client", FakeClient)
    db = FakeDb()
    ok = dlq_replay.process_ml_followup(
        {"session_id": "missing-sess", "stage": "Day 1", "lead_data": {}}, db
    )
    assert ok is False
    assert twilio_calls == []
    assert db.add_calls == []


def test_source_has_no_tenant_one_fallback():
    assert "else 1" not in SRC


def test_main_uses_row_lock():
    assert "skip_locked" in SRC
    assert "with_for_update" in SRC


def test_resolve_client_none():
    assert followup_arm._resolve_client(None) is None


def test_resolve_client_garbage():
    assert followup_arm._resolve_client("nope") is None


def test_resolve_client_numeric():
    assert followup_arm._resolve_client("Client_3") == 3


def test_on_lead_created_without_tenant_does_not_arm(monkeypatch):
    calls = []
    monkeypatch.setattr(
        followup_arm, "arm_followup_state", lambda *a, **k: calls.append((a, k))
    )
    asyncio.run(
        followup_arm.on_lead_created(
            {
                "event_type": "lead.created",
                "entity_id": "sess-x",
                "payload": {"session_id": "sess-x"},
            }
        )
    )
    assert calls == []
