"""Oct 2 — tenant context on async jobs, and tagged RAG chunk filter."""

import inspect

import pytest

from config import tenant_id_ctx, use_tenant
from rag import _chunk_visible


def test_use_tenant_resets_after_block():
    tenant_id_ctx.set("None")
    with use_tenant("Client_3"):
        assert tenant_id_ctx.get() == "Client_3"
    assert tenant_id_ctx.get() == "None"


def test_use_tenant_resets_on_exception():
    tenant_id_ctx.set("None")
    with pytest.raises(RuntimeError):
        with use_tenant("Client_9"):
            raise RuntimeError("boom")
    assert tenant_id_ctx.get() == "None"


def test_empty_tenant_becomes_none():
    tenant_id_ctx.set("Client_1")
    with use_tenant(""):
        assert tenant_id_ctx.get() == "None"
    assert tenant_id_ctx.get() == "Client_1"


@pytest.mark.parametrize(
    "module,qualname",
    [
        ("app.clients.event_bus_client", "EventBusClient._dispatch"),
        ("app.orchestrator.ceo_orchestrator", "CEOOrchestrator.handle_event"),
        ("app.automation_engine.n8n_bridge", "N8NBridge._handle_message"),
        ("app.execution_engine.execution_engine", "ExecutionEngine.dispatch"),
        ("crm_sync", "crm_resync_job"),
        ("app.workflows.competitor_monitor", "competitor_monitor_job"),
        ("app.workflows.weekly_marketing_cron", "weekly_marketing_cron_job"),
        ("app.automation_engine.engine", "expire_stale_approvals"),
        ("main", "daily_cleanup_job"),
        ("db_backup", "backup_postgres"),
    ],
)
def test_job_sets_tenant_scope(module, qualname):
    mod = __import__(module, fromlist=["*"])
    obj = mod
    for part in qualname.split("."):
        obj = getattr(obj, part)
    src = inspect.getsource(obj)
    assert "use_tenant(" in src


def test_untagged_faq_chunk_stays_visible():
    assert _chunk_visible({"location": "Baner"}, client_id=3) is True
    assert _chunk_visible({"location": "Baner"}, client_id=None) is True


def test_foreign_tagged_chunk_is_dropped():
    assert _chunk_visible({"client_id": 9, "location": "Baner"}, client_id=3) is False
    assert _chunk_visible({"client_id": 3, "location": "Baner"}, client_id=3) is True
    assert _chunk_visible({"client_id": "3", "location": "Baner"}, client_id=3) is True
