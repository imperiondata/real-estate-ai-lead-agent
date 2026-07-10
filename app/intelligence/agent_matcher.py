from typing import Optional

from sqlalchemy.orm import Session

from models import Agent, Lead
from app.intelligence.feedback_loop import get_agent_success_rate

# Classifier labels → accepted agent.speciality / lead_type values (P1.6)
SPECIALITY_ALIASES = {
    "investor": frozenset({"investor", "investment"}),
    "tenant": frozenset({"tenant", "rental"}),
    "luxury": frozenset({"luxury", "premium"}),
    "buyer": frozenset({"buyer", "mid_range", "mid-range", "midrange"}),
}


def classify_lead_type(query: str) -> str:
    text = query.lower()
    if any(w in text for w in ["investment", "roi", "returns", "yield", "appreciation"]):
        return "investor"
    if any(w in text for w in ["rent", "lease", "rental"]):
        return "tenant"
    if any(w in text for w in ["luxury", "premium", "villa", "penthouse"]):
        return "luxury"
    return "buyer"


def detect_deal_size(query: str) -> str:
    text = query.lower()
    if "cr" in text or "crore" in text:
        return "high"
    if "lakh" in text or "lac" in text:
        return "medium"
    return "low"


def detect_urgency(query: str) -> str:
    text = query.lower()
    high_urgency = ["urgent", "immediately", "asap", "this week", "closing soon", "loan approved"]
    return "high" if any(w in text for w in high_urgency) else "medium"


def normalize_location_token(value: str) -> str:
    return " ".join((value or "").lower().strip().split())


def specialities_match(lead_type: str, agent_speciality: Optional[str]) -> bool:
    """P1.6: map classifier types to agent speciality vocabulary."""
    if not agent_speciality:
        return False
    lt = (lead_type or "").lower().strip()
    sp = (agent_speciality or "").lower().strip()
    if lt == sp:
        return True
    aliases = SPECIALITY_ALIASES.get(lt, frozenset({lt}))
    return sp in aliases or any(a in sp or sp in a for a in aliases if a)


def location_match_score(lead_location: Optional[str], agent_locations: Optional[str]) -> int:
    """
    P1.7: exact / membership → 40; substring either way → 25; else 0.
    """
    if not lead_location or not agent_locations:
        return 0
    lead_locs = [normalize_location_token(l) for l in lead_location.split(",") if l.strip()]
    agent_locs = [normalize_location_token(l) for l in agent_locations.split(",") if l.strip()]
    if not lead_locs or not agent_locs:
        return 0

    for ll in lead_locs:
        for al in agent_locs:
            if ll == al:
                return 40
    for ll in lead_locs:
        for al in agent_locs:
            if ll in al or al in ll:
                return 25
    return 0


def count_open_leads_for_agent(db: Session, client_id: int, agent_name: str) -> int:
    """P1.8: live open-lead load for scoring."""
    if not agent_name:
        return 0
    return (
        db.query(Lead)
        .filter(
            Lead.client_id == client_id,
            Lead.assigned_agent == agent_name,
            Lead.conversion_status == "open",
        )
        .count()
    )


def resolve_followup_agent_label(lead, client=None) -> Optional[str]:
    """
    P1.9: never invent demo agency names.
    Prefer real assignee; else client company name; else None (omit sentence).
    """
    name = getattr(lead, "assigned_agent", None) if lead else None
    if name and str(name).strip() and str(name).strip() != "ABC Properties Team":
        return str(name).strip()
    if client is not None:
        company = getattr(client, "company_name", None)
        if company and str(company).strip():
            return str(company).strip()
    return None


def calculate_dynamic_agent_score(base_score, learned_rate, lead_type, urgency, response_speed_score=50, active_leads=0):
    score = base_score
    score += int(learned_rate / 4)
    score += int(response_speed_score / 5)
    if lead_type == "investor" and learned_rate >= 60:
        score += 18
    if urgency == "high":
        score += 12
    score -= int(active_leads * 1.8)
    return score


