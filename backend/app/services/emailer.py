"""Email delivery via the PHP relay on the NeuroWaves hosting.

The VPS POSTs JSON to NOTIFY_URL with the NOTIFY_TOKEN header; the PHP script
sends the mail with the hosting's mail(). When NOTIFY_TOKEN is not set, emails
are logged instead so the platform keeps working during development and testing.
"""
import json
import logging
import urllib.request

from ..config import settings
from ..database import get_connection, get_trial_days

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
    site = f"https://{business['slug']}.wab.ad" if business else "your booking website"
    body = (
        f"Hi {full_name},\n\n"
        f"Welcome to WaveBook! Your account is ready and your {get_trial_days()}-day free trial "
        "has started — every feature is included.\n\n"
        f"Your business is set up and your booking website is live at:\n{site}\n\n"
        "Next steps:\n"
        "1. Download the WaveBook app from the App Store (iPhone) or Google Play Store (Android).\n"
        "2. Open the app and log in with the email and password you just created.\n"
        "3. Add your services, opening hours and deposit settings.\n"
        "4. Share your booking website with customers to start receiving bookings.\n\n"
        "After the trial, choose a plan at getwavebook.com/subscribe.\n\n"
        "Need help? Reply to this email or contact support@getwavebook.com.\n\n"
        "Best regards,\nThe WaveBook Team\n"
        "© 2026 NeuroWaves Data Systems Ltd"
    )
    return send_email(to, f"Welcome to WaveBook — your {get_trial_days()}-day free trial is active", body)


def send_password_reset_email(to: str, full_name: str, temp_password: str) -> dict:
    """Send a temporary password after a password reset request."""
    body = (
        f"Hi {full_name},\n\n"
        "You asked to reset your WaveBook password. Here is your temporary password:\n\n"
        f"  {temp_password}\n\n"
        "Sign in with this temporary password — you'll be asked to set a new password "
        "the first time you log in.\n\n"
        "If you didn't request this, you can ignore this email and your password will "
        "stay the same.\n\n"
        "Need help? Reply to this email or contact support@getwavebook.com.\n\n"
        "Best regards,\nThe WaveBook Team\n"
        "© 2026 NeuroWaves Data Systems Ltd"
    )
    return send_email(to, "Your WaveBook temporary password", body)


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


def _owner_address(business: dict) -> str:
    """The business contact email, falling back to the owner's account email."""
    contact = (business.get("contact_email") or "").strip()
    if contact:
        return contact
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT email FROM users WHERE business_id = ? AND role = 'owner' ORDER BY id LIMIT 1",
            (business["id"],),
        ).fetchone()
    finally:
        conn.close()
    return row["email"] if row else ""


def send_owner_new_booking_email(booking: dict, business: dict) -> dict:
    """Email the business owner when a new booking is received."""
    to = _owner_address(business)
    if not to:
        return {"provider": "none", "status": "skipped", "reason": "no owner email"}
    body = (
        f"You have a new booking for {business.get('name', '')}:\n\n"
        f"  Customer: {booking.get('customer_name', '')}\n"
        f"  Email: {booking.get('customer_email', '')}\n"
        f"  Phone: {booking.get('customer_phone', '')}\n"
        f"  Service: {booking.get('service_name', '')}\n"
        f"  Date: {booking.get('date', '')}\n"
        f"  Time: {booking.get('time', '')}\n"
        f"  Booking reference: {booking.get('reference', '')}\n"
    )
    if booking.get("notes"):
        body += f"  Notes: {booking['notes']}\n"
    body += "\nManage it in the WaveBook app.\n\nWaveBook"
    return send_email(
        to,
        f"New booking — {booking.get('service_name', '')} on {booking.get('date', '')} at {booking.get('time', '')}",
        body,
    )


def _order_items(order: dict) -> list:
    try:
        return json.loads(order.get("items") or "[]")
    except json.JSONDecodeError:
        return []


def send_order_paid_emails(order: dict, business: dict) -> None:
    """Email the customer a receipt and the business owner a new paid order."""
    name = business.get("name", "")
    lines = "\n".join(f"  {i.get('name', 'item')} x{i.get('quantity', 1)}" for i in _order_items(order))
    total = f"£{float(order.get('total') or 0):.2f}"
    order_no = order.get("id", "")
    customer_to = (order.get("customer_email") or "").strip()
    if customer_to:
        send_email(
            customer_to,
            f"Order #{order_no} confirmed — {name}",
            (
                f"Hi {order.get('customer_name', '')},\n\n"
                f"Thank you for your order from {name}. Your payment has been received:\n\n"
                f"{lines}\n\n"
                f"  Total: {total}\n"
                f"  Order number: {order_no}\n\n"
                f"{name} will be in touch about delivery or collection.\n\n"
                f"{name}"
            ),
        )
    owner_to = _owner_address(business)
    if owner_to:
        send_email(
            owner_to,
            f"New paid order #{order_no} — {total}",
            (
                f"You have a new paid order for {name}:\n\n"
                f"  Customer: {order.get('customer_name', '')}\n"
                f"  Email: {order.get('customer_email', '')}\n"
                f"  Phone: {order.get('customer_phone', '')}\n\n"
                f"{lines}\n\n"
                f"  Total: {total}\n\n"
                "Manage it in the WaveBook app.\n\nWaveBook"
            ),
        )


def send_staff_invite_email(to: str, full_name: str, business_name: str, temp_password: str | None) -> dict:
    """Tell a staff member they were added to a business, with login details for new accounts."""
    if temp_password:
        login = (
            f"Your login details:\n"
            f"  Email: {to}\n"
            f"  Temporary password: {temp_password}\n\n"
            "Sign in and keep this password private.\n\n"
        )
    else:
        login = "Sign in with your existing WaveBook email and password.\n\n"
    body = (
        f"Hi {full_name},\n\n"
        f"{business_name} has added you as a staff member on WaveBook.\n\n"
        f"{login}"
        "Download the WaveBook app from the App Store or Google Play and sign in.\n\n"
        "WaveBook"
    )
    return send_email(to, f"You've been added to {business_name} on WaveBook", body)


def send_booking_assigned_email(booking: dict, business: dict, staff_email: str, staff_name: str) -> dict:
    """Tell a staff member a booking has been assigned to them."""
    body = (
        f"Hi {staff_name},\n\n"
        f"A booking at {business.get('name', '')} has been assigned to you:\n"
        f"  Customer: {booking.get('customer_name', '')}\n"
        f"  Phone: {booking.get('customer_phone', '')}\n"
        f"  Service: {booking.get('service_name', '')}\n"
        f"  Date: {booking.get('date', '')}\n"
        f"  Time: {booking.get('time', '')}\n"
        f"  Booking reference: {booking.get('reference', '')}\n\n"
        "Open the WaveBook app to see your assigned bookings.\n\n"
        "WaveBook"
    )
    return send_email(
        staff_email,
        f"Booking assigned to you — {booking.get('service_name', '')} on {booking.get('date', '')}",
        body,
    )
