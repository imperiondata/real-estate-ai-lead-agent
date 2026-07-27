"""IREIOS 3.0 — Phase 6 + Wave B.1/B.2: Sales AI agent + CEO bus + objections.

`SalesAgent` turns qualification output into a recommended next-best sales
action and (optionally) advances the deal stage and syncs the lead to the CRM
through the AutomationEngine -> ExecutionEngine (so CRM writes are observable
and DLQ-protected, reusing the Phase 3 `CRMExecutor`).

Wave B.1: registered on the CEO bus (``lead.scored``, ``lead.hot``, ``conversation.updated``, ``lead.qualified``)
so hot/scored leads trigger real AE actions without an HTTP call.
Wave B.2: lightweight objection detection via rule lexicon.

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
from database import SessionLocal
from models import Lead

from app.agents.whatsapp_agent import score_lead
from app.automation_engine.engine import submit as ae_submit
from app.intelligence.agent_matcher import ensure_lead_assignment

logger = logging.getLogger("sales_agent")

# Wave B.1: bus subscription events.
SALES_BUS_EVENTS = ["lead.scored", "lead.hot", "conversation.updated", "lead.qualified"]

# Wave B.2: objection lexicon.
_OBJECTION_PATTERNS = {
    "price": ["too expensive", "out of budget", "over budget", "costly", "high price", "can't afford", "pricey"],
    "timing": ["not now", "later", "not ready", "need time", "thinking", "maybe next month", "no rush"],
    "location": ["too far", "not in that area", "other location", "wrong area", "too remote"],
    "trust": ["scam", "fraud", "not sure about you", "unreliable", "never heard"],
    "competitor": ["other builder", "another project", "found better", "going with", "other company"],
}

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

    if lead.visit_date and (lead.funnel_stage or "New") not in ("Site Visit Booked", "Negotiation"):
        return {"action": "schedule_site_visit",
                "rationale": "Visit date captured — confirm and book the site tour."}

    if temp == "hot":
        return {"action": "escalate_hot",
                "rationale": "Hot lead — pause automation and alert a human agent."}

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


# --------------------------------------------------------------------------- #
# Wave B.1: CEO bus handler — maps NBA actions to AE submissions.
# --------------------------------------------------------------------------- #

def _resolve_client_id(tenant_id) -> Optional[int]:
    if tenant_id is None:
        return None
    s = str(tenant_id)
    if s.startswith("Client_"):
        s = s.split("_", 1)[1]
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


def _lead_id(envelope: dict) -> Optional[int]:
    payload = envelope.get("payload") or {}
    raw = payload.get("lead_id", envelope.get("entity_id"))
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


def _debounce_key(client_id: int, lead_id: int) -> str:
    """Redis key for per-lead sales AI debounce (10min TTL)."""
    return f"sales_ai_lock:{client_id}:{lead_id}"


async def _nba_to_ae_action(lead: Lead, client_id: int, recommendation: dict) -> None:
    """Map a Sales NBA recommendation to an AE action request when applicable."""
    action = recommendation.get("action")
    if action == "escalate_hot":
        reason = recommendation.get("rationale", "Hot lead — auto-escalated by Sales AI")
        await ae_submit({
            "action_type": "notify_agent",
            "tenant_id": f"Client_{client_id}",
            "entity_id": str(lead.id),
            "parameters": {
                "kind": "hot_lead",
                "lead_id": lead.id,
                "reason": reason,
            },
            "source": "sales_agent",
        })
        # B.7: internal task so humans see a durable work item even if notify fails.
        await ae_submit({
            "action_type": "create_task",
            "tenant_id": f"Client_{client_id}",
            "entity_id": str(lead.id),
            "parameters": {
                "lead_id": lead.id,
                "title": f"Call hot lead {lead.name or lead.id}",
                "description": reason,
                "assignee": lead.assigned_agent or None,
                "source": "sales_agent",
            },
            "source": "sales_agent",
        })
    elif action == "schedule_site_visit" and lead.visit_date:
        await ae_submit({
            "action_type": "schedule_visit",
            "tenant_id": f"Client_{client_id}",
            "entity_id": str(lead.id),
            "parameters": {
                "lead_id": lead.id,
                "visit_date": lead.visit_date,
                "name": lead.name or "",
                "phone": lead.phone or "",
                "location": lead.location or "",
            },
            "source": "sales_agent",
        })
        # P3: When a hot lead has a visit date, fire hot lead notification alongside
        # so the agent gets the WhatsApp alert even though escalate_hot was bypassed.
        if (lead.lead_temperature or "").lower() == "hot":
            hot_reason = "Hot lead with confirmed visit date — alert agent."
            await ae_submit({
                "action_type": "notify_agent",
                "tenant_id": f"Client_{client_id}",
                "entity_id": str(lead.id),
                "parameters": {
                    "kind": "hot_lead",
                    "lead_id": lead.id,
                    "reason": hot_reason,
                },
                "source": "sales_agent",
            })
            await ae_submit({
                "action_type": "create_task",
                "tenant_id": f"Client_{client_id}",
                "entity_id": str(lead.id),
                "parameters": {
                    "lead_id": lead.id,
                    "title": f"Call hot lead {lead.name or lead.id}",
                    "description": hot_reason,
                    "assignee": lead.assigned_agent or None,
                    "source": "sales_agent",
                },
                "source": "sales_agent",
            })
    elif action == "send_brochure":
        from app.agents.whatsapp_agent import generate_brochure, resolve_tool_media_url

        media_url = resolve_tool_media_url("brochure")
        if media_url:
            body = (
                f"Hi {lead.name or 'there'}, here is the brochure for "
                f"{lead.property_type or 'properties'} in {lead.location or 'our projects'}."
            )
        else:
            body = generate_brochure(lead)
        params = {
            "to": lead.phone or "",
            "body": body,
            "source": "sales_agent",
            "tool": "brochure",
        }
        if media_url:
            params["media_url"] = media_url
        await ae_submit({
            "action_type": "send_whatsapp",
            "tenant_id": f"Client_{client_id}",
            "entity_id": str(lead.id),
            "parameters": params,
            "source": "sales_agent",
        })
    # Other actions (request_info, nurture_followup, assign_agent) are handled
    # by the follow-up scheduler and agent assignment — no AE action needed here.


async def sales_bus_handler(envelope: dict) -> None:
    """CEO handler for sales bus events: score/assign/recommend → AE actions."""
    client_id = _resolve_client_id(envelope.get("tenant_id"))
    lid = _lead_id(envelope)
    if client_id is None or lid is None:
        return

    # Debounce: skip if this lead was acted on recently.
    # P3: lead.qualified bypasses debounce — visit booking is time-critical.
    event_type = envelope.get("event_type", "")
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        lock_key = _debounce_key(client_id, lid)
        already = await r.get(lock_key)
        if already:
            if event_type == "lead.qualified":
                logger.debug("sales_bus debounce bypassed for lead.qualified: lead %s client %s", lid, client_id)
            else:
                logger.debug("sales_bus debounce: lead %s client %s skipped", lid, client_id)
                await r.aclose()
                return
        await r.set(lock_key, "1", ex=600)  # 10 minute TTL (refreshes for bypassed events)
        await r.aclose()
    except Exception:
        pass  # debounce is best-effort; proceed without it

    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.id == lid, Lead.client_id == client_id).first()
        if lead is None:
            return

        recommendation = recommend_next_action(lead)
        await _nba_to_ae_action(lead, client_id, recommendation)
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Wave B.2: Objection detection (lightweight rule lexicon).
# --------------------------------------------------------------------------- #

def detect_objections(message: str) -> list[dict]:
    """Scan a user message for known objection patterns.

    Returns a list of dicts ``[{"type": "price", "matched": "too expensive"}, …]``.
    Empty list when no objection is detected.
    """
    if not message:
        return []
    msg_lower = message.lower()
    hits: list[dict] = []
    for obj_type, patterns in _OBJECTION_PATTERNS.items():
        for pat in patterns:
            if pat in msg_lower:
                hits.append({"type": obj_type, "matched": pat})
                break  # one match per type per message
    return hits


async def persist_objection(db, lead_id: int, client_id: int, objection: dict) -> None:
    """Store an objection in LeadMemory."""
    from models import LeadMemory
    mem = LeadMemory(
        client_id=client_id,
        lead_id=lead_id,
        key=f"objection_{objection['type']}",
        value=objection["matched"],
        memory_type="objection",
    )
    db.add(mem)
    db.commit()


# --------------------------------------------------------------------------- #
# CEO registration
# --------------------------------------------------------------------------- #

def register_sales_agent(ceo) -> None:
    ceo.register_agent(
        "sales_agent", sales_bus_handler, subscriptions=list(SALES_BUS_EVENTS), status="active"
    )
    logger.info("Registered sales_agent on %d event types (B.1 bus)", len(SALES_BUS_EVENTS))


sales_agent = SalesAgent()
