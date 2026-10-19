"""Text (SMS) notification delivery via The SMS Works API.

Docs: https://www.thesmsworks.co.uk/developers
  - POST https://api.thesmsworks.co.uk/v1/message/send
  - Headers: Content-Type: application/json, Authorization: <JWT>
  - Body: {"sender": "...", "destination": "4477...", "content": "..."}

Uses the configured JWT when present; otherwise falls back to a console log
so the platform keeps working during development and testing.
"""
import logging

import requests

from ..config import settings
from ..database import get_connection, row_to_dict
from ..deps import business_tier_features
from ..phone import is_uk_number, normalise_uk_number

logger = logging.getLogger("wavebook")

SMSWORKS_API_URL = "https://api.thesmsworks.co.uk/v1/message/send"

DEFAULT_SMS_TEMPLATE = (
    "Hi {customer_name}, your booking with {business_name} is confirmed: "
    "{service_name} on {date} at {time}.{instructions} Contact: {contact_phone}"
)


def render_sms_template(booking: dict, business: dict) -> str:
    """Render the fixed SMS confirmation template with booking details.

    The message text is fixed (not owner-editable). Owners can only add
    optional special instructions (address, parking, etc.) which are appended
    via the {instructions} placeholder and omitted when not set.
    """
    instructions = (business.get("sms_instructions") or "").strip()
    values = {
        "customer_name": booking.get("customer_name", ""),
        "business_name": business.get("name", ""),
        "service_name": booking.get("service_name", ""),
        "date": booking.get("date", ""),
        "time": booking.get("time", ""),
        "contact_phone": business.get("contact_phone") or "",
        "instructions": (" " + instructions) if instructions else "",
    }
    tpl = DEFAULT_SMS_TEMPLATE
    for key, value in values.items():
        tpl = tpl.replace("{" + key + "}", str(value))
    return tpl


def send_sms(to: str, message: str) -> dict:
    """Send an SMS text message via The SMS Works. Returns delivery info."""
    if not to:
        return {"provider": "none", "message_id": "", "status": "skipped", "reason": "no recipient"}
    if not is_uk_number(to):
        # Non-UK numbers can't receive SMS Works texts; email is used instead.
        return {"provider": "none", "message_id": "", "status": "skipped", "reason": "non_uk_phone"}

    if settings.SMSWORKS_API_KEY:
        payload = {
            "sender": settings.SMSWORKS_SENDER_ID[:11],
            "destination": normalise_uk_number(to),
            "content": message,
        }
        try:
            resp = requests.post(
                SMSWORKS_API_URL,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": settings.SMSWORKS_API_KEY,
                },
                json=payload,
                timeout=15,
            )
            data = resp.json()
        except requests.RequestException as exc:
            logger.error("[SMS Works] request failed: %s", exc)
            return {"provider": "thesmsworks", "message_id": "", "status": "error", "error": str(exc)}

        if resp.status_code in (200, 201):
            return {
                "provider": "thesmsworks",
                "message_id": data.get("messageid", ""),
                "status": "sent",
            }
        logger.error("[SMS Works] send failed (%s): %s", resp.status_code, data)
        return {
            "provider": "thesmsworks",
            "message_id": "",
            "status": "error",
            "error": data,
        }

    logger.info("[SMS dev-mode] To: %s | %s", to, message)
    return {"provider": "dev-log", "message_id": "", "status": "queued"}


def sms_balance(business: dict) -> dict:
    """Return the SMS credit balance for a business (free allowance per plan, then purchased)."""
    used = int(business.get("sms_used") or 0)
    credits = int(business.get("sms_credits") or 0)
    free_limit = business_tier_features(business)["free_sms"]
    free_remaining = max(0, free_limit - used)
    return {
        "used": used,
        "free_limit": free_limit,
        "free_remaining": free_remaining,
        "credits": credits,
        "total_remaining": free_remaining + credits,
    }


def consume_sms_credit(conn, business: dict) -> bool:
    """Consume one SMS credit for a business. Returns False when the limit is reached."""
    balance = sms_balance(business)
    if balance["total_remaining"] <= 0:
        return False
    if balance["free_remaining"] > 0:
        conn.execute(
            "UPDATE businesses SET sms_used = sms_used + 1 WHERE id = ?", (business["id"],)
        )
    else:
        conn.execute(
            "UPDATE businesses SET sms_credits = sms_credits - 1 WHERE id = ?", (business["id"],)
        )
    return True


def send_business_sms(business: dict, to: str, message: str) -> dict:
    """Send an SMS on behalf of a business, consuming one SMS credit.

    The credit is only consumed when the provider accepts the message, so a
    failed send does not burn a credit.
    """
    conn = get_connection()
    try:
        fresh = row_to_dict(
            conn.execute("SELECT * FROM businesses WHERE id = ?", (business["id"],)).fetchone()
        )
        if fresh:
            business = fresh
        if not consume_sms_credit(conn, business):
            return {
                "provider": "none",
                "status": "blocked",
                "reason": "sms_limit_reached",
            }
        result = send_sms(to, message)
        if result.get("status") in ("sent", "queued"):
            conn.commit()
        else:
            conn.rollback()  # refund the credit when delivery failed
    finally:
        conn.close()
    return result


def send_booking_confirmation_sms(booking: dict, business: dict) -> dict:
    """Send the customer a confirmation text after their booking is paid/confirmed."""
    message = render_sms_template(booking, business)
    return send_business_sms(business, booking["customer_phone"], message)
