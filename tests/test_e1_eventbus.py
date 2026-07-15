"""Expansion Phase 1 — Redis Streams Event Bus + Agent registry (Tasks 1.1-1.3).

Tests the EventBusClient against the running redis-local container
(transport = Redis Streams only; no in-process fallback). Each test uses a
unique stream + consumer group so runs never collide. Registry tests are
pure (no Redis).

See plans/IREIOS_3.0_EXPANSION_CHANGELOG.md (Phase 1 status).
"""
import asyncio
import uuid

import pytest

from app.clients.event_bus_client import EventBusClient
from app.orchestrator.agent_registry import AgentRegistry, AgentRecord
from app.orchestrator.ceo_orchestrator import CEOOrchestrator
from app.execution_engine.execution_engine import ExecutionEngine, resolve_client_id
from app.execution_engine.base_executor import BaseExecutor, NoopExecutor
from app.agents.base_agent import BaseAgent
from app.automation_engine.engine import submit
from models import DLQEvent


def _names() -> tuple[str, str]:
    suffix = uuid.uuid4().hex[:8]
    return f"ireios:test:{suffix}", f"cg-{suffix}"


def test_publish_reaches_subscriber():
    async def run():
        stream, group = _names()
        bus = EventBusClient(stream=stream, group=group)
        received = []
        bus.subscribe("lead.created", lambda e: received.append(e))
        await bus.start()
        try:
            eid = await bus.publish("lead.created", "client_A", "lead_1", {"name": "x"})
            await asyncio.sleep(1.0)
        finally:
            await bus.stop()
        assert len(received) == 1, received
        env = received[0]
        assert env["event_id"] == eid
        assert env["event_type"] == "lead.created"
        assert env["tenant_id"] == "client_A"
        assert env["entity_id"] == "lead_1"
        assert env["payload"] == {"name": "x"}
        assert env["correlation_id"]
        assert env["source"] == "system"

    asyncio.run(run())


def test_wildcard_subscriber_receives_all():
    async def run():
        stream, group = _names()
        bus = EventBusClient(stream=stream, group=group)
        seen = []
        bus.subscribe("*", lambda e: seen.append(e["event_type"]))
        await bus.start()
        try:
            await bus.publish("lead.created", "t", "e1", {})
            await bus.publish("whatsapp.sent", "t", "e2", {})
            await asyncio.sleep(1.0)
        finally:
            await bus.stop()
        assert sorted(seen) == ["lead.created", "whatsapp.sent"], seen

    asyncio.run(run())


def test_durable_redelivery_after_restart():
    """A consumer that crashes before ACKing must have its message
    redelivered to a restarted consumer (same consumer identity)."""
    async def run():
        stream, group = _names()
        consumer = f"consumer-{uuid.uuid4().hex[:8]}"

        seen1 = []

        async def slow_handler(e):
            seen1.append(e)
            await asyncio.sleep(30)  # simulate long work / crash before ack

        bus1 = EventBusClient(stream=stream, group=group, consumer=consumer)
        bus1.subscribe("lead.created", slow_handler)
        await bus1.start()
        await bus1.publish("lead.created", "client_A", "lead_1", {})
        await asyncio.sleep(0.4)  # handler started, message now in PEL unacked
        await bus1.stop()  # simulate crash before ack
        assert len(seen1) == 1

        seen2 = []
        bus2 = EventBusClient(stream=stream, group=group, consumer=consumer)
        bus2.subscribe("lead.created", lambda e: seen2.append(e))
        await bus2.start()
        await asyncio.sleep(1.0)  # drains PEL on startup -> redelivers
        await bus2.stop()

        assert len(seen2) == 1, f"expected redelivery from PEL, got {len(seen2)}"
        assert seen2[0]["entity_id"] == "lead_1"

    asyncio.run(run())


def test_redis_down_fails_loud():
    """When Redis is unreachable, the bus must not pretend success."""
    async def run():
        stream, group = _names()
        bus = EventBusClient(stream=stream, group=group, redis_url="redis://127.0.0.1:1")
        with pytest.raises(Exception):
            await bus.start()

    asyncio.run(run())


