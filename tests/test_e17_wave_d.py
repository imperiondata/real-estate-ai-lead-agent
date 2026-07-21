"""Wave D skeletons — forecast, memory, n8n, brochure Approach B media.

Plan: plans/IREIOS_3.0_WAVE_A_D_EXPANSION.md §4 (esp. §4.4 Approach B)
Changelog: plans/IREIOS_3.0_WAVE_A_D_CHANGELOG.md

Approach B = host static PDF/image at public HTTPS URL; send via Twilio MediaUrl
(document bubble) + short caption; plain-text generate_* remains fallback.
"""
from __future__ import annotations

import pytest

_WAVE_D_IMPLEMENTED = False
_WAVE_D4_MEDIA_IMPLEMENTED = False


def _need_wave_d():
    if not _WAVE_D_IMPLEMENTED:
        pytest.skip("Wave D not implemented yet — see plans/IREIOS_3.0_WAVE_A_D_EXPANSION.md")


def _need_d4_media():
    if not _WAVE_D4_MEDIA_IMPLEMENTED:
        pytest.skip("Wave D.4 Approach B media not implemented yet — see plan §4.4")


# --------------------------------------------------------------------------- #
# D.1 — prediction routes
# --------------------------------------------------------------------------- #
def test_predictions_revenue_heuristic_shape():
    _need_wave_d()
    raise NotImplementedError


def test_predictions_cancellation_risk_shape():
    _need_wave_d()
    raise NotImplementedError


def test_predictions_inventory_counts():
    _need_wave_d()
    raise NotImplementedError


def test_predictions_cashflow_shape():
    _need_wave_d()
    raise NotImplementedError


def test_predictions_tenant_isolation():
    _need_wave_d()
    raise NotImplementedError


# --------------------------------------------------------------------------- #
# D.2 — memory on WA turn
# --------------------------------------------------------------------------- #
def test_whatsapp_turn_best_effort_memory_write(monkeypatch):
    _need_wave_d()
    raise NotImplementedError


def test_memory_write_failure_does_not_break_reply(monkeypatch):
    _need_wave_d()
    raise NotImplementedError


# --------------------------------------------------------------------------- #
# D.3 — n8n multi-workflow (config/docs; always-on degrade check)
# --------------------------------------------------------------------------- #
def test_n8n_client_still_degrades_when_empty():
    """Always-on regression (no Wave D gate): empty config must not crash."""
    from app.automation_engine.n8n_client import N8NClient
    import asyncio

    c = N8NClient(base_url="", api_key="")
    out = asyncio.run(c.trigger_workflow("x", {}))
    assert out.get("error") == "n8n_not_configured"


# --------------------------------------------------------------------------- #
# D.4 — Approach B brochure / floorplan media
# --------------------------------------------------------------------------- #
def test_resolve_tool_media_url_empty_fallback():
    _need_d4_media()
    # TODO: settings empty → resolve_tool_media_url("brochure") is None
    raise NotImplementedError


def test_resolve_tool_media_url_https_brochure(monkeypatch):
    _need_d4_media()
    # TODO: set BROCHURE_MEDIA_URL https://… → returns that URL
    raise NotImplementedError


def test_tool_branch_with_media_calls_ae_with_media_url(monkeypatch):
    _need_d4_media()
    # TODO: intent brochure + URL set → ae_submit parameters include media_url
    raise NotImplementedError


def test_tool_branch_without_media_returns_plain_text_no_ae(monkeypatch):
    _need_d4_media()
    # Must preserve e12 contract: empty media → no AE on default path
    raise NotImplementedError


def test_dispatch_outbound_forwards_media_url(monkeypatch):
    _need_d4_media()
    raise NotImplementedError


def test_brochure_twiml_path_no_double_delivery_with_media(monkeypatch):
    _need_d4_media()
    # W1: either AE media OR TwiML media — never both for same turn
    raise NotImplementedError


def test_ae_brochure_dispatch_may_include_media_url(monkeypatch):
    _need_d4_media()
    raise NotImplementedError
