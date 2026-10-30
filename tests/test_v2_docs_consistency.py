"""Dependency-free checks for the frozen V2 Phase 1 documentation.

These guard the 29 October 2026 status-matrix decisions without importing the
application or touching a database. They are intentionally structural: the
meta-schema parses, the examples obey the booking/stage/prompt rules, and the
three canonical documents agree on the locked decisions.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "Industry_Profile_Schema.json"
PROFILE_DOC = ROOT / "V2_Industry_Profile.md"
MIGRATION_DOC = ROOT / "V2_Migration_and_Security.md"
MATRIX_DOC = ROOT / "plans" / "V2_CONSOLIDATED_STATUS_MATRIX.md"


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _examples() -> dict:
    return {profile["key"]: profile for profile in _load_schema()["examples"]}


def test_meta_schema_and_examples_parse():
    schema = _load_schema()
    assert schema["$schema"].endswith("2020-12/schema")
    assert set(schema["required"]) == {
        "key",
        "version",
        "status",
        "qualification_schema",
        "scoring_rules",
        "dashboard_config",
        "pipeline_stages",
        "base_ai_prompt",
        "overrides",
        "security_boundary",
    }
    assert set(_examples()) == {"real_estate", "education"}


def test_partial_leads_are_valid_but_booking_keys_are_separate():
    for key, profile in _examples().items():
        qualification = profile["qualification_schema"]
        assert qualification["required"] == [], key
        assert qualification["additionalProperties"] is False, key
        for booking_key in qualification["required_for_booking"]:
            assert booking_key in qualification["properties"], (key, booking_key)
        assert "name" not in qualification["properties"], key
        assert "phone" not in qualification["properties"], key


def test_scoring_contract_values():
    real_estate = _examples()["real_estate"]["scoring_rules"]
    assert real_estate["engagement"] == {
        "fields": ["name", "phone", "budget", "location", "property_type", "visit_date"],
        "points_per_field": 16,
        "opt_in_points": 4,
        "cap": 100,
    }
    assert real_estate["temperature"]["hot_min_probability"] == 82
    assert real_estate["temperature"]["warm_min_probability"] == 45
    assert real_estate["temperature"]["full_qualify_floor"] == 88
    assert real_estate["temperature"]["field_floors"] == {"visit_date": 82}
    assert real_estate["manual_review"]["when_confidence_below"] == 75
    assert real_estate["probability"]["temperature_weights"] == {"hot": 60, "warm": 40, "cold": 15}
    assert real_estate["probability"]["cap"] == 98


def test_dashboard_stage_keys_resolve():
    for key, profile in _examples().items():
        stages = {stage["key"] for stage in profile["pipeline_stages"]}
        assert len(stages) == len(profile["pipeline_stages"]), key
        positions = [stage["position"] for stage in profile["pipeline_stages"]]
        assert sorted(positions) == list(range(1, len(positions) + 1)), key
        assert set(profile["dashboard_config"]["kanban"]) == stages, key


def test_prompt_slots_resolve():
    for key, profile in _examples().items():
        properties = set(profile["qualification_schema"]["properties"])
        fields = set(re.findall(r"\{\{field:([a-z_]+)\}\}", profile["base_ai_prompt"]))
        tenants = set(re.findall(r"\{\{tenant:([a-z_]+)\}\}", profile["base_ai_prompt"]))
        assert fields <= properties, (key, fields - properties)
        assert tenants <= {"name"}, (key, tenants)


def test_override_paths_exist_and_ranges_are_bounded():
    for key, profile in _examples().items():
        allowed = profile["overrides"]["allowed"]
        ranges = profile["overrides"]["ranges"]
        assert allowed, key
        for path in allowed:
            node = profile
            for part in path.split("."):
                assert part in node, (key, path)
                node = node[part]
        for path, bounds in ranges.items():
            assert path in allowed, (key, path)
            assert bounds["min"] <= bounds["max"], (key, path)


def test_documents_use_the_option_b_storage_decision():
    profile_text = PROFILE_DOC.read_text(encoding="utf-8")
    migration_text = MIGRATION_DOC.read_text(encoding="utf-8")
    matrix_text = MATRIX_DOC.read_text(encoding="utf-8")

    assert "option B" in profile_text
    assert "v2.industry_profiles" in profile_text
    assert "v2.tenant_configurations" in profile_text
    assert "option B" in migration_text
    assert "v2.industry_profiles" in migration_text
    assert "v2.tenant_configurations" in migration_text
    assert "M-01" in matrix_text and "M-20" in matrix_text


def test_stale_contradictions_are_removed():
    profile_text = PROFILE_DOC.read_text(encoding="utf-8")
    migration_text = MIGRATION_DOC.read_text(encoding="utf-8")

    assert "That is a storage gap." not in profile_text
    assert "does not add a validator library" not in profile_text
    assert "all four decisions" not in migration_text
    assert "accepted all five decisions" in migration_text
    assert "Live database changes remain banned" in migration_text


def test_security_boundary_const_and_rejected_checksum_are_locked():
    schema = _load_schema()
    const = schema["$defs"]["security_boundary"]["const"]
    assert const["locked"] is True
    assert "tenant_id" in const["forbidden"]
    assert "api_key" in const["forbidden"]
    assert "test_mode" in const["forbidden"]
    allowed_enum = schema["$defs"]["overrides"]["properties"]["allowed"]["items"]["enum"]
    assert "tenant_id" not in allowed_enum
    assert "api_key" not in allowed_enum

    migration_text = MIGRATION_DOC.read_text(encoding="utf-8")
    profile_text = PROFILE_DOC.read_text(encoding="utf-8")
    assert "v1_lead_id|name|phone|budget" not in migration_text
    assert "checksum of name, phone, and budget" not in migration_text
    assert "plans/V2_MIGRATION_DRY_RUN.md" in migration_text
    assert "security_boundary" in profile_text
    assert "Publishing a profile cannot change tenant isolation" in profile_text


def test_matrix_has_no_shipped_isolation_claim():
    matrix_text = MATRIX_DOC.read_text(encoding="utf-8")
    assert "No live database changes" in matrix_text
    assert "Target-only" in matrix_text
    assert "no CI workflow" in matrix_text.lower() or "no `.github/workflows`" in matrix_text
