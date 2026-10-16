"""PII Redaction Utilities.

Masks personally identifiable information (emails, phone numbers) before
they are logged to event stores, emitted to streams, or rendered in timeline payloads.
"""
from __future__ import annotations

import re
from typing import Any

# Regex patterns for detection
_EMAIL_PATTERN = re.compile(
    r"\b([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b"
)
_PHONE_PATTERN = re.compile(
    r"(?:\+?\d{1,4}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\b\d{3,4}[-.\s]?(\d{4})\b"
)


def mask_email(email: str) -> str:
    """Mask email preserving the first character of username and the domain.

    Example:
        'mayank@gmail.com' -> 'm***@gmail.com'
    """
    if not email or "@" not in email:
        return email
    parts = email.split("@", 1)
    username, domain = parts[0], parts[1]
    if not username:
        return f"***@{domain}"
    return f"{username[0]}***@{domain}"


def mask_phone(phone: str) -> str:
    """Mask phone preserving only the last 4 digits in a standard format.

    Example:
        '+919876541234' -> '***-***-1234'
        '987-654-1234'  -> '***-***-1234'
    """
    if not phone:
        return phone
    digits = re.sub(r"\D", "", phone)
    if len(digits) >= 7:
        return f"***-***-{digits[-4:]}"
    return phone


def mask_name(name: str) -> str:
    """Mask name/contact/company field preserving only the first character of each word.

    Examples:
        'Mayank Jindal' -> 'M*** J***'
        'Acme Real Estate' -> 'A*** R*** E***'
        'Alice' -> 'A***'
    """
    if not name or not isinstance(name, str):
        return name
    words = name.strip().split()
    if not words:
        return name
    return " ".join(f"{w[0]}***" if len(w) > 0 else "***" for w in words)


def redact_text(text: str) -> str:
    """Mask all emails and phone numbers embedded inside free-form text."""
    if not isinstance(text, str):
        return text

    # Mask emails
    text = _EMAIL_PATTERN.sub(r"\1***@\2", text)

    # Mask phone numbers (matches 7+ digits sequences)
    def _phone_sub(m: re.Match) -> str:
        full = m.group(0)
        digits = re.sub(r"\D", "", full)
        if len(digits) >= 7:
            return f"***-***-{digits[-4:]}"
        return full

    phone_sequence = re.compile(
        r"(?:\+?\d{1,4}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{4}"
    )
    return phone_sequence.sub(_phone_sub, text)


def redact_payload(obj: Any) -> Any:
    """Recursively redacts PII (emails, phone numbers, names, and companies) in dicts, lists, and strings.

    Field keys explicitly associated with email, phone, name, or company are directly formatted with
    standard mask shapes.
    """
    if isinstance(obj, dict):
        redacted = {}
        for k, v in obj.items():
            key_lower = str(k).lower()
            if any(term in key_lower for term in ("email", "mail")) and isinstance(v, str):
                redacted[k] = mask_email(v)
            elif any(
                term in key_lower
                for term in ("phone", "mobile", "whatsapp", "caller", "from_number", "to_number")
            ) and isinstance(v, str):
                redacted[k] = mask_phone(v)
            elif any(
                term in key_lower
                for term in ("company", "company_name")
            ) and isinstance(v, str):
                redacted[k] = mask_name(v)
            elif any(
                term in key_lower
                for term in (
                    "name",
                    "full_name",
                    "first_name",
                    "last_name",
                    "contact_name",
                    "lead_name",
                    "customer_name",
                    "user_name",
                    "agent_name",
                )
            ) and isinstance(v, str):
                if key_lower in (
                    "event_name",
                    "model_name",
                    "table_name",
                    "class_name",
                    "file_name",
                    "filename",
                    "endpoint_name",
                    "service_name",
                    "queue_name",
                    "task_name",
                    "action_name",
                    "template_name",
                ):
                    redacted[k] = v
                else:
                    redacted[k] = mask_name(v)
            else:
                redacted[k] = redact_payload(v)
        return redacted
    elif isinstance(obj, list):
        return [redact_payload(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(redact_payload(item) for item in obj)
    elif isinstance(obj, str):
        return redact_text(obj)
    return obj
