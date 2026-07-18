"""IREIOS 3.0 — Phase 7.5–7.7: Conversation Memory layer.

`ConversationMemory` persists structured per-lead memory items in Postgres
(`lead_memories`) so the agent can recall facts/preferences/objections across
sessions without re-reading the full message history. Client-scoped for
tenant isolation. Also offers a lightweight `summarize` over recent messages.

See plans/IREIOS_3.0_STEP_BY_STEP_EXPANSION.md (Phase 7) and
plans/IREIOS_3.0_EXPANSION_CHANGELOG.md.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from models import Lead, LeadMemory, Message

logger = logging.getLogger("conversation_memory")


class ConversationMemory:
    """Persistent, client-scoped lead memory."""

    def remember(self, db: Session, *, lead_id: int, client_id: int, key: str,
                 value: str, session_id: Optional[str] = None,
                 memory_type: str = "fact") -> LeadMemory:
        item = LeadMemory(
            client_id=client_id, lead_id=lead_id, session_id=session_id,
            key=key, value=value, memory_type=memory_type,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    def recall(self, db: Session, *, lead_id: int, client_id: int,
               key: Optional[str] = None, memory_type: Optional[str] = None) -> list:
        q = db.query(LeadMemory).filter(
            LeadMemory.lead_id == lead_id, LeadMemory.client_id == client_id
        )
        if key:
            q = q.filter(LeadMemory.key == key)
        if memory_type:
            q = q.filter(LeadMemory.memory_type == memory_type)
        return q.order_by(LeadMemory.id.desc()).all()

    def summarize_recent(self, db: Session, *, session_id: str, turns: int = 6) -> str:
        """Deterministic text summary of the last `turns` message pairs."""
        msgs = (
            db.query(Message)
            .filter(Message.session_id == session_id)
            .order_by(Message.id.desc())
            .limit(turns * 2)
            .all()
        )
        msgs.reverse()
        parts = []
        for m in msgs:
            role = "User" if m.role == "user" else "Agent"
            parts.append(f"{role}: {m.content}")
        return "\n".join(parts)

    def extract_and_store(self, db: Session, *, lead: Lead, client_id: int,
                          user_message: str) -> list:
        """Store a few deterministic memory facts derived from the lead row.

        Returns the LeadMemory rows created. Best-effort; never raises.
        """
        created = []
        facts = {
            "name": lead.name,
            "location": lead.location,
            "budget": lead.budget,
            "property_type": lead.property_type,
            "intent": lead.intent,
        }
        for k, v in facts.items():
            if v:
                created.append(self.remember(
                    db, lead_id=lead.id, client_id=client_id, key=k, value=str(v),
                    session_id=lead.session_id, memory_type="fact",
                ))
        return created


conversation_memory = ConversationMemory()
