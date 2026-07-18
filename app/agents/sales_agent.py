"""IREIOS 3.0 — Phase 6: Sales AI agent + CRM automation (Tasks 6.1–6.4).

`SalesAgent` turns qualification output into a recommended next-best sales
action and (optionally) advances the deal stage and syncs the lead to the CRM
through the AutomationEngine -> ExecutionEngine (so CRM writes are observable
and DLQ-protected, reusing the Phase 3 `CRMExecutor`).

It is deterministic (no extra LLM call) and reuses:
  * `agent_matcher.ensure_lead_assignment` for sticky assignment
  * `whatsapp_agent.score_lead` for the lead score breakdown
  * `crm_sync` indirectly via the `update_crm` executor

See plans/IREIOS_3.0_STEP_BY_STEP_EXPANSION.md (Phase 6) and
plans/IREIOS_3.0_EXPANSION_CHANGELOG.md.
"""
from __future__ import annotations

import logging
from typing import Optional

from config import settings
from models import Lead

from app.agents.whatsapp_agent import score_lead
from app.automation_engine.engine import submit as ae_submit
from app.intelligence.agent_matcher import ensure_lead_assignment

logger = logging.getLogger("sales_agent")

# Canonical funnel progression used by `progress_deal_stage`.
_FUNNEL_NEXT = {
    "New": "Contacted",
    "Contacted": "Qualified",
    "Qualified": "Site Visit Booked",
    "Site Visit Booked": "Negotiation",
    "Negotiation": "Closed Won",
}
_TERMINAL_STAGES = {"Closed Won", "Closed Lost", "Lost"}


def recommend_next_action(lead: Lead) -> dict:
    """Return the next-best sales action for a lead.

    Deterministic policy:
      * missing mandatory fields -> request_info
      * temperature hot -> escalate_hot (human handoff)
      * visit_date present but stage < Site Visit Booked -> schedule_site_visit
      * warm + assigned -> send_brochure
      * assigned + qualified-ish -> assign_agent (notify)
      * otherwise -> nurture_followup
    """
    temp = (lead.lead_temperature or "cold").lower()
    has_core = all([lead.name, lead.phone, lead.location, lead.budget, lead.property_type])

    if not has_core:
        missing = [f for f in ("name", "phone", "location", "budget", "property_type")
                   if not getattr(lead, f)]
        return {"action": "request_info", "missing_fields": missing,
                "rationale": "Capture remaining mandatory fields before routing."}

    if temp == "hot":
        return {"action": "escalate_hot",
                "rationale": "Hot lead — pause automation and alert a human agent."}

    if lead.visit_date and (lead.funnel_stage or "New") not in ("Site Visit Booked", "Negotiation"):
        return {"action": "schedule_site_visit",
                "rationale": "Visit date captured — confirm and book the site tour."}

    if temp == "warm" and lead.assigned_agent:
        return {"action": "send_brochure",
                "rationale": "Warm, assigned lead — share property brochure to build intent."}

    if lead.assigned_agent:
        return {"action": "assign_agent",
                "rationale": "Assigned lead — notify the human owner to take over."}

    return {"action": "nurture_followup",
            "rationale": "Cold/unassigned — keep in the automated follow-up sequence."}


def progress_deal_stage(lead: Lead) -> Optional[str]:
    """Advance the funnel stage based on captured signals. Returns new stage or None."""
    current = lead.funnel_stage or "New"
    if current in _TERMINAL_STAGES:
        return None

    if all([lead.name, lead.phone, lead.location, lead.budget, lead.property_type, lead.visit_date]):
        # Fully qualified with a visit -> jump straight to Site Visit Booked.
        return "Site Visit Booked" if current not in ("Site Visit Booked", "Negotiation") else None

    nxt = _FUNNEL_NEXT.get(current)
    if nxt and current == "New" and lead.assigned_agent:
        return "Contacted"
    return nxt


class SalesAgent:
    """Phase 6 Sales AI orchestrator."""

    async def run_sales_ai(self, db, lead: Lead, client_id: int, *, sync_crm: bool = False) -> dict:
        """Score, assign, recommend, and (optionally) advance + sync the lead.

        All mutations are committed by the caller's session (`db`); CRM sync is
        fired as an AE action (fire-and-forget, DLQ-protected) when `sync_crm`.
        """
        scores = score_lead(lead)
        for k, v in scores.items():
            setattr(lead, k, v)

        previous_agent = lead.assigned_agent
        assigned = ensure_lead_assignment(db, lead, client_id, lead.intent or lead.location or "", force=False)
        if assigned and previous_agent != assigned:
            from models import EventLog
            db.add(EventLog(
                session_id=lead.session_id, client_id=client_id, event_type="audit",
                action_type=f"sales_ai_assigned_{assigned.replace(' ', '_').lower()}", agent_type="SalesAI",
            ))

        recommendation = recommend_next_action(lead)

        new_stage = progress_deal_stage(lead)
        if new_stage:
            lead.funnel_stage = new_stage

        crm_status = None
        if sync_crm and lead.id:
            crm_status = await self.sync_crm_via_ae(lead.id, client_id)

        db.commit()
        return {
            "scores": scores,
            "assigned_agent": assigned,
            "recommendation": recommendation,
            "funnel_stage": lead.funnel_stage,
            "crm_sync": crm_status,
        }

    async def sync_crm_via_ae(self, lead_id: int, client_id: int) -> dict:
        """Route CRM sync through AutomationEngine -> ExecutionEngine (CRMExecutor)."""
        try:
            result = await ae_submit({
                "action_type": "update_crm",
                "tenant_id": f"Client_{client_id}",
                "entity_id": f"lead:{lead_id}",
                "parameters": {"lead_id": lead_id},
                "source": "sales_agent",
            })
            return result
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"SalesAI CRM sync via AE failed (DLQ may catch): {e}")
            return {"status": "error", "error": str(e)}


sales_agent = SalesAgent()
