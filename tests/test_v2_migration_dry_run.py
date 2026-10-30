"""Isolated proof of full-table parity, partial dual-write retry, and rollback.

No database is opened. The procedure under test is in-memory. A Render or
LIVE_DATABASE_URL DSN is refused and is not a connection attempt.
"""

from __future__ import annotations

from pathlib import Path

from app.migration.dry_run import (
    LEAD_COLUMNS,
    REJECTED_CHECKSUM_COLUMNS,
    TABLES,
    DryRunStore,
    IsolationError,
    apply_dual_write,
    assert_isolated_dsn,
    reconcile_all,
    rejected_selected_field_checksum,
    retry_decision,
    retry_missing,
    rollback,
)

ROOT = Path(__file__).resolve().parents[1]


def _lead(**overrides) -> dict:
    row = {column: None for column in LEAD_COLUMNS}
    row.update(
        {
            "id": 1,
            "session_id": "s1",
            "client_id": 1,
            "name": "Ada",
            "phone": "9000000000",
            "budget": "50L",
            "location": "Baner",
            "property_type": "2bhk",
            "intent": "buy",
            "score": "Low",
            "visit_date": None,
            "source": "whatsapp",
            "whatsapp_opt_in": False,
            "funnel_stage": "New",
            "lead_temperature": "cold",
            "conversion_probability": 0,
        }
    )
    row.update(overrides)
    return row


def _fixture() -> dict:
    return {
        "clients": [{"id": 1, "company_name": "Imperion", "email": "a@example.com", "api_key": "secret-value"}],
        "sessions": [{"id": "s1", "client_id": 1, "status": "active", "follow_up_count": 0}],
        "leads": [_lead()],
        "messages": [{"id": 10, "client_id": 1, "session_id": "s1", "role": "user", "content": "hello"}],
        "webhook_logs": [{"message_sid": "SM1", "processed_at": "t0"}],
    }


def test_module_does_not_import_a_database():
    text = (ROOT / "app" / "migration" / "dry_run.py").read_text(encoding="utf-8")
    assert "sqlalchemy" not in text
    assert "psycopg" not in text
    assert "SessionLocal" not in text
    assert "rejected_selected_field_checksum" in text
    assert "reconcile_all" in text


def test_every_v1_table_and_every_lead_column_is_classified():
    migration = (ROOT / "V2_Migration_and_Security.md").read_text(encoding="utf-8")
    for table in (
        "sessions",
        "messages",
        "leads",
        "event_logs",
        "follow_up_states",
        "dlq_events",
        "agents",
        "approval_requests",
        "agent_learning",
        "notification_logs",
        "lead_memories",
        "inventory_units",
        "pricing_rules",
        "agent_tasks",
    ):
        assert table in TABLES, table
        assert f"| `{table}` |" in migration
    assert "webhook_logs" in TABLES
    assert TABLES["webhook_logs"]["global"] is True
    assert set(LEAD_COLUMNS) >= {
        "name",
        "phone",
        "budget",
        "location",
        "funnel_stage",
        "updated_at",
        "is_negotiating",
    }
    assert LEAD_COLUMNS["updated_at"] == "reported_only"
    assert LEAD_COLUMNS["budget"] == "industry_json"
    assert "name" in REJECTED_CHECKSUM_COLUMNS


def test_a_non_selected_column_mismatch_fails_parity():
    v1 = _fixture()
    v2 = _fixture()
    v2["leads"][0]["funnel_stage"] = "Contacted"
    v2["leads"][0]["location"] = "Wakad"
    # The rejected checksum still matches, because name, phone, and budget did not change.
    assert rejected_selected_field_checksum(v1["leads"]) == rejected_selected_field_checksum(v2["leads"])
    result = reconcile_all(v1, v2, tenant_id=1)
    assert result["ok"] is False
    mismatches = result["tables"]["leads"]["column_mismatches"]
    columns = {item["column"] for item in mismatches}
    assert "funnel_stage" in columns
    assert "location" in columns
    assert "name" not in columns


