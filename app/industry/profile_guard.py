"""Publish-time lock for Industry Profile overrides.

Publishing a profile must not be able to change tenant isolation, API auth,
or server-side security controls. The denylist in this module is the source
of truth. ``Industry_Profile_Schema.json`` repeats it as a const. A publish
that shrinks, deletes, or overrides that const is rejected.

This module does not open a database and does not load a profile into the
live engine.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

_CAMEL = re.compile(r"([a-z0-9])([A-Z])")

# Closed set. A tenant override may name only these leaves.
SAFE_OVERRIDE_PATHS = (
    "scoring_rules.temperature.hot_min_probability",
    "scoring_rules.temperature.warm_min_probability",
    "scoring_rules.manual_review.when_confidence_below",
    "dashboard_config.card_fields",
    "dashboard_config.filters",
    "dashboard_config.badges",
)

NUMERIC_OVERRIDE_PATHS = frozenset(
    {
        "scoring_rules.temperature.hot_min_probability",
        "scoring_rules.temperature.warm_min_probability",
        "scoring_rules.manual_review.when_confidence_below",
    }
)

# Grouped so a review can see the three controls Piyush locked.
# The published const is the sorted union, not a prose list.
FORBIDDEN_GROUPS = {
    "tenant_isolation": (
        "agency_id",
        "client_id",
        "current_tenant_id",
        "membership",
        "rls",
        "tenant_id",
    ),
    "api_auth": (
        "admin_key",
        "api_key",
        "api_key_hash",
        "hashed_password",
        "jwt",
        "twilio_auth_token",
        "twilio_secret",
    ),
    "server_controls": (
        "bypass",
        "claim_check",
        "database_url",
        "dlq",
        "test_mode",
        "webhook_signature",
    ),
}

FORBIDDEN_TOKENS = tuple(
    sorted({token for group in FORBIDDEN_GROUPS.values() for token in group})
)

SECURITY_BOUNDARY = {
    "locked": True,
    "forbidden": list(FORBIDDEN_TOKENS),
}


class ProfileGuardError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code


def normalize_segment(segment: str) -> str:
    text = _CAMEL.sub(r"\1_\2", segment)
    text = text.replace("-", "_").replace(".", "_").replace(" ", "_").lower()
    text = re.sub(r"[^a-z0-9_]", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text


def path_hits_denylist(path: str) -> str | None:
    """Return the longest forbidden token a path normalizes onto, or None."""
    best: str | None = None
    for raw in str(path).split("."):
        if not raw:
            continue
        parts = [part for part in normalize_segment(raw).split("_") if part]
        for token in FORBIDDEN_TOKENS:
            token_parts = token.split("_")
            width = len(token_parts)
            if width == 0 or width > len(parts):
                continue
            for index in range(len(parts) - width + 1):
                if parts[index : index + width] == token_parts:
                    if best is None or len(token) > len(best):
                        best = token
    return best


def _lookup(document: dict, path: str) -> Any:
    node: Any = document
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise ProfileGuardError("override_missing", path)
        node = node[part]
    return node


def _iter_key_paths(node: Any, prefix: str = "") -> Iterable[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield path
            if path == "security_boundary":
                # The forbidden list is the declaration of the tokens, not an
                # override. Walk its keys only.
                if isinstance(value, dict):
                    for child in value:
                        yield f"{path}.{child}"
                continue
            yield from _iter_key_paths(value, path)
    elif isinstance(node, list):
        for item in node:
            if isinstance(item, (dict, list)):
                yield from _iter_key_paths(item, prefix)


def assert_schema_lock(schema: dict) -> None:
    try:
        const = schema["$defs"]["security_boundary"]["const"]
    except (KeyError, TypeError) as exc:
        raise ProfileGuardError("schema_drift", "security_boundary const missing") from exc
    if const != SECURITY_BOUNDARY:
        raise ProfileGuardError(
            "schema_drift",
            "schema const does not equal the code denylist",
        )
    allowed_enum = schema["$defs"]["overrides"]["properties"]["allowed"]["items"]["enum"]
    if list(allowed_enum) != list(SAFE_OVERRIDE_PATHS):
        raise ProfileGuardError("schema_drift", "overrides.allowed enum drifted")


def assert_publish_safe(document: dict) -> None:
    if not isinstance(document, dict):
        raise ProfileGuardError("boundary_missing", "profile is not an object")
    boundary = document.get("security_boundary")
    if boundary != SECURITY_BOUNDARY:
        if not isinstance(boundary, dict) or "forbidden" not in boundary:
            raise ProfileGuardError("boundary_missing", "security_boundary const missing")
        published = set(boundary.get("forbidden") or [])
        required = set(FORBIDDEN_TOKENS)
        if boundary.get("locked") is not True or not required <= published:
            raise ProfileGuardError(
                "boundary_drift",
                "publishing cannot shrink or unlock security_boundary",
            )
        raise ProfileGuardError("boundary_drift", "security_boundary is not the locked const")

    for path in _iter_key_paths(document):
        if path == "security_boundary" or path.startswith("security_boundary."):
            continue
        hit = path_hits_denylist(path)
        if hit:
            raise ProfileGuardError("forbidden_path", f"{path} hits {hit}")

    overrides = document.get("overrides")
    if not isinstance(overrides, dict):
        raise ProfileGuardError("override_missing", "overrides missing")
    assert_override_safe(overrides, document)


def assert_override_safe(overrides: dict, document: dict) -> None:
    if set(overrides) - {"allowed", "ranges"}:
        raise ProfileGuardError("boundary_override", "overrides has an unknown key")
    allowed = overrides.get("allowed")
    ranges = overrides.get("ranges")
    if not isinstance(allowed, list) or not isinstance(ranges, dict):
        raise ProfileGuardError("override_missing", "overrides.allowed or ranges missing")

    allowed_set = set(allowed)
    forbidden_hits: set[str] = set()
    for path in allowed:
        if path == "security_boundary" or str(path).startswith("security_boundary."):
            raise ProfileGuardError("boundary_override", path)
        if path not in SAFE_OVERRIDE_PATHS:
            raise ProfileGuardError("override_not_allowed", str(path))
        hit = path_hits_denylist(str(path))
        if hit:
            forbidden_hits.add(str(path))
            raise ProfileGuardError("forbidden_path", f"{path} hits {hit}")
        _lookup(document, str(path))

    if forbidden_hits:
        raise ProfileGuardError("forbidden_path", "allowed intersects the denylist")

    for path, bounds in ranges.items():
        if path_hits_denylist(str(path)):
            raise ProfileGuardError("forbidden_path", str(path))
        if path not in allowed_set:
            raise ProfileGuardError("range_violation", f"{path} is not an allowed override")
        if not isinstance(bounds, dict) or "min" not in bounds or "max" not in bounds:
            raise ProfileGuardError("range_violation", str(path))
        if bounds["min"] > bounds["max"]:
            raise ProfileGuardError("range_violation", str(path))
        if path in NUMERIC_OVERRIDE_PATHS:
            default = _lookup(document, str(path))
            if not isinstance(default, (int, float)) or isinstance(default, bool):
                raise ProfileGuardError("range_violation", f"{path} default is not numeric")
            if not bounds["min"] <= default <= bounds["max"]:
                raise ProfileGuardError("range_violation", f"{path} default is outside its range")

    for path in allowed:
        if path in NUMERIC_OVERRIDE_PATHS and path not in ranges:
            raise ProfileGuardError("range_violation", f"{path} is numeric and has no range")


def allowed_forbidden_intersection(document: dict) -> set[str]:
    hits = set()
    for path in document.get("overrides", {}).get("allowed", []):
        if path_hits_denylist(str(path)):
            hits.add(str(path))
    return hits
