"""IREIOS 3.0 — Wave B.7: create_task executor (Postgres agent_tasks)."""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.execution_engine.base_executor import BaseExecutor
from app.execution_engine.execution_engine import resolve_client_id
from database import SessionLocal
from models import AgentTask

logger = logging.getLogger("executor.task")


class TaskExecutor(BaseExecutor):
    """Persist an internal agent task row (Sales escalate, ops follow-ups)."""

    action_type = "create_task"

    async def execute(self, action_request: dict) -> dict:
        params: dict[str, Any] = action_request.get("parameters") or {}
        title = (params.get("title") or "").strip()
        if not title:
            return {"status": "error", "error": "title_required"}

        client_id = resolve_client_id(action_request.get("tenant_id"))
        if client_id is None:
            raw = params.get("client_id")
            try:
                client_id = int(raw) if raw is not None else None
            except (TypeError, ValueError):
                client_id = None
        if client_id is None:
            return {"status": "error", "error": "client_id_required"}

        lead_id: Optional[int] = None
        raw_lead = params.get("lead_id")
        if raw_lead is None:
            raw_lead = action_request.get("entity_id")
        try:
            if raw_lead is not None and str(raw_lead).strip().isdigit():
                parsed = int(str(raw_lead).strip())
                if parsed > 0:
                    lead_id = parsed
        except (TypeError, ValueError):
            lead_id = None

        db = SessionLocal()
        try:
            row = AgentTask(
                client_id=client_id,
                lead_id=lead_id,
                title=title[:500],
                description=(params.get("description") or params.get("reason") or "")[:4000] or None,
                status=(params.get("status") or "open")[:40],
                assignee=(params.get("assignee") or None),
                source=(params.get("source") or action_request.get("source") or "ae")[:120],
                meta_json=params.get("meta") if isinstance(params.get("meta"), dict) else None,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            logger.info("create_task id=%s client=%s lead=%s", row.id, client_id, lead_id)
            return {
                "status": "success",
                "task_id": row.id,
                "client_id": client_id,
                "lead_id": lead_id,
                "title": row.title,
            }
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.error("create_task failed: %s", exc)
            return {"status": "error", "error": str(exc)[:200]}
        finally:
            db.close()
