"""Runtime loader for a published Industry Profile.

Reads the matching ``(key, version)`` entry from the ``examples`` array in
``Industry_Profile_Schema.json``. This module does not open a database and does
not read tenant rows. Tenant overrides are passed in by the caller and are
validated against the profile's declared ``overrides`` contract.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.industry.profile_guard import (
    ProfileGuardError,
    assert_publish_safe,
    validate_override_value,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "Industry_Profile_Schema.json"

HOT_PATH = "scoring_rules.temperature.hot_min_probability"
WARM_PATH = "scoring_rules.temperature.warm_min_probability"


def load_schema(path: Path = SCHEMA_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_profile(key: str = "real_estate", version: int = 1, *, schema: dict | None = None) -> dict:
    """Return the published profile document for ``(key, version)``."""
    document = schema if schema is not None else load_schema()
    for profile in document.get("examples", []):
        if profile.get("key") == key and profile.get("version") == version:
            assert_publish_safe(profile)
            return profile
    raise ProfileGuardError("profile_not_found", f"{key}/{version}")


def _get(document: dict, path: str) -> Any:
    node: Any = document
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise ProfileGuardError("override_missing", path)
        node = node[part]
    return node


def resolve_threshold(
    profile: dict,
    path: str,
    tenant_override: Any = None,
    *,
    strict: bool = False,
) -> Any:
    """Resolve a threshold from the profile, honoring a valid tenant override.

    No override means the published default. An invalid override is rejected;
    with ``strict=False`` (the engine default) it falls back to the published
    default so a bad tenant value cannot change the score.
    """
    default = _get(profile, path)
    if tenant_override is None:
        return default
    try:
        return validate_override_value(profile, path, tenant_override)
    except ProfileGuardError:
        if strict:
            raise
        return default


def classify_temperature(probability: int, hot_min: int, warm_min: int) -> str:
    if probability >= hot_min:
        return "hot"
    if probability >= warm_min:
        return "warm"
    return "cold"
