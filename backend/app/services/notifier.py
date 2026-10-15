"""Text (SMS) notification delivery via The SMS Works API.

Docs: https://www.thesmsworks.co.uk/developers
  - POST https://api.thesmsworks.co.uk/v1/message/send
  - Headers: Content-Type: application/json, Authorization: <JWT>
  - Body: {"sender": "...", "destination": "4477...", "content": "..."}

Uses the configured JWT when present; otherwise falls back to a console log
so the platform keeps working during development and testing.
"""
import logging
import re

import requests

from ..config import settings

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


def _normalise_uk_number(phone: str) -> str:
    """Convert a UK phone number to international format (e.g. 07xxx -> 447xxx)."""
    digits = re.sub(r"[^0-9+]", "", phone or "")
    if digits.startswith("+44"):
        return digits[1:]  # 44...
    if digits.startswith("44") and len(digits) == 12:
        return digits
    if digits.startswith("0") and len(digits) == 11:
        return "44" + digits[1:]
    return digits


def send_sms(to: str, message: str) -> dict:
    """Send an SMS text message via The SMS Works. Returns delivery info."""
    if not to:
        return {"provider": "none", "message_id": "", "status": "skipped", "reason": "no recipient"}

    if settings.SMSWORKS_API_KEY:
        payload = {
            "sender": settings.SMSWORKS_SENDER_ID[:11],
            "destination": _normalise_uk_number(to),
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


def send_booking_confirmation_sms(booking: dict, business: dict) -> dict:
    """Send the customer a confirmation text after their booking is paid/confirmed."""
    message = render_sms_template(booking, business)
    return send_sms(booking["customer_phone"], message)
