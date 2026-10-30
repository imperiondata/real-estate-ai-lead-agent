"""V2 migration dry-run rules.

Full-table reconciliation, partial dual-write detection, and rollback.
No database driver is imported. Nothing here opens a connection, runs DDL,
or reads ``LIVE_DATABASE_URL`` from the environment. A future isolated
Postgres drill must call ``assert_isolated_dsn`` before it connects, and
that drill is not claimed by this module.
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from urllib.parse import urlparse

# Piyush rejected this checksum on 29 October 2026. It is kept only so a test
# can show that reconcile() does not use it.
REJECTED_CHECKSUM_COLUMNS = ("name", "phone", "budget")

SECRET_COLUMNS = frozenset(
    {"hashed_password", "api_key", "twilio_auth_token", "twilio_secret_ref"}
)

# Free-text or payload columns are digested so a change fails parity, but the
# human report lists the primary key and column name only.
REDACT_FROM_REPORT = SECRET_COLUMNS | frozenset(
    {"content", "value", "payload", "action_payload", "error_trace", "settings", "meta_json"}
)

# Every Lead column is classified. identity and reported_only are not digested.
LEAD_COLUMNS = {
    "id": "identity",
    "session_id": "relational",
    "client_id": "identity_map",
    "name": "relational",
    "phone": "relational",
    "budget": "industry_json",
    "location": "industry_json",
    "property_type": "industry_json",
    "intent": "industry_json",
    "score": "relational",
    "visit_date": "industry_json",
    "source": "relational",
    "whatsapp_opt_in": "relational",
    "updated_at": "reported_only",
    "conversion_probability": "relational",
    "expected_closure_days": "relational",
    "lead_temperature": "relational",
    "engagement_score": "relational",
    "budget_alignment_status": "relational",
    "inactivity_penalty": "relational",
    "response_speed_score": "relational",
    "urgency_level": "relational",
    "assigned_agent": "relational",
    "conversion_status": "relational",
    "followup_stage": "relational",
    "best_performing_script": "relational",
    "funnel_stage": "relational",
    "external_crm_id": "relational",
    "crm_sync_status": "relational",
    "crm_resync_pending": "relational",
    "confidence_score": "relational",
    "requires_manual_review": "relational",
    "is_negotiating": "relational",
}

LEAD_DIGEST_COLUMNS = tuple(
    col for col, kind in LEAD_COLUMNS.items() if kind in {"relational", "industry_json"}
)

# V1 tables from V2_Migration_and_Security.md section 1, plus clients and
# webhook_logs. webhook_logs has no tenant column.
TABLES = {
    "clients": {
        "pk": "id",
        "tenant_column": None,
        "digest": (
            "company_name",
            "email",
            "is_api_key_hashed",
            "is_active",
            "twilio_phone_number",
            "twilio_account_sid",
            "subscription_status",
            "stripe_customer_id",
        ),
        "secrets": ("hashed_password", "api_key", "twilio_auth_token"),
        "reported_only": ("created_at", "settings"),
    },
    "sessions": {
        "pk": "id",
        "tenant_column": "client_id",
        "digest": ("follow_up_count", "status"),
        "secrets": (),
        "reported_only": ("created_at", "last_activity_at"),
    },
    "messages": {
        "pk": "id",
        "tenant_column": "client_id",
        "digest": ("session_id", "role", "content"),
        "secrets": (),
        "reported_only": ("timestamp",),
        "parent": ("session_id", "sessions", "id"),
    },
    "leads": {
        "pk": "id",
        "tenant_column": "client_id",
        "digest": LEAD_DIGEST_COLUMNS,
        "secrets": (),
        "reported_only": ("updated_at",),
        "parent": ("session_id", "sessions", "id"),
    },
    "event_logs": {
        "pk": "id",
        "tenant_column": "client_id",
        "digest": ("session_id", "event_type", "action_type", "latency_ms", "agent_type"),
        "secrets": (),
        "reported_only": ("timestamp",),
        "parent": ("session_id", "sessions", "id"),
    },
    "follow_up_states": {
        "pk": "id",
        "tenant_column": "client_id",
        "digest": ("session_id", "follow_up_stage", "follow_up_status", "inactivity_score", "send_retry_count"),
        "secrets": (),
        "reported_only": (
            "last_user_reply_timestamp",
            "last_ai_reply_timestamp",
            "follow_up_sent_at",
            "next_follow_up_at",
        ),
        "parent": ("session_id", "sessions", "id"),
    },
    "dlq_events": {
        "pk": "id",
        "tenant_column": "client_id",
        "digest": ("target_endpoint", "status"),
        "secrets": (),
        "reported_only": ("payload", "error_trace", "created_at"),
        "nullable_tenant": True,
    },
    "agents": {
        "pk": "id",
        "tenant_column": "client_id",
        "digest": (
            "name",
            "phone",
            "email",
            "is_manager",
            "is_director",
            "locations",
            "speciality",
            "deal_size",
            "lead_type",
            "conversion_rate",
            "response_speed_score",
            "active_leads",
        ),
        "secrets": (),
        "reported_only": (),
    },
    "approval_requests": {
        "pk": "id",
        "tenant_column": "client_id",
        "digest": ("entity_id", "action_type", "status", "requested_by", "resolved_by", "reason"),
        "secrets": (),
        "reported_only": ("action_payload", "created_at", "resolved_at", "correlation_id"),
    },
    "agent_learning": {
        "pk": "id",
        "tenant_column": "client_id",
        "digest": ("agent_name", "wins", "losses"),
        "secrets": (),
        "reported_only": (),
    },
    "notification_logs": {
        "pk": "id",
        "tenant_column": "client_id",
        "digest": (
            "lead_id",
            "assigned_agent",
            "status",
            "reason",
            "severity",
            "twilio_message_sid",
            "twilio_delivery_status",
        ),
        "secrets": (),
        "reported_only": ("sent_at", "escalate_at", "correlation_id"),
        "parent": ("lead_id", "leads", "id"),
    },
    "lead_memories": {
        "pk": "id",
        "tenant_column": "client_id",
        "digest": ("lead_id", "session_id", "key", "value", "memory_type"),
        "secrets": (),
        "reported_only": ("created_at",),
        "parent": ("lead_id", "leads", "id"),
    },
    "inventory_units": {
        "pk": "id",
        "tenant_column": "client_id",
        "digest": (
            "project_name",
            "tower",
            "unit_code",
            "bhk",
            "location",
            "list_price",
            "status",
            "carpet_sqft",
        ),
        "secrets": (),
        "reported_only": ("meta_json", "created_at"),
    },
    "pricing_rules": {
        "pk": "id",
        "tenant_column": "client_id",
        "digest": ("location", "bhk", "min_budget", "max_budget", "list_price", "notes"),
        "secrets": (),
        "reported_only": ("created_at",),
    },
    "agent_tasks": {
        "pk": "id",
        "tenant_column": "client_id",
        "digest": ("lead_id", "title", "description", "status", "assignee", "source"),
        "secrets": (),
        "reported_only": ("meta_json", "created_at", "updated_at"),
        "parent": ("lead_id", "leads", "id"),
        "nullable_parent": True,
    },
    "webhook_logs": {
        "pk": "message_sid",
        "tenant_column": None,
        "global": True,
        "digest": (),
        "secrets": (),
        "reported_only": ("processed_at",),
    },
}

RETRY_CAP = 5


class IsolationError(ValueError):
    pass


class DryRunStore:
    """In-memory V1 fixture plus a shadow namespace. Never a database."""

    def __init__(self, v1: dict) -> None:
        self.v1 = deepcopy(v1)
        self._v1_snapshot = deepcopy(v1)
        self.shadow: dict = {}
        self.dual_write = False
        self.read_source = "v1"
        self.failures: list[dict] = []
        self.read_cut_blocked: set[str] = set()

    def assert_v1_unchanged(self) -> None:
        if self.v1 != self._v1_snapshot:
            raise AssertionError("V1 fixture was rewritten")


def _host_of(dsn: str) -> str:
    parsed = urlparse(dsn)
    return (parsed.hostname or "").lower()


def assert_isolated_dsn(dsn: str, *, live_database_url: str | None = None) -> None:
    """Refuse Render and any DSN that is the live database URL.

    Passing this check does not connect. The dry-run procedure does not call it
    in order to open a socket. A later runner must call it and then still
    refuse to proceed unless the host is local.
    """
    if dsn is None or not str(dsn).strip():
        raise IsolationError("refusing empty DSN")
    if live_database_url and dsn == live_database_url:
        raise IsolationError("refusing LIVE_DATABASE_URL")
    lowered = str(dsn).lower()
    host = _host_of(str(dsn))
    if "render.com" in lowered or host.endswith("render.com") or host.startswith("dpg-"):
        raise IsolationError("refusing Render host")


def _cell(row: dict, column: str, *, secret: bool) -> str:
    value = row.get(column)
    if value is None:
        return ""
    if secret:
        return hashlib.sha256(str(value).encode("utf-8")).hexdigest()
    return str(value)


def row_digest(rows: list[dict], pk: str, columns: tuple[str, ...], secrets: tuple[str, ...] = ()) -> str:
    secret_set = set(secrets)
    lines = []
    for row in sorted(rows, key=lambda item: str(item.get(pk, ""))):
        parts = ["" if row.get(pk) is None else str(row.get(pk))]
        for column in columns:
            parts.append(_cell(row, column, secret=column in secret_set))
        for column in secrets:
            if column not in columns:
                parts.append(_cell(row, column, secret=True))
        lines.append("|".join(parts))
    payload = "\n".join(lines)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def rejected_selected_field_checksum(rows: list[dict], pk: str = "id") -> str:
    """The 29 October checksum Piyush rejected. reconcile() must not call this."""
    return row_digest(rows, pk, REJECTED_CHECKSUM_COLUMNS)


def _rows_for_tenant(rows: list[dict], spec: dict, tenant_id) -> list[dict]:
    if spec.get("global"):
        return list(rows)
    column = spec.get("tenant_column")
    if column is None:
        return [row for row in rows if str(row.get(spec["pk"])) == str(tenant_id)]
    selected = []
    for row in rows:
        owner = row.get(column)
        if owner is None and spec.get("nullable_tenant"):
            continue
        if str(owner) == str(tenant_id):
            selected.append(row)
    return selected


def reconcile_table(v1_rows: list[dict], v2_rows: list[dict], spec: dict) -> dict:
    pk = spec["pk"]
    v1_ids = {row.get(pk) for row in v1_rows}
    v2_ids = {row.get(pk) for row in v2_rows}
    missing = sorted((v1_ids - v2_ids), key=lambda item: str(item))
    extra = sorted((v2_ids - v1_ids), key=lambda item: str(item))
    digest_columns = tuple(spec.get("digest") or ())
    secrets = tuple(spec.get("secrets") or ())
    v1_digest = row_digest(v1_rows, pk, digest_columns, secrets)
    v2_digest = row_digest(v2_rows, pk, digest_columns, secrets)
    column_mismatches = []
    v2_by_pk = {row.get(pk): row for row in v2_rows}
    comparable = [col for col in digest_columns if col not in REDACT_FROM_REPORT]
    comparable += [col for col in secrets if col not in comparable]
    for row in v1_rows:
        other = v2_by_pk.get(row.get(pk))
        if other is None:
            continue
        for column in list(digest_columns) + list(secrets):
            left = _cell(row, column, secret=column in secrets or column in SECRET_COLUMNS)
            right = _cell(other, column, secret=column in secrets or column in SECRET_COLUMNS)
            if left != right:
                sample = {
                    "pk": row.get(pk),
                    "column": column,
                }
                if column not in REDACT_FROM_REPORT and column not in secrets:
                    sample["v1"] = row.get(column)
                    sample["v2"] = other.get(column)
                column_mismatches.append(sample)
    ok = not missing and not extra and v1_digest == v2_digest and not column_mismatches
    return {
        "ok": ok,
        "v1_count": len(v1_rows),
        "v2_count": len(v2_rows),
        "missing": missing,
        "extra": extra,
        "v1_digest": v1_digest,
        "v2_digest": v2_digest,
        "column_mismatches": column_mismatches,
    }


def reconcile_all(v1: dict, v2: dict, *, tenant_id) -> dict:
    """Per-tenant, per-table parity over every mapped column. Not name/phone/budget."""
    tables = {}
    ok = True
    for name, spec in TABLES.items():
        if spec.get("global"):
            continue
        left = _rows_for_tenant(list(v1.get(name) or []), spec, tenant_id)
        right = _rows_for_tenant(list(v2.get(name) or []), spec, tenant_id)
        result = reconcile_table(left, right, spec)
        tables[name] = result
        if not result["ok"]:
            ok = False
    global_spec = TABLES["webhook_logs"]
    webhook = reconcile_table(
        list(v1.get("webhook_logs") or []),
        list(v2.get("webhook_logs") or []),
        global_spec,
    )
    tables["webhook_logs"] = webhook
    if not webhook["ok"]:
        ok = False
    orphans = orphan_ids(v1)
    if orphans:
        ok = False
    return {"ok": ok, "tenant_id": tenant_id, "tables": tables, "orphans": orphans}


def orphan_ids(v1: dict) -> list[dict]:
    found = []
    for name, spec in TABLES.items():
        parent = spec.get("parent")
        if not parent:
            continue
        child_key, parent_table, parent_pk = parent
        parent_ids = {row.get(parent_pk) for row in v1.get(parent_table) or []}
        for row in v1.get(name) or []:
            ref = row.get(child_key)
            if ref is None and spec.get("nullable_parent"):
                continue
            if ref not in parent_ids:
                found.append({"table": name, "pk": row.get(spec["pk"]), "missing_parent": ref})
    null_dlq = [
        row.get("id")
        for row in v1.get("dlq_events") or []
        if row.get("client_id") is None
    ]
    for pk in null_dlq:
        found.append({"table": "dlq_events", "pk": pk, "missing_parent": None, "note": "null client_id reported, not assigned"})
    return found


def classify_failure(error: str) -> str:
    normalized = (error or "").lower()
    if normalized in {"schema_invalid", "invalid_json", "unknown_key", "wrong_type"}:
        return "schema_invalid"
    return "transient"


def retry_decision(kind: str, retry_count: int) -> tuple[str, int | None]:
    """Schema-invalid is not retried. Transient retries cap at 5.

    Delays are 1, 2, 4, 8, 16 minutes. This is the shadow upsert policy, not
    the follow-up send backoff.
    """
    if kind == "schema_invalid":
        return ("reject", None)
    if retry_count >= RETRY_CAP:
        return ("exhausted", None)
    return ("retry", 2**retry_count)


def detect_partial(expected: set[str], written: set[str]) -> dict:
    missing = expected - written
    if written and missing:
        status = "partial"
    elif missing and not written:
        status = "failed"
    else:
        status = "complete"
    return {
        "status": status,
        "written": sorted(written),
        "missing": sorted(missing),
    }


def apply_dual_write(store: DryRunStore, aggregate: dict, *, fail_tables: Iterable[str] | None = None, error: str = "transient") -> dict:
    """Write the shadow aggregate. V1 is never rolled back and never blocked."""
    store.assert_v1_unchanged()
    if not store.dual_write:
        return {"status": "skipped", "reason": "dual_write_off"}
    expected = set(aggregate["tables"])
    kind = classify_failure(error) if fail_tables else "transient"
    # An invalid industry document is not partially inserted.
    if fail_tables and kind == "schema_invalid":
        record = {
            "tenant": str(aggregate["tenant"]),
            "status": "failed",
            "written": [],
            "missing": sorted(expected),
            "error": error,
            "kind": "schema_invalid",
            "retry_count": 0,
            "retry": "reject",
        }
        store.failures.append(record)
        store.read_cut_blocked.add(record["tenant"])
        store.assert_v1_unchanged()
        return record

    written: set[str] = set()
    blocked = set(fail_tables or [])
    for table, rows in aggregate["tables"].items():
        if table in blocked:
            continue
        bucket = store.shadow.setdefault(table, {})
        for pk, row in rows.items():
            bucket[pk] = deepcopy(row)
        written.add(table)
    partial = detect_partial(expected, written)
    if partial["status"] == "complete":
        store.assert_v1_unchanged()
        return {"status": "complete", "written": partial["written"]}
    record = {
        "tenant": str(aggregate["tenant"]),
        "status": partial["status"],
        "written": partial["written"],
        "missing": partial["missing"],
        "error": error,
        "kind": "transient",
        "retry_count": 0,
    }
    store.failures.append(record)
    store.assert_v1_unchanged()
    return record


def retry_missing(store: DryRunStore, aggregate: dict, failure: dict) -> dict:
    """Idempotent upsert of the missing tables only. Does not insert a second parent."""
    decision, delay = retry_decision(failure["kind"], failure["retry_count"])
    if decision == "exhausted":
        store.read_cut_blocked.add(str(failure["tenant"]))
        store.assert_v1_unchanged()
        return {"status": "exhausted"}
    if decision == "reject":
        store.read_cut_blocked.add(str(failure["tenant"]))
        store.assert_v1_unchanged()
        return {"status": "reject"}
    for table in failure["missing"]:
        bucket = store.shadow.setdefault(table, {})
        for pk, row in aggregate["tables"][table].items():
            bucket[pk] = deepcopy(row)
    failure["retry_count"] += 1
    failure["status"] = "retried"
    failure["missing"] = []
    store.assert_v1_unchanged()
    return {"status": "retried", "delay_minutes": delay, "retry_count": failure["retry_count"]}


def rollback(store: DryRunStore) -> dict:
    """Turn dual-write off and drop the shadow namespace. V1 is not rewritten.

    Valid before the read cut, and after the read cut while V1 writes are still
    on. Stopping V1 writes is not this package.
    """
    store.dual_write = False
    store.read_source = "v1"
    store.shadow.clear()
    store.failures.clear()
    store.read_cut_blocked.clear()
    store.assert_v1_unchanged()
    return {
        "read_source": store.read_source,
        "dual_write": store.dual_write,
        "shadow_tables": len(store.shadow),
    }
