"""IREIOS 3.0 — Phase 10.1: Placeholder agents (Layer-2 names).

Registers the remaining Layer-2 agent names (Pricing, Negotiation, Inventory,
Legal, Finance, etc.) as `status=placeholder` with a log-only no-op handler.
The CEO already skips `placeholder` records (Task 1.4), so they are visible in
`CEOOrchestrator.list_agents()` but never invoked on the runtime path.

This satisfies Phase 10.1 (placeholders registered; `list_agents` shows active
+ placeholders) without fabricating behaviour for agents not yet built.

See plans/IREIOS_3.0_STEP_BY_STEP_EXPANSION.md (Phase 10) and
plans/IREIOS_3.0_EXPANSION_CHANGELOG.md.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.orchestrator.ceo_orchestrator import CEOOrchestrator

logger = logging.getLogger("placeholders")

# Layer-2 agent names reserved for future IREIOS 3.0 builds.
# NOTE: marketing_agent, customer_success_agent, crm_automation, lead_scoring,
# and kg_event_writer are now REAL active agents (registered in main.py lifespan)
# and are intentionally no longer placeholders. `retention_agent` responsibilities
# are covered by customer_success_agent (renewal.due / payment.due handling).
PLACEHOLDER_AGENTS = [
    "pricing_agent",
    "negotiation_agent",
    "inventory_agent",
    "legal_agent",
    "finance_agent",
    "onboarding_agent",
]


async def _placeholder_handler(event: dict) -> None:
    """Log-only no-op. Placeholder agents never perform side effects."""
    logger.debug(f"[placeholder] {event.get('event_type')} received by placeholder agent (no-op)")


def register_placeholders(ceo: Optional[CEOOrchestrator] = None) -> list[str]:
    """Register all Layer-2 placeholder agents on the CEO/registry.

    Idempotent — re-registering is a no-op (registry overwrites by agent_id).
    Returns the list of registered placeholder agent ids.
    """
    if ceo is None:
        from app.orchestrator.ceo_orchestrator import ceo as default_ceo
        ceo = default_ceo
    for agent_id in PLACEHOLDER_AGENTS:
        ceo.register_agent(agent_id, _placeholder_handler, subscriptions=["*"], status="placeholder")
    logger.info(f"Registered {len(PLACEHOLDER_AGENTS)} placeholder agents")
    return list(PLACEHOLDER_AGENTS)
