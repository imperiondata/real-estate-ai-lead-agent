"""Canonical tenant GUC. No database. V1 must not set it."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.migration.tenant_context import TENANT_GUC, set_current_tenant_id

ROOT = Path(__file__).resolve().parents[1]


class _Cursor:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def execute(self, query, params=None) -> None:
        self.calls.append((query, params))


def test_helper_sets_only_current_tenant_id():
    cursor = _Cursor()
    tenant_id = "aaaaaaaa-0000-0000-0000-000000000001"
    set_current_tenant_id(cursor, tenant_id)
    assert TENANT_GUC == "app.current_tenant_id"
    assert cursor.calls == [
        ("SELECT set_config(%s, %s, true)", (TENANT_GUC, tenant_id))
    ]
    assert "app.tenant_id" not in cursor.calls[0][1]


def test_helper_passes_an_invalid_value_through():
    cursor = _Cursor()
    set_current_tenant_id(cursor, "not-a-uuid")
    assert cursor.calls[0][1] == (TENANT_GUC, "not-a-uuid")


def test_helper_does_not_default_a_missing_value():
    cursor = _Cursor()
    for missing in (None, "", "   "):
        with pytest.raises(ValueError):
            set_current_tenant_id(cursor, missing)
    assert cursor.calls == []


def test_v1_paths_do_not_set_the_tenant_guc():
    for relative in ("database.py", "main.py"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "set_current_tenant_id" not in text
        assert "app.current_tenant_id" not in text
        assert "app.tenant_id" not in text
