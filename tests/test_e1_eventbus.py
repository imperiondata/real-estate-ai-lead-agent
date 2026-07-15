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

