"""Live DLQ follow-up concurrency proof. Local Postgres only. No Twilio. No Render."""
from __future__ import annotations

import logging
import sys
import threading
import uuid
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import event, text
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal
from dlq_replay import process_ml_followup
from models import Client, DLQEvent, EventLog, Message, Session as SessionModel

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class _IntegrityCapture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


def _refuse_nonlocal() -> None:
    url = settings.DATABASE_URL or ""
    if not url.startswith("postgres"):
        print("Refusing proof: DATABASE_URL is not local postgres.")
        sys.exit(1)
    try:
        host = urlparse(url).hostname
    except Exception:
        host = None
    if host not in _LOCAL_HOSTS:
        print("Refusing proof: DATABASE_URL is not a local postgres host.")
        sys.exit(1)


def _payload(session_id: str) -> dict:
    return {
        "session_id": session_id,
        "stage": "Day 0",
        "lead_data": {
            "name": "Proof",
            "location": "Wakad",
            "budget": "5000000",
            "property_type": "2bhk",
        },
    }


def _ensure_client_columns() -> None:
    db = SessionLocal()
    try:
        db.execute(text(
            "ALTER TABLE clients ADD COLUMN IF NOT EXISTS is_api_key_hashed BOOLEAN DEFAULT FALSE"
        ))
        db.execute(text(
            "ALTER TABLE clients ADD COLUMN IF NOT EXISTS twilio_phone_number VARCHAR"
        ))
        db.execute(text(
            "ALTER TABLE clients ADD COLUMN IF NOT EXISTS twilio_auth_token VARCHAR"
        ))
        db.execute(text(
            "ALTER TABLE clients ADD COLUMN IF NOT EXISTS twilio_account_sid VARCHAR"
        ))
        db.commit()
    finally:
        db.close()


