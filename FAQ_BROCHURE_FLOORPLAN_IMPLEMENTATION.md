# FAQ, Brochure & Floor Plan Sharing — Implementation Guide

## Overview

This document details the exact implementation of an **Event-Driven Execution Engine** for handling FAQ automation, brochure sharing, and floor plan sharing. The implementation introduces 4 pieces:

1. **Event Bus Client** — publishes `brochure.sent` / `floorplan.sent` events
2. **System Prompt Update** — teaches Gemini when to use document tools vs. RAG FAQ
3. **AI Agent Tools** — `share_brochure` / `share_floor_plan` registered with Gemini
4. **Execution Engine** — Twilio media dispatch + Event Bus publish

---

## File 1: `app/clients/__init__.py` — CREATE

Empty file. Enables `from app.clients.event_bus_client import publish_event`.

```python
# app/clients/__init__.py
```

---

## File 2: `app/clients/event_bus_client.py` — CREATE

```python
import logging
import json
from datetime import datetime, timezone
import httpx

logger = logging.getLogger("event_bus")

# Aritro will provide the real URL once the Event Bus is live
EVENT_BUS_URL = "http://localhost:8000/api/v1/mock-event-bus"

async def publish_event(event_type: str, tenant_id: int, entity_id: str, payload: dict):
    """
    Publishes an event to the Central Event Bus (Aritro's domain)
    so it feeds into the Company Memory and AI Timeline.
    """
    event_data = {
        "event_id": f"evt_{int(datetime.now().timestamp())}",
        "event_type": event_type,
        "tenant_id": f"tenant_{tenant_id}",
        "entity_type": "lead",
        "entity_id": str(entity_id),
        "source": "whatsapp_ai",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": payload
    }

    logger.info(f"⚡ [EVENT BUS] Publishing: {event_type}")
    logger.info(json.dumps(event_data, indent=2))

    # Ready to be uncommented when Aritro's API is ready
    # async with httpx.AsyncClient() as client:
    #     try:
    #         await client.post(EVENT_BUS_URL, json=event_data, timeout=3.0)
    #     except Exception as e:
    #         logger.error(f"Failed to publish to Event Bus: {e}")
```

---

## File 3: `system_prompt.py` — EDIT

**Insert** 12 lines before the `🔹 TOOL USE RULE` section (before line 57).

### Insertion point

After:

```
- Make sure your follow-ups are specific to real estate constraints (budget, location, timeline, BHK) rather than generic ("How else can I help?").

-----------------------------------
```

Before:

```
🔹 TOOL USE RULE (CRITICAL — MANDATORY):
```

### New content to insert:

```
-----------------------------------
🔹 FAQ & DOCUMENT SHARING RULES:
- FAQ: If the user asks about amenities, location, hospitals, maintenance, or pricing, answer them naturally using the provided "Property Context". Do NOT use document tools for general questions.
- BROCHURES: If a user explicitly asks for a "brochure", "catalog", or "project details PDF", use the `share_brochure` tool.
- FLOOR PLANS: If a user asks for a "floor plan", "layout", "map", or "dimensions image", use the `share_floor_plan` tool.
- MISSING INFO: If the user asks for a document but hasn't specified a location/project yet, ask them for the location first before sending the document.

-----------------------------------
```

---

## File 4: `agent.py` — EDIT (5 changes)

### Change 4a: Expand `PROPERTY_KEYWORDS` (line ~585)

**Before:**

```python
PROPERTY_KEYWORDS = {
    "flat", "bhk", "rent", "buy", "invest", "area", "location", "baner", "wakad",
    "hinjewadi", "price", "budget", "property", "apartment", "villa", "plot",
    "2bhk", "3bhk", "1bhk", "pune", "noida", "mumbai", "sqft", "furnish",
    "visit", "book", "schedule", "bedroom", "floor", "tower", "society",
    "possession", "ready", "availability", "cheap", "affordable", "luxury",
    "options", "available"
}
```

**After:**

```python
PROPERTY_KEYWORDS = {
    "flat", "bhk", "rent", "buy", "invest", "area", "location", "baner", "wakad",
    "hinjewadi", "price", "budget", "property", "apartment", "villa", "plot",
    "2bhk", "3bhk", "1bhk", "pune", "noida", "mumbai", "sqft", "furnish",
    "visit", "book", "schedule", "bedroom", "floor", "tower", "society",
    "possession", "ready", "availability", "cheap", "affordable", "luxury",
    "options", "available",
    # FAQ & Document Keywords
    "amenities", "school", "hospital", "maintenance", "parking", "pool", "gym", "security",
    "brochure", "catalog", "pdf", "floor plan", "layout", "map", "dimensions"
}
```

### Change 4b: Add tool functions (between line 214 and line 218)

Insert after `extract_lead_info` (ends at `pass` on line 214), before model initialization (line 218).

```python
def share_brochure(location: str, property_type: str, conversational_reply: str):
    """
    Call this tool ONLY when the user explicitly asks for a brochure, catalog, or project details PDF.
    Args:
        location: The area the user is interested in (e.g., 'Baner').
        property_type: The property type (e.g., '2BHK'). MUST remain empty/None if not specified.
        conversational_reply: A friendly text reply to accompany the file (e.g., "Here is the brochure for Baner 2BHKs!").
    """
    pass

def share_floor_plan(location: str, property_type: str, conversational_reply: str):
    """
    Call this tool ONLY when the user asks for a floor plan, layout, map, or dimensions.
    Args:
        location: The area the user is interested in.
        property_type: The property type. MUST remain empty/None if not specified.
        conversational_reply: A friendly text reply to accompany the image.
    """
    pass
```

