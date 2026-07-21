"""Wave C skeletons — promote six placeholder agents to active.

Plan: plans/IREIOS_3.0_WAVE_A_D_EXPANSION.md §3
Changelog: plans/IREIOS_3.0_WAVE_A_D_CHANGELOG.md
"""
from __future__ import annotations

import pytest

_WAVE_C_IMPLEMENTED = False


def _need_wave_c():
    if not _WAVE_C_IMPLEMENTED:
        pytest.skip("Wave C not implemented yet — see plans/IREIOS_3.0_WAVE_A_D_EXPANSION.md")


# --------------------------------------------------------------------------- #
# C.0 — inventory seed / schema
# --------------------------------------------------------------------------- #
def test_inventory_unit_model_roundtrip():
    _need_wave_c()
    raise NotImplementedError


def test_seed_inventory_creates_available_units():
    _need_wave_c()
    raise NotImplementedError


# --------------------------------------------------------------------------- #
# C.1 — negotiation
# --------------------------------------------------------------------------- #
def test_negotiation_agent_active_not_placeholder():
    _need_wave_c()
    raise NotImplementedError


def test_negotiation_high_discount_requires_approval(monkeypatch):
    _need_wave_c()
    raise NotImplementedError


def test_negotiation_low_risk_path(monkeypatch):
    _need_wave_c()
    raise NotImplementedError


# --------------------------------------------------------------------------- #
# C.2 — pricing
# --------------------------------------------------------------------------- #
def test_pricing_agent_publishes_quote(monkeypatch):
    _need_wave_c()
    raise NotImplementedError


def test_pricing_quote_matches_location_bhk():
    _need_wave_c()
    raise NotImplementedError


# --------------------------------------------------------------------------- #
# C.3 — inventory agent
# --------------------------------------------------------------------------- #
def test_inventory_match_on_lead_qualified(monkeypatch):
    _need_wave_c()
    raise NotImplementedError


def test_inventory_ignores_other_tenant():
    _need_wave_c()
    raise NotImplementedError


# --------------------------------------------------------------------------- #
# C.4 — onboarding
# --------------------------------------------------------------------------- #
def test_onboarding_on_booking_emits_customer_onboarded(monkeypatch):
    _need_wave_c()
    raise NotImplementedError


# --------------------------------------------------------------------------- #
# C.5 — finance
# --------------------------------------------------------------------------- #
def test_finance_publishes_payment_due(monkeypatch):
    _need_wave_c()
    raise NotImplementedError


def test_finance_cashflow_summary_route_shape():
    _need_wave_c()
    raise NotImplementedError


# --------------------------------------------------------------------------- #
# C.6 — legal
# --------------------------------------------------------------------------- #
def test_legal_publishes_document_pending(monkeypatch):
    _need_wave_c()
    raise NotImplementedError


# --------------------------------------------------------------------------- #
# C.7 — placeholders cleared
# --------------------------------------------------------------------------- #
def test_six_former_placeholders_are_active():
    _need_wave_c()
    # TODO: agent_registry / ceo.list_agents — pricing, negotiation, inventory,
    # legal, finance, onboarding all status == "active"
    raise NotImplementedError


def test_placeholders_list_empty_or_without_six():
    _need_wave_c()
    raise NotImplementedError
