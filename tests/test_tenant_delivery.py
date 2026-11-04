"""Tenant email and webhook delivery proofs.

Real rows in the local Postgres, but no SMTP connection and no HTTP request:
every transport callable is an injected spy. Rows created here are deleted in a
``finally`` block.
"""

from __future__ import annotations

import uuid

import pytest

from app.services.tenant_delivery import deliver_tenant_lead
from config import settings
from database import SessionLocal
from models import Client, EventLog, Lead
from models import Session as SessionModel


class Spy:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[tuple] = []

    def __call__(self, *args):
        self.calls.append(args)


class ExplodingSpy:
    def __init__(self, name: str) -> None:
        self.name = name

    def __call__(self, *args):
        raise AssertionError(f"{self.name} must not be called")


def _client(db, tag: str, settings_value: dict) -> Client:
    suffix = uuid.uuid4().hex
    client = Client(
        company_name=f"Tenant {tag} {suffix[:8]}",
        email=f"tenant-{tag}-{suffix}@delivery.test",
        hashed_password="not-used-in-this-test",
        api_key=f"tenant-delivery-{tag}-{suffix}",
        is_api_key_hashed=True,
        is_active=True,
        settings=settings_value,
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


def _session(db, client: Client, tag: str) -> SessionModel:
    session = SessionModel(
        id=f"{client.id}_delivery-{tag}-{uuid.uuid4().hex}",
        client_id=client.id,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _lead(db, client: Client, session: SessionModel, tag: str) -> Lead:
    lead = Lead(
        session_id=session.id,
        client_id=client.id,
        name=f"Lead {tag}",
        phone="9000000000",
        location="Baner",
        budget="50L",
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


def _wipe(db, client_ids: list[int]) -> None:
    try:
        db.rollback()
        if client_ids:
            db.query(EventLog).filter(EventLog.client_id.in_(client_ids)).delete(
                synchronize_session=False
            )
            db.query(Lead).filter(Lead.client_id.in_(client_ids)).delete(
                synchronize_session=False
            )
            db.query(SessionModel).filter(SessionModel.client_id.in_(client_ids)).delete(
                synchronize_session=False
            )
            db.query(Client).filter(Client.id.in_(client_ids)).delete(
                synchronize_session=False
            )
        db.commit()
    finally:
        db.close()


def test_tenant_delivery_uses_only_its_own_targets(monkeypatch):
    monkeypatch.setattr(settings, "TEST_MODE", False)
    db = SessionLocal()
    client_ids: list[int] = []
    try:
        client_a = _client(
            db,
            "a",
            {
                "notify_email": "owner-a@tenant-a.test",
                "webhook_url": "https://tenant-a.test/hook",
            },
        )
        client_b = _client(
            db,
            "b",
            {
                "notify_email": "owner-b@tenant-b.test",
                "webhook_url": "https://tenant-b.test/hook",
            },
        )
        client_ids = [client_a.id, client_b.id]
        session_a = _session(db, client_a, "a")
        _session(db, client_b, "b")
        lead_a = _lead(db, client_a, session_a, "a")

        email_spy = Spy("email")
        webhook_spy = Spy("webhook")
        recorded = deliver_tenant_lead(
            db,
            client_a,
            lead_a,
            session_a.id,
            email_sender=email_spy,
            webhook_poster=webhook_spy,
        )

        assert recorded == ["tenant_email", "tenant_webhook"]
        assert [call[0] for call in email_spy.calls] == ["owner-a@tenant-a.test"]
        assert [call[0] for call in webhook_spy.calls] == [
            "https://tenant-a.test/hook"
        ]
        assert all("tenant-b" not in str(call) for call in email_spy.calls)
        assert all("tenant-b" not in str(call) for call in webhook_spy.calls)
        payload = webhook_spy.calls[0][1]
        assert payload == {
            "lead_id": lead_a.id,
            "tenant_id": client_a.id,
            "name": lead_a.name,
            "phone": lead_a.phone,
        }

        rows = (
            db.query(EventLog)
            .filter(EventLog.client_id.in_(client_ids))
            .all()
        )
        assert {row.client_id for row in rows} == {client_a.id}
        assert {row.action_type for row in rows} == {"tenant_email", "tenant_webhook"}
        assert {row.session_id for row in rows} == {session_a.id}
        assert {row.agent_type for row in rows} == {"sent"}
        assert all(row.client_id != client_b.id for row in rows)
    finally:
        _wipe(db, client_ids)


def test_no_target_records_one_skipped_row(monkeypatch):
    monkeypatch.setattr(settings, "TEST_MODE", False)
    db = SessionLocal()
    client_ids: list[int] = []
    try:
        client = _client(db, "none", {})
        client_ids = [client.id]
        session = _session(db, client, "none")
        lead = _lead(db, client, session, "none")

        email_spy = Spy("email")
        webhook_spy = Spy("webhook")
        recorded = deliver_tenant_lead(
            db,
            client,
            lead,
            session.id,
            email_sender=email_spy,
            webhook_poster=webhook_spy,
        )

        assert recorded == ["tenant_delivery_skipped"]
        assert email_spy.calls == []
        assert webhook_spy.calls == []
        rows = db.query(EventLog).filter(EventLog.client_id == client.id).all()
        assert len(rows) == 1
        assert rows[0].event_type == "tenant_delivery"
        assert rows[0].action_type == "tenant_delivery_skipped"
        assert rows[0].agent_type == "no_target"
    finally:
        _wipe(db, client_ids)


def test_non_http_webhook_is_ignored(monkeypatch):
    monkeypatch.setattr(settings, "TEST_MODE", False)
    db = SessionLocal()
    client_ids: list[int] = []
    try:
        client = _client(db, "file", {"webhook_url": "file:///tmp/x"})
        client_ids = [client.id]
        session = _session(db, client, "file")
        lead = _lead(db, client, session, "file")

        webhook_spy = Spy("webhook")
        recorded = deliver_tenant_lead(
            db, client, lead, session.id, webhook_poster=webhook_spy
        )

        assert recorded == ["tenant_delivery_skipped"]
        assert webhook_spy.calls == []
        rows = db.query(EventLog).filter(EventLog.client_id == client.id).all()
        assert len(rows) == 1
        assert rows[0].action_type == "tenant_delivery_skipped"
        assert rows[0].agent_type == "no_target"
    finally:
        _wipe(db, client_ids)


def test_second_delivery_does_not_send_or_duplicate(monkeypatch):
    monkeypatch.setattr(settings, "TEST_MODE", False)
    db = SessionLocal()
    client_ids: list[int] = []
    try:
        client = _client(db, "once", {"notify_email": "once@tenant.test"})
        client_ids = [client.id]
        session = _session(db, client, "once")
        lead = _lead(db, client, session, "once")

        email_spy = Spy("email")
        first = deliver_tenant_lead(
            db, client, lead, session.id, email_sender=email_spy
        )
        second = deliver_tenant_lead(
            db, client, lead, session.id, email_sender=email_spy
        )

        assert first == ["tenant_email"]
        assert second == []
        assert len(email_spy.calls) == 1
        rows = (
            db.query(EventLog)
            .filter(
                EventLog.client_id == client.id,
                EventLog.event_type == "tenant_delivery",
                EventLog.action_type == "tenant_email",
            )
            .all()
        )
        assert len(rows) == 1
    finally:
        _wipe(db, client_ids)


def test_unconfigured_smtp_records_without_sending(monkeypatch):
    monkeypatch.setattr(settings, "TEST_MODE", False)
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    monkeypatch.setattr(settings, "SMTP_PORT", 0)
    monkeypatch.setattr(settings, "SMTP_USER", "")
    monkeypatch.setattr(settings, "SMTP_PASS", "")
    db = SessionLocal()
    client_ids: list[int] = []
    try:
        client = _client(db, "smtp", {"notify_email": "smtp@tenant.test"})
        client_ids = [client.id]
        session = _session(db, client, "smtp")
        lead = _lead(db, client, session, "smtp")

        recorded = deliver_tenant_lead(db, client, lead, session.id)

        assert recorded == ["tenant_email"]
        rows = db.query(EventLog).filter(EventLog.client_id == client.id).all()
        assert len(rows) == 1
        assert rows[0].agent_type == "smtp_unconfigured"
    finally:
        _wipe(db, client_ids)


def test_transport_failures_are_recorded_not_raised(monkeypatch):
    monkeypatch.setattr(settings, "TEST_MODE", False)
    db = SessionLocal()
    client_ids: list[int] = []
    try:
        client = _client(
            db,
            "fail",
            {
                "notify_email": "fail@tenant.test",
                "webhook_url": "https://tenant.test/fail",
            },
        )
        client_ids = [client.id]
        session = _session(db, client, "fail")
        lead = _lead(db, client, session, "fail")

        def boom(*_args):
            raise RuntimeError("transport down")

        recorded = deliver_tenant_lead(
            db, client, lead, session.id, email_sender=boom, webhook_poster=boom
        )

        assert recorded == ["tenant_email", "tenant_webhook"]
        rows = db.query(EventLog).filter(EventLog.client_id == client.id).all()
        agents = {row.action_type: row.agent_type for row in rows}
        assert agents == {
            "tenant_email": "email_failed",
            "tenant_webhook": "webhook_failed",
        }
    finally:
        _wipe(db, client_ids)


def test_test_mode_records_without_calling_transports(monkeypatch):
    monkeypatch.setattr(settings, "TEST_MODE", True)
    db = SessionLocal()
    client_ids: list[int] = []
    try:
        client = _client(
            db,
            "mode",
            {
                "notify_email": "mode@tenant.test",
                "webhook_url": "https://tenant.test/hook",
            },
        )
        client_ids = [client.id]
        session = _session(db, client, "mode")
        lead = _lead(db, client, session, "mode")

        recorded = deliver_tenant_lead(
            db,
            client,
            lead,
            session.id,
            email_sender=ExplodingSpy("email"),
            webhook_poster=ExplodingSpy("webhook"),
        )

        assert recorded == ["tenant_email", "tenant_webhook"]
        rows = db.query(EventLog).filter(EventLog.client_id == client.id).all()
        assert {row.action_type for row in rows} == {"tenant_email", "tenant_webhook"}
        assert {row.agent_type for row in rows} == {"recorded"}
    finally:
        _wipe(db, client_ids)
