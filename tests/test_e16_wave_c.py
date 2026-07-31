"""Wave C — Promote 6 placeholders to real agents (C.0–C.7).

Plan: plans/IREIOS_3.0_WAVE_A_D_EXPANSION.md §3
Changelog: plans/IREIOS_3.0_WAVE_A_D_CHANGELOG.md
"""
from __future__ import annotations

import asyncio
import os

import pytest

os.environ.setdefault("ADMIN_API_KEY", "test-admin-key-wave-c")

from database import SessionLocal
from models import Client, Lead, Message, Session
from models import InventoryUnit as InvUnit, PricingRule as Prule


def _clean(db, sid):
    db.query(Message).filter(Message.session_id == sid).delete()
    db.query(Lead).filter(Lead.session_id == sid).delete()
    db.query(Session).filter(Session.id == sid).delete()
    db.commit()


def _db_ok() -> bool:
    try:
        db = SessionLocal()
        db.query(Client).first()
        db.close()
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# C.0 — Data model + seed
# --------------------------------------------------------------------------- #

def test_inventory_unit_model_exists():
    from models import InventoryUnit
    assert hasattr(InventoryUnit, "project_name")
    assert hasattr(InventoryUnit, "unit_code")
    assert hasattr(InventoryUnit, "status")
    assert hasattr(InventoryUnit, "bhk")
    assert hasattr(InventoryUnit, "list_price")


def test_pricing_rule_model_exists():
    from models import PricingRule
    assert hasattr(PricingRule, "location")
    assert hasattr(PricingRule, "bhk")
    assert hasattr(PricingRule, "min_budget")
    assert hasattr(PricingRule, "max_budget")


def test_seed_inventory_creates_units(monkeypatch):
    if not _db_ok():
        pytest.skip("DB not available")
    import pytest
    from seed_inventory import seed_inventory
    from database import SessionLocal
    from models import InventoryUnit

    db = SessionLocal()
    client = db.query(Client).first()
    if not client:
        db.close()
        pytest.skip("no client seed data")
    cid = client.id

    # Clear existing
    db.query(InventoryUnit).filter(InventoryUnit.client_id == cid).delete()
    db.commit()
    db.close()

    seed_inventory(cid)

    db2 = SessionLocal()
    try:
        count = db2.query(InventoryUnit).filter(InventoryUnit.client_id == cid).count()
        assert count >= 10
    finally:
        db2.query(InventoryUnit).filter(InventoryUnit.client_id == cid).delete()
        db2.commit()
        db2.close()


def test_seed_inventory_creates_pricing_rules(monkeypatch):
    if not _db_ok():
        pytest.skip("DB not available")
    import pytest
    from seed_inventory import seed_inventory
    from database import SessionLocal
    from models import PricingRule

    db = SessionLocal()
    client = db.query(Client).first()
    if not client:
        db.close()
        pytest.skip("no client seed data")
    cid = client.id

    db.query(PricingRule).filter(PricingRule.client_id == cid).delete()
    db.commit()
    db.close()

    seed_inventory(cid)

    db2 = SessionLocal()
    try:
        count = db2.query(PricingRule).filter(PricingRule.client_id == cid).count()
        assert count >= 3
    finally:
        db2.query(PricingRule).filter(PricingRule.client_id == cid).delete()
        db2.commit()
        db2.close()


# --------------------------------------------------------------------------- #
# C.1 — Negotiation agent
# --------------------------------------------------------------------------- #


def test_negotiation_agent_registered():
    from app.orchestrator.ceo_orchestrator import ceo
    from app.agents.negotiation_agent import register_negotiation
    # Remove first in case previously registered
    ceo.registry.unregister("negotiation_agent")
    register_negotiation(ceo)
    agents = ceo.registry.list_agents()
    matches = [a for a in agents if a.agent_id == "negotiation_agent"]
    assert len(matches) >= 1
    assert matches[0].status == "active"


def test_negotiation_handler_requests_approval_on_misaligned_budget(monkeypatch):
    if not _db_ok():
        pytest.skip("DB not available")
    from app.agents.negotiation_agent import handler
    from database import SessionLocal
    db = SessionLocal()
    client = db.query(Client).first()
    if not client:
        db.close()
        pytest.skip("no client")
    cid = client.id
    import uuid
    s = Session(id=str(uuid.uuid4()), client_id=cid, status="active")
    db.add(s); db.flush()
    l = Lead(session_id=s.id, client_id=cid, phone="+911234567890", name="Neg Test",
             budget="1.5cr", budget_alignment_status="misaligned", conversion_status="open")
    db.add(l); db.flush(); db.commit()
    lid = l.id; sid = s.id
    db.close()

    submitted = []
    async def fake_submit(req):
        submitted.append(req)
        return {"status": "success"}
    import app.agents.negotiation_agent as mod
    monkeypatch.setattr(mod, "ae_submit", fake_submit)

    asyncio.run(handler({
        "event_type": "lead.negotiation.started",
        "tenant_id": f"Client_{cid}",
        "entity_id": str(lid),
        "payload": {"lead_id": lid},
    }))

    assert len(submitted) >= 1
    assert submitted[0]["parameters"].get("kind") == "notify_admin"

    db2 = SessionLocal()
    _clean(db2, sid)
    db2.close()


