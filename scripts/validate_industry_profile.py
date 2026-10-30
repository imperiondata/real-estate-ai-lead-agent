"""Prove the Industry Profile publish lock. No database. No network.

Prints INDUSTRY_PROFILE_GUARD_OK when both examples publish cleanly and the
schema const equals the code denylist. Exit 1 otherwise.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.industry.profile_guard import (  # noqa: E402
    assert_publish_safe,
    assert_schema_lock,
)


def main() -> int:
    path = Path(__file__).resolve().parent.parent / "Industry_Profile_Schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    try:
        assert_schema_lock(schema)
        for example in schema["examples"]:
            assert_publish_safe(example)
    except Exception as exc:
        print(f"INDUSTRY_PROFILE_GUARD_FAIL {exc}")
        return 1
    print("INDUSTRY_PROFILE_GUARD_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
