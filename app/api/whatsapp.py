import logging
from urllib.parse import urlparse, urlunparse
from fastapi import Request, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession
from twilio.request_validator import RequestValidator

import models
from database import get_db
from config import tenant_id_ctx, settings

logger = logging.getLogger("twilio_auth")


def get_effective_request_url(request: Request) -> str:
    """Reconstructs the authentic external URL that Twilio signed against,

    properly handling reverse proxies, SSL termination, and forwarded headers.
    """
    url = str(request.url)

    # 1. Forwarded Protocol (SSL termination at reverse proxy / load balancer)
    forwarded_proto = request.headers.get("x-forwarded-proto")
    if forwarded_proto:
        # Proxies may send comma-separated list e.g. "https, http"
        proto = forwarded_proto.split(",")[0].strip().lower()
        if proto == "https" and url.startswith("http://"):
            url = "https://" + url[len("http://"):]
        elif proto == "http" and url.startswith("https://"):
            url = "http://" + url[len("https://"):]
    elif settings.IS_PRODUCTION and url.startswith("http://"):
        url = "https://" + url[len("http://"):]

    # 2. Forwarded Host (if reverse proxy alters the host header)
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_host:
        host = forwarded_host.split(",")[0].strip()
        parsed = urlparse(url)
        url = urlunparse(parsed._replace(netloc=host))

    return url


async def validate_twilio_request(
    request: Request,
    db: DBSession = Depends(get_db)
) -> models.Client:
    """FastAPI security dependency for Twilio WhatsApp/SMS webhooks.

    1. Extracts payload parameters (To, AccountSid) from application/x-www-form-urlencoded data.
    2. Resolves destination tenant from the clients table.
       - Rejects unmapped/unregistered recipients with HTTP 404 immediately.
       - NEVER trusts URL path or query parameters for tenant identity.
    3. Fetches the tenant's specific Twilio Auth Token.
    4. Validates the X-Twilio-Signature header using RequestValidator against the full URL and POST body.
       - Accounts for proxy SSL termination via X-Forwarded-Proto.
       - Fails closed with HTTP 401 if signature is missing, invalid, or mismatched.
    5. Sets tenant context and returns the authenticated Client model instance.
    """
    # 1. Extract application/x-www-form-urlencoded body
    try:
        form_data = await request.form()
    except Exception as exc:
        logger.warning("Twilio webhook: Failed to parse form-encoded payload: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid form-encoded payload",
        )

    to_number = form_data.get("To")
    account_sid = form_data.get("AccountSid")

    if not to_number and not account_sid:
        logger.warning("Twilio webhook rejected: Missing destination number (To) and AccountSid.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Destination recipient or AccountSid is missing",
        )

    # 2. Tenant Resolution based strictly on incoming destination configuration
    client = None
    if to_number:
        clean_to = str(to_number).replace("whatsapp:", "").strip()
        # Query active client matching phone number
        client = db.query(models.Client).filter(
            models.Client.is_active.is_(True),
            (
                (models.Client.twilio_phone_number == str(to_number).strip()) |
                (models.Client.twilio_phone_number == clean_to) |
                (models.Client.twilio_phone_number == f"whatsapp:{clean_to}")
            )
        ).first()

        # Fallback: check JSONB settings if column not populated
        if not client:
            candidates = db.query(models.Client).filter(models.Client.is_active.is_(True)).all()
            for cand in candidates:
                cand_phone = (cand.settings or {}).get("twilio_phone_number", "")
                if cand_phone and cand_phone.replace("whatsapp:", "").strip() == clean_to:
                    client = cand
                    break

    if not client and account_sid:
        client = db.query(models.Client).filter(
            models.Client.is_active.is_(True),
            models.Client.twilio_account_sid == str(account_sid).strip()
        ).first()
        if not client:
            candidates = db.query(models.Client).filter(models.Client.is_active.is_(True)).all()
            for cand in candidates:
                if (cand.settings or {}).get("twilio_account_sid") == str(account_sid).strip():
                    client = cand
                    break

    if not client:
        logger.warning(
            "Twilio webhook rejected: No active tenant mapped to destination To=%s, AccountSid=%s",
            to_number, account_sid
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active tenant configured for this Twilio recipient",
        )

    # 3. Retrieve Tenant Twilio Auth Token
    auth_token = client.twilio_auth_token or (client.settings or {}).get("twilio_auth_token")
    if not auth_token:
        logger.error("Tenant %s is missing twilio_auth_token in credentials.", client.id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant Twilio credentials not configured",
        )

    # 4. Twilio SDK Signature Validation
    signature = request.headers.get("X-Twilio-Signature")
    if not signature:
        logger.warning("Twilio webhook rejected: Missing X-Twilio-Signature header for tenant %s", client.id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Twilio-Signature header",
        )

    effective_url = get_effective_request_url(request)
    validator = RequestValidator(auth_token)

    # Convert FormData to dictionary for validation
    params = {k: v for k, v in form_data.items() if isinstance(v, str)}

    if not validator.validate(effective_url, params, signature):
        logger.warning(
            "SECURITY ALERT: Invalid Twilio signature for tenant %s against URL %s",
            client.id, effective_url
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Twilio signature",
        )

    # 5. Bind tenant context and return authenticated client
    tenant_id_ctx.set(f"Client_{client.id}")
    return client
