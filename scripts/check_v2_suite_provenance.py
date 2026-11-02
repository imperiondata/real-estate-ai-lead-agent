"""Fail unless the 27 V2 tests passed inside one pytest JUnit report.

The reliability test is extra. It does not replace any of the 27.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REQUIRED = (
    "tests/test_v2_industry_profile_guard.py::test_schema_const_equals_code_denylist",
    "tests/test_v2_industry_profile_guard.py::test_published_examples_are_safe_and_disjoint",
    "tests/test_v2_industry_profile_guard.py::test_each_forbidden_token_is_rejected_as_an_override",
    "tests/test_v2_industry_profile_guard.py::test_nested_and_aliased_security_paths_are_rejected",
    "tests/test_v2_industry_profile_guard.py::test_shrinking_or_unlocking_the_boundary_fails",
    "tests/test_v2_industry_profile_guard.py::test_a_security_key_inside_scoring_rules_fails_publish",
    "tests/test_v2_industry_profile_guard.py::test_numeric_override_outside_its_range_fails",
    "tests/test_v2_docs_consistency.py::test_meta_schema_and_examples_parse",
    "tests/test_v2_docs_consistency.py::test_partial_leads_are_valid_but_booking_keys_are_separate",
    "tests/test_v2_docs_consistency.py::test_scoring_contract_values",
    "tests/test_v2_docs_consistency.py::test_dashboard_stage_keys_resolve",
    "tests/test_v2_docs_consistency.py::test_prompt_slots_resolve",
    "tests/test_v2_docs_consistency.py::test_override_paths_exist_and_ranges_are_bounded",
    "tests/test_v2_docs_consistency.py::test_documents_use_the_option_b_storage_decision",
    "tests/test_v2_docs_consistency.py::test_stale_contradictions_are_removed",
    "tests/test_v2_docs_consistency.py::test_security_boundary_const_and_rejected_checksum_are_locked",
    "tests/test_v2_docs_consistency.py::test_matrix_has_no_shipped_isolation_claim",
    "tests/test_v2_migration_dry_run.py::test_module_does_not_import_a_database",
    "tests/test_v2_migration_dry_run.py::test_every_v1_table_and_every_lead_column_is_classified",
    "tests/test_v2_migration_dry_run.py::test_a_non_selected_column_mismatch_fails_parity",
    "tests/test_v2_migration_dry_run.py::test_secret_values_are_not_copied_into_the_report",
    "tests/test_v2_migration_dry_run.py::test_partial_dual_write_is_detected_and_retried_without_touching_v1",
    "tests/test_v2_migration_dry_run.py::test_schema_invalid_json_is_not_retried_and_not_partially_inserted",
    "tests/test_v2_migration_dry_run.py::test_transient_retries_exhaust_at_five_and_block_only_the_read_cut",
    "tests/test_v2_migration_dry_run.py::test_rollback_drops_the_shadow_and_leaves_v1",
    "tests/test_v2_migration_dry_run.py::test_render_and_live_dsn_are_refused_without_connecting",
    "tests/test_v2_agency_isolation.py::test_agency_isolation_drill_passes_and_cleans_up",
)


def _nodeid(case: ET.Element) -> str:
    classname = case.get("classname") or ""
    name = case.get("name") or ""
    file_name = classname.replace(".", "/") + ".py"
    if file_name.startswith("tests/"):
        return f"{file_name}::{name}"
    return f"{classname}::{name}"


def main(path: str) -> int:
    root = ET.parse(path).getroot()
    passed = set()
    failed = set()
    for case in root.iter("testcase"):
        nodeid = _nodeid(case)
        if case.find("failure") is not None or case.find("error") is not None:
            failed.add(nodeid)
        elif case.find("skipped") is None:
            passed.add(nodeid)
    missing = [item for item in REQUIRED if item not in passed]
    print(f"V2_PROVENANCE required=27 passed_in_report={len(passed & set(REQUIRED))}")
    if missing or any(item in failed for item in REQUIRED):
        print("V2_PROVENANCE_FAIL")
        for item in missing:
            print(f"missing {item}")
        for item in REQUIRED:
            if item in failed:
                print(f"failed {item}")
        return 1
    print("V2_PROVENANCE_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "pytest-report.xml"))
