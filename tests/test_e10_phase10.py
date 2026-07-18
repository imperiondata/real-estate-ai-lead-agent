"""Expansion Phase 10 — Placeholders, decommission, evidence (Tasks 10.1–10.5).

Tracks Step 19 (Expansion Phase 10). Exercises placeholder agent registration
and the evidence pack builder. Tasks 10.2/10.3 (remove dual-path WhatsApp,
decommission crm_sync/follow_up) are intentionally deferred to a dedicated
decommission window and recorded as `[-]` with reason in the changelog; the
runtime path already routes new work through AE->EE and the legacy modules are
still shared by the v3 wrappers.

See plans/IREIOS_3.0_EXPANSION_CHANGELOG.md (Phase 10 status).
"""
from app.agents.placeholders import PLACEHOLDER_AGENTS, register_placeholders
from app.orchestrator.ceo_orchestrator import CEOOrchestrator, AgentRegistry


def test_register_placeholders():
    reg = AgentRegistry()
    ceo = CEOOrchestrator(registry=reg)
    ids = register_placeholders(ceo)
    assert set(ids) == set(PLACEHOLDER_AGENTS)
    records = reg.list_agents()
    placeholders = [r for r in records if r.status == "placeholder"]
    assert len(placeholders) == len(PLACEHOLDER_AGENTS)
    # CEO must skip placeholder agents when dispatching (no side effects).
    seen = []
    ceo.register_agent("probe", lambda e: seen.append(e), subscriptions=["lead.created"])
    ceo.bootstrap()
    import asyncio
    asyncio.run(ceo.handle_event({"event_type": "lead.created", "tenant_id": "Client_1"}))
    # only the active probe handler should have run
    assert len(seen) == 1


def test_evidence_pack_builds():
    from ireios_evidence import build_evidence
    ev = build_evidence()
    assert ev["event_bus_backend"] == "redis_streams"
    assert "runtime_path" in ev
    assert isinstance(ev["registered_agents"], list)
