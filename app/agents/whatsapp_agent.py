"""IREIOS 3.0 — Phase 5: WhatsApp Agent v3 + brochure/floorplan + lead scoring.

`WhatsAppAgent` is the v3 chat orchestrator. It reuses the proven qualification
pipeline in `agent.process_chat` (no behaviour regression) and layers on:

  * deterministic lead scoring (`score_lead`) — conversion probability,
    temperature, urgency, engagement, budget alignment.
  * brochure / floorplan tool handlers that produce rich outbound media-style
    messages and dispatch them through the AutomationEngine -> ExecutionEngine
    (so outbound delivery is observable / DLQ-protected).
  * intent routing so a "send brochure" / "show floor plan" request is served
    by the new tools instead of the generic pipeline.

The v3 path is selected by `FEATURE_WHATSAPP_V3` in `main.py`; legacy routes
still call `agent.process_chat` directly when the flag is off.

See plans/IREIOS_3.0_STEP_BY_STEP_EXPANSION.md (Phase 5) and
plans/IREIOS_3.0_EXPANSION_CHANGELOG.md.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from config import settings
from database import SessionLocal
from models import Lead, Message, Session
from sqlalchemy.orm import Session as DBSession

from app.automation_engine.engine import submit as ae_submit

logger = logging.getLogger("whatsapp_agent_v3")

_PROP_TYPE_RE = re.compile(r"\b(1bhk|2bhk|3bhk|4bhk|villa|plot|studio|penthouse|flat|apartment)\b", re.I)
_AREA_RE = re.compile(r"\b(\d{3,5})\s*sq\s*(ft|feet)\b", re.I)


def detect_tool_intent(message: str) -> Optional[str]:
    """Return 'brochure' | 'floorplan' | None based on the user message."""
    m = (message or "").lower()
    if any(k in m for k in ("brochure", "send details", "property details", "more info", "share details")):
        return "brochure"
    if any(k in m for k in ("floor plan", "floorplan", "layout", "floor map", "plan")):
        return "floorplan"
    return None


def _fmt_budget(budget: Optional[str]) -> str:
    return budget or "as per your preference"


def generate_brochure(lead: Lead) -> str:
    """Deterministic brochure text derived from captured lead fields."""
    pt = lead.property_type or "property"
    loc = lead.location or "Pune"
    budget = _fmt_budget(lead.budget)
    name = lead.name or "there"
    return (
        f"Hi {name}, here is the brochure for {pt} options in {loc}.\n"
        f"• Property type: {pt}\n"
        f"• Location: {loc}\n"
        f"• Budget range: {budget}\n"
        f"• Highlights: ready possession, gated community, Vastu-compliant, "
        f"clubhouse & parking.\n"
        f"Reply 'floor plan' to see the layout, or share a visit date to book a site tour."
    )


def generate_floorplan(lead: Lead) -> str:
    """Deterministic floor-plan description derived from captured lead fields."""
    pt = lead.property_type or "2BHK"
    match = _PROP_TYPE_RE.search(pt) or _PROP_TYPE_RE.search(lead.intent or "")
    label = (match.group(1).upper() if match else "2BHK").upper()
    area = _AREA_RE.search(lead.budget or "") or _AREA_RE.search(lead.intent or "")
    sqft = area.group(1) if area else ("950" if "1bhk" in label.lower() else "1250" if "2bhk" in label.lower() else "1800")
    name = lead.name or "there"
    return (
        f"Hi {name}, here is the {label} floor plan (~{sqft} sq ft):\n"
        f"• Entrance lobby → living/dining\n"
        f"• {label} bedrooms with attached baths\n"
        f"• Modular kitchen + utility\n"
        f"• Balcony facing the greens\n"
        f"Want me to share the brochure or lock a site-visit date?"
    )


def score_lead(lead: Lead) -> dict:
    """Compute lead scores and persist them on the lead row.

    Pure-ish heuristic (no LLM) so it is fast and deterministic:
      * engagement_score: +1 per filled core field, capped at 100
      * conversion_probability: weighted blend of completeness + temperature
      * lead_temperature: hot/warm/cold from probability
      * urgency_level: high/medium/low from visit intent / recency
      * budget_alignment_status: aligned / unknown / mismatch
    """
    core = [lead.name, lead.phone, lead.budget, lead.location, lead.property_type, lead.visit_date]
    filled = sum(1 for c in core if c)
    engagement = min(100, filled * 16 + (lead.whatsapp_opt_in and 4 or 0))

    temp = (lead.lead_temperature or "cold").lower()
    temp_weight = {"hot": 60, "warm": 40, "cold": 15}.get(temp, 15)
    prob = min(98, int(engagement * 0.5 + temp_weight * 0.5))

    if prob >= 70:
        temperature = "hot"
    elif prob >= 45:
        temperature = "warm"
    else:
        temperature = "cold"

    if lead.visit_date:
        urgency = "high"
    elif lead.budget and lead.location:
        urgency = "medium"
    else:
        urgency = "low"

    if lead.budget and lead.property_type:
        alignment = "aligned"
    else:
        alignment = "unknown"

    return {
        "engagement_score": engagement,
        "conversion_probability": prob,
        "lead_temperature": temperature,
        "urgency_level": urgency,
        "budget_alignment_status": alignment,
    }


class WhatsAppAgent:
    """v3 chat agent. Delegates qualification to the shared pipeline and adds
    brochure/floorplan tools + scoring + Neo4j graph context on the reply path."""

    def _upsert_lead_snapshot(self, lead: Optional[Lead], client_id: int) -> None:
        """Best-effort Neo4j Lead upsert from current ORM fields (never raises)."""
        if not lead or not getattr(lead, "id", None):
            return
        try:
            from app.knowledge_graph.neo4j_kg import knowledge_graph

            if not knowledge_graph.available:
                return
            knowledge_graph.upsert_lead(
                lead.id,
                client_id,
                {
                    k: v
                    for k, v in {
                        "name": lead.name,
                        "location": lead.location,
                        "property_type": lead.property_type,
                        "lead_temperature": lead.lead_temperature,
                        "intent": lead.intent,
                        "conversion_probability": getattr(
                            lead, "conversion_probability", None
                        ),
                    }.items()
                    if v is not None
                },
            )
        except Exception as e:  # noqa: BLE001
            logger.debug("graph upsert skipped: %s", e)

    def _graph_extra_context(self, lead: Optional[Lead], client_id: int) -> str:
        """BD-5: best-effort Neo4j context for the LLM (never raises / blocks hard)."""
        if not lead or not getattr(lead, "id", None):
            return ""
        try:
            from app.clients.graph_client import format_graph_context_for_llm, graph_client

            # Ensure this lead exists in the graph so similarity queries can anchor.
            self._upsert_lead_snapshot(lead, client_id)

            ctx = graph_client.get_lead_context(lead.id, client_id)
            return format_graph_context_for_llm(ctx)
        except Exception as e:  # noqa: BLE001
            logger.debug("graph context skipped: %s", e)
            return ""

    async def process_chat(
        self,
        session_id: str,
        user_message: str,
        db: DBSession,
        client_id: int = 1,
        is_background: bool = False,
        dispatch_via_ae: bool = False,
    ) -> str:
        # Shared qualification core (app.agents.qualification → agent.process_chat).
        from app.agents.qualification import process_chat as qualify_chat

        lead_pre = db.query(Lead).filter(Lead.session_id == session_id).first()
        extra = self._graph_extra_context(lead_pre, client_id)

        reply = await qualify_chat(
            session_id,
            user_message,
            db,
            client_id=client_id,
            is_background=is_background,
            extra_context=extra or None,
        )

        lead = db.query(Lead).filter(Lead.session_id == session_id).first()
        if not lead:
            return reply

        # v3 enrichment: keep scores fresh on every turn.
        scores = score_lead(lead)
        for k, v in scores.items():
            setattr(lead, k, v)
        db.commit()

        # Post-turn graph sync so location/name changes in this turn land same-turn.
        self._upsert_lead_snapshot(lead, client_id)

        # v3 tool routing: brochure/floorplan reply is returned to the caller
        # (TwiML /chat JSON). Do NOT also AE-send here — that double-delivers on
        # the Twilio webhook path. Async/out-of-band sends use dispatch_via_ae=True.
        intent = detect_tool_intent(user_message)
        if intent and lead.whatsapp_opt_in:
            tool_reply = generate_brochure(lead) if intent == "brochure" else generate_floorplan(lead)
            db.add(Message(session_id=session_id, client_id=client_id, role="assistant", content=tool_reply))
            db.commit()
            if dispatch_via_ae:
                await self._dispatch_outbound(session_id, client_id, lead, tool_reply, tool=intent)
            else:
                # Timeline/SSE signal only — delivery is the TwiML/chat response body.
                try:
                    from app.clients.event_bus_client import event_bus

                    if getattr(event_bus, "_running", False):
                        await event_bus.publish(
                            f"{intent}.generated",
                            f"Client_{client_id}",
                            str(lead.id),
                            {
                                "lead_id": lead.id,
                                "session_id": session_id,
                                "tool": intent,
                                "preview": tool_reply[:200],
                            },
                            source="whatsapp_agent_v3",
                        )
                except Exception as e:  # pragma: no cover
                    logger.debug("tool event publish skipped: %s", e)
            return tool_reply

        return reply

    async def _dispatch_outbound(self, session_id, client_id, lead, text, tool="brochure"):
        """Route an outbound WhatsApp message through AE->EE (observable + DLQ).

        Only for out-of-band delivery (not when the HTTP/TwiML caller already
        returns the same text to Twilio).
        """
        try:
            await ae_submit(
                {
                    "action_type": "send_whatsapp",
                    "tenant_id": f"Client_{client_id}",
                    "entity_id": session_id,
                    "parameters": {
                        "to": lead.phone or session_id.split("_")[-1],
                        "body": text,
                        "source": "whatsapp_agent_v3",
                        "tool": tool,
                    },
                    "source": "whatsapp_agent_v3",
                }
            )
        except Exception as e:  # pragma: no cover - defensive; delivery is best-effort
            logger.warning(f"v3 outbound dispatch failed (queued best-effort): {e}")


whatsapp_agent_v3 = WhatsAppAgent()
