"""P1 REL01 — failed bus publish is recorded, not replayed. No live Redis."""
import asyncio
from pathlib import Path

from app.events.lead_hot import _safe_publish
from app.events.publish_dlq import record_publish_failure

REPO = Path(__file__).resolve().parent.parent


class FakeDb:
    def __init__(self, error=None):
        self.added = []
        self.committed = False
        self.error = error

    def add(self, obj):
        if self.error:
            raise self.error
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def close(self):
        pass


class BoomBus:
    async def publish(self, *args, **kwargs):
        raise RuntimeError("redis down")


def test_publish_failure_writes_event_bus_row(monkeypatch):
    holder = {}

    def factory():
        holder["db"] = FakeDb()
        return holder["db"]

    monkeypatch.setattr("app.events.publish_dlq.record_publish_failure", record_publish_failure)
    import app.clients.event_bus_client as bus_mod
    import app.events.publish_dlq as publish_dlq

    monkeypatch.setattr(bus_mod, "event_bus", BoomBus())
    monkeypatch.setattr(publish_dlq, "record_publish_failure", lambda *a, **k: record_publish_failure(*a, session_factory=factory, **k))

    asyncio.run(_safe_publish("lead.hot", 3, 9, {"name": "Ada", "phone": "+919876543210"}, "test"))

    row = holder["db"].added[0]
    assert row.target_endpoint == "event_bus"
    assert row.client_id == 3
    assert row.status == "pending"
    assert row.payload["event_type"] == "lead.hot"
    assert row.payload["tenant_id"] == "Client_3"
    assert "phone" not in row.payload["payload"]
    assert holder["db"].committed is True


def test_missing_client_is_not_tenant_one():
    db = FakeDb()
    record_publish_failure(
        "lead.hot", None, 9, {"name": "Ada"}, "test", RuntimeError("x"), session_factory=lambda: db
    )
    assert db.added[0].client_id is None
    assert db.added[0].payload["tenant_id"] is None


def test_dlq_write_error_does_not_raise():
    record_publish_failure(
        "lead.hot",
        3,
        9,
        {},
        "test",
        RuntimeError("redis"),
        session_factory=lambda: FakeDb(error=RuntimeError("db down")),
    )


def test_replay_does_not_republish_event_bus():
    src = (REPO / "dlq_replay.py").read_text(encoding="utf-8")
    assert "event_bus" not in src
    hot = (REPO / "app" / "events" / "lead_hot.py").read_text(encoding="utf-8")
    neg = (REPO / "app" / "events" / "negotiation.py").read_text(encoding="utf-8")
    agent = (REPO / "app" / "agents" / "negotiation_agent.py").read_text(encoding="utf-8")
    assert "record_publish_failure" in hot
    assert "record_publish_failure" in neg
    assert agent.count("record_publish_failure(") == 2
