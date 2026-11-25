"""Alias for the post-cutover rollback drill.

The canonical CLI is ``scripts/run_v2_post_cutover_rollback_drill.py``. This
shim keeps the plan's ``python scripts/prove_v2_post_cutover_rollback.py``
command working without importing the ``scripts`` directory as a package.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.migration.post_cutover_rollback_drill import (  # noqa: E402
    run_post_cutover_rollback_drill,
)

LOG_PATH = ROOT / "plans" / "evidence" / "POST_CUTOVER_ROLLBACK.log"


def main() -> int:
    try:
        lines = run_post_cutover_rollback_drill()
    except Exception as exc:  # noqa: BLE001 - the log must record the failure
        text = f"POST_CUTOVER_ROLLBACK_FAIL {type(exc).__name__}: {exc}\n"
        print(text, end="")
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOG_PATH.write_text(text, encoding="utf-8")
        return 1

    text = "\n".join(lines) + "\n"
    print(text, end="")
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(text, encoding="utf-8")
    return 0 if "POST_CUTOVER_ROLLBACK_PASS" in text else 1


if __name__ == "__main__":
    sys.exit(main())