# --------------------------------------------------------------------------- #
# C.2 — Pricing agent
# --------------------------------------------------------------------------- #


def test_pricing_agent_registered():
    from app.orchestrator.ceo_orchestrator import ceo
    from app.agents.pricing_agent import register_pricing
    ceo.registry.unregister("pricing_agent")
    register_pricing(ceo)
    agents = ceo.registry.list_agents()
    matches = [a for a in agents if a.agent_id == "pricing_agent"]
    assert len(matches) >= 1
    assert matches[0].status == "active"


def test_pricing_resolve_matches_budget(monkeypatch):
    if not _db_ok():
        pytest.skip("DB not available")
    from app.agents.pricing_agent import resolve_pricing
    from database import SessionLocal
    from models import PricingRule

    db = SessionLocal()
    client = db.query(Client).first()
    if not client:
        db.close()
        pytest.skip("no client")
    cid = client.id

    # Create a test pricing rule
    rule = PricingRule(client_id=cid, location="Test City", bhk="2BHK", min_budget=5000000, max_budget=10000000, list_price=8000000)
    db.add(rule); db.commit()
    rid = rule.id

    match = resolve_pricing(cid, "Test City", 7500000)
    assert match is not None
    assert match["list_price"] == 8000000

    no_match = resolve_pricing(cid, "Test City", 2000000)
    assert no_match is None

    db.delete(rule); db.commit(); db.close()


# --------------------------------------------------------------------------- #
# C.3 — Inventory agent
# --------------------------------------------------------------------------- #


def test_inventory_agent_registered():
    from app.orchestrator.ceo_orchestrator import ceo
    from app.agents.inventory_agent import register_inventory
    ceo.registry.unregister("inventory_agent")
    register_inventory(ceo)
    agents = ceo.registry.list_agents()
    matches = [a for a in agents if a.agent_id == "inventory_agent"]
    assert len(matches) >= 1
    assert matches[0].status == "active"


def test_inventory_query_returns_units(monkeypatch):
    if not _db_ok():
        pytest.skip("DB not available")
    from app.agents.inventory_agent import query_inventory
    from database import SessionLocal
    from models import InventoryUnit

    db = SessionLocal()
    client = db.query(Client).first()
    if not client:
        db.close()
        pytest.skip("no client")
    cid = client.id
    unit = InventoryUnit(client_id=cid, project_name="Test Proj", unit_code="T-001", bhk="2BHK",
                         location="Test City", list_price=8000000, status="available")
    db.add(unit); db.commit()
    uid = unit.id

    results = query_inventory(cid, location="Test City")
    assert len(results) >= 1
    assert results[0]["unit_code"] == "T-001"

    db.delete(unit); db.commit(); db.close()


# --------------------------------------------------------------------------- #
# C.4 — Onboarding agent
# --------------------------------------------------------------------------- #


def test_onboarding_agent_registered():
    from app.orchestrator.ceo_orchestrator import ceo
    from app.agents.onboarding_agent import register_onboarding
    ceo.registry.unregister("onboarding_agent")
    register_onboarding(ceo)
    agents = ceo.registry.list_agents()
    matches = [a for a in agents if a.agent_id == "onboarding_agent"]
    assert len(matches) >= 1
    assert matches[0].status == "active"


# --------------------------------------------------------------------------- #
# C.5 — Finance agent
# --------------------------------------------------------------------------- #


def test_finance_agent_registered():
    from app.orchestrator.ceo_orchestrator import ceo
    from app.agents.finance_agent import register_finance
    ceo.registry.unregister("finance_agent")
    register_finance(ceo)
    agents = ceo.registry.list_agents()
    matches = [a for a in agents if a.agent_id == "finance_agent"]
    assert len(matches) >= 1
    assert matches[0].status == "active"


# --------------------------------------------------------------------------- #
# C.6 — Legal agent
# --------------------------------------------------------------------------- #


def test_legal_agent_registered():
    from app.orchestrator.ceo_orchestrator import ceo
    from app.agents.legal_agent import register_legal
    ceo.registry.unregister("legal_agent")
    register_legal(ceo)
    agents = ceo.registry.list_agents()
    matches = [a for a in agents if a.agent_id == "legal_agent"]
    assert len(matches) >= 1
    assert matches[0].status == "active"


# --------------------------------------------------------------------------- #
# C.7 — Placeholder cleanup
# --------------------------------------------------------------------------- #


def test_placeholders_cleaned():
    from app.agents.placeholders import PLACEHOLDER_AGENTS
    assert len(PLACEHOLDER_AGENTS) == 0
    from app.orchestrator.ceo_orchestrator import ceo
    agents = ceo.registry.list_agents()
    placeholder_ids = [a.agent_id for a in agents if a.status == "placeholder"]
    assert len(placeholder_ids) == 0
