"""Run the application-process restart drill and write the raw console log.

Local Postgres only. Refuses Render, refuses non-loopback hosts, and refuses any
database other than the throwaway ``v2_process_restart``. It does not read
``LIVE_DATABASE_URL`` and does not touch ``realestate_db``.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.migration.process_restart_drill import run_process_restart_drill  # noqa: E402

LOG_PATH = ROOT / "plans" / "evidence" / "NOV4_PROCESS_RESTART.log"


def main() -> int:
    try:
        lines = run_process_restart_drill()
    except Exception as exc:  # noqa: BLE001 - the log must record the failure
        text = f"PROCESS_RESTART_DRILL_FAIL {type(exc).__name__}: {exc}\n"
        print(text, end="")
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOG_PATH.write_text(text, encoding="utf-8")
        return 1

    text = "\n".join(lines) + "\n"
    print(text, end="")
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(text, encoding="utf-8")
    return 0 if "PROCESS_RESTART_DRILL_PASS" in text else 1


if __name__ == "__main__":
    sys.exit(main())
