"""Run the isolated V2 agency-isolation drill and write the raw console log.

Local Postgres only. Refuses Render, refuses non-loopback hosts, and refuses any
database other than ``v2_isolation_drill``. It does not read
``LIVE_DATABASE_URL`` as a connection target and does not touch ``realestate_db``.

Prints the raw lines to stdout and writes the same text to
``plans/evidence/ISOLATION_DRILL.log``.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.migration.isolation_drill import run_isolation_drill  # noqa: E402

LOG_PATH = ROOT / "plans" / "evidence" / "ISOLATION_DRILL.log"


def main() -> int:
    try:
        lines = run_isolation_drill()
    except Exception as exc:  # noqa: BLE001 - the log must record the failure
        text = f"ISOLATION_DRILL_FAIL {type(exc).__name__}: {exc}\n"
        print(text, end="")
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOG_PATH.write_text(text, encoding="utf-8")
        return 1

    text = "\n".join(lines) + "\n"
    print(text, end="")
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(text, encoding="utf-8")
    return 0 if "ISOLATION_DRILL_PASS" in text else 1


if __name__ == "__main__":
    sys.exit(main())