def test_secret_values_are_not_copied_into_the_report():
    v1 = _fixture()
    v2 = _fixture()
    v2["clients"][0]["api_key"] = "other-secret"
    result = reconcile_all(v1, v2, tenant_id=1)
    assert result["tables"]["clients"]["ok"] is False
    blob = str(result)
    assert "secret-value" not in blob
    assert "other-secret" not in blob


def test_partial_dual_write_is_detected_and_retried_without_touching_v1():
    store = DryRunStore(_fixture())
    store.dual_write = True
    aggregate = {
        "tenant": "1",
        "tables": {
            "leads": {"1": _lead()},
            "messages": {"10": _fixture()["messages"][0]},
        },
    }
    failure = apply_dual_write(store, aggregate, fail_tables=["messages"], error="connection reset")
    assert failure["status"] == "partial"
    assert failure["written"] == ["leads"]
    assert failure["missing"] == ["messages"]
    assert "messages" not in store.shadow
    retried = retry_missing(store, aggregate, failure)
    assert retried["status"] == "retried"
    assert store.shadow["messages"]["10"]["role"] == "user"
    assert list(store.shadow["leads"]) == ["1"]
    store.assert_v1_unchanged()


def test_schema_invalid_json_is_not_retried_and_not_partially_inserted():
    store = DryRunStore(_fixture())
    store.dual_write = True
    aggregate = {
        "tenant": "1",
        "tables": {"leads": {"1": _lead()}, "messages": {"10": {"id": 10}}},
    }
    failure = apply_dual_write(store, aggregate, fail_tables=["leads"], error="schema_invalid")
    assert failure["retry"] == "reject"
    assert failure["written"] == []
    assert store.shadow == {}
    assert retry_missing(store, aggregate, failure)["status"] == "reject"
    decision, delay = retry_decision("schema_invalid", 0)
    assert decision == "reject"
    assert delay is None
    store.assert_v1_unchanged()


def test_transient_retries_exhaust_at_five_and_block_only_the_read_cut():
    store = DryRunStore(_fixture())
    failure = {"tenant": "1", "kind": "transient", "retry_count": 5, "missing": ["messages"]}
    assert retry_decision("transient", 5) == ("exhausted", None)
    result = retry_missing(store, {"tenant": "1", "tables": {}}, failure)
    assert result["status"] == "exhausted"
    assert "1" in store.read_cut_blocked
    store.assert_v1_unchanged()


def test_rollback_drops_the_shadow_and_leaves_v1():
    store = DryRunStore(_fixture())
    store.dual_write = True
    store.read_source = "v2"
    aggregate = {"tenant": "1", "tables": {"leads": {"1": _lead()}}}
    assert apply_dual_write(store, aggregate)["status"] == "complete"
    assert store.shadow["leads"]["1"]["name"] == "Ada"
    outcome = rollback(store)
    assert outcome == {"read_source": "v1", "dual_write": False, "shadow_tables": 0}
    assert store.shadow == {}
    assert store.v1["leads"][0]["name"] == "Ada"
    store.assert_v1_unchanged()


def test_render_and_live_dsn_are_refused_without_connecting():
    assert_isolated_dsn("postgresql://user:pass@127.0.0.1:5432/dryrun")
    for dsn in (
        "postgresql://user:pass@dpg-abc.render.com:5432/prod",
        "postgresql://user:pass@dpg-abc-a.oregon-postgres.render.com/prod",
    ):
        try:
            assert_isolated_dsn(dsn)
        except IsolationError:
            pass
        else:
            raise AssertionError(dsn)
    live = "postgresql://live.example/prod"
    try:
        assert_isolated_dsn(live, live_database_url=live)
    except IsolationError as exc:
        assert "LIVE_DATABASE_URL" in str(exc)
    else:
        raise AssertionError("live DSN was accepted")