def test_handler_failure_does_not_kill_loop():
    """A raising handler must not crash the consumer loop; sibling
    handlers for the same event still run."""
    async def run():
        stream, group = _names()
        bus = EventBusClient(stream=stream, group=group)
        ok = []

        def boom(e):
            raise RuntimeError("boom")

        bus.subscribe("lead.created", boom)
        bus.subscribe("lead.created", lambda e: ok.append(e))

        await bus.start()
        try:
            await bus.publish("lead.created", "t", "e1", {})
            await asyncio.sleep(1.0)
            await bus.publish("lead.created", "t", "e2", {})
            await asyncio.sleep(1.0)
        finally:
            await bus.stop()
        assert len(ok) == 2, ok  # loop survived both bad dispatches

    asyncio.run(run())


# ---------------------------------------------------------------------- #
# Task 1.3 — Agent registry (pure, no Redis)
# ---------------------------------------------------------------------- #
def _noop(e):
    return None


def test_register_two_agents_same_event():
    reg = AgentRegistry()
    reg.register("agent_a", _noop, ["lead.created"])
    reg.register("agent_b", _noop, ["lead.created"])
    subs = reg.get_subscribers("lead.created")
    assert {r.agent_id for r in subs} == {"agent_a", "agent_b"}


def test_placeholder_still_listed():
    reg = AgentRegistry()
    reg.register("agent_real", _noop, ["lead.created"], status="active")
    reg.register("agent_future", _noop, ["lead.created"], status="placeholder")
    subs = reg.get_subscribers("lead.created")
    # placeholder is returned by the registry; the CEO decides to skip it
    assert {r.agent_id for r in subs} == {"agent_real", "agent_future"}
    assert {r.status for r in subs} == {"active", "placeholder"}


def test_wildcard_subscription():
    reg = AgentRegistry()
    reg.register("catch_all", _noop, ["*"])
    reg.register("specific", _noop, ["lead.created"])
    assert "catch_all" in {r.agent_id for r in reg.get_subscribers("whatsapp.sent")}
    assert "specific" not in {r.agent_id for r in reg.get_subscribers("whatsapp.sent")}
    assert "specific" in {r.agent_id for r in reg.get_subscribers("lead.created")}


def test_unregister():
    reg = AgentRegistry()
    reg.register("agent_a", _noop, ["lead.created"])
    reg.register("agent_b", _noop, ["lead.created"])
    reg.unregister("agent_a")
    assert {r.agent_id for r in reg.get_subscribers("lead.created")} == {"agent_b"}
    assert len(reg.list_agents()) == 1
    reg.unregister("agent_a")  # no-op, must not raise
    assert len(reg.list_agents()) == 1


def test_record_success_failure():
    reg = AgentRegistry()
    reg.register("agent_a", _noop, ["lead.created"])
    reg.record_failure("agent_a", RuntimeError("boom"))
    rec = reg.get_subscribers("lead.created")[0]
    assert rec.last_error == "boom"
    assert rec.last_seen is not None
    reg.record_success("agent_a")
    rec = reg.get_subscribers("lead.created")[0]
    assert rec.last_error is None
    assert rec.last_seen is not None


def test_register_invalid_status():
    reg = AgentRegistry()
    with pytest.raises(ValueError):
        reg.register("bad", _noop, ["lead.created"], status="weird")


# ---------------------------------------------------------------------- #
# Task 1.4 — CEO Orchestrator (routes bus events -> registered agents)
# ---------------------------------------------------------------------- #
def test_ceo_routes_to_active_agent():
    async def run():
        import uuid

        stream, group = f"ireios:test:{uuid.uuid4().hex[:8]}", f"cg-{uuid.uuid4().hex[:8]}"
        registry = AgentRegistry()
        bus = EventBusClient(stream=stream, group=group)
        ceo_inst = CEOOrchestrator(registry=registry, bus=bus)
        seen = []

        def handler(e):
            seen.append(e)

        ceo_inst.register_agent("a1", handler, ["lead.created"])
        ceo_inst.bootstrap()
        await bus.start()
        try:
            await bus.publish("lead.created", "t", "e1", {"name": "x"})
            await asyncio.sleep(0.8)
        finally:
            await bus.stop()
        assert len(seen) == 1, seen
        assert seen[0]["event_type"] == "lead.created"

    asyncio.run(run())


