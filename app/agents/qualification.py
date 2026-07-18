"""Canonical lead-qualification entrypoint (BD-3).

Implementation remains in root ``agent.py`` (proven pipeline). All production
callers should import ``process_chat`` from here — not from ``main`` dual paths.
WhatsAppAgent is the default orchestrator; this module is the shared core it
delegates to (and the emergency legacy path when FEATURE_WHATSAPP_V3=false).
"""
from __future__ import annotations

from agent import process_chat

__all__ = ["process_chat"]
