"""Expansion Phase 2 — Automation Engine, HITL, LangGraph/n8n (Tasks 2.1-2.7).

Tracks Step 11 (Expansion Phase 2). Exercises the approval model + HITL module,
the AutomationEngine validate/pause/retry policy, the LangGraph runner
scaffold (linear fallback), the n8n client scaffold, and the approve/reject
API route registration.

See plans/IREIOS_3.0_EXPANSION_CHANGELOG.md (Phase 2 status).
"""
import asyncio
import json
import os
from uuid import uuid4

import pytest
from app.automation_engine.engine import submit, resume, reject, expire_stale_approvals
from app.automation_engine.hitl import request_approval, resolve, get_pending
from app.automation_engine.langgraph_runner import run_graph, resume_graph, serialize_state
from app.automation_engine.n8n_client import N8NClient
from app.execution_engine.base_executor import BaseExecutor, NoopExecutor
from app.execution_engine.execution_engine import ExecutionEngine
from database import SessionLocal
from models import ApprovalRequest


# --------------------------------------------------------------------------- #
# Fixtures: ApprovalRequest uses a JSONB column, which the SQLite dialect cannot
# compile, so these tests run against the real Postgres dev DB (the same one the
# bug-fix suite uses). Client id=1 already exists in dev. To keep the DB clean
# between runs, the HITL tests create rows tagged with unique markers and delete
# them in a finally block.
# --------------------------------------------------------------------------- #
@pytest.fixture()
def approval_db():
    return SessionLocal


def _cleanup_approvals(entity_ids):
    """Delete approval rows created by a test so the dev DB stays clean."""
    with SessionLocal() as db:
        db.query(ApprovalRequest).filter(
            ApprovalRequest.entity_id.in_(entity_ids)
        ).delete(synchronize_session=False)
        db.commit()


