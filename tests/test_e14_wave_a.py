"""Wave A skeletons — close dead loops + AE template dispatch + producers.

Plan: plans/IREIOS_3.0_WAVE_A_D_EXPANSION.md §1
Changelog: plans/IREIOS_3.0_WAVE_A_D_CHANGELOG.md

Replace pytest.skip stubs with real assertions as each A.* task ships.
Keep asyncio.run + monkeypatch style consistent with test_e11_parity.py / test_e2_automation.py.
"""
from __future__ import annotations

import pytest

# Flip to False (or delete skips) when Wave A implementation starts.
_WAVE_A_IMPLEMENTED = False


def _need_wave_a():
    if not _WAVE_A_IMPLEMENTED:
        pytest.skip("Wave A not implemented yet — see plans/IREIOS_3.0_WAVE_A_D_EXPANSION.md")


# --------------------------------------------------------------------------- #
# A.1 — weekly marketing cron publishes cron.weekly_report
# --------------------------------------------------------------------------- #
def test_weekly_marketing_cron_publishes_per_client():
    _need_wave_a()
    # TODO: monkeypatch event_bus.publish; run weekly job; assert event_type
    # == "cron.weekly_report" and tenant_id starts with Client_
    raise NotImplementedError


def test_marketing_agent_still_emits_report_on_weekly_event():
    _need_wave_a()
    # TODO: call marketing_agent_handler with cron.weekly_report envelope;
    # assert marketing.report.generated published (parity with test_e11)
    raise NotImplementedError


# --------------------------------------------------------------------------- #
# A.2 — lifecycle producers
# --------------------------------------------------------------------------- #
def test_lifecycle_inject_booking_confirmed_wakes_cs(monkeypatch):
    _need_wave_a()
    # TODO: POST or direct publish booking.confirmed; CS ae_submit called
    raise NotImplementedError


def test_lifecycle_inject_rejects_bad_event_type():
    _need_wave_a()
    raise NotImplementedError


def test_lifecycle_inject_other_tenant_lead_404():
    _need_wave_a()
    raise NotImplementedError


# --------------------------------------------------------------------------- #
# A.3 — AE template_type dispatch
# --------------------------------------------------------------------------- #
def test_ae_n8n_template_unconfigured_returns_clean_error(monkeypatch):
    _need_wave_a()
    # TODO: submit template_type=n8n with empty N8N_*; assert n8n_not_configured
    raise NotImplementedError


def test_ae_n8n_template_calls_client_when_configured(monkeypatch):
    _need_wave_a()
    raise NotImplementedError


def test_ae_langgraph_template_reaches_execute_or_fallback(monkeypatch):
    _need_wave_a()
    raise NotImplementedError


def test_ae_linear_default_unchanged(monkeypatch):
    _need_wave_a()
    # Regression: existing linear path still hits execution_engine.dispatch
    raise NotImplementedError


# --------------------------------------------------------------------------- #
# A.4 — expire_stale_approvals
# --------------------------------------------------------------------------- #
def test_expire_stale_approvals_marks_old_pending():
    _need_wave_a()
    raise NotImplementedError


def test_expire_approvals_job_registered_in_scheduler():
    _need_wave_a()
    # TODO: import main scheduler job ids includes expire_approvals
    raise NotImplementedError


# --------------------------------------------------------------------------- #
# A.5 — NotificationExecutor admin / manager
# --------------------------------------------------------------------------- #
def test_notify_admin_invokes_outbound_not_log_only(monkeypatch):
    _need_wave_a()
    raise NotImplementedError


def test_manager_approval_kind_notifies_manager(monkeypatch):
    _need_wave_a()
    raise NotImplementedError
