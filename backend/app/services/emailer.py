"""Email delivery via SMTP.

Uses SMTP settings when configured; otherwise falls back to a console log so
the platform keeps working during development and testing.
"""
import logging
import smtplib
from email.message import EmailMessage

from ..config import settings

logger = logging.getLogger("wavebook")


def send_email(to: str, subject: str, body_text: str) -> dict:
    """Send a plain-text email. Returns delivery info."""
    if not to:
        return {"provider": "none", "status": "skipped", "reason": "no recipient"}

    if settings.SMTP_HOST:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM or "WaveBook <no-reply@getwavebook.com>"
        msg["To"] = to
        msg.set_content(body_text)
        try:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
                if settings.SMTP_USER:
                    server.starttls()
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.send_message(msg)
            return {"provider": "smtp", "status": "sent", "to": to}
        except Exception as exc:  # pragma: no cover
            logger.error("[email] send failed: %s", exc)
            return {"provider": "smtp", "status": "error", "error": str(exc)}

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
