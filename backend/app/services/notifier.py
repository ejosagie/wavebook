"""Text (SMS) notification delivery.

Uses Twilio when configured; otherwise falls back to a console log so the
platform keeps working during development and testing.
"""
import logging

from ..config import settings

logger = logging.getLogger("wavebook")


def send_sms(to: str, message: str) -> dict:
    """Send an SMS text message. Returns delivery info."""
    if not to:
        return {"provider": "none", "sid": "", "status": "skipped", "reason": "no recipient"}

    if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_FROM_NUMBER:
        from twilio.rest import Client

        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        msg = client.messages.create(to=to, from_=settings.TWILIO_FROM_NUMBER, body=message)
        return {"provider": "twilio", "sid": msg.sid, "status": msg.status}

    logger.info("[SMS dev-mode] To: %s | %s", to, message)
    return {"provider": "dev-log", "sid": "", "status": "queued"}


def send_booking_confirmation_sms(booking: dict, business: dict) -> dict:
    """Send the customer a confirmation text after their booking is paid/confirmed."""
    message = (
        f"Hi {booking['customer_name']}, your booking with {business['name']} is confirmed: "
        f"{booking['service_name']} on {booking['date']} at {booking['time']}. "
        f"See you soon!"
    )
    return send_sms(booking["customer_phone"], message)