def test_ceo_skips_placeholder():
    async def run():
        import uuid

        stream, group = f"ireios:test:{uuid.uuid4().hex[:8]}", f"cg-{uuid.uuid4().hex[:8]}"
        registry = AgentRegistry()
        bus = EventBusClient(stream=stream, group=group)
        ceo_inst = CEOOrchestrator(registry=registry, bus=bus)
        active_seen, placeholder_seen = [], []

        ceo_inst.register_agent("active_a", lambda e: active_seen.append(e), ["lead.created"])
        ceo_inst.register_agent("future_a", lambda e: placeholder_seen.append(e), ["lead.created"], status="placeholder")
        ceo_inst.bootstrap()
        await bus.start()
        try:
            await bus.publish("lead.created", "t", "e1", {})
            await asyncio.sleep(0.8)
        finally:
            await bus.stop()
        assert len(active_seen) == 1
        assert placeholder_seen == []  # placeholder NOT invoked

    asyncio.run(run())


def test_ceo_publishes_failed_event():
    async def run():
        import uuid

        stream, group = f"ireios:test:{uuid.uuid4().hex[:8]}", f"cg-{uuid.uuid4().hex[:8]}"
        registry = AgentRegistry()
        bus = EventBusClient(stream=stream, group=group)
        ceo_inst = CEOOrchestrator(registry=registry, bus=bus)
        failed_seen = []

        def boom(e):
            raise RuntimeError("agent broke")

        ceo_inst.register_agent("a1", boom, ["lead.created"])
        ceo_inst.bootstrap()
        bus.subscribe("a1.failed", lambda e: failed_seen.append(e))
        await bus.start()
        try:
            await bus.publish("lead.created", "t", "e1", {})
            await asyncio.sleep(0.8)
        finally:
            await bus.stop()
        assert len(failed_seen) == 1, failed_seen
        assert failed_seen[0]["event_type"] == "a1.failed"
        assert failed_seen[0]["payload"]["agent_id"] == "a1"
        # health recorded
        rec = registry.get_subscribers("lead.created")[0]
        assert rec.last_error == "agent broke"

    asyncio.run(run())


def test_ceo_handle_event_direct_no_bus():
    async def run():
        registry = AgentRegistry()
        ceo_inst = CEOOrchestrator(registry=registry, bus=None)
        active_seen, placeholder_seen = [], []

        ceo_inst.register_agent("active_a", lambda e: active_seen.append(e), ["lead.created"])
        ceo_inst.register_agent("future_a", lambda e: placeholder_seen.append(e), ["lead.created"], status="placeholder")

        def boom(e):
            raise RuntimeError("agent broke")

        ceo_inst.register_agent("bad_a", boom, ["lead.created"])
        await ceo_inst.handle_event({"event_type": "lead.created", "tenant_id": "t", "entity_id": "e1"})
        assert len(active_seen) == 1
        assert placeholder_seen == []
        bad_rec = next(r for r in registry.list_agents() if r.agent_id == "bad_a")
        assert bad_rec.last_error == "agent broke"

    asyncio.run(run())