def _fake_session_factory(sink):
    class _S:
        def __init__(self):
            self.sink = sink

        def add(self, o):
            self.sink.append(o)

        def commit(self):
            pass

        def close(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.close()

    return lambda: _S()


# --------------------------------------------------------------------------- #
# Task 2.1 / 2.2 — Approval model + HITL
# --------------------------------------------------------------------------- #
def test_approval_request_model_columns():
    from sqlalchemy import inspect

    cols = {c.key for c in inspect(ApprovalRequest).columns}
    assert {"id", "client_id", "entity_id", "action_type", "action_payload",
            "status", "requested_by", "resolved_by", "reason",
            "correlation_id"} <= cols


def test_request_approval_persists_pending(approval_db):
    entity = f"e_persist_{uuid4()}"
    try:
        async def run():
            return await request_approval(
                {"action_type": "send_whatsapp", "tenant_id": "Client_1", "entity_id": entity,
                 "parameters": {"phone": "+91", "message": "hi"}},
                tenant_id="Client_1", entity_id=entity, requested_by="sales_agent",
            )

        res = asyncio.run(run())
        assert res["status"] == "pending"
        assert res["action_type"] == "send_whatsapp"
        with approval_db() as db:
            row = db.query(ApprovalRequest).filter(ApprovalRequest.id == res["id"]).first()
            assert row is not None
            assert row.status == "pending"
            assert row.client_id == 1
    finally:
        _cleanup_approvals([entity])


def test_approval_approve_returns_payload(approval_db):
    entity = f"e_approve_{uuid4()}"
    try:
        async def run():
            res = await request_approval(
                {"action_type": "send_whatsapp", "tenant_id": "Client_1", "entity_id": entity,
                 "parameters": {"phone": "+91", "message": "hi"}},
                tenant_id="Client_1", entity_id=entity,
            )
            return res, await resolve(res["id"], "approve", manager_id="m1", reason="looks good")

        res, out = asyncio.run(run())
        assert out["status"] == "approved"
        assert out["action_request"]["action_type"] == "send_whatsapp"
        with approval_db() as db:
            row = db.query(ApprovalRequest).filter(ApprovalRequest.id == res["id"]).first()
            assert row.status == "approved"
            assert row.resolved_by == "m1"
    finally:
        _cleanup_approvals([entity])


def test_approval_reject_marks_rejected(approval_db):
    entity = f"e_reject_{uuid4()}"
    try:
        async def run():
            res = await request_approval(
                {"action_type": "discount", "tenant_id": "Client_1", "entity_id": entity,
                 "parameters": {"amount": 5}},
                tenant_id="Client_1", entity_id=entity,
            )
            return res, await resolve(res["id"], "reject", manager_id="m1", reason="too risky")

        res, out = asyncio.run(run())
        assert out["status"] == "rejected"
        assert out["action_request"] is None
        with approval_db() as db:
            row = db.query(ApprovalRequest).filter(ApprovalRequest.id == res["id"]).first()
            assert row.status == "rejected"
            assert row.reason == "too risky"
    finally:
        _cleanup_approvals([entity])


def test_get_pending_scoped(approval_db):
    entity = f"e_scope_{uuid4()}"
    try:
        async def _seed():
            await request_approval(
                {"action_type": "x", "tenant_id": "Client_1", "entity_id": entity, "parameters": {}},
                tenant_id="Client_1", entity_id=entity,
            )
            await request_approval(
                {"action_type": "y", "tenant_id": "Client_2", "entity_id": entity, "parameters": {}},
                tenant_id="Client_2", entity_id=entity,
            )

        asyncio.run(_seed())
        pend1 = get_pending(client_id=1)
        pend1 = [p for p in pend1 if p["entity_id"] == entity]
        assert len(pend1) == 1
        assert pend1[0]["action_type"] == "x"
    finally:
        _cleanup_approvals([entity])


# --------------------------------------------------------------------------- #
# Task 2.3 — AutomationEngine validate / pause / retry
# --------------------------------------------------------------------------- #
def test_submit_invalid_rejected_without_ee():
    sink = []
    ee = ExecutionEngine(session_factory=_fake_session_factory(sink), bus=None)
    ee.register("noop", NoopExecutor())
    import app.automation_engine.engine as eng

    orig = eng.execution_engine
    eng.execution_engine = ee
    try:
        res = asyncio.run(submit({"action_type": "noop"}))  # missing keys
        assert res["status"] == "error"
        assert "missing" in res["error"]
    finally:
        eng.execution_engine = orig


def test_submit_linear_success():
    sink = []
    ee = ExecutionEngine(session_factory=_fake_session_factory(sink), bus=None)
    ee.register("noop", NoopExecutor())
    import app.automation_engine.engine as eng

    orig = eng.execution_engine
    eng.execution_engine = ee
    try:
        res = asyncio.run(submit({
            "action_type": "noop", "tenant_id": "Client_1", "entity_id": "e", "parameters": {},
        }))
        assert res["status"] == "success"
    finally:
        eng.execution_engine = orig


def test_submit_hitl_pauses_and_resume_runs():
    sink = []
    ee = ExecutionEngine(session_factory=_fake_session_factory(sink), bus=None)
    ee.register("noop", NoopExecutor())

    import app.automation_engine.engine as eng

    orig_ee = eng.execution_engine
    eng.execution_engine = ee
    try:
        req = {
            "action_type": "noop", "tenant_id": "Client_1", "entity_id": "e", "parameters": {},
            "requires_approval": True,
        }
        paused = asyncio.run(submit(req))
        assert paused["status"] == "pending_approval"
        # resume should strip the flag and execute
        out = asyncio.run(resume(paused["approval_id"]))
        assert out["status"] == "success"
    finally:
        eng.execution_engine = orig_ee
        # Clean up the approval row created against the dev DB.
        with SessionLocal() as db:
            db.query(ApprovalRequest).filter(
                ApprovalRequest.entity_id == "e", ApprovalRequest.action_type == "noop"
            ).delete()
            db.commit()


def test_submit_retries_then_dlq():
    sink = []

    class BoomExecutor(BaseExecutor):
        action_type = "boom"

        async def execute(self, action_request):
            raise RuntimeError("always fails")

    ee = ExecutionEngine(session_factory=_fake_session_factory(sink), bus=None)
    ee.register("boom", BoomExecutor())
    import app.automation_engine.engine as eng

    orig = eng.execution_engine
    eng.execution_engine = ee
    try:
        eng._MAX_ATTEMPTS = 2  # keep the test fast
        res = asyncio.run(submit({
            "action_type": "boom", "tenant_id": "Client_1", "entity_id": "e", "parameters": {},
        }))
        assert res["status"] == "error"
        # retries + final attempt -> EE writes DLQ on error
        assert len(sink) >= 1
    finally:
        eng.execution_engine = orig
        eng._MAX_ATTEMPTS = 3


# --------------------------------------------------------------------------- #
# Task 2.4 — LangGraph runner scaffold (linear fallback)
# --------------------------------------------------------------------------- #
def test_langgraph_linear_run_and_resume():
    state = run_graph({"action_type": "send_whatsapp", "requires_approval": False,
                       "parameters": {"message": "hi"}})
    assert state["ready_to_execute"] is True
    raw = serialize_state(state)
    resumed = resume_graph(json.loads(raw), "approve")
    assert resumed["ready_to_execute"] is True
    rejected = resume_graph(json.loads(raw), "reject")
    assert rejected["rejected"] is True


# --------------------------------------------------------------------------- #
# Task 2.5 — n8n client scaffold
# --------------------------------------------------------------------------- #
def test_n8n_unconfigured_returns_clean_error():
    async def run():
        client = N8NClient(base_url="", api_key="")
        assert client.configured is False
        return await client.trigger_workflow("wf1", {"x": 1})

    res = asyncio.run(run())
    assert res["status"] == "error"
    assert res["error"] == "n8n_not_configured"


def test_n8n_trigger_success(monkeypatch):
    import app.automation_engine.n8n_client as nc

    class _Resp:
        status_code = 200

        def json(self):
            return {"ok": True}

        def raise_for_status(self):
            pass

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return _Resp()

    monkeypatch.setattr(nc.httpx, "AsyncClient", _Client)
    async def run():
        client = N8NClient(base_url="http://n8n", api_key="key")
        assert client.configured is True
        return await client.trigger_workflow("wf1", {"x": 1})

    res = asyncio.run(run())
    assert res["status"] == "success"


# --------------------------------------------------------------------------- #
# Task 2.6 — Approve / reject API route registration
# --------------------------------------------------------------------------- #
def test_approve_reject_api_routes_registered():
    from fastapi.testclient import TestClient

    import main as main_mod

    # Routes are protected by JWT; we only assert they exist (not 404).
    with TestClient(main_mod.app) as client:
        r1 = client.post("/api/v1/approvals/1/approve")
        r2 = client.post("/api/v1/approvals/1/reject")
        r3 = client.get("/api/v1/approvals")
    assert r1.status_code in (401, 403)
    assert r2.status_code in (401, 403)
    assert r3.status_code in (401, 403)
