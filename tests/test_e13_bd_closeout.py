"""BD-1…BD-6 closeout checks — graph-on-reply path, CRM single path, outbound purity."""
from __future__ import annotations

import inspect

import main as main_mod
from app.agents.whatsapp_agent import WhatsAppAgent
from app.clients.graph_client import format_graph_context_for_llm
from app.execution_engine import outbound as outbound_mod


def test_format_graph_context_for_llm():
    assert format_graph_context_for_llm({}) == ""
    text = format_graph_context_for_llm(
        {
            "similar_leads": [
                {"lead_id": 1, "location": "Wakad", "property_type": "2BHK"},
                {"lead_id": 2, "location": "Wakad", "property_type": "2BHK"},
            ],
            "assigned_agent": "Sneha",
        }
    )
    assert "similar" in text.lower()
    assert "Wakad" in text
    assert "Sneha" in text
    assert "Do NOT invent" in text


def test_whatsapp_agent_has_graph_hook():
    assert hasattr(WhatsAppAgent, "_graph_extra_context")
    src = inspect.getsource(WhatsAppAgent.process_chat)
    assert "extra_context" in src
    assert "qualification" in src


def test_process_chat_accepts_extra_context():
    from agent import process_chat

    sig = inspect.signature(process_chat)
    assert "extra_context" in sig.parameters


def test_main_no_direct_create_time_crm_sync():
    src = inspect.getsource(main_mod.process_unified_lead)
    assert "sync_lead_to_crm" not in src
    assert "_emit_turn_events" in src


def test_agent_no_create_time_crm_import_usage():
    import agent as agent_mod

    src = inspect.getsource(agent_mod)
    # Import removed; create path must not call sync_lead_to_crm
    assert "task2 = sync_lead_to_crm" not in src


def test_outbound_helpers_exist():
    assert callable(outbound_mod.send_whatsapp_async)
    assert callable(outbound_mod.send_whatsapp_blocking)


def test_escalation_uses_outbound_not_twilio_client():
    src = inspect.getsource(main_mod.escalation_cron_job)
    assert "send_whatsapp_blocking" in src
    assert "messages.create" not in src


def test_qualification_module_reexports():
    from app.agents import qualification
    from agent import process_chat as root_pc

    assert qualification.process_chat is root_pc


def test_notification_uses_executor():
    import notification_service as ns

    src = inspect.getsource(ns._send_alert_whatsapp)
    assert "WhatsAppExecutor" in src
    assert "from twilio.rest import Client" not in src