def apply_workload_on_assignment(db: Session, client_id: int, previous_name: Optional[str], new_name: Optional[str]) -> None:
    """
    P1.3: Adjust active_leads only when the assignee changes.
    Same agent reselected → no increment. Reassignment → +1 new, -1 previous (floor 0).
    Does not commit; caller owns the transaction.
    """
    if not new_name or previous_name == new_name:
        return

    new_agent = db.query(Agent).filter(
        Agent.client_id == client_id,
        Agent.name == new_name,
    ).first()
    if new_agent:
        new_agent.active_leads = (new_agent.active_leads or 0) + 1

    if previous_name:
        old_agent = db.query(Agent).filter(
            Agent.client_id == client_id,
            Agent.name == previous_name,
        ).first()
        if old_agent:
            old_agent.active_leads = max(0, (old_agent.active_leads or 0) - 1)


def match_best_agent(db: Session, client_id: int, location: str, query: str, *, apply_workload: bool = False):
    """
    Dynamically routes a lead to the best agent for this specific tenant (client_id).

    By default does NOT bump active_leads (P1.3). Call apply_workload_on_assignment
    via ensure_lead_assignment when the assignee actually changes.
    apply_workload=True preserves legacy +1 behavior for any external callers.
    """
    agents = db.query(Agent).filter(Agent.client_id == client_id).all()
    if not agents:
        return {"assigned_agent": None, "agent_name": None, "match_score": 0}

    lead_type = classify_lead_type(query)
    deal_size = detect_deal_size(query)
    urgency = detect_urgency(query)

    best_agent = None
    best_score = -1

    for agent in agents:
        score = 0

        score += location_match_score(location, agent.locations)

        if deal_size == agent.deal_size:
            score += 20
        if lead_type == agent.lead_type or specialities_match(lead_type, agent.lead_type):
            score += 25
        if specialities_match(lead_type, agent.speciality):
            score += 30

        score += int((agent.conversion_rate or 30) / 5)
        try:
            learned_rate = max(agent.conversion_rate or 30, get_agent_success_rate(agent.name))
        except Exception:
            learned_rate = agent.conversion_rate or 30

        # P1.8: prefer live open-lead count for load penalty
        try:
            open_load = count_open_leads_for_agent(db, client_id, agent.name)
        except Exception:
            open_load = agent.active_leads or 0

        score = calculate_dynamic_agent_score(
            score, learned_rate, lead_type, urgency, agent.response_speed_score or 50, open_load
        )

        if open_load > 18:
            score -= 25

        if score > best_score:
            best_score = score
            best_agent = agent

    if not best_agent:
        return {"assigned_agent": None, "agent_name": None, "match_score": 0}

    if apply_workload:
        best_agent.active_leads = (best_agent.active_leads or 0) + 1
        db.commit()

    return {
        "assigned_agent": best_agent.name,
        "agent_name": best_agent.name,
        "match_score": best_score,
        "agent_data": {"name": best_agent.name, "phone": best_agent.phone, "email": best_agent.email},
    }


def ensure_lead_assignment(
    db: Session,
    lead,
    client_id: int,
    query: str,
    *,
    force: bool = False,
) -> Optional[str]:
    """
    P1.1 / P1.2: Sticky-until-claimed assignment.

    - If conversion_status == claimed and not force: return existing assignee (no rematch).
    - Else match and set lead.assigned_agent when a name is returned.
    - Workload counters only change when the assignee changes (P1.3).
    Caller owns commit and optional EventLog audit.
    """
    if not lead:
        return None

    if getattr(lead, "conversion_status", None) == "claimed" and not force:
        return lead.assigned_agent

    previous = lead.assigned_agent
    agent_data = match_best_agent(
        db=db,
        client_id=client_id,
        location=getattr(lead, "location", None) or "",
        query=query or "",
        apply_workload=False,
    )
    new_name = agent_data.get("assigned_agent")
    if not new_name:
        return lead.assigned_agent

    if previous != new_name:
        apply_workload_on_assignment(db, client_id, previous, new_name)
        lead.assigned_agent = new_name

    return lead.assigned_agent


def hot_threshold_notification_reason(probability: int) -> str:
    """P1.10: score-path reason must not claim explicit human request."""
    return f"Lead crossed HOT threshold (conversion_probability ≥ {probability})"