### Change 4c: Update model initialization (line ~221)

**Before:**

```python
tools=[extract_lead_info]
```

**After:**

```python
tools=[extract_lead_info, share_brochure, share_floor_plan]
```

### Change 4d: Restructure FC routing (lines ~738-845)

This is the core change. Replace the single-branch tool handler with an `if/elif` pattern.

**Before (current structure):**

```python
fc = None
if response.candidates and response.candidates[0].content.parts:
    for part in response.candidates[0].content.parts:
        if part.function_call:
            fc = part.function_call
            if fc and fc.name == "extract_lead_info":
                # ... extract_lead_info logic ...
                extracted_early = True
                break
```

**After:**

```python
fc = None
if response.candidates and response.candidates[0].content.parts:
    for part in response.candidates[0].content.parts:
        if part.function_call:
            fc = part.function_call

            # ==========================================
            # ACTION: EXTRACT LEAD INFO
            # ==========================================
            if fc.name == "extract_lead_info":
                args = normalize_lead_data(dict(fc.args), existing_intent=lead.intent)
                # ... KEEP ALL EXISTING extract_lead_info LOGIC EXACTLY AS-IS ...
                # (budget/location updating, new_fields set, text fallback, etc.)
                final_text = local_reply
                extracted_early = True
                break

            # ==========================================
            # ACTION: SHARE BROCHURE OR FLOOR PLAN
            # ==========================================
            elif fc.name in ["share_brochure", "share_floor_plan"]:
                args = dict(fc.args)
                location_arg = args.get("location", "Unknown")
                property_type_arg = args.get("property_type", "")

                # Extract Gemini's text from the tool call arguments
                final_text = args.get("conversational_reply", "Here is the document you requested!")
                doc_type = "Brochure" if fc.name == "share_brochure" else "Floor Plan"
                event_name = "brochure.sent" if fc.name == "share_brochure" else "floorplan.sent"

                # 1. SEND MEDIA VIA TWILIO (Execution Engine)
                if settings.TWILIO_ACCOUNT_SID and lead.phone:
                    # Dummy URLs representing Aritro's future Document Knowledge Graph
                    media_url = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf" if fc.name == "share_brochure" else "https://dummyimage.com/600x400/000/fff&text=Floor+Plan"

                    try:
                        from twilio.rest import Client
                        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
                        to_num = f"whatsapp:{lead.phone}" if not lead.phone.startswith("whatsapp:") else lead.phone

                        client.messages.create(
                            from_=settings.TWILIO_PHONE_NUMBER,
                            body=final_text,
                            media_url=[media_url],
                            to=to_num
                        )
                        logger.info(f"✅ Executed {doc_type} dispatch to {to_num}")
                    except Exception as e:
                        logger.error(f"❌ Failed to send {doc_type} via Twilio: {e}")

                # 2. PUBLISH TO EVENT BUS (The Master Rule)
                from app.clients.event_bus_client import publish_event

                asyncio.create_task(publish_event(
                    event_type=event_name,
                    tenant_id=client_id,
                    entity_id=lead.id,
                    payload={
                        "document_type": doc_type,
                        "location_requested": location_arg,
                        "property_type": property_type_arg,
                        "message": final_text
                    }
                ))

                # 3. Save Context to DB Memory
                db.add(Message(session_id=session_id, client_id=client_id, role="assistant", content=f"[{doc_type} Shared] {final_text}"))
                db.commit()

                message_saved = True  # ⚠️ Prevents duplicate save at line 1035
                extracted_early = True
                break
```

**⚠️ Important:** The `message_saved = True` flag is critical. Without it, the generic message save at line 1035 (`if not locals().get('message_saved', False)`) will create a duplicate `[Brochure Shared] ...` / `[Floor Plan Shared] ...` entry.

---

## Verification Checklist

After implementing, verify each step:

| # | Check | Command |
|---|-------|---------|
| 1 | Event bus client imports | `python -c "from app.clients.event_bus_client import publish_event"` |
| 2 | Model has 3 tools | Check `agent.py` line ~221: `tools=[extract_lead_info, share_brochure, share_floor_plan]` |
| 3 | RAG triggers on FAQ keywords | Message "amenities in Baner" should set `is_rag_eligible = True` |
| 4 | Test runner passes | `python test_runner.py` (tests C04, C14, C26, W04, H01, A07 involve brochures/floor plans) |
| 5 | Stress test passes | `python task3_runner.py` (test W07 = "Requests Floor Plan") |

## Rollback Plan

If any change causes regressions:
1. Revert `agent.py` changes — remove tool functions, restore `tools=[extract_lead_info]`, restore single-branch FC handler, restore original `PROPERTY_KEYWORDS`
2. Revert `system_prompt.py` — remove the inserted FAQ & Document Sharing Rules block
3. Delete `app/clients/event_bus_client.py` and `app/clients/__init__.py`

The execution engine for extract_lead_info is entirely unchanged (unsurrounded), so lead extraction will continue working immediately after revert.