def _seed(tag: str) -> tuple[int, str, int]:
    db = SessionLocal()
    try:
        token = uuid.uuid4().hex
        client = Client(
            company_name=f"DLQ Proof {tag}",
            email=f"dlq-proof-{tag}-{token}@local.test",
            hashed_password="not-a-login",
            api_key=f"dlq-proof-{tag}-{token}",
            is_api_key_hashed=False,
            is_active=True,
        )
        db.add(client)
        db.commit()
        db.refresh(client)
        session_id = f"dlq-proof-{tag}-{token}"
        db.add(SessionModel(id=session_id, client_id=client.id))
        row = DLQEvent(
            client_id=client.id,
            target_endpoint="ml_followup_scheduler",
            payload=_payload(session_id),
            error_trace="proof",
            status="pending",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return client.id, session_id, row.id
    finally:
        db.close()


def _cleanup(client_id: int, session_id: str, event_id: int) -> None:
    db = SessionLocal()
    try:
        db.query(Message).filter(Message.session_id == session_id).delete(synchronize_session=False)
        db.query(EventLog).filter(EventLog.session_id == session_id).delete(synchronize_session=False)
        db.query(DLQEvent).filter(DLQEvent.id == event_id).delete(synchronize_session=False)
        db.query(SessionModel).filter(SessionModel.id == session_id).delete(synchronize_session=False)
        db.query(Client).filter(Client.id == client_id).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _read_row(event_id: int) -> tuple[str | None, str | None]:
    db = SessionLocal()
    try:
        row = db.query(DLQEvent).filter(DLQEvent.id == event_id).one()
        return row.status, row.error_trace
    finally:
        db.close()


def _fail(message: str) -> None:
    print(f"DLQ_PROOF_FAIL {message}")
    sys.exit(1)


def _prove_race() -> None:
    client_id, session_id, event_id = _seed("race")
    sends: list[str] = []
    results: dict[str, bool] = {}
    lock = threading.Lock()
    barrier = threading.Barrier(2)
    payload = _payload(session_id)

    def worker(worker_id: str) -> None:
        db = SessionLocal()

        def sender(**kwargs):
            with lock:
                sends.append(worker_id)

        try:
            barrier.wait()
            results[worker_id] = process_ml_followup(
                payload,
                db,
                event_client_id=client_id,
                event_id=event_id,
                worker_id=worker_id,
                sender=sender,
            )
        finally:
            db.close()

    try:
        threads = [
            threading.Thread(target=worker, args=("worker_1",)),
            threading.Thread(target=worker, args=("worker_2",)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        status, trace = _read_row(event_id)
        winners = [name for name, ok in results.items() if ok]
        print("CASE race")
        print(f"worker_1_returned={results.get('worker_1')}")
        print(f"worker_2_returned={results.get('worker_2')}")
        print(f"error_trace={trace}")
        print(f"external_actions={len(sends)}")
        print(f"sender={sends[0] if sends else None}")
        print(f"status={status}")
        if len(winners) != 1:
            _fail(f"expected one winner, got {winners}")
        winner = winners[0]
        if trace != f"claimed:{winner}":
            _fail(f"claim receipt {trace} does not name {winner}")
        if sends != [winner]:
            _fail(f"sender calls {sends} do not match {winner}")
        if status != "resolved":
            _fail(f"status is {status}, expected resolved")
        print(f"winner={winner}")
    finally:
        _cleanup(client_id, session_id, event_id)


def _arm_poison(db: Session, session_id: str) -> None:
    state = {"n": 0}

    def _poison(session: Session) -> None:
        if session is not db:
            return
        state["n"] += 1
        if state["n"] != 2:
            return
        session.add(EventLog(
            session_id=session_id,
            client_id=2_000_000_000,
            event_type="tracking",
            action_type="proof_fault",
        ))
        session.flush()

    event.listen(db, "before_commit", _poison)


def _prove_db_failure(capture: _IntegrityCapture) -> None:
    client_id, session_id, event_id = _seed("fail")
    sends: list[str] = []
    payload = _payload(session_id)
    db = SessionLocal()
    _arm_poison(db, session_id)

    def sender(**kwargs):
        sends.append("worker_fail")

    try:
        returned = process_ml_followup(
            payload,
            db,
            event_client_id=client_id,
            event_id=event_id,
            worker_id="worker_fail",
            sender=sender,
        )
    finally:
        db.close()

    status, trace = _read_row(event_id)
    print("CASE db_failure")
    print(f"first_call_returned={returned}")
    print(f"error_trace={trace}")
    print(f"external_actions={len(sends)}")
    print(f"status={status}")
    if returned is not False:
        _fail("post-send commit failure returned True")
    if trace != "claimed:worker_fail":
        _fail(f"claim receipt {trace} is not worker_fail")
    if len(sends) != 1:
        _fail(f"external_actions={len(sends)} after failed commit")
    if status != "processing":
        _fail(f"status is {status}, expected processing")
    if not any("IntegrityError" in line for line in capture.lines):
        _fail("IntegrityError was not logged")
    print("IntegrityError")

    db2 = SessionLocal()
    try:
        again = process_ml_followup(
            payload,
            db2,
            event_client_id=client_id,
            event_id=event_id,
            worker_id="worker_late",
            sender=sender,
        )
    finally:
        db2.close()
    print(f"second_call_returned={again}")
    print(f"external_actions={len(sends)}")
    if again is not False:
        _fail("second worker claimed a processing row")
    if len(sends) != 1:
        _fail(f"second call sent, external_actions={len(sends)}")
    status_after, _trace_after = _read_row(event_id)
    print(f"status_after_second_call={status_after}")
    if status_after != "processing":
        _fail(f"status changed to {status_after}")
    _cleanup(client_id, session_id, event_id)


def main() -> None:
    _refuse_nonlocal()
    capture = _IntegrityCapture()
    logging.getLogger("dlq_replay").addHandler(capture)
    probe = SessionLocal()
    try:
        probe.execute(text("SELECT 1"))
    except Exception:
        print("local postgres is unreachable.")
        sys.exit(1)
    finally:
        probe.close()
    _ensure_client_columns()
    _prove_race()
    _prove_db_failure(capture)
    print("DLQ_PROOF_PASS")


if __name__ == "__main__":
    main()
