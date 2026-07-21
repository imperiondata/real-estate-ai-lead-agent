"""Named AE template: hot-lead notification action_request.

Returns a dict suitable for ``ae_submit``. The caller may override
``template_type`` (default ``"linear"``) to route through n8n etc.
"""


def build_hot_lead_action(
    *,
    tenant_id: str,
    lead_id: int,
    lead_name: str = "",
    lead_phone: str = "",
    score: float = 0.0,
    template_type: str = "linear",
    workflow_id: str = "",
) -> dict:
    return {
        "action_type": "notify_agent",
        "tenant_id": tenant_id,
        "entity_id": str(lead_id),
        "parameters": {
            "kind": "hot_lead",
            "lead_name": lead_name,
            "lead_phone": lead_phone,
            "score": score,
            "message": f"Hot lead alert: {lead_name or lead_phone} (score={score})",
        },
        "template_type": template_type,
        "workflow_id": workflow_id,
        "source": "hot_lead_notify_template",
    }
