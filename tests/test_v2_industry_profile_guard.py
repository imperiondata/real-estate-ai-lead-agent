"""Proof that a published Industry Profile cannot override security controls.

Dependency-free. No database. The denylist in app.industry.profile_guard is the
source of truth, and Industry_Profile_Schema.json must repeat it as a const.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from app.industry.profile_guard import (
    FORBIDDEN_TOKENS,
    SAFE_OVERRIDE_PATHS,
    SECURITY_BOUNDARY,
    ProfileGuardError,
    allowed_forbidden_intersection,
    assert_override_safe,
    assert_publish_safe,
    assert_schema_lock,
    path_hits_denylist,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "Industry_Profile_Schema.json"


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _examples() -> dict:
    return {profile["key"]: profile for profile in _schema()["examples"]}


def test_schema_const_equals_code_denylist():
    schema = _schema()
    assert_schema_lock(schema)
    assert schema["$defs"]["security_boundary"]["const"] == SECURITY_BOUNDARY
    assert schema["$defs"]["security_boundary"]["const"]["forbidden"] == list(FORBIDDEN_TOKENS)
    assert "security_boundary" in schema["required"]


def test_published_examples_are_safe_and_disjoint():
    schema = _schema()
    assert_schema_lock(schema)
    for key, profile in _examples().items():
        assert_publish_safe(profile)
        assert allowed_forbidden_intersection(profile) == set(), key
        assert set(profile["overrides"]["allowed"]) <= set(SAFE_OVERRIDE_PATHS)


def test_each_forbidden_token_is_rejected_as_an_override():
    profile = _examples()["real_estate"]
    for token in FORBIDDEN_TOKENS:
        mutated = copy.deepcopy(profile)
        mutated["overrides"]["allowed"].append(token)
        try:
            assert_publish_safe(mutated)
        except ProfileGuardError as exc:
            assert exc.code in {"forbidden_path", "override_not_allowed"}, token
        else:
            raise AssertionError(f"{token} was accepted")
        assert path_hits_denylist(token) == token


def test_nested_and_aliased_security_paths_are_rejected():
    assert path_hits_denylist("TenantId") == "tenant_id"
    assert path_hits_denylist("current-tenant-id") == "current_tenant_id"
    assert path_hits_denylist("auth.api_key_hash") == "api_key_hash"
    assert path_hits_denylist("security.rls_enabled") == "rls"
    assert path_hits_denylist("server.test_mode") == "test_mode"
    profile = _examples()["real_estate"]
    hostile_paths = [
        "tenant_id",
        "auth.api_key_hash",
        "security.rls_enabled",
        "TenantId",
        "current-tenant-id",
        "server.test_mode",
        "twilio_secret",
        "security_boundary.locked",
    ]
    for path in hostile_paths:
        mutated = copy.deepcopy(profile)
        mutated["overrides"]["allowed"].append(path)
        try:
            assert_override_safe(mutated["overrides"], mutated)
        except ProfileGuardError as exc:
            assert exc.code in {"forbidden_path", "override_not_allowed", "boundary_override"}, path
        else:
            raise AssertionError(path)


def test_shrinking_or_unlocking_the_boundary_fails():
    profile = _examples()["education"]
    shrunk = copy.deepcopy(profile)
    shrunk["security_boundary"] = {
        "locked": True,
        "forbidden": [token for token in FORBIDDEN_TOKENS if token != "tenant_id"],
    }
    try:
        assert_publish_safe(shrunk)
    except ProfileGuardError as exc:
        assert exc.code == "boundary_drift"
    else:
        raise AssertionError("shrunk denylist was accepted")

    unlocked = copy.deepcopy(profile)
    unlocked["security_boundary"] = {**SECURITY_BOUNDARY, "locked": False}
    try:
        assert_publish_safe(unlocked)
    except ProfileGuardError as exc:
        assert exc.code == "boundary_drift"
    else:
        raise AssertionError("unlocked boundary was accepted")


def test_a_security_key_inside_scoring_rules_fails_publish():
    profile = copy.deepcopy(_examples()["real_estate"])
    profile["scoring_rules"]["engagement"]["tenant_id"] = 1
    try:
        assert_publish_safe(profile)
    except ProfileGuardError as exc:
        assert exc.code == "forbidden_path"
    else:
        raise AssertionError("nested tenant_id was accepted")


def test_numeric_override_outside_its_range_fails():
    profile = copy.deepcopy(_examples()["real_estate"])
    profile["overrides"]["ranges"]["scoring_rules.temperature.hot_min_probability"] = {
        "min": 91,
        "max": 95,
    }
    try:
        assert_publish_safe(profile)
    except ProfileGuardError as exc:
        assert exc.code == "range_violation"
    else:
        raise AssertionError("default outside range was accepted")