# --------------------------------------------------------------------------- #
# Task 1.5 — BaseExecutor + ExecutionEngine skeleton
# --------------------------------------------------------------------------- #
class _FakeSession:
    """Minimal in-memory stand-in for an SQLAlchemy SessionLocal."""

    def __init__(self, sink: list):
        self._sink = sink

    def add(self, obj):
        self._sink.append(obj)

    def commit(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def test_resolve_client_id_parses_tenant():
    assert resolve_client_id("Client_1") == 1
    assert resolve_client_id("42") == 42
    assert resolve_client_id("garbage") is None
    assert resolve_client_id(None) is None


def test_ee_unknown_action_errors_and_dlq():
    async def run():
        sink = []
        ee = ExecutionEngine(session_factory=lambda: _FakeSession(sink), bus=None)
        result = await ee.dispatch({"action_type": "missing", "tenant_id": "Client_7", "entity_id": "e1"})
        assert result["status"] == "error"
        assert result["error"] == "no_executor"
        assert len(sink) == 1
        dlq = sink[0]
        assert isinstance(dlq, DLQEvent)
        assert dlq.target_endpoint == "missing"
        assert dlq.client_id == 7
        assert dlq.status == "pending"
        assert dlq.error_trace == "no_executor"

    asyncio.run(run())


def test_ee_noop_success_no_dlq():
    async def run():
        sink = []
        ee = ExecutionEngine(session_factory=lambda: _FakeSession(sink), bus=None)
        ee.register("noop", NoopExecutor())
        result = await ee.dispatch({"action_type": "noop", "tenant_id": "Client_1", "entity_id": "e1"})
        assert result["status"] == "success"
        assert sink == []  # success writes no DLQ

    asyncio.run(run())


def test_ee_failing_executor_writes_dlq():
    async def run():
        sink = []

        class BoomExecutor(BaseExecutor):
            action_type = "boom"

            async def execute(self, action_request):
                raise RuntimeError("kaboom")

        ee = ExecutionEngine(session_factory=lambda: _FakeSession(sink), bus=None)
        ee.register("boom", BoomExecutor())
        result = await ee.dispatch({"action_type": "boom", "tenant_id": "Client_3", "entity_id": "e1"})
        assert result["status"] == "error"
        assert result["error"] == "kaboom"
        assert len(sink) == 1
        assert sink[0].target_endpoint == "boom"
        assert sink[0].client_id == 3

    asyncio.run(run())


# --------------------------------------------------------------------------- #
# Task 1.6 — BaseAgent lifecycle + AutomationEngine stub
# --------------------------------------------------------------------------- #
def test_base_agent_lifecycle_success():
    async def run():
        # BaseAgent routes through the global execution_engine singleton
        # (via app.automation_engine.engine.submit), so register there.
        from app.execution_engine.execution_engine import execution_engine as ee_singleton

        ee_singleton.register("send_test", NoopExecutor())

        class TestAgent(BaseAgent):
            agent_id = "test_agent"
            subscriptions = ["lead.created"]

            async def fetch_context(self, event):
                return {"event": event}

            async def analyze(self, context):
                return {"ok": True}

            async def decide(self, analysis):
                return {
                    "action_type": "send_test",
                    "tenant_id": "Client_1",
                    "entity_id": "lead_1",
                    "parameters": {"message": "hi"},
                }

        agent = TestAgent(bus=None)
        result = await agent.process_event({"event_type": "lead.created", "tenant_id": "Client_1", "entity_id": "lead_1"})
        assert result["status"] == "success"

    asyncio.run(run())


def test_base_agent_lifecycle_failure_publishes_failed():
    async def run():
        stream, group = _names()
        bus = EventBusClient(stream=stream, group=group)
        failed_seen = []
        bus.subscribe("broken_agent.failed", lambda e: failed_seen.append(e))
        await bus.start()
        try:

            class BrokenAgent(BaseAgent):
                agent_id = "broken_agent"
                subscriptions = ["lead.created"]

                async def fetch_context(self, event):
                    raise RuntimeError("context broke")

                async def analyze(self, context):  # pragma: no cover - not reached
                    return context

                async def decide(self, analysis):  # pragma: no cover - not reached
                    return None

            agent = BrokenAgent(bus=bus)
            result = await agent.process_event({"event_type": "lead.created", "tenant_id": "Client_1", "entity_id": "e1"})
            assert result["status"] == "error"
            await asyncio.sleep(1.0)
        finally:
            await bus.stop()
        assert len(failed_seen) == 1, failed_seen
        assert failed_seen[0]["payload"]["agent_id"] == "broken_agent"

    asyncio.run(run())


# --------------------------------------------------------------------------- #
# Task 1.7 — lifespan wires bus start/stop (needs Redis)
# --------------------------------------------------------------------------- #
def test_lifespan_starts_and_stops_bus():
    import os

    import redis

    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        client = redis.Redis.from_url(url, socket_connect_timeout=3)
        if not client.ping():
            pytest.skip(f"Redis not reachable at {url}")
    except redis.exceptions.RedisError as exc:
        pytest.skip(f"Redis not reachable at {url}: {exc}")

    import main
    from app.clients.event_bus_client import event_bus as singleton_bus

    async def run():
        async with main.lifespan(main.app):
            assert singleton_bus._running is True
        assert singleton_bus._running is False
        assert singleton_bus._task is None

    asyncio.run(run())

