"""Dual-write call path. No database.

Proves the injected V2-before-V1 case is selected only by its case name, and
that a non-injected decision upserts V1 before V2.
"""

from __future__ import annotations

import pytest

from app.migration.dry_run import DryRunStore, apply_dual_write
from app.migration.process_restart_worker import (
    fail_tables_for_case,
    production_upsert_order,
)


def _aggregate() -> dict:
    return {
        "tenant": "1",
        "tables": {
            "v1_leads": {1: {"id": 1, "name": "restart-lead"}},
            "v2.leads": {1: {"v1_lead_id": 1, "name": "restart-lead"}},
        },
    }


def test_only_the_injected_case_skips_v1():
    assert fail_tables_for_case("v2_success_v1_failure") == ["v1_leads"]
    assert fail_tables_for_case("v1_success_v2_failure") == ["v2.leads"]
    assert fail_tables_for_case("partial_commit") is None
    for case in ("v1_success_v2_failure", "partial_commit"):
        assert fail_tables_for_case(case) != ["v1_leads"]
    with pytest.raises(ValueError):
        fail_tables_for_case("production")


def test_production_branch_upserts_v1_before_v2():
    store = DryRunStore({"leads": []})
    store.dual_write = True
    decision = apply_dual_write(store, _aggregate())
    order = production_upsert_order(decision["written"])
    assert order == ["v1_leads", "v2.leads"]
    assert order.index("v1_leads") < order.index("v2.leads")

    injected_store = DryRunStore({"leads": []})
    injected_store.dual_write = True
    injected = apply_dual_write(
        injected_store,
        _aggregate(),
        fail_tables=fail_tables_for_case("v2_success_v1_failure"),
        error="injected_crash",
    )
    assert "v1_leads" not in injected["written"]
    assert production_upsert_order(injected["written"]) == ["v2.leads"]
    injected_store.assert_v1_unchanged()
