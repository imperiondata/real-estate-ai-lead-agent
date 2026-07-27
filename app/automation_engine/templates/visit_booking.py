"""Named AE template: visit-booking action_request.

Returns a dict suitable for ``ae_submit``. The caller may override
``template_type`` (default ``"linear"``) to route through n8n etc.
"""


def build_visit_action(
    *,
    tenant_id: str,
    lead_id: int,
    visit_date: str,
    lead_name: str = "",
    lead_phone: str = "",
    property_type: str = "",
    template_type: str = "linear",
    workflow_id: str = "",
) -> dict:
    return {
        "action_type": "schedule_visit",
        "tenant_id": tenant_id,
        "entity_id": str(lead_id),
        "parameters": {
            "visit_date": visit_date,
            "lead_name": lead_name,
            "lead_phone": lead_phone,
            "property_type": property_type,
            "message": f"Site visit booked: {lead_name or lead_phone} at {visit_date}",
        },
        "template_type": template_type,
        "workflow_id": workflow_id,
        "source": "visit_booking_template",
    }
