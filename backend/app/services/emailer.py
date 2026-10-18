"""Email delivery via the PHP relay on the NeuroWaves hosting.

The VPS POSTs JSON to NOTIFY_URL with the NOTIFY_TOKEN header; the PHP script
sends the mail with the hosting's mail(). When NOTIFY_TOKEN is not set, emails
are logged instead so the platform keeps working during development and testing.
"""
import json
import logging
import urllib.request

from ..config import settings

logger = logging.getLogger("wavebook")


def send_email(to: str, subject: str, body_text: str) -> dict:
    """Send a plain-text email. Returns delivery info."""
    if not to:
        return {"provider": "none", "status": "skipped", "reason": "no recipient"}

    if settings.NOTIFY_TOKEN:
        payload = json.dumps({"to": to, "subject": subject, "body": body_text}).encode("utf-8")
        req = urllib.request.Request(
            settings.NOTIFY_URL,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Notify-Token": settings.NOTIFY_TOKEN,
                "User-Agent": "WaveBook/1.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf-8") or "{}")
            return {"provider": "php-relay", "status": result.get("status", "sent"), "to": to}
        except Exception as exc:  # pragma: no cover
            logger.error("[email] relay send failed: %s", exc)
            return {"provider": "php-relay", "status": "error", "error": str(exc)}

    logger.info("[email dev-mode] To: %s | Subject: %s | %s", to, subject, body_text)
    return {"provider": "dev-log", "status": "queued"}


def send_welcome_email(to: str, full_name: str, business: dict | None = None) -> dict:
    """Welcome email sent to a business owner when they register."""
    site = f"https://{business['slug']}.wab.is" if business else "your booking website"
    body = (
        f"Hi {full_name},\n\n"
        "Welcome to WaveBook! Your account is ready and your 14-day free trial "
        "has started — every feature is included.\n\n"
        f"Your business is set up and your booking website is live at:\n{site}\n\n"
        "Next steps:\n"
        "1. Download the WaveBook app from the App Store (iPhone) or Google Play Store (Android).\n"
        "2. Open the app and log in with the email and password you just created.\n"
        "3. Add your services, opening hours and deposit settings.\n"
        "4. Share your booking website with customers to start receiving bookings.\n\n"
        "After the trial you can subscribe for £9.99/month on getwavebook.com/subscribe.\n\n"
        "Need help? Reply to this email or contact support@getwavebook.com.\n\n"
        "Best regards,\nThe WaveBook Team\n"
        "© 2026 NeuroWaves Data Systems Ltd"
    )
    return send_email(to, "Welcome to WaveBook — your 14-day free trial is active", body)


def _booking_manage_url() -> str:
    return f"{settings.API_PUBLIC_URL}/booking/manage"


def send_booking_confirmation_email(booking: dict, business: dict) -> dict:
    """Email the customer their booking confirmation with reference and manage link."""
    to = (booking.get("customer_email") or "").strip()
    if not to:
        return {"provider": "none", "status": "skipped", "reason": "no recipient"}
    reference = booking.get("reference") or ""
    body = (
        f"Hi {booking.get('customer_name', '')},\n\n"
        f"Your booking with {business.get('name', '')} is confirmed:\n"
        f"  Service: {booking.get('service_name', '')}\n"
        f"  Date: {booking.get('date', '')}\n"
        f"  Time: {booking.get('time', '')}\n"
        f"  Booking reference: {reference}\n\n"
        "Need to change or cancel? Use your email address and booking reference above at:\n"
        f"{_booking_manage_url()}\n\n"
        "We look forward to seeing you!\n"
        f"{business.get('name', '')}"
    )
    return send_email(to, f"Booking confirmed — {booking.get('service_name', '')}", body)


def send_booking_received_email(booking: dict, business: dict) -> dict:
    """Email the customer when their booking request is received (before owner confirmation)."""
    to = (booking.get("customer_email") or "").strip()
    if not to:
        return {"provider": "none", "status": "skipped", "reason": "no recipient"}
    reference = booking.get("reference") or ""
    body = (
        f"Hi {booking.get('customer_name', '')},\n\n"
        f"We've received your booking request with {business.get('name', '')}:\n"
        f"  Service: {booking.get('service_name', '')}\n"
        f"  Date: {booking.get('date', '')}\n"
        f"  Time: {booking.get('time', '')}\n"
        f"  Booking reference: {reference}\n\n"
        "The business will confirm shortly. Need to change or cancel? Use your email "
        f"address and booking reference above at:\n{_booking_manage_url()}\n\n"
        f"Thanks,\n{business.get('name', '')}"
    )
    return send_email(to, f"Booking received — {booking.get('service_name', '')}", body)


def send_booking_reminder_email(booking: dict, business: dict) -> dict:
    """Reminder email sent ahead of an upcoming appointment."""
    to = (booking.get("customer_email") or "").strip()
    if not to:
        return {"provider": "none", "status": "skipped", "reason": "no recipient"}
    body = (
        f"Hi {booking.get('customer_name', '')},\n\n"
        f"This is a friendly reminder about your upcoming appointment:\n"
        f"  Service: {booking.get('service_name', '')}\n"
        f"  Date: {booking.get('date', '')}\n"
        f"  Time: {booking.get('time', '')}\n"
        f"  Booking reference: {booking.get('reference', '')}\n\n"
        "Need to change or cancel? Use your email address and booking reference above at:\n"
        f"{_booking_manage_url()}\n\n"
        f"See you soon!\n{business.get('name', '')}"
    )
    return send_email(to, f"Reminder — {booking.get('service_name', '')} on {booking.get('date', '')}", body)
